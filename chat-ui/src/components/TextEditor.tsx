// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { useEffect, useMemo, useRef, useState } from "react";

import { correctionOf, type CorrectionRecord, correctionTask, correctText, pageCorrections } from "../lib/corrections";
import { locale, t } from "../lib/i18n";
import type { Stroke } from "../lib/ink";
import { correctionArea, marksOf } from "../lib/marks";
import type { WordLists } from "../lib/sets";
import type { Settings } from "../lib/settings";
import { type BackgroundTask, fetchTasks } from "../lib/tasks";
import { fetchText, saveText, type Text } from "../lib/texts";
import type { UsageEntry } from "../lib/usage";
import { CheckedTextarea } from "./CheckedTextarea";
import { CorrectedText, CorrectionList, said } from "./CorrectedText";
import { HandwrittenPages, type HandwrittenPagesHandle, type PageNote } from "./HandwrittenPages";
import { PlaceSentenceChecks } from "./SentenceChecks";

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
    /** Opens another text, such as the text a correction is of. */
    onOpenText: (id: string) => void;
    /** Told when the text was corrected, so that its correction is listed. */
    onCorrected: () => void;
    /** Told of the correction as it is started, so that it is shown among the tasks. */
    onTask: (task: BackgroundTask) => void;
    /** Deletes the correction of the text, which can then be changed, and corrected, again. */
    onDeleteCorrection: (correction: Text) => void;
}

/** How often whether the text is still being corrected is asked, in milliseconds. */
const CORRECTION_POLL_MS = 3000;

/** How long after the last change the text is kept, in milliseconds. */
const SAVE_AFTER_MS = 700;

