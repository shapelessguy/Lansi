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
    useMemo,
    useRef,
    useState,
} from "react";
import { createPortal } from "react-dom";

import {
    applySuggestion,
    type LiveCheck,
    type MarkedPart,
    type ProfileUsage,
    sentenceParts,
    type SentenceState,
    sentenceState,
    type SpellingIssue,
    spellingIssues,
    wordTint,
} from "../lib/checker";
import { t } from "../lib/i18n";
import { markedAncestor } from "../lib/selection";
import {
    askedOf,
    checkedBox,
    checkText,
    mirrorStyle,
    type Profiling,
    type Sent,
    worthSending,
    WRITING_ATTRIBUTE,
} from "../lib/writing";

/**
 * What a panel that registered a text box of its own, or a place whose
 * boxes are its own, is told, and asked: how the sentences of its boxes are
 * profiled, or null to check their spelling alone.
 */
interface Owner {
    profiling: () => Profiling | null;
    onUsage: (usage: ProfileUsage) => void;
    /** What is known about a box of its own, `element`, once it changes. */
    onCheck: (checked: Checked, element: HTMLTextAreaElement) => void;
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
    /**
     * The element the box is in, made the one the copy is placed in, so that
     * the copy scrolls with the box, and the position it had. Otherwise the
     * copy may be placed in an element outside what the box scrolls in, and
     * be left behind, over whatever comes under it, as the box scrolls away.
     */
    parent: { element: HTMLElement; position: string } | null;
    background: string;
    sent: Sent;
    awaiting: boolean;
    check: LiveCheck | null;
    text: string;
    caret: number | null;
    lastCaret: number | null;
    /** How large the box was last, and where, to tell when the copy must be styled again. */
    place: string;
    detach: () => void;
}

/**
 * What tells the boxes of this page from those of another open at the same
 * time, which the checker server, shared by both, is told with each box.
 */
const PAGE = Math.random().toString(36).slice(2, 10);

/** How often the text boxes are looked at for changes, and how many of those go by between checks, in milliseconds. */
const LOOK_MS = 100;
const LOOKS_PER_CHECK = 3;

/** How a panel registers a text box of its own, and a place whose boxes are its own, each until it lets it go. */
interface Registry {
    register: (element: HTMLTextAreaElement, owner: Owner) => () => void;
    registerPlace: (place: HTMLElement, owner: Owner) => () => void;
}

const WritingContext = createContext<Registry | null>(null);

/**
 * Has the spelling of the text box that `box` is checked as every text box
 * where writing is marked is, and, with `profiling`, its sentences profiled
 * too; with null, the spelling alone. Returns what is known about it, for a panel that shows more of it.
 */
export function useWritingCheck(
    box: RefObject<HTMLTextAreaElement>,
    profiling: Profiling | null,
    onUsage: (usage: ProfileUsage) => void,
): Checked {
    const registry = useContext(WritingContext);
    const [checked, setChecked] = useState<Checked>({ check: null, lastCaret: null });
    const latest = useRef({ profiling, onUsage });
    latest.current = { profiling, onUsage };
    useEffect(() => {
        const element = box.current;
        if (!element || !registry) {
            return;
        }
        return registry.register(element, {
            profiling: () => latest.current.profiling,
            onUsage: (usage) => latest.current.onUsage(usage),
            onCheck: setChecked,
        });
    }, [box, registry]);
    return checked;
}

/** What is known about the text box of a place the caret is in, or was last in, and the box. */
export interface PlaceChecked extends Checked {
    element: HTMLTextAreaElement | null;
}

/**
 * Has the sentences of the text boxes in `place`, a place marked for
 * writing whose boxes no panel registers, such as the interface of an
 * exercise, profiled as `profiling` says when they are checked: asked each
 * time, so that it may change, and null to check their spelling alone.
 * Returns what is known about the box the caret is in, or was last in,
 * for a panel that shows more of it.
 */
