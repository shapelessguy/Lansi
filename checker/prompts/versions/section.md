# A section of a part of a book, transformed

What the model is told to write one section of a part of a book with, the sections one after the other, each in an answer of its own: what the learner asked for, the whole part, what was decided of how to transform it, as plan.md says, and every block of it written so far, so that the last sections are written knowing all that came before. It answers, without reasoning, with the blocks of the section, each after its marker as the part is sent, so that nothing in the text needs escaping, from which the version is made with those written before. An answer that broke off, as it reached the most it may write at once, is taken up with the same prompt, the blocks it wrote whole among those written so far and the section starting after them. It starts as plan.md does, so that what is the same in both is sent first.

Variables:
- `$instructions`: what the learner asked for, as in plan.md
- `$part`: the whole part, as in plan.md
- `$notes`: what was decided of how to transform the part, or "(none)" if the model did not reason first
- `$written`: the blocks of the part written so far, after their markers as the part is, or "(nothing yet)"
- `$first`: the key of the first block to write now
- `$last`: the key of the last block of the section

## Prompt

You are transforming a part of a book, as the instructions below say. The part is made of blocks of the book (a paragraph, a heading, a title, a line of a list or of a poem), in the order they come in the book: each starts with a line such as [[12]], the marker that names it, and its text is on the lines after it, up to the next marker.

Instructions:
$instructions

The part:
$part

What was decided of how to transform the whole part, before any of it was written, which every section keeps to:
$notes

The part is written a section at a time, each in an answer of its own. What has been written of it so far:
$written

Write now the blocks from [[$first]] to [[$last]], and only those: the blocks after them are written in other answers. Write them as the blocks before them were written: the same words for the same names and things, the same tone, the same level. Write every one of them in full, however long the part is: transform each block as the instructions say, and never shorten or summarize it.

Answer with the blocks alone, as the part is written: for each block from [[$first]] to [[$last]], in the same order, a line with its marker alone, and on the lines after it the text of the block transformed as the instructions say. Nothing before the first marker or after the last block: no explanation, no Markdown fence, no JSON. The structure must not change at all:
- every marker from [[$first]] to [[$last]] is in your answer once, written exactly as it was given; add no marker, leave none out, and never merge two blocks into one or split one into two, even if the instructions would read better that way;
- a block that is a heading or a title stays a heading or a title, short as it was; a block that needs no change, such as a name or a number, is repeated as it is;
- the text of each block is plain text, written as it is, with nothing escaped: no Markdown, no HTML, no notes of your own.
