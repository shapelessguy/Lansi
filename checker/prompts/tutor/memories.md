# The memories in the tutor's context

How the memories the tutor has are told in its system prompt, system.md, in this order: `earlier`, the recaps of the chats before the latest, as recap.md writes them, when there are any; `listed` when it has memories that last, `none` when it has none; and `latest`, the recap of the latest chat, when there is one.

Variables:
- `$memories`: the memories that last, one to a line as "- [date] what it says"
- `$recaps`: the recaps of the chats before the latest, the oldest first, each as "Recap of the lesson of DATE:" with its lines under it, and a blank line between them
- `$recap`: the recap of the latest chat, in the same way

## Prompt: earlier

What happened in your earlier lessons with your student, the oldest first:
$recaps

## Prompt: listed

What you remember of your student from earlier lessons:
$memories

## Prompt: none

You do not remember anything of your student from earlier lessons yet.

## Prompt: latest

What happened in your last lesson with your student:
$recap
