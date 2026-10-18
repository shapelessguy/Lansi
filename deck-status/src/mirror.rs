// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

//! A local copy of the collection that is kept up to date by syncing.

use std::path::Path;
use std::sync::mpsc;
use std::sync::Arc;
use std::sync::RwLock;
use std::time::Duration;
use std::time::SystemTime;
use std::time::UNIX_EPOCH;

use anki::backend::init_backend;
use anki::backend::Backend;
use anki_proto::backend::BackendInit;
use anki_proto::collection::OpenCollectionRequest;
use anki_proto::decks::DeckTreeNode;
use anki_proto::decks::DeckTreeRequest;
use anki_proto::generic::Empty;
use anki_proto::sync::sync_collection_response::ChangesRequired;
use anki_proto::sync::FullUploadOrDownloadRequest;
use anki_proto::sync::SyncAuth;
use anki_proto::sync::SyncCollectionRequest;
use anki_proto::sync::SyncCollectionResponse;
use anyhow::anyhow;
use anyhow::Context;
use anyhow::Result;
use prost::Message;

use crate::api;
use crate::status::decks_in_tree;
use crate::status::Status;

/// Empty until the first sync attempt has finished.
pub(crate) type SharedStatus = Arc<RwLock<Option<Status>>>;

/// Starts a backend with the collection at `collection_path` open, creating
/// the collection if it does not exist. Media goes in a folder next to it.
pub(crate) fn open_backend(collection_path: &Path) -> Result<Backend> {
    let init = BackendInit {
        preferred_langs: vec!["en".into()],
        ..Default::default()
    };
    let backend = init_backend(&init.encode_to_vec()).map_err(|err| anyhow!(err))?;
    let request = OpenCollectionRequest {
        collection_path: path_string(collection_path)?,
        media_folder_path: path_string(&media_folder(collection_path))?,
        media_db_path: path_string(&collection_path.with_extension("media.db2"))?,
    };
    api::run::<_, Empty>(&backend, "openCollection", &request)
        .map_err(|err| anyhow!(err))
        .with_context(|| format!("opening {}", collection_path.display()))?;
    Ok(backend)
}

pub(crate) fn media_folder(collection_path: &Path) -> std::path::PathBuf {
    collection_path.with_extension("media")
}

fn path_string(path: &Path) -> Result<String> {
    path.to_str()
        .map(str::to_owned)
        .with_context(|| format!("path is not valid UTF-8: {}", path.display()))
}

pub(crate) struct Mirror {
    backend: Backend,
    auth: SyncAuth,
    sync_media: bool,
    last_sync: Option<i64>,
    last_sync_error: Option<String>,
}

impl Mirror {
    pub(crate) fn new(backend: Backend, auth: SyncAuth, sync_media: bool) -> Self {
        Mirror {
            backend,
            auth,
            sync_media,
            last_sync: None,
            last_sync_error: None,
        }
    }

    /// Syncs and publishes the deck status every `interval`, until `stop`
    /// is dropped or sent to.
    pub(crate) fn run(
        mut self,
        interval: Duration,
        shared: SharedStatus,
        stop: mpsc::Receiver<()>,
    ) {
        loop {
            match self.sync() {
                Ok(()) => {
                    self.last_sync = Some(now());
                    self.last_sync_error = None;
                }
                Err(message) => {
                    eprintln!("sync failed: {message}");
                    self.last_sync_error = Some(message);
                }
            }
            // counted even when the sync failed, as the due counts change with
            // the time of day
            match self.status() {
                Ok(status) => *shared.write().unwrap() = Some(status),
                Err(message) => eprintln!("reading decks failed: {message}"),
            }
            if !matches!(
                stop.recv_timeout(interval),
                Err(mpsc::RecvTimeoutError::Timeout)
            ) {
                return;
            }
        }
    }

    fn sync(&mut self) -> Result<(), String> {
        let request = SyncCollectionRequest {
            auth: Some(self.auth.clone()),
            sync_media: self.sync_media,
        };
        let output: SyncCollectionResponse = api::run(&self.backend, "syncCollection", &request)?;
        // AnkiWeb moves accounts between hosts; later requests must go to the
        // new one
        if output.new_endpoint.is_some() {
            self.auth.endpoint = output.new_endpoint.clone();
        }
        // Nothing is edited here, so when the two sides can't be merged the
        // server's copy wins. If the server has no collection yet, there is
        // nothing to fetch.
        if matches!(
            output.required(),
            ChangesRequired::FullDownload | ChangesRequired::FullSync
        ) {
            let request = FullUploadOrDownloadRequest {
                auth: Some(self.auth.clone()),
                upload: false,
                server_usn: self.sync_media.then_some(output.server_media_usn),
            };
            api::run::<_, Empty>(&self.backend, "fullUploadOrDownload", &request)?;
        }
        Ok(())
    }

    fn status(&self) -> Result<Status, String> {
        let now = now();
        let tree: DeckTreeNode = api::run(&self.backend, "deckTree", &DeckTreeRequest { now })?;
        Ok(Status {
            last_sync: self.last_sync,
            last_sync_error: self.last_sync_error.clone(),
            counted_at: now,
            decks: decks_in_tree(&tree),
        })
    }
}

fn now() -> i64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_or(0, |elapsed| elapsed.as_secs() as i64)
}
