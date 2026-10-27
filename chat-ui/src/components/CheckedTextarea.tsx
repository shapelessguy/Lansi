// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { type RefObject, type TextareaHTMLAttributes, useCallback, useMemo, useRef } from "react";
import { createPortal } from "react-dom";

import type { ProfileUsage } from "../lib/checker";
import type { WordLists } from "../lib/sets";
import type { Settings } from "../lib/settings";
import type { UsageEntry } from "../lib/usage";
import { type CheckedPlace, placeChecked, profilingOf } from "../lib/writing";
import { SettingsChecksPanel } from "./ChecksPanel";
import { useWritingCheck } from "./WritingChecks";

export interface CheckedTextareaProps
    extends Omit<TextareaHTMLAttributes<HTMLTextAreaElement>, "value" | "onChange" | "spellCheck">
{
    value: string;
    onChange: (value: string) => void;
    /** The class of the element the box is in, which is marked as one whose writing is checked. */
    className: string;
    /** The box, for whoever must reach it, such as to focus it. */
    inputRef?: RefObject<HTMLTextAreaElement>;
    /** Where the box is, whose sentences are checked as the learner chose there; the spelling is checked either way. */
    place: CheckedPlace;
    /** What the sentences are profiled by, and what changes it from the panel of the checks. */
    settings: Settings;
    onSettingsChange: (settings: Settings) => void;
    /** What the keywords for words in the questions stand for. */
    words: WordLists;
    /** Counts what profiling the sentences used, under `usageId`, the chat or the text it is of. */
    onUsage: (entry: UsageEntry) => void;
    usageId: string;
    /** Where to show the panel with the checks of the sentence under the caret, or null while it is closed. */
    checksSlot: HTMLElement | null;
    onCloseChecks: () => void;
    onEditQuestions: () => void;
}

/**
 * A text box whose spelling is checked and whose sentences are profiled, as
 * the questions of the settings ask, with the checks of the sentence under
 * the caret in the panel on the right while it is open. The chat, the
 * tutor and the texts are written in one.
 */
export function CheckedTextarea(
    {
        value,
        onChange,
        className,
        inputRef,
        place,
        settings,
        onSettingsChange,
        words,
        onUsage,
        usageId,
        checksSlot,
        onCloseChecks,
        onEditQuestions,
        ...rest
    }: CheckedTextareaProps,
) {
    const ownRef = useRef<HTMLTextAreaElement>(null);
    const box = inputRef ?? ownRef;
    const checked = placeChecked(place, settings);
    const profiling = useMemo(
        () => (checked ? profilingOf(settings, words, usageId) : null),
        [checked, settings, words, usageId],
    );
    const countProfiling = useCallback(
        (used: ProfileUsage) =>
            onUsage({
                id: used.id,
                at: Date.now(),
                category: "checking",
                chatId: usageId,
                model: used.model,
                promptTokens: used.input_tokens,
                completionTokens: used.output_tokens,
                cost: used.cost,
            }),
        [usageId, onUsage],
    );
    const { check, lastCaret } = useWritingCheck(box, profiling, countProfiling);
    return (
        <>
            <div className={className} data-writing>
                <textarea
                    {...rest}
                    ref={box}
                    value={value}
                    // the browser's own checker would underline the same words a second time
                    spellCheck={false}
                    onChange={(event) => onChange(event.target.value)}
                />
            </div>
            {checksSlot && createPortal(
                <SettingsChecksPanel
                    settings={settings}
                    onSettingsChange={onSettingsChange}
                    check={check}
                    lastCaret={lastCaret}
                    text={value}
                    onEditQuestions={onEditQuestions}
                    onClose={onCloseChecks}
                />,
                checksSlot,
            )}
        </>
    );
}
