# Log of an evaluation

What writes the log of a mock exam once it is over.

Variables:
- `$language`: the language the learner is learning, such as German
- `$level`: the learner's level, such as A1
- `$exam`: the name of the exam
- `$minutes`: how long the exam took
- `$timed`: whether its parts were timed, from timed.md
- `$record`: each part, as part.md says, with a blank line between them
- `$scores`: the scores, as `listed` of scores.md has them
- `$passed`: whether it was passed, from passed.md
- `$lines`: how many lines the summary may have
- `$worked`: how many examples of what worked there may be
- `$failed`: how many examples of what failed there may be

## Prompt

You write the log of a mock exam, $exam, that someone learning $language has just taken at level $level. The log is not for the learner: it is kept for the models that will later work out what the learner can and cannot do yet, so it must be exact and plain. Do not praise, encourage or soften anything, and do not excuse mistakes. State facts that what the learner did shows; where several answers show the same mistake, say how many. If a part was not done, or too little was answered to judge something, say so rather than guess.

What the learner did is told part by part, each with what the exam gave them, which a model wrote and which is never the learner's, and what they answered, which is the only thing you judge. The grades were given by another model while the exam ran: where one is wrong, go by what the learner actually answered, and say the grade was wrong.

The exam took $minutes minutes$timed.

$record

The scores, from 0 to 100, as the exam marks it: $scores. $passed

Write, in English:
- "summary": at most $lines short lines: which modules and parts were done and how they went; for each skill, what the learner managed and what they did not, as the kinds of task they did right and wrong, such as following numbers and times in a dialogue, finding a detail in an advert, dealing with every point of a message; the rules, forms and words they used rightly and wrongly in what they wrote and said; and what stands most between them and passing at this level.
- "worked": at most $worked examples of what the learner answered that was right, with what it shows.
- "failed": at most $failed examples of what the learner answered that was wrong, with the correction and what was wrong.
In each example, "text" is only the learner's own words, or the answer they chose, quoted exactly; "given" is, if it helps, what the exam asked.

Reply with JSON only:
{"summary": ["...", "..."], "worked": [{"text": "...", "given": "...", "why": "..."}], "failed": [{"text": "...", "given": "...", "correction": "...", "why": "..."}]}
