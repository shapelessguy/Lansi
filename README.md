# Lansi

A language-learning chat built on an Anki collection.

- `deck-status/` keeps a synced copy of the collection and serves its contents
  as JSON on http://127.0.0.1:8090. Settings are read from `deck-status/.env`.
- `chat-ui/` is the GUI, on http://localhost:5173: a chat, a reader of books
  and practice with lessons and exercises, which use the words you know,
  through OpenRouter.
- `checker/` splits what is typed in the chat into sentences, spell-checks
  them and has each finished sentence profiled, on http://127.0.0.1:8092. It
  is also where everything a user has is kept: the chats, the books, the
  sessions of practice, the settings and the vocabulary.

`rslib/`, `proto/` and `ftl/` are Anki's Rust core, which `deck-status` is
built on. They come from [Anki](https://github.com/ankitects/anki) and are
under the same licence.

## Running

```
just dev
```

starts all three parts in one terminal. `just --list` shows the other
commands, such as `just test` and `just check`.

## Users

The app is logged in to. Who may log in is written in `users.json`, at the
top of the repository, as a password for each name:

```
{ "ada": "her password" }
```

The file is read every time someone logs in, so a change needs no restart.
It holds the passwords as they are and is not checked in. Everything a user
has is kept in `checker/data/users/<name>/`; only the OpenRouter key stays
in the browser.

## The vocabulary

The language being learned is chosen in the settings of the GUI, and every
part goes by it: the spelling and sentence checks, the prompts that have
`{{language}}` in them, and the vocabulary.

The checker keeps a vocabulary for each user and language, in
`checker/data/users/<name>/vocabulary.<language>.db`, in which each word is stored once per
category (noun, verb, adjective and so on) under its dictionary form, with
all of its forms. German words are stored by rules written for German, and
the words of other languages by general ones. Words are taken in with

```
POST http://127.0.0.1:8092/vocabulary/words
X-OpenRouter-Key: <key>

{"words": ["ging", {"word": "Essen", "sentence": "Das Essen ist gut."}],
 "model": "<a chat model on OpenRouter>"}
```

Each word is sorted into a category by the decision model. If it is not
among the stored forms of that category, the chat model judges whether it is
a form of a stored word or a new one, and describes a new one in the shape
its category asks for. The categories, with everything the models are told
about each, are in `checker/categories.py`. The reply says what became of
each word: `known`, `added`, `form`, `skipped`, `rejected` or `failed`.

`GET /vocabulary/words` lists the stored words, and
`GET /vocabulary/words/<id>` gives everything stored of one.

Every ten seconds the checker also asks the deck-status server for the Anki
words that have a card in review, and takes those the vocabulary was never
given into it, ten at a time. It uses the key and the models of the chat,
which hands them over while it is open; the switch for it is in the
Vocabulary tab of the Library. Expressions of several words are passed over.

## Requirements

Rust, Node.js, Python 3.10 or later, and [just](https://github.com/casey/just).

Building the Rust core needs `protoc`. A copy from the Anki build is expected
in `out/extracted/protoc`; on a fresh checkout, install protoc and set
`PROTOC_BINARY` to its path. The translation submodules are needed as well:

```
git submodule update --init
```
