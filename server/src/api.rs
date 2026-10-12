// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

//! Maps the method names posted by the web frontend onto backend calls.

use anki::backend::Backend;
use anki_proto::backend::backend_error::Kind;
use anki_proto::backend::BackendError;
use anki_proto::generic;
use prost::Message;

include!(concat!(env!("OUT_DIR"), "/methods.rs"));

/// The backend methods a web client may call. Anything else, such as opening
/// a different collection or running raw database commands, is refused.
const EXPOSED_METHODS: &[&str] = &[
    // CollectionService
    "latestProgress",
    // ConfigService
    "getConfigJson",
    "setConfigJson",
    "getConfigBool",
    // DeckService
    "deckTree",
    "getDeckNames",
    "getDeck",
    "setCurrentDeck",
    // I18nService
    "i18nResources",
    // NotetypesService
    "getNotetype",
    "getNotetypeNames",
    // NotesService
    "getFieldNames",
    "getNote",
    // StatsService
    "cardStats",
    "getReviewLogs",
    "graphs",
    "getGraphPreferences",
    "setGraphPreferences",
];

#[derive(Debug, PartialEq, Eq)]
pub(crate) enum ApiError {
    /// The method does not exist, or web clients may not call it.
    UnknownMethod,
    /// The backend ran the method and it failed; holds the localized message.
    Backend(String),
}

/// Runs `method` with the protobuf-encoded `input`, returning the encoded
/// response.
pub(crate) fn call(backend: &Backend, method: &str, input: &[u8]) -> Result<Vec<u8>, ApiError> {
    if !EXPOSED_METHODS.contains(&method) {
        return Err(ApiError::UnknownMethod);
    }
    match run(backend, method, input) {
        // the frontend expects a missing config key to read as null
        Err(err) if method == "getConfigJson" && err.kind() == Kind::NotFoundError => {
            let null = generic::Json {
                json: b"null".to_vec(),
            };
            Ok(null.encode_to_vec())
        }
        Err(err) => Err(ApiError::Backend(err.message)),
        Ok(output) => Ok(output),
    }
}

/// Runs any backend method, bypassing the list of exposed ones.
pub(crate) fn run(backend: &Backend, method: &str, input: &[u8]) -> Result<Vec<u8>, BackendError> {
    let Some((service, method)) = backend_method(method) else {
        return Err(BackendError {
            message: format!("no such method: {method}"),
            ..Default::default()
        });
    };
    backend
        .run_service_method(service, method, input)
        .map_err(|bytes| {
            BackendError::decode(bytes.as_slice()).unwrap_or_else(|_| BackendError {
                message: "backend returned an unreadable error".into(),
                ..Default::default()
            })
        })
}

#[cfg(test)]
mod tests {
    use anki_proto::decks::DeckTreeNode;
    use anki_proto::decks::DeckTreeRequest;
    use tempfile::TempDir;

    use super::*;
    use crate::open_backend;

    fn backend_with_new_collection() -> (Backend, TempDir) {
        let dir = tempfile::tempdir().unwrap();
        let backend = open_backend(&dir.path().join("collection.anki2")).unwrap();
        (backend, dir)
    }

    #[test]
    fn exposed_methods_all_exist_in_backend() {
        for method in EXPOSED_METHODS {
            assert!(backend_method(method).is_some(), "{method} is not known");
        }
    }

    #[test]
    fn call_returns_backend_response_for_exposed_method() {
        let (backend, _dir) = backend_with_new_collection();

        let output = call(
            &backend,
            "deckTree",
            &DeckTreeRequest { now: 0 }.encode_to_vec(),
        );

        let tree = DeckTreeNode::decode(output.unwrap().as_slice()).unwrap();
        let names: Vec<_> = tree.children.iter().map(|deck| &deck.name).collect();
        assert_eq!(names, ["Default"]);
    }

    #[test]
    fn call_refuses_backend_method_that_is_not_exposed() {
        let (backend, _dir) = backend_with_new_collection();

        let output = call(&backend, "closeCollection", &[]);

        assert_eq!(output, Err(ApiError::UnknownMethod));
    }

    #[test]
    fn call_reads_missing_config_key_as_null() {
        let (backend, _dir) = backend_with_new_collection();
        let key = generic::String {
            val: "llm.exercises".into(),
        };

        let output = call(&backend, "getConfigJson", &key.encode_to_vec());

        let json = generic::Json::decode(output.unwrap().as_slice()).unwrap();
        assert_eq!(json.json, b"null");
    }

    #[test]
    fn call_reports_backend_failure_with_its_message() {
        let (backend, _dir) = backend_with_new_collection();
        let missing_deck = anki_proto::decks::DeckId { did: 12345 };

        let output = call(&backend, "getDeck", &missing_deck.encode_to_vec());

        assert!(
            matches!(&output, Err(ApiError::Backend(message)) if !message.is_empty()),
            "{output:?}"
        );
    }
}
