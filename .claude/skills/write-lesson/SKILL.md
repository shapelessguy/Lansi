---
name: write-lesson
description: Write or rework a grammar lesson of the practice app (its points and its pages of theory in more_info), following the book and the house style. Use when asked to add, enrich or fix a lesson in checker/languages/<language>/grammar/.
---

# Write a lesson

1. Read `checker/languages/german/grammar/WRITING.md` in full and follow it: it holds the
   structure, the size of pages, the colour marks and the boxes.
2. Read one lesson already written, such as
   `checker/languages/german/grammar/lessons/trennbare-verben.json`, for the tone.
3. Find the chapter in `chat-ui/Grammatik aktiv A1B1.md`, and note what it
   covers. Do not copy its text.
4. Add the points the lesson needs to `points.json`, then write the lesson
   with a small Python script in the scratchpad, as WRITING.md says.
5. Run `just check`, then look at every page as Theory in the app, in light
   and dark.
6. Tell the user what the lesson covers, page by page, so they can review
   it.
