// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { useCallback, useEffect, useRef, useState } from "react";

import type { ProfileUsage } from "./checker";
import { t } from "./i18n";
import { type ModelChoice, modelRequest } from "./models";
import { checkerFetch } from "./session";

/** How often the checker server is asked how the translating of the words is going. */
const INTERVAL_MS = 3000;

/** What the checker server's translating of the stored words into one language is doing. */
export interface TranslationsStatus {
    /**
     * "idle": nothing is being translated
     * "translating": words are being translated
     * "no-key": it was asked to, but there is no OpenRouter key
     * "unavailable": a model or the checker could not be asked; `message` says why
     */
    state: "idle" | "translating" | "no-key" | "unavailable";
    /** How many words are not translated into the language, or null until the server has said. */
    remaining: number | null;
    /** How many words have been translated since it was started. */
    translated: number;
    message: string;
}

interface TranslationsReply extends TranslationsStatus {
    /** The requests to the models the translating has made since it was last asked. */
    usage: ProfileUsage[];
}

/**
 * Asks the checker server how many stored words of `language` are not
 * translated into `into`, and how the translating of them is going, and has
 * it start translating them if `start` is true. The key goes along so that
 * the server, which does the translating by itself, has one to ask the
 * models with.
 */
export async function syncTranslations(
    apiKey: string,
    model: ModelChoice,
    language: string,
    into: string,
    start: boolean,
): Promise<TranslationsReply> {
    let response: Response;
    try {
        response = await checkerFetch("/vocabulary/translations", {
            method: "POST",
            headers: apiKey ? { "X-OpenRouter-Key": apiKey } : undefined,
            body: JSON.stringify({ model: modelRequest(model), language, into, start }),
        });
    } catch {
        throw new Error(t("The checker server cannot be reached."));
    }
    if (!response.ok) {
        throw new Error(t("The checker server answered {status}.", { status: response.status }));
    }
    return await response.json();
}

interface Options {
    /** Whether the words are on show: the server is asked only while they are. */
    active: boolean;
    apiKey: string;
    /** The model that translates the words, the one that describes new words. */
    model: ModelChoice;
    /** The language being learned, whose vocabulary it is. */
    language: string;
    /** The language the words are wanted translated into. */
    into: string;
    onUsage: (used: ProfileUsage) => void;
}

export interface WordTranslations {
    status: TranslationsStatus;
    /** Has the words that are not translated into the language translated. */
    start: () => void;
}

/** Follows how many stored words are not translated into the language translated into, and their translating. */
export function useWordTranslations(options: Options): WordTranslations {
    const [status, setStatus] = useState<TranslationsStatus>({
        state: "idle",
        remaining: null,
        translated: 0,
        message: "",
    });
    const latest = useRef(options);
    latest.current = options;
    const { active, language, into } = options;

    const sync = useCallback(async (start: boolean) => {
        const { apiKey, model, language, into, onUsage } = latest.current;
        try {
            const { usage, ...next } = await syncTranslations(apiKey, model, language, into, start);
            usage.forEach(onUsage);
            // what is said of another language than the one wanted by now is of no use
            if (latest.current.language === language && latest.current.into === into) {
                setStatus(next);
            }
        } catch (error) {
            setStatus((current) => ({ ...current, state: "unavailable", message: (error as Error).message }));
        }
    }, []);

    useEffect(() => {
        setStatus({ state: "idle", remaining: null, translated: 0, message: "" });
    }, [language, into]);

    useEffect(() => {
        if (!active) {
            return;
        }
        let stopped = false;
        let timer: ReturnType<typeof setTimeout>;
        async function follow() {
            await sync(false);
            if (!stopped) {
                timer = setTimeout(follow, INTERVAL_MS);
            }
        }
        follow();
        return () => {
            stopped = true;
            clearTimeout(timer);
        };
    }, [active, language, into, sync]);

    const start = useCallback(() => {
        setStatus((current) => ({ ...current, state: "translating", message: "" }));
        sync(true);
    }, [sync]);

    return { status, start };
}
