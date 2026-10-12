// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

//! A small server that signs in to a sync account like any other device,
//! fetches the collection periodically, and serves its contents as JSON so
//! that other applications can read them.

mod api;
mod library;
mod mirror;
mod status;

use std::net::IpAddr;
use std::net::Ipv4Addr;
use std::net::SocketAddr;
use std::path::Path as FsPath;
use std::path::PathBuf;
use std::time::Duration;

use anki::backend::Backend;
use anki_io::create_dir_all;
use anki_io::read_to_string;
use anki_io::write_file;
use anki_proto::sync::SyncAuth;
use anki_proto::sync::SyncLoginRequest;
use anyhow::anyhow;
use anyhow::bail;
use anyhow::Context;
use anyhow::Result;
use axum::body::Bytes;
use axum::extract::DefaultBodyLimit;
use axum::extract::Path;
use axum::extract::Request;
use axum::extract::State;
use axum::http::header::AUTHORIZATION;
use axum::http::header::CONTENT_TYPE;
use axum::http::HeaderMap;
use axum::http::StatusCode;
use axum::middleware;
use axum::middleware::Next;
use axum::response::IntoResponse;
use axum::response::Response;
use axum::routing::get;
use axum::routing::post;
use axum::routing::put;
use axum::Json;
use axum::Router;
use serde::Deserialize;
use tokio::net::TcpListener;

use crate::api::ApiError;
use crate::mirror::media_folder;
use crate::mirror::open_backend;
use crate::mirror::Mirror;
use crate::mirror::SharedStatus;

/// Read from environment variables prefixed with `ANKI_STATUS_`.
#[derive(Deserialize, Debug)]
struct Config {
    /// Folder holding the copy of the collection and the saved sync key.
    data_dir: PathBuf,
    /// Only needed on the first run, to obtain the sync key.
    username: Option<String>,
    password: Option<String>,
    /// A self-hosted sync server. AnkiWeb is used if unset.
    endpoint: Option<String>,
    #[serde(default = "default_interval_mins")]
    interval_mins: u64,
    /// Also download images and audio, and serve them under `/media`.
    #[serde(default)]
    sync_media: bool,
    #[serde(default = "default_host")]
    host: IpAddr,
    #[serde(default = "default_port")]
    port: u16,
    /// If set, requests must send it as `Authorization: Bearer <token>`.
    token: Option<String>,
}

fn default_interval_mins() -> u64 {
    15
}

fn default_host() -> IpAddr {
    Ipv4Addr::LOCALHOST.into()
}

fn default_port() -> u16 {
    8090
}

/// Settings left empty in the .env file count as unset.
fn filled(value: &Option<String>) -> Option<String> {
    value.clone().filter(|value| !value.is_empty())
}

#[derive(Clone)]
struct AppState {
    backend: Backend,
    status: SharedStatus,
    media_folder: PathBuf,
    /// Where generated texts and their audio are kept.
    texts_folder: PathBuf,
    token: Option<String>,
}

/// A few minutes of uncompressed speech.
const MAX_AUDIO_BYTES: usize = 64 * 1024 * 1024;

// The backend runs its own async tasks to sync, so it is set up before ours
// are started.
fn main() -> Result<()> {
    let config: Config = envy::prefixed("ANKI_STATUS_")
        .from_env()
        .context("reading ANKI_STATUS_* environment variables")?;
    let token = filled(&config.token);
    if !config.host.is_loopback() && token.is_none() {
        bail!("ANKI_STATUS_TOKEN must be set to accept connections from other machines");
    }
    create_dir_all(&config.data_dir)?;
    let collection_path = config.data_dir.join("collection.anki2");
    let backend = open_backend(&collection_path)?;
    let auth = sync_auth(&config, &backend)?;

    let state = AppState {
        backend: backend.clone(),
        status: SharedStatus::default(),
        media_folder: media_folder(&collection_path),
        texts_folder: config.data_dir.join("texts"),
        token,
    };
    let mirror = Mirror::new(backend, auth, config.sync_media);
    let interval = Duration::from_secs(config.interval_mins.max(1) * 60);
    let shared = state.status.clone();
    std::thread::spawn(move || mirror.run(interval, shared));

    let addr = SocketAddr::new(config.host, config.port);
    tokio::runtime::Runtime::new()?.block_on(serve(addr, state))
}

