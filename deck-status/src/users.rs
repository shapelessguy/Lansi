// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

//! The collections of the users, each linked to a sync account of its own.
//!
//! A user's collection is kept in a folder named after the user, with the
//! sync key it was linked with; the password is only used to obtain the key
//! and is never kept. Linking a user starts a mirror of the account, and
//! unlinking stops it and removes the folder.

use std::collections::HashMap;
use std::path::Path;
use std::path::PathBuf;
use std::sync::mpsc;
use std::sync::Arc;
use std::sync::Mutex;
use std::time::Duration;

use anki::backend::init_backend;
use anki::backend::Backend;
use anki_io::create_dir_all;
use anki_io::read_to_string;
use anki_io::write_file;
use anki_proto::backend::BackendInit;
use anki_proto::collection::CloseCollectionRequest;
use anki_proto::generic::Empty;
use anki_proto::sync::SyncAuth;
use anki_proto::sync::SyncLoginRequest;
use anyhow::anyhow;
use anyhow::Context;
use anyhow::Result;
use prost::Message;

use crate::api;
use crate::mirror::media_folder;
use crate::mirror::open_backend;
use crate::mirror::Mirror;
use crate::mirror::SharedStatus;

const COLLECTION_FILE: &str = "collection.anki2";
const KEY_FILE: &str = "hkey";

/// The collection of a linked user, as the requests about it need it.
pub(crate) struct Linked {
    pub backend: Backend,
    pub status: SharedStatus,
    pub media_folder: PathBuf,
    /// Dropped to stop the mirror, which then removes the collection.
    stop: Mutex<Option<mpsc::Sender<()>>>,
}

/// Why a user could not be linked.
#[derive(Debug)]
pub(crate) enum LinkError {
    /// The name is not one a user can have.
    BadName,
    /// The user is linked already, or is still being unlinked.
    Taken,
    /// The sync server refused the login; the message says why.
    Refused(String),
    Failed(anyhow::Error),
}

pub(crate) struct Users {
    dir: PathBuf,
    /// A self-hosted sync server. AnkiWeb is used if unset.
    endpoint: Option<String>,
    interval: Duration,
    sync_media: bool,
    linked: Mutex<HashMap<String, Arc<Linked>>>,
    /// Held while a user is linked, so that two links can't make one folder.
    linking: Mutex<()>,
}

/// Names as the checker gives them to its users, which are safe to use as
/// the name of a folder.
pub(crate) fn is_user_name(name: &str) -> bool {
    (1..=40).contains(&name.len())
        && name
            .bytes()
            .all(|byte| byte.is_ascii_lowercase() || byte.is_ascii_digit() || byte == b'_')
}

impl Users {
    pub(crate) fn new(
        dir: PathBuf,
        endpoint: Option<String>,
        interval: Duration,
        sync_media: bool,
    ) -> Self {
        Users {
            dir,
            endpoint,
            interval,
            sync_media,
            linked: Mutex::default(),
            linking: Mutex::default(),
        }
    }

    /// Starts the mirror of every user that was linked before.
    pub(crate) fn load(&self) -> Result<()> {
        create_dir_all(&self.dir)?;
        for entry in std::fs::read_dir(&self.dir).context("listing the users")? {
            let entry = entry?;
            let Some(name) = entry.file_name().to_str().map(str::to_owned) else {
                continue;
            };
            let key_path = entry.path().join(KEY_FILE);
            if !is_user_name(&name) || !key_path.exists() {
                continue;
            }
            let hkey = read_to_string(&key_path)?.trim().to_owned();
            self.start(&name, hkey)
                .with_context(|| format!("starting the collection of {name}"))?;
            println!("Mirroring the collection of {name}");
        }
        Ok(())
    }

    pub(crate) fn get(&self, name: &str) -> Option<Arc<Linked>> {
        self.linked.lock().unwrap().get(name).cloned()
    }

    /// Logs in to the sync account of `username` and starts mirroring its
    /// collection for `name`. Blocks while logging in.
    pub(crate) fn link(
        &self,
        name: &str,
        username: String,
        password: String,
    ) -> Result<(), LinkError> {
        if !is_user_name(name) {
            return Err(LinkError::BadName);
        }
        let _linking = self.linking.lock().unwrap();
        // a folder without a mirror is one still being removed
        if self.get(name).is_some() || self.folder(name).exists() {
            return Err(LinkError::Taken);
        }
        let request = SyncLoginRequest {
            username,
            password,
            endpoint: self.endpoint.clone(),
        };
        let auth: SyncAuth = api::run(
            &login_backend().map_err(LinkError::Failed)?,
            "syncLogin",
            &request,
        )
        .map_err(LinkError::Refused)?;
        let started = create_dir_all(self.folder(name))
            .map_err(anyhow::Error::from)
            .and_then(|()| Ok(write_file(self.folder(name).join(KEY_FILE), &auth.hkey)?))
            .and_then(|()| self.start(name, auth.hkey));
        if let Err(err) = started {
            let _ = std::fs::remove_dir_all(self.folder(name));
            return Err(LinkError::Failed(err));
        }
        println!("Linked the collection of {name}");
        Ok(())
    }

