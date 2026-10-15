# Writing lessons

How the lessons in this directory are written, so that each new one looks
and reads like the others. A lesson is practised by the exercises and
taught by **Theory**, which shows its `more_info` page by page with a chat
beside it (`checker/exercises/theory/`).

## Where things are

- `<Language>/points.json`: the grammar points, each one decision the
  learner makes: `id`, `level`, `title`, `statement`, `when`,
  `confused_with`, `requires`. Add the points a lesson needs here first.
- `<Language>/lessons/<id>.json`: one file per lesson: `id`, `level`,
  `title`, `points` (each `{ "id": ..., "role": "new" | "review" | "preview" }`)
  and `more_info`, the pages of theory.
- Ask before adding fields to points or lessons: only what something reads
  is kept.

`more_info` is shown by Theory alone. The exercises are told the points'
statements and not the pages, so a rule the exercises must follow belongs
in a point, not only on a page.

## Source and language

- The book is `chat-ui/Grammatik aktiv A1B1.md`, an OCR of *Grammatik aktiv
  A1–B1*. Follow its order of chapters and what each covers, but write
  the explanations and examples yourself: never copy its text. The OCR is
  garbled in places anyway.
- Explanations are in **German**, simple enough for the lesson's level,
  addressing the learner as *du*. Short sentences, one idea each.
- Meanings of words go in a column **Bedeutung**, in English.
- Every example is a natural, everyday sentence a learner at the level
  can read.

## The pages

Pages are Markdown, with a line of `---` between them. Each page starts
with a `# Heading`, which is also its name in the list of pages: keep it to
two to five words.

A lesson has 8 to 10 pages, in about this order:

1. **What it is**: the idea, with a first table and why it matters.
2. **The core rule**, as a diagram (a table coloured by sentence part).
3. **One page per further aspect**: a case, a sentence type, a group of
   words. One aspect per page.
4. **Besonderheiten**: the exceptions and small irregularities.
5. **Vorsicht** or a comparison with what it is confused with.
6. **Typische Fehler**: a table `Falsch | Richtig | Warum?`, 5 to 8 rows,
   the wrong sentence marked `{x:...}`. Every row in *Falsch* must really
   be wrong.
7. **Kurz gesagt**: a `[!merke]` box with the whole lesson in 4 to 6
   bullets, then **Probier es aus:** with 6 to 8 numbered tasks, and the
   line *Schreib deine Antworten in den Chat, oder frag, wenn etwas nicht
   klar ist.* The chat checks the answers.

## Size

The page is shown in a card about **720 px wide**, and every page takes
the height of the tallest, so that the buttons below stay in place. A page
that is much taller than the others leaves the rest half empty; one that
is much shorter looks thin. Aim for every page to be about the same:

- One main table of up to 8 rows plus one or two boxes, or two small
  tables. About 450 to 600 px tall at that width.
- Tables of up to 4 columns, with short cells (a word, a short phrase). A
  column of whole example sentences only in a table of 3 columns. A
  paradigm (a row label and maskulin | neutral | feminin | Plural) may
  have 5 columns, as its cells are a word or two.
- A long list goes into two pairs of columns
  (`Präfix | Beispiele | Präfix | Beispiele`), not one long table.
- A page that is only a paragraph or two gets a table, an example box or a
  summary table instead of staying short.
- Tables span the whole card.

## Markup

The renderer (`checker/exercises/theory/ui/markdown.js`) knows headings,
paragraphs, **bold**, *italic*, ~~struck~~, `code`, lists (one level),
quotes, tables and `---`. No links, images or nested lists. A gap to fill
in a task is `___`. A `|` inside a cell breaks the table. Lines of a box
run together into one paragraph: put a line of `>` alone between two
paragraphs of a box.

### Colour

A part of a sentence is coloured with `{mark:text}`:

| Mark | Colour | For |
|---|---|---|
| `{v:stehe}` | blue | the conjugated verb |
| `{p:auf}` | orange | a prefix |
| `{i:aufstehen}` | purple | a verb at the end, such as an infinitive |
| `{e:st}` | pink | an ending |
| `{c:ie}` | red | a vowel that changes |
| `{x:Ich aufstehe.}` | red, struck | what is wrong |
| `{h:...}` | yellow | anything else that must stand out |
| `{s:ich}` | green | the subject; not used so far |

- Colour only what the lesson is about. Everything else stays plain: the
  subject, the middle of a sentence, the words around.
- A mark may sit inside a word: `l{c:ie}st`, `mach{e:st}`.
- A table cell that is *all* one mark is coloured as a whole. This makes a
  table a diagram of a sentence:

  ```
  | Position 1 | Position 2 | Mitte | Ende |
  |---|---|---|---|
  | Ich | {v:stehe} | jeden Tag um 7 Uhr | {p:auf} |
  ```

- Under the first diagram of a lesson, say what the colours are:
  `Farben: {v:konjugiertes Verb} · {p:Präfix}`.
- Marks do not nest, and hold no `{`, `}` or `|`.

### Boxes

A quote whose first line is `[!kind]` is a coloured box:

```
> [!merke]
> The rule to remember.
```

- `merke` (blue): the rule.
- `tipp` (green): a way to remember it.
- `achtung` (orange): a trap.
- `beispiel` (purple): examples.

A title after the kind replaces the default one: `> [!tipp] Aussprache`.
Use one or two boxes a page, not more.

## Writing the file

`more_info` is one JSON string, which is hard to write by hand. Write the
pages as Markdown in a raw string of a short Python script, and have it
write the file with `json.dumps(..., ensure_ascii=False)`. Keep the layout
the other lessons have: each point on a line of its own, `more_info` last.

A lesson may name a point of a later lesson as `preview` only once that
point is in `points.json`: a lesson naming a point there is not is refused.
Write each rule only once: before adding a point, look for one that says it
already, and give it the role `review` instead.

## Checking

- `just check`. The test
  `test_the_lessons_that_are_kept_have_theory_to_show` in
  `checker/exercises/theory/test_backend.py` reads every lesson.
- Open the lesson as Theory in the app, in light and dark, and turn every
  page: the buttons must not move much, no page may be much taller than the
  rest, and no table may need to scroll.
