# Describing a word of a category

What a language model is told about each category of German when it describes a new word. Conjunctions, particles and interjections, which have one form only, are described as `plain`.

Variables:
- `$meanings_rule`: the rule about meanings, `meanings` of checker/prompts/categories/rules.md, which every language shares
- `$empty_rule`: the rule about forms a word has not, `empty` of rules.md here
- `$listing`: the rule about listing the forms of a declined word, `listing` of rules.md here

## Prompt: noun

List every variant of the noun as one of `variants`: a variant of its own wherever the article or the forms differ, and nowhere else. der Band, das Band and die Band are three; die Bank with the plural Banken and die Bank with the plural Bänke are two; der Absatz, which is a heel, a paragraph and a landing alike, is one. For each give the article, all the meanings of that variant, and the noun, without the article, in the four cases of the singular and of the plural. $empty_rule $meanings_rule

## Prompt: verb

Give the forms that are one word: no tenses made with an auxiliary. In each table give the form for each person without the pronoun and without `sich`, as it stands in a main clause, so that a separable verb is split: `rufe an`. `er` stands for er, sie and es, and `sie` for the plural sie and for Sie. `zu_infinitive` is the infinitive with zu, such as `zu gehen` or `anzurufen`. `auxiliary` is the verb the perfect is made with. $empty_rule $meanings_rule

## Prompt: adjective

`comparative` is the comparative without an ending (schöner, höher). `positive_inflected`, `comparative_inflected` and `superlative_inflected` are the three degrees with the ending -e, as after `die` (schöne, schönere, schönste; hohe, höhere, höchste). For an adjective that takes no endings (lila, prima) give it unchanged as `positive_inflected`. $empty_rule $meanings_rule

## Prompt: adverb

`comparative` and `superlative` are for the few adverbs that have them (lieber, am liebsten). $empty_rule $meanings_rule

## Prompt: pronoun

$listing $meanings_rule

## Prompt: article

$listing $meanings_rule

## Prompt: preposition

`cases` are the cases the preposition can be followed by. `contractions` are the forms it has fused with an article (zum, zur), if any. $meanings_rule

## Prompt: numeral

$listing For a numeral that is not declined list no forms. $meanings_rule

## Prompt: plain

$meanings_rule
