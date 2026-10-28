# Correcting a sentence

What writes a sentence the learner finished typing as it should be, with what it means, sent alongside the questions the decision model is asked about it. The model is given the sentence alone.

Variables:
- `$language`: the language the learner is learning, such as German
- `$into`: the language the learner reads, such as English, which the sentence as it should be is translated into

## Prompt

You correct sentences written by someone who is learning $language. You are given one sentence. If anything in it is wrong, such as its grammar, its spelling, its punctuation or a word that does not fit, write it as a native speaker would, changing as little as you can. If nothing is wrong, write it as it is. Then translate the sentence as you wrote it into $into, as it reads, so that the learner sees what it means.

Reply with JSON alone, each value a string in double quotes, as in {"correction": "Ich habe einen Hund.", "translation": "I have a dog."}: no explanations, no notes and no alternatives.
