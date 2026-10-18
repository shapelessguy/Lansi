# Describing a word of a category

What a language model is told about a word of any category when it describes a new word, in a language that has no rules of its own in languages/.

Variables:
- `$meanings_rule`: the rule about meanings, `meanings` of categories/rules.md

## Prompt

List every inflected form of the word as one of `forms`, each with `tags` that say which form it is, in English grammatical terms in small letters: `present 2nd singular`, `plural`, `feminine singular`. Give a spelling once for every form it serves. List no forms for a word that never changes. $meanings_rule
