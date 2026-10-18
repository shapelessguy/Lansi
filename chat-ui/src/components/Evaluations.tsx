// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { useCallback, useEffect, useMemo, useState } from "react";
import { canAsk } from "../lib/models";

import type { ProfileUsage } from "../lib/checker";
import {
    currentPart,
    describeLength,
    endEvaluation,
    type Evaluation,
    type EvaluationResult,
    type ExamLevel,
    fetchEvaluations,
    fetchLevels,
    finishPart,
    LENGTHS,
    shownScores,
    startEvaluation,
    startPart,
} from "../lib/evaluations";
import { type ExerciseInfo, fetchExercises, fetchSession, type Learner, type PracticeSession } from "../lib/practice";
import type { Settings } from "../lib/settings";
import type { BackgroundTask } from "../lib/tasks";
import { ExerciseView } from "./ExerciseView";
import { LevelBadge } from "./Level";
import { TimeLeft } from "./TimeLeft";

interface Props {
    settings: Settings;
    learner: Learner;
    onUsage: (used: ProfileUsage[]) => void;
    onTask: (task: BackgroundTask) => void;
    /** Keeps the settings changed, such as how long an evaluation takes. */
    onChangeSettings: (next: Settings) => void;
    onOpenSettings: () => void;
    /** Has a text of an exercise of a part read aloud, which the exercise numbers `number`. */
    onReadAloud: (sessionId: string, exercise: string, number: number, text: string) => void;
    /** An evaluation ended, and its log is being written. */
    onEnded: () => void;
}

/** What each module of an exam is called, for those that are not in the plan. */
const MODULE_TITLES: Record<string, string> = {
    hoeren: "Hören",
    lesen: "Lesen",
    schreiben: "Schreiben",
    sprechen: "Sprechen",
};

