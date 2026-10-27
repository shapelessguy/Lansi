# Log of an exercise done again

What adds to the log of an exercise that the learner has just done again, exactly as it was: a few sentences on what went better than the times before and what did not, for the models that profile the learner rather than for the learner.

Variables:
- `$language`: the language the learner is learning, such as German
- `$task`: what the exercise was, as task.md says, one to a line
- `$before`: the log of the times before, as writing.md wrote it and this prompt added to it
- `$record`: what the learner did this time, as record.md says
- `$lines`: how many sentences there may be at most

## Prompt

Someone learning $language has just done an exercise again, exactly as they did it before: the same sentences, the same tasks. Its log tells how the times before went. You add to it a few sentences on this time. They are not for the learner: they are kept for the models that will later work out what the learner can and cannot do yet, so they must be exact and plain. Do not praise, encourage or soften anything.

What the learner did is told in two parts that must never be mixed. "Given by the exercise" was written by a model, not by the learner, and is there only so that you know what was asked. "Written by the learner" is the only thing the learner did, and the only thing you judge. The grades were given by another model while the exercise ran: where one is wrong, go by what the learner actually wrote.

The exercise:
$task

Its log, of the times before:
$before

What the learner did this time:
$record

Write, in English, at most $lines whole sentences, in this order: how much of it was done this time and how the result compares with before; what they now get right that they got wrong before, naming the rules and forms; what they still get wrong, and any mistake they did not make before. Quote the learner's own words where it makes a point clearer. Do not repeat what the log already says unless it changed.

Reply with JSON only:
{"summary": ["...", "..."]}
