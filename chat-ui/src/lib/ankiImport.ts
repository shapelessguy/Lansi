// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { useEffect, useRef, useState } from "react";

import type { ProfileUsage } from "./checker";
import { checkerFetch } from "./session";

/** How often the checker server is told the settings and asked how the import is going. */
const INTERVAL_MS = 3000;

/** What the checker server's import of the Anki words into the vocabulary is doing. */
export interface ImportStatus {
    /**
     * "off": it is switched off
     * "no-key": it waits for an OpenRouter key
     * "unavailable": Anki, a model or the checker could not be asked; `message` says why
     * "importing": words are being taken in
     * "waiting": it waits for the next look
     */
    state: "off" | "no-key" | "unavailable" | "importing" | "waiting";
    /** How many Anki words the vocabulary still lacks, once that is known. */
    remaining: number | null;
    /** How many words have been taken in since the server started. */
    taken: number;
    /** What was said when Anki, a model or the checker could not be asked. */
    message: string;
}

interface ImportReply extends ImportStatus {
    /** The requests to the models the import has made since it was last asked. */
    usage: ProfileUsage[];
}

/**
 * Tells the checker server what its import of the Anki words is to go by,
 * and returns what the import is doing. The key goes along so that the
 * server, which does the importing by itself, has one to ask the models with.
 */
export async function syncImport(
    enabled: boolean,
    apiKey: string,
    model: string,
    decisionModel: string,
    language: string,
    ankiLanguage: string,
): Promise<ImportReply> {
    let response: Response;
    try {
        response = await checkerFetch("/vocabulary/import", {
            method: "POST",
            headers: apiKey ? { "X-OpenRouter-Key": apiKey } : undefined,
            body: JSON.stringify({
                enabled,
                model,
                decision_model: decisionModel,
                language,
                anki_language: ankiLanguage,
            }),
        });
    } catch {
        throw new Error("The checker server cannot be reached.");
    }
    if (!response.ok) {
        throw new Error(`The checker server answered ${response.status}.`);
    }
    return await response.json();
}

interface Options {
    enabled: boolean;
    apiKey: string;
    /** The model that judges and describes new words. */
    model: string;
    /** The model that sorts words into categories when there is none on this machine. */
    decisionModel: string;
    /** The language being learned. */
    language: string;
    /** The language the Anki words are of, and so the vocabulary they go into. */
    ankiLanguage: string;
    onUsage: (used: ProfileUsage) => void;
    /** Told each time more words have been taken in. */
    onImported: () => void;
}

/**
 * Keeps the checker server's import of the Anki words going by the settings,
 * and follows what it is doing. The importing itself is the server's: every
 * ten seconds it looks through the Anki words for ones the vocabulary lacks.
 */
export function useAnkiImport(options: Options): ImportStatus {
    const [status, setStatus] = useState<ImportStatus>({
        state: "waiting",
        remaining: null,
        taken: 0,
        message: "",
    });
    const latest = useRef(options);
    latest.current = options;

    useEffect(() => {
        let stopped = false;
        let timer: ReturnType<typeof setTimeout>;
        let taken: number | null = null;

        async function sync() {
            const { enabled, apiKey, model, decisionModel, language, ankiLanguage, onUsage, onImported } =
                latest.current;
            try {
                const { usage, ...next } = await syncImport(
                    enabled,
                    apiKey,
                    model,
                    decisionModel,
                    language,
                    ankiLanguage,
                );
                if (stopped) {
                    return;
                }
                usage.forEach(onUsage);
                setStatus(next);
                if (taken !== null && next.taken !== taken) {
                    onImported();
                }
                taken = next.taken;
            } catch (error) {
                if (!stopped) {
                    setStatus((current) => ({
                        ...current,
                        state: "unavailable",
                        message: (error as Error).message,
                    }));
                }
            }
            if (!stopped) {
                timer = setTimeout(sync, INTERVAL_MS);
            }
        }
        sync();
        return () => {
            stopped = true;
            clearTimeout(timer);
        };
    }, []);

    return status;
}
