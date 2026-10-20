# The memories in the tutor's context

How the memories the tutor has are told in its system prompt, system.md: `listed` when it has some, `none` when it has none.

Variables:
- `$memories`: the memories, one to a line as "- [date] what it says"

## Prompt: listed

What you remember of your student from earlier lessons:
$memories

## Prompt: none

You do not remember anything of your student from earlier lessons yet.
