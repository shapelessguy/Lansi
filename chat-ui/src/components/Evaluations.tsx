// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { canAsk } from "../lib/models";

import type { ProfileUsage } from "../lib/checker";
import {
    currentPart,
    endEvaluation,
    type Evaluation,
    type ExamLevel,
    fetchEvaluations,
    fetchLevels,
    finishPart,
    moduleTitle,
    SIZES,
    startEvaluation,
    startPart,
} from "../lib/evaluations";
import { interfaceLanguage, languageName, plural, t } from "../lib/i18n";
import { type ExerciseInfo, fetchExercises, fetchSession, type Learner, type PracticeSession } from "../lib/practice";
import type { Settings } from "../lib/settings";
import type { BackgroundTask } from "../lib/tasks";
import { EvaluationReview, passedOf } from "./EvaluationsDone";
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
    /** An evaluation started elsewhere, such as one the tutor offered, to be taken up here, with a number that tells it from the one before. */
    opening?: { evaluation: Evaluation; nonce: number } | null;
}

type Loaded<T> = { status: "loading" } | { status: "error"; message: string } | { status: "ready"; items: T[] };

/**
 * Evaluations: a mock exam of the learner's level, as the institute that examines the language
 * sets it, made of the exercises of practice, part after part, each in a
 * session of its own and in its time if it is timed. Once it is over, the
 * server has its log written, with the scores.
 */
