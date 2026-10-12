# Word Chat

A language-learning chat built on an Anki collection.

- `deck-status/` keeps a synced copy of the collection and serves its contents
  as JSON on http://127.0.0.1:8090. It also stores the generated texts and
  their audio. Settings are read from `deck-status/.env`.
- `chat-ui/` is the GUI, on http://localhost:5173: a chat and a text studio
  that use the words you know, through OpenRouter.
- `checker/` splits what is typed in the chat into sentences, spell-checks
  them and has each finished sentence profiled, on http://127.0.0.1:8092.

`rslib/`, `proto/` and `ftl/` are Anki's Rust core, which `deck-status` is
built on. They come from [Anki](https://github.com/ankitects/anki) and are
under the same licence.

## Running

```
just dev
```

starts all three parts in one terminal. `just --list` shows the other
commands, such as `just test` and `just check`.

## Requirements

Rust, Node.js, Python 3.10 or later, and [just](https://github.com/casey/just).

Building the Rust core needs `protoc`. A copy from the Anki build is expected
in `out/extracted/protoc`; on a fresh checkout, install protoc and set
`PROTOC_BINARY` to its path. The translation submodules are needed as well:

```
git submodule update --init
```
