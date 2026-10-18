# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any
from unittest.mock import ANY

import exercising
import pytest
from exercising import (
    EXERCISES_DIRECTORY,
    Choosing,
    ExerciseError,
    Practice,
    Runner,
    exercises,
    ui_file,
)
from models import Model
from profiling import Profile
from storage import UserStore
from test_topics import KEY, FakeOpenRouter
from topics import DEFAULT_EMBEDDING_MODEL
from translating import TranslationError

EMBEDDING = Model(DEFAULT_EMBEDDING_MODEL, key=KEY)

LESSON = "trennbare-verben"

# A backend that says back what it was given, and asks the model when it is
# told to, written with the kit as every backend is.
ECHO = """\
import os
from kit import Step, grade, serve, written

def start(context, model):
    return Step(state={"done": 0}, show={"instances": context["instances"]})

def act(context, state, message, model):
    if message == "ask":
        return Step(state=state, show=model.ask([{"role": "user", "content": "hi"}]))
    if message == "see":
        return Step(state=state, show=model.look([{"role": "user", "content": "hi"}]))
    if message == "draw":
        return Step(state=state, show=model.draw("a cat", "4:3"))
    if message in ("look", "fetch"):
        url = "data:image/jpeg;base64,AAAA" if message == "look" else "http://x/a.png"
        content = [
            {"type": "text", "text": "what is it?"},
            {"type": "image_url", "image_url": {"url": url}},
        ]
        return Step(state=state, show=model.ask([{"role": "user", "content": content}]))
    if message == "key":
        return Step(state=state, show=sorted(os.environ))
    if message == "crash":
        raise RuntimeError("something broke")
    if message == "hang":
        import time
        time.sleep(30)
    if message == "print":
        print("not a reply")
    if message == "mark":
        state["scored"] = True
        return Step(state=state, show=None)
    if message == "score":
        return Step(state=state, show=None, scores={"tanzen": 3})
    if message == "context":
        return Step(state=state, show={"minutes": context["minutes"], "exam": context["exam"]})
    if message == "write":
        said = written(["Ich stehe auf."], ["Wann stehst du auf?"])
        return Step(state=state, show=None, written=said)
    state["done"] += 1
    return Step(state=state, show=state["done"], graded=[grade("right", message)])

def finish(context, state, model):
    scores = {"lesen": 100 * state["done"] / 3} if state.get("scored") else None
    return Step(results={"done": state["done"]}, scores=scores)

serve(start, act, finish)
"""


@pytest.fixture
def directory(tmp_path: Path) -> Path:
    """A directory of exercises with the kit and one exercise, `echo`."""
    exercises_directory = tmp_path / "exercises"
    (exercises_directory / "echo" / "ui").mkdir(parents=True)
    shutil.copy(EXERCISES_DIRECTORY / "kit.py", exercises_directory)
    shutil.copy(EXERCISES_DIRECTORY / "kit.js", exercises_directory)
    echo = exercises_directory / "echo"
    (echo / "manifest.json").write_text('{"title": "Echo"}', encoding="utf-8")
    (echo / "backend.py").write_text(ECHO, encoding="utf-8")
    (echo / "ui" / "index.js").write_text(
        "export function mount() {}", encoding="utf-8"
    )
    return exercises_directory


def answering(text: str = "hello") -> Any:
    def ask(messages: list[dict[str, str]]) -> tuple[str, Profile]:
        return text, Profile({}, id="gen-1", model="some/model", input_tokens=3)

    return ask


# what a model replies when it is asked for the log of an exercise
LOG_REPLY = (
    '{"summary": ["1 of 3 done.", "Separable verb split correctly."],'
    ' "worked": [{"text": "Ich stehe auf.", "why": "prefix at the end"}],'
    ' "failed": []}'
)


def failing(messages: list[dict[str, str]]) -> tuple[str, Profile]:
    raise TranslationError("an OpenRouter key is needed")


CONTEXT = {"instances": 2}


def test_a_step_of_a_backend_is_its_reply(directory: Path) -> None:
    reply, used = Runner(directory).run(
        "echo",
        {"op": "start", "context": CONTEXT, "state": None, "message": None},
        answering(),
    )

    assert reply["state"] == {"done": 0}
    assert reply["show"] == {"instances": 2}
    assert (reply["graded"], used) == ([], [])


