// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

//! Keeps the texts another application generates, and the speech made from
//! them, as files in a folder: `<id>.json` for the text and its details, and
//! `<id>.wav` or `<id>.mp3` for the audio.

use std::fs;
use std::path::Path;
use std::path::PathBuf;

use anki_io::create_dir_all;
use anki_io::read_file;
use anki_io::write_file;
use anyhow::bail;
use anyhow::Context;
use anyhow::Result;
use serde_json::Value;

/// The audio types that can be stored, with the extension each is saved under.
const AUDIO_TYPES: &[(&str, &str)] = &[("audio/wav", "wav"), ("audio/mpeg", "mp3")];

/// Ids become file names, so only characters that are safe in one are allowed.
pub(crate) fn is_valid_id(id: &str) -> bool {
    (1..=80).contains(&id.len())
        && id
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || c == '-' || c == '_')
}

fn checked(id: &str) -> Result<&str> {
    if !is_valid_id(id) {
        bail!("invalid id");
    }
    Ok(id)
}

/// Every stored text, in no particular order.
pub(crate) fn list(folder: &Path) -> Result<Vec<Value>> {
    let Ok(entries) = fs::read_dir(folder) else {
        // nothing has been saved yet
        return Ok(vec![]);
    };
    let mut texts = vec![];
    for entry in entries {
        let path = entry?.path();
        if path
            .extension()
            .is_some_and(|extension| extension == "json")
        {
            let text = serde_json::from_slice(&read_file(&path)?)
                .with_context(|| format!("reading {}", path.display()))?;
            texts.push(text);
        }
    }
    Ok(texts)
}

/// Stores the JSON object in `body` as the text with that id, replacing any
/// earlier version.
pub(crate) fn save_text(folder: &Path, id: &str, body: &[u8]) -> Result<()> {
    let id = checked(id)?;
    let text: Value = serde_json::from_slice(body).context("body is not JSON")?;
    if !text.is_object() {
        bail!("body must be a JSON object");
    }
    create_dir_all(folder)?;
    write_file(folder.join(format!("{id}.json")), body)?;
    Ok(())
}

/// Stores the audio for a text, replacing any earlier audio for it.
pub(crate) fn save_audio(folder: &Path, id: &str, content_type: &str, data: &[u8]) -> Result<()> {
    let id = checked(id)?;
    let Some((_, extension)) = AUDIO_TYPES.iter().find(|(kind, _)| *kind == content_type) else {
        bail!("unsupported audio type: {content_type}");
    };
    create_dir_all(folder)?;
    remove_audio(folder, id)?;
    write_file(folder.join(format!("{id}.{extension}")), data)?;
    Ok(())
}

/// The audio file stored for a text and its content type, if there is one.
pub(crate) fn audio(folder: &Path, id: &str) -> Option<(PathBuf, &'static str)> {
    if !is_valid_id(id) {
        return None;
    }
    AUDIO_TYPES.iter().find_map(|(kind, extension)| {
        let path = folder.join(format!("{id}.{extension}"));
        path.exists().then_some((path, *kind))
    })
}

/// Removes a text and its audio. Removing one that does not exist is fine.
pub(crate) fn delete(folder: &Path, id: &str) -> Result<()> {
    let id = checked(id)?;
    remove_if_present(&folder.join(format!("{id}.json")))?;
    remove_audio(folder, id)
}

fn remove_audio(folder: &Path, id: &str) -> Result<()> {
    for (_, extension) in AUDIO_TYPES {
        remove_if_present(&folder.join(format!("{id}.{extension}")))?;
    }
    Ok(())
}

fn remove_if_present(path: &Path) -> Result<()> {
    match fs::remove_file(path) {
        Err(err) if err.kind() != std::io::ErrorKind::NotFound => {
            Err(err).with_context(|| format!("removing {}", path.display()))
        }
        _ => Ok(()),
    }
}

#[cfg(test)]
mod tests {
    use serde_json::json;
    use tempfile::tempdir;

    use super::*;

    #[test]
    fn is_valid_id_accepts_names_made_of_letters_digits_dashes_and_underscores() {
        for id in ["2026-10-12-170501-der-film", "a", "Text_1"] {
            assert!(is_valid_id(id), "{id}");
        }
    }