async fn serve(addr: SocketAddr, state: AppState) -> Result<()> {
    let app = Router::new()
        .route("/decks", get(decks))
        .route("/api", get(api_methods))
        .route("/api/{method}", get(api_call).post(api_call))
        .route("/sql", post(sql))
        .route("/media/{name}", get(media))
        .route("/texts", get(texts))
        .route("/texts/{id}", put(save_text).delete(delete_text))
        .route(
            "/texts/{id}/audio",
            get(text_audio)
                .put(save_text_audio)
                .layer(DefaultBodyLimit::max(MAX_AUDIO_BYTES)),
        )
        .layer(middleware::from_fn_with_state(state.clone(), require_token))
        .with_state(state);
    let listener = TcpListener::bind(addr)
        .await
        .with_context(|| format!("listening on {addr}"))?;
    println!("Serving on http://{addr}/decks");
    axum::serve(listener, app)
        .with_graceful_shutdown(async {
            let _ = tokio::signal::ctrl_c().await;
        })
        .await?;
    Ok(())
}

/// Returns the saved sync key, logging in to obtain and save one if there is
/// none yet.
fn sync_auth(config: &Config, backend: &Backend) -> Result<SyncAuth> {
    let endpoint = filled(&config.endpoint);
    let key_path = config.data_dir.join("hkey");
    let hkey = if key_path.exists() {
        read_to_string(&key_path)?.trim().to_owned()
    } else {
        let (Some(username), Some(password)) = (filled(&config.username), filled(&config.password))
        else {
            bail!("set ANKI_STATUS_USERNAME and ANKI_STATUS_PASSWORD for the first run");
        };
        let request = SyncLoginRequest {
            username,
            password,
            endpoint: endpoint.clone(),
        };
        let auth: SyncAuth = api::run(backend, "syncLogin", &request)
            .map_err(|err| anyhow!(err))
            .context("logging in")?;
        write_file(&key_path, &auth.hkey)?;
        println!("Logged in; sync key saved to {}", key_path.display());
        auth.hkey
    };
    Ok(SyncAuth {
        hkey,
        endpoint,
        io_timeout_secs: None,
    })
}

async fn require_token(State(state): State<AppState>, request: Request, next: Next) -> Response {
    if !authorized(request.headers(), state.token.as_deref()) {
        return StatusCode::UNAUTHORIZED.into_response();
    }
    next.run(request).await
}

/// Anyone may read when no token is configured.
fn authorized(headers: &HeaderMap, token: Option<&str>) -> bool {
    let Some(token) = token else {
        return true;
    };
    let sent = headers
        .get(AUTHORIZATION)
        .and_then(|value| value.to_str().ok())
        .and_then(|value| value.strip_prefix("Bearer "));
    sent == Some(token)
}

async fn decks(State(state): State<AppState>) -> Response {
    match state.status.read().unwrap().clone() {
        Some(status) => Json(status).into_response(),
        None => (
            StatusCode::SERVICE_UNAVAILABLE,
            "first sync has not finished",
        )
            .into_response(),
    }
}

async fn api_methods() -> Response {
    Json(api::methods()).into_response()
}

async fn api_call(
    State(state): State<AppState>,
    Path(method): Path<String>,
    body: Bytes,
) -> Response {
    // backend calls block on the collection, so keep them off the async threads
    let result =
        tokio::task::spawn_blocking(move || api::call_json(&state.backend, &method, &body)).await;
    json_response(result)
}

async fn sql(State(state): State<AppState>, body: Bytes) -> Response {
    let result = tokio::task::spawn_blocking(move || api::query(&state.backend, &body)).await;
    json_response(result)
}

fn json_response(result: Result<Result<Vec<u8>, ApiError>, tokio::task::JoinError>) -> Response {
    match result {
        Ok(Ok(json)) => ([(CONTENT_TYPE, "application/json")], json).into_response(),
        Ok(Err(ApiError::UnknownMethod)) => {
            (StatusCode::NOT_FOUND, "no such method").into_response()
        }
        Ok(Err(ApiError::BadRequest(message))) => {
            (StatusCode::BAD_REQUEST, message).into_response()
        }
        Ok(Err(ApiError::Backend(message))) => {
            (StatusCode::INTERNAL_SERVER_ERROR, message).into_response()
        }
        Err(_) => (StatusCode::INTERNAL_SERVER_ERROR, "request failed").into_response(),
    }
}

async fn media(State(state): State<AppState>, Path(name): Path<String>) -> Response {
    if !is_plain_file_name(&name) {
        return StatusCode::NOT_FOUND.into_response();
    }
    match tokio::fs::read(state.media_folder.join(&name)).await {
        Ok(data) => ([(CONTENT_TYPE, content_type(&name))], data).into_response(),
        Err(_) => StatusCode::NOT_FOUND.into_response(),
    }
}

