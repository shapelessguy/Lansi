// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

//! Lets other applications call the backend methods the Anki GUI reads its
//! data from, with JSON in place of protobuf, and run read-only SQL.

use std::sync::LazyLock;

use anki::backend::Backend;
use anki_proto::backend::BackendError;
use prost::Message;
use prost_reflect::DescriptorPool;
use prost_reflect::DynamicMessage;
use prost_reflect::MessageDescriptor;
use prost_reflect::SerializeOptions;
use serde::Deserialize;
use serde::Serialize;
use serde_json::json;

pub(crate) struct Method {
    service: u32,
    method: u32,
    /// Full names of the protobuf messages, e.g. `anki.decks.DeckTreeNode`.
    input: &'static str,
    output: &'static str,
}

include!(concat!(env!("OUT_DIR"), "/methods.rs"));

static DESCRIPTORS: LazyLock<DescriptorPool> = LazyLock::new(|| {
    let bytes: &[u8] = include_bytes!(concat!(env!("OUT_DIR"), "/descriptors.bin"));
    DescriptorPool::decode(bytes).expect("descriptors were checked at build time")
});

/// The backend methods other applications may call. Only ones that look
/// things up are listed, as any change made here would be synced to the
/// user's other devices.
const READ_METHODS: &[&str] = &[
    // CardsService
    "getCard",
    // CardRenderingService
    "renderExistingCard",
    // ConfigService
    "getConfigBool",
    "getConfigString",
    "getPreferences",
    // DeckConfigService
    "getDeckConfig",
    "getDeckConfigsForUpdate",
    // DecksService
    "deckTree",
    "getCurrentDeck",
    "getDeck",
    "getDeckAndChildNames",
    "getDeckIdByName",
    "getDeckNames",
    // NotesService
    "cardsOfNote",
    "clozeNumbersInNote",
    "fieldNamesForNotes",
    "getNote",
    // NotetypesService
    "getClozeFieldOrds",
    "getFieldNames",
    "getNotetype",
    "getNotetypeIdByName",
    "getNotetypeNames",
    "getNotetypeNamesAndCounts",
    // SchedulerService
    "congratsInfo",
    "countsForDeckToday",
    "describeNextStates",
    "getQueuedCards",
    "getSchedulingStates",
    "schedTimingToday",
    "studiedToday",
    "studiedTodayMessage",
    // SearchService
    "allBrowserColumns",
    "browserRowForId",
    "buildSearchString",
    "searchCards",
    "searchNotes",
    // StatsService
    "cardStats",
    "getGraphPreferences",
    "getReviewLogs",
    "graphs",
    // TagsService
    "allTags",
    "completeTag",
    "tagTree",
];

#[derive(Debug, PartialEq, Eq)]
pub(crate) enum ApiError {
    /// The method does not exist, or other applications may not call it.
    UnknownMethod,
    /// The request could not be understood; holds the reason.
    BadRequest(String),
    /// The backend ran the request and it failed; holds its message.
    Backend(String),
}

#[derive(Serialize)]
pub(crate) struct MethodInfo {
    name: &'static str,
    input: &'static str,
    output: &'static str,
}

/// Describes each method that [call_json] accepts.
pub(crate) fn methods() -> Vec<MethodInfo> {
    READ_METHODS
        .iter()
        .filter_map(|name| {
            backend_method(name).map(|method| MethodInfo {
                name,
                input: method.input,
                output: method.output,
            })
        })
        .collect()
}

/// Runs `method` with the JSON form of its protobuf input, returning the JSON
/// form of its output. An empty `body` stands for an input with no fields set.
pub(crate) fn call_json(backend: &Backend, method: &str, body: &[u8]) -> Result<Vec<u8>, ApiError> {
    if !READ_METHODS.contains(&method) {
        return Err(ApiError::UnknownMethod);
    }
    let method = backend_method(method).ok_or(ApiError::UnknownMethod)?;
    let input = json_to_proto(message(method.input), body)?;
    let output = run_bytes(backend, &method, &input).map_err(ApiError::Backend)?;
    proto_to_json(message(method.output), &output)
}

/// Runs any backend method, bypassing the list of ones open to other
/// applications.
pub(crate) fn run<I, O>(backend: &Backend, method: &str, input: &I) -> Result<O, String>
where
    I: Message,
    O: Message + Default,
{
    let method = backend_method(method).ok_or_else(|| format!("no such method: {method}"))?;
    let output = run_bytes(backend, &method, &input.encode_to_vec())?;
    O::decode(output.as_slice()).map_err(|err| err.to_string())
}

#[derive(Deserialize)]
struct SqlRequest {
    sql: String,
    #[serde(default)]
    args: Vec<serde_json::Value>,
}

/// Runs the select statement in a `{"sql": ..., "args": [...]}` request
/// against the collection, returning the rows as a JSON array of arrays.
pub(crate) fn query(backend: &Backend, body: &[u8]) -> Result<Vec<u8>, ApiError> {
    let request: SqlRequest =
        serde_json::from_slice(body).map_err(|err| ApiError::BadRequest(err.to_string()))?;
    if !is_select(&request.sql) {
        return Err(ApiError::BadRequest(
            "only select statements are allowed".into(),
        ));
    }
    let command = json!({
        "kind": "query",
        "sql": request.sql,
        "args": request.args,
        "first_row_only": false,
    });
    backend
        .run_db_command_bytes(command.to_string().as_bytes())
        .map_err(|bytes| ApiError::Backend(error_message(&bytes)))
}

