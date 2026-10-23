# A part of a book, transformed

What the reasoning model is told to transform one part of a book with, such as a story of a book of short stories: what the learner asked for, and the part as a JSON object of its blocks. It answers with an object of the same keys, from which the version is made.

Variables:
- `$instructions`: what the learner asked for, the prompt they chose and perhaps changed, with its keywords filled in
- `$part`: the part, as a JSON object whose keys name its blocks, in order, each with its text
- `$reasoning`: how long to reason, as reasoning.md says, when the model reasons within a budget, and nothing otherwise

## Prompt

You transform a part of a book, as the instructions below say. The part is a JSON object: each key names a block of the book (a paragraph, a heading, a title, a line of a list or of a poem) and its value is the text of that block, in the order they come in the book.

Instructions:
$instructions

$reasoning

Answer with a single JSON object and nothing else: no explanation, no Markdown fence around it. The structure must not change at all. The object has exactly the same keys as the one you are given, in the same order, each with the text of its block transformed as the instructions say:
- every key you are given is in your answer once, written exactly as it was given; add no key, leave none out, and never merge two blocks into one or split one into two, even if the instructions would read better that way;
- a block that is a heading or a title stays a heading or a title, short as it was; a block that needs no change, such as a name or a number, is repeated as it is;
- each value is plain text: no Markdown, no HTML, no notes of your own;
- escape quotation marks, backslashes and line breaks in the values as JSON requires.

The part:
$part