/**
 * A text of the learner's, to be written in, with its spelling checked and
 * its sentences profiled as the chat's are, the checks of the sentence under
 * the caret in the panel on the right. It is kept as it is written. It is
 * corrected when the learner asks, its correction kept as a text of its own;
 * it is then locked, and shown with its correction under it: the
 * corrections worked into it, or drawn on its pages, and listed. A
 * correction whose text was deleted is shown on its own.
 *
 * A text may instead be written by hand, in pages, as it is started: it
 * then says what its pages were read to say, below them, and is checked as
 * a typed one is, but not typed in.
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
        onOpenText,
        onCorrected,
        onDeleteCorrection,
        onTask,
    }: Props,
) {
    const [text, setText] = useState<Text | null>(null);
    const [error, setError] = useState<string | null>(null);

    const timer = useRef<number>();
    const latest = useRef({ title: "", content: "" });
    const pagesRef = useRef<HandwrittenPagesHandle>(null);
    // whether it is being corrected, on the server, which goes on though the app is closed
    const [correcting, setCorrecting] = useState(false);
    // the correction of the text, once it is corrected, shown under it
    const [correction, setCorrection] = useState<Text | null>(null);
    useEffect(() => {
        setCorrection(null);
        if (correctionId) {
            fetchText(correctionId).then(setCorrection, () => undefined);
        }
    }, [correctionId]);
    const record = useMemo(() => correction ? correctionOf(correction.content) : null, [correction]);
    const marks = useMemo(() => text?.handwritten && record ? pageMarks(text, record) : undefined, [text, record]);
    const notes = useMemo(() => text?.handwritten && record ? pageNotes(text, record) : undefined, [text, record]);

    // a correction started before, such as before the app was closed, is waited for again
    useEffect(() => {
        let gone = false;
        setCorrecting(false);
        fetchTasks().then(
            (tasks) => !gone && setCorrecting(correctionTask(tasks, id)?.state === "running"),
            () => undefined,
        );
        return () => {
            gone = true;
        };
    }, [id]);

    // and once it is done, its correction is opened, or why it failed said
    useEffect(() => {
        if (!correcting) {
            return;
        }
        const timer = window.setInterval(() => {
            fetchTasks().then((tasks) => {
                const task = correctionTask(tasks, id);
                if (task?.state === "running") {
                    return;
                }
                setCorrecting(false);
                if (task?.state === "failed") {
                    setError(task.error);
                } else {
                    // done, or gone, as the server was started again meanwhile
                    onCorrected();
                }
            }, () => undefined);
        }, CORRECTION_POLL_MS);
        return () => window.clearInterval(timer);
    }, [correcting, id]);

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
        window.clearTimeout(timer.current);
        timer.current = window.setTimeout(() => {
            timer.current = undefined;
            saveText(id, title, content, language).then(
                () => {
                    onSaved();
                },
                (failed: Error) => {
                    setError(failed.message);
                },
            );
        }, SAVE_AFTER_MS);
    }

    /** What the text came to on the server, with the title that may not be kept yet. */
    function changed(found: Text) {
        latest.current = { ...latest.current, content: found.content ?? "" };
        setText((current) => ({ ...found, title: current?.title ?? found.title }));
    }

    if (error && !text) {
        return <p className="practice-note error">{error}</p>;
    }
    if (!text) {
        return <p className="practice-note">{t("Loading…")}</p>;
    }
    if (text.kind === "correction") {
        return <CorrectionView correction={text} settings={settings} onOpenText={onOpenText} />;
    }
    const locked = text.lockedAt !== null;
    const handwritten = text.handwritten;
    const pages = text.pages ?? [];
    // what keeps it from being corrected, if anything
    const unread = pages.some((page) =>
        page.ink.length > 0 && (page.words === null || page.inkedAt > (page.readAt ?? 0))
    );
    const blocked = !settings.apiKey
        ? t("Set your OpenRouter key in Settings to correct the text.")
        : handwritten
        ? !pages.some((page) => page.ink.length > 0)
            ? t("Write something first.")
            : unread && !settings.visionKey
            ? t("Set your Google Cloud Vision key in Settings, under Models, to read the pages.")
            : null
        : !(text.content ?? "").trim()
        ? t("Write something first.")
        : null;

    async function correct() {
        setError(null);
        setCorrecting(true);
        try {
            if (handwritten) {
                // what is written on the pages is read first, as it is what is corrected
                if (!(await pagesRef.current?.readUnread())) {
                    setCorrecting(false);
                    return;
                }
            } else if (timer.current !== undefined) {
                // and what is typed is kept first
                window.clearTimeout(timer.current);
                timer.current = undefined;
                await saveText(id, latest.current.title, latest.current.content, language);
            }
            onTask(await correctText(id, settings));
        } catch (failed) {
            setError((failed as Error).message);
            setCorrecting(false);
        }
    }

    return (
        <section className="text-editor">
            <div className="text-header">
                <input
                    className="text-title-input"
                    value={text.title}
                    placeholder={t("Title")}
                    aria-label={t("Title")}
                    readOnly={locked}
                    onChange={(event) => change(event.target.value, text.content ?? "")}
                />
                {!handwritten && !locked && (
                    <PlaceSentenceChecks place="texts" settings={settings} onChangeSettings={onSettingsChange} />
                )}
                {!locked && (
                    <button
                        type="button"
                        className="text-correct"
                        disabled={correcting || blocked !== null}
                        title={blocked
                            ?? t(
                                "Correct this text: each mistake is marked, and the correction kept as a text of its own; the text is then locked.",
                            )}
                        onClick={() => void correct()}
                    >
                        {correcting && <span className="spinner" aria-hidden="true" />}
                        {correcting ? t("Correcting…") : t("Correct")}
                    </button>
                )}
            </div>
            {locked && (
                <p className="practice-note">
                    {t("Corrected on {day}: it stays as it was handed in.", {
                        day: new Date((text.lockedAt as number) * 1000).toLocaleDateString(locale()),
                    })}
                    {correction && (
                        <>
                            {" "}
                            <button
                                type="button"
                                className="link-button"
                                title={t("Delete the correction, so that the text can be changed and corrected again")}
                                onClick={() => onDeleteCorrection(correction)}
                            >
                                {t("Delete the correction")}
                            </button>
                        </>
                    )}
                </p>
            )}
            {handwritten && (
                <HandwrittenPages
                    ref={pagesRef}
                    textId={id}
                    pages={text.pages ?? []}
                    locked={locked}
                    visionKey={settings.visionKey}
                    onText={(found) => {
                        changed(found);
                        onSaved();
                    }}
                    onError={setError}
                    marks={marks}
                    notes={notes}
                />
            )}
            {error && <p className="practice-note error">{error}</p>}
            {!handwritten && record && <CorrectedText content={text.content ?? ""} record={record} />}
            {!handwritten && !record && (
                <>
                    {/* made only once the text is there, as the box is registered for its sentences when it is made */}
                    <CheckedTextarea
                        className="text-body"
                        place="texts"
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
                </>
            )}
            {correction && !record && <p className="practice-note error">{t("This correction cannot be read.")}</p>}
            {record && <CorrectionList record={record} />}
        </section>
    );
}

