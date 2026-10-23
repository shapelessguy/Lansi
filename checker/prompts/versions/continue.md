# A part of a book, transformed, taken up again

What the model is told to go on with a part of a book whose answer broke off, as it reached the most it may write at once: the same instructions and part as part.md, what it reasoned the first time, and the blocks it has written whole. It answers, without reasoning, with an object of the blocks that are left, from which the version is made with those written before.

Variables:
- `$instructions`: what the learner asked for, as in part.md
- `$notes`: what the model reasoned before it began to write the part, or "(none)"
- `$part`: the whole part, as in part.md
- `$written`: the blocks written so far, as a JSON object of the same keys
- `$next`: the key of the first block that is left to write

## Prompt

You are transforming a part of a book, as the instructions below say, and have already written the start of it: your answer broke off because it was too long for one answer. Go on where it broke off. The part is a JSON object: each key names a block of the book (a paragraph, a heading, a title, a line of a list or of a poem) and its value is the text of that block, in the order they come in the book.

Instructions:
$instructions

What you thought about this part before you started writing it, to keep to the same choices:
$notes

Answer with a single JSON object and nothing else: no explanation, no Markdown fence around it. It has the blocks that are left, from the key "$next" to the last key of the part, in the same order, each with the text of its block transformed as the instructions say. Do not write again the blocks you have already written. The structure must not change at all:
- every key that is left is in your answer once, written exactly as it was given; add no key, leave none out, and never merge two blocks into one or split one into two;
- a block that is a heading or a title stays a heading or a title, short as it was; a block that needs no change, such as a name or a number, is repeated as it is;
- each value is plain text: no Markdown, no HTML, no notes of your own;
- write as you wrote the blocks before: the same words for the same names and things, the same tone, the same level;
- escape quotation marks, backslashes and line breaks in the values as JSON requires.

The part:
$part

What you have written so far:
$written
