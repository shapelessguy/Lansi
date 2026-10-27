# How to transform a part of a book

What the reasoning model is told to settle how to transform one part of a book, such as a story of a book of short stories, before any of it is written: what the learner asked for, and the part as its blocks, each after the marker that names it, as section.md says. It reasons over the whole part and answers with what it decided, which every answer that then writes a section of the part, as section.md says, is sent. It writes none of the part itself. The prompt starts as section.md does, so that what is the same in both is sent first.

Variables:
- `$instructions`: what the learner asked for, the prompt they chose and perhaps changed, with its keywords filled in
- `$part`: the part, its blocks in order, each on the lines after a line `[[key]]` that names it
- `$reasoning`: how long to reason, as reasoning.md says

## Prompt

You are transforming a part of a book, as the instructions below say. The part is made of blocks of the book (a paragraph, a heading, a title, a line of a list or of a poem), in the order they come in the book: each starts with a line such as [[12]], the marker that names it, and its text is on the lines after it, up to the next marker.

Instructions:
$instructions

The part:
$part

The part is going to be written a section at a time, each in an answer of its own that is sent the whole part, what you decide now and every block written before it. Before any of it is written, settle how to transform the whole of it, so that every section is written the same way. $reasoning

Then answer with what you decided, as short notes for whoever writes each section: the tone and the voice, how hard the language is, the words to use for the names, the terms and the things that come back, and how to render the passages that are hard. Write none of the part itself, not even a draft of a block.
