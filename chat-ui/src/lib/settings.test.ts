// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { expect, test } from "vitest";

import { defaultSettings, expandPrompt, normalizeSettings } from "./settings";
import type { Word } from "./words";

function word(text: string): Word {
    return { noteId: 0, word: text, meaning: "", partOfSpeech: "", due: "2026-01-01", intervalDays: 1 };
}

test("the placeholder is replaced by the known words", () => {
    const prompt = expandPrompt("Use only: {{words}}.", [word("sitzen"), word("der Film")]);

    expect(prompt).toBe("Use only: sitzen, der Film.");
});

test("a prompt without the placeholder is left as written", () => {
    expect(expandPrompt("You are a helpful assistant.", [word("sitzen")])).toBe("You are a helpful assistant.");
});

test("missing stored settings give the defaults", () => {
    expect(normalizeSettings(null)).toEqual(defaultSettings());
});

test("stored values are kept and gaps are filled from the defaults", () => {
    const settings = normalizeSettings({ apiKey: "sk-or-test", model: "" });

    expect(settings.apiKey).toBe("sk-or-test");
    expect(settings.model).toBe(defaultSettings().model);
    expect(settings.profileModel).toBe("typesafe/jev-1.13");
    expect(settings.contexts).toEqual(defaultSettings().contexts);
});

test("a default context that no longer exists falls back to the first one", () => {
    const contexts = [{ id: "a", name: "A", prompt: "" }, { id: "b", name: "B", prompt: "" }];

    const settings = normalizeSettings({ contexts, defaultContextId: "deleted" });

    expect(settings.defaultContextId).toBe("a");
});