async fn texts(State(state): State<AppState>) -> Response {
    match library::list(&state.texts_folder) {
        Ok(texts) => Json(texts).into_response(),
        Err(err) => (StatusCode::INTERNAL_SERVER_ERROR, format!("{err:#}")).into_response(),
    }
}

async fn save_text(State(state): State<AppState>, Path(id): Path<String>, body: Bytes) -> Response {
    stored(library::save_text(&state.texts_folder, &id, &body))
}

async fn save_text_audio(
    State(state): State<AppState>,
    Path(id): Path<String>,
    headers: HeaderMap,
    body: Bytes,
) -> Response {
    let content_type = headers
        .get(CONTENT_TYPE)
        .and_then(|value| value.to_str().ok())
        .unwrap_or_default();
    stored(library::save_audio(
        &state.texts_folder,
        &id,
        content_type,
        &body,
    ))
}

async fn delete_text(State(state): State<AppState>, Path(id): Path<String>) -> Response {
    stored(library::delete(&state.texts_folder, &id))
}

/// What is refused is something about the request, such as its id or type.
fn stored(result: Result<()>) -> Response {
    match result {
        Ok(()) => StatusCode::NO_CONTENT.into_response(),
        Err(err) => (StatusCode::BAD_REQUEST, format!("{err:#}")).into_response(),
    }
}

async fn text_audio(State(state): State<AppState>, Path(id): Path<String>) -> Response {
    let Some((path, content_type)) = library::audio(&state.texts_folder, &id) else {
        return StatusCode::NOT_FOUND.into_response();
    };
    match tokio::fs::read(path).await {
        Ok(data) => ([(CONTENT_TYPE, content_type)], data).into_response(),
        Err(_) => StatusCode::NOT_FOUND.into_response(),
    }
}

/// False for anything that could name a file outside the media folder.
fn is_plain_file_name(name: &str) -> bool {
    FsPath::new(name).file_name().and_then(|file| file.to_str()) == Some(name)
        && !name.contains(['/', '\\', ':'])
}

fn content_type(name: &str) -> &'static str {
    let extension = FsPath::new(name)
        .extension()
        .and_then(|extension| extension.to_str())
        .unwrap_or_default();
    match extension.to_ascii_lowercase().as_str() {
        "png" => "image/png",
        "jpg" | "jpeg" => "image/jpeg",
        "gif" => "image/gif",
        "webp" => "image/webp",
        "svg" => "image/svg+xml",
        "mp3" => "audio/mpeg",
        "ogg" | "oga" => "audio/ogg",
        "wav" => "audio/wav",
        "m4a" => "audio/mp4",
        "mp4" => "video/mp4",
        "webm" => "video/webm",
        _ => "application/octet-stream",
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn headers_with_authorization(value: &str) -> HeaderMap {
        let mut headers = HeaderMap::new();
        headers.insert(AUTHORIZATION, value.parse().unwrap());
        headers
    }

    #[test]
    fn authorized_accepts_any_request_when_no_token_is_configured() {
        assert!(authorized(&HeaderMap::new(), None));
    }

    #[test]
    fn authorized_accepts_the_configured_token_as_bearer() {
        let headers = headers_with_authorization("Bearer s3cret");

        assert!(authorized(&headers, Some("s3cret")));
    }

    #[test]
    fn authorized_rejects_requests_without_the_configured_token() {
        let rejected = [
            ("no header", HeaderMap::new()),
            ("wrong token", headers_with_authorization("Bearer other")),
            ("not bearer", headers_with_authorization("s3cret")),
        ];

        for (case, headers) in rejected {
            assert!(!authorized(&headers, Some("s3cret")), "{case}");
        }
    }

    #[test]
    fn is_plain_file_name_accepts_names_inside_the_media_folder() {
        for name in ["cat.png", "paste-1a2b.jpg", "audio 01.mp3", ".hidden"] {
            assert!(is_plain_file_name(name), "{name}");
        }
    }

    #[test]
    fn is_plain_file_name_rejects_names_that_leave_the_media_folder() {
        let outside = [
            "..",
            ".",
            "",
            "../hkey",
            "..\\hkey",
            "sub/cat.png",
            "/etc/passwd",
            "C:\\secret.txt",
            "C:secret.txt",
        ];

        for name in outside {
            assert!(!is_plain_file_name(name), "{name}");
        }
    }
}