    /// Stops mirroring the collection of `name`, which is then removed.
    /// Returns whether there was one.
    pub(crate) fn unlink(&self, name: &str) -> bool {
        let Some(linked) = self.linked.lock().unwrap().remove(name) else {
            return false;
        };
        linked.stop.lock().unwrap().take();
        println!("Unlinked the collection of {name}");
        true
    }

    fn folder(&self, name: &str) -> PathBuf {
        self.dir.join(name)
    }

    fn start(&self, name: &str, hkey: String) -> Result<()> {
        let folder = self.folder(name);
        let collection_path = folder.join(COLLECTION_FILE);
        let backend = open_backend(&collection_path)?;
        let auth = SyncAuth {
            hkey,
            endpoint: self.endpoint.clone(),
            io_timeout_secs: None,
        };
        let (stop, stopped) = mpsc::channel();
        let linked = Arc::new(Linked {
            backend: backend.clone(),
            status: SharedStatus::default(),
            media_folder: media_folder(&collection_path),
            stop: Mutex::new(Some(stop)),
        });
        let mirror = Mirror::new(backend.clone(), auth, self.sync_media);
        let (interval, shared) = (self.interval, linked.status.clone());
        let user = name.to_owned();
        std::thread::spawn(move || {
            mirror.run(interval, shared, stopped);
            if let Err(err) = remove(&backend, &folder) {
                eprintln!("removing the collection of {user} failed: {err:#}");
            }
        });
        self.linked.lock().unwrap().insert(name.to_owned(), linked);
        Ok(())
    }
}

/// A backend without a collection, which is all logging in needs.
fn login_backend() -> Result<Backend> {
    let init = BackendInit {
        preferred_langs: vec!["en".into()],
        ..Default::default()
    };
    init_backend(&init.encode_to_vec()).map_err(|err| anyhow!(err))
}

/// Closes the collection of an unlinked user and removes its folder.
fn remove(backend: &Backend, folder: &Path) -> Result<()> {
    let request = CloseCollectionRequest {
        downgrade_to_schema11: false,
    };
    api::run::<_, Empty>(backend, "closeCollection", &request).map_err(|err| anyhow!(err))?;
    std::fs::remove_dir_all(folder).with_context(|| format!("removing {}", folder.display()))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn is_user_name_accepts_the_names_the_checker_gives() {
        for name in ["ada", "cian_cl", "user_2", "a"] {
            assert!(is_user_name(name), "{name}");
        }
    }

    #[test]
    fn is_user_name_rejects_names_that_are_not_a_plain_folder() {
        let long = "a".repeat(41);
        for name in ["", "..", "Ada", "a/b", "a\\b", "a.b", "a b", long.as_str()] {
            assert!(!is_user_name(name), "{name}");
        }
    }

    #[test]
    fn unlink_says_there_was_nothing_when_the_user_was_never_linked() {
        let dir = tempfile::tempdir().unwrap();
        let users = Users::new(dir.path().into(), None, Duration::from_secs(60), false);

        assert!(!users.unlink("ada"));
        assert!(users.get("ada").is_none());
    }

    #[test]
    fn link_refuses_a_name_that_is_not_one() {
        let dir = tempfile::tempdir().unwrap();
        let users = Users::new(dir.path().into(), None, Duration::from_secs(60), false);

        let result = users.link("../ada", "a@b.c".into(), "pw".into());

        assert!(matches!(result, Err(LinkError::BadName)));
    }

    #[test]
    fn link_refuses_a_user_whose_folder_is_still_being_removed() {
        let dir = tempfile::tempdir().unwrap();
        std::fs::create_dir(dir.path().join("ada")).unwrap();
        let users = Users::new(dir.path().into(), None, Duration::from_secs(60), false);

        let result = users.link("ada", "a@b.c".into(), "pw".into());

        assert!(matches!(result, Err(LinkError::Taken)));
    }

    #[test]
    fn load_passes_over_folders_that_were_never_linked() {
        let dir = tempfile::tempdir().unwrap();
        std::fs::create_dir(dir.path().join("ada")).unwrap();
        std::fs::create_dir(dir.path().join("Not A User")).unwrap();
        let users = Users::new(dir.path().into(), None, Duration::from_secs(60), false);

        users.load().unwrap();

        assert!(users.get("ada").is_none());
    }
}
