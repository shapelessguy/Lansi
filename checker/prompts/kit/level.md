# The level

How hard what a model writes is to be. `with_sentences` is told at a level that level_sentences.md has sentences for, and `plain` at any other.

Variables:
- `$level`: the learner's level, such as A1
- `$sentences`: what the sentences of the level are like, from level_sentences.md

## Prompt: with_sentences

The learner is at level $level: use only words a learner at $level knows, and write $sentences. Where the rules below need more than that, the rules come first.

## Prompt: plain

The learner is at level $level: use only words a learner at $level knows. Where the rules below need more than that, the rules come first.
