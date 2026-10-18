// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { defaultQuestions, isQuestion, type ProfileQuestion, upToDateQuestions } from "./questions";
import { checkerFetch } from "./session";
import type { WordLists } from "./sets";

/** Instructions a chat starts with. */
export interface ChatContext {
    id: string;
    name: string;
    prompt: string;
}

export interface Settings {
    apiKey: string;
    /** The language being learned, by its English name. The vocabulary is of this language. */
    language: string;
    /** The language the words in Anki are of, which need not be the one being learned at present. */
    ankiLanguage: string;
    /** How far along the learner is in the language being learned, such as "B1". */
    level: string;
    /** The language what is selected is translated into, by its English name. */
    translateInto: string;
    /** The set of words `{{words}}` stands for, by its id, for each language. Without one it is every word. */
    activeSets: Record<string, string>;
    model: string;
    /** The model that translates what is selected. Left empty, it is the one of the chat. */
    translationModel: string;
    contexts: ChatContext[];
    /** The context new chats start with. */
    defaultContextId: string;
    speechModel: string;
    speechVoice: string;
    /**
     * What the speech model is told about how to read, such as the language
     * and the pace, with `{{language}}` and `{{level}}` filled in. Not spoken.
     */
    speechDirection: string;
    /** The model that profiles each sentence typed in the chat. */
    profileModel: string;
    /** What the model is asked about each sentence. */
    questions: ProfileQuestion[];
    /** Whether Enter sends the message and Shift+Enter starts a new line, rather than the other way round. */
    enterSends: boolean;
    /** Whether the words of each sentence are rated once the questions about it are answered. */
    rateWords: boolean;
    /** Whether each reply in the chat is read aloud once it has arrived. */
    speakReplies: boolean;
    /** Whether the Anki words the vocabulary lacks are taken into it as the app runs. */
    importAnki: boolean;
    /** Whether the app is light or dark, or as the machine it is shown on is. */
    theme: keyof typeof THEMES;
    /** The colour of what stands out, such as the buttons that send. */
    accent: keyof typeof ACCENTS;
    /** How large the app is written. */
    textSize: keyof typeof TEXT_SIZES;
    /** The model that makes the icon of a topic, and the pictures of exercises. */
    imageModel: string;
    /** The model that looks at the pictures of exercises, or blank for the chat model. */
    visionModel: string;
    /** The model that embeds the words of the vocabulary and the topics, to find the words of a topic. */
    embeddingModel: string;
    /** Whether the exercises bring all the topics chosen together, rather than one of them drawn for the session. */
    exerciseMixTopics: boolean;
    /** The words the exercises are given, for each language: "none", "all" of the vocabulary, or a set by its id. */
    exerciseVocabulary: Record<string, string>;
    /** Whether the words given are those nearest the topics, rather than those used last. */
    exerciseTopicWords: boolean;
    /** What the options of each exercise were last set to, by exercise and option. */
    exerciseOptions: Record<string, Record<string, string | number>>;
    /** How many times each exercise was last to be done, by exercise. */
    exerciseInstances: Record<string, number>;
    /** How many minutes each exercise was last to take, 0 for no limit, by exercise. */
    exerciseMinutes: Record<string, number>;
    /** How long an evaluation is to take, in half hours, from 1 to 8. */
    evaluationLength: number;
    /** Whether each part of an evaluation is to be done in its time. */
    evaluationTimed: boolean;
}

export const THEMES = { system: "As the system", light: "Light", dark: "Dark" } as const;

/** The colours to choose from for what stands out, each as it is on a light and on a dark app. */
export const ACCENTS = {
    blue: { label: "Blue", light: "#2f6fde", dark: "#6ea0f5" },
    teal: { label: "Teal", light: "#0b7285", dark: "#4fc3d9" },
    green: { label: "Green", light: "#1f7a4d", dark: "#5cc48d" },
    orange: { label: "Orange", light: "#b85c00", dark: "#f0a04b" },
    rose: { label: "Rose", light: "#c2255c", dark: "#f783ac" },
    purple: { label: "Purple", light: "#6b4fd8", dark: "#a594f9" },
} as const;

/** How large the app can be written, in pixels. */
export const TEXT_SIZES = {
    small: { label: "Small", px: 13.5 },
    normal: { label: "Normal", px: 15 },
    large: { label: "Large", px: 16.5 },
    larger: { label: "Larger", px: 18 },
} as const;

