// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import {
    createContext,
    type CSSProperties,
    type ReactNode,
    type RefObject,
    useCallback,
    useContext,
    useEffect,
    useRef,
    useState,
} from "react";
import { createPortal } from "react-dom";

import {
    applySuggestion,
    doubt,
    type LiveCheck,
    type MarkedPart,
    type ProfileUsage,
    sentenceParts,
    type SentenceState,
    sentenceState,
    type SpellingIssue,
    spellingIssues,
} from "../lib/checker";
import { askedOf, checkedBox, checkText, mirrorStyle, type Profiling, type Sent, worthSending } from "../lib/writing";

/** What a panel that registered a text box of its own is told, and asked. */
interface Owner {
    profiling: () => Profiling;
    onUsage: (usage: ProfileUsage) => void;
    onCheck: (checked: Checked) => void;
}

/** What is known about a text box a panel registered. */
export interface Checked {
    check: LiveCheck | null;
    /** Where the caret is in the box, or was last if the box is no longer in use. */
    lastCaret: number | null;
}

/** A text box that is checked, with the copy of its text behind it that carries the underlines. */
interface Watch {
    /** Tells the copies apart, as React draws them. */
    id: number;
    element: HTMLTextAreaElement;
    mirror: HTMLDivElement;
    owner: Owner | null;
    /** The background and position the box had, which are changed to lay the copy behind it. */
    restore: { background: string; position: string };
    background: string;
    sent: Sent;
    awaiting: boolean;
    check: LiveCheck | null;
    text: string;
    caret: number | null;
    lastCaret: number | null;
    /** Where the box was last, to tell when the copy must follow it. */
    place: string;
    detach: () => void;
}

/** How often the text boxes are looked at for changes, and how many of those go by between checks, in milliseconds. */
const LOOK_MS = 100;
const LOOKS_PER_CHECK = 3;

const WritingContext = createContext<((element: HTMLTextAreaElement, owner: Owner) => () => void) | null>(null);

/**
 * Has the spelling of the text box that `box` is checked as every text box
 * where writing is marked is, and, with `profiling`, its sentences profiled
 * too. Returns what is known about it, for a panel that shows more of it.
 */
export function useWritingCheck(
    box: RefObject<HTMLTextAreaElement>,
    profiling: Profiling,
    onUsage: (usage: ProfileUsage) => void,
): Checked {
    const register = useContext(WritingContext);
    const [checked, setChecked] = useState<Checked>({ check: null, lastCaret: null });
    const latest = useRef({ profiling, onUsage });
    latest.current = { profiling, onUsage };
    useEffect(() => {
        const element = box.current;
        if (!element || !register) {
            return;
        }
        return register(element, {
            profiling: () => latest.current.profiling,
            onUsage: (usage) => latest.current.onUsage(usage),
            onCheck: setChecked,
        });
    }, [box, register]);
    return checked;
}

/** Sets what is in a text box as typing would, so that whoever listens to it, React or an exercise, hears of it. */
function typeInto(element: HTMLTextAreaElement, text: string) {
    Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")?.set?.call(element, text);
    element.dispatchEvent(new Event("input", { bubbles: true, composed: true }));
}

function isFocused(element: HTMLTextAreaElement): boolean {
    return (element.getRootNode() as Document | ShadowRoot).activeElement === element;
}

/** How a sentence is tinted by how far along it is, where its sentences are profiled. */
function sentenceStyle(state: SentenceState, rateWords: boolean): CSSProperties {
    // with the words rated, a sentence would be green first and only then get its red words
    const background = state === "typing"
        ? undefined
        : rateWords && state === "checking"
        ? "var(--checking-bg)"
        : "var(--done-bg)";
    return {
        backgroundColor: background,
        borderRadius: 4,
        boxDecorationBreak: "clone",
        WebkitBoxDecorationBreak: "clone",
        transition: "background-color 0.2s",
    };
}

/**
 * A stretch of the copy of the text, underlined if it is misspelled. The
 * copy may be in the shadow root of an exercise, where the styles of the
 * app do not reach, so it is styled where it is drawn.
 */
