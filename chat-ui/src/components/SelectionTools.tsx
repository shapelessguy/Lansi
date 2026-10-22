// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { useEffect, useRef, useState } from "react";
import type { ModelChoice } from "../lib/models";

import { type Message, t } from "../lib/i18n";
import { readWhere, type Where, WHERE_ATTRIBUTE } from "../lib/logs";
import { markedAncestor, regionOf, selectableShadowRoots, selectedRange } from "../lib/selection";
import { type BookSelection, bookSelection } from "../lib/speaking";
import type { BackgroundTask } from "../lib/tasks";
import {
    type Anchor,
    anchorFor,
    type Asking,
    type Picked,
    takeWords,
    textAround,
    translate,
    type Translated,
    usageEntry,
} from "../lib/translate";
import type { UsageEntry } from "../lib/usage";

interface Props {
    /** Who translates, and into which language. */
    translating: Asking;
    /** Who looks into the words that are new to the vocabulary, and the model that sorts them into categories. */
    describing: Asking;
    decisionModel: ModelChoice;
    onUsage: (entry: UsageEntry) => void;
    /** Told the selection and its translation when a chat about them is asked for. */
    onChat: (translated: Translated) => void;
    /** Told the task the server started to take words into the vocabulary. */
    onTask: (task: BackgroundTask) => void;
    /** Told when something was logged, such as a translation. */
    onLogged: () => void;
    /** Told what was selected of the book in the reader when it is to be read aloud. */
    onPlay: (selection: BookSelection) => void;
}

/** How wide the buttons and the box they open are at most, and the room each needs above a selection, in pixels. */
const BAR = { width: 360, room: 48 };
const BOX = { width: 380, room: 150 };

/** What can be done with a selection, and what each is called on its button. */
const TASKS = { translate: "Translate", words: "Add to vocabulary" } as const satisfies Record<string, Message>;
type Task = keyof typeof TASKS;

/** What was selected, and where on the window. */
interface Found {
    picked: Picked;
    rect: DOMRect;
    /** What it is of the book in the reader, if it was selected there. */
    book: BookSelection | null;
    /** Where it was selected, as what is done with it is logged. */
    where: Where | null;
}

type Box =
    & { found: Found; task: Task }
    & (
        | { status: "loading" }
        | { status: "error"; message: string }
        | { status: "translated"; translated: Translated }
    );

/** What is selected where text can be translated, if anything is, in the page or in the interface of an exercise. */
function findSelection(): Found | null {
    const selection = window.getSelection();
    const range = selection ? selectedRange(selection, selectableShadowRoots()) : null;
    if (!selection || !range) {
        return null;
    }
    const found = regionOf(range.commonAncestorContainer);
    if (!found) {
        return null;
    }
    const { region, root, book } = found;
    // the selection of the document has only the host of a shadow root
    const text = root === region ? selection.toString() : range.toString();
    return {
        picked: textAround(range, root, text),
        rect: range.getBoundingClientRect(),
        book: book && region instanceof Element ? bookSelection(range, region) : null,
        where: readWhere(markedAncestor(range.commonAncestorContainer, WHERE_ATTRIBUTE)?.value),
    };
}

function placed(anchor: Anchor) {
    return {
        left: anchor.left,
        top: anchor.top,
        transform: anchor.above ? "translate(-50%, -100%)" : "translateX(-50%)",
    };
}

/**
 * The buttons that come up over text that is selected, and the box with
 * the translation that the first of them opens. The second has the words
 * taken into the vocabulary, which is done in the background and shows
 * here only if it cannot be started. What is translated is taken into the
 * vocabulary as well.
 */
