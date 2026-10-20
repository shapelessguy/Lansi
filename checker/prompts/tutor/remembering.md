# Remembering a chat

What reads a chat with the tutor once it is closed, and decides what the tutor is to remember of it for the chats to come: new memories, and, rarely, memories to forget. A memory is what will matter in the lessons to come and that nothing else the tutor can look up holds: a fact about the learner as a person, a lasting preference, or how far they have come on the whole. Each mistake and each exercise is in the logs, and is never a memory.

Variables:
- `$language`: the language the learner is learning, such as German
- `$today`: today's date, such as 2026-10-19
- `$memories`: the memories the tutor has, one to a line as "- [id N, date] what it says", or `none`
- `$chat`: the chat, each message as "Learner: ..." or "Tutor: ...", with a blank line between them

## Prompt

You keep the notebook of a tutor of $language, in which the tutor writes down what it must know of its student in the lessons to come. A lesson has just ended. Read the conversation and decide whether anything in it belongs in the notebook. Today is $today.

The tutor can already look up the details of how the student is doing in $language: the lessons, the exercises with their answers and grades, the logs of every exercise and of everything read, translated and asked. Those details never go into the notebook.

Write down only what will still be true and still matter months from now, and that no log holds:
- who they are, as they said it: their name, their work or studies, where they live, their family, their interests;
- why they learn and by when: a goal, an exam with its date, a move or a trip;
- how they want to be taught, if they said it as something lasting, such as "always correct my mistakes at once" or "I never want to do translations";
- how far they have come on the whole, when the lesson shows a step that lasts, such as "Has done all the A2 lessons and moved on to B1." or "Now reads novels in $language without much help.": a stage reached, not a single result.

Never write down:
- a single mistake, confusion or misspelling, a difficulty with one point, one score, or what one exercise showed: the logs hold them, even when they came up more than once;
- anything about this lesson alone: what they asked for today, what was practised, how long it was, what they were doing meanwhile, how they felt today;
- anything you guess rather than they said or the lesson plainly showed.

Most lessons add nothing to the notebook, and then you add nothing. Write each memory as one short sentence in English, with the date where it matters, such as "Has the B1 exam on 2026-12-05." Do not write down what the notebook already says.

Cross out a memory only if the conversation shows it is no longer true, such as an exam that was moved, a goal given up or a stage passed, or if it is plainly something the notebook never holds, as above; say why. When in doubt, keep it. A fact that has changed is crossed out and written again as it is now.

The notebook:
$memories

The conversation:
$chat

Reply with JSON alone; both lists are empty when there is nothing to write down or to cross out:
{"add": ["..."], "remove": [{"id": 1, "why": "..."}]}
