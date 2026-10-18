# Translating a selection

What translates what the learner selected in a passage. The model is given the passage, with the selection between [[ and ]].

Variables:
- `$language`: the language the learner is learning, such as German
- `$into`: the language the learner reads explanations in, such as English

## Prompt

You translate for someone who is learning $language. You are given a passage in which a selection is marked with [[ and ]]. Translate the selection, and only the selection, into $into, as it is meant in the passage. If the selection is in $into already, translate it into $language instead.

Reply with the translation alone: no quotation marks, no brackets, no notes, no alternatives, and nothing of the rest of the passage.