export function useWritingPlace(
    place: RefObject<HTMLElement>,
    profiling: () => Profiling | null,
    onUsage: (usage: ProfileUsage) => void,
): PlaceChecked {
    const registry = useContext(WritingContext);
    const latest = useRef({ profiling, onUsage });
    latest.current = { profiling, onUsage };
    const [checked, setChecked] = useState<PlaceChecked>({ check: null, lastCaret: null, element: null });
    useEffect(() => {
        const element = place.current;
        if (!element || !registry) {
            return;
        }
        return registry.registerPlace(element, {
            profiling: () => latest.current.profiling(),
            onUsage: (usage) => latest.current.onUsage(usage),
            // what is shown is of the box the caret is in, or was last in
            onCheck: (known, element) =>
                setChecked((current) =>
                    current.element === element || isFocused(element) ? { ...known, element } : current
                ),
        });
    }, [place, registry]);
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
    // a word that was rated is tinted green, yellow or red by how right it is
    const tint: CSSProperties = part.value === null
        ? {}
        : { backgroundColor: wordTint(part.value), borderRadius: 3 };
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
    const places = useRef(new Map<HTMLElement, Owner>());
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
        }
        // laid where the box is, whatever it is placed by, and laid there
        // again should it be left behind as the box moves
        const at = element.getBoundingClientRect();
        const from = mirror.getBoundingClientRect();
        if (Math.abs(at.left - from.left) > 0.5 || Math.abs(at.top - from.top) > 0.5) {
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
        const container = element.parentElement;
        const parent = container && getComputedStyle(container).position === "static"
            ? { element: container, position: container.style.position }
            : null;
        if (parent) {
            parent.element.style.position = "relative";
        }
        element.before(mirror);
        const restore = { background: element.style.background, position: element.style.position };
        const watch: Watch = {
            id: ++count.current,
            element,
            mirror,
            owner,
            restore,
            parent,
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
            if (parent) {
                parent.element.style.position = parent.position;
            }
        };
        watches.current.set(element, watch);
        follow(watch);
        redraw();
    }, [follow, redraw]);

    // a box is checked once it is written in, wherever it is
    useEffect(() => {
        // The shadow roots of the exercises, listened to as well: the caret
        // going from one box of an exercise to another is not told outside
        // it, as seen from there the focus stays on the exercise.
        const roots = new Set<ShadowRoot>();
        function onFocusIn(event: Event) {
            const box = checkedBox(event.composedPath() as unknown as HTMLElement[]);
            if (box instanceof HTMLTextAreaElement) {
                // one in a place that has its boxes profiled is that place's
                const place = markedAncestor<HTMLElement>(box, WRITING_ATTRIBUTE)?.marked;
                attach(box, (place && places.current.get(place)) ?? null);
                const root = box.getRootNode();
                if (root instanceof ShadowRoot && !roots.has(root)) {
                    roots.add(root);
                    root.addEventListener("focusin", onFocusIn);
                }
            }
        }
        document.addEventListener("focusin", onFocusIn);
        return () => {
            document.removeEventListener("focusin", onFocusIn);
            roots.forEach((root) => root.removeEventListener("focusin", onFocusIn));
        };
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
            checkText(current.text, current.caret, latestLanguage.current, profiling, `${PAGE}:${watch.id}`).then(
                (reply) => {
                    // The server reports a request only once, so it is counted
                    // even if the rest of this answer is no longer of use.
                    reply.usage.forEach((usage) => watch.owner?.onUsage(usage));
                    watch.awaiting ||= reply.pending;
                    // an answer that arrives after something newer was sent is out of date
                    if (stopped || watch.sent !== current) {
                        return;
                    }
                    watch.check = { text: current.text, sentences: reply.sentences };
                    watch.owner?.onCheck({ check: watch.check, lastCaret: watch.lastCaret }, watch.element);
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

    // What was found in one language does not hold in another: once the
    // language changes, every box is shown unchecked, an answer still to come
    // is let go of, and the box is sent again, its finished sentences with it.
    const checkedLanguage = useRef(language);
    useEffect(() => {
        if (checkedLanguage.current === language) {
            return;
        }
        checkedLanguage.current = language;
        watches.current.forEach((watch) => {
            watch.check = null;
            watch.sent = { ...watch.sent, asked: "" };
            watch.awaiting = true;
            watch.owner?.onCheck({ check: null, lastCaret: watch.lastCaret }, watch.element);
        });
        setHint(null);
        redraw();
    }, [language, redraw]);

    // the boxes are given back as they were when this goes
    useEffect(() => () => watches.current.forEach((watch) => watch.detach()), []);

    const registry = useMemo<Registry>(() => ({
        register: (element, owner) => {
            attach(element, owner);
            return () => detach(element);
        },
        registerPlace: (place, owner) => {
            places.current.set(place, owner);
            return () => {
                if (places.current.get(place) === owner) {
                    places.current.delete(place);
                }
            };
        },
    }), [attach, detach]);

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
        <WritingContext.Provider value={registry}>
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
                    {hintIssue.suggestions.length === 0 && <span>{t("Not in the dictionary")}</span>}
                    {hintIssue.suggestions.map((suggestion) => (
                        <button
                            key={suggestion}
                            type="button"
                            onClick={() => fix(hint.watch, hintIssue, suggestion)}
                            title={t("Replace “{word}” with “{suggestion}”", { word: hintIssue.word, suggestion })}
                        >
                            {suggestion}
                        </button>
                    ))}
                </div>
            )}
        </WritingContext.Provider>
    );
}
