// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { expect, test } from "vitest";

import { onOpenRouter } from "./models";
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
    expect(settings.model).toEqual(defaultSettings().model);
    expect(settings.profileModel).toEqual(onOpenRouter("typesafe/jev-1.13"));
    expect(settings.enterSends).toBe(true);
    expect(settings.rateWords).toBe(true);
    // each correction is a billed request, so it is asked for only by turning it on
    expect(settings.correctSentences).toBe(false);
    expect(normalizeSettings({ correctSentences: true }).correctSentences).toBe(true);
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
    expect(normalizeSettings({ ankiLanguage: "Italian" }).ankiLanguage).toBe("Italian");
});

test("a language that can no longer be learned or translated into is stored as the usual one", () => {
    const stored = normalizeSettings({ language: "Spanish", ankiLanguage: "French", translateInto: "Polish" });
    expect([stored.language, stored.ankiLanguage, stored.translateInto]).toEqual(["German", "German", "English"]);
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
    expect([kept.imageModel, kept.embeddingModel]).toEqual([
        onOpenRouter("some/image"),
        defaultSettings().embeddingModel,
    ]);
    expect([unusable.exerciseMixTopics, unusable.exerciseVocabulary]).toEqual([false, {}]);
});

test("the options of the exercises are remembered, those that are not text or numbers left out", () => {
    const kept = normalizeSettings({
        exerciseOptions: { stories: { then: "retell", questions: 5, odd: [1] }, cloze: "five" },
    });

    expect(kept.exerciseOptions).toEqual({ stories: { then: "retell", questions: 5 } });
    expect(normalizeSettings({ exerciseOptions: 3 }).exerciseOptions).toEqual({});
});

test("how many times each exercise is done is remembered, what is not a number left out", () => {
    const kept = normalizeSettings({ exerciseInstances: { cloze: 3, stories: "two" } });

    expect(kept.exerciseInstances).toEqual({ cloze: 3 });
    expect(normalizeSettings({}).exerciseInstances).toEqual({});
});

test("the vision model is kept, and names none for the chat model", () => {
    expect(normalizeSettings({ visionModel: " some/seeing " }).visionModel).toEqual(onOpenRouter("some/seeing"));
    expect(normalizeSettings({}).visionModel).toEqual(onOpenRouter(""));
});

test("a model at an address is kept with its address and key", () => {
    const atHome = { model: "jev", url: "http://127.0.0.1:10000/v1", key: "k" };

    const kept = normalizeSettings({ profileModel: atHome, model: { url: 3 } });

    expect(kept.profileModel).toEqual(atHome);
    expect(kept.model).toEqual(defaultSettings().model);
});

test("the exercises are given the whole vocabulary of a language unless the settings say otherwise", () => {
    const settings = { ...defaultSettings(), exerciseVocabulary: { German: "none" } };

    expect(exerciseVocabularyOf(settings, "German")).toBe("none");
    expect(exerciseVocabularyOf(settings, "Spanish")).toBe("all");
});

test("the speech direction asks for the language being learned and the level unless it is changed", () => {
    expect(defaultSettings().speechDirection).toMatch(/^Speak \{\{language\}\}, .*level \{\{level\}\}\.$/);
    expect(normalizeSettings({ speechDirection: "Read slowly." }).speechDirection).toBe("Read slowly.");
    expect(normalizeSettings({ speechDirection: "" }).speechDirection).toBe("");
});

test("a speech direction saved before it could be written in full gets the language to speak put before it once", () => {
    const moved = normalizeSettings({ speechInstructions: " Read slowly. " });

    expect(moved.speechDirection).toBe(
        "Speak {{language}}, with native {{language}} pronunciation, even where a word looks like one of another"
            + " language. Read slowly.",
    );
    expect(normalizeSettings(moved).speechDirection).toBe(moved.speechDirection);
    expect(normalizeSettings({ speechInstructions: "" }).speechDirection).toMatch(/language\.$/);
});

test("the time limit of each exercise is remembered, what is not a number left out", () => {
    const kept = normalizeSettings({ exerciseMinutes: { cloze: 10, stories: "ten" } });

    expect(kept.exerciseMinutes).toEqual({ cloze: 10 });
    expect(normalizeSettings({}).exerciseMinutes).toEqual({});
});

test("an evaluation takes 1 to 8 half hours, timed unless it was chosen not to be", () => {
    expect(normalizeSettings({ evaluationLength: 5, evaluationTimed: false })).toMatchObject({
        evaluationLength: 5,
        evaluationTimed: false,
    });
    expect(normalizeSettings({ evaluationLength: 9 }).evaluationLength).toBe(2);
    expect(normalizeSettings({ evaluationLength: 1.5 }).evaluationLength).toBe(2);
    expect(normalizeSettings({}).evaluationTimed).toBe(true);
});

test("the reasoning model is kept, and names none for the chat model", () => {
    expect(normalizeSettings({ reasoningModel: "some/thinker" }).reasoningModel).toEqual(onOpenRouter("some/thinker"));
    expect(normalizeSettings({}).reasoningModel).toEqual(onOpenRouter(""));
});

test("every keyword is filled in, as often as it is named", () => {
    const words = { active: ["Hund"], named: { travel: ["Zug", "Bahnhof"] } };

    expect(expandPrompt("{{language}} at {{level}}: {{words}}; {{words:Travel}}; {{language}}", words, "German", "B1"))
        .toBe("German at B1: Hund; Zug, Bahnhof; German");
});
