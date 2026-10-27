# The tutor's tools

What the tutor is told of each of its tools, and of what each is called with: `lessons`, `sessions`, `logs` and `evaluations` look up what the learner has done, `recaps`, `strategy` and `calendar` look up what the tutor wrote down of the lessons, the last two called with `from` and `to`; `remember` writes down a fact about the learner, called with `remember_what`, `agree_strategy` a strategy, called with `strategy_what` and `replaces`, `plan` an entry of the calendar, called with `day` and `plan_what`, and `cross_out` crosses out either, called with `entry` and `why`; `words_known` looks up the words they know, called with `categories`, `set`, `anki_only`, `sorted_by`, `reverse` and `count`; `exercise` offers the learner an exercise of practice, each listed in it as `exercise_theory`, `exercise_no_lesson`, `exercise_once` and `exercise_options` say, each option as `option_choices` or `option_number` says, `own_exercise` is said of an exercise that is offered with a tool of its own, such as one that makes nothing, and `offered` is what the tutor is told once either has; `evaluation` offers a mock exam, and `offered_evaluation` is what the tutor is told once it has. `focus` and `words` are what an exercise is steered with, and `level`, `size` and `timed` what a mock exam is set to. The names of the others are those of what the tools are called with: `count` and `kind` of `sessions` and `logs`, and `exercise_id`, `lesson`, `instances`, `topics` and `options` of an exercise.

Variables:
- `$exercises`: the exercises there are, one to a line as "- id: title. what it is", with what `exercise_theory`, `exercise_no_lesson`, `exercise_once` and `exercise_options` say of it after
- `$title`, `$description`: the title of an exercise offered with a tool of its own, and what it is, as its manifest says
- `$options`: the options of an exercise, each as `option_choices` or `option_number` says, joined by semicolons
- `$name`, `$label`: the name of an option, and what it is, as the manifest of the exercise says
- `$choices`: the choices of an option, each as "value (what it is)", joined by commas
- `$least`, `$usual`: the least an option may be, and what it is unless another fits better
- `$most`: how many there may be at most, or the most an option may be
- `$kinds`: the kinds of logs there are, joined by commas
- `$offered`: the exercise or the mock exam offered, with what it was called with, as JSON
- `$levels`: the levels there are mock exams of, joined by commas
- `$sizes`: how long the mock exam of each level takes at each size, from the first, as "A1: 43 min, 50 min, …", the levels joined by semicolons
- `$usual`: how many words, or recaps, the tool gives when it is not told how many
- `$practised`: the categories whose words practice is best built on, joined by commas, as the categories of the language say

## Prompt: lessons

The lessons of the language the learner is learning, in the order they are taught: the id of each, its level and its title, and whether the learner has practised it.

## Prompt: sessions

The learner's latest sessions of practice, the latest first: when each was, its lesson, its status, and for each of its exercises how many answers were right, partial and wrong, with the scores it came to.

## Prompt: logs

The learner's latest logs, the latest first, each with its id, its kind, when it was written, what it is about and what it says. The logs of exercises are short accounts of what worked and what did not; the others are of what was translated or asked about while reading.

## Prompt: evaluations

The mock exams there are, by level, each with its modules and how long it takes in full; and those the learner took, the latest first: when, the level, how long and whether timed, its status, the score of each module and criterion, and whether it was passed. The log of each, with what was answered, is among the logs of the kind evaluation.

## Prompt: words_known

The words the learner knows, as their vocabulary has them: every word they met in the chats, the exercises and what they read, and those of their Anki cards. With each, its categories, as a word spelt alike in several categories is one word, how often the learner used it in what they wrote ("used") and how often it came up in what a model wrote to them ("seen"), and the day each last did; and how many words there are in all of those asked for. Use it to pick the words an exercise is to build on: those they have not used for long, those they see but never write, or those of a set or of Anki. Build on words of these categories, asking for them by name: $practised. The words of the others are few and come up in every sentence anyway. Ask for $usual words, which is what you are given if you do not say, unless what you and your student agreed on needs more or fewer.

## Prompt: categories

Only the words of these categories; leave it out for words of every category.

## Prompt: set

Only the words of this set, one the learner made of their words for a purpose.

## Prompt: anki_only

Only the words that have a card in review in the learner's Anki, which they study there.

## Prompt: sorted_by

Which words come first: last_used, last_used_by_user and last_used_by_assistant, those used most lately by either, by the learner or by a model, and the ones never used last; first_used, those met most lately; most_used, most_used_by_user and most_used_by_assistant, those used most often; added, those stored most lately; alphabetical; random, a different choice every time. last_used if left out.

## Prompt: reverse

Whether to turn the order round, such as to have the words the learner has not used for longest first, with those never used before all others.

## Prompt: evaluation

Offer the learner a mock exam of a level, as the institute that examines the language sets it, ready to start: its modules are done one after another, each part an exercise. It takes long, from about three quarters of an hour to as long as the real exam, so offer it when the learner wants to know where they stand, or before an exam.

## Prompt: level

The level of the exam, one of: $levels.

## Prompt: size

