// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { type RefObject, type TextareaHTMLAttributes, useCallback, useMemo, useRef } from "react";
import { createPortal } from "react-dom";

import { type ProfileUsage, sentenceAtCaret } from "../lib/checker";
import { orModel } from "../lib/models";
import { requestQuestions } from "../lib/questions";
import type { WordLists } from "../lib/sets";
import { expandPrompt, type Settings } from "../lib/settings";
import type { UsageEntry } from "../lib/usage";
import { ChecksPanel } from "./ChecksPanel";
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
    const { language, level } = settings;
    const questions = useMemo(
        () => requestQuestions(settings.questions, (text) => expandPrompt(text, words, language, level)),
        [settings.questions, words, language, level],
    );
    // as a selection is translated: by the translation model, or else the chat model
    const corrector = useMemo(
        () => orModel(settings.translationModel, settings.model),
        [settings.translationModel, settings.model],
    );
    const correctWith = settings.correctSentences ? corrector : null;
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
    const { check, lastCaret } = useWritingCheck(
        box,
        {
            apiKey: settings.apiKey,
            model: settings.profileModel,
            questions,
            rateWords: settings.rateWords,
            correctWith,
            usageId,
        },
        countProfiling,
    );
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
                <ChecksPanel
                    questions={settings.questions}
                    onToggle={(question) =>
                        onSettingsChange({
                            ...settings,
                            questions: settings.questions.map((each) =>
                                each.id === question ? { ...each, enabled: !each.enabled } : each
                            ),
                        })}
                    rateWords={settings.rateWords}
                    onRateWords={(rateWords) => onSettingsChange({ ...settings, rateWords })}
                    corrector={corrector}
                    correct={settings.correctSentences}
                    onCorrect={(correctSentences) => onSettingsChange({ ...settings, correctSentences })}
                    // the panel goes on showing the sentence the caret was on after a click in it
                    sentence={value ? sentenceAtCaret(check, lastCaret) : null}
                    hasText={value.trim() !== ""}
                    checkerRunning={check !== null}
                    hasKey={settings.apiKey !== ""}
                    model={settings.profileModel}
                    onEditQuestions={onEditQuestions}
                    onClose={onCloseChecks}
                />,
                checksSlot,
            )}
        </>
    );
}
