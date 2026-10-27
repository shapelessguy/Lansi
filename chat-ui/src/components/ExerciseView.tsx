// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { ankiMediaUrl } from "../lib/anki";
import type { ProfileUsage } from "../lib/checker";
import { t } from "../lib/i18n";
import type { Where } from "../lib/logs";
import {
    exerciseKit,
    knowExercises,
    type Learner,
    loadInterface,
    sentencesChecked,
    stepExercise,
} from "../lib/practice";
import type { WordLists } from "../lib/sets";
import type { Settings } from "../lib/settings";
import { profilingOf } from "../lib/writing";
import { SettingsChecksPanel } from "./ChecksPanel";
import { SidePanel } from "./SidePanel";
import { useWritingPlace } from "./WritingChecks";

interface Props {
    sessionId: string;
    exercise: string;
    /** Whether it is theory, which is read rather than made by a model. */
    theory?: boolean;
    /** What the sentences written in it are checked by, if they are, as its manifest and the learner say. */
    settings: Settings;
    /** What the keywords for words in the questions of the sentence checks stand for. */
    words: WordLists;
    /** Where to show the panel with the checks of the sentence under the caret, or null while it is closed. */
    checksSlot?: HTMLElement | null;
    onSettingsChange?: (settings: Settings) => void;
    onCloseChecks?: () => void;
    onEditQuestions?: () => void;
    learner: Learner;
    onUsage: (used: ProfileUsage[]) => void;
    /** The learner is done with the exercise, as its interface says. */
    onFinish: () => void;
    /** Has a text of the exercise read aloud, which it numbers `number`. */
    onReadAloud: (text: string, number: number) => void;
    /** The exercise is shown, which is when its time starts. */
    onStarted?: () => void;
}

/** How tall the room for the exercise is while it is being made, in pixels. */
const WAITING_HEIGHT = 240;

/**
 * Shows the interface of an exercise, in a shadow root of its own, and
 * carries what it asks to its backend, as `exercises/kit.js` on the server
 * describes.
 */
export function ExerciseView(
    {
        sessionId,
        exercise,
        theory = false,
        settings,
        words,
        checksSlot = null,
        onSettingsChange = () => undefined,
        onCloseChecks = () => undefined,
        onEditQuestions = () => undefined,
        learner,
        onUsage,
        onFinish,
        onReadAloud,
        onStarted,
    }: Props,
) {
    const host = useRef<HTMLDivElement>(null);
    const [error, setError] = useState<string | null>(null);
    // Whether the interface shows what the backend made. Until then it is
    // kept out of sight, and what is happening is said in its place.
    const [rendered, setRendered] = useState(false);
    // counted up to start again after a failure
    const [attempt, setAttempt] = useState(0);
    const latest = useRef({ learner, onUsage, onFinish, onReadAloud, onStarted });
    latest.current = { learner, onUsage, onFinish, onReadAloud, onStarted };

    // its spelling is checked as everywhere, and its sentences as the
    // manifest and the learner say, asked at each check, so that the
    // learner may turn them on and off as they write; what that uses is
    // counted under the session
    const checked = useWritingPlace(
        host,
        () =>
            sentencesChecked(exercise, settings.exerciseSentenceChecks)
                ? profilingOf(settings, words, sessionId)
                : null,
        (used) => latest.current.onUsage([used]),
    );

    useEffect(() => {
        const element = host.current;
        if (!element) {
            return;
        }
        let gone = false;
        let unmount: (() => void) | void;
        setError(null);
        setRendered(false);
        // the interface is loaded while the backend makes the exercise
        Promise.all([
            // what it shows in the language of the interface, which the kit has it say
            knowExercises().then(() => loadInterface(exercise)),
            stepExercise(sessionId, exercise, "start", null, latest.current.learner).then(({ show, usage }) => {
                latest.current.onUsage(usage);
                return show;
            }),
        ]).then(([ui, first]) => {
            if (gone) {
                return;
            }
            const shadow = element.shadowRoot ?? element.attachShadow({ mode: "open" });
            shadow.adoptedStyleSheets = ui.sheets;
            const root = document.createElement("div");
            root.className = "root";
            shadow.replaceChildren(root);
            const { kit, show } = exerciseKit(
                (message) =>
                    stepExercise(sessionId, exercise, "act", message, latest.current.learner).then(
                        ({ show: shown, usage }) => {
                            latest.current.onUsage(usage);
                            return shown;
                        },
                    ),
                () => latest.current.onFinish(),
                (text, number) => latest.current.onReadAloud(text, number),
                ankiMediaUrl,
                exercise,
            );
            unmount = ui.mount(root, kit);
            show(first);
            setRendered(true);
            latest.current.onStarted?.();
        }).catch((failed: Error) => {
            if (!gone) {
                setError(failed.message);
            }
        });
        return () => {
            gone = true;
            unmount?.();
            element.shadowRoot?.replaceChildren();
        };
    }, [sessionId, exercise, attempt]);

    return (
        <div className="exercise">
            {!rendered && !error && (
                <div className="exercise-waiting" style={{ minHeight: WAITING_HEIGHT }} role="status">
                    <span className="exercise-spinner" aria-hidden="true" />
                    {theory ? <strong>{t("Opening the lesson…")}</strong> : (
                        <>
                            <strong>{t("Making the exercise…")}</strong>
                            <span className="practice-detail">
                                {t("The model is writing it for you. This takes a few seconds.")}
                            </span>
                        </>
                    )}
                </div>
            )}
            {error && (
                <div className="exercise-waiting error" style={{ minHeight: WAITING_HEIGHT }} role="alert">
                    <strong>{t("The exercise could not be made.")}</strong>
                    <span>{error}</span>
                    <button onClick={() => setAttempt((count) => count + 1)}>{t("Try again")}</button>
                </div>
            )}
            <div
                ref={host}
                className="exercise-ui"
                data-selectable
                data-writing
                data-where={JSON.stringify({ kind: "exercise", session: sessionId, exercise } satisfies Where)}
                hidden={!rendered || error !== null}
            />
            {checksSlot && createPortal(
                sentencesChecked(exercise, settings.exerciseSentenceChecks)
                    ? (
                        <SettingsChecksPanel
                            settings={settings}
                            onSettingsChange={onSettingsChange}
                            check={checked.check}
                            lastCaret={checked.lastCaret}
                            text={checked.element?.value ?? ""}
                            onEditQuestions={onEditQuestions}
                            onClose={onCloseChecks}
                        />
                    )
                    : (
                        <SidePanel title={t("Sentence checks")} onClose={onCloseChecks}>
                            <p className="checks-note">
                                {t("The sentences of this exercise are not checked. Turn on Sentence checks above, where the exercise has them.")}
                            </p>
                        </SidePanel>
                    ),
                checksSlot,
            )}
        </div>
    );
}