/** Has the page look as the settings say. */
export function applyAppearance(settings: Pick<Settings, "theme" | "accent" | "textSize">): void {
    const page = document.documentElement;
    // without a theme, the page is as the machine is
    if (settings.theme === "system") {
        delete page.dataset.theme;
    } else {
        page.dataset.theme = settings.theme;
    }
    page.style.setProperty("--accent-light", ACCENTS[settings.accent].light);
    page.style.setProperty("--accent-dark", ACCENTS[settings.accent].dark);
    page.style.fontSize = `${TEXT_SIZES[settings.textSize].px}px`;
}

/** Replaced in a prompt by the words of the set that is in use. */
export const WORDS_PLACEHOLDER = "{{words}}";
/** Replaced in a prompt by the words of the set of that name, such as `{{words:Travel}}`. */
const NAMED_WORDS = /\{\{words:([^}]+)\}\}/g;
/** Replaced in a prompt by the language being learned. */
export const LANGUAGE_PLACEHOLDER = "{{language}}";
/** Replaced in a prompt by the learner's level in that language. */
export const LEVEL_PLACEHOLDER = "{{level}}";

/** What the speech model was always told before what it is told could be written in full. */
const SPEAK_LANGUAGE = `Speak ${LANGUAGE_PLACEHOLDER}, with native ${LANGUAGE_PLACEHOLDER} pronunciation, `
    + "even where a word looks like one of another language.";

/** The levels a learner can be at, from beginner to proficient. */
export const LEVELS = ["A1", "A2", "B1", "B2", "C1", "C2"] as const;

/**
 * The languages that can be learned, by their English names: those the
 * checker server has a spelling dictionary for. The forms of words are
 * stored by rules of its own for German, and by general ones for the others.
 */
export const LANGUAGES = [
    "German",
    "Arabic",
    "Basque",
    "Dutch",
    "English",
    "French",
    "Italian",
    "Latvian",
    "Persian",
    "Portuguese",
    "Russian",
    "Spanish",
] as const;

/** The languages what is selected can be translated into, by their English names. */
export const TRANSLATION_LANGUAGES = [
    ...LANGUAGES,
    "Chinese",
    "Greek",
    "Hindi",
    "Japanese",
    "Korean",
    "Polish",
    "Romanian",
    "Swedish",
    "Turkish",
    "Ukrainian",
].sort();

const STORAGE_KEY = "chat-ui.settings";

export function defaultSettings(): Settings {
    return {
        apiKey: "",
        language: "German",
        ankiLanguage: "German",
        level: "B1",
        translateInto: "English",
        activeSets: {},
        model: "openrouter/auto",
        translationModel: "",
        contexts: [
            {
                id: "tutor",
                name: "Language tutor",
                prompt:
                    `You are a friendly language tutor. Talk with me in ${LANGUAGE_PLACEHOLDER}, which I am learning at level ${LEVEL_PLACEHOLDER}, `
                    + "using mostly the words I already know, and explain any new word you introduce.\n\n"
                    + `Words I know: ${WORDS_PLACEHOLDER}`,
            },
            {
                id: "assistant",
                name: "Plain assistant",
                prompt: "You are a helpful assistant.",
            },
        ],
        defaultContextId: "tutor",
        speechModel: "google/gemini-3.8-flash-tts",
        speechVoice: "Kore",
        speechDirection:
            `${SPEAK_LANGUAGE} Read clearly and a little slowly, for a learner at level ${LEVEL_PLACEHOLDER}.`,
        profileModel: "typesafe/jev-1.13",
        questions: defaultQuestions(),
        enterSends: true,
        rateWords: true,
        speakReplies: false,
        importAnki: true,
        theme: "system",
        accent: "blue",
        textSize: "normal",
        imageModel: "google/gemini-3.1-flash-lite-image",
        visionModel: "",
        embeddingModel: "baai/bge-m3",
        exerciseMixTopics: false,
        exerciseVocabulary: {},
        exerciseTopicWords: true,
        exerciseOptions: {},
        exerciseInstances: {},
        exerciseMinutes: {},
        evaluationLength: 2,
        evaluationTimed: true,
    };
}

/** What the exercises are given of the vocabulary of `language`: "none", "all", or the id of a set. */
export function exerciseVocabularyOf(settings: Settings, language: string): string {
    return settings.exerciseVocabulary[language] ?? "all";
}

