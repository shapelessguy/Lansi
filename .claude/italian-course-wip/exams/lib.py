"""Helpers to write the Italian exams: parts with their sizes, and the file."""

import json
import sys
from pathlib import Path

ROOT = Path("/home/claudio/Documents/Lansi")
OUT = ROOT / "checker/languages/italian/evaluations"
FRACTIONS = (0.4, 0.55, 0.7, 0.85)


def sizes(instances, minutes, options):
    """What a part is at the first four sizes: fewer instances, questions,
    words or turns, and fewer minutes."""
    found = []
    for f in FRACTIONS:
        size = {}
        if instances > 1:
            size["instances"] = max(1, round(instances * f))
        elif options.get("questions", 1) > 1:
            size["questions"] = max(2, round(options["questions"] * f))
        elif "words" in options:
            size["words"] = max(20, round(options["words"] * f / 5) * 5)
        elif options.get("prompts", 1) > 1:
            size["prompts"] = max(1, round(options["prompts"] * f))
        size["minutes"] = max(1, round(minutes * f))
        found.append(size)
    return found


def part(title, exercise, options, instances, minutes, points, instructions,
         task, example, sized=True):
    made = {
        "title": title,
        "exercise": exercise,
        "options": options,
        "instances": instances,
        "minutes": minutes,
    }
    if sized:
        made["sizes"] = sizes(instances, minutes, options)
    made.update(
        points=points, instructions=instructions, task=task, example=example
    )
    return made


def reading(q=1, answers="choice", text=None):
    options = {"by": "reading"}
    if text:
        options["text"] = text
    options.update(answers=answers, questions=q)
    return options


def listening(q=1, answers="choice", plays="2", text=None):
    options = {"by": "listening"}
    if text:
        options["text"] = text
    options.update(answers=answers, questions=q, plays=plays)
    return options


def text(title, body, questions, shown=""):
    return {"title": title, "shown": shown, "text": body, "questions": [
        {"prompt": p, "options": o, "answer": a} for p, o, a in questions
    ]}


def module(id_, title, parts):
    return {"id": id_, "title": title, "weight": 25, "parts": parts}


def write(level, exam, passing, themes, modules):
    data = {
        "level": level,
        "exam": exam,
        "pass": {"total": passing},
        "themes": themes,
        "modules": modules,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{level}.json"
    path.write_text(json.dumps(data, indent=4, ensure_ascii=False) + "\n",
                    encoding="utf-8")
    check(path)


def check(path):
    sys.path.insert(0, str(ROOT / "checker"))
    from evaluating import SIZES, read_exam
    from exercising import exercises

    manifests = {m.id: m for m in exercises()}
    exam = read_exam(json.loads(path.read_text()), path.name, manifests)
    minutes = [exam.minutes_at(s) for s in SIZES]
    assert minutes == sorted(set(minutes)), minutes
    for p in exam.parts:
        ex = p.example
        if p.exercise == "comprehension":
            assert ex and ex["questions"], p.title
            for q in ex["questions"]:
                if p.options["answers"] in ("truefalse", "yesno"):
                    assert q["options"] == [] and q["answer"] in (0, 1), (p.title, q)
                else:
                    assert 0 <= q["answer"] < len(q["options"]), (p.title, q)
    print(path.name, exam.title, minutes,
          {m["id"]: sum(p.minutes for p in exam.parts if p.module == m["id"])
           for m in exam.modules})
