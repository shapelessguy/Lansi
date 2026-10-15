// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { useEffect, useRef, useState } from "react";

import type { ProfileAnswer, RequestQuestions } from "./questions";
import { checkerFetch } from "./session";

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
    /** False while the caret is on the sentence. Behind its ending mark, the caret has left it. */
    complete: boolean;
    spelling: SpellingIssue[];
    /** Whether the sentence, as it is now, has been profiled. */
    processed: boolean;
    /** What the questions asked about the sentence came back with, once it has been profiled. */
    profile?: SentenceProfile | null;
    /** True while the profile is being made. */
    profiling?: boolean;
    /** Why the profile could not be made, if it could not. */
    profile_error?: string | null;
    /** How right each word is where it stands, once the words have been rated. */
    words?: WordRating[];
    /** True while the words are being rated. */
    rating_words?: boolean;
}

/** How right a word of a sentence is where it stands. */
export interface WordRating {
    word: string;
    /** Where the word is in its sentence. */
    start: number;
    end: number;
    /** From 0, for a word that is wrong, to 1, for one that is right. */
    value: number;
}

/** The answers to the questions asked about a sentence. */
export interface SentenceProfile {
    /** The answer to each question, by the question's id. */
    answers: Record<string, ProfileAnswer>;
}

/** What one request to the model that answers the questions used. */
export interface ProfileUsage {
    /** Tells the request from any other. */
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
    /** The model on this machine that answers the questions at present, or null if OpenRouter does. */
    localModel: string | null;
}

/** The checker server's reply to a text. */
interface CheckReply {
    sentences: Sentence[];
    /**
     * The requests to the model that have come back since the last reply.
     * Each is reported once, whether or not its answer was still wanted.
     */
    usage: ProfileUsage[];
    /** Whether requests to the model are still out. */
    pending: boolean;
    /** The model on this machine that answers the questions at present, or null if OpenRouter does. */
    local_model: string | null;
}

const INTERVAL_MS = 300;

/**
 * Has the checker server split `text` into sentences and check each. `caret`
 * is where the caret is in the text, or null if the text box is not in use;
 * the sentence it is in comes back as not complete. Finished sentences are
 * profiled by having `model` answer `questions`, if there is a key, and with
 * `rateWords` their words are then rated. `language` is the one being
 * learned, which the spelling and the sentences are checked by.
 */
export async function fetchCheck(
    text: string,
    caret: number | null,
    apiKey: string,
    model: string,
    questions: RequestQuestions,
    rateWords: boolean,
    language: string,
): Promise<CheckReply> {
    const response = await checkerFetch("/sentences", {
        method: "POST",
        // the server profiles finished sentences with the key; it stays on this machine until then
        headers: apiKey ? { "X-OpenRouter-Key": apiKey } : {},
        body: JSON.stringify({ text, caret, model, questions, words: rateWords, language }),
    });
    if (!response.ok) {
        throw new Error(`checker server: ${response.status}`);
    }
    return response.json();
}

/**
 * Sends the text being typed and the place of the caret to the checker server
 * a few times a second, whenever either has changed since they were last sent, or
 * what is asked about the sentences has, and returns the latest answer. The
 * answer may be about a slightly older text than the one given. It stays null
 * if the server is not running.
 *
 * `onUsage` is told of every request to the model that the server reports.
 */