def test_a_backend_asks_the_model_through_the_server(directory: Path) -> None:
    request = {"op": "act", "context": CONTEXT, "state": {}, "message": "ask"}

    reply, used = Runner(directory).run("echo", request, answering("Grüß dich"))

    assert reply["show"] == "Grüß dich"
    assert [profile.id for profile in used] == ["gen-1"]


def test_a_backend_has_pictures_drawn_through_the_server(directory: Path) -> None:
    drawn: list[tuple[str, str]] = []

    def draw(prompt: str, aspect_ratio: str) -> tuple[str, Profile]:
        drawn.append((prompt, aspect_ratio))
        return "data:image/jpeg;base64,BBBB", Profile({}, id="img-1", model="m")

    request = {"op": "act", "context": CONTEXT, "state": {}, "message": "draw"}

    reply, used = Runner(directory).run("echo", request, answering(), draw)

    assert reply["show"] == "data:image/jpeg;base64,BBBB"
    assert drawn == [("a cat", "4:3")]
    assert [profile.id for profile in used] == ["img-1"]


def test_a_backend_looks_with_the_model_that_sees_or_else_the_chat_model(
    directory: Path,
) -> None:
    request = {"op": "act", "context": CONTEXT, "state": {}, "message": "see"}

    seen, _ = Runner(directory).run(
        "echo", request, answering("chat"), look=answering("vision")
    )
    asked, _ = Runner(directory).run("echo", request, answering("chat"))

    assert (seen["show"], asked["show"]) == ("vision", "chat")


def test_a_backend_cannot_have_pictures_drawn_without_an_image_model(
    directory: Path,
) -> None:
    request = {"op": "act", "context": CONTEXT, "state": {}, "message": "draw"}

    with pytest.raises(ExerciseError, match="no image model"):
        Runner(directory).run("echo", request, answering())


def test_a_backend_shows_the_model_pictures_it_has_but_no_addresses(
    directory: Path,
) -> None:
    asked: list[Any] = []

    def ask(messages: list[dict[str, Any]]) -> tuple[str, Profile]:
        asked.append(messages)
        return "a cat", Profile({}, id="gen-1", model="m")

    look = {"op": "act", "context": CONTEXT, "state": {}, "message": "look"}
    fetch = {**look, "message": "fetch"}

    reply, _ = Runner(directory).run("echo", look, ask)

    assert reply["show"] == "a cat"
    assert asked[0][0]["content"][1]["image_url"]["url"].startswith("data:image/")
    with pytest.raises(ExerciseError, match="data URL"):
        Runner(directory).run("echo", fetch, ask)
    assert len(asked) == 1


def test_a_backend_that_cannot_have_the_model_asked_says_why(directory: Path) -> None:
    request = {"op": "act", "context": CONTEXT, "state": {}, "message": "ask"}

    with pytest.raises(ExerciseError, match="an OpenRouter key is needed"):
        Runner(directory).run("echo", request, failing)


