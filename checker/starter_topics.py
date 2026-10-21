# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""The topics every user starts with, besides those they add: a title and
what it is about, each with the icon of it in starter_icons/, a PNG named
by its title, as `starter_icon` gives it, so that no image model, which is
paid for, has to draw them again for each user."""

from __future__ import annotations

import re
from pathlib import Path

STARTER_ICONS = Path(__file__).parent / "starter_icons"

STARTER_TOPICS: list[tuple[str, str]] = [
    ("Family", "parents, brothers and sisters, relatives and family life"),
    ("Friends", "meeting friends, making plans and doing each other favours"),
    ("At home", "rooms, furniture and the housework"),
    ("Food and cooking", "ingredients, recipes and meals"),
    ("At the restaurant", "ordering, paying the bill and complaining"),
    ("At the supermarket", "groceries, quantities and prices"),
    ("Shopping", "shops, sizes, prices and paying"),
    ("Clothes and fashion", "what people wear, trying things on and style"),
    ("Work and jobs", "professions, the office and colleagues"),
    ("Job interview", "applying for a job, experience and strengths"),
    ("School and studying", "lessons, exams, teachers and university"),
    ("At the doctor", "symptoms, appointments and medicine"),
    ("Health and fitness", "exercise, sleep and eating well"),
    ("Travel", "planning a trip, luggage and hotels"),
    ("At the train station", "tickets, platforms, delays and connections"),
    ("At the airport", "check-in, security, gates and flights"),
    ("In the city", "asking the way, sights and public transport"),
    ("Weather and seasons", "the forecast, the seasons and what to wear"),
    ("Nature", "hiking, mountains, the sea, animals and plants"),
    ("Holidays and celebrations", "birthdays, Christmas, weddings and festivals"),
    ("Hobbies and free time", "what people do at the weekend"),
    ("Films and TV", "series, cinema, actors and recommendations"),
    ("Books and reading", "novels, authors and favourite stories"),
    ("Technology", "phones, computers and the internet"),
    ("Social media", "posts, messages, photos and being online"),
    ("The environment", "recycling, the climate and saving energy"),
    ("Renting a flat", "looking for a flat, the landlord and the neighbours"),
    ("At the bank and the post office", "accounts, cards, parcels and letters"),
    ("Feelings", "being happy, sad, angry, nervous or tired"),
    ("Love and relationships", "dating, couples and breaking up"),
    ("Pets and animals", "dogs, cats, farm animals and the zoo"),
    ("Cars and driving", "the driving test, traffic and repairs"),
    ("Emergencies", "the police, accidents, fires and lost things"),
    ("Society and politics", "elections, news and how people live together"),
    ("History", "the past, famous events and how things used to be"),
    ("Art and museums", "paintings, exhibitions and artists"),
    ("Childhood memories", "growing up, games and school days"),
]


def starter_icon(title: str) -> bytes | None:
    """The icon of a starter topic, by its title, as a PNG, if it has one."""
    name = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    file = STARTER_ICONS / f"{name}.png"
    return file.read_bytes() if file.is_file() else None
