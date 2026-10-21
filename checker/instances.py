# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""What an exercise makes for the learner, kept so that it can be done
again exactly as it was: an instance, such as a set of sentences or a story
with its questions, of the shape the manifest of the exercise declares
under `instance`, with nothing of what the learner answered.

The shape is a small part of JSON Schema, the same for every exercise, so
that what is kept is always of one shape and can be read back without the
exercise that made it:

    {"type": "object", "properties": {NAME: SCHEMA, ...},
     "required": [NAME, ...]}       an object of those properties alone, those
                                    required in it, and no others
    {"type": "array", "items": SCHEMA}
    {"type": "string"}, {"type": "integer"}, {"type": "number"},
    {"type": "boolean"}             each may have an "enum" of what it may be

A property that is not required may be left out, but is never null.
"""

from __future__ import annotations

from typing import Any

Schema = dict[str, Any]

# the types an instance may be made of, by what each is in Python
_TYPES: dict[str, tuple[type, ...]] = {
    "object": (dict,),
    "array": (list,),
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
}
# what each type is called where something is not of it
_SAID = {
    "object": "an object",
    "array": "a list",
    "string": "text",
    "integer": "a whole number",
    "number": "a number",
    "boolean": "true or false",
}
# what a schema of each type may say besides its type
_KEYS = {
    "object": {"type", "properties", "required", "description"},
    "array": {"type", "items", "description"},
}
_PLAIN = {"type", "enum", "description"}


def schema_problem(schema: object, where: str = "instance") -> str | None:
    """What keeps `schema` from being one an instance may be declared
    with, or None if nothing does."""
    if not isinstance(schema, dict) or schema.get("type") not in _TYPES:
        return f"{where} has no type, one of {', '.join(_TYPES)}"
    kind = schema["type"]
    unknown = set(schema) - _KEYS.get(kind, _PLAIN)
    if unknown:
        return f"{where} says what an instance cannot: {', '.join(sorted(unknown))}"
    if kind == "object":
        properties = schema.get("properties")
        required = schema.get("required", [])
        if not isinstance(properties, dict) or not properties:
            return f"{where} has no properties"
        if not isinstance(required, list) or not set(required) <= set(properties):
            return f"{where} requires what it has no property of"
        problems = (
            schema_problem(each, f"{where}.{name}") for name, each in properties.items()
        )
        return next((problem for problem in problems if problem), None)
    if kind == "array":
        return schema_problem(schema.get("items"), f"{where}[]")
    enum = schema.get("enum")
    if enum is not None and not (
        isinstance(enum, list) and enum and all(_is(each, kind) for each in enum)
    ):
        return f"{where} has an enum of what it cannot be"
    return None


def instance_problem(
    value: object, schema: Schema, where: str = "instance"
) -> str | None:
    """What keeps `value` from being of the shape of `schema`, a schema
    `schema_problem` finds nothing wrong with, or None if nothing does."""
    kind = schema["type"]
    if not _is(value, kind):
        return f"{where} is not {_SAID[kind]}"
    if "enum" in schema and value not in schema["enum"]:
        return f"{where} is not one of {', '.join(map(str, schema['enum']))}"
    if isinstance(value, dict):
        properties: dict[str, Schema] = schema["properties"]
        unknown = set(value) - set(properties)
        if unknown:
            return f"{where} has what its shape does not: {', '.join(sorted(unknown))}"
        missing = [name for name in schema.get("required", []) if name not in value]
        if missing:
            return f"{where} has no {', '.join(missing)}"
        problems = (
            instance_problem(value[name], properties[name], f"{where}.{name}")
            for name in value
        )
        return next((problem for problem in problems if problem), None)
    if isinstance(value, list):
        problems = (
            instance_problem(each, schema["items"], f"{where}[{number}]")
            for number, each in enumerate(value)
        )
        return next((problem for problem in problems if problem), None)
    return None


def _is(value: object, kind: str) -> bool:
    # in Python, true and false are whole numbers, which they are not in JSON
    if isinstance(value, bool) and kind != "boolean":
        return False
    return isinstance(value, _TYPES[kind])
