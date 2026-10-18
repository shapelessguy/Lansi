# Describing a new word

What describes a new word, given its dictionary form, by the shape of its category.

Variables:
- `$language`: the language the learner is learning, such as German
- `$name`: the name of the category
- `$rules`: how the category is described, from categories/describing.md

## Prompt

You fill in the entry of a $language $name for a vocabulary. You are given its dictionary form as `lemma`. Spell every form as it is written in $language, with the letters and marks of its own, and with a capital letter only where $language has one.

$rules
