# Claude Code Configuration

> **Note:** Every command you need — running, testing, linting, formatting —
> is defined as a recipe in the project `justfile`. Run `just --list` to see
> them.

## Project Overview

A language-learning chat built on an Anki collection. Three parts:

- `deck-status/`: Rust (axum) server that keeps a synced copy of the
  collection and serves its contents as JSON; also stores generated texts
  and their audio. Settings come from `deck-status/.env`, which may hold a
  password: do not read it.
- `chat-ui/`: React + TypeScript GUI (Vite), talking to OpenRouter and to the
  two servers through the dev server's `/anki` and `/checker` proxies.
- `checker/`: Python server that splits typed text into sentences,
  spell-checks them and profiles finished sentences with a decision model.
  It also keeps everything a user has, in `checker/data/users/<name>/`:
  the chats, texts and settings (`storage.py`) and a vocabulary for each
  language (`intake.py`, `vocabulary.py`); what the models are told about
  each category of word is in `categories.py`. Who may log in is in
  `users.json` at the top of the repository, which holds passwords: do not
  read it.

`rslib/`, `proto/` and `ftl/` are Anki's Rust core, kept only because
`deck-status` is built on it. Avoid changing them.

## Running

`just dev` runs all three parts. `just deck-status`, `just checker` and
`just chat-ui` run one each.

## Building/checking

`just check` formats the code and runs the linters and tests. Please do this
as a final step before marking a task as completed. `just test`, `just lint`
and `just fix-fmt` run one stage each.

## Conventions

- Source files start with the copyright header the existing ones have.
- Tests are named for the unit, what is expected and when, such as
  `test_a_sentence_is_profiled_when_the_caret_leaves_it`.
- Rust: prefer adding dependencies to the root workspace and using
  `dep.workspace = true`; use anyhow with context for errors.
- The files in out/ are generated. Ignore that folder.

## Individual preferences

See @.claude/user.md
