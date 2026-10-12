// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { useEffect, useRef, useState } from "react";

/** A word the checker server's spell checker does not know. */
export interface SpellingIssue {
    word: string;
    /** Where the word is: in its sentence as the server sends it, in the whole text once placed. */
    start: number;
    end: number;
    /** Best first. May be empty. */
    suggestions: string[];
}

/** A sentence of the text being typed, as the checker server splits and checks it. */
export interface Sentence {
    text: string;
    /** Where it is in the text that was sent. */
    start: number;
    end: number;
    /** False while the caret is on the sentence, start and end included. */
    complete: boolean;
    spelling: SpellingIssue[];
    /** Whether the sentence, as it is now, has been profiled. */
    processed: boolean;
    /** What the questions asked about the sentence came back with, once it has been profiled. */
    profile?: SentenceProfile | null;
    /** True while the profile is being made. */
    profiling?: boolean;
}

/** The answers to the questions asked about a sentence, and what asking used. */
export interface SentenceProfile {
    /** Tells the request that made it from any other. */
    id: string;
    model: string;
    input_tokens: number;
    output_tokens: number;
    /** In US dollars; null if not reported. */
    cost: number | null;
}

/** What the checker server said about a text. */
export interface LiveCheck {
    text: string;
    sentences: Sentence[];
}

/** Where the dev server forwards requests to the checker server. */
const BASE = "/checker";
const INTERVAL_MS = 1000;

/**
 * Has the checker server split `text` into sentences and check each. `caret`
 * is where the caret is in the text, or null if the text box is not in use;
 * the sentence it is in comes back as not complete. Finished sentences are
 * profiled by `model`, if there is a key.
 */
export async function fetchSentences(
    text: string,
    caret: number | null,
    apiKey: string,
    model: string,
): Promise<Sentence[]> {
    const response = await fetch(`${BASE}/sentences`, {
        method: "POST",
        // the server profiles finished sentences with the key; it stays on this machine until then
        headers: apiKey ? { "X-OpenRouter-Key": apiKey } : {},
        body: JSON.stringify({ text, caret, model }),
    });
    if (!response.ok) {
        throw new Error(`checker server: ${response.status}`);
    }
    return response.json();
}

/**
 * Sends the text being typed and the place of the caret to the checker server
 * once a second, whenever either has changed since they were last sent, and
 * returns the latest answer. The answer may be about a slightly older text
 * than the one given. It stays null if the server is not running.
 */
export function useLiveCheck(text: string, caret: number | null, apiKey: string, model: string): LiveCheck | null {
    const [check, setCheck] = useState<LiveCheck | null>(null);
    const latest = useRef({ text, caret });
    latest.current = { text, caret };
    const profiling = useRef({ apiKey, model });
    profiling.current = { apiKey, model };

    useEffect(() => {
        let sent: { text: string; caret: number | null } = { text: "", caret: null };
        // a profile was still being made at the last answer, so it is worth asking again
        let awaitingProfile = false;
        let stopped = false;
        const timer = setInterval(() => {
            const current = latest.current;
            // an empty box has nothing to say about, wherever the caret is
            const unchanged = current.text === sent.text && (current.caret === sent.caret || current.text === "");
            if (unchanged && !awaitingProfile) {
                return;
            }
            sent = current;
            awaitingProfile = false;
            fetchSentences(current.text, current.caret, profiling.current.apiKey, profiling.current.model).then(
                (sentences) => {
                    // an answer that arrives after something newer was sent is out of date
                    if (stopped || sent !== current) {
                        return;
                    }
                    awaitingProfile = sentences.some((sentence) => sentence.profiling);
                    setCheck({ text: current.text, sentences });
                },
                () => {
                    // typing must not be disturbed by the checker being off
                },
            );
        }, INTERVAL_MS);
        return () => {
            stopped = true;
            clearInterval(timer);
        };
    }, []);

    return check;
}

/**
 * The spelling issues to show in `text`, placed in the whole text.
 *
 * The check may be of an older version of the text, so an issue is kept only
 * if its word is still where it was. The word the caret is in or next to is
 * left out as well, as it is probably not finished.
 */
export function spellingIssues(check: LiveCheck | null, text: string, caret: number | null): SpellingIssue[] {
    if (!check) {
        return [];
    }
    return check.sentences
        .flatMap((sentence) =>
            // a checker server from before spelling was added sends none
            (sentence.spelling ?? []).map((issue) => ({
                ...issue,
                start: sentence.start + issue.start,
                end: sentence.start + issue.end,
            }))
        )
        .filter((issue) => text.slice(issue.start, issue.end) === issue.word)
        .filter((issue) => caret === null || caret < issue.start || caret > issue.end);
}

/** The models OpenRouter offers that can profile a sentence: those that answer set questions. Needs no key. */
export async function fetchProfileModels(): Promise<string[]> {
    const response = await fetch("https://openrouter.ai/api/v1/models?output_modalities=decisions");
    const models: { id: string }[] = (await response.json()).data;
    return models.map((model) => model.id);
}

/** `text` cut into the stretches with and without a spelling issue, in order. */
export function markedParts(text: string, issues: SpellingIssue[]): { text: string; issue: SpellingIssue | null }[] {
    const parts: { text: string; issue: SpellingIssue | null }[] = [];
    let position = 0;
    for (const issue of issues) {
        if (issue.start > position) {
            parts.push({ text: text.slice(position, issue.start), issue: null });
        }
        parts.push({ text: text.slice(issue.start, issue.end), issue });
        position = issue.end;
    }
    if (position < text.length) {
        parts.push({ text: text.slice(position), issue: null });
    }
    return parts;
}

/** `text` with the misspelled word replaced by one of its suggestions. */
export function applySuggestion(text: string, issue: SpellingIssue, suggestion: string): string {
    return text.slice(0, issue.start) + suggestion + text.slice(issue.end);
}
