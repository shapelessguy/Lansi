// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

//! A standalone server that hosts a collection and serves the web frontend,
//! so the frontend can be used from a browser instead of the desktop app.

mod api;
mod static_files;

use std::fs;
use std::net::IpAddr;
use std::net::Ipv4Addr;
use std::net::SocketAddr;
use std::path::Path as FsPath;
use std::path::PathBuf;

use anki::backend::init_backend;
use anki::backend::Backend;
use anki_proto::backend::BackendInit;
use anki_proto::collection::OpenCollectionRequest;
use anyhow::anyhow;
use anyhow::Context;
use anyhow::Result;
use axum::body::Bytes;
use axum::extract::Path;
use axum::extract::State;
use axum::http::header::CONTENT_TYPE;
use axum::http::HeaderMap;
use axum::http::StatusCode;
use axum::http::Uri;
use axum::response::IntoResponse;
use axum::response::Redirect;
use axum::response::Response;
use axum::routing::get;
use axum::routing::post;
use axum::Router;
use prost::Message;
use serde::Deserialize;
use tokio::net::TcpListener;

use crate::api::ApiError;

/// The content type the frontend posts with. Browsers can't send it
/// cross-origin without a preflight, so requiring it keeps other sites from
/// calling the API.
const API_CONTENT_TYPE: &str = "application/binary";

/// Read from environment variables prefixed with `ANKI_WEB_`.
#[derive(Deserialize, Debug)]
struct Config {
    /// Path to the .anki2 file to serve. Created if it does not exist.
    collection: PathBuf,
    /// Folder holding the built frontend.
    #[serde(default = "default_static_dir")]
    static_dir: PathBuf,
    #[serde(default = "default_host")]
    host: IpAddr,
    #[serde(default = "default_port")]
    port: u16,
}

fn default_static_dir() -> PathBuf {
    "out/sveltekit".into()
}

/// There is no authentication yet, so only local connections are accepted
/// unless told otherwise.
fn default_host() -> IpAddr {
    Ipv4Addr::LOCALHOST.into()
}

fn default_port() -> u16 {
    8080
}

#[derive(Clone)]
struct AppState {
    backend: Backend,
    static_dir: PathBuf,
}

#[tokio::main]
async fn main() -> Result<()> {
    let config: Config = envy::prefixed("ANKI_WEB_")
        .from_env()
        .context("reading ANKI_WEB_* environment variables")?;
    let state = AppState {
        backend: open_backend(&config.collection)?,
        static_dir: config.static_dir,
    };
    let app = Router::new()
        .route("/", get(|| async { Redirect::temporary("/decks") }))
        .route("/_anki/{method}", post(api_request))
        .fallback(get(static_file))
        .with_state(state);

    let addr = SocketAddr::new(config.host, config.port);
    let listener = TcpListener::bind(addr)
        .await
        .with_context(|| format!("listening on {addr}"))?;
    println!("Serving on http://{addr}");
    axum::serve(listener, app)
        .with_graceful_shutdown(async {
            let _ = tokio::signal::ctrl_c().await;
        })
        .await?;
    Ok(())
}

/// Starts a backend with the collection at `collection_path` open.
fn open_backend(collection_path: &FsPath) -> Result<Backend> {
    if let Some(folder) = collection_path.parent() {
        fs::create_dir_all(folder)?;
    }
    let init = BackendInit {
        preferred_langs: vec!["en".into()],
        ..Default::default()
    };
    let backend = init_backend(&init.encode_to_vec()).map_err(|err| anyhow!(err))?;
    let request = OpenCollectionRequest {
        collection_path: path_string(collection_path)?,
        media_folder_path: path_string(&collection_path.with_extension("media"))?,
        media_db_path: path_string(&collection_path.with_extension("media.db2"))?,
    };
    api::run(&backend, "openCollection", &request.encode_to_vec())
        .map_err(|err| anyhow!(err.message))
        .with_context(|| format!("opening {}", collection_path.display()))?;
    Ok(backend)
}

fn path_string(path: &FsPath) -> Result<String> {
    path.to_str()
        .map(str::to_owned)
        .with_context(|| format!("path is not valid UTF-8: {}", path.display()))
}

async fn api_request(
    State(state): State<AppState>,
    Path(method): Path<String>,
    headers: HeaderMap,
    body: Bytes,
) -> Response {
    if headers.get(CONTENT_TYPE).map(|value| value.as_bytes()) != Some(API_CONTENT_TYPE.as_bytes())
    {
        return (StatusCode::FORBIDDEN, "unexpected content type").into_response();
    }
    // backend calls block on the collection, so keep them off the async threads
    let result =
        tokio::task::spawn_blocking(move || api::call(&state.backend, &method, &body)).await;
    match result {
        Ok(Ok(output)) if output.is_empty() => StatusCode::NO_CONTENT.into_response(),
        Ok(Ok(output)) => ([(CONTENT_TYPE, API_CONTENT_TYPE)], output).into_response(),
        Ok(Err(ApiError::UnknownMethod)) => {
            (StatusCode::NOT_FOUND, "no such method").into_response()
        }
        Ok(Err(ApiError::Backend(message))) => {
            (StatusCode::INTERNAL_SERVER_ERROR, message).into_response()
        }
        Err(_) => (StatusCode::INTERNAL_SERVER_ERROR, "request failed").into_response(),
    }
}

async fn static_file(State(state): State<AppState>, uri: Uri) -> Response {
    let path = static_files::resolve(&state.static_dir, uri.path());
    match tokio::fs::read(&path).await {
        Ok(data) => ([(CONTENT_TYPE, static_files::content_type(&path))], data).into_response(),
        Err(_) => (StatusCode::NOT_FOUND, "frontend has not been built").into_response(),
    }
}