def test_a_backend_is_given_no_key(
    directory: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-secret")
    request = {"op": "act", "context": CONTEXT, "state": {}, "message": "key"}

    reply, _ = Runner(directory).run("echo", request, answering())

    assert "OPENROUTER_API_KEY" not in reply["show"]
    assert "sk-secret" not in str(reply)
    assert os.environ["OPENROUTER_API_KEY"] == "sk-secret"


def test_what_a_backend_prints_is_not_taken_for_its_reply(directory: Path) -> None:
    request = {
        "op": "act",
        "context": CONTEXT,
        "state": {"done": 0},
        "message": "print",
    }

    reply, _ = Runner(directory).run("echo", request, answering())

    assert reply["show"] == 1


def test_a_backend_that_breaks_says_how_it_did(directory: Path) -> None:
    request = {"op": "act", "context": CONTEXT, "state": {}, "message": "crash"}

    with pytest.raises(ExerciseError, match="something broke"):
        Runner(directory).run("echo", request, answering())


def test_a_backend_that_takes_too_long_is_stopped(directory: Path) -> None:
    request = {"op": "act", "context": CONTEXT, "state": {}, "message": "hang"}

    with pytest.raises(ExerciseError, match="took more than"):
        Runner(directory, timeout=2).run("echo", request, answering())


def test_there_is_no_backend_but_those_of_the_exercises(directory: Path) -> None:
    request = {"op": "start", "context": CONTEXT, "state": None, "message": None}

    with pytest.raises(ExerciseError, match="no exercise"):
        Runner(directory).run("../echo", request, answering())


def test_the_exercises_that_are_kept_are_listed() -> None:
    found = {manifest.id for manifest in exercises()}

    assert {"cloze", "picture", "translation"} <= found


def test_the_files_of_an_interface_are_given_and_nothing_else(directory: Path) -> None:
    assert ui_file("echo/ui/index.js", directory) == (
        b"export function mount() {}",
        "text/javascript; charset=utf-8",
    )
    assert ui_file("kit.js", directory) is not None
    assert ui_file("kit.py", directory) is None
    assert ui_file("echo/backend.py", directory) is None
    assert ui_file("echo/manifest.json", directory) is None
    assert ui_file("echo/ui/../backend.py", directory) is None
    assert ui_file("echo/ui/../../kit.py", directory) is None


@pytest.fixture
def practice(directory: Path, tmp_path: Path) -> Practice:
    return Practice(UserStore(tmp_path / "user"), directory=directory)


LEARNER = {"into": "English", "level": "A1"}


def test_the_grades_of_a_step_are_kept_as_soon_as_it_is_made(
    practice: Practice,
) -> None:
    session, _ = practice.start_session("German", LESSON, [], {"echo": 3})

    practice.step(session["id"], "echo", "start", None, LEARNER, answering())
    shown, _ = practice.step(
        session["id"], "echo", "act", "Ich stehe auf.", LEARNER, answering()
    )

    assert shown == 1
    kept = practice._store.grades(session["id"])
    assert kept == [
        {
            "session": session["id"],
            "exercise": "echo",
            "result": "right",
            "task": "",
            "answer": "Ich stehe auf.",
            "correction": "",
            "note": "",
        }
    ]


def test_an_exercise_is_told_the_lesson_with_its_points(
    practice: Practice, directory: Path
) -> None:
    told: list[dict[str, Any]] = []

    class Recording(Runner):
        def run(
            self,
            exercise: str,
            request: dict[str, Any],
            ask: Any,
            draw: Any = None,
            look: Any = None,
        ) -> Any:
            told.append(request["context"])
            return {"state": {}, "show": None, "graded": []}, []

    practice._runner = Recording(directory)
    session, _ = practice.start_session("German", LESSON, [], {"echo": 4})

    practice.step(session["id"], "echo", "start", None, LEARNER, answering())

    (context,) = told
    assert (context["language"], context["into"], context["instances"]) == (
        "German",
        "English",
        4,
    )
    assert context["lesson"]["id"] == LESSON
    assert context["lesson"]["points"][0]["statement"]


def test_what_the_learner_and_the_models_wrote_in_a_step_is_kept(
    practice: Practice,
) -> None:
    session, _ = practice.start_session("German", LESSON, [], {"echo": 3})
    practice.step(session["id"], "echo", "start", None, LEARNER, answering())

    practice.step(session["id"], "echo", "act", "write", LEARNER, answering())

    assert practice._store.written(session["id"], "echo") == {
        "user": ["Ich stehe auf."],
        "assistant": ["Wann stehst du auf?"],
    }


def with_options(directory: Path) -> None:
    """Gives the exercise `echo` an option of what to do after a story."""
    (directory / "echo" / "manifest.json").write_text(
        '{"title": "Echo", "options": {"then": {"label": "Then", "choices":'
        ' {"questions": "Answer questions", "retell": "Retell it"}},'
        ' "questions": {"label": "Questions", "min": 1, "max": 8, "default": 3},'
        ' "broken": {"choices": []},'
        ' "outside": {"min": 1, "max": 3, "default": 5},'
        ' "half": {"min": 1, "max": 3, "default": 1.5}}}',
        encoding="utf-8",
    )


def test_the_options_of_an_exercise_are_listed_without_those_that_are_not_options(
    directory: Path,
) -> None:
    with_options(directory)

    (echo,) = exercises(directory)

    assert echo.options == {
        "then": {
            "label": "Then",
            "choices": {"questions": "Answer questions", "retell": "Retell it"},
        },
        "questions": {"label": "Questions", "min": 1, "max": 8, "default": 3},
    }


def test_an_exercise_is_told_the_options_it_was_chosen_with_or_else_the_first(
    practice: Practice, directory: Path
) -> None:
    with_options(directory)
    told: list[dict[str, Any]] = []

    class Recording(Runner):
        def run(self, exercise: str, request: dict[str, Any], *rest: Any) -> Any:
            told.append(request["context"])
            return {"state": {}, "show": None, "graded": []}, []

    practice._runner = Recording(directory)
    chosen, _ = practice.start_session(
        "German",
        LESSON,
        [],
        {"echo": 1},
        options={"echo": {"then": "retell", "questions": 5}},
    )
    practice.step(chosen["id"], "echo", "start", None, LEARNER, answering())
    left, _ = practice.start_session("German", LESSON, [], {"echo": 1})
    practice.step(left["id"], "echo", "start", None, LEARNER, answering())

    assert [context["options"] for context in told] == [
        {"then": "retell", "questions": 5},
        {"then": "questions", "questions": 3},
    ]


def test_a_session_with_an_option_that_is_no_choice_is_not_started(
    practice: Practice, directory: Path
) -> None:
    with_options(directory)

    with pytest.raises(ValueError, match="not a choice"):
        practice.start_session(
            "German", LESSON, [], {"echo": 1}, options={"echo": {"then": "sing"}}
        )
    assert practice._store.sessions() == []


@pytest.mark.parametrize("questions", [0, 9, 2.5, "3", True])
def test_a_session_with_a_number_out_of_its_option_is_not_started(
    practice: Practice, directory: Path, questions: Any
) -> None:
    with_options(directory)

    with pytest.raises(ValueError, match="whole number from 1 to 8"):
        practice.start_session(
            "German",
            LESSON,
            [],
            {"echo": 1},
            options={"echo": {"questions": questions}},
        )
    assert practice._store.sessions() == []


def test_an_exercise_that_is_opened_again_is_shown_what_it_showed(
    practice: Practice,
) -> None:
    session, _ = practice.start_session("German", LESSON, [], {"echo": 3})
    practice.step(session["id"], "echo", "start", None, LEARNER, answering())
    practice.step(session["id"], "echo", "act", "Eins.", LEARNER, answering())

    shown, used = practice.step(
        session["id"], "echo", "start", None, LEARNER, answering()
    )

    assert (shown, used) == (1, [])


def test_a_finished_exercise_keeps_its_results_and_takes_no_more_steps(
    practice: Practice,
) -> None:
    session, _ = practice.start_session("German", LESSON, [], {"echo": 3})
    practice.step(session["id"], "echo", "start", None, LEARNER, answering())
    practice.step(session["id"], "echo", "act", "Eins.", LEARNER, answering())

    practice.step(session["id"], "echo", "finish", None, LEARNER, answering(LOG_REPLY))

    assert practice._store.results(session["id"], "echo") == {"done": 1}
    progress = practice._store.session(session["id"])
    assert progress and progress["progress"]["echo"] == {
        "status": "finished",
        "answered": 1,
        "started_at": ANY,
        "scores": None,
        "results": {"right": 1, "partial": 0, "wrong": 0},
    }
    with pytest.raises(ValueError, match="finished"):
        practice.step(session["id"], "echo", "act", "Zwei.", LEARNER, answering())


def test_the_log_of_an_exercise_is_written_from_its_grades_after_it_finishes(
    directory: Path, tmp_path: Path
) -> None:
    jobs: list[tuple[str, Any]] = []
    practice = Practice(
        UserStore(tmp_path / "user"),
        directory=directory,
        later=lambda title, job: jobs.append((title, job)),
    )
    asked: list[list[dict[str, Any]]] = []

    def ask(messages: list[dict[str, Any]]) -> tuple[str, Profile]:
        asked.append(messages)
        return LOG_REPLY, Profile({}, id="gen-log", model="some/model")

    session, _ = practice.start_session("German", LESSON, [], {"echo": 3})
    practice.step(session["id"], "echo", "start", None, LEARNER, answering())
    practice.step(session["id"], "echo", "act", "Ich stehe auf.", LEARNER, answering())

    _, finishing = practice.step(session["id"], "echo", "finish", None, LEARNER, ask)
    # the step is over before the log is written
    assert (finishing, asked, practice._store.logs(session["id"])) == ([], [], {})
    title, job = jobs[0]
    used = job()

    prompt = asked[0][0]["content"]
    assert title == "Echo"
    assert "Echo" in prompt and "Instances to do: 3" in prompt
    assert "Written by the learner:\n    Ich stehe auf." in prompt
    assert [profile.id for profile in used] == ["gen-log"]
    assert practice._store.logs(session["id"]) == {
        "echo": "1 of 3 done.\nSeparable verb split correctly.\nWorked:\n"
        '- "Ich stehe auf.": prefix at the end'
    }


def test_an_exercise_in_which_nothing_was_done_gets_no_log(
    practice: Practice,
) -> None:
    session, _ = practice.start_session("German", LESSON, [], {"echo": 3})
    practice.step(session["id"], "echo", "start", None, LEARNER, answering())

    _, used = practice.step(session["id"], "echo", "finish", None, LEARNER, failing)

    assert (used, practice._store.logs(session["id"])) == ([], {})


def test_an_exercise_whose_log_cannot_be_written_is_finished_all_the_same(
    practice: Practice,
) -> None:
    session, _ = practice.start_session("German", LESSON, [], {"echo": 3})
    practice.step(session["id"], "echo", "start", None, LEARNER, answering())
    practice.step(session["id"], "echo", "act", "Eins.", LEARNER, answering())

    with pytest.raises(ExerciseError, match="log of Echo could not be written"):
        practice.step(session["id"], "echo", "finish", None, LEARNER, failing)

    found = practice._store.session(session["id"])
    assert found and found["progress"]["echo"]["status"] == "finished"
    assert practice._store.logs(session["id"]) == {}


def test_ending_a_session_finishes_the_exercises_that_were_started(
    practice: Practice, directory: Path
) -> None:
    shutil.copytree(directory / "echo", directory / "other")
    session, _ = practice.start_session("German", LESSON, [], {"echo": 3, "other": 2})
    practice.step(session["id"], "echo", "start", None, LEARNER, answering())

    ended, _ = practice.end_session(session["id"], "finished", LEARNER, answering())

    assert ended["status"] == "finished"
    assert ended["exercises"] == {"echo": 3, "other": 2}
    assert ended["progress"]["echo"]["status"] == "finished"
    assert ended["progress"]["other"]["status"] == "pending"
    with pytest.raises(ValueError, match="ended"):
        practice.step(session["id"], "other", "start", None, LEARNER, answering())


def theory_beside(directory: Path) -> None:
    """Adds an exercise of theory, `notes`, beside `echo`."""
    shutil.copytree(directory / "echo", directory / "notes")
    (directory / "notes" / "manifest.json").write_text(
        '{"title": "Aaa notes", "theory": true}', encoding="utf-8"
    )
    (directory / "echo" / "manifest.json").write_text(
        '{"title": "Aaa echo"}', encoding="utf-8"
    )


def test_an_exercise_of_theory_is_listed_before_the_others(directory: Path) -> None:
    theory_beside(directory)

    found = [(manifest.id, manifest.theory) for manifest in exercises(directory)]

    assert found == [("notes", True), ("echo", False)]


def test_an_exercise_of_theory_comes_first_in_a_session_without_instances(
    practice: Practice, directory: Path
) -> None:
    theory_beside(directory)

    session, _ = practice.start_session(
        "German", LESSON, [], {"echo": 3, "notes": 5000}
    )

    assert list(session["exercises"].items()) == [("notes", 0), ("echo", 3)]


def test_a_session_of_theory_alone_is_about_no_topic_and_given_no_words(
    practice: Practice, directory: Path
) -> None:
    theory_beside(directory)
    topic = practice._store.add_topic("sport", "Sport", "")
    choosing = Choosing(vocabulary="set", words=["laufen"], topic_words=False)

    session, _ = practice.start_session(
        "German", LESSON, [topic["id"]], {"notes": 1}, choosing
    )

    assert (session["topics"], session["words"]) == ([], None)


def test_starting_a_session_abandons_the_one_that_was_running(
    practice: Practice,
) -> None:
    first, _ = practice.start_session("German", LESSON, [], {"echo": 3})

    practice.start_session("German", LESSON, [], {"echo": 1})

    kept = practice._store.session(first["id"])
    assert kept and kept["status"] == "abandoned"


def test_logs_that_are_not_logs_are_refused_and_none_is_kept(
    practice: Practice, directory: Path
) -> None:
    class Wrong(Runner):
        def run(
            self,
            exercise: str,
            request: dict[str, Any],
            ask: Any,
            draw: Any = None,
            look: Any = None,
        ) -> Any:
            logs = [{"result": "right", "answer": "a"}, {"result": "great"}]
            return {"state": {}, "show": None, "graded": logs}, []

    practice._runner = Wrong(directory)
    session, _ = practice.start_session("German", LESSON, [], {"echo": 3})

    with pytest.raises(ExerciseError, match="result"):
        practice.step(session["id"], "echo", "start", None, LEARNER, answering())
    assert practice._store.grades(session["id"]) == []


@pytest.mark.parametrize(
    "lesson, chosen, wrong",
    [
        ("no-such-lesson", {"echo": 3}, "no lesson"),
        (LESSON, {}, "choose an exercise"),
        (LESSON, {"nothing": 3}, "no exercise nothing"),
        (LESSON, {"echo": 0}, "1 to"),
        (LESSON, {"echo": 1000}, "1 to"),
    ],
)
def test_a_session_that_cannot_be_had_is_not_started(
    practice: Practice, lesson: str, chosen: dict[str, int], wrong: str
) -> None:
    with pytest.raises(ValueError, match=wrong):
        practice.start_session("German", lesson, [], chosen)
    assert practice._store.sessions() == []


def test_a_session_without_a_lesson_reviews_the_lessons_practised_last_in_order(
    practice: Practice, directory: Path
) -> None:
    taught = [lesson.id for lesson in practice._grammar.lessons("German")]
    # the first twelve lessons, practised from the last to the first
    for lesson in reversed(taught[:12]):
        practice.start_session("German", lesson, [], {"echo": 1})
    told = recording(practice, directory)

    session, _ = practice.start_session("German", "", [], {"echo": 2})
    practice.step(session["id"], "echo", "start", None, LEARNER, answering())

    assert session["lesson"] == ""
    assert session["lessons"] == taught[:10]
    assert told[0]["lesson"]["title"].startswith("Review of ")
    assert {point["role"] for point in told[0]["lesson"]["points"]} == {"review"}
    # a review is not a lesson practised, so the next one goes over the same
    again, _ = practice.start_session("German", "", [], {"echo": 1})
    assert again["lessons"] == taught[:10]


def test_a_session_without_a_lesson_has_no_theory_and_needs_a_lesson_practised(
    practice: Practice, directory: Path
) -> None:
    theory_beside(directory)

    with pytest.raises(ValueError, match="practise one first"):
        practice.start_session("German", "", [], {"echo": 1})
    practice.start_session("German", LESSON, [], {"echo": 1})
    with pytest.raises(ValueError, match="theory"):
        practice.start_session("German", "", [], {"notes": 1, "echo": 1})


def recording(practice: Practice, directory: Path) -> list[dict[str, Any]]:
    """Has `practice` run its exercises as one that keeps the context it is
    given, and returns where those are kept."""
    told: list[dict[str, Any]] = []

    class Recording(Runner):
        def run(
            self,
            exercise: str,
            request: dict[str, Any],
            ask: Any,
            draw: Any = None,
            look: Any = None,
        ) -> Any:
            told.append(request["context"])
            return {"state": {}, "show": None, "graded": []}, []

    practice._runner = Recording(directory)
    return told


@pytest.fixture
def with_topics(directory: Path, tmp_path: Path) -> Practice:
    """A practice about two topics, with a vocabulary the fake embedding
    model knows, which draws the last of the topics when it draws one."""
    store = UserStore(tmp_path / "user")
    store.add_topic("doctor", "Beim Arzt", "symptoms")
    store.add_topic("football", "Fußball", "")
    return Practice(
        store,
        directory=directory,
        lemmas_of=lambda language: ["gehen", "das Tor", "krank", "der Arzt"],
        draw=lambda topics: topics[-1],
        send=FakeOpenRouter(),
    )


def test_one_of_the_topics_is_drawn_for_the_session_unless_they_are_mixed(
    with_topics: Practice, directory: Path
) -> None:
    told = recording(with_topics, directory)
    # one session runs at a time, so each is started when the one before is done
    drawn, _ = with_topics.start_session(
        "German", LESSON, ["doctor", "football"], {"echo": 1}
    )
    with_topics.step(drawn["id"], "echo", "start", None, LEARNER, answering())
    mixed, _ = with_topics.start_session(
        "German", LESSON, ["doctor", "football"], {"echo": 1}, Choosing(mix_topics=True)
    )
    with_topics.step(mixed["id"], "echo", "start", None, LEARNER, answering())

    assert (drawn["topics"], drawn["mix_topics"]) == (["football"], False)
    assert (mixed["topics"], mixed["mix_topics"]) == (["doctor", "football"], True)
    assert told[0]["topics"] == [{"title": "Fußball", "description": ""}]
    assert [topic["title"] for topic in told[1]["topics"]] == ["Beim Arzt", "Fußball"]
    assert told[1]["mix_topics"] is True


def test_a_session_about_a_topic_there_is_not_is_not_started(
    with_topics: Practice,
) -> None:
    with pytest.raises(ValueError, match="no such topic"):
        with_topics.start_session("German", LESSON, ["gone"], {"echo": 1})


def test_the_words_nearest_the_topic_come_first_and_alone_when_there_are_enough(
    with_topics: Practice, directory: Path
) -> None:
    told = recording(with_topics, directory)
    others = [f"Wort {number}" for number in range(30)]
    choosing = Choosing(
        vocabulary="set",
        words=["gehen", *others, "krank", "der Arzt"],
        embedding_model=EMBEDDING,
    )

    session, used = with_topics.start_session(
        "German", LESSON, ["doctor"], {"echo": 1}, choosing
    )
    with_topics.step(session["id"], "echo", "start", None, LEARNER, answering())

    assert session["words"]["mode"] == "only"
    assert session["words"]["lemmas"][:3] == ["der Arzt", "krank", "gehen"]
    assert len(session["words"]["lemmas"]) == 33
    assert told[0]["words"] == session["words"]
    # the words and the topic were embedded when the session started
    assert used


def test_the_words_are_preferred_when_there_are_too_few_to_use_them_alone(
    with_topics: Practice,
) -> None:
    session, _ = with_topics.start_session(
        "German",
        LESSON,
        ["doctor"],
        {"echo": 1},
        Choosing(vocabulary="all", embedding_model=EMBEDDING),
    )

    assert session["words"] == {
        "mode": "prefer",
        "lemmas": ["der Arzt", "krank", "gehen", "das Tor"],
    }


def test_without_topics_the_first_words_of_the_vocabulary_are_preferred(
    with_topics: Practice,
) -> None:
    session, used = with_topics.start_session(
        "German", LESSON, [], {"echo": 1}, Choosing(vocabulary="all")
    )

    assert session["words"] == {
        "mode": "prefer",
        "lemmas": ["gehen", "das Tor", "krank", "der Arzt"],
    }
    assert used == []


def test_without_a_vocabulary_the_exercises_are_given_no_words(
    with_topics: Practice,
) -> None:
    session, _ = with_topics.start_session("German", LESSON, ["doctor"], {"echo": 1})

    assert session["words"] is None


def test_a_session_waits_for_a_vocabulary_that_is_mostly_not_embedded(
    with_topics: Practice, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(exercising, "MAX_EMBEDDED_AT_START", 2)
    choosing = Choosing(vocabulary="all", embedding_model=EMBEDDING)

    with pytest.raises(ValueError, match="5 words of the vocabulary are not embedded"):
        with_topics.start_session("German", LESSON, ["doctor"], {"echo": 1}, choosing)
    assert with_topics.vocabulary_to_embed("German", EMBEDDING.name) == [
        "gehen",
        "das Tor",
        "krank",
        "der Arzt",
    ]


def test_an_exercise_is_told_what_it_was_answered_with_in_the_sessions_before(
    practice: Practice, directory: Path
) -> None:
    told: list[dict[str, Any]] = []

    class Recording(Runner):
        def run(
            self,
            exercise: str,
            request: dict[str, Any],
            ask: Any,
            draw: Any = None,
            look: Any = None,
        ) -> Any:
            told.append(request["context"])
            return {"state": {}, "show": None, "graded": []}, []

    first, _ = practice.start_session("German", LESSON, [], {"echo": 2})
    practice._store.add_grades(
        first["id"],
        "echo",
        [
            {"result": "right", "answer": "der Tisch"},
            {"result": "wrong", "answer": "der Preis", "correction": "der Pokal"},
        ],
    )
    practice._runner = Recording(directory)

    second, _ = practice.start_session("German", LESSON, [], {"echo": 2})
    practice.step(second["id"], "echo", "start", None, LEARNER, answering())

    (context,) = told
    assert context["guidance"].endswith("\nder Tisch; der Pokal")
    assert "Do not use them again" in context["guidance"]
    assert second["guidance"] == {"echo": context["guidance"]}
    assert first["guidance"] == {"echo": ""}


def test_what_an_exercise_is_told_of_the_sessions_before_is_kept_short(
    practice: Practice, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(exercising, "MAX_GUIDANCE", 30)
    first, _ = practice.start_session("German", LESSON, [], {"echo": 1})
    practice._store.add_grades(
        first["id"],
        "echo",
        [{"result": "right", "answer": f"Satz Nummer {number}"} for number in range(9)],
    )

    told = practice.guidance("echo")

    assert told.endswith("\nSatz Nummer 0; Satz Nummer 1")


def test_an_exercise_finished_keeps_the_scores_it_reported(practice: Practice) -> None:
    session, _ = practice.start_session("German", LESSON, [], {"echo": 3})
    practice.step(session["id"], "echo", "start", None, LEARNER, answering())
    practice.step(session["id"], "echo", "act", "mark", LEARNER, answering())
    practice.step(session["id"], "echo", "act", "Eins.", LEARNER, answering())

    practice.step(session["id"], "echo", "finish", None, LEARNER, answering(LOG_REPLY))

    found = practice._store.session(session["id"])  # noqa: SLF001
    assert found and found["progress"]["echo"]["scores"] == {"lesen": 33.3}
    (log,) = practice._store.all_logs()  # noqa: SLF001
    assert log["content"].endswith("Scores: lesen 33.3")


def test_an_exercise_cannot_score_what_there_is_no_score_of(practice: Practice) -> None:
    session, _ = practice.start_session("German", LESSON, [], {"echo": 3})
    practice.step(session["id"], "echo", "start", None, LEARNER, answering())

    with pytest.raises(ExerciseError, match="cannot score tanzen"):
        practice.step(session["id"], "echo", "act", "score", LEARNER, answering())


def test_an_exercise_is_told_its_time_limit_and_takes_nothing_once_it_is_up(
    directory: Path, tmp_path: Path
) -> None:
    now = [1000.0]
    practice = Practice(
        UserStore(tmp_path / "user", now=lambda: now[0]),
        directory=directory,
        now=lambda: now[0],
    )
    session, _ = practice.start_session(
        "German", LESSON, [], {"echo": 3}, minutes={"echo": 2}
    )
    practice.step(session["id"], "echo", "start", None, LEARNER, answering())
    shown, _ = practice.step(
        session["id"], "echo", "act", "context", LEARNER, answering()
    )
    now[0] += 2 * 60 + 29

    practice.step(session["id"], "echo", "act", "Eins.", LEARNER, answering())
    now[0] += 2

    assert shown == {"minutes": 2, "exam": ""}
    with pytest.raises(ValueError, match="time for this exercise is up"):
        practice.step(session["id"], "echo", "act", "Zwei.", LEARNER, answering())
    # what was done in it is kept all the same
    practice.step(session["id"], "echo", "finish", None, LEARNER, answering(LOG_REPLY))


def test_a_time_limit_is_whole_minutes_up_to_four_hours(practice: Practice) -> None:
    with pytest.raises(ValueError, match="0 to 240 minutes"):
        practice.start_session("German", LESSON, [], {"echo": 3}, minutes={"echo": 241})


def test_a_session_of_an_exam_tells_its_exercises_the_exam_and_is_kept_from_practice(
    practice: Practice,
) -> None:
    session, _ = practice.start_session(
        "German",
        "",
        [],
        {"echo": 3},
        exam="Exam: Goethe A1, Lesen, Teil 1.",
        reviewing=[],
    )
    practice.step(session["id"], "echo", "start", None, LEARNER, answering())

    shown, _ = practice.step(
        session["id"], "echo", "act", "context", LEARNER, answering()
    )

    assert shown == {"minutes": 0, "exam": "Exam: Goethe A1, Lesen, Teil 1."}
    assert session["kind"] == "evaluation"
    assert practice._store.sessions() == []  # noqa: SLF001