function markedPart(part: MarkedPart, index: number) {
    // a word that was rated is tinted red, the more the less right it is
    const strength = part.value === null ? 0 : doubt(part.value);
    const tint: CSSProperties = strength > 0
        ? { backgroundColor: `rgb(var(--doubt) / ${(strength * 0.6).toFixed(2)})`, borderRadius: 3 }
        : {};
    return part.issue
        ? (
            <span
                key={index}
                data-start={part.issue.start}
                style={{
                    ...tint,
                    textDecoration: "underline wavy var(--danger)",
                    textDecorationSkipInk: "none",
                    textUnderlineOffset: 3,
                }}
            >
                {part.text}
            </span>
        )
        : <span key={index} style={tint}>{part.text}</span>;
}

/** What is drawn behind a text box: its text, see-through, with what was found on it. */
function Mirror({ watch }: { watch: Watch }) {
    const profiling = watch.owner?.profiling() ?? null;
    const issues = spellingIssues(watch.check, watch.text, watch.caret);
    return (
        <>
            {sentenceParts(watch.text, watch.check, issues).map(({ sentence, parts }, index) =>
                sentence && profiling
                    ? (
                        <span key={index} style={sentenceStyle(sentenceState(sentence), profiling.rateWords)}>
                            {parts.map(markedPart)}
                        </span>
                    )
                    : <span key={index}>{parts.map(markedPart)}</span>
            )}
            {/* keeps a last, empty line as tall as it is in the box */}
            {" "}
        </>
    );
}

/** The misspelled word the mouse is over, and where it is on the window. */
interface Hint {
    watch: Watch;
    start: number;
    left: number;
    top: number;
}

/**
 * Checks the spelling of every text box of several lines in a place marked
 * with `data-writing`, in the page or in the interface of an exercise, once
 * it is written in, and the sentences of those that panels register with
 * `useWritingCheck` as they ask. Misspelled words are underlined in a copy
 * of the text laid behind the box, and the suggestions for one are shown
 * when the mouse is over it.
 */
