// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { defaultQuestions, isQuestion, type ProfileQuestion, upToDateQuestions } from "./questions";
import type { Word } from "./words";

/** Instructions a chat starts with. */
export interface ChatContext {
    id: string;
    name: string;
    prompt: string;
}

export interface Settings {
    apiKey: string;
    model: string;
    contexts: ChatContext[];
    /** The context new chats start with. */
    defaultContextId: string;
    /** The instructions texts are generated with. */
    textPrompt: string;
    speechModel: string;
    speechVoice: string;
    /** How texts are read aloud, such as the pace. Not spoken. */
    speechInstructions: string;
    /** The model that profiles each sentence typed in the chat. */
    profileModel: string;
    /** What the model is asked about each sentence. */
    questions: ProfileQuestion[];
    /** Whether Enter sends the message and Shift+Enter starts a new line, rather than the other way round. */
    enterSends: boolean;
    /** Whether the words of each sentence are rated once the questions about it are answered. */
    rateWords: boolean;
}

/** Replaced in a context's prompt by the list of known words. */
export const WORDS_PLACEHOLDER = "{{words}}";

const STORAGE_KEY = "chat-ui.settings";

export function defaultSettings(): Settings {
    return {
        apiKey: "",
        model: "openrouter/auto",
        contexts: [
            {
                id: "tutor",
                name: "Language tutor",
                prompt: "You are a friendly language tutor. Talk with me in the language I am learning, "
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
        textPrompt: "Write a text in the language I am learning, for me to read and listen to. "
            + "Use the words I know wherever you can; a few new words are fine. "
            + "Start with a short title as a Markdown heading, then the text. Write nothing else.\n\n"
            + `Words I know: ${WORDS_PLACEHOLDER}`,
        speechModel: "google/gemini-3.8-flash-tts",
        speechVoice: "Kore",
        speechInstructions: "Read clearly and a little slowly, for a language learner.",
        profileModel: "typesafe/jev-1.13",
        questions: defaultQuestions(),
        enterSends: true,
        rateWords: true,
    };
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
    const text = (key: "model" | "textPrompt" | "speechModel" | "speechVoice" | "profileModel") =>
        typeof candidate[key] === "string" && candidate[key] ? candidate[key] : defaults[key];
    return {
        apiKey: typeof candidate.apiKey === "string" ? candidate.apiKey : defaults.apiKey,
        model: text("model"),
        contexts,
        defaultContextId,
        textPrompt: text("textPrompt"),
        speechModel: text("speechModel"),
        speechVoice: text("speechVoice"),
        speechInstructions: typeof candidate.speechInstructions === "string"
            ? candidate.speechInstructions
            : defaults.speechInstructions,
        profileModel: text("profileModel"),
        // every question may have been deleted on purpose, so an empty list is kept
        questions: Array.isArray(candidate.questions)
            ? upToDateQuestions(candidate.questions.filter(isQuestion))
            : defaults.questions,
        enterSends: typeof candidate.enterSends === "boolean" ? candidate.enterSends : defaults.enterSends,
        rateWords: typeof candidate.rateWords === "boolean" ? candidate.rateWords : defaults.rateWords,
    };
}

export function loadSettings(): Settings {
    try {
        return normalizeSettings(JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "null"));
    } catch {
        return defaultSettings();
    }
}

export function saveSettings(settings: Settings): void {
    try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
    } catch {
        // storage can be unavailable in private windows; settings then last for the session
    }
}

/** The text a chat is started with: the prompt with the known words filled in. */
export function expandPrompt(prompt: string, words: Word[]): string {
    return prompt.replaceAll(WORDS_PLACEHOLDER, words.map((word) => word.word).join(", "));
}
