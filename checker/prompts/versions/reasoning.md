# How long to reason over a part of a book

What the reasoning model is told of how much it may reason before it settles how to transform a part, put into plan.md as `$reasoning`.

Variables:
- `$budget`: the most tokens it may reason in

## Prompt

You have at most $budget tokens to reason in, and the part does not need all of them. Use them to settle what is hard, such as the tone, the names, the words the instructions call for and the passages that are hard to render. Do not draft the part, or any block of it, while you reason.
