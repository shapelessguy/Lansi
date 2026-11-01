# Writing lessons

How the lessons in this directory are written, so that each new one looks
and reads like the others. It follows `languages/german/grammar/WRITING.md`,
with what Italian does otherwise. A lesson is practised by the exercises and
taught by **Theory**, which shows its `more_info` page by page with a chat
beside it (`checker/exercises/theory/`).

## Where things are

- `points.json`: the grammar points, each one decision the
  learner makes: `id`, `level`, `title`, `statement`, `when`,
  `confused_with`, `requires`. Add the points a lesson needs here first.
  Ids are Italian, in small letters with hyphens (`passato-prossimo-essere`);
  titles, statements and `when` are in English, as the exercises read them.
- `lessons/<id>.json`: one file per lesson: `id`, `level`,
  `title` (in Italian), `points` (each
  `{ "id": ..., "role": "new" | "review" | "preview" }`) and `more_info`,
  the pages of theory.
- `order.json`: the ids of the lessons in the order they are taught.
- Ask before adding fields to points or lessons: only what something reads
  is kept.

`more_info` is shown by Theory alone. The exercises are told the points'
statements and not the pages, so a rule the exercises must follow belongs
in a point, not only on a page.

## Source and language

- There is no book: the lessons follow the usual progression of Italian
  for foreigners from A1 to B2 (articles and nouns, essere and avere, the
  present, prepositions, the passato prossimo, pronouns, the imperfetto,
  the future and the conditional, the imperative, the congiuntivo, the
  periodo ipotetico, the passive, indirect speech), with the level of each
  point as the CELI exams expect it.
- Explanations are in **Italian**, simple enough for the lesson's level,
  addressing the learner as *tu*. Short sentences, one idea each. At A1
  the words of explanation are the commonest ones: *verbo, nome, maschile,
  femminile, singolare, plurale, frase, domanda*.
- Meanings of words go in a column **Significato**, in English.
- Every example is a natural, everyday sentence a learner at the level
  can read, of life in Italy: names such as Marco, Giulia, Luca, Sara;
  places such as Roma, Milano, Napoli, Bologna.

## The pages

Pages are Markdown, with a line of `---` between them. Each page starts
with a `# Heading`, which is also its name in the list of pages: keep it to
two to five words, in Italian.

A lesson has 8 to 10 pages, in about this order:

1. **What it is**: the idea, with a first table and why it matters.
2. **The core rule**, as a diagram (a table coloured by sentence part).
3. **One page per further aspect**: a person, a tense, a group of words.
   One aspect per page.
4. **Casi particolari**: the exceptions and small irregularities.
5. **Attenzione** or a comparison with what it is confused with, such as
   *Passato prossimo o imperfetto?*
6. **Errori tipici**: a table `Sbagliato | Giusto | Perché?`, 5 to 8 rows,
   the wrong sentence marked `{x:...}`. Every row in *Sbagliato* must
   really be wrong, not merely less usual: *Ieri sono andato* is not a
   mistake, *Ieri ho andato* is.
7. **In breve**: a `[!merke] Ricorda` box with the whole lesson in 4 to 6
   bullets, then **Prova tu:** with 6 to 8 numbered tasks, and the line
   *Scrivi le tue risposte nella chat, o chiedi se qualcosa non è chiaro.*
   The chat checks the answers.

## Size

The page is shown in a card about **720 px wide**, and every page takes
the height of the tallest, so that the buttons below stay in place. A page
that is much taller than the others leaves the rest half empty; one that
is much shorter looks thin. Aim for every page to be about the same:

- One main table of up to 8 rows plus one or two boxes, or two small
  tables. About 450 to 600 px tall at that width.
- Tables of up to 4 columns, with short cells (a word, a short phrase). A
  column of whole example sentences only in a table of 3 columns. A
  paradigm (a row label and three forms, or maschile | femminile in the
  singular and the plural) may have 5 columns, as its cells are a word or
  two.
- A long list goes into two pairs of columns
  (`Verbo | Participio | Verbo | Participio`), not one long table.
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

A part of a sentence is coloured with `{mark:text}`. The marks are those
of every language; Italian uses them so:

| Mark | Colour | For |
|---|---|---|
| `{v:sono}` | blue | the conjugated verb, or the auxiliary |
| `{i:andato}` | purple | the verb that is not conjugated: a participle, an infinitive, a gerund |
| `{e:iamo}` | pink | an ending |
| `{c:isc}` | red | a change of the stem, such as *-isc-* or *esco* |
| `{h:gli}` | yellow | the word the lesson is about: an article, a pronoun, a preposition |
| `{x:Ho andato.}` | red, struck | what is wrong |
| `{p:...}` | orange | a prefix; Italian lessons do not use it |
| `{s:...}` | green | the subject; not used so far |

- Colour only what the lesson is about. Everything else stays plain.
- A mark may sit inside a word: `parl{e:iamo}`, `fin{c:isc}o`,
  `andat{e:a}`.
- A table cell that is *all* one mark is coloured as a whole. This makes a
  table a diagram of a sentence:

  ```
  | Soggetto | Ausiliare | Participio | Resto |
  |---|---|---|---|
  | Giulia | {v:è} | {i:andata} | a Roma. |
  ```

- Under the first diagram of a lesson, say what the colours are:
  `Colori: {v:ausiliare} · {i:participio}`.
- Marks do not nest, and hold no `{`, `}` or `|`.

### Boxes

A quote whose first line is `[!kind]` is a coloured box. The kinds are
fixed keywords, and the renderer's default titles are German, so **every
box is given its Italian title**, always the same for a kind:

| Box | Colour | Title | For |
|---|---|---|---|
| `> [!merke] Ricorda` | blue | Ricorda | the rule |
| `> [!tipp] Consiglio` | green | Consiglio | a way to remember it |
| `> [!achtung] Attenzione` | orange | Attenzione | a trap |
| `> [!beispiel] Esempi` | purple | Esempi | examples |

```
> [!merke] Ricorda
> The rule to remember.
```

Another title may replace these where it says more, such as
`> [!tipp] Pronuncia`. Use one or two boxes a page, not more.

## Writing the file

`more_info` is one JSON string, which is hard to write by hand. Write the
pages as Markdown in a raw string of a short Python script, and have it
write the file with `json.dumps(..., ensure_ascii=False)`. Keep the layout
the other lessons have: each point on a line of its own, `more_info` last.
The script may give a box written as `> [!merke]` its Italian title.

A lesson may name a point of a later lesson as `preview` only once that
point is in `points.json`: a lesson naming a point there is not is refused.
Write each rule only once: before adding a point, look for one that says it
already, and give it the role `review` instead.

## Checking

- `just check`. The test
  `test_the_lessons_of_italian_have_theory_to_show` in
  `checker/languages/italian/test_language.py` reads every lesson.
- Open the lesson as Theory in the app, in light and dark, and turn every
  page: the buttons must not move much, no page may be much taller than the
  rest, and no table may need to scroll.
