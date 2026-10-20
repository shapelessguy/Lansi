# The tutor's tools

What the tutor is told of each of its tools, and of what each is called with: `lessons`, `sessions`, `logs` and `evaluations` look up what the learner has done; `exercise` is said of each exercise of practice, which offers it to the learner, and `offered` is what the tutor is told once it has; `evaluation` offers a mock exam, and `offered_evaluation` is what the tutor is told once it has. `focus` and `words` are what an exercise is steered with, and `level`, `length` and `timed` what a mock exam is set to. The names of the others are those of what the tools are called with: `count` and `kind` of `sessions` and `logs`, `lesson`, `instances` and `topics` of an exercise, and `theory_lesson` in place of `lesson` for one that teaches the lesson rather than asks.

Variables:
- `$title`: the title of the exercise
- `$description`: what the exercise is, as its manifest says
- `$most`: how many there may be at most
- `$kinds`: the kinds of logs there are, joined by commas
- `$offered`: the exercise or the mock exam offered, with what it was called with, as JSON
- `$levels`: the levels there are mock exams of, joined by commas

## Prompt: lessons

The lessons of the language the learner is learning, in the order they are taught: the id of each, its level and its title, and whether the learner has practised it.

## Prompt: sessions

The learner's latest sessions of practice, the latest first: when each was, its lesson, its status, and for each of its exercises how many answers were right, partial and wrong, with the scores it came to.

## Prompt: logs

The learner's latest logs, the latest first, each with its id, its kind, when it was written, what it is about and what it says. The logs of exercises are short accounts of what worked and what did not; the others are of what was translated or asked about while reading.

## Prompt: evaluations

The mock exams there are, by level, each with its modules and how long it takes in full; and those the learner took, the latest first: when, the level, how long and whether timed, its status, the score of each module and criterion, and whether it was passed. The log of each, with what was answered, is among the logs of the kind evaluation.

## Prompt: evaluation

Offer the learner a mock exam of a level, as the institute that examines the language sets it, ready to start: its modules are done one after another, each part an exercise. It takes long, from half an hour to four hours, so offer it when the learner wants to know where they stand, or before an exam.

## Prompt: level

The level of the exam, one of: $levels.

## Prompt: length

How long it is to take, in half hours, from 1 to 8: every part is made shorter or longer to fit.

## Prompt: timed

Whether each part must be done in its time, as in the real exam.

## Prompt: offered_evaluation

The mock exam was offered to the learner, who decides whether to start it; it runs in the tab of evaluations, and its log comes once it is over: $offered

## Prompt: focus

What the models that make the exercise are to aim it at, besides the lesson, the topics and the options, as you would brief a colleague in a sentence or two of English: a mistake that keeps coming back, a rule, a kind of sentence, what to leave out. They are told it as it is.

## Prompt: words

Words the exercise is to be made of, as the learner's vocabulary has them, such as words they got wrong or looked up; leave it out for the usual choice of their words.

## Prompt: count

How many to give, at most $most.

## Prompt: kind

Only the logs of this kind, one of: $kinds. Leave it out for logs of every kind.

## Prompt: exercise

Offer the learner the exercise "$title", ready to start: $description

## Prompt: lesson

The lesson to practise, by its id as the lessons tool gives it; empty to review the lessons practised last.

## Prompt: theory_lesson

The lesson to read, by its id as the lessons tool gives it.

## Prompt: instances

How many times the exercise is to be done.

## Prompt: topics

The topics the exercise is to be about, by their titles; none for everyday life.

## Prompt: offered

The exercise was offered to the learner, who decides whether to start it: $offered
