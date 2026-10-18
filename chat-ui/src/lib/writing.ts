// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { type CheckReply, fetchCheck } from "./checker";
import { type ModelChoice, onOpenRouter } from "./models";
import type { RequestQuestions } from "./questions";
import { type Climbing, markedAncestor } from "./selection";

/**
 * The attribute that a panel puts on where text is written in it, to have
 * the spelling of what is written in its text boxes checked. What is in the
 * shadow root of such an element, as the interface of an exercise is, is
 * checked as well.
 */
export const WRITING_ATTRIBUTE = "data-writing";
/** The attribute that leaves a text box in such a place unchecked, such as one that is written in another language. */
export const NO_CHECK_ATTRIBUTE = "data-no-check";

/** An element as far as telling whether it is a text box to check needs it. */
export interface Box extends Climbing {
    tagName?: string;
}

/**
 * The text box to check that `path`, the composed path of an event, starts
 * at, if it starts at one: a text box of several lines in a place marked
 * for writing, not marked to be left out. Boxes of one line, such as the
 * gaps of a text to fill in, take a word or two, and are left out.
 */
export function checkedBox<B extends Box>(path: readonly B[]): B | null {
    const [target] = path;
    if (!target || target.tagName !== "TEXTAREA" || target.getAttribute?.(NO_CHECK_ATTRIBUTE) != null) {
        return null;
    }
    return markedAncestor(target, WRITING_ATTRIBUTE) ? target : null;
}

/** What a text box is checked for, beyond its spelling: its sentences are profiled, as they are in the chat. */
export interface Profiling {
    apiKey: string;
    model: ModelChoice;
    questions: RequestQuestions;
    rateWords: boolean;
}

/** What was last sent about a text box, or is about to be. */
export interface Sent {
    text: string;
    caret: number | null;
    /** What was asked about it, as text, so that a change in it is easy to notice. */
    asked: string;
}

/** What is asked about a text box: its spelling, in `language`, and, if they are profiled, about its sentences. */
export function askedOf(language: string, profiling: Profiling | null): string {
    return JSON.stringify(
        profiling ? [language, profiling.model, profiling.questions, profiling.rateWords] : [language],
    );
}

/**
 * Whether a text box is worth checking again: what is in it, where its
 * caret is or what is asked about it has changed since `sent`, or requests
 * to the model were still out at the last answer. An empty box has nothing
 * to say about, wherever the caret is.
 */
export function worthSending(sent: Sent, current: Sent, awaiting: boolean): boolean {
    const unchanged = current.text === sent.text
        && (current.text === "" || (current.caret === sent.caret && current.asked === sent.asked));
    return awaiting || !unchanged;
}

/** Has the checker server check `text`: its spelling alone, or, with `profiling`, its sentences too. */
export function checkText(
    text: string,
    caret: number | null,
    language: string,
    profiling: Profiling | null,
): Promise<CheckReply> {
    return profiling
        ? fetchCheck(
            text,
            caret,
            profiling.apiKey,
            profiling.model,
            profiling.questions,
            profiling.rateWords,
            language,
        )
        : fetchCheck(text, caret, "", onOpenRouter(""), {}, false, language, false);
}

/** How a text box lays out its text, which the copy of it behind the box that carries the underlines must match. */
const COPIED = [
    "boxSizing",
    "paddingTop",
    "paddingRight",
    "paddingBottom",
    "paddingLeft",
    "borderTopWidth",
    "borderRightWidth",
    "borderBottomWidth",
    "borderLeftWidth",
    "borderTopLeftRadius",
    "borderTopRightRadius",
    "borderBottomRightRadius",
    "borderBottomLeftRadius",
    "fontFamily",
    "fontSize",
    "fontStyle",
    "fontWeight",
    "fontVariant",
    "fontStretch",
    "lineHeight",
    "letterSpacing",
    "wordSpacing",
    "textIndent",
    "textTransform",
    "textAlign",
    "tabSize",
    "direction",
    "whiteSpace",
    "overflowWrap",
    "wordBreak",
] as const;

type Copied = (typeof COPIED)[number];

/**
 * The style of the copy of a text box's text that is laid behind it: laid
 * out as the box, whose style is `style`, lays out its text, with a scroll
 * bar of `scrollbar` pixels taken off the right, and drawn with nothing but
 * what is put on the text, on the `background` the box had, as the box is
 * made see-through.
 */
export function mirrorStyle(
    style: Pick<CSSStyleDeclaration, Copied>,
    background: string,
    scrollbar: number,
): Record<string, string> {
    const copied: Record<string, string> = Object.fromEntries(COPIED.map((name) => [name, style[name]]));
    return {
        ...copied,
        paddingRight: `calc(${style.paddingRight} + ${scrollbar}px)`,
        position: "absolute",
        margin: "0",
        borderStyle: "solid",
        borderColor: "transparent",
        backgroundColor: background,
        color: "transparent",
        overflow: "hidden",
        pointerEvents: "none",
    };
}