function day(seconds: number): string {
    return new Date(seconds * 1000).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

/** Whether it was passed, in a word. */
function passedOf(result: EvaluationResult): string {
    return result.passed === null ? "not every module done" : result.passed ? "passed" : "not passed";
}

/** The scores of an evaluation, each with a bar. */
function ScoreTable({ result }: { result: EvaluationResult }) {
    const shown = shownScores(result);
    if (shown.length === 0) {
        return <p className="practice-detail">Nothing was scored.</p>;
    }
    return (
        <dl className="evaluation-scores">
            {shown.map(({ name, label, value }) => (
                <div key={name} className={name.includes("_") ? "evaluation-score criterion" : "evaluation-score"}>
                    <dt>{label}</dt>
                    <dd>
                        <span className="evaluation-meter">
                            <span className={value >= 60 ? "pass" : ""} style={{ width: `${value}%` }} />
                        </span>
                        <span>{Math.round(value)}</span>
                    </dd>
                </div>
            ))}
        </dl>
    );
}

type Loaded<T> = { status: "loading" } | { status: "error"; message: string } | { status: "ready"; items: T[] };

/**
 * Evaluations: a mock exam of the learner's level, as the Goethe-Institut
 * sets it, made of the exercises of practice, part after part, each in a
 * session of its own and in its time if it is timed. Once it is over, the
 * server has its log written, with the scores.
 */
export function Evaluations(
    { settings, learner, onUsage, onTask, onChangeSettings, onOpenSettings, onReadAloud, onEnded }: Props,
) {
    const language = settings.language;
    const level = settings.level;
    const [levels, setLevels] = useState<Loaded<ExamLevel>>({ status: "loading" });
    const [exercises, setExercises] = useState<ExerciseInfo[]>([]);
    const [history, setHistory] = useState<Evaluation[]>([]);
    const [evaluation, setEvaluation] = useState<Evaluation | null>(null);
    // the session of the part being done
    const [session, setSession] = useState<PracticeSession | null>(null);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);
    // the evaluation that ended last, to say how it went
    const [ended, setEnded] = useState<Evaluation | null>(null);
    const [opened, setOpened] = useState<string | null>(null);

    const loadHistory = useCallback(() => {
        fetchEvaluations().then(setHistory, () => undefined);
    }, []);
    useEffect(loadHistory, [loadHistory, evaluation?.id, ended]);
    useEffect(() => {
        setLevels({ status: "loading" });
        fetchLevels(language).then(
            (items) => setLevels({ status: "ready", items }),
            (failed: Error) => setLevels({ status: "error", message: failed.message }),
        );
        fetchExercises().then(setExercises, () => undefined);
    }, [language]);

    const exam = levels.status === "ready" ? levels.items.find((each) => each.level === level) ?? null : null;
    const unfinished = evaluation ? null : history.find((each) => each.status === "running") ?? null;
    // the exercises of a part are asked as for a learner of the level of the exam
    const examined = useMemo<Learner>(
        () => ({ ...learner, level: evaluation?.level ?? learner.level }),
        [learner, evaluation?.level],
    );

    function titleOf(id: string): string {
        return exercises.find((each) => each.id === id)?.title ?? id;
    }

    function moduleTitle(of: Evaluation, id: string): string {
        return of.plan.modules.find((module) => module.id === id)?.title ?? MODULE_TITLES[id] ?? id;
    }

    function begin() {
        setBusy(true);
        setError(null);
        setEnded(null);
        startEvaluation(language, level, settings.evaluationLength, settings.evaluationTimed).then(
            (started) => {
                setEvaluation(started);
                setSession(null);
            },
            (failed: Error) => setError(failed.message),
        ).finally(() => setBusy(false));
    }

    /** Takes up an evaluation where it was left, in the part that is running if one is. */
    function resume(left: Evaluation) {
        setError(null);
        setEnded(null);
        setEvaluation(left);
        setSession(null);
        const at = currentPart(left);
        if (at !== null && left.parts[at].status === "running") {
            openPart(left, at);
        }
    }

    function openPart(of: Evaluation, position: number) {
        setBusy(true);
        setError(null);
        startPart(of.id, position).then(
            ({ evaluation: now, session: started }) => {
                setEvaluation(now);
                setSession(started);
            },
            (failed: Error) => setError(failed.message),
        ).finally(() => setBusy(false));
    }

    /** What the server has of the session, such as when its exercise started, which its time goes by. */
    function refresh(current: PracticeSession) {
        fetchSession(current.id).then(
            (found) => setSession((shown) => (shown?.id === found.id ? found : shown)),
            () => undefined,
        );
    }

    function over(done: { evaluation: Evaluation; usage: ProfileUsage[]; tasks?: BackgroundTask[] }) {
        onUsage(done.usage);
        // the logs of the exercise and of the evaluation, written in the background
        done.tasks?.forEach(onTask);
        setSession(null);
        if (done.evaluation.status === "running") {
            setEvaluation(done.evaluation);
        } else {
            setEvaluation(null);
            setEnded(done.evaluation);
            onEnded();
        }
    }

    function finish(of: Evaluation, position: number) {
        setBusy(true);
        setError(null);
        finishPart(of.id, position, examined).then(over, (failed: Error) => setError(failed.message)).finally(() =>
            setBusy(false)
        );
    }

    function end(of: Evaluation) {
        setBusy(true);
        setError(null);
        endEvaluation(of.id, { ...learner, level: of.level }).then(over, (failed: Error) => setError(failed.message))
            .finally(() => setBusy(false));
    }

    if (evaluation) {
        const at = currentPart(evaluation);
        const part = at === null ? null : evaluation.parts[at];
        const running = part && session && part.status === "running" && part.session === session.id;
        return (
            <div className="practice evaluation">
                <div className="practice-bar">
                    <span>
                        <strong>{evaluation.plan.exam}</strong>
                        {part && (
                            <>
                                {" · "}
                                {moduleTitle(evaluation, part.module)} {part.title} ({at! + 1} of{" "}
                                {evaluation.parts.length})
                            </>
                        )}
                    </span>
                    {running && (
                        <TimeLeft
                            key={session.id}
                            session={session}
                            exercise={part.exercise}
                            onUp={() => finish(evaluation, at!)}
                        />
                    )}
                    {/* where the player of a text that is heard goes, which never shows the text */}
                    <span className="speech-dock" data-speech-dock="evaluation" />
                    <span className="practice-actions">
                        {running && (
                            <button
                                disabled={busy}
                                title="Hand in this part as it is and go on. What you answered is kept."
                                onClick={() => finish(evaluation, at!)}
                            >
                                Next part
                            </button>
                        )}
                        <button
                            disabled={busy}
                            title="Stop the evaluation here. What you answered is scored."
                            onClick={() => end(evaluation)}
                        >
                            End evaluation
                        </button>
                    </span>
                </div>
                {error && <p className="practice-note error">{error}</p>}
                <ol className="evaluation-parts" aria-label="Parts">
                    {evaluation.parts.map((each, number) => (
                        <li
                            key={number}
                            className={`evaluation-part ${each.status}${number === at ? " current" : ""}`}
                            title={titleOf(each.exercise)}
                        >
                            <span>{moduleTitle(evaluation, each.module)}</span>
                            <span className="practice-detail">{each.title}</span>
                        </li>
                    ))}
                </ol>
                <div className="practice-body">
                    {running
                        ? (
                            <>
                                {part.instructions && <p className="evaluation-instructions">{part.instructions}</p>}
                                <ExerciseView
                                    key={session.id}
                                    sessionId={session.id}
                                    exercise={part.exercise}
                                    learner={examined}
                                    onUsage={onUsage}
                                    onFinish={() => finish(evaluation, at!)}
                                    onReadAloud={(text, number) => onReadAloud(session.id, part.exercise, number, text)}
                                    onStarted={() => refresh(session)}
                                />
                            </>
                        )
                        : part && (
                            <section className="evaluation-next">
                                <h2>
                                    {moduleTitle(evaluation, part.module)} · {part.title}
                                </h2>
                                <p>{part.instructions}</p>
                                <p className="practice-detail">
                                    {titleOf(part.exercise)} · {part.instances}{" "}
                                    {part.instances === 1 ? "task" : "tasks"} · {evaluation.timed
                                        ? `${part.minutes} min, timed from when it is shown`
                                        : `about ${part.minutes} min`}
                                </p>
                                <button className="primary" disabled={busy} onClick={() => openPart(evaluation, at!)}>
                                    {busy ? "Starting…" : part.status === "running" ? "Continue" : "Start"}
                                </button>
                            </section>
                        )}
                </div>
            </div>
        );
    }

    return (
        <div className="practice evaluation">
            <div className="practice-body">
                {ended && (
                    <section className="evaluation-result">
                        <h2>
                            {ended.plan.exam}: {passedOf(ended.result)}
                        </h2>
                        <ScoreTable result={ended.result} />
                        <p className="practice-detail">
                            The log of the evaluation is being written, with these scores.
                        </p>
                    </section>
                )}
                {unfinished && (
                    <div className="practice-resume">
                        <span>
                            <strong>Not finished:</strong> {unfinished.plan.exam}
                            <span className="practice-detail">
                                {" · "}
                                {unfinished.parts.filter((part) => part.status === "done").length} of{" "}
                                {unfinished.parts.length} parts done
                            </span>
                        </span>
                        <span className="practice-actions">
                            <button className="primary" onClick={() => resume(unfinished)}>Continue</button>
                            <button disabled={busy} onClick={() => end(unfinished)}>End it</button>
                        </span>
                    </div>
                )}
                {!canAsk(learner.model, learner.apiKey) && (
                    <p className="practice-note">
                        The parts are made by a model. <button onClick={onOpenSettings}>Add your OpenRouter key</button>
                    </p>
                )}
                <section className="evaluation-start">
                    <h2>
                        Evaluation <LevelBadge level={level} />
                    </h2>
                    {levels.status === "loading" && <p className="practice-note">Loading the exams…</p>}
                    {levels.status === "error" && <p className="practice-note error">{levels.message}</p>}
                    {levels.status === "ready" && !exam && (
                        <p className="practice-note">
                            There is no exam of {language} at {level} yet
                            {levels.items.length > 0
                                && ` (there is at ${levels.items.map((each) => each.level).join(", ")})`}.{" "}
                            <button onClick={onOpenSettings}>Change your level</button>
                        </p>
                    )}
                    {exam && (
                        <>
                            <p>
                                <strong>{exam.exam}</strong>
                                <span className="practice-detail">
                                    {" · "}
                                    {exam.modules.map((module) => module.title).join(", ")} · {exam.minutes} min in full
                                </span>
                            </p>
                            <label className="exercise-setting">
                                <span>Length</span>
                                <span className="evaluation-length">
                                    <input
                                        type="range"
                                        min={LENGTHS.min}
                                        max={LENGTHS.max}
                                        step={1}
                                        value={settings.evaluationLength}
                                        onChange={(event) =>
                                            onChangeSettings({
                                                ...settings,
                                                evaluationLength: Number(event.target.value),
                                            })}
                                    />
                                    <span>{describeLength(settings.evaluationLength)}</span>
                                </span>
                            </label>
                            <label className="exercise-setting">
                                <span>Timed</span>
                                <span>
                                    <input
                                        type="checkbox"
                                        checked={settings.evaluationTimed}
                                        onChange={(event) =>
                                            onChangeSettings({ ...settings, evaluationTimed: event.target.checked })}
                                    />{" "}
                                    <span className="practice-detail">each part in its time, as in the exam</span>
                                </span>
                            </label>
                            <p className="practice-detail">
                                Your level is set in the settings. What you write in an evaluation is not taken into
                                your vocabulary.
                            </p>
                        </>
                    )}
                    {error && <p className="practice-note error">{error}</p>}
                    <button className="primary" disabled={busy || !exam} onClick={begin}>
                        {busy ? "Starting…" : "Start the evaluation"}
                    </button>
                </section>
                {history.length > 0 && (
                    <section className="history">
                        <h2>Past evaluations</h2>
                        <ul className="evaluation-history">
                            {history.filter((each) => each.status !== "running").map((each) => (
                                <li key={each.id}>
                                    <button
                                        className="practice-choice"
                                        aria-expanded={opened === each.id}
                                        onClick={() => setOpened(opened === each.id ? null : each.id)}
                                    >
                                        <LevelBadge level={each.level} />
                                        <span className="practice-title">
                                            {day(each.started_at)} · {describeLength(each.length)}
                                            {each.timed ? ", timed" : ""}
                                        </span>
                                        <span className="practice-detail">
                                            {typeof each.result.scores.total === "number"
                                                ? `${Math.round(each.result.scores.total)} · `
                                                : ""}
                                            {passedOf(each.result)}
                                        </span>
                                    </button>
                                    {opened === each.id && <ScoreTable result={each.result} />}
                                </li>
                            ))}
                        </ul>
                    </section>
                )}
            </div>
        </div>
    );
}
