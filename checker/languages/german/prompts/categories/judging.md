# Judging a word of a category

What a language model is told about each category of German when it judges whether a word is new: which is the dictionary form, and what is and is not the same word. Conjunctions, particles and interjections, which have one form only, are judged as `plain`.

## Prompt: noun

The dictionary form is the nominative singular, without an article, or the nominative plural for a noun that has no singular. The same word: its cases and its plural, and the same spelling with another gender or meaning (der, das and die Band are one word). Words of their own: compounds (Haustür is not Haus), diminutives (Häuschen), and verbs and adjectives used as nouns (das Essen, der Alte).

## Prompt: verb

The dictionary form is the infinitive, without `sich`. The same word: every person, tense and mood of the verb and its participles, and the same infinitive with another meaning or used reflexively. Words of their own: verbs with a prefix, separable or not (anrufen, berufen and rufen are three words).

## Prompt: adjective

The dictionary form is the positive without an ending (schön, not schöne). The same word: every ending, and the comparative and the superlative. Words of their own: adjectives made with a prefix or a suffix (unschön, kindlich), and participles that have become adjectives with a meaning of their own (bekannt, spannend).

## Prompt: adverb

The dictionary form is the word itself. The same word: its comparative and superlative, for the few adverbs that have them (gern, lieber, am liebsten). Every other adverb is a word of its own.

## Prompt: pronoun

The dictionary form is the nominative, masculine singular where there are genders (ich, dieser, jemand). The same word: its cases, genders and plural (mich and mir are ich; diese and diesem are dieser). Words of their own: each person (ich, du, er, sie, es, wir, ihr), and each possessive (mein, dein).

## Prompt: article

The dictionary form is the nominative masculine singular (der, ein, kein, mein). The same word: its cases, genders and plural (die, das, dem and den are der).

## Prompt: preposition

The dictionary form is the preposition itself. The same word: the preposition fused with an article (zum and zur are zu, im is in).

## Prompt: numeral

The dictionary form of a cardinal is the word itself (drei), and of an ordinal the form with -e (dritte). The same word: the endings of an ordinal (dritten, dritter), and of eins (ein, eine, einen). A cardinal and its ordinal are two words.

## Prompt: plain

The dictionary form is the word itself, which has no other forms. Every other word is a word of its own.
