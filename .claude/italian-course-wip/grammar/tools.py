"""Write the points and lessons of Italian in the layout of the German ones."""

import json
import re
import sys
from pathlib import Path

ROOT = Path("/home/claudio/Documents/Lansi/checker/languages")
GRAMMAR = ROOT / "italian" / "grammar"
LESSONS = GRAMMAR / "lessons"
MARKS = set("vpsiecxh")
ROLES = ("new", "review", "preview")
# a box with no title is given the Italian one
TITLES = {"merke": "Ricorda", "tipp": "Consiglio", "achtung": "Attenzione",
          "beispiel": "Esempi"}
FIELDS = ("id", "level", "title", "statement", "when", "confused_with", "requires")


def format_points(points):
    blocks = []
    for point in points:
        lines = [
            f"        {json.dumps(name)}: {json.dumps(point[name], ensure_ascii=False)}"
            for name in FIELDS
        ]
        blocks.append("    {\n" + ",\n".join(lines) + "\n    }")
    return "[\n" + ",\n".join(blocks) + "\n]\n"


def format_lesson(lesson):
    points = ",\n".join(
        f'        {{ "id": {json.dumps(p["id"])}, "role": {json.dumps(p["role"])} }}'
        for p in lesson["points"]
    )
    return (
        "{\n"
        f'    "id": {json.dumps(lesson["id"])},\n'
        f'    "level": {json.dumps(lesson["level"])},\n'
        f'    "title": {json.dumps(lesson["title"], ensure_ascii=False)},\n'
        f'    "points": [\n{points}\n    ],\n'
        f'    "more_info": {json.dumps(lesson["more_info"], ensure_ascii=False)}\n'
        "}\n"
    )


def read_points():
    path = GRAMMAR / "points.json"
    return json.loads(path.read_text()) if path.exists() else []


def add_points(new):
    """Add points, or replace those of the same id, in their order."""
    points = read_points()
    at = {p["id"]: n for n, p in enumerate(points)}
    for point in new:
        assert set(point) == set(FIELDS), point
        assert point["level"] in ("A1", "A2", "B1", "B2", "C1", "C2")
        if point["id"] in at:
            points[at[point["id"]]] = point
        else:
            at[point["id"]] = len(points)
            points.append(point)
    ids = {p["id"] for p in points}
    for point in points:
        for other in point["confused_with"] + point["requires"]:
            assert other in ids, (point["id"], other)
    GRAMMAR.mkdir(parents=True, exist_ok=True)
    (GRAMMAR / "points.json").write_text(format_points(points), encoding="utf-8")


def titled(pages):
    """Give each box with no title its Italian one."""
    return re.sub(
        r"^> \[!(merke|tipp|achtung|beispiel)\]\s*$",
        lambda m: f"> [!{m.group(1)}] {TITLES[m.group(1)]}",
        pages,
        flags=re.M,
    )


def check_pages(lesson_id, pages):
    split = [p.strip() for p in pages.split("\n---\n")]
    assert 8 <= len(split) <= 10, (lesson_id, len(split))
    for page in split:
        assert page.startswith("# "), (lesson_id, page[:40])
        for line in page.splitlines():
            if line.startswith("|"):
                cells = line.strip().strip("|").split("|")
                assert len(cells) <= 5, (lesson_id, line)
    for mark, inner in re.findall(r"\{([a-z]):([^}]*)\}", pages):
        assert mark in MARKS, (lesson_id, mark, inner)
        assert inner and not set(inner) & set("|{"), (lesson_id, inner)
    # every brace is part of a mark
    rest = re.sub(r"\{[a-z]:[^{}|]+\}", "", pages)
    assert "{" not in rest and "}" not in rest, (lesson_id, rest[rest.find("{") - 40:][:80])
    assert "[!" not in re.sub(r"> \[!(merke|tipp|achtung|beispiel)\] ", "", pages), lesson_id
    errors = [p for p in split if p.startswith("# Errori tipici")]
    assert errors, lesson_id
    rows = [l for l in errors[0].splitlines() if l.startswith("|")][2:]
    assert 5 <= len(rows) <= 8, (lesson_id, len(rows))
    for row in rows:
        assert row.split("|")[1].strip().startswith("{x:"), (lesson_id, row)
    assert split[-1].startswith("# In breve"), lesson_id
    assert "Scrivi le tue risposte nella chat" in split[-1], lesson_id
    first = next(p for p in split if "{" in p and "| " in p)
    assert "Colori:" in first, (lesson_id, "no Colori: legend")


def save_lesson(lesson_id, level, title, points, pages):
    pages = titled(pages.strip())
    check_pages(lesson_id, pages)
    known = {p["id"]: p for p in read_points()}
    for point_id, role in points:
        assert point_id in known, (lesson_id, point_id)
        assert role in ROLES, (lesson_id, role)
    lesson = {
        "id": lesson_id,
        "level": level,
        "title": title,
        "points": [{"id": p, "role": r} for p, r in points],
        "more_info": pages,
    }
    LESSONS.mkdir(parents=True, exist_ok=True)
    (LESSONS / f"{lesson_id}.json").write_text(format_lesson(lesson), encoding="utf-8")
    order_path = GRAMMAR / "order.json"
    order = json.loads(order_path.read_text()) if order_path.exists() else []
    if lesson_id not in order:
        order.append(lesson_id)
    order_path.write_text(json.dumps(order, indent=4) + "\n", encoding="utf-8")
    print("saved", lesson_id, len(pages.split("\n---\n")), "pages")


def point(id_, level, title, statement, when, confused_with=(), requires=()):
    return {
        "id": id_, "level": level, "title": title, "statement": statement,
        "when": when, "confused_with": list(confused_with),
        "requires": list(requires),
    }


if __name__ == "__main__":
    german = ROOT / "german" / "grammar"
    text = (german / "points.json").read_text()
    assert format_points(json.loads(text)) == text, "points round trip"
    for path in sorted((german / "lessons").glob("*.json")):
        text = path.read_text()
        assert format_lesson(json.loads(text)) == text, path.name
    text = (german / "order.json").read_text()
    assert json.dumps(json.loads(text), indent=4) + "\n" == text
    print("round trips ok")
    sys.exit(0)