export function WritingChecks({ language, children }: { language: string; children: ReactNode }) {
    const watches = useRef(new Map<HTMLTextAreaElement, Watch>());
    const count = useRef(0);
    // counted up to draw the copies again
    const [, setDrawn] = useState(0);
    const redraw = useCallback(() => setDrawn((count) => count + 1), []);
    const [hint, setHint] = useState<Hint | null>(null);
    const hintTimer = useRef<number>();
    // React tells of the mouse coming onto the hint before the box hears it leave, so the timer looks here
    const overHint = useRef(false);
    const latestLanguage = useRef(language);
    latestLanguage.current = language;

    /** Brings the copy of a box's text up to what is in the box, and where the box is; true if anything changed. */
    const follow = useCallback((watch: Watch): boolean => {
        const { element, mirror } = watch;
        const text = element.value;
        const caret = isFocused(element) ? element.selectionStart : null;
        const changed = text !== watch.text || caret !== watch.caret;
        watch.text = text;
        watch.caret = caret;
        if (caret !== null) {
            watch.lastCaret = caret;
        }
        const place = [
            element.offsetWidth,
            element.offsetHeight,
            element.clientWidth,
            element.offsetLeft,
            element.offsetTop,
        ]
            .join();
        if (place !== watch.place) {
            watch.place = place;
            const style = getComputedStyle(element);
            const scrollbar = element.offsetWidth - element.clientWidth - parseFloat(style.borderLeftWidth)
                - parseFloat(style.borderRightWidth);
            Object.assign(mirror.style, mirrorStyle(style, watch.background, scrollbar), {
                width: `${element.offsetWidth}px`,
                height: `${element.offsetHeight}px`,
            });
            // laid where the box is, whatever it is placed by
            const at = element.getBoundingClientRect();
            const from = mirror.getBoundingClientRect();
            mirror.style.left = `${parseFloat(mirror.style.left) + at.left - from.left}px`;
            mirror.style.top = `${parseFloat(mirror.style.top) + at.top - from.top}px`;
        }
        mirror.scrollTop = element.scrollTop;
        return changed;
    }, []);

    const detach = useCallback((element: HTMLTextAreaElement) => {
        const watch = watches.current.get(element);
        if (!watch) {
            return;
        }
        watch.detach();
        watches.current.delete(element);
        setHint((current) => (current?.watch === watch ? null : current));
        redraw();
    }, [redraw]);

    const attach = useCallback((element: HTMLTextAreaElement, owner: Owner | null) => {
        const known = watches.current.get(element);
        if (known) {
            known.owner = owner ?? known.owner;
            return;
        }
        const style = getComputedStyle(element);
        const mirror = document.createElement("div");
        mirror.setAttribute("aria-hidden", "true");
        Object.assign(mirror.style, { position: "absolute", left: "0px", top: "0px" });
        element.before(mirror);
        const restore = { background: element.style.background, position: element.style.position };
        const watch: Watch = {
            id: ++count.current,
            element,
            mirror,
            owner,
            restore,
            background: style.backgroundColor,
            sent: { text: "", caret: null, asked: "" },
            // Requests to the model may be left from before, such as from
            // the chat shown before this one, so it asks once anyway.
            awaiting: true,
            check: null,
            text: "",
            caret: null,
            lastCaret: null,
            place: "",
            detach: () => undefined,
        };
        // the box is drawn over the copy of its text, and lets it show through
        element.style.background = "transparent";
        if (style.position === "static") {
            element.style.position = "relative";
        }
        const onInput = () => follow(watch) && redraw();
        const onScroll = () => (mirror.scrollTop = element.scrollTop);
        const onMove = (event: MouseEvent) => hoverAt(watch, event.clientX, event.clientY);
        element.addEventListener("input", onInput);
        element.addEventListener("focus", onInput);
        element.addEventListener("blur", onInput);
        element.addEventListener("scroll", onScroll);
        element.addEventListener("mousemove", onMove);
        element.addEventListener("mouseleave", closeHintSoon);
        watch.detach = () => {
            element.removeEventListener("input", onInput);
            element.removeEventListener("focus", onInput);
            element.removeEventListener("blur", onInput);
            element.removeEventListener("scroll", onScroll);
            element.removeEventListener("mousemove", onMove);
            element.removeEventListener("mouseleave", closeHintSoon);
            mirror.remove();
            Object.assign(element.style, restore);
        };
        watches.current.set(element, watch);
        follow(watch);
        redraw();
    }, [follow, redraw]);

    // a box is checked once it is written in, wherever it is
    useEffect(() => {
        function onFocusIn(event: FocusEvent) {
            const box = checkedBox(event.composedPath() as unknown as HTMLElement[]);
            if (box instanceof HTMLTextAreaElement) {
                attach(box, null);
            }
        }
        document.addEventListener("focusin", onFocusIn);
        return () => document.removeEventListener("focusin", onFocusIn);
    }, [attach]);

    useEffect(() => {
        let looks = 0;
        let stopped = false;
        const timer = setInterval(() => {
            let changed = false;
            for (const watch of [...watches.current.values()]) {
                // a box that was taken away, as an exercise does with its own, is let go
                if (!watch.element.isConnected) {
                    detach(watch.element);
                    continue;
                }
                // what a panel puts in its box itself, such as nothing once it is sent, is not typed
                changed = follow(watch) || changed;
            }
            if (changed) {
                redraw();
            }
            if (++looks % LOOKS_PER_CHECK === 0) {
                watches.current.forEach(send);
            }
        }, LOOK_MS);

        function send(watch: Watch) {
            const profiling = watch.owner?.profiling() ?? null;
            const current: Sent = {
                text: watch.text,
                caret: watch.caret,
                asked: askedOf(latestLanguage.current, profiling),
            };
            if (!worthSending(watch.sent, current, watch.awaiting)) {
                return;
            }
            watch.sent = current;
            watch.awaiting = false;
            checkText(current.text, current.caret, latestLanguage.current, profiling).then(
                (reply) => {
                    // The server reports a request only once, so it is counted
                    // even if the rest of this answer is no longer of use.
                    reply.usage.forEach((usage) => watch.owner?.onUsage(usage));
                    watch.awaiting ||= reply.pending;
                    // an answer that arrives after something newer was sent is out of date
                    if (stopped || watch.sent !== current) {
                        return;
                    }
                    watch.check = {
                        text: current.text,
                        sentences: reply.sentences,
                        localModel: reply.local_model ?? null,
                    };
                    watch.owner?.onCheck({ check: watch.check, lastCaret: watch.lastCaret });
                    redraw();
                },
                () => {
                    // typing must not be disturbed by the checker being off
                },
            );
        }

        return () => {
            stopped = true;
            clearInterval(timer);
        };
    }, [detach, follow, redraw]);

    // the boxes are given back as they were when this goes
    useEffect(() => () => watches.current.forEach((watch) => watch.detach()), []);

    const register = useCallback((element: HTMLTextAreaElement, owner: Owner) => {
        attach(element, owner);
        return () => detach(element);
    }, [attach, detach]);

    useEffect(() => () => clearTimeout(hintTimer.current), []);

    // a hint taken away from under the mouse, as a click on a suggestion does, is not told the mouse left
    useEffect(() => {
        if (!hint) {
            overHint.current = false;
        }
    }, [hint]);

    /**
     * Shows the suggestions for the misspelled word under the mouse, if any.
     * The mouse is over the text box, so the word is found through its
     * underline in the copy of the text behind the box.
     */
    function hoverAt(watch: Watch, x: number, y: number) {
        for (const mark of watch.mirror.querySelectorAll<HTMLElement>("[data-start]")) {
            // a word that is broken across two lines has two rectangles
            const under = [...mark.getClientRects()].find((rect) =>
                x >= rect.left && x <= rect.right && y >= rect.top && y <= rect.bottom
            );
            if (under) {
                clearTimeout(hintTimer.current);
                setHint({ watch, start: Number(mark.dataset.start), left: under.left, top: under.top });
                return;
            }
        }
        closeHintSoon();
    }

    /** Leaves a moment to move the mouse from the word onto its suggestions. */
    function closeHintSoon() {
        clearTimeout(hintTimer.current);
        hintTimer.current = window.setTimeout(() => {
            if (!overHint.current) {
                setHint(null);
            }
        }, 250);
    }

    function fix(watch: Watch, issue: SpellingIssue, suggestion: string) {
        const { element } = watch;
        typeInto(element, applySuggestion(element.value, issue, suggestion));
        element.focus();
        const after = issue.start + suggestion.length;
        element.setSelectionRange(after, after);
        setHint(null);
    }

    const hintIssue = hint
        ? spellingIssues(hint.watch.check, hint.watch.text, hint.watch.caret).find((issue) =>
            issue.start === hint.start
        )
        : undefined;

    return (
        <WritingContext.Provider value={register}>
            {children}
            {[...watches.current.values()].map((watch) =>
                createPortal(<Mirror watch={watch} />, watch.mirror, String(watch.id))
            )}
            {hint && hintIssue && (
                <div
                    className="spelling-hint"
                    style={{ left: hint.left, top: hint.top }}
                    // moving from the word onto the hint must not close it
                    onMouseEnter={() => {
                        overHint.current = true;
                        clearTimeout(hintTimer.current);
                    }}
                    onMouseLeave={() => {
                        overHint.current = false;
                        closeHintSoon();
                    }}
                    // nor may a click on it take the caret out of the box
                    onMouseDown={(event) => event.preventDefault()}
                >
                    {hintIssue.suggestions.length === 0 && <span>Not in the dictionary</span>}
                    {hintIssue.suggestions.map((suggestion) => (
                        <button
                            key={suggestion}
                            type="button"
                            onClick={() => fix(hint.watch, hintIssue, suggestion)}
                            title={`Replace “${hintIssue.word}” with “${suggestion}”`}
                        >
                            {suggestion}
                        </button>
                    ))}
                </div>
            )}
        </WritingContext.Provider>
    );
}
