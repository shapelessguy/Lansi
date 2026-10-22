// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

// The interface is shown in the language the learner has what they select
// translated into, if it is one of those it is written in, and in English
// otherwise. What it shows is written in English where it is shown, and
// `t` finds it in MESSAGES, which has it in each of the other languages; a
// text MESSAGES lacks does not compile. A text can have `{name}` in it, for
// what is put in its place when it is shown.

import { type Message, MESSAGES } from "./messages";

export type { Message } from "./messages";

/** The languages the interface is written in, by their English names. */
export const INTERFACE_LANGUAGES = ["English", "German", "Italian"] as const;
export type InterfaceLanguage = (typeof INTERFACE_LANGUAGES)[number];

/** The tag of each language, for the dates and the numbers it shows. */
const LOCALES: Record<InterfaceLanguage, string> = { English: "en", German: "de", Italian: "it" };

const STORAGE_KEY = "chat-ui.interface-language";

/** The language of the interface for one who has what they select translated into `language`. */
export function interfaceLanguageOf(language: string): InterfaceLanguage {
    return (INTERFACE_LANGUAGES as readonly string[]).includes(language) ? (language as InterfaceLanguage) : "English";
}

/** The language the interface was shown in last, or the browser's, for the login before any settings are known. */
function startingLanguage(): InterfaceLanguage {
    try {
        const kept = localStorage.getItem(STORAGE_KEY);
        if (kept) {
            return interfaceLanguageOf(kept);
        }
    } catch {
        // storage is blocked, so the browser's language is taken
    }
    // outside a page, as in the tests, the language of the machine is not the learner's
    const tag = typeof window === "undefined" ? "" : navigator.language.slice(0, 2);
    const found = Object.entries(LOCALES).find(([, locale]) => locale === tag);
    return found ? (found[0] as InterfaceLanguage) : "English";
}

let current: InterfaceLanguage = startingLanguage();

/** The language the interface is shown in now. */
export function interfaceLanguage(): InterfaceLanguage {
    return current;
}

/** The tag of the language of the interface, for `toLocaleString` and the like. */
export function locale(): string {
    return LOCALES[current];
}

/**
 * Shows the interface in `language` from now on. The app calls it as it
 * renders, so that all it renders then is in that language.
 */
export function setInterfaceLanguage(language: InterfaceLanguage) {
    if (language === current) {
        return;
    }
    current = language;
    try {
        localStorage.setItem(STORAGE_KEY, language);
    } catch {
        // the login is shown in the browser's language next time
    }
    if (typeof document !== "undefined") {
        document.documentElement.lang = LOCALES[language];
    }
}

/** `text` with each `{name}` in it given its value; a name without one is left as it is. */
export function filled(text: string, values: Record<string, string | number> = {}): string {
    return text.replace(/\{(\w+)\}/g, (whole, name: string) => (name in values ? String(values[name]) : whole));
}

/** `message` in the language of the interface, with each `{name}` in it given its value. */
export function t(message: Message, values: Record<string, string | number> = {}): string {
    // one the catalog lacks, such as one handed on from the server, is shown as it is
    return filled(current === "English" ? message : MESSAGES[message]?.[current] ?? message, values);
}

/**
 * `text`, which is known only as the app runs, such as what an exercise
 * shows, in the language of the interface if the catalog has it, and as it
 * is otherwise.
 */
export function translated(text: string, values: Record<string, string | number> = {}): string {
    return Object.hasOwn(MESSAGES, text) ? t(text as Message, values) : filled(text, values);
}

/** A language, by its English name, as the interface calls it; one the interface does not know keeps its name. */
export function languageName(name: string): string {
    return translated(name);
}

/**
 * `one` if `count` is 1, and `other` otherwise, with `{count}` given it,
 * which is how each language of the interface tells one from many.
 */
export function plural(
    count: number,
    one: Message,
    other: Message,
    values: Record<string, string | number> = {},
): string {
    return t(count === 1 ? one : other, { count, ...values });
}
