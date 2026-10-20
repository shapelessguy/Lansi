# How the prompts are used

What makes the server ask a model, which prompt it is told, and what fills
each of the prompt's `$variables`. The prompts are in `prompts/` (as
`prompts.py` describes), those of an exercise in the `prompts.toml` of its
directory in `exercises/`; a file in `languages/<language>/prompts/` stands
for the one of the same name in `prompts/` (marked `*`).

A box is a prompt sent to a model; a line into it, a smaller prompt or a
value that fills one of its variables.

## Chatting

The chat goes from the browser to OpenRouter and does not pass through
`prompts/`.

```mermaid
flowchart LR
    message([user sends a message]) --> system["chat system prompt<br/>the chat's own prompt, expanded by<br/>expandPrompt() in Chat.tsx:<br/>word lists, language, level"]
    system --> chatModel[[chat model]]
    typed([a sentence is finished]) -->|POST /sentences| questions["profile questions<br/>chat-ui/src/lib/questions.ts"]
    questions --> decision1[[decision model]]
    message -.->|stored chat, after it settles| intake([vocabulary intake])
```

## Vocabulary intake

Run by the processor on chats and on what was written in exercises once
they have settled, and at once by `POST /vocabulary/words` and
`POST /vocabulary/selection`. Each word goes through these steps.

```mermaid
flowchart TD
    word([a word and its sentence]) --> question

    criteria["categories/criteria.&lt;category&gt; *"] -->|$criterion| question
    notStored["categories/not_stored.&lt;name&gt;"] -->|$criterion| question
    question["<b>intake.question</b><br/>$language ← the vocabulary's language<br/>$criterion<br/><i>decision model, once for each category</i>"]

    question -->|"a category, not stored yet"| judging
    judgingRules["categories/judging.&lt;category&gt; *"] -->|$rules| judging
    capitals["intake.capitals<br/>$language"] -->|$capitals| judging
    judging["<b>intake.judging</b><br/>$language<br/>$name ← the category<br/>$categories ← every category, joined by commas<br/>$rules, $capitals<br/><i>language model; also given the stored words spelt most like it</i>"]

    judging -->|"elsewhere: another category"| judging
    judging -->|new word| describing
    describingRules["categories/describing.&lt;category&gt; *<br/>$meanings_rule ← categories/rules.meanings<br/>$empty_rule ← rules.empty (German)<br/>$listing ← rules.listing (German)"] -->|$rules| describing
    describing["<b>intake.describing</b><br/>$language<br/>$name ← the category<br/>$rules<br/><i>language model</i>"]

    judging -.->|a problem| rescuing
    describing -.->|a problem| rescuing
    capitals -->|$capitals| rescuing
    rescuing["<b>intake.rescuing</b><br/>$language, $categories, $capitals<br/>$rules ← every judging rule, as '- name: rules'<br/><i>language model; also told the problem</i>"]
```

## Translating a selection

```mermaid
flowchart LR
    selected([text selected in a chat or a book]) -->|POST /translate| translating
    translating["<b>translating.translating</b><br/>$language ← the language learned<br/>$into ← the language of explanations<br/><i>given the passage with [[selection]]</i>"]

    translating -->|"the learner asks about it<br/>POST /translate/chat"| chatting
    chatting["<b>translating.chatting</b><br/>$language, $into<br/>$passage ← with [[selection]]<br/>$selection<br/>$translation ← the one given"]

    chatting -->|"the side chat is closed<br/>POST /translate/chat/end"| writing
    names["lookups.names.user / .assistant"] -->|names in $chat| writing
    cut1["cut"] -->|$chat too long| writing
    writing["<b>lookups.writing</b><br/>$language, $into, $passage, $translation<br/>$chat ← 'name: text' for each message<br/>$matters ← MAX_MATTERS<br/><i>writes a log for each matter</i>"]

    translating -->|no side chat| plain["<b>lookups.translation</b>, no model<br/>asked: $selection, $sentence<br/>translated: $translation"]
```

## An exercise

An exercise is run in a process of its own. `exercises/kit.py` makes the
pieces that the exercise's prompts are filled with from what the session
tells it (its context); what an exercise asks of a model is in its
`prompts.toml`.