/**
 * The direction for the speech model in stored settings. Those saved before
 * it could be written in full kept only how to read, after which the
 * language to speak was always put; that is put before it once, to be
 * changed or taken out from then on.
 */
function speechDirectionOf(stored: { speechDirection?: unknown; speechInstructions?: unknown }, usual: string): string {
    if (typeof stored.speechDirection === "string") {
        return stored.speechDirection;
    }
    if (typeof stored.speechInstructions === "string") {
        return [SPEAK_LANGUAGE, stored.speechInstructions.trim()].filter(Boolean).join(" ");
    }
    return usual;
}

/** Fills in anything missing or unusable in stored settings with the defaults. */
export function normalizeSettings(stored: unknown): Settings {
    const defaults = defaultSettings();
    if (typeof stored !== "object" || stored === null) {
        return defaults;
    }
    const candidate = stored as Partial<Settings>;
    const contexts = Array.isArray(candidate.contexts) && candidate.contexts.length > 0
        ? candidate.contexts
        : defaults.contexts;
    const defaultContextId = contexts.some((context) => context.id === candidate.defaultContextId)
        ? candidate.defaultContextId!
        : contexts[0].id;
    // settings saved before a field existed, or left blank where a value is needed, get the default
    const text = (
        key:
            | "model"
            | "speechModel"
            | "speechVoice"
            | "profileModel"
            | "translateInto"
            | "imageModel"
            | "embeddingModel",
    ) => typeof candidate[key] === "string" && candidate[key].trim() ? candidate[key] : defaults[key];
    return {
        apiKey: typeof candidate.apiKey === "string" ? candidate.apiKey : defaults.apiKey,
        language: LANGUAGES.find((language) => language === candidate.language) ?? defaults.language,
        ankiLanguage: LANGUAGES.find((language) => language === candidate.ankiLanguage) ?? defaults.ankiLanguage,
        level: LEVELS.find((level) => level === candidate.level) ?? defaults.level,
        translateInto: text("translateInto"),
        activeSets: typeof candidate.activeSets === "object" && candidate.activeSets !== null
            ? candidate.activeSets
            : defaults.activeSets,
        model: text("model"),
        translationModel: typeof candidate.translationModel === "string"
            ? candidate.translationModel
            : defaults.translationModel,
        contexts,
        defaultContextId,
        speechModel: text("speechModel"),
        speechVoice: text("speechVoice"),
        speechDirection: speechDirectionOf(candidate, defaults.speechDirection),
        profileModel: text("profileModel"),
        // every question may have been deleted on purpose, so an empty list is kept
        questions: Array.isArray(candidate.questions)
            ? upToDateQuestions(candidate.questions.filter(isQuestion))
            : defaults.questions,
        enterSends: typeof candidate.enterSends === "boolean" ? candidate.enterSends : defaults.enterSends,
        rateWords: typeof candidate.rateWords === "boolean" ? candidate.rateWords : defaults.rateWords,
        speakReplies: typeof candidate.speakReplies === "boolean" ? candidate.speakReplies : defaults.speakReplies,
        importAnki: typeof candidate.importAnki === "boolean" ? candidate.importAnki : defaults.importAnki,
        theme: Object.hasOwn(THEMES, candidate.theme ?? "") ? candidate.theme! : defaults.theme,
        accent: Object.hasOwn(ACCENTS, candidate.accent ?? "") ? candidate.accent! : defaults.accent,
        textSize: Object.hasOwn(TEXT_SIZES, candidate.textSize ?? "") ? candidate.textSize! : defaults.textSize,
        imageModel: text("imageModel"),
        // blank on purpose, for the chat model
        visionModel: typeof candidate.visionModel === "string" ? candidate.visionModel.trim() : defaults.visionModel,
        embeddingModel: text("embeddingModel"),
        exerciseMixTopics: typeof candidate.exerciseMixTopics === "boolean"
            ? candidate.exerciseMixTopics
            : defaults.exerciseMixTopics,
        exerciseVocabulary: typeof candidate.exerciseVocabulary === "object" && candidate.exerciseVocabulary !== null
            ? Object.fromEntries(
                Object.entries(candidate.exerciseVocabulary).filter(([, value]) => typeof value === "string"),
            )
            : defaults.exerciseVocabulary,
        exerciseTopicWords: typeof candidate.exerciseTopicWords === "boolean"
            ? candidate.exerciseTopicWords
            : defaults.exerciseTopicWords,
        exerciseOptions: exerciseOptionsOf(candidate.exerciseOptions),
        exerciseInstances: numbersOf(candidate.exerciseInstances),
        exerciseMinutes: numbersOf(candidate.exerciseMinutes),
        evaluationLength: typeof candidate.evaluationLength === "number"
                && Number.isInteger(candidate.evaluationLength)
                && candidate.evaluationLength >= 1
                && candidate.evaluationLength <= 8
            ? candidate.evaluationLength
            : defaults.evaluationLength,
        evaluationTimed: typeof candidate.evaluationTimed === "boolean"
            ? candidate.evaluationTimed
            : defaults.evaluationTimed,
    };
}

