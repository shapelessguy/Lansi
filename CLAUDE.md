# Claude Code Configuration

> **Note:** Every command you need — running, testing, linting, formatting —
> is defined as a recipe in the project `justfile`. Run `just --list` to see
> them.

## Project Overview

A language-learning chat built on an Anki collection. Three parts:

- `deck-status/`: Rust (axum) server that keeps a synced copy of the
  collection of each user who linked an Anki account, in
  `deck-status/data/users/<name>/` with the sync key, and serves its contents
  as JSON under `/users/<name>/` (`users.rs`). Optional settings come from
  `deck-status/.env`: do not read it.
- `chat-ui/`: React + TypeScript GUI (Vite), served under `/lansi/` on
  127.0.0.1 for the nginx of CyanHouse, talking to OpenRouter and, through
  the dev server's `/lansi/checker` proxy, to the checker; only the checker
  reaches deck-status, which the browser never does.
- `checker/`: Python server that splits typed text into sentences,
  spell-checks them and profiles finished sentences with a decision model.
  It also keeps everything a user has, in `checker/data/users/<name>/`:
  the chats, books, sessions of practice and settings (`storage.py`) and a vocabulary for
  each language (`intake.py`, `vocabulary.py`); a book is an EPUB file read
  into its text and font sizes (`books.py`); the categories of words are
  in `categories.py`. What the server tells the models is in
  `checker/prompts/`, a Markdown file for each kind of prompt, with
  `$variables`, as `prompts.py` describes; what an exercise tells them is
  in the `prompts.toml` of its directory. Practice is made of
  lessons, which are grammar points kept by hand in the `grammar/` of each
  language
  (`grammar.py`), and exercises, each a directory in `checker/exercises/`
  with a backend run in a process of its own and an interface, a module
  the app mounts in a shadow root, as `exercises/kit.py` and
  `exercises/kit.js` describe;
  sessions of practice, the grades of what was answered and what was written
  in each exercise, whose words go into the vocabulary as those of the
  chats do (`processing.py`), are kept by `exercising.py` and `storage.py`;
  once an exercise is over, a model writes its log from them (`logs.py`), a
  short account of what worked and what did not, for the models that
  profile the learner rather than for the learner. Evaluations are mock
  exams of a level, as the institute that examines the language sets
  them, kept by hand in
  `checker/languages/<language>/evaluations/<level>.json`: each part is an exercise of
  practice with its options, done in a session of its own, and an
  evaluation counts up the scores the exercises report (`evaluating.py`).
  Everything that is of one language alone is in its directory in
  `checker/languages/`, as `languages/__init__.py` describes: its
  categories of words and their prompts, its lessons, its exams and
  whatever else it does its own way.
  Who may log in is in
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

- Nothing outside `checker/languages/<language>/` is written for one
  language: not the code, the prompts, the exercises or the app. Where
  something differs by language, give `Language` (`languages/__init__.py`)
  a general attribute or method that fits every language, and set what one
  language does in its own directory. An exercise, which cannot import the
  server's modules, is told what it needs in its context.

- Source files start with the copyright header the existing ones have.
- Tests are named for the unit, what is expected and when, such as
  `test_a_sentence_is_profiled_when_the_caret_leaves_it`.
- Rust: prefer adding dependencies to the root workspace and using
  `dep.workspace = true`; use anyhow with context for errors.
- The files in out/ are generated. Ignore that folder.

## Individual preferences

See @.claude/user.md
