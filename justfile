set windows-shell := ["pwsh", "-NoLogo", "-NoProfileLoadTime", "-Command"]
set dotenv-filename := "deck-status/.env"

# Show available commands
default:
    @just --list

# Run everything the chat needs in one terminal: the deck-status server, the
# checker server and the chat GUI. Ctrl+C stops all three.
dev:
    cd chat-ui && npm install && npm run all

# Sync a copy of the collection periodically and serve its contents as JSON on
# http://127.0.0.1:8090 (try /decks). Settings are read from deck-status/.env.
deck-status:
    cargo run --target-dir out/rust -p anki-deck-status

# Run the chat GUI on port 5173, open to the LAN (http://<this machine>:5173
# from another one; Windows may ask to let Node through the firewall). It reads the known words from the
# deck-status server, so start `just deck-status` first.
chat-ui:
    cd chat-ui && npm install && npm run dev

# Run the checker server on http://127.0.0.1:8092. The chat GUI sends it what
# is being typed, and it prints the sentences it finds.
checker: _checker-env
    {{ checker_python }} checker/server.py

# Run the tests of all three parts
test: _checker-env
    cargo test --target-dir out/rust -p anki-deck-status
    {{ checker_python }} -m pytest -q checker
    cd chat-ui && npm install && npm test

# Run linting and type checking
lint: _checker-env
    cargo clippy --target-dir out/rust -p anki-deck-status -- -D warnings
    {{ checker_python }} -m ruff check checker
    {{ checker_python }} -m mypy checker
    cd chat-ui && npm install && npm run check

# Fix formatting
fix-fmt: _checker-env
    cargo fmt -p anki-deck-status
    {{ checker_python }} -m ruff format checker
    cd chat-ui && npm install && npm run fmt

# Run the tests and the linters. Do this before calling a change done.
check: fix-fmt lint test

[private]
_checker-env:
    {{ if path_exists("checker/.venv") == "true" { "" } else { "python -m venv checker/.venv" } }}
    {{ checker_python }} -m pip install --quiet --disable-pip-version-check -r checker/requirements-dev.txt

checker_python := if os() == "windows" { "checker\\.venv\\Scripts\\python" } else { "checker/.venv/bin/python" }
