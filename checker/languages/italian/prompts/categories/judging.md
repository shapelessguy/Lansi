# Judging a word of a category

What a language model is told about each category of Italian when it judges whether a word is new: which is the dictionary form, and what is and is not the same word. Conjunctions, particles and interjections, which have one form only, are judged as `plain`.

## Prompt: noun

The dictionary form is the singular, or the plural for a noun that has no singular (le forbici). The same word: its plural, also one of another gender (le braccia is braccio, le uova is uovo), and the same spelling with another gender or meaning (il fine and la fine are one word). Words of their own: compounds (il portafoglio is not il foglio), diminutives and augmentatives (casetta, librone), and verbs and adjectives used as nouns (il mangiare, il vecchio).

## Prompt: verb

The dictionary form is the infinitive, without the reflexive -si (lavare for lavarsi, pentire for pentirsi). The same word: every person, tense and mood of the verb, its participles and its gerund, and the same infinitive with another meaning or used reflexively. Words of their own: verbs made with a prefix (rifare and disfare are not fare).

## Prompt: adjective

The dictionary form is the masculine singular (bello, not bella). The same word: its genders and numbers, its superlative in -issimo, and its own comparative and superlative (migliore and ottimo are buono). Words of their own: adjectives made with a prefix or a suffix (infelice, bellino), and participles that have become adjectives with a meaning of their own (interessante, stanco).

## Prompt: adverb

The dictionary form is the word itself. The same word: its comparative and superlative, for the few adverbs that have them (bene, meglio, benissimo). Adverbs in -mente are words of their own (velocemente is not veloce). Every other adverb is a word of its own.

## Prompt: pronoun

The dictionary form is the subject form, masculine singular where there are genders (io, questo, qualcuno). The same word: its object forms, genders and plural (me and mi are io; questa and questi are questo). Words of their own: each person (io, tu, lui, lei, noi, voi, loro), and each possessive (mio, tuo).

## Prompt: article

The dictionary form is the masculine singular (il, un, mio, questo). The same word: its genders, its plural and its elided forms (lo, la, l', i, gli and le are il).

## Prompt: preposition

The dictionary form is the preposition itself. The same word: the preposition fused with an article (della and dei are di, nel is in, sul is su).

## Prompt: numeral

The dictionary form of a cardinal is the word itself (tre), and of an ordinal its masculine singular (terzo). The same word: the genders and numbers of an ordinal (terza, terzi), and una of uno. A cardinal and its ordinal are two words.

## Prompt: plain

The dictionary form is the word itself, which has no other forms. Every other word is a word of its own.