```mermaid
flowchart TD
    session([a session of practice, or a part of an evaluation]) --> context[(context of the exercise)]

    context --> level["$level<br/>kit.level.with_sentences<br/>($level, $sentences ← kit.level_sentences.&lt;A1…C2&gt;)<br/>or kit.level.plain ($level)"]
    context --> topics["$topics<br/>kit.topics.none / one ($topic) /<br/>several / mixed ($topics),<br/>each topic as kit.topics.described ($title, $description)"]
    context --> words["$words<br/>kit.words.only / prefer<br/>($language, $lemmas ← the learner's words, best fit first)"]
    context --> lesson["$lesson<br/>kit.lesson.heading ($title, $level)<br/>+ kit.lesson.point ($title, $role, $statement, $when)<br/>for each point"]
    context --> plan["$plan<br/>kit.plan.once / repeated<br/>+ the numbered points"]
    context --> exam["$exam<br/>kit.exam ($exam ← what the exam says the part is like)<br/>empty in practice"]
    context --> guidance["$guidance<br/>what the app said; empty if nothing"]
    context --> made["$made<br/>the exercise's own <i>made</i> ($listed ← sentences made before)"]
    criteria["$criteria<br/>a line for each of kit.criteria.task / coherence /<br/>vocabulary / structures / pronunciation"]

    level & topics & words & lesson & plan & exam & guidance & made --> making
    making["<b>making</b> / <b>planning</b> / <b>teaching</b><br/>the exercise's prompt that makes an instance<br/>+ $language, $into, $count and its own variables"]
    making --> answer([the learner answers])
    criteria --> grading
    answer --> grading["<b>judging</b> / <b>rating</b> / <b>checking_form</b><br/>the exercise's prompt that grades the answer"]
    grading --> over([the exercise is over]) --> log([log of the exercise])
    answer -.->|what was written, after it settles| intake([vocabulary intake])
```

The variables of each exercise's prompts:

| Exercise | Prompt | Variables |
| --- | --- | --- |
| cloze | making | count guidance into language lesson level made plan topics words |
| comprehension | making | answers by count exam guidance heard kind language length lesson level made topics words |
| | made | listed |
| oral | making | count exam guidance language level made task topics words |
| | rating | card criteria into language level shape turns |
| | turn | answer number prompt |
| | made | listed |
| picture | planning | avoid count guidance language level topics words |
| | drawing | scene things |
| | locating | things |
| | judging | into labels language level |
| | label | given number thing |
| | words | lemmas |
| | avoid.scenes / avoid.drawn | scenes / drawn |
| stories | making | asking guidance language length lesson level made shape topics words |
| | asking | count language |
| | judging_answers | answers into language level story |
| | judging_retelling | into language level retelling story |
| | answer | answer given number question |
| | made | listed |
| theory | teaching | into language lesson level pages |
| | question | page pages question |
| translation | making | count guidance into language lesson level made topics words |
| | judging | into language lesson level sentences |
| | sentence | given into number reference source |
| writing | making | count exam guidance kind language lesson level made topics words |
| | making_form | count exam guidance language level made topics |
| | rating | count criteria into language level points shape situation text written |
| | checking_form | fields into language text |
| | field | answer given label number |

## Logs of exercises and evaluations

```mermaid
flowchart TD
    over([an exercise is over]) --> logWriting

    task["$task, one to a line:<br/>logs.task.heading ($title, $description)<br/>logs.task.level ($level)<br/>logs.task.instances ($count), then the options<br/>logs.task.topics ($topics)<br/>logs.task.lesson ($title) + kit.lesson.point for each point"] --> logWriting
    record["$record, for each instance:<br/>logs.record.instance ($number, $result)<br/>logs.record.given / written / correction / note / nothing<br/>or, with no grades:<br/>logs.record.exercise / learner ($text)<br/>cut where it is too long"] --> logWriting
    logWriting["<b>logs.writing</b><br/>$language, $task, $record<br/>$lines ← by how much the learner wrote<br/>$worked, $failed ← MAX_WORKED, MAX_FAILED"]

    ended([an evaluation ends:<br/>its last part is finished, or<br/>POST /evaluations/E/end]) --> evaluationLog
    parts["$record, for each part under its title:<br/>evaluating.scores.listed ($scores) + logs.record<br/>or evaluating.part.pending / nothing<br/>cut where it is too long"] --> evaluationLog
    evaluationLog["<b>evaluating.log</b><br/>$language, $level ← the exam's, $exam ← its name<br/>$minutes<br/>$timed ← evaluating.timed.yes / no<br/>$record<br/>$scores ← evaluating.scores.listed / none<br/>$passed ← evaluating.passed.yes / no / incomplete<br/>$lines, $worked, $failed ← constants"]
```

## Topics

```mermaid
flowchart LR
    added([a topic is added<br/>POST /topics]) --> icon["<b>topics.icon</b><br/>$topic ← its title and description<br/><i>image model, drawn on white</i>"]
```
