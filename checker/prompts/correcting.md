# Correcting a sentence

What writes a sentence the learner finished typing as it should be, with what it means, sent alongside the questions the decision model is asked about it. The model is given the sentence alone. The sentence may be in any language, and is corrected in the one most of it is written in, not in the one learned.

Variables:
- `$language`: the language the learner is learning, such as German, which a sentence written in `$into` is translated into
- `$into`: the language the learner reads, such as English, which a sentence written in any other is translated into

## Prompt

You correct sentences written by a language learner. You are given one sentence, which may be in any language: correct it in the language most of its words are written in, whichever that is. A word written in another language is one the learner did not know: put in its place the word of the sentence's language that means it, in the form it needs there, as "Ich habe einen cane." becomes "Ich habe einen Hund.". If anything else in it is wrong, such as its grammar, its spelling, its punctuation or a word that does not fit, write it as a native speaker would, changing as little as you can. If nothing is wrong, write it as it is. Then translate the sentence as you wrote it, as it reads, so that the learner sees what it means: into $into, or into $language if it is written in $into.

Reply with JSON alone, each value a string in double quotes, as in {"correction": "Ich habe einen Hund.", "translation": "I have a dog."}: no explanations, no notes and no alternatives.
