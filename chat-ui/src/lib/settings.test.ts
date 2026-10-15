// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { expect, test } from "vitest";

import type { WordLists } from "./sets";
import { defaultSettings, exerciseVocabularyOf, expandPrompt, normalizeSettings, withoutKey } from "./settings";

/** The lists of words a prompt can ask for, with these as the ones in use. */
function lists(active: string[] = [], named: Record<string, string[]> = {}): WordLists {
    return { active, named };
}

test("the placeholder is replaced by the words of the set in use", () => {
    const prompt = expandPrompt("Use only: {{words}}.", lists(["sitzen", "Film"]), "German", "B1");

    expect(prompt).toBe("Use only: sitzen, Film.");
});

test("a prompt without the placeholder is left as written", () => {
    expect(expandPrompt("You are a helpful assistant.", lists(["sitzen"]), "German", "B1")).toBe(
        "You are a helpful assistant.",
    );
});

test("missing stored settings give the defaults", () => {
    expect(normalizeSettings(null)).toEqual(defaultSettings());
});

test("stored values are kept and gaps are filled from the defaults", () => {
    const settings = normalizeSettings({ apiKey: "sk-or-test", model: "" });

    expect(settings.apiKey).toBe("sk-or-test");
    expect(settings.model).toBe(defaultSettings().model);
    expect(settings.profileModel).toBe("typesafe/jev-1.13");
    expect(settings.enterSends).toBe(true);
    expect(settings.rateWords).toBe(true);
    expect(settings.contexts).toEqual(defaultSettings().contexts);
});

test("a default context that no longer exists falls back to the first one", () => {
    const contexts = [{ id: "a", name: "A", prompt: "" }, { id: "b", name: "B", prompt: "" }];

    const settings = normalizeSettings({ contexts, defaultContextId: "deleted" });

    expect(settings.defaultContextId).toBe("a");
});

test("the placeholder is replaced by the language being learned", () => {
    expect(expandPrompt("Talk with me in {{language}}.", lists(), "Italian", "B1")).toBe("Talk with me in Italian.");
});

test("a new chat is told the language being learned", () => {
    const settings = defaultSettings();

    expect(settings.language).toBe("German");
    expect(expandPrompt(settings.contexts[0].prompt, lists(), settings.language, settings.level)).toContain(
        "Talk with me in German, which I am learning at level B1",
    );
});

test("a stored language that cannot be learned gives the usual one", () => {
    expect(normalizeSettings({ language: "Italian" }).language).toBe("Italian");
    expect(normalizeSettings({ language: "Klingon" }).language).toBe("German");
});

test("the Anki words are taken to be German unless another language is stored", () => {
    expect(normalizeSettings({}).ankiLanguage).toBe("German");
    expect(normalizeSettings({ ankiLanguage: "Spanish" }).ankiLanguage).toBe("Spanish");
});

test("the placeholder is replaced by the level of the learner", () => {
    expect(expandPrompt("Write for level {{level}}.", lists(), "German", "B2")).toBe("Write for level B2.");
});

test("a stored level that there is not gives the usual one", () => {
    expect(normalizeSettings({ level: "C1" }).level).toBe("C1");
    expect(normalizeSettings({ level: "Z9" }).level).toBe("B1");
});

test("the server is given the settings without the key", () => {
    const given = withoutKey({ ...defaultSettings(), apiKey: "sk-or-test", level: "B2" });

    expect("apiKey" in given).toBe(false);
    expect(given.level).toBe("B2");
});

test("a set is asked for by its name, however the name is capitalised", () => {
    const words = lists(["sitzen"], { travel: ["Zug", "Reise"], "at home": ["Tisch"] });

    const prompt = expandPrompt(
        "All: {{words}}. Trip: {{words:Travel}}. Home: {{words: At Home }}.",
        words,
        "German",
        "B1",
    );

    expect(prompt).toBe("All: sitzen. Trip: Zug, Reise. Home: Tisch.");
});

test("a set that there is not gives no words", () => {
    expect(expandPrompt("Use: {{words:Gone}}.", lists(["sitzen"]), "German", "B1")).toBe("Use: .");
});

test("the app looks as it was set to, and as usual where what is stored is not a way to look", () => {
    const stored = { theme: "dark", accent: "green", textSize: "large" };
    const unusable = { theme: "pink", accent: "toString", textSize: 3 };

    expect(normalizeSettings(stored)).toMatchObject(stored);
    expect(normalizeSettings(unusable)).toMatchObject({ theme: "system", accent: "blue", textSize: "normal" });
    expect(normalizeSettings({})).toMatchObject({ theme: "system", accent: "blue", textSize: "normal" });
});

test("the exercise settings are kept, and those that cannot be are the usual ones", () => {
    const kept = normalizeSettings({
        exerciseMixTopics: true,
        exerciseVocabulary: { German: "set-1", Spanish: 3 },
        exerciseTopicWords: false,
        imageModel: "some/image",
        embeddingModel: " ",
    });
    const unusable = normalizeSettings({ exerciseMixTopics: "yes", exerciseVocabulary: "all" });

    expect([kept.exerciseMixTopics, kept.exerciseTopicWords]).toEqual([true, false]);
    expect(kept.exerciseVocabulary).toEqual({ German: "set-1" });
    expect([kept.imageModel, kept.embeddingModel]).toEqual(["some/image", defaultSettings().embeddingModel]);
    expect([unusable.exerciseMixTopics, unusable.exerciseVocabulary]).toEqual([false, {}]);
});

test("the vision model is kept, and left blank for the chat model", () => {
    expect(normalizeSettings({ visionModel: " some/seeing " }).visionModel).toBe("some/seeing");
    expect(normalizeSettings({}).visionModel).toBe("");
});

test("the exercises are given the whole vocabulary of a language unless the settings say otherwise", () => {
    const settings = { ...defaultSettings(), exerciseVocabulary: { German: "none" } };

    expect(exerciseVocabularyOf(settings, "German")).toBe("none");
    expect(exerciseVocabularyOf(settings, "Spanish")).toBe("all");
});
