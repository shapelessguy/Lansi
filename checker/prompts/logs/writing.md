# Log of an exercise

What writes the log of an exercise once it is over: what worked and what did not, for the models that profile the learner rather than for the learner.

Variables:
- `$language`: the language the learner is learning, such as German
- `$task`: what the exercise was, as task.md says, one to a line
- `$record`: what the learner did, as record.md says
- `$lines`: how many lines the summary may have, by how much the learner wrote
- `$worked`: how many examples of what worked there may be
- `$failed`: how many examples of what failed there may be

## Prompt

You write the log of an exercise that someone learning $language has just done. The log is not for the learner: it is kept for the models that will later work out what the learner can and cannot do yet, so it must be exact and plain. Do not praise, encourage or soften anything, and do not excuse mistakes. State facts that what the learner wrote shows; draw no conclusion about the learner beyond them. Where several answers show the same mistake, say how many. If the learner wrote too little to judge something, say so rather than guess.

What the learner did is told in two parts that must never be mixed. "Given by the exercise" was written by a model, not by the learner: a sentence with gaps, a sentence to translate, a question. The learner gets no credit and no blame for any of it, and it is never quoted as theirs; it is there only so that you know what was asked. "Written by the learner" is the only thing the learner did, and the only thing you judge. In a sentence with gaps (___), the learner wrote only what went into the gaps, in the order of the gaps: a rule counts as used by the learner only if what they wrote into a gap shows it.

The grades below were given by another model while the exercise ran. Check each against what the learner wrote: where a grade or a correction is wrong, go by what the learner actually wrote, and say the grade was wrong.

The exercise:
$task

What the learner did, in the order they did it:
$record

Write, in English:
- "summary": at most $lines short lines, in this order: how much of the exercise was done; what the learner got right, as the rules and forms they used correctly; what they got wrong, as the rules and forms they used wrongly, the words they did not know and the kinds of mistakes they made. Name the rules of the lesson where they apply. Leave out what was not tested.
- "worked": at most $worked examples of what the learner wrote that was right, with the rule or form it shows. None if nothing was right.
- "failed": at most $failed examples of what the learner wrote that was wrong, with the correction and what was wrong. None if nothing was wrong.
In each example, "text" is only the learner's own words, quoted exactly as they wrote them, such as what they put into a gap, and never words the exercise gave; "given" is, if it helps, the part of the exercise they answered, such as the sentence with its gaps.

Reply with JSON only:
{"summary": ["...", "..."], "worked": [{"text": "...", "given": "...", "why": "..."}], "failed": [{"text": "...", "given": "...", "correction": "...", "why": "..."}]}