export function Evaluations(
    { settings, learner, onUsage, onTask, onChangeSettings, onOpenSettings, onReadAloud, onEnded, opening }: Props,
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

    const loadHistory = useCallback(() => {
        fetchEvaluations().then(setHistory, () => undefined);
    }, []);
    useEffect(loadHistory, [loadHistory, evaluation?.id, ended]);
    // the exercises are listed again in the language of the interface when it changes
    const shownIn = interfaceLanguage();
    useEffect(() => {
        setLevels({ status: "loading" });
        fetchLevels(language).then(
            (items) => setLevels({ status: "ready", items }),
            (failed: Error) => setLevels({ status: "error", message: failed.message }),
        );
        fetchExercises().then(setExercises, () => undefined);
    }, [language, shownIn]);

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

    function begin() {
        setBusy(true);
        setError(null);
        setEnded(null);
        startEvaluation(language, level, settings.evaluationSize, settings.evaluationTimed).then(
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

    // one started elsewhere, such as one the tutor offered, is taken up here
    const take = useRef(resume);
    take.current = resume;
    useEffect(() => {
        if (opening) {
            take.current(opening.evaluation);
        }
    }, [opening]);

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

    // In an exam there is nothing to choose: each part is opened as soon as it
    // is the one to do, the first as the evaluation starts and each other
    // once the one before was handed in. One that failed to open waits for
    // the learner to try again.
    const opened = useRef("");
    useEffect(() => {
        if (!evaluation || busy || error) {
            return;
        }
        const next = currentPart(evaluation);
        const part = next === null ? null : evaluation.parts[next];
        const shown = part && session && part.status === "running" && part.session === session.id;
        const key = `${evaluation.id}:${next}`;
        if (next === null || shown || opened.current === key) {
            return;
        }
        opened.current = key;
        openPart(evaluation, next);
    });

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
                                {moduleTitle(evaluation.plan.modules, part.module)} {part.title}{" "}
                                {t("({at} of {count})", { at: at! + 1, count: evaluation.parts.length })}
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
                                title={t("Hand in this part as it is and go on. What you answered is kept.")}
                                onClick={() => finish(evaluation, at!)}
                            >
                                {t("Next part")}
                            </button>
                        )}
                        <button
                            disabled={busy}
                            title={t("Stop the evaluation here. What you answered is scored.")}
                            onClick={() => end(evaluation)}
                        >
                            {t("End evaluation")}
                        </button>
                    </span>
                </div>
                {error && <p className="practice-note error">{error}</p>}
                <ol className="evaluation-parts" aria-label={t("Parts")}>
                    {evaluation.parts.map((each, number) => (
                        <li
                            key={number}
                            className={`evaluation-part ${each.status}${number === at ? " current" : ""}`}
                            title={titleOf(each.exercise)}
                        >
                            <span>{moduleTitle(evaluation.plan.modules, each.module)}</span>
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
                                    {moduleTitle(evaluation.plan.modules, part.module)} · {part.title}
                                </h2>
                                <p>{part.instructions}</p>
                                <p className="practice-detail">
                                    {titleOf(part.exercise)} · {plural(part.instances, "{count} task", "{count} tasks")}
                                    {" · "}
                                    {evaluation.timed
                                        ? t("{minutes} min, timed from when it is shown", { minutes: part.minutes })
                                        : t("about {minutes} min", { minutes: part.minutes })}
                                </p>
                                <button className="primary" disabled={busy} onClick={() => openPart(evaluation, at!)}>
                                    {busy ? t("Starting…") : part.status === "running" ? t("Continue") : t("Start")}
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
                        {/* what was not right is told only now, as an exam does */}
                        <EvaluationReview evaluation={ended} />
                        <p className="practice-detail">
                            {t("The log of the evaluation is being written, with these scores.")}
                        </p>
                    </section>
                )}
                {unfinished && (
                    <div className="practice-resume">
                        <span>
                            <strong>{t("Not finished:")}</strong> {unfinished.plan.exam}
                            <span className="practice-detail">
                                {" · "}
                                {t("{done} of {count} parts done", {
                                    done: unfinished.parts.filter((part) => part.status === "done").length,
                                    count: unfinished.parts.length,
                                })}
                            </span>
                        </span>
                        <span className="practice-actions">
                            <button className="primary" onClick={() => resume(unfinished)}>{t("Continue")}</button>
                            <button disabled={busy} onClick={() => end(unfinished)}>{t("End it")}</button>
                        </span>
                    </div>
                )}
                {!canAsk(learner.model, learner.apiKey) && (
                    <p className="practice-note">
                        {t("The parts are made by a model.")}{" "}
                        <button onClick={onOpenSettings}>{t("Add your OpenRouter key")}</button>
                    </p>
                )}
                <section className="evaluation-start">
                    <h2>
                        {t("Evaluation")} <LevelBadge level={level} />
                    </h2>
                    {levels.status === "loading" && <p className="practice-note">{t("Loading the exams…")}</p>}
                    {levels.status === "error" && <p className="practice-note error">{levels.message}</p>}
                    {levels.status === "ready" && !exam && (
                        <p className="practice-note">
                            {levels.items.length > 0
                                ? t("There is no exam of {language} at {level} yet (there is at {levels}).", {
                                    language: languageName(language),
                                    level,
                                    levels: levels.items.map((each) => each.level).join(", "),
                                })
                                : t("There is no exam of {language} at {level} yet.", {
                                    language: languageName(language),
                                    level,
                                })} <button onClick={onOpenSettings}>{t("Change your level")}</button>
                        </p>
                    )}
                    {exam && (
                        <>
                            <p>
                                <strong>{exam.exam}</strong>
                                <span className="practice-detail">
                                    {" · "}
                                    {exam.modules.map((module) => module.title).join(", ")} ·{" "}
                                    {t("{minutes} min in full", { minutes: exam.minutes })}
                                </span>
                            </p>
                            <label className="exercise-setting">
                                <span>{t("Length")}</span>
                                <span className="evaluation-length">
                                    <input
                                        type="range"
                                        min={SIZES.min}
                                        max={SIZES.max}
                                        step={1}
                                        value={settings.evaluationSize}
                                        onChange={(event) =>
                                            onChangeSettings({
                                                ...settings,
                                                evaluationSize: Number(event.target.value),
                                            })}
                                    />
                                    <span>
                                        {settings.evaluationSize === SIZES.max
                                            ? t("{minutes} min, the exam in full", { minutes: exam.minutes })
                                            : t("{minutes} min", {
                                                minutes: exam.sizes[settings.evaluationSize - SIZES.min],
                                            })}
                                    </span>
                                </span>
                            </label>
                            <label className="exercise-setting">
                                <span>{t("Timed")}</span>
                                <span>
                                    <input
                                        type="checkbox"
                                        checked={settings.evaluationTimed}
                                        onChange={(event) =>
                                            onChangeSettings({ ...settings, evaluationTimed: event.target.checked })}
                                    />{" "}
                                    <span className="practice-detail">
                                        {t("each part in its time, as in the exam")}
                                    </span>
                                </span>
                            </label>
                            <p className="practice-detail">
                                {t(
                                    "Your level is set in the settings. What you write in an evaluation is not taken into your vocabulary.",
                                )}
                            </p>
                        </>
                    )}
                    {error && <p className="practice-note error">{error}</p>}
                    <button className="primary" disabled={busy || !exam} onClick={begin}>
                        {busy ? t("Starting…") : t("Start the evaluation")}
                    </button>
                </section>
            </div>
        </div>
    );
}
