// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

//! A small server that signs in to a sync account like any other device,
//! fetches the collection periodically, and serves its contents as JSON so
//! that other applications can read them.

mod api;
mod mirror;
mod status;
mod users;

use std::net::IpAddr;
use std::net::Ipv4Addr;
use std::net::SocketAddr;
use std::path::Path as FsPath;
use std::path::PathBuf;
use std::sync::Arc;
use std::time::Duration;

use anyhow::bail;
use anyhow::Context;
use anyhow::Result;
use axum::body::Bytes;
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
use axum::Json;
use axum::Router;
use serde::Deserialize;
use tokio::net::TcpListener;

use serde_json::json;

use crate::api::ApiError;
use crate::users::LinkError;
use crate::users::Users;

/// Read from environment variables prefixed with `ANKI_STATUS_`.
#[derive(Deserialize, Debug)]
struct Config {
    /// Folder holding a folder for each user, with the copy of their
    /// collection and the sync key it was linked with.
    #[serde(default = "default_data_dir")]
    data_dir: PathBuf,
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

fn default_data_dir() -> PathBuf {
    PathBuf::from("deck-status/data")
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
    users: Arc<Users>,
    token: Option<String>,
}

// The backends run their own async tasks to sync, so they are set up before
// ours are started.
fn main() -> Result<()> {
    let config: Config = envy::prefixed("ANKI_STATUS_")
        .from_env()
        .context("reading ANKI_STATUS_* environment variables")?;
    let token = filled(&config.token);
    if !config.host.is_loopback() && token.is_none() {
        bail!("ANKI_STATUS_TOKEN must be set to accept connections from other machines");
    }
    let interval = Duration::from_secs(config.interval_mins.max(1) * 60);
    let users = Users::new(
        config.data_dir.join("users"),
        filled(&config.endpoint),
        interval,
        config.sync_media,
    );
    users.load()?;
    let state = AppState {
        users: Arc::new(users),
        token,
    };

    let addr = SocketAddr::new(config.host, config.port);
    tokio::runtime::Runtime::new()?.block_on(serve(addr, state))
}

async fn serve(addr: SocketAddr, state: AppState) -> Result<()> {
    let app = Router::new()
        .route("/api", get(api_methods))
        .route("/users/{user}", get(user_state))
        .route("/users/{user}/link", post(link).delete(unlink))
        .route("/users/{user}/decks", get(decks))
        .route("/users/{user}/api/{method}", get(api_call).post(api_call))
        .route("/users/{user}/sql", post(sql))
        .route("/users/{user}/media/{name}", get(media))
        .layer(middleware::from_fn_with_state(state.clone(), require_token))
        .with_state(state);
    let listener = TcpListener::bind(addr)
        .await
        .with_context(|| format!("listening on {addr}"))?;
    println!("Serving on http://{addr}/users/<name>/decks");
    axum::serve(listener, app)
        .with_graceful_shutdown(async {
            let _ = tokio::signal::ctrl_c().await;
        })
        .await?;
    Ok(())
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

fn not_linked() -> Response {
    (StatusCode::NOT_FOUND, "no Anki account is linked").into_response()
}

/// Whether `user` has a collection, with what its last sync left.
async fn user_state(State(state): State<AppState>, Path(user): Path<String>) -> Response {
    match state.users.get(&user) {
        Some(linked) => {
            let status = linked.status.read().unwrap().clone();
            Json(json!({ "linked": true, "status": status })).into_response()
        }
        None => Json(json!({ "linked": false })).into_response(),
    }
}

#[derive(Deserialize)]
struct LinkRequest {
    username: String,
    password: String,
}

/// Logs in to a sync account and mirrors its collection for `user`.
async fn link(
    State(state): State<AppState>,
    Path(user): Path<String>,
    Json(request): Json<LinkRequest>,
) -> Response {
    let linked = tokio::task::spawn_blocking(move || {
        state.users.link(&user, request.username, request.password)
    })
    .await;
    match linked {
        Ok(Ok(())) => Json(json!({ "linked": true })).into_response(),
        Ok(Err(LinkError::BadName)) => (StatusCode::NOT_FOUND, "no such user").into_response(),
        Ok(Err(LinkError::Taken)) => (
            StatusCode::CONFLICT,
            "an Anki account is linked already, or still being unlinked",
        )
            .into_response(),
        Ok(Err(LinkError::Refused(message))) => (StatusCode::BAD_REQUEST, message).into_response(),
        Ok(Err(LinkError::Failed(err))) => {
            eprintln!("linking failed: {err:#}");
            (StatusCode::INTERNAL_SERVER_ERROR, format!("{err:#}")).into_response()
        }
        Err(_) => (StatusCode::INTERNAL_SERVER_ERROR, "linking failed").into_response(),
    }
}

/// Stops mirroring the collection of `user` and removes it.
async fn unlink(State(state): State<AppState>, Path(user): Path<String>) -> Response {
    state.users.unlink(&user);
    Json(json!({ "linked": false })).into_response()
}

async fn decks(State(state): State<AppState>, Path(user): Path<String>) -> Response {
    let Some(linked) = state.users.get(&user) else {
        return not_linked();
    };
    let status = linked.status.read().unwrap().clone();
    match status {
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
    Path((user, method)): Path<(String, String)>,
    body: Bytes,
) -> Response {
    let Some(linked) = state.users.get(&user) else {
        return not_linked();
    };
    // backend calls block on the collection, so keep them off the async threads
    let result =
        tokio::task::spawn_blocking(move || api::call_json(&linked.backend, &method, &body)).await;
    json_response(result)
}

async fn sql(State(state): State<AppState>, Path(user): Path<String>, body: Bytes) -> Response {
    let Some(linked) = state.users.get(&user) else {
        return not_linked();
    };
    let result = tokio::task::spawn_blocking(move || api::query(&linked.backend, &body)).await;
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

async fn media(
    State(state): State<AppState>,
    Path((user, name)): Path<(String, String)>,
) -> Response {
    let Some(linked) = state.users.get(&user) else {
        return not_linked();
    };
    if !is_plain_file_name(&name) {
        return StatusCode::NOT_FOUND.into_response();
    }
    match tokio::fs::read(linked.media_folder.join(&name)).await {
        Ok(data) => ([(CONTENT_TYPE, content_type(&name))], data).into_response(),
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
