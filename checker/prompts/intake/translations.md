# Translating a word

What translates a stored word into another language, variant by variant, for a learner who has changed the language they read translations in.

Variables:
- `$language`: the language the learner is learning, such as German
- `$name`: the name of the category of the word
- `$into`: the language the translations are to be written in, such as Italian

## Prompt

You translate an entry of a vocabulary of $language for a learner who reads translations in $into. You are given a $language $name by its dictionary form as `lemma`, and its `variants`, each by its name: the ways the word differs in its grammar, each with what is known of it and its translations into another language where it has them. A variant is not a meaning: one variant can have many meanings. Give the translations of each variant in $into, under its name: short translations of the $language word itself, one for each distinct meaning of that variant, the most common first. Keep to the meanings the translations given have, as they are what the variant was stored with; where none are given, give those of the word.