export function SelectionTools(
    { translating, describing, decisionModel, onUsage, onChat, onTask, onLogged, onPlay }: Props,
) {
    // what the buttons are shown for, until something is done with it
    const [found, setFound] = useState<Found | null>(null);
    const [box, setBox] = useState<Box | null>(null);
    const tools = useRef<HTMLDivElement>(null);
    const request = useRef<AbortController | null>(null);

    useEffect(() => {
        // The selection is as it will be only after the click that made or
        // dropped it is over.
        let timer: number | undefined;
        function look(event: Event) {
            // a click on the player or on the sign of the tasks is not about the selection
            const own = (event.target instanceof Node && tools.current?.contains(event.target))
                || (event.target instanceof Element && event.target.closest(".speech-player, .task-sign"));
            // the key that put the buttons away does not bring them back as it is let go
            if (own || (event instanceof KeyboardEvent && event.key === "Escape")) {
                return;
            }
            clearTimeout(timer);
            timer = window.setTimeout(() => setFound(findSelection()));
        }
        function onMouseDown(event: MouseEvent) {
            if (!(event.target instanceof Node && tools.current?.contains(event.target))) {
                close();
            }
        }
        function onKeyDown(event: KeyboardEvent) {
            if (event.key === "Escape") {
                close();
                setFound(null);
            }
        }
        // the buttons would be left behind by text that moves from under them
        const drop = () => setFound(null);
        document.addEventListener("mouseup", look);
        document.addEventListener("keyup", look);
        document.addEventListener("mousedown", onMouseDown);
        document.addEventListener("keydown", onKeyDown);
        document.addEventListener("scroll", drop, true);
        document.addEventListener("wheel", drop, true);
        window.addEventListener("resize", drop);
        return () => {
            clearTimeout(timer);
            document.removeEventListener("mouseup", look);
            document.removeEventListener("keyup", look);
            document.removeEventListener("mousedown", onMouseDown);
            document.removeEventListener("keydown", onKeyDown);
            document.removeEventListener("scroll", drop, true);
            document.removeEventListener("wheel", drop, true);
            window.removeEventListener("resize", drop);
        };
    }, []);

    useEffect(() => () => request.current?.abort(), []);

    function close() {
        request.current?.abort();
        request.current = null;
        setBox(null);
    }

    function start(task: Task, of: Found) {
        request.current?.abort();
        const controller = new AbortController();
        request.current = controller;
        const show = (result: object) => {
            if (!controller.signal.aborted) {
                setBox({ found: of, task, ...result } as Box);
            }
        };
        const count = (usage: Parameters<typeof usageEntry>[0][]) =>
            usage.forEach((used) => onUsage(usageEntry(used, Date.now())));
        const failed = (error: Error) => show({ status: "error", message: error.message });
        setFound(null);
        if (task === "translate") {
            show({ status: "loading" });
            translate(of.picked, translating, controller.signal, of.where).then(({ usage, ...translated }) => {
                count(usage);
                show({ status: "translated", translated });
                if (translated.log) {
                    onLogged();
                }
            }, failed);
            // the words go into the vocabulary whatever becomes of the box, unless they cannot
            takeWords(of.picked, describing, decisionModel).then(
                onTask,
                (error) => console.warn("the words translated were not taken into the vocabulary:", error),
            );
        } else {
            takeWords(of.picked, describing, decisionModel, controller.signal).then(onTask, failed);
        }
    }

    return (
        <div ref={tools}>
            {found && !box && (
                <div
                    className="selection-bar"
                    role="toolbar"
                    aria-label={t("Selected text")}
                    style={placed(anchorFor(found.rect, window.innerWidth, BAR.width, BAR.room))}
                    // a click on a button must not drop the selection the button is for
                    onMouseDown={(event) => event.preventDefault()}
                >
                    {(Object.keys(TASKS) as Task[]).map((task) => (
                        <button key={task} onClick={() => start(task, found)}>{t(TASKS[task])}</button>
                    ))}
                    {found.book && (
                        <button
                            onClick={() => {
                                onPlay(found.book!);
                                setFound(null);
                            }}
                            title={t("Read the selected sentences aloud")}
                        >
                            ▶ {t("Play")}
                        </button>
                    )}
                </div>
            )}
            {box && (
                <div
                    className="selection-box"
                    role="dialog"
                    aria-label={t(TASKS[box.task])}
                    style={placed(anchorFor(box.found.rect, window.innerWidth, BOX.width, BOX.room))}
                >
                    <p className="selection-source">{box.found.picked.selection.trim()}</p>
                    {box.status === "loading" && <p className="typing">{t("Translating…")}</p>}
                    {box.status === "error" && (
                        <>
                            <p className="selection-error" role="alert">{box.message}</p>
                            <div className="selection-actions">
                                <button onClick={() => start(box.task, box.found)}>{t("Try again")}</button>
                                <button onClick={close}>{t("Close")}</button>
                            </div>
                        </>
                    )}
                    {box.status === "translated" && (
                        <>
                            <p className="selection-translation">{box.translated.translation}</p>
                            <div className="selection-actions">
                                <button
                                    className="primary"
                                    onClick={() => {
                                        onChat(box.translated);
                                        close();
                                    }}
                                    title={t("Ask about this in a chat at the side")}
                                >
                                    {t("Chat")}
                                </button>
                                <button onClick={close}>{t("Close")}</button>
                            </div>
                        </>
                    )}
                </div>
            )}
        </div>
    );
}
