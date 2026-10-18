# The learner's words

The words of the learner's vocabulary that the sentences are to be made of (`only`) or are to lean on (`prefer`).

Variables:
- `$language`: the language the learner is learning, such as German
- `$lemmas`: the words, those that fit the topics best first, joined by commas

## Prompt: only

Words the learner knows, those that fit the topic first. Write the $language sentences with these words alone, in any of their forms, besides articles, pronouns, prepositions, conjunctions, numbers, auxiliary and modal verbs, and the words the rules above need:
$lemmas

## Prompt: prefer

Words the learner knows, those that fit the topic first. Use these in the $language sentences wherever they fit, in any of their forms; other words are fine where none of these does, as long as a learner at the level knows them:
$lemmas
