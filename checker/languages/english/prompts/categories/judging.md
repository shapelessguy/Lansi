# Judging a word of a category

What a language model is told about each category of English when it judges whether a word is new: which is the dictionary form, and what is and is not the same word. Prepositions, conjunctions, particles and interjections, which have one form only, are judged as `plain`.

## Prompt: noun

The dictionary form is the singular, or the plural for a noun that has no singular (scissors, trousers). The same word: its plural, and the same spelling with another meaning (a bank of a river and a bank for money are one word). Words of their own: compounds (football is not ball), and verbs and adjectives used as nouns (swimming, the poor).

## Prompt: verb

The dictionary form is the base form, without to. The same word: every form of the verb, its participles, and the same verb with another meaning. Words of their own: verbs made with a prefix (redo and undo are not do).

## Prompt: adjective

The dictionary form is the positive (big, not bigger). The same word: its comparative and superlative, also those of their own (better and best are good). Words of their own: adjectives made with a prefix or a suffix (unhappy, childish), and participles that have become adjectives with a meaning of their own (interesting, tired).

## Prompt: adverb

The dictionary form is the word itself. The same word: its comparative and superlative, for the adverbs that have them (well, better, best; soon, sooner). Adverbs in -ly are words of their own (quickly is not quick).

## Prompt: pronoun

The dictionary form is the subject form, or the singular where there is one (I, he, this, someone). The same word: its object and plural forms (me is I, him is he, these is this). Words of their own: each person (I, you, he, she, it, we, they), each possessive (mine, yours) and each reflexive (myself).

## Prompt: article

The dictionary form is the article or determiner itself, or its singular (a, the, this). The same word: its other forms (an is a, these is this).

## Prompt: numeral

The dictionary form is the word itself (three, third). A cardinal and its ordinal are two words.

## Prompt: plain

The dictionary form is the word itself, which has no other forms. Every other word is a word of its own.
