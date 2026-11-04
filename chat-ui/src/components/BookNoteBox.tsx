// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { useEffect, useRef, useState } from "react";

import { useBack } from "../lib/back";
import type { BookNote, NoteBody, NoteKind } from "../lib/books";
import { ask } from "../lib/dialogs";
import { t } from "../lib/i18n";
import { loadPen, type PenChoice, savePen, type Stroke } from "../lib/ink";
import type { HandwrittenPage } from "../lib/texts";
import { InkPage, PenTools, type Tool } from "./HandwrittenPages";

interface Props {
    /** The text the note is on. */
    quote: string;
    /** The note as it is kept, or null for one being written for the first time. */
    note: BookNote | null;
    /** Keeps what the note says; the box is closed once it is kept. */
    onSave: (body: NoteBody) => Promise<void>;
    onDelete: () => Promise<void>;
    onClose: () => void;
}

/**
 * The page a note is written on by hand: as wide as a page of a text
 * written by hand, and half as high, which the server keeps it within.
 */
const NOTE_PAGE: HandwrittenPage = {
    id: "note",
    width: 1240,
    height: 620,
    ink: [],
    words: null,
    inkedAt: 0,
    readAt: null,
};

/**
 * The box a note on a book is written in, over the page: typed, or written
 * by hand with the pens of the texts written by hand. A note that is kept
 * opens in it again to be read, changed or removed.
 */
export function BookNoteBox({ quote, note, onSave, onDelete, onClose }: Props) {
    const [kind, setKind] = useState<NoteKind>(note?.kind ?? "typed");
    const [text, setText] = useState(note?.text ?? "");
    const [ink, setInk] = useState<Stroke[]>(note?.ink ?? []);
    const [choice, setChoice] = useState<PenChoice>(loadPen);
    const [tool, setTool] = useState<Tool>("write");
    // what each stroke, or rubbing of the eraser, undoes, the last last
    const [undo, setUndo] = useState<Stroke[][]>([]);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const typed = useRef<HTMLTextAreaElement>(null);

    useBack("cover", onClose);
    useEffect(() => savePen(choice), [choice]);
    useEffect(() => {
        if (kind === "typed") {
            typed.current?.focus();
        }
    }, [kind]);

    const empty = kind === "typed" ? text.trim() === "" : ink.length === 0;
    const unchanged = note !== null && note.kind === kind && note.text === text && note.ink === ink;

    async function run(action: () => Promise<void>) {
        setBusy(true);
        setError(null);
        try {
            await action();
        } catch (failed) {
            setError((failed as Error).message);
            setBusy(false);
        }
    }

    function save() {
        // only what the note is written in is kept
        void run(() => onSave({ kind, text: kind === "typed" ? text : "", ink: kind === "handwritten" ? ink : [] }));
    }

    function remove() {
        void ask(t("Remove this note?"), { confirm: t("Remove"), danger: true }).then((agreed) => {
            if (agreed) {
                void run(onDelete);
            }
        });
    }

    return (
        <div
            className="dialog-backdrop"
            onMouseDown={(event) => {
                if (event.target === event.currentTarget && (empty || unchanged)) {
                    onClose();
                }
            }}
        >
            <div
                className="dialog book-note-box"
                role="dialog"
                aria-modal="true"
                aria-label={t("Note")}
                onKeyDown={(event) => {
                    if (event.key === "Escape") {
                        onClose();
                    } else if (event.key === "Enter" && (event.ctrlKey || event.metaKey) && !empty) {
                        save();
                    }
                }}
            >
                <blockquote className="book-note-quote">{quote}</blockquote>
                <div className="switch" role="tablist" aria-label={t("How the note is written")}>
                    <button role="tab" aria-selected={kind === "typed"} onClick={() => setKind("typed")}>
                        {t("Typed")}
                    </button>
                    <button role="tab" aria-selected={kind === "handwritten"} onClick={() => setKind("handwritten")}>
                        {t("Handwritten")}
                    </button>
                </div>
                {kind === "typed"
                    ? (
                        <textarea
                            ref={typed}
                            className="book-note-text"
                            value={text}
                            rows={6}
                            placeholder={t("Write your note…")}
                            aria-label={t("Note")}
                            onChange={(event) => setText(event.target.value)}
                        />
                    )
                    : (
                        <>
                            <div className="ink-toolbar book-note-pens" role="toolbar" aria-label={t("Pen")}>
                                <PenTools
                                    choice={choice}
                                    tool={tool}
                                    canUndo={undo.length > 0}
                                    onChoice={setChoice}
                                    onTool={setTool}
                                    onUndo={() => {
                                        setInk(undo[undo.length - 1]);
                                        setUndo(undo.slice(0, -1));
                                    }}
                                />
                            </div>
                            <figure className="ink-page book-note-page">
                                <InkPage
                                    page={NOTE_PAGE}
                                    ink={ink}
                                    choice={choice}
                                    tool={tool}
                                    locked={false}
                                    turned={false}
                                    showWords={false}
                                    onWrite={(before, after) => {
                                        setUndo([...undo, before]);
                                        setInk(after);
                                    }}
                                />
                            </figure>
                        </>
                    )}
                {error && <p className="selection-error" role="alert">{error}</p>}
                <div className="dialog-buttons">
                    {note && (
                        <button className="danger book-note-remove" disabled={busy} onClick={remove}>
                            {t("Remove")}
                        </button>
                    )}
                    <button disabled={busy} onClick={onClose}>{note ? t("Close") : t("Cancel")}</button>
                    <button className="primary" disabled={busy || empty || unchanged} onClick={save}>
                        {t("Save")}
                    </button>
                </div>
            </div>
        </div>
    );
}
