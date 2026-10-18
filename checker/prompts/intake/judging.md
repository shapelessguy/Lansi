# Judging a word

What judges whether a word that is not stored is a form of a stored word of a category, a new word of it, a word of another category, or no word. The model is given the word, the sentence it was used in and the stored words spelt most like it.

Variables:
- `$language`: the language the learner is learning, such as German
- `$name`: the name of the category
- `$categories`: the names of all the categories, joined by commas
- `$rules`: how the category is judged, from categories/judging.md
- `$capitals`: capitals.md

## Prompt

You keep a vocabulary of $language, in which every word is stored once, under its dictionary form, together with all of its forms. The words are kept apart by category. This is about the category "$name".

You are given a `word` that is not among the stored forms of this category, the `sentence` it was used in, if there was one, and `candidates`: the stored words of the category that are spelt most like it. Decide what the word is:

- "form": it is a form of one of the candidates. Give that candidate's `lemma`, exactly as it was given to you.
- "new": it is a $language $name that is none of the candidates. Give its dictionary form as `lemma`.
- "elsewhere": it is a $language word, but not a $name, as it is used in the sentence or, without one, as it is most often used. Name what it is as `category`: one of $categories.
- "reject": it is not a $language word of any category: it is misspelt, a name, or a word of another language. Say which in `reason`.

The rules of this category: $rules

$capitals

Give a `lemma` only for "form" and "new", a `category` only for "elsewhere", and a `reason` only for "reject". Leave the others empty.
