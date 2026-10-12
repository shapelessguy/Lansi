// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

//! Locates the built frontend's files on disk.

use std::path::Path;
use std::path::PathBuf;

/// The page every route falls back to; the frontend does its own routing.
const FALLBACK_PAGE: &str = "index.html";

/// The file to serve for `url_path`: the matching file under `root` if there
/// is one, and the frontend's entry page otherwise.
pub(crate) fn resolve(root: &Path, url_path: &str) -> PathBuf {
    file_under_root(root, url_path).unwrap_or_else(|| root.join(FALLBACK_PAGE))
}

fn file_under_root(root: &Path, url_path: &str) -> Option<PathBuf> {
    let mut path = root.to_path_buf();
    for component in url_path.split('/').filter(|c| !c.is_empty()) {
        // refuse anything that could step outside of the root
        if component == "." || component == ".." || component.contains(['\\', ':']) {
            return None;
        }
        path.push(component);
    }
    path.is_file().then_some(path)
}

pub(crate) fn content_type(path: &Path) -> &'static str {
    match path.extension().and_then(|ext| ext.to_str()) {
        Some("html") => "text/html; charset=utf-8",
        Some("js" | "mjs") => "text/javascript; charset=utf-8",
        Some("css") => "text/css; charset=utf-8",
        Some("json" | "map") => "application/json",
        Some("svg") => "image/svg+xml",
        Some("png") => "image/png",
        Some("jpg" | "jpeg") => "image/jpeg",
        Some("ico") => "image/x-icon",
        Some("woff2") => "font/woff2",
        Some("woff") => "font/woff",
        Some("ttf") => "font/ttf",
        _ => "application/octet-stream",
    }
}

#[cfg(test)]
mod tests {
    use std::fs;

    use tempfile::TempDir;

    use super::*;

    /// A frontend build, next to a file that must never be served.
    fn site() -> (TempDir, PathBuf) {
        let dir = tempfile::tempdir().unwrap();
        let root = dir.path().join("site");
        fs::create_dir_all(root.join("_app/immutable")).unwrap();
        fs::write(root.join("index.html"), "").unwrap();
        fs::write(root.join("_app/immutable/start.mjs"), "").unwrap();
        fs::write(dir.path().join("secret.txt"), "").unwrap();
        (dir, root)
    }

    #[test]
    fn resolve_returns_existing_file() {
        let (_dir, root) = site();

        let path = resolve(&root, "/_app/immutable/start.mjs");

        assert_eq!(path, root.join("_app").join("immutable").join("start.mjs"));
    }

    #[test]
    fn resolve_falls_back_to_entry_page_for_frontend_routes() {
        let (_dir, root) = site();

        assert_eq!(resolve(&root, "/decks"), root.join("index.html"));
        assert_eq!(resolve(&root, "/"), root.join("index.html"));
    }

    #[test]
    fn resolve_never_leaves_the_root() {
        let (_dir, root) = site();

        for url_path in [
            "/../secret.txt",
            "/_app/../../secret.txt",
            "/..\\secret.txt",
        ] {
            assert_eq!(
                resolve(&root, url_path),
                root.join("index.html"),
                "{url_path}"
            );
        }
    }

    #[test]
    fn content_type_marks_modules_as_javascript() {
        assert_eq!(
            content_type(Path::new("start.mjs")),
            "text/javascript; charset=utf-8"
        );
    }
}
