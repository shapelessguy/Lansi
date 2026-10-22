// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { afterEach, expect, test } from "vitest";

import {
    INTERFACE_LANGUAGES,
    interfaceLanguage,
    interfaceLanguageOf,
    languageName,
    type Message,
    plural,
    setInterfaceLanguage,
    t,
} from "./i18n";
import { MESSAGES } from "./messages";

afterEach(() => setInterfaceLanguage("English"));

const names = (text: string) => [...text.matchAll(/\{(\w+)\}/g)].map((found) => found[1]).sort();

test("the interface is in English when nothing else is known", () => {
    expect(interfaceLanguage()).toBe("English");
    expect(t("Log out")).toBe("Log out");
});

test("each translation has the names to fill in that its English has", () => {
    for (const [english, translated] of Object.entries(MESSAGES)) {
        for (const language of INTERFACE_LANGUAGES.filter((each) => each !== "English")) {
            expect(names(translated[language]), `${language}: ${english}`).toEqual(names(english));
        }
    }
});

test("a text is shown in the language of the interface, with its names filled in", () => {
    setInterfaceLanguage("German");
    expect(t("Log out (logged in as {user})", { user: "anna" })).toBe("Abmelden (angemeldet als anna)");
    setInterfaceLanguage("Italian");
    expect(t("Log out (logged in as {user})", { user: "anna" })).toBe("Esci (accesso come anna)");
});

test("the interface is in English when what is selected is translated into a language it is not written in", () => {
    expect(interfaceLanguageOf("German")).toBe("German");
    expect(interfaceLanguageOf("Spanish")).toBe("English");
});

test("a text the catalog lacks is shown as it is when the interface is not in English", () => {
    setInterfaceLanguage("Italian");
    expect(t("Not a message of the app" as Message)).toBe("Not a message of the app");
});

test("plural takes the form for one only when the count is one", () => {
    setInterfaceLanguage("German");
    expect(plural(1, "{count} word", "{count} words")).toBe("1 Wort");
    expect(plural(3, "{count} word", "{count} words")).toBe("3 Wörter");
    expect(plural(0, "{count} word", "{count} words")).toBe("0 Wörter");
});

test("a language is named in the language of the interface, and one it does not know keeps its name", () => {
    setInterfaceLanguage("Italian");
    expect(languageName("German")).toBe("Tedesco");
    expect(languageName("Klingon")).toBe("Klingon");
});