/**
 * A correction, a text of its own: the text it is of with its corrections
 * worked in, if it was typed, or drawn on its pages, if it was written by
 * hand, and the corrections listed, with what the text most needs.
 */
function CorrectionView(
    { correction, settings, onOpenText }: {
        correction: Text;
        settings: Settings;
        onOpenText: (id: string) => void;
    },
) {
    const record = useMemo(() => correctionOf(correction.content), [correction.content]);
    // the text it is of, as it was when it was corrected, which it is shown on
    const [original, setOriginal] = useState<Text | null | "gone">(null);
    useEffect(() => {
        setOriginal(null);
        if (correction.corrects) {
            fetchText(correction.corrects).then(setOriginal, () => setOriginal("gone"));
        } else {
            setOriginal("gone");
        }
    }, [correction.corrects]);
    const marks = useMemo(() => original && original !== "gone" && record ? pageMarks(original, record) : {}, [
        original,
        record,
    ]);

    return (
        <section className="text-editor">
            <h2 className="text-corrected-title">{correction.title || t("Untitled")}</h2>
            <p className="practice-note">
                {t("Corrected on {day}", {
                    day: new Date(correction.createdAt * 1000).toLocaleDateString(locale()),
                })}
                {correction.corrects && original !== "gone" && (
                    <>
                        {" "}
                        <button
                            type="button"
                            className="link-button"
                            onClick={() => onOpenText(correction.corrects as string)}
                        >
                            {t("Open the text as it was written")}
                        </button>
                    </>
                )}
            </p>
            {!record && <p className="practice-note error">{t("This correction cannot be read.")}</p>}
            {record && original === "gone" && (
                <p className="practice-note">{t("The text this corrects was deleted.")}</p>
            )}
            {record && original && original !== "gone" && (
                original.handwritten
                    ? (
                        <HandwrittenPages
                            textId={original.id}
                            pages={original.pages ?? []}
                            locked
                            visionKey={settings.visionKey}
                            onText={() => undefined}
                            onError={() => undefined}
                            marks={marks}
                        />
                    )
                    : <CorrectedText content={original.content ?? ""} record={record} />
            )}
            {record && <CorrectionList record={record} />}
        </section>
    );
}

/** What each correction of a text written by hand says, on the words of its page it is about, by the id of the page. */
function pageNotes(text: Text, record: CorrectionRecord): Record<string, PageNote[]> {
    const notes: Record<string, PageNote[]> = {};
    let offset = 0;
    for (const page of text.pages ?? []) {
        const words = page.words ?? [];
        notes[page.id] = record.corrections.flatMap((correction) => {
            // said with the ids of the whole text, and placed with those of the page
            const [placed] = pageCorrections([correction], offset, words.length);
            const note = placed && said(correction, record.words);
            const boxes = placed ? correctionArea(placed, words) : [];
            return note && boxes.length > 0 ? [{ boxes, note, kind: correction.type }] : [];
        });
        offset += words.length;
    }
    return notes;
}

/** The marks of the corrections of a text written by hand, drawn on each of its pages, by its id. */
function pageMarks(text: Text, record: CorrectionRecord): Record<string, Stroke[]> {
    const marks: Record<string, Stroke[]> = {};
    let offset = 0;
    for (const page of text.pages ?? []) {
        const words = page.words ?? [];
        marks[page.id] = marksOf(pageCorrections(record.corrections, offset, words.length), words, page.ink);
        offset += words.length;
    }
    return marks;
}
