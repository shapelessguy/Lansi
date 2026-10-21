// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { useEffect, useRef, useState } from "react";

import { ankiMediaUrl } from "../lib/anki";
import type { ProfileUsage } from "../lib/checker";
import type { Where } from "../lib/logs";
import { exerciseKit, type Learner, loadInterface, stepExercise } from "../lib/practice";

interface Props {
    sessionId: string;
    exercise: string;
    /** Whether it is theory, which is read rather than made by a model. */
    theory?: boolean;
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
    { sessionId, exercise, theory = false, learner, onUsage, onFinish, onReadAloud, onStarted }: Props,
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
            loadInterface(exercise),
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
                    {theory ? <strong>Opening the lesson…</strong> : (
                        <>
                            <strong>Making the exercise…</strong>
                            <span className="practice-detail">
                                The model is writing it for you. This takes a few seconds.
                            </span>
                        </>
                    )}
                </div>
            )}
            {error && (
                <div className="exercise-waiting error" style={{ minHeight: WAITING_HEIGHT }} role="alert">
                    <strong>The exercise could not be made.</strong>
                    <span>{error}</span>
                    <button onClick={() => setAttempt((count) => count + 1)}>Try again</button>
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
        </div>
    );
}