/** The numbers of stored settings kept by exercise, those that are not numbers left out. */
function numbersOf(stored: unknown): Record<string, number> {
    if (typeof stored !== "object" || stored === null) {
        return {};
    }
    return Object.fromEntries(
        Object.entries(stored).filter(([, value]) => typeof value === "number" && Number.isFinite(value)),
    );
}

/** The options of the exercises in stored settings, those that are not text or numbers left out. */
function exerciseOptionsOf(stored: unknown): Record<string, Record<string, string | number>> {
    if (typeof stored !== "object" || stored === null) {
        return {};
    }
    return Object.fromEntries(
        Object.entries(stored)
            .filter(([, options]) => typeof options === "object" && options !== null)
            .map(([exercise, options]) => [
                exercise,
                Object.fromEntries(
                    Object.entries(options as Record<string, unknown>).filter(([, value]) =>
                        typeof value === "string" || (typeof value === "number" && Number.isFinite(value))
                    ),
                ) as Record<string, string | number>,
            ]),
    );
}

/** Where the key is kept: in this browser only, and never by the server. */
const KEY_STORAGE_KEY = "chat-ui.key";

function loadApiKey(): string {
    try {
        return localStorage.getItem(KEY_STORAGE_KEY) ?? "";
    } catch {
        return "";
    }
}

/** The settings as they were kept in this browser, before the server kept them. */
function settingsOfThisBrowser(): Settings {
    try {
        return normalizeSettings(JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "null"));
    } catch {
        return defaultSettings();
    }
}

/** The settings without the key, which is all of them the server is given. */
export function withoutKey(settings: Settings): Omit<Settings, "apiKey"> {
    const { apiKey: _, ...rest } = settings;
    return rest;
}

/**
 * The settings of whoever is logged in, with the key of this browser. The
 * first time, the server has none, and is given the ones this browser has.
 */
export async function fetchSettings(): Promise<Settings> {
    const response = await checkerFetch("/settings");
    if (!response.ok) {
        throw new Error(`The server answered ${response.status}.`);
    }
    const { settings: kept }: { settings: unknown } = await response.json();
    if (kept === null) {
        const mine = settingsOfThisBrowser();
        saveSettings({ ...mine, apiKey: mine.apiKey || loadApiKey() });
        return { ...mine, apiKey: mine.apiKey || loadApiKey() };
    }
    return { ...normalizeSettings(kept), apiKey: loadApiKey() };
}

/** Keeps the key in this browser, and has the server keep everything else. */
export function saveSettings(settings: Settings): void {
    try {
        localStorage.setItem(KEY_STORAGE_KEY, settings.apiKey);
        // what was kept here before the server kept the settings, key and all
        localStorage.removeItem(STORAGE_KEY);
    } catch {
        // storage can be unavailable in private windows; the key then lasts for the session
    }
    checkerFetch("/settings", { method: "PUT", body: JSON.stringify(withoutKey(settings)) }).catch(() => undefined);
}

/**
 * The text a chat is started with: the prompt with the words of the sets it
 * asks for, the language being learned and the learner's level filled in.
 * A set that there is not gives no words.
 */
export function expandPrompt(prompt: string, words: WordLists, language: string, level: string): string {
    return prompt
        .replace(NAMED_WORDS, (_, name: string) => (words.named[name.trim().toLowerCase()] ?? []).join(", "))
        .replaceAll(WORDS_PLACEHOLDER, words.active.join(", "))
        .replaceAll(LANGUAGE_PLACEHOLDER, language)
        .replaceAll(LEVEL_PLACEHOLDER, level);
}
