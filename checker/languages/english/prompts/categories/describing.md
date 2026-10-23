# Describing a word of a category

What a language model is told about each category of English when it describes a new word. Prepositions, conjunctions, particles and interjections, which have one form only, are described as `plain`.

Variables:
- `$meanings_rule`: the rule about meanings, `meanings` of checker/prompts/categories/rules.md, which every language shares
- `$empty_rule`: the rule about forms a word has not, `empty` of rules.md here
- `$listing`: the rule about listing the forms of a word that changes, `listing` of rules.md here

## Prompt: noun

`plural` is the plural of the noun, or its singular again for one whose plural is the same (sheep); leave it empty for a noun that is not counted (information). $empty_rule $meanings_rule

## Prompt: verb

`present` is a form of the present other than the base form and the third person, which only be has (`am / are`). `third_person` is the third person singular of the present (goes, has, is), `past` the past (went, was / were), `past_participle` the past participle (gone, been) and `ing` the form in -ing (going). For a modal verb, which has no such forms, leave them empty, and give its past as `past` if it has one (can, could). $empty_rule $meanings_rule

## Prompt: adjective

`comparative` and `superlative` are those of one word (bigger, biggest; better, best); leave them empty for an adjective that makes them with more and most. $empty_rule $meanings_rule

## Prompt: adverb

`comparative` and `superlative` are those of one word, for the adverbs that have them (better, best; sooner, soonest); leave them empty for the others. $empty_rule $meanings_rule

## Prompt: pronoun

$listing $meanings_rule

## Prompt: article

$listing $meanings_rule

## Prompt: numeral

$listing For a numeral that does not change list no forms. $meanings_rule

## Prompt: plain

$meanings_rule
