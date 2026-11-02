// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { Fragment, type ReactNode } from "react";

import { changedLetters, type Correction, type CorrectionRecord, spanOf, tokensOf } from "../lib/corrections";
import { t } from "../lib/i18n";

/** The corrections that are shown to the learner, as a misreading of the page is not theirs, by their numbers from 1. */
function numbered(corrections: Correction[]): Map<Correction, number> {
    const shown = corrections.filter((correction) => correction.type !== "misread");
    return new Map(shown.map((correction, index) => [correction, index + 1]));
}

/** A word written as another, with only the letters that are wrong marked, if they are few. */
function wordChanged(was: string, text: string): ReactNode {
    const changed = !/\s/.test(text) && !/\s/.test(was) ? changedLetters(was, text) : null;
    if (!changed) {
        return (
            <>
                <del>{was}</del>
                <ins>{text}</ins>
            </>
        );
    }
    const [old, next] = [[...was.normalize("NFC")], [...text.normalize("NFC")]];
    const wrong = old.slice(changed.start, old.length - changed.end).join("");
    const right = next.slice(changed.start, next.length - changed.end).join("");
    return (
        <>
            {old.slice(0, changed.start).join("")}
            {wrong && <del>{wrong}</del>}
            {right && <ins>{right}</ins>}
            {old.slice(old.length - changed.end).join("")}
        </>
    );
}

/**
 * A typed text with its corrections worked into it, as it was written,
 * each numbered as it is in the list of them: what is wrong struck out,
 * what is right beside it, only the letters that changed where only a few
 * did, words that are missing or moved where they go, and what is only
 * remarked on marked.
 */
export function CorrectedText({ content, record }: { content: string; record: CorrectionRecord }) {
    const tokens = tokensOf(content);
    const numbers = numbered(record.corrections);
    // what each word starts, and what goes after each, -1 for before the first
    const starting = new Map<number, Correction>();
    const after = new Map<number, ReactNode[]>();
    const put = (at: number, node: ReactNode) => after.set(at, [...(after.get(at) ?? []), node]);
    for (const correction of record.corrections) {
        const span = spanOf(correction);
        if (span && span[0] < tokens.length && span[1] < tokens.length) {
            starting.set(span[0], correction);
        }
        const number = numbers.get(correction);
        if (correction.type === "insert") {
            put(
                correction.after_id,
                <ins key={`i${number}`} className="corrected-added">
                    {correction.text}
                    <sup>{number}</sup>
                </ins>,
            );
        }
        if (correction.type === "move" && span) {
            put(
                correction.after_id,
                <ins key={`m${number}`} className="corrected-moved">
                    {tokens.slice(span[0], span[1] + 1).map((token) => token.text).join(" ")}
                    <sup>{number}</sup>
                </ins>,
            );
        }
    }

    const parts: ReactNode[] = [];
    const added = (at: number) => after.get(at)?.flatMap((node) => [" ", node]) ?? [];
    parts.push(...(after.get(-1)?.flatMap((node) => [node, " "]) ?? []));
    let at = 0;
    let from = tokens.length ? tokens[0].start : content.length;
    parts.push(content.slice(0, from));
    while (at < tokens.length) {
        const correction = starting.get(at);
        const span = correction ? spanOf(correction) : null;
        const last = span ? span[1] : at;
        const was = content.slice(tokens[at].start, tokens[last].end);
        const number = correction ? numbers.get(correction) : undefined;
        const mark = number ? <sup>{number}</sup> : null;
        let shown: ReactNode = was;
        switch (correction?.type) {
            case "replace":
                shown = wordChanged(was, correction.text);
                break;
            case "join":
            case "split":
                shown = (
                    <>
                        <del>{was}</del>
                        <ins>{correction.text}</ins>
                    </>
                );
                break;
            case "erase":
            case "move":
                shown = <del className={correction.type === "move" ? "corrected-moved" : undefined}>{was}</del>;
                break;
            case "suggest":
                shown = (
                    <>
                        <span className="corrected-suggested">{was}</span>
                        <ins className="corrected-suggestion">{correction.text}</ins>
                    </>
                );
                break;
            case "comment":
                shown = <mark className="corrected-comment">{was}</mark>;
                break;
            case "praise":
                shown = <span className="corrected-praised">{was}</span>;
                break;
            case "misread":
                shown = correction.text;
                break;
            case "illegible":
                shown = <span className="corrected-illegible">{was}</span>;
                break;
        }
        parts.push(
            <span key={at} className={correction ? `corrected ${correction.type}` : undefined}>
                {shown}
                {mark}
            </span>,
            ...added(last),
        );
        at = last + 1;
        from = tokens[last].end;
        // the spaces and the line breaks between the words, as they are
        parts.push(content.slice(from, at < tokens.length ? tokens[at].start : content.length));
    }
    return <div className="corrected-text">{parts.map((part, index) => <Fragment key={index}>{part}</Fragment>)}</div>;
}

/** What a correction says, as it is listed: the words it is about, what they are to be, and why. */
export function said(correction: Correction, words: string[]): ReactNode {
    const span = spanOf(correction);
    const was = span ? words.slice(span[0], span[1] + 1).join(" ") : "";
    const why = "explanation" in correction && correction.explanation ? correction.explanation : "";
    switch (correction.type) {
        case "insert":
            return (
                <>
                    <ins>{correction.text}</ins> {why}
                </>
            );
        case "erase":
            return (
                <>
                    <del>{was}</del> {why}
                </>
            );
        case "move":
            return (
                <>
                    <del>{was}</del> → {correction.after_id < 0
                        ? t("to the start")
                        : t("after «{word}»", { word: words[correction.after_id] ?? "" })} {why}
                </>
            );
        case "comment":
        case "praise":
            return (
                <>
                    «{was}»: {correction.text}
                </>
            );
        case "illegible":
            return (
                <>
                    «{was}»: {t("could not be read")}
                </>
            );
        case "misread":
            return null;
        default:
            return (
                <>
                    <del>{was}</del> → <ins>{correction.text}</ins> {why}
                </>
            );
    }
}

/** The corrections of a text, numbered, each with what it is about and why, and what the text most needs. */
export function CorrectionList({ record }: { record: CorrectionRecord }) {
    const numbers = numbered(record.corrections);
    return (
        <div className="correction-list">
            {record.summary && <p className="correction-summary">{record.summary}</p>}
            {numbers.size === 0
                ? <p className="practice-note">{t("No mistakes.")}</p>
                : (
                    <ol>
                        {[...numbers].map(([correction, number]) => (
                            <li key={number} value={number} className={`correction-item ${correction.type}`}>
                                {said(correction, record.words)}
                            </li>
                        ))}
                    </ol>
                )}
        </div>
    );
}