    #[test]
    fn is_valid_id_rejects_names_that_could_leave_the_folder() {
        let long = "a".repeat(81);
        for id in [
            "", "..", "../hkey", "a/b", "a\\b", "a.json", "C:x", "a b", &long,
        ] {
            assert!(!is_valid_id(id), "{id}");
        }
    }

    #[test]
    fn list_is_empty_before_anything_is_saved() {
        let dir = tempdir().unwrap();

        let texts = list(&dir.path().join("texts")).unwrap();

        assert_eq!(texts, Vec::<Value>::new());
    }

    #[test]
    fn save_text_makes_the_text_appear_in_the_list() {
        let dir = tempdir().unwrap();
        let text = json!({ "id": "one", "title": "Der Film", "text": "Es war einmal…" });

        save_text(dir.path(), "one", text.to_string().as_bytes()).unwrap();

        assert_eq!(list(dir.path()).unwrap(), [text]);
    }

    #[test]
    fn save_text_replaces_the_earlier_version_with_the_same_id() {
        let dir = tempdir().unwrap();
        save_text(dir.path(), "one", br#"{"title": "old"}"#).unwrap();

        save_text(dir.path(), "one", br#"{"title": "new"}"#).unwrap();

        assert_eq!(list(dir.path()).unwrap(), [json!({ "title": "new" })]);
    }

    #[test]
    fn save_text_refuses_bodies_that_are_not_json_objects() {
        let dir = tempdir().unwrap();

        for body in ["not json", "[1, 2]", "\"text\""] {
            assert!(
                save_text(dir.path(), "one", body.as_bytes()).is_err(),
                "{body}"
            );
        }
        assert_eq!(list(dir.path()).unwrap(), Vec::<Value>::new());
    }

    #[test]
    fn save_text_refuses_ids_that_are_not_plain_names() {
        let dir = tempdir().unwrap();
        let folder = dir.path().join("texts");

        let result = save_text(&folder, "../escaped", b"{}");

        assert!(result.is_err());
        assert!(!dir.path().join("escaped.json").exists());
    }

    #[test]
    fn audio_returns_the_saved_file_with_its_content_type() {
        let dir = tempdir().unwrap();

        save_audio(dir.path(), "one", "audio/wav", b"RIFFdata").unwrap();

        let (path, content_type) = audio(dir.path(), "one").unwrap();
        assert_eq!(content_type, "audio/wav");
        assert_eq!(fs::read(path).unwrap(), b"RIFFdata");
    }

    #[test]
    fn save_audio_replaces_earlier_audio_of_another_type() {
        let dir = tempdir().unwrap();
        save_audio(dir.path(), "one", "audio/wav", b"wav").unwrap();

        save_audio(dir.path(), "one", "audio/mpeg", b"mp3").unwrap();

        let (path, content_type) = audio(dir.path(), "one").unwrap();
        assert_eq!(content_type, "audio/mpeg");
        assert_eq!(fs::read(path).unwrap(), b"mp3");
        assert!(!dir.path().join("one.wav").exists());
    }

    #[test]
    fn save_audio_refuses_types_that_are_not_audio() {
        let dir = tempdir().unwrap();

        let result = save_audio(dir.path(), "one", "text/html", b"<script>");

        assert!(result.is_err());
        assert!(audio(dir.path(), "one").is_none());
    }

    #[test]
    fn audio_is_none_for_a_text_without_any() {
        let dir = tempdir().unwrap();
        save_text(dir.path(), "one", b"{}").unwrap();

        assert!(audio(dir.path(), "one").is_none());
    }

    #[test]
    fn delete_removes_the_text_and_its_audio_but_not_other_texts() {
        let dir = tempdir().unwrap();
        save_text(dir.path(), "one", br#"{"id": "one"}"#).unwrap();
        save_audio(dir.path(), "one", "audio/wav", b"wav").unwrap();
        save_text(dir.path(), "two", br#"{"id": "two"}"#).unwrap();

        delete(dir.path(), "one").unwrap();

        assert_eq!(list(dir.path()).unwrap(), [json!({ "id": "two" })]);
        assert!(audio(dir.path(), "one").is_none());
    }

    #[test]
    fn delete_of_a_text_that_does_not_exist_succeeds() {
        let dir = tempdir().unwrap();

        delete(dir.path(), "missing").unwrap();
    }
}