export function useLiveCheck(
    text: string,
    caret: number | null,
    apiKey: string,
    model: string,
    questions: RequestQuestions,
    rateWords: boolean,
    language: string,
    onUsage: (usage: ProfileUsage) => void,
): LiveCheck | null {
    const [check, setCheck] = useState<LiveCheck | null>(null);
    // what is asked, as text, so that a change in it is easy to notice
    const asked = JSON.stringify([model, questions, rateWords, language]);
    const latest = useRef({ text, caret, asked });
    if (latest.current.text !== text || latest.current.caret !== caret || latest.current.asked !== asked) {
        latest.current = { text, caret, asked };
    }
    const profiling = useRef({ apiKey, model, questions, rateWords, language, onUsage });
    profiling.current = { apiKey, model, questions, rateWords, language, onUsage };

    useEffect(() => {
        let sent: { text: string; caret: number | null; asked: string } = { text: "", caret: null, asked: "" };
        // Requests to the model were still out at the last answer, so it is
        // worth asking again. Some may also be left from before this started,
        // such as from the chat shown before this one, so it asks once anyway.
        let awaiting = true;
        let stopped = false;
        const timer = setInterval(() => {
            const current = latest.current;
            // an empty box has nothing to say about, wherever the caret is
            const unchanged = current.text === sent.text
                && (current.text === "" || (current.caret === sent.caret && current.asked === sent.asked));
            if (unchanged && !awaiting) {
                return;
            }
            sent = current;
            awaiting = false;
            const { apiKey, model, questions, rateWords, language } = profiling.current;
            fetchCheck(current.text, current.caret, apiKey, model, questions, rateWords, language).then(
                (reply) => {
                    // The server reports a request only once, so it is counted
                    // even if the rest of this answer is no longer of use.
                    reply.usage.forEach(profiling.current.onUsage);
                    awaiting ||= reply.pending;
                    // an answer that arrives after something newer was sent is out of date
                    if (stopped || sent !== current) {
                        return;
                    }
                    setCheck({ text: current.text, sentences: reply.sentences, localModel: reply.local_model ?? null });
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
 * The sentence the caret is on, or was last on if the text box is no longer
 * in use; null if there is none.
 */
export function sentenceAtCaret(check: LiveCheck | null, caret: number | null): Sentence | null {
    if (!check || caret === null) {
        return null;
    }
    const sentences = check.sentences;
    // the one the server took the caret to be on, if it knew where the caret was
    const beingWritten = sentences.find((sentence) => !sentence.complete);
    if (beingWritten) {
        return beingWritten;
    }
    const upToCaret = sentences.filter((sentence) => sentence.start <= caret);
    return upToCaret[upToCaret.length - 1] ?? sentences[0] ?? null;
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

/** A stretch of the text, with what is to be shown on it. */
export interface MarkedPart {
    text: string;
    /** The spelling issue it is, if it is one. */
    issue: SpellingIssue | null;
    /** How right the word it is, or is part of, was rated, from 0 to 1; null if it was not rated. */
    value: number | null;
}

/** A stretch of the text that was rated, by where it is in the whole text. */
interface Rated {
    start: number;
    end: number;
    value: number;
}

/**
 * `text` from `from` to `to`, cut wherever a spelling issue or a rated word
 * starts or ends, in order.
 */
function markedRange(
    text: string,
    issues: SpellingIssue[],
    from: number,
    to: number,
    rated: Rated[] = [],
): MarkedPart[] {
    const within = <Range extends { start: number; end: number }>(ranges: Range[]) =>
        ranges.filter((range) => range.start >= from && range.end <= to && range.end > range.start);
    const shownIssues = within(issues);
    const shownRated = within(rated);
    const cuts = new Set([from, to]);
    for (const range of [...shownIssues, ...shownRated]) {
        cuts.add(range.start);
        cuts.add(range.end);
    }
    const places = [...cuts].sort((a, b) => a - b);
    const parts: MarkedPart[] = [];
    for (let index = 0; index + 1 < places.length; index++) {
        const [start, end] = [places[index], places[index + 1]];
        const covers = (range: { start: number; end: number }) => range.start <= start && range.end >= end;
        parts.push({
            text: text.slice(start, end),
            issue: shownIssues.find(covers) ?? null,
            value: shownRated.find(covers)?.value ?? null,
        });
    }
    return parts;
}

/** `text` cut into the stretches with and without a spelling issue, in order. */
export function markedParts(text: string, issues: SpellingIssue[]): MarkedPart[] {
    return markedRange(text, issues, 0, text.length);
}

/**
 * How far along a sentence is, which is what it is drawn by:
 * - "typing": the caret is on it
 * - "done": the caret has left it
 * - "checking": it is done, and questions about it, or the rating of its words, are out
 * - "checked": it is done, every question about it has been answered and its
 *   words, if they are rated, have been
 * - "failed": it is done, and a question about it could not be answered
 */
export type SentenceState = "typing" | "done" | "checking" | "checked" | "failed";

export function sentenceState(sentence: Sentence): SentenceState {
    if (!sentence.complete) {
        return "typing";
    }
    if (sentence.processed && !sentence.rating_words) {
        return "checked";
    }
    if (sentence.profiling || sentence.rating_words) {
        return "checking";
    }
    return sentence.profile_error ? "failed" : "done";
}

/**
 * How strongly to mark a word that was rated `value`, from 0 for a word that
 * is right to 1 for one that is wrong. Words that are nearly right are not
 * marked at all, so that a sentence without mistakes stays clean.
 */
export function doubt(value: number): number {
    const CLEAR_FROM = 0.85;
    return Math.min(1, Math.max(0, (CLEAR_FROM - value) / CLEAR_FROM));
}

/** A stretch of the text that is one sentence, or the space between two. */
export interface SentencePart {
    /** Null for what lies between sentences, and for text the checker has not seen yet. */
    sentence: Sentence | null;
    parts: MarkedPart[];
}

/**
 * `text` cut into its sentences and what lies between them, in order, each
 * cut further at the spelling issues to show.
 *
 * The check may be of an older version of the text, so a sentence is only
 * taken as one if it still reads the same in the same place.
 */
export function sentenceParts(text: string, check: LiveCheck | null, issues: SpellingIssue[]): SentencePart[] {
    const pieces: SentencePart[] = [];
    let position = 0;
    const between = (to: number) => {
        if (to > position) {
            pieces.push({ sentence: null, parts: markedRange(text, issues, position, to) });
        }
    };
    for (const sentence of check?.sentences ?? []) {
        if (sentence.start < position || text.slice(sentence.start, sentence.end) !== sentence.text) {
            continue;
        }
        between(sentence.start);
        // a word is rated by where it is in its sentence
        const rated = (sentence.words ?? []).map((word) => ({
            start: sentence.start + word.start,
            end: sentence.start + word.end,
            value: word.value,
        }));
        pieces.push({ sentence, parts: markedRange(text, issues, sentence.start, sentence.end, rated) });
        position = sentence.end;
    }
    between(text.length);
    return pieces;
}

/** `text` with the misspelled word replaced by one of its suggestions. */
export function applySuggestion(text: string, issue: SpellingIssue, suggestion: string): string {
    return text.slice(0, issue.start) + suggestion + text.slice(issue.end);
}
