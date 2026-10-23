# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Takes words into the vocabulary.

A word comes with the sentence it was used in, if it has one, and the
decision model is first asked whether that sentence is mostly written in
the language the words are taken in as. The words of one that is not, such
as an explanation in English with a German example in it, are left out, so
that the words of another language do not end up in the vocabulary.

Each word goes through the same steps. A decision model says which category
it is of. If the vocabulary has it among the forms of that category, that is
all. Otherwise a language model is given the word with the stored words
spelt most like it, and judges whether it is a form of one of them, a new
word, or no word of the category at all. A new word is then described by the
language model, in the shape its category asks for, and stored with every
form it has, so that none of them needs to be asked about again.
"""

from __future__ import annotations

import copy
import json
import threading
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from functools import lru_cache, partial
from typing import Any

from categories import (
    CATEGORIES,
    MEANINGS,
    NOT_STORED,
    Category,
    Description,
    Schema,
    categories_of,
    dictionary_form,
    one_of,
    shape,
    unknown_details,
)
from languages import DEFAULT_INTO, DEFAULT_LANGUAGE, language_of
from models import Model
from profiling import Profile, ProfileError, Profiler, Questions, post
from prompts import PROMPTS
from vocabulary import Entry, Form, Vocabularies, Vocabulary, fold

# How long a language model is given to answer, all in all. Writing out every
# form of a verb takes a while, but a model that is still at it after this
# long holds up every word that waits behind it.
CHAT_WITHIN_SECS = 90
# how long to wait for the next piece of its answer
CHAT_TIMEOUT_SECS = 30
# How many of the stored words spelt most like a word are shown to the
# language model that judges whether the word is new.
CANDIDATES = 10
# how many words are worked on at the same time
WORKERS = 12
# more than a request should bring at once
MAX_WORDS = 500
MAX_WORD_LENGTH = 100
# How many sentences the answer of whether each is in its language is kept
# for, so that one whose words are taken in again is not asked about again.
MAX_JUDGED_SENTENCES = 5000
# what the decision model is asked about a sentence before its words are
# taken in, and how sure it must be to have them taken in
IN_LANGUAGE = "in_language"
IN_LANGUAGE_AT_LEAST = 0.5


# What the decision model is asked about a word of a language: of every category whether
# the word is of it, all at once. It tells the categories apart better so
# than when it is made to pick one of them.
@lru_cache
def category_questions(language: str) -> Questions:
    return {
        name: {
            "type": "noul",
            "instructions": PROMPTS(
                "intake.question", language=language, criterion=criterion
            ),
        }
        for name, criterion in (
            *(
                (category.name, category.criterion)
                for category in categories_of(language).values()
            ),
            *NOT_STORED.items(),
        )
    }


VERDICT_SCHEMA = shape(
    verdict=one_of("form", "new", "elsewhere", "reject"),
    lemma={"type": "string"},
    category=one_of("", *CATEGORIES),
    reason={"type": "string"},
)

RESCUE_SCHEMA = shape(
    savable={"type": "boolean"},
    category=one_of("", *CATEGORIES),
    lemma={"type": "string"},
    reason={"type": "string"},
)


class IntakeError(Exception):
    """A word could not be taken in. The message says why."""


@dataclass
class Word:
    """A word to take in, with the sentence it was used in, if any."""

    word: str
    sentence: str = ""


@dataclass
class Outcome:
    """What became of a word."""

    word: str
    sentence: str
    # What happened:
    #   "known": it is a stored form; nothing was done
    #   "added": it is a new word, now stored
    #   "form": it is a form of a stored word that was not among its forms
    #   "skipped": it is of a kind that is not stored, such as a name, or
    #     its sentence is not mostly in the language
    #   "rejected": it was found not to be a word of its category
    #   "failed": it could not be worked out; `reason` says why
    # A word that cannot be placed is put to the language model once more,
    # with what went wrong, before it is given up on.
    status: str
    # the category it was found to be of, if it got that far
    category: str = ""
    # the word it is stored as or under
    entry: Entry | None = None
    reason: str = ""


# Sends a chat request body to a model and returns the decoded response.
Chat = Callable[[dict[str, Any], Model], dict[str, Any]]
# What a model is told so that it answers without reasoning first, as the
# chat and text models do unless a request says otherwise.
NO_REASONING = {"enabled": False}


def send_chat(body: dict[str, Any], model: Model) -> dict[str, Any]:
    """Send a chat request to `model`. One that does not say how the model
    is to reason has it answer without reasoning, and a model that cannot
    but reason is asked again as the request was. Raises ProfileError."""
    if "reasoning" in body:
        return _post_chat(body, model)
    try:
        return _post_chat({**body, "reasoning": NO_REASONING}, model)
    except ProfileError as error:
        if "(400)" not in str(error):
            raise
        return _post_chat(body, model)


def _post_chat(body: dict[str, Any], model: Model) -> dict[str, Any]:
    return post(
        model.endpoint("chat/completions"),
        body,
        model.headers(),
        model.where,
        CHAT_TIMEOUT_SECS,
        CHAT_WITHIN_SECS,
    )


class Intake:
    def __init__(
        self,
        vocabulary: Vocabulary | Vocabularies,
        profiler: Profiler,
        chat: Chat = send_chat,
        model: str = "",
        workers: int = WORKERS,
        known: Callable[[str], bool] | None = None,
        into: Callable[[], str] = lambda: DEFAULT_INTO,
    ) -> None:
        # one vocabulary, or one for each language
        self._vocabulary = vocabulary
        self._profiler = profiler
        self._chat = chat
        # the language model asked when a request names none
        self._model = model
        self._workers = workers
        # says whether a word is in a dictionary of the language
        self._known = known
        # The language the meanings of new words are written in: the one the
        # learner has what they read translated into at the time.
        self.into = into
        # The language the words are of, by its English name. It is whoever
        # sends the words that says which, and there is one for all of them.
        self.language = DEFAULT_LANGUAGE
        # One for each word being described, so that two forms of a new word
        # that come in together do not both have it described.
        self._describing: dict[tuple[str, str], threading.Lock] = {}
        # The vocabularies, with their languages, whose dictionary forms were
        # brought to the spelling they are now given, for those stored before.
        self._respelt: set[tuple[int, str]] = set()
        # whether each sentence was found to be mostly in its language, by
        # the language and the sentence, the latest found last
        self._in_language: dict[tuple[str, str], bool] = {}
        self._lock = threading.Lock()

    @property
    def vocabulary(self) -> Vocabulary:
        """The vocabulary of the language the words are of at present."""
        return self.vocabulary_of(self.language)

    def vocabulary_of(self, language: str) -> Vocabulary:
        vocabulary = (
            self._vocabulary.of(language)
            if isinstance(self._vocabulary, Vocabularies)
            else self._vocabulary
        )
        key = (id(vocabulary), language.strip().lower())
        with self._lock:
            if key not in self._respelt:
                for name in CATEGORIES:
                    vocabulary.respell(
                        name, partial(dictionary_form, category=name, language=language)
                    )
                self._respelt.add(key)
        return vocabulary

    def has_vocabulary(self, language: str) -> bool:
        """Whether anything was ever stored for `language`."""
        if isinstance(self._vocabulary, Vocabularies):
            return self._vocabulary.has(language)
        return True

    @property
    def categories(self) -> dict[str, Category]:
        return categories_of(self.language)

    def take(
        self,
        words: list[Word],
        model: Model = Model(),
        decision_model: Model = Model(),
        on_outcome: Callable[[Outcome], None] | None = None,
        language: str | None = None,
    ) -> tuple[list[Outcome], list[Profile]]:
        """Take each of `words` into the vocabulary, several at a time, and
        return what became of each, in the order they were given, with what
        the requests to the models used. `model` is the language model that
        judges and describes new words, and `decision_model` the one that
        sorts words into categories when there is none on this machine, and
        says of each sentence whether it is mostly in the language; the words
        of one that is not are skipped. A word given twice is worked on once.
        `on_outcome` is told what became of each word as soon as it is known,
        on the thread that worked on it.

        The words are taken in as words of `language`, or of the language
        there is at present if none is given, and stay words of it until
        all are done, whatever the language is changed to in the meantime."""
        used: list[Profile] = []
        # a copy of this that keeps to the one language
        bound = copy.copy(self)
        bound.language = language or self.language

        def judge(sentence: str) -> bool | str:
            try:
                return bound._is_in_language(sentence, decision_model, used)
            except ProfileError as error:
                return str(error)

        distinct = list({(word.word, word.sentence): word for word in words}.values())
        sentences = list(
            dict.fromkeys(word.sentence for word in distinct if word.sentence)
        )
        with ThreadPoolExecutor(max_workers=self._workers) as pool:
            judged = dict(zip(sentences, pool.map(judge, sentences)))

        def take(word: Word) -> Outcome:
            outcome = Outcome(word.word, word.sentence, "known")
            in_language = judged.get(word.sentence, True)
            if in_language is not True:
                outcome.status, outcome.reason = (
                    ("failed", in_language)
                    if isinstance(in_language, str)
                    else ("skipped", f"its sentence is not mostly in {bound.language}")
                )
                if on_outcome:
                    on_outcome(outcome)
                return outcome
            try:
                bound._take(word, outcome, model, decision_model, used)
            except ProfileError as error:
                # a model could not be asked, so there is nobody to ask again
                outcome.status, outcome.reason = "failed", str(error)
            except IntakeError as error:
                bound._fall_back(word, outcome, str(error), model, used)
            # A word in a sentence may be another word in another sentence,
            # and one that failed is to be tried again.
            if not outcome.sentence and outcome.status != "failed":
                bound.vocabulary.note_taken(outcome.word, outcome.status)
            if on_outcome:
                on_outcome(outcome)
            return outcome

        with ThreadPoolExecutor(max_workers=self._workers) as pool:
            outcomes = dict(
                zip(
                    ((word.word, word.sentence) for word in distinct),
                    pool.map(take, distinct),
                )
            )
        return [outcomes[(word.word, word.sentence)] for word in words], used

    def _take(
        self,
        word: Word,
        outcome: Outcome,
        model: Model,
        decision_model: Model,
        used: list[Profile],
    ) -> None:
        """Take one word in, and fill in what became of it."""
        # One found to be no word at all is not sorted into a category again.
        discarded = self.vocabulary.discarded(word.word)
        if discarded is not None:
            outcome.status, outcome.reason = "rejected", discarded
            return
        name: str | None = self._classify(word, decision_model, used)
        tried: set[str] = set()
        while name:
            if name in tried:
                raise IntakeError(f"it was found to be a {name} and then not to be")
            tried.add(name)
            outcome.category = name
            name = self._take_as(name, word, outcome, model, used)

    def _take_as(
        self,
        name: str,
        word: Word,
        outcome: Outcome,
        model: Model,
        used: list[Profile],
    ) -> str | None:
        """Take a word in as one of the category called `name`, and fill in
        what became of it. Should it turn out to be of another category
        instead, that one's name is returned, for the word to be taken in
        as."""
        category = self.categories.get(name)
        if category is None:
            outcome.status = "skipped"
            outcome.reason = NOT_STORED[name]
            return None
        outcome.entry = self.vocabulary.find(name, word.word, word.sentence)
        if outcome.entry:
            return None
        rejection = self.vocabulary.rejection(name, word.word)
        if rejection and rejection.belongs_to:
            return rejection.belongs_to
        if rejection:
            outcome.status, outcome.reason = "rejected", rejection.reason
            return None

        model = model.or_named(self._model)
        problem = model.problem()
        if problem:
            raise ProfileError(
                f"a new {name} needs a language model to judge it, and {problem}"
            )
        verdict, said = self._judge(word, category, model, used)
        if verdict == "elsewhere":
            # What a word is depends on the sentence it is in, so this is
            # remembered only for a word that came on its own.
            if not word.sentence:
                self.vocabulary.reject(name, word.word, "", belongs_to=said)
            return said
        if verdict == "reject":
            self.vocabulary.reject(name, word.word, said)
            self.vocabulary.discard(word.word, said)
            outcome.status, outcome.reason = "rejected", said
            return None
        self._store(said, verdict, category, word, outcome, model, used)
        return None

    def _store(
        self,
        lemma: str,
        verdict: str,
        category: Category,
        word: Word,
        outcome: Outcome,
        model: Model,
        used: list[Profile],
    ) -> None:
        """Put a word that was judged a form of `lemma`, or a new word with
        that dictionary form, where it belongs."""
        name = category.name
        lemma = dictionary_form(lemma, name, self.language)
        with self._describing_lock(name, lemma):
            stored = self.vocabulary.entry(name, lemma)
            # Another word taken in at the same time may have stored it
            # while this one was judged, with this word among its forms.
            found = self.vocabulary.find(name, word.word, word.sentence)
            if stored and found and found.id == stored.id:
                outcome.entry = found
                return
            if stored:
                # so that it is found the next time without asking
                outcome.entry = self.vocabulary.add_forms(stored.id, [Form(word.word)])
                outcome.status = "form"
                return
            if verdict == "form":
                raise IntakeError(
                    f"it was judged a form of {lemma}, which is not a stored {name}"
                )
            into = self.into()
            variants = self._describe(lemma, category, into, model, used)
            described = [fold(form.form) for each in variants for form in each.forms]
            # the spelling it was met in, if it was described without it
            met = [] if fold(word.word) in described else [Form(word.word)]
            outcome.entry, _ = self.vocabulary.save_variants(
                name, lemma, variants, into, met
            )
            outcome.status = "added"

    def _fall_back(
        self,
        word: Word,
        outcome: Outcome,
        problem: str,
        model: Model,
        used: list[Profile],
    ) -> None:
        """Have the language model look at a word that could not be placed,
        with what went wrong, and save the word if it says the word can be
        saved. What became of the word is filled in."""
        outcome.entry = None
        try:
            self._rescue(word, outcome, problem, model.or_named(self._model), used)
        except (IntakeError, ProfileError) as error:
            outcome.status = "failed"
            outcome.reason = f"{problem}; and asked again: {error}"

    def _rescue(
        self,
        word: Word,
        outcome: Outcome,
        problem: str,
        model: Model,
        used: list[Profile],
    ) -> None:
        given = {"word": word.word, "category": outcome.category, "problem": problem}
        if word.sentence:
            given["sentence"] = word.sentence
        rules = "\n".join(
            f"- {category.name}: {category.judging}"
            for category in self.categories.values()
        )
        reply = self._ask(
            PROMPTS(
                "intake.rescuing",
                capitals=PROMPTS("intake.capitals", language=self.language),
                language=self.language,
                categories=", ".join(CATEGORIES),
                rules=rules,
            ),
            given,
            "rescue",
            RESCUE_SCHEMA,
            model,
            used,
        )
        if not reply["savable"]:
            reason = reply["reason"].strip()
            if outcome.category in CATEGORIES:
                self.vocabulary.reject(outcome.category, word.word, reason)
            self.vocabulary.discard(word.word, reason)
            outcome.status, outcome.reason = "rejected", reason
            return
        category = self.categories.get(reply["category"])
        lemma = reply["lemma"].strip()
        if category is None or not 0 < len(lemma) <= MAX_WORD_LENGTH:
            raise IntakeError("no category or dictionary form was given for it")
        outcome.category = category.name
        self._store(lemma, "new", category, word, outcome, model, used)
        # kept, to show where the first answers about a word go wrong
        outcome.reason = f"saved when asked again, after: {problem}"

    def _is_in_language(self, sentence: str, model: Model, used: list[Profile]) -> bool:
        """Whether `sentence` is mostly in the language, as the decision
        model says. Raises ProfileError."""
        key = (self.language.strip().lower(), sentence)
        with self._lock:
            known = self._in_language.get(key)
        if known is not None:
            return known
        question = {
            IN_LANGUAGE: {
                "type": "noul",
                "instructions": PROMPTS("intake.language", language=self.language),
            }
        }
        profile = self._profiler.ask(
            {"sentence": sentence, "language": self.language}, question, model
        )
        used.append(profile)
        found = (profile.answers[IN_LANGUAGE].yes or 0.0) >= IN_LANGUAGE_AT_LEAST
        with self._lock:
            self._in_language[key] = found
            while len(self._in_language) > MAX_JUDGED_SENTENCES:
                del self._in_language[next(iter(self._in_language))]
        return found

    def _classify(self, word: Word, model: Model, used: list[Profile]) -> str:
        state = {"word": word.word}
        if word.sentence:
            state["sentence"] = word.sentence
        questions = category_questions(self.language)
        profile = self._profiler.ask(state, questions, model)
        used.append(profile)
        likely = {name: answer.yes or 0.0 for name, answer in profile.answers.items()}
        return max(self._possible(word), key=likely.__getitem__)

    def _possible(self, word: Word) -> list[str]:
        """What the word can be, going by what is known without a model."""
        ruled_out = set()
        if self._known and self._known(word.word):
            # it is in the dictionary, so it is a word
            ruled_out.add("other")
        capitals = language_of(self.language).nouns_have_capitals
        if capitals and not word.sentence and word.word.islower():
            # Nouns and names have a capital letter in this language. Someone
            # writing a sentence may leave it out, but a word on its own is
            # taken as it is written.
            ruled_out |= {"noun", "name"}
        return [name for name in (*CATEGORIES, *NOT_STORED) if name not in ruled_out]

    def _judge(
        self,
        word: Word,
        category: Category,
        model: Model,
        used: list[Profile],
    ) -> tuple[str, str]:
        """Whether the word is a "form" of a stored word, a "new" one, one
        that belongs "elsewhere" or one to "reject", with what was said
        about it: its dictionary form, the category it belongs in, or the
        reason, in that order."""
        candidates = self.vocabulary.closest(category.name, word.word, CANDIDATES)
        given: dict[str, Any] = {"word": word.word}
        if word.sentence:
            given["sentence"] = word.sentence
        given["candidates"] = [
            {"lemma": entry.lemma, "meanings": entry.translations_into(self.into())}
            for entry in candidates
        ]
        reply = self._ask(
            PROMPTS(
                "intake.judging",
                capitals=PROMPTS("intake.capitals", language=self.language),
                language=self.language,
                name=category.name,
                rules=category.judging,
                categories=", ".join(CATEGORIES),
            ),
            given,
            "verdict",
            VERDICT_SCHEMA,
            model,
            used,
        )
        verdict: str = reply["verdict"]
        if verdict == "elsewhere":
            if reply["category"] not in CATEGORIES:
                raise IntakeError("the model did not say which category it is of")
            return verdict, reply["category"]
        if verdict == "reject":
            return verdict, reply["reason"].strip()
        lemma = reply["lemma"].strip()
        if not 0 < len(lemma) <= MAX_WORD_LENGTH:
            raise IntakeError("the model gave no dictionary form")
        return verdict, lemma

    def translate(
        self,
        language: str,
        entry: Entry,
        into: str,
        model: Model,
        used: list[Profile],
    ) -> Entry:
        """Have the translations of each variant of a stored word of
        `language` written in `into`, from the word itself, what is known of
        each variant and its translations into another language, which keep
        the variants apart, and return the word with them."""
        source = entry.shown_in(DEFAULT_INTO)
        # Each variant by a name of its own, which the answer has to fill in:
        # given a list, a model takes the meanings of one variant for several.
        names = [f"variant_{number}" for number in range(1, len(entry.variants) + 1)]
        given = {
            "lemma": entry.lemma,
            "variants": {
                name: {
                    **({"details": variant.details} if variant.details else {}),
                    **(
                        {source: variant.translations[source]}
                        if source in variant.translations
                        else {}
                    ),
                }
                for name, variant in zip(names, entry.variants, strict=True)
            },
        }
        reply = self._ask(
            PROMPTS(
                "intake.translations", language=language, name=entry.category, into=into
            ),
            given,
            "translations",
            shape(**dict.fromkeys(names, MEANINGS)),
            model,
            used,
        )
        vocabulary = self.vocabulary_of(language)
        return vocabulary.set_translations(
            entry.id, into, [reply[name] for name in names]
        )

    def _describe(
        self,
        lemma: str,
        category: Category,
        into: str,
        model: Model,
        used: list[Profile],
    ) -> Description:
        reply = self._ask(
            PROMPTS(
                "intake.describing",
                language=self.language,
                name=category.name,
                rules=category.describing,
                into=into,
            ),
            {"lemma": lemma},
            category.name,
            category.schema,
            model,
            used,
        )
        variants = category.read(reply)
        if not variants:
            raise IntakeError(f"the model gave no variant of the {category.name}")
        # what is stored of a word is named only as the language's tables.json has it
        known = language_of(self.language).details()
        unknown = [
            name for each in variants for name in unknown_details(each.details, known)
        ]
        if unknown:
            raise IntakeError(
                f"the {category.name} is described by {', '.join(unknown)}"
            )
        return variants

    def _ask(
        self,
        instructions: str,
        given: dict[str, Any],
        schema_name: str,
        schema: Schema,
        model: Model,
        used: list[Profile],
    ) -> dict[str, Any]:
        """Ask the language model for an answer of the shape of `schema`."""
        body = {
            "model": model.name,
            "messages": [
                {"role": "system", "content": instructions},
                {"role": "user", "content": json.dumps(given, ensure_ascii=False)},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": schema_name, "strict": True, "schema": schema},
            },
            "temperature": 0,
            "usage": {"include": True},
        }
        try:
            response = self._chat(body, model)
        except ProfileError:
            # It may have been too slow or out of reach for once, so it is
            # asked a second time before the word is given up on.
            response = self._chat(body, model)
        used.append(read_usage(response, model.name))
        reply = read_reply(response)
        problem = mismatch(reply, schema)
        if problem:
            raise IntakeError(f"the model's answer is not as asked: {problem}")
        assert isinstance(reply, dict)
        return reply

    def _describing_lock(self, category: str, lemma: str) -> threading.Lock:
        with self._lock:
            return self._describing.setdefault((category, lemma), threading.Lock())


def read_reply(response: dict[str, Any]) -> object:
    """The JSON a chat response holds as its text. Raises IntakeError."""
    try:
        content = response["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        content = None
    if not isinstance(content, str):
        raise IntakeError("the model gave no answer")
    content = content.strip()
    if content.startswith("```"):
        # some models wrap what they write in a code block all the same
        content = content.strip("`").removeprefix("json")
    try:
        return json.loads(content)
    except ValueError:
        raise IntakeError("the model's answer is not JSON") from None


def read_usage(response: dict[str, Any], model: str) -> Profile:
    """What a chat request used, for whoever keeps count."""
    usage = response.get("usage")
    if not isinstance(usage, dict):
        usage = {}
    cost = usage.get("cost")
    request_id = response.get("id")
    answered_by = response.get("model")
    return Profile(
        {},
        cost=cost if isinstance(cost, (int, float)) else None,
        id=request_id if isinstance(request_id, str) else str(uuid.uuid4()),
        model=answered_by if isinstance(answered_by, str) else model,
        input_tokens=_count(usage.get("prompt_tokens")),
        output_tokens=_count(usage.get("completion_tokens")),
    )


def _count(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def mismatch(value: object, schema: Schema, where: str = "answer") -> str | None:
    """What keeps `value` from being of the shape of `schema`, or None if
    nothing does. It knows the few kinds of schema the categories use."""
    kind = schema["type"]
    expected = {"object": dict, "array": list, "boolean": bool, "string": str}[kind]
    if not isinstance(value, expected):
        return f"{where} is not {_KINDS[kind]}"
    # the parts of the value, each with its schema and where it is
    parts: list[tuple[object, Schema, str]] = []
    if isinstance(value, dict):
        for name, property_schema in schema["properties"].items():
            if name not in value:
                return f"{where} has no {name}"
            parts.append((value[name], property_schema, f"{where}.{name}"))
    elif isinstance(value, list):
        parts = [
            (item, schema["items"], f"{where}[{number}]")
            for number, item in enumerate(value)
        ]
    elif "enum" in schema and value not in schema["enum"]:
        return f"{where} is not one of {', '.join(schema['enum'])}"
    problems = (mismatch(*part) for part in parts)
    return next((problem for problem in problems if problem), None)


_KINDS = {
    "object": "an object",
    "array": "a list",
    "boolean": "true or false",
    "string": "text",
}


def read_words(value: object) -> list[Word]:
    """Check the words of a request that came in from outside: each is a
    word, or a word with the sentence it was used in. Raises ValueError."""
    if not isinstance(value, list) or not 0 < len(value) <= MAX_WORDS:
        raise ValueError(f"words must be a list of 1 to {MAX_WORDS}")
    words = []
    for item in value:
        sentence: object = ""
        if isinstance(item, dict):
            sentence = item.get("sentence", "")
            item = item.get("word")
        if not isinstance(item, str) or not isinstance(sentence, str):
            raise ValueError('every word must be text, or {"word", "sentence"}')
        word = item.strip()
        if not 0 < len(word) <= MAX_WORD_LENGTH:
            raise ValueError("a word is empty or too long")
        words.append(Word(word, sentence.strip()))
    return words
