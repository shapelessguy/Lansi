// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { Fragment, useEffect, useRef, useState } from "react";

import { locale, plural, t } from "../lib/i18n";
import type { WordLists } from "../lib/sets";
import type { Settings } from "../lib/settings";
import { blocksOf, fetchText, type Inline, saveText, type Text } from "../lib/texts";
import type { UsageEntry } from "../lib/usage";
import { CheckedTextarea } from "./CheckedTextarea";

interface Props {
    id: string;
    language: string;
    /** What the sentences are checked with, as in the chat, and what changes it. */
    settings: Settings;
    onSettingsChange: (next: Settings) => void;
    /** What the keywords for words in the questions stand for. */
    words: WordLists;
    onUsage: (entry: UsageEntry) => void;
    /** Where the checks of the sentence under the caret are shown, while the panel is open. */
    checksSlot: HTMLElement | null;
    onCloseChecks: () => void;
    onEditQuestions: () => void;
    /** The correction made of the text, once it is corrected. */
    correctionId: string | null;
    /** Told when the text was kept, so that the list shows it as it is. */
    onSaved: () => void;
}

/** How long after the last change the text is kept, in milliseconds. */
const SAVE_AFTER_MS = 700;

/**
 * A text of the learner's, to be written in, with its spelling checked and
 * its sentences profiled as the chat's are, the checks of the sentence under
 * the caret in the panel on the right. It is kept as it is written. Once it is corrected it is
 * locked, and shown as it was; a correction is shown with what was wrong
 * struck through and what is right beside it.
 */
export function TextEditor(
    {
        id,
        language,
        settings,
        words,
        onSettingsChange,
        onUsage,
        checksSlot,
        onCloseChecks,
        onEditQuestions,
        correctionId,
        onSaved,
    }: Props,
) {
    const [text, setText] = useState<Text | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [state, setState] = useState<"saved" | "saving" | "changed">("saved");
    const timer = useRef<number>();
    const latest = useRef({ title: "", content: "" });
    // what the text came to once it was corrected, which is shown in its place
    const [correction, setCorrection] = useState<string | null>(null);
    useEffect(() => {
        setCorrection(null);
        if (correctionId) {
            fetchText(correctionId).then((found) => setCorrection(found.content), () => undefined);
        }
    }, [correctionId]);

    useEffect(() => {
        setText(null);
        setError(null);
        fetchText(id).then(
            (found) => {
                latest.current = { title: found.title, content: found.content ?? "" };
                setText(found);
            },
            (failed: Error) => setError(failed.message),
        );
        // what was changed and not kept yet is kept when another text is opened
        return () => {
            if (timer.current !== undefined) {
                window.clearTimeout(timer.current);
                saveText(id, latest.current.title, latest.current.content, language).then(
                    onSaved,
                    // such as a text that was corrected meanwhile, and is not changed
                    () => undefined,
                );
            }
        };
        // a text is loaded once, when it is opened
    }, [id]);

    function change(title: string, content: string) {
        if (!text) {
            return;
        }
        latest.current = { title, content };
        setText({ ...text, title, content });
        setState("changed");
        window.clearTimeout(timer.current);
        timer.current = window.setTimeout(() => {
            timer.current = undefined;
            setState("saving");
            saveText(id, title, content, language).then(
                () => {
                    setState("saved");
                    onSaved();
                },
                (failed: Error) => {
                    setState("changed");
                    setError(failed.message);
                },
            );
        }, SAVE_AFTER_MS);
    }

    if (error && !text) {
        return <p className="practice-note error">{error}</p>;
    }
    if (!text) {
        return <p className="practice-note">{t("Loading…")}</p>;
    }
    if (text.kind === "correction") {
        return (
            <section className="text-editor">
                <Correction markdown={text.content ?? ""} />
            </section>
        );
    }
    const locked = text.lockedAt !== null;
    if (locked && correction !== null) {
        // corrected, it is shown with its corrections and their comments worked in
        return (
            <section className="text-editor">
                <h2 className="text-corrected-title">{text.title || t("Untitled")}</h2>
                <p className="practice-note">
                    {t("Corrected on {day}", {
                        day: new Date((text.lockedAt as number) * 1000).toLocaleDateString(locale()),
                    })}
                </p>
                <Correction markdown={correction} />
            </section>
        );
    }
    return (
        <section className="text-editor">
            <input
                className="text-title-input"
                value={text.title}
                placeholder={t("Title")}
                aria-label={t("Title")}
                readOnly={locked}
                onChange={(event) => change(event.target.value, text.content ?? "")}
            />
            {locked && (
                <p className="practice-note">
                    {t("Corrected on {day}: it stays as it was handed in.", {
                        day: new Date((text.lockedAt as number) * 1000).toLocaleDateString(locale()),
                    })}
                </p>
            )}
            {/* made only once the text is there, as the box is registered for its sentences when it is made */}
            <CheckedTextarea
                className="text-body"
                value={text.content ?? ""}
                placeholder={t("Write here")}
                aria-label={t("Text")}
                readOnly={locked}
                onChange={(content) => change(text.title, content)}
                settings={settings}
                onSettingsChange={onSettingsChange}
                words={words}
                onUsage={onUsage}
                // counted under the text, as what the chat asks is under the chat
                usageId={`text:${id}`}
                checksSlot={checksSlot}
                onCloseChecks={onCloseChecks}
                onEditQuestions={onEditQuestions}
            />
            <div className="text-status">
                {plural((text.content ?? "").split(/\s+/).filter(Boolean).length, "{count} word", "{count} words")}
                {!locked
                    && ` · ${state === "saved" ? t("Saved") : state === "saving" ? t("Saving…") : t("Not saved yet")}`}
                {error && <span className="error">· {error}</span>}
            </div>
        </section>
    );
}

/** A text with its corrections and their comments worked in, as the exercise that corrected it wrote it. */
function Correction({ markdown }: { markdown: string }) {
    return (
        <div className="text-correction">
            {blocksOf(markdown).map((block, number) =>
                block.kind === "heading"
                    ? block.level === 1
                        ? <h2 key={number}>{pieces(block.inline)}</h2>
                        : <h3 key={number}>{pieces(block.inline)}</h3>
                    : block.kind === "item"
                    ? (
                        <p key={number} className="text-correction-item">
                            <span className="text-correction-number">{block.number}.</span> {pieces(block.inline)}
                        </p>
                    )
                    : (
                        <p key={number} className="text-correction-paragraph">
                            {block.lines.map((line, place) => (
                                <Fragment key={place}>
                                    {place > 0 && <br />}
                                    {pieces(line)}
                                </Fragment>
                            ))}
                        </p>
                    )
            )}
        </div>
    );
}

function pieces(inline: Inline[]) {
    return inline.map((piece, place) =>
        piece.kind === "wrong"
            ? <del key={place}>{piece.text}</del>
            : piece.kind === "right"
            ? <ins key={place}>{piece.text}</ins>
            : piece.kind === "comment"
            ? <span key={place} className="text-comment">{piece.text}</span>
            : <Fragment key={place}>{piece.text}</Fragment>
    );
}
