# Logs of a chat about a selection

What writes the logs of a chat about a translation, one for each matter discussed.

Variables:
- `$language`: the language the learner is learning, such as German
- `$into`: the language the learner reads explanations in, such as English
- `$passage`: the passage, with the selection between [[ and ]]
- `$translation`: the translation the learner was given
- `$chat`: the chat, each message as "name: text" with the names of names.md, with a blank line between them
- `$matters`: how many logs there may be at most

## Prompt

You write the logs of a chat in which someone learning $language asked about a passage they had selected and had translated into $into. The logs are not for the learner: they are kept for the models that will later work out what the learner can and cannot do yet, so they must be exact and plain. Do not praise, encourage or soften anything. State what the learner asked about and did not know, and the gist of what they were told; draw no conclusion about the learner beyond that.

Split the chat into the separate matters that were discussed, such as what a word means there, how it is used, why it stands where it does or a construction. Write one log for each, with:
- "subject": the words of $language it is about, in a few words, as they were written, such as a word or a phrase;
- "points": one or two short lines, in English: what the learner asked or did not know, and what they were told. No more than that.
At most $matters logs. Leave out greetings, thanks and anything that is not about the language.

The passage, with the selection marked with [[ and ]]:
$passage

The translation they were given:
$translation

The chat:
$chat

Reply with JSON only:
{"logs": [{"subject": "...", "points": ["...", "..."]}]}