fn is_select(sql: &str) -> bool {
    sql.trim_start()
        .get(..6)
        .is_some_and(|start| start.eq_ignore_ascii_case("select"))
}

fn run_bytes(backend: &Backend, method: &Method, input: &[u8]) -> Result<Vec<u8>, String> {
    backend
        .run_service_method(method.service, method.method, input)
        .map_err(|bytes| error_message(&bytes))
}

fn error_message(bytes: &[u8]) -> String {
    match BackendError::decode(bytes) {
        Ok(err) => err.message,
        Err(_) => "backend returned an unreadable error".into(),
    }
}

fn message(full_name: &str) -> MessageDescriptor {
    DESCRIPTORS
        .get_message_by_name(full_name)
        .expect("method table and descriptors come from the same build")
}

fn json_to_proto(descriptor: MessageDescriptor, body: &[u8]) -> Result<Vec<u8>, ApiError> {
    if body.iter().all(u8::is_ascii_whitespace) {
        return Ok(vec![]);
    }
    let mut deserializer = serde_json::Deserializer::from_slice(body);
    let message = DynamicMessage::deserialize(descriptor, &mut deserializer)
        .and_then(|message| deserializer.end().map(|_| message))
        .map_err(|err| ApiError::BadRequest(err.to_string()))?;
    Ok(message.encode_to_vec())
}

fn proto_to_json(descriptor: MessageDescriptor, bytes: &[u8]) -> Result<Vec<u8>, ApiError> {
    let message = DynamicMessage::decode(descriptor, bytes)
        .map_err(|err| ApiError::Backend(err.to_string()))?;
    // ids are written as plain numbers, and fields keep the names the .proto
    // files give them
    let options = SerializeOptions::new()
        .stringify_64_bit_integers(false)
        .use_proto_field_name(true)
        .skip_default_fields(false);
    let mut json = vec![];
    message
        .serialize_with_options(&mut serde_json::Serializer::new(&mut json), &options)
        .map_err(|err| ApiError::Backend(err.to_string()))?;
    Ok(json)
}

#[cfg(test)]
mod tests {
    use serde_json::Value;
    use tempfile::TempDir;

    use super::*;
    use crate::mirror::open_backend;

    fn backend_with_new_collection() -> (Backend, TempDir) {
        let dir = tempfile::tempdir().unwrap();
        let backend = open_backend(&dir.path().join("collection.anki2")).unwrap();
        (backend, dir)
    }

    fn json(bytes: Vec<u8>) -> Value {
        serde_json::from_slice(&bytes).unwrap()
    }

    #[test]
    fn read_methods_all_exist_in_backend() {
        for method in READ_METHODS {
            assert!(backend_method(method).is_some(), "{method} is not known");
        }
    }

    #[test]
    fn call_json_returns_backend_response_with_proto_field_names() {
        let (backend, _dir) = backend_with_new_collection();

        let output = call_json(&backend, "deckTree", br#"{"now": 0}"#);

        let tree = json(output.unwrap());
        assert_eq!(tree["children"][0]["name"], "Default");
        assert_eq!(tree["children"][0]["deck_id"], 1);
    }

    #[test]
    fn call_json_treats_empty_body_as_input_without_fields() {
        let (backend, _dir) = backend_with_new_collection();

        let output = call_json(&backend, "getNotetypeNames", b"");

        let names = json(output.unwrap());
        assert!(
            names["entries"]
                .as_array()
                .unwrap()
                .iter()
                .any(|entry| entry["name"] == "Basic"),
            "{names}"
        );
    }

    #[test]
    fn call_json_refuses_backend_method_that_changes_the_collection() {
        let (backend, _dir) = backend_with_new_collection();

        let output = call_json(&backend, "removeNotes", b"{}");

        assert_eq!(output, Err(ApiError::UnknownMethod));
    }

    #[test]
    fn call_json_rejects_body_that_does_not_match_the_input_message() {
        let (backend, _dir) = backend_with_new_collection();

        let output = call_json(&backend, "deckTree", br#"{"no_such_field": 1}"#);

        assert!(matches!(output, Err(ApiError::BadRequest(_))), "{output:?}");
    }

    #[test]
    fn call_json_reports_backend_failure_with_its_message() {
        let (backend, _dir) = backend_with_new_collection();

        let output = call_json(&backend, "getDeck", br#"{"did": 12345}"#);

        assert!(
            matches!(&output, Err(ApiError::Backend(message)) if !message.is_empty()),
            "{output:?}"
        );
    }

    #[test]
    fn query_returns_rows_for_select_with_args() {
        let (backend, _dir) = backend_with_new_collection();
        let request =
            br#"{"sql": "select id, name from notetypes where name = ?", "args": ["Basic"]}"#;

        let output = query(&backend, request);

        let rows = json(output.unwrap());
        assert_eq!(rows.as_array().unwrap().len(), 1, "{rows}");
        assert_eq!(rows[0][1], "Basic");
    }

    #[test]
    fn query_refuses_statements_other_than_select() {
        let (backend, _dir) = backend_with_new_collection();
        let statements = [
            "delete from notetypes",
            "  UPDATE notetypes set name = 'x'",
            "pragma journal_mode = delete",
            "",
        ];

        for sql in statements {
            let request = json!({ "sql": sql }).to_string();

            let output = query(&backend, request.as_bytes());

            assert!(matches!(output, Err(ApiError::BadRequest(_))), "{sql}");
        }
        let remaining = query(&backend, br#"{"sql": "SELECT count(*) from notetypes"}"#);
        assert_ne!(json(remaining.unwrap())[0][0], 0);
    }
}
