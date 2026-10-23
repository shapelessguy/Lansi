# How long to reason over a part of a book

What the reasoning model is told of how much it may reason before it writes a part, put into part.md as `$reasoning` when it reasons within a budget.

Variables:
- `$budget`: the most tokens it may reason in

## Prompt

Think briefly before you write: you have at most $budget tokens to reason in, and the part does not need all of them. Use them only to settle what is hard, such as the tone, the names, the words the instructions call for and the passages that are hard to render. Do not write a draft of the answer, or of any block of it, while you reason: write it once, in the answer.