How long it is to take, from 1, the shortest, to $most, the exam in full: each part is made shorter by as much as still makes a fair task. At each size it takes: $sizes.

## Prompt: timed

Whether each part must be done in its time, as in the real exam.

## Prompt: offered_evaluation

The mock exam was offered to the learner, who decides whether to start it; it runs in the tab of evaluations, and its log comes once it is over: $offered

## Prompt: focus

The brief of what the exercise is to contain, in English, which the models that make it follow before the lesson, the topics and everything else they know: the rule or the mistake it practises, what to leave out, and what each item is to be, one to a line, with the construction it practises, the words it uses and, where it matters, the answer it expects. They know nothing of the learner but this, so be detailed; they are told it as it is, and give it the form of the exercise. Empty only where the learner asked for the exercise as it is, with nothing to aim it at.

## Prompt: words

Words the exercise is to be made of, as the learner's vocabulary has them, such as words they got wrong or looked up; leave it out for the usual choice of their words.

## Prompt: count

How many to give, at most $most.

## Prompt: kind

Only the logs of this kind, one of: $kinds. Leave it out for logs of every kind.

## Prompt: exercise

Offer the learner an exercise, ready to start; it appears under your message. The exercises:
$exercises

## Prompt: own_exercise

Offer the learner the exercise "$title", ready to start; it appears under your message: $description

## Prompt: exercise_id

The exercise to offer, by its id.

## Prompt: exercise_theory

It teaches a lesson rather than asks, and is called with the lesson alone.

## Prompt: exercise_no_lesson

It practises no lesson, and is called with none.

## Prompt: exercise_once

It is done once, and is called with no instances.

## Prompt: exercise_options

Options: $options.

## Prompt: option_choices

$name, $label, one of $choices, the first unless another fits better

## Prompt: option_number

$name, $label, from $least to $most, $usual unless another fits better

## Prompt: options

The options of the exercise, as its line in the list of exercises gives them, such as {"sentences": 5}; one left out is as usual, and {} leaves them all as usual.

## Prompt: lesson

The lesson to practise or to read, by its id as the lessons tool gives it; empty to review the lessons practised last, except for one that teaches a lesson.

## Prompt: instances

How many times the exercise is to be done, 1 if left out.

## Prompt: topics

The topics the exercise is to be about, by their titles; none for everyday life.

## Prompt: offered

The exercise was offered to the learner, who decides whether to start it: $offered

## Prompt: recaps

The recaps of your latest lessons with the learner, the latest first, each with its day and what was done in it, a point to a line, as you wrote it once the lesson was over. Gives the $usual latest if you do not say how many.

## Prompt: strategy

The strategy: how you and the learner agreed to hold the lessons, each with its id and the day it was agreed on.

## Prompt: calendar

What you and the learner planned to do on a day, such as a mock exam or a chapter to have read by then, by day, each with its id and the day it was planned on; one that was crossed out says by whom and why, such as that it was done. Every entry if you give neither day.

## Prompt: from

The first day to give the entries of, as YYYY-MM-DD; leave it out for every day before `to`.

## Prompt: to

The last day to give the entries of, as YYYY-MM-DD; leave it out for every day after `from`.

## Prompt: agree_strategy

Write down a strategy, as soon as you and the learner agree on it: how the lessons are to be held from now on, such as what a lesson is made of and in what order. Call it only once they plainly agreed, never for a way you merely suggested, and never for what you do in this lesson alone. A day set for something, such as a mock exam, goes on the calendar instead.

## Prompt: strategy_what

The strategy, whole, as you agreed on it, in a sentence or two of English, such as "Each lesson: first one exercise, then a chapter of the book they are reading, talked over."

## Prompt: replaces

The ids of the strategies this one takes the place of, which are crossed out; leave it out when it adds to them.

## Prompt: remember

Write down a fact about the learner at once, for every lesson to come: whenever they ask you to remember something, and whenever they tell you something about themselves that lasts, such as their name, their work, a goal, an exam and its date, or how they always want to be taught or talked to. Never tell them you noted or will remember something without calling it, or agree_strategy or plan for what belongs there: a way of holding the lessons is a strategy, a day set for something goes on the calendar.

## Prompt: remember_what

What to remember, as one short sentence of English about the learner, such as "Wants every exercise to list the words it uses before it starts." or "Has the B1 exam on 2026-12-05."

## Prompt: plan

Put something on the calendar, as soon as you and the learner agree to do it on a day, today or later, such as a mock exam, or a chapter to have read. Call it only once they plainly agreed.

## Prompt: day

The day, as YYYY-MM-DD, worked out from what the learner said, such as "next Friday" or "21.10.26", with today's date.

## Prompt: plan_what

What is to be done on the day, in a sentence of English, such as "A mock exam of A2, in full."

## Prompt: cross_out

Cross out a strategy or an entry of the calendar: a strategy given up, an entry done, cancelled or moved. An entry moved is crossed out and planned again for its new day.

## Prompt: entry

The id of the strategy or of the entry of the calendar, as the tool that looks them up gives it.

## Prompt: why

Why it is crossed out, in a few words, such as "done" or "moved to 2026-11-02".
