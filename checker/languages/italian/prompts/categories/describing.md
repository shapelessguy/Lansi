# Describing a word of a category

What a language model is told about each category of Italian when it describes a new word. Conjunctions, particles and interjections, which have one form only, are described as `plain`.

Variables:
- `$meanings_rule`: the rule about meanings, `meanings` of checker/prompts/categories/rules.md, which every language shares
- `$empty_rule`: the rule about forms a word has not, `empty` of rules.md here
- `$listing`: the rule about listing the forms of a word that changes, `listing` of rules.md here

## Prompt: noun

List every variant of the noun as one of `variants`: a variant of its own wherever the gender or the plural differ, and nowhere else. il fine and la fine are two; il braccio with the plural le braccia, of the body, and il braccio with the plural i bracci, of a river or a lamp, are two; il riso, which is rice and a laugh alike, is one. For each give its `gender`, all the meanings of that variant, the noun in the `singular` and the `plural`, without an article, and the gender of the plural, which is that of the singular but for a few, such as le uova and le braccia, which are feminine. A noun that does not change, such as città or film, has the same form in both. $empty_rule $meanings_rule

## Prompt: verb

Give the forms that are one word: no tenses made with an auxiliary. In each table give the form for each person without the pronoun and without a reflexive pronoun: `lavo`, not `mi lavo`. `lui` stands for lui, lei and Lei, and `loro` for loro. `participio_passato` is the past participle in the masculine singular (andato, fatto), and `gerundio` the gerund (andando). `auxiliary` is the verb the passato prossimo is made with: essere for a verb that is used reflexively, avere o essere for one that takes either by its meaning, such as correre or cominciare. `imperativo` is the imperative of tu, noi and voi, the first that of a positive command (va' / vai, fa' / fai). $empty_rule $meanings_rule

## Prompt: adjective

Give the adjective in each gender and number. An adjective in -e has one form for both genders (felice, felici), and one that does not change has the same form in all four (blu, rosa). `comparativo` is a comparative of one word of its own, as buono has migliore, cattivo peggiore, grande maggiore and piccolo minore; leave it empty for the others, which make it with più. `superlativo` is the superlative in the masculine singular: in -issimo (bellissimo), and also one of its own where there is one, such as `buonissimo / ottimo`; leave it empty for an adjective that has none. $empty_rule $meanings_rule

## Prompt: adverb

`comparativo` and `superlativo` are for the few adverbs that have them (bene, meglio, benissimo / ottimamente; molto, più, moltissimo). $empty_rule $meanings_rule

## Prompt: pronoun

$listing $meanings_rule

## Prompt: article

$listing $meanings_rule

## Prompt: preposition

`contractions` are the forms it has fused with an article (del, dello, della, dei, degli, delle, dell'), if any. $meanings_rule

## Prompt: numeral

$listing For a numeral that does not change list no forms. $meanings_rule

## Prompt: plain

$meanings_rule
