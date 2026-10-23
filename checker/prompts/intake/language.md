# Is the sentence in the language?

What the decision model is asked about a sentence before its words are taken in: whether it is mostly written in the language being learned. The words of one that is not, such as an explanation in English with an example in it, are not taken in.

Variables:
- `$language`: the language the learner is learning, such as German

## Prompt

Is the `sentence` mostly written in $language? Answer yes if most of its words are $language words, though it may have a name or a word of another language in it. Answer no if it is mostly written in another language, even if it quotes $language words or has a $language example in it.
