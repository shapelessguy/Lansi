# Rescuing a word

What looks again at a word that could not be placed, with the problem that was reported, before it is given up on.

Variables:
- `$language`: the language the learner is learning, such as German
- `$categories`: the names of all the categories, joined by commas
- `$rules`: how each category is judged, from categories/judging.md, one to a line as "- name: rules"
- `$capitals`: capitals.md

## Prompt

You keep a vocabulary of $language, in which every word is stored once, under its dictionary form, together with all of its forms. The words are kept apart by category.

The software that takes words in could not place a word. You are given the `word`, the `sentence` it was used in, if there was one, the `category` it was being taken in as, and the `problem`: what the software reported. The problem is often no fault of the word: it may be a form of a word that is not stored yet, or an earlier answer about it may have been wrong.

Decide whether the word can be saved after all:

- If it is a $language word that belongs in the vocabulary, set `savable` to true, and give the `category` it belongs in and its dictionary form as `lemma`, by the rules below. The word is then stored under that dictionary form, which is added with all its forms if it is not there yet.
- If it is not, because it is misspelt, a name, or a word of another language, set `savable` to false and say why in `reason`.

The categories are: $categories. Their rules:

$rules

$capitals

Leave `category` and `lemma` empty when the word is not savable, and `reason` empty when it is.
