// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { useCallback, useEffect, useMemo, useState } from "react";
import { canAsk } from "../lib/models";

import type { ProfileUsage } from "../lib/checker";
import { interfaceLanguage, languageName, plural, t } from "../lib/i18n";
import {
    answeredOf,
    choosingOf,
    clampInstances,
    DEFAULT_INSTANCES,
    endSession,
    type ExerciseInfo,
    fetchExercises,
    fetchLessons,
    fetchPracticeSessions,
    fetchSession,
    interfaceAddress,
    type Learner,
    type Lesson,
    lessonsRead,
    lessonsToReview,
    optionsOf,
    type OptionValue,
    type PracticeSession,
    resumeAt,
    scoreOf,
    sessionTitleOf,
    startSession,
    stepExercise,
} from "../lib/practice";
import { exerciseVocabularyOf, type Settings } from "../lib/settings";
import type { BackgroundTask } from "../lib/tasks";
import {
    createTopic,
    deleteTopic,
    embedVocabulary,
    fetchTopics,
    forgetIcon,
    remakeIcon,
    type Topic,
} from "../lib/topics";
import { type ChosenExercise, ExerciseSettings } from "./ExerciseSettings";
import { ExerciseView } from "./ExerciseView";
import { LevelBadge } from "./Level";
import { TimeLeft } from "./TimeLeft";
import { TopicList } from "./TopicList";

interface Props {
    /** Whether practice is on show, which is when the vocabulary is embedded for the topics. */
    active: boolean;
    settings: Settings;
    learner: Learner;
    /** The words of the set of the vocabulary that goes by `id`, as they are now, or null if it is gone. */
    wordsOfSet: (id: string) => Promise<string[] | null>;
    /** Changes when an icon of a topic has been made, so that the topics are fetched again. */
    topicsRevision: number;
    /** The task that embeds the vocabulary in the background, while it runs. */
    embedding: BackgroundTask | null;
    onUsage: (used: ProfileUsage[]) => void;
    onTask: (task: BackgroundTask) => void;
    /** Keeps the settings changed, such as the options of an exercise. */
    onChangeSettings: (next: Settings) => void;
    onOpenSettings: () => void;
    /** Has a text of an exercise of a session read aloud, which the exercise numbers `number`. */
    onReadAloud: (sessionId: string, exercise: string, number: number, text: string) => void;
    /** A session left unfinished to take up, as chosen among the practice sessions, with what tells it from before. */
    resuming?: { session: PracticeSession; nonce: number } | null;
}

type Loaded<T> = { status: "loading" } | { status: "error"; message: string } | { status: "ready"; items: T[] };

/**
 * Practice: a lesson, the topics to talk about and the exercises are
 * chosen in three columns, and the exercises are then done one after
 * another in a session. What is answered is logged by the server as it goes.
 */
export function Practice(
    {
        active,
        settings,
        learner,
        wordsOfSet,
        topicsRevision,
        embedding,
        onUsage,
        onTask,
        onChangeSettings,
        onOpenSettings,
        onReadAloud,
        resuming,
    }: Props,
) {
    const language = settings.language;
    const [lessons, setLessons] = useState<Loaded<Lesson>>({ status: "loading" });
    const [topics, setTopics] = useState<Loaded<Topic>>({ status: "loading" });
    // the topics chosen for the next session, by their ids
    const [chosenTopics, setChosenTopics] = useState<string[]>([]);
    const [addingTopic, setAddingTopic] = useState(false);
    const [exercises, setExercises] = useState<Loaded<ExerciseInfo>>({ status: "loading" });
    const [lessonId, setLessonId] = useState<string | null>(null);
    // the exercises chosen, with how many instances of each, in the order they were chosen
    const [chosen, setChosen] = useState<Record<string, number>>({});
    const [session, setSession] = useState<PracticeSession | null>(null);
    // which of the exercises of the session is being done
    const [at, setAt] = useState(0);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);
    // the session that ended last, to say how it went
    const [ended, setEnded] = useState<PracticeSession | null>(null);
    // every session there was, the latest first, which is what a session left open is taken up from
    const [history, setHistory] = useState<PracticeSession[]>([]);
    const loadHistory = useCallback(() => {
        fetchPracticeSessions().then(setHistory, () => undefined);
    }, []);
    // the sessions are listed again whenever one starts or ends
    useEffect(loadHistory, [loadHistory, session?.id, ended]);
    const unfinished = session ? null : history.find((each) => each.status === "running") ?? null;
    // the lessons done, which are those whose theory has been read
    const read = useMemo(
        () =>
            lessonsRead(
                history,
                exercises.status === "ready"
                    ? exercises.items.filter((each) => each.theory).map((each) => each.id)
                    : [],
                language,
            ),
        [history, exercises, language],
    );

    // the exercises are listed again in the language of the interface when it changes
    const shownIn = interfaceLanguage();
    const load = useCallback(() => {
        setLessons({ status: "loading" });
        setExercises({ status: "loading" });
        fetchLessons(language).then(
            (items) => setLessons({ status: "ready", items }),
            (failed: Error) => setLessons({ status: "error", message: failed.message }),
        );
        fetchExercises().then(
            (items) => setExercises({ status: "ready", items }),
            (failed: Error) => setExercises({ status: "error", message: failed.message }),
        );
    }, [language, shownIn]);

    useEffect(load, [load]);
    useEffect(() => setLessonId(null), [language]);

    useEffect(() => {
        let current = true;
        fetchTopics().then(
            (items) => {
                if (current) {
                    // icons made since are fetched again
                    items.forEach((topic) => forgetIcon(topic.id));
                    setTopics({ status: "ready", items });
                    setChosenTopics((chosen) => chosen.filter((id) => items.some((topic) => topic.id === id)));
                }
            },
            (failed: Error) => current && setTopics({ status: "error", message: failed.message }),
        );
        return () => {
            current = false;
        };
    }, [topicsRevision]);

    // The words of the vocabulary are embedded once, in the background, so
    // that the words of a topic can be found when a session starts.
    const vocabulary = exerciseVocabularyOf(settings, language);
    const embedFor = active && settings.exerciseTopicWords && vocabulary !== "none"
            && canAsk(settings.embeddingModel, learner.apiKey)
        ? settings.embeddingModel
        : null;
    useEffect(() => {
        if (!embedFor) {
            return;
        }
        embedVocabulary(language, embedFor, learner.apiKey).then(
            ({ task }) => task && onTask(task),
            () => undefined,
        );
    }, [embedFor, language, learner.apiKey, onTask]);

    function addTopic(title: string, description: string) {
        setAddingTopic(true);
        setError(null);
        createTopic(title, description, settings.imageModel, learner.apiKey).then(
            ({ topic, task }) => {
                setTopics((loaded) => ({
                    status: "ready",
                    items: [topic, ...(loaded.status === "ready" ? loaded.items : [])],
                }));
                setChosenTopics((chosen) => [...chosen, topic.id]);
                if (task) {
                    onTask(task);
                }
            },
            (failed: Error) => setError(failed.message),
        ).finally(() => setAddingTopic(false));
    }

    function removeTopic(id: string) {
        deleteTopic(id).then(
            () => {
                setTopics((loaded) =>
                    loaded.status === "ready"
                        ? { status: "ready", items: loaded.items.filter((topic) => topic.id !== id) }
                        : loaded
                );
                setChosenTopics((chosen) => chosen.filter((each) => each !== id));
            },
            (failed: Error) => setError(failed.message),
        );
    }

    function iconAgain(id: string) {
        setError(null);
        remakeIcon(id, settings.imageModel, learner.apiKey).then(
            ({ task }) => (task ? onTask(task) : setError(t("Add your OpenRouter key to make icons."))),
            (failed: Error) => setError(failed.message),
        );
    }

    function topicTitle(id: string): string {
        return (topics.status === "ready" && topics.items.find((topic) => topic.id === id)?.title) || "a topic";
    }

    function lessonTitle(id: string): string {
        return (lessons.status === "ready" && lessons.items.find((lesson) => lesson.id === id)?.title) || id;
    }

    function sessionTitle(of: PracticeSession): string {
        return sessionTitleOf(of, lessonTitle, titleOf);
    }

    function titleOf(id: string): string {
        return (exercises.status === "ready" && exercises.items.find((each) => each.id === id)?.title) || id;
    }

    function isTheory(id: string): boolean {
        return exercises.status === "ready" && exercises.items.some((each) => each.id === id && each.theory);
    }

    /** Whether an exercise is done once, as theory is, or one whose manifest says so, such as correcting a text. */
    function isOnce(id: string): boolean {
        return isTheory(id)
            || (exercises.status === "ready" && exercises.items.some((each) => each.id === id && each.once));
    }

    /** Chooses a lesson, or leaves it out again, which makes the session a review. */
    function chooseLesson(id: string) {
        const leftOut = id === lessonId;
        setLessonId(leftOut ? null : id);
        if (leftOut) {
            // theory is that of a lesson
            setChosen((current) => Object.fromEntries(Object.entries(current).filter(([each]) => !isTheory(each))));
        }
    }

    /** Chooses an exercise or leaves it out. Theory is done once, before the others. */
    /** The options of an exercise, as they were last set. */
    function optionsFor(exercise: ExerciseInfo): Record<string, OptionValue> {
        return optionsOf(exercise, settings.exerciseOptions[exercise.id]);
    }

    function setOption(exercise: ExerciseInfo, name: string, value: OptionValue) {
        onChangeSettings({
            ...settings,
            exerciseOptions: {
                ...settings.exerciseOptions,
                [exercise.id]: { ...optionsFor(exercise), [name]: value },
            },
        });
    }

    /** How many times an exercise is done, as it was last set. */
    function instancesOf(id: string): number {
        const remembered = settings.exerciseInstances[id];
        return remembered === undefined ? DEFAULT_INSTANCES : clampInstances(remembered);
    }

    function setInstances(exercise: ExerciseInfo, instances: number) {
        setChosen((current) => ({ ...current, [exercise.id]: instances }));
        onChangeSettings({
            ...settings,
            exerciseInstances: { ...settings.exerciseInstances, [exercise.id]: instances },
        });
    }

    /** How many minutes an exercise may take, as it was last set, 0 for no limit. */
    function minutesOf(id: string): number {
        return settings.exerciseMinutes[id] ?? 0;
    }

    function setMinutes(exercise: ExerciseInfo, minutes: number) {
        onChangeSettings({
            ...settings,
            exerciseMinutes: { ...settings.exerciseMinutes, [exercise.id]: minutes },
        });
    }

    /** Takes what the server has of the session, such as when its exercise started, which its time goes by. */
    function refresh(current: PracticeSession) {
        fetchSession(current.id).then(
            (found) => setSession((shown) => (shown?.id === found.id ? found : shown)),
            () => undefined,
        );
    }

    // an exercise chosen that cannot be with the lesson and the topics chosen since is left out
    useEffect(() => {
        if (exercises.status !== "ready") {
            return;
        }
        const left = exercises.items.filter((exercise) => chosen[exercise.id] !== undefined && unavailable(exercise));
        if (left.length > 0) {
            setChosen((current) =>
                Object.fromEntries(Object.entries(current).filter(([id]) => !left.some((each) => each.id === id)))
            );
        }
    });

    /** Why an exercise cannot be chosen with the lesson and the topics chosen, or null if it can. */
    function unavailable(exercise: ExerciseInfo): string | null {
        if (exercise.theory && !lessonId) {
            return t("Theory is that of a lesson: choose one");
        }
        if (exercise.lesson === false && exercise.topics === false && (lessonId || chosenTopics.length > 0)) {
            return t("It is done on its own, with no lesson or topic: leave them unchosen");
        }
        return null;
    }

    function toggle(id: string) {
        setChosen(({ [id]: had, ...rest }) => {
            if (had !== undefined) {
                return rest;
            }
            if (isTheory(id)) {
                return { [id]: 1, ...rest };
            }
            return { ...rest, [id]: isOnce(id) ? 1 : instancesOf(id) };
        });
    }

    function begin() {
        const lesson = lessonId;
        setBusy(true);
        setError(null);
        setEnded(null);
        const known = vocabulary === "all" || vocabulary === "none" ? Promise.resolve(null) : wordsOfSet(vocabulary);
        known.then((setWords) =>
            startSession(
                language,
                lesson,
                chosen,
                chosenTopics,
                choosingOf(settings, vocabulary, setWords),
                learner.apiKey,
                Object.fromEntries(
                    (exercises.status === "ready" ? exercises.items : [])
                        .filter((exercise) => chosen[exercise.id] !== undefined)
                        .map((exercise) => [exercise.id, optionsFor(exercise)]),
                ),
                Object.fromEntries(Object.keys(chosen).map((id) => [id, isTheory(id) ? 0 : minutesOf(id)])),
            )
        ).then(
            ({ usage, ...started }) => {
                onUsage(usage);
                setSession(started);
                setAt(0);
            },
            (failed: Error) => setError(failed.message),
        ).finally(() => setBusy(false));
    }

    /** Takes up a session where it was left, at its first exercise that is not finished. */
    function resume(left: PracticeSession) {
        setError(null);
        setEnded(null);
        setSession(left);
        setAt(resumeAt(left));
    }

    // a session taken up from the list of the practice sessions
    useEffect(() => {
        if (resuming) {
            resume(resuming.session);
        }
    }, [resuming]);

    function end(current: PracticeSession) {
        setBusy(true);
        endSession(current.id, "finished", learner).then(
            ({ session: done, usage, tasks }) => {
                onUsage(usage);
                // the logs of the exercises it finished, written in the background
                tasks?.forEach(onTask);
                setSession(null);
                setEnded(done);
            },
            (failed: Error) => setError(failed.message),
        ).finally(() => setBusy(false));
    }

    /** Finishes the exercise being done, and goes on to the next, or ends the session after the last. */
    function next(current: PracticeSession) {
        const order = Object.keys(current.exercises);
        setBusy(true);
        setError(null);
        stepExercise(current.id, order[at], "finish", null, learner).then(
            ({ usage, tasks }) => {
                onUsage(usage);
                // the log of the exercise, written in the background
                tasks?.forEach(onTask);
                if (at + 1 < order.length) {
                    setAt(at + 1);
                    setBusy(false);
                } else {
                    end(current);
                }
            },
            (failed: Error) => {
                setError(failed.message);
                setBusy(false);
            },
        );
    }

    if (session) {
        const order = Object.keys(session.exercises);
        const exercise = order[at];
        const info = exercises.status === "ready" ? exercises.items.find((each) => each.id === exercise) : undefined;
        return (
            <div className="practice">
                <div className="practice-bar">
                    <span>
                        {/* a session of no lesson is told by its exercise alone */}
                        {(session.lesson || (session.lessons?.length ?? 0) > 0) && (
                            <>
                                <strong>{sessionTitle(session)}</strong>
                                {" · "}
                            </>
                        )}
                        {info?.title ?? exercise} {t("({at} of {count})", { at: at + 1, count: order.length })}
                        {
                            /* theory is about the lesson alone, and one of neither a lesson nor topics, such as a
                            review of the Anki cards, about nothing of the kind: neither has topics or words */
                        }
                        <span
                            className="practice-detail"
                            hidden={info?.theory || (info?.lesson === false && info?.topics === false)}
                        >
                            {session.topics.length > 0 && ` · ${session.topics.map(topicTitle).join(" + ")}`}
                            {session.words
                                && ` · ${
                                    t(
                                        session.words.mode === "only"
                                            ? "only {count} of your words"
                                            : "mostly {count} of your words",
                                        { count: session.words.lemmas.length },
                                    )
                                }`}
                        </span>
                    </span>
                    <TimeLeft
                        key={`${session.id}:${exercise}`}
                        session={session}
                        exercise={exercise}
                        onUp={() => next(session)}
                    />
                    {/* where the player of a story read aloud goes */}
                    <span className="speech-dock" data-speech-dock="practice" />
                    <span className="practice-actions">
                        {at + 1 < order.length && (
                            <button
                                disabled={busy}
                                title={t(
                                    "Leave this exercise as it is and go on to the next. What you answered is kept.",
                                )}
                                onClick={() => next(session)}
                            >
                                {t("Next exercise")}
                            </button>
                        )}
                        <button
                            disabled={busy}
                            title={t("Stop the whole session here. What you answered is kept.")}
                            onClick={() => end(session)}
                        >
                            {t("End session")}
                        </button>
                    </span>
                </div>
                {error && <p className="practice-note error">{error}</p>}
                <div className={info?.theory ? "practice-body wide" : "practice-body"}>
                    <ExerciseView
                        key={`${session.id}:${exercise}`}
                        sessionId={session.id}
                        exercise={exercise}
                        theory={info?.theory}
                        learner={learner}
                        onUsage={onUsage}
                        onFinish={() => next(session)}
                        onReadAloud={(text, number) => onReadAloud(session.id, exercise, number, text)}
                        onStarted={() => refresh(session)}
                    />
                </div>
            </div>
        );
    }

    const chosenCount = Object.keys(chosen).length;
    // the exercises chosen that have something to set, as they are listed
    const configured: ChosenExercise[] = (exercises.status === "ready" ? exercises.items : [])
        .filter((exercise) => chosen[exercise.id] !== undefined && !exercise.theory)
        .map((exercise) => ({
            exercise,
            instances: chosen[exercise.id],
            minutes: minutesOf(exercise.id),
            values: optionsFor(exercise),
        }));
    // what a session without a lesson goes over
    const reviewed = lessons.status === "ready" ? lessonsToReview(history, lessons.items, language) : [];
    return (
        <div className="practice">
            <div className="practice-body">
                {ended && (
                    <p className="practice-note">
                        {t("Session over: {done}", {
                            done: Object.entries(ended.progress)
                                .map(([id, progress]) =>
                                    ended.exercises[id]
                                        ? `${titleOf(id)} ${t("{count} answered", { count: progress.answered })}`
                                        : `${titleOf(id)} ${t("read")}`
                                )
                                .join(", "),
                        })}
                        {scoreOf(ended).percent !== null && ` · ${scoreOf(ended).percent}%`}.
                    </p>
                )}
                {unfinished && (
                    <div className="practice-resume">
                        <span>
                            <strong>{t("Not finished:")}</strong> {sessionTitle(unfinished)}
                            <span className="practice-detail">
                                {" · "}
                                {Object.keys(unfinished.exercises)
                                    .map((id) => `${titleOf(id)} ${answeredOf(unfinished, id)}`.trim())
                                    .join(", ")}
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
                        {t("The exercises are made by a model.")}{" "}
                        <button onClick={onOpenSettings}>{t("Add your OpenRouter key")}</button>
                    </p>
                )}
                <div className="practice-columns">
                    <section className="practice-column">
                        <h2>
                            {t("Lesson")} <span className="practice-hint">{t("one, or none to review")}</span>
                        </h2>
                        {lessons.status === "loading" && <p className="practice-note">{t("Loading lessons…")}</p>}
                        {lessons.status === "error" && (
                            <div className="practice-note error">
                                <p>{lessons.message}</p>
                                <button onClick={load}>{t("Try again")}</button>
                            </div>
                        )}
                        {lessons.status === "ready" && lessons.items.length === 0 && (
                            <p className="practice-note">
                                {t("There are no lessons for {language} yet.", { language: languageName(language) })}
                            </p>
                        )}
                        <ul className="practice-list">
                            {lessons.status === "ready" && lessons.items.map((lesson, number) => (
                                <li key={lesson.id}>
                                    <button
                                        className="practice-choice practice-radio practice-lesson"
                                        aria-pressed={lesson.id === lessonId}
                                        title={lesson.id === lessonId ? t("Click again to review instead") : undefined}
                                        onClick={() => chooseLesson(lesson.id)}
                                    >
                                        <span className="practice-number">{number + 1}</span>
                                        <span className="practice-title">{lesson.title}</span>
                                        {read.has(lesson.id)
                                            ? (
                                                <span
                                                    className="practice-read"
                                                    title={t("Theory read")}
                                                    aria-label={t("Theory read")}
                                                >
                                                    ✓
                                                </span>
                                            )
                                            : <span />}
                                        <LevelBadge level={lesson.level} />
                                    </button>
                                </li>
                            ))}
                        </ul>
                    </section>
                    <section className="practice-column">
                        <h2>
                            {t("Topics")} <span className="practice-hint">{t("optional")}</span>
                        </h2>
                        {topics.status === "loading" && <p className="practice-note">{t("Loading topics…")}</p>}
                        {topics.status === "error" && <p className="practice-note error">{topics.message}</p>}
                        {topics.status === "ready" && (
                            <TopicList
                                topics={topics.items}
                                chosen={chosenTopics}
                                adding={addingTopic}
                                revision={topicsRevision}
                                onToggle={(id) =>
                                    setChosenTopics((current) =>
                                        current.includes(id) ? current.filter((each) => each !== id) : [...current, id]
                                    )}
                                onAdd={addTopic}
                                onDelete={removeTopic}
                                onRemakeIcon={iconAgain}
                            />
                        )}
                        {chosenTopics.length > 1 && (
                            <p className="practice-detail">
                                {settings.exerciseMixTopics
                                    ? t("The topics are mixed.")
                                    : t("One of them is drawn for the session.")}
                            </p>
                        )}
                        {embedding && (
                            <p className="practice-detail">
                                {t("Embedding {name}, to find the words of each topic: {done} of {total} batches.", {
                                    name: embedding.title,
                                    done: embedding.done,
                                    total: embedding.total,
                                })}
                            </p>
                        )}
                    </section>
                    <section className="practice-column">
                        <h2>
                            {t("Exercises")} <span className="practice-hint">{t("one or more")}</span>
                        </h2>
                        {exercises.status === "loading" && <p className="practice-note">{t("Loading exercises…")}</p>}
                        {exercises.status === "error" && <p className="practice-note error">{exercises.message}</p>}
                        <ul className="practice-list">
                            {exercises.status === "ready"
                                && exercises.items.map((exercise) => (
                                    <li key={exercise.id} className="practice-exercise">
                                        <button
                                            className="practice-choice practice-exercise-choice"
                                            aria-pressed={chosen[exercise.id] !== undefined}
                                            disabled={unavailable(exercise) !== null}
                                            // what it is, which its icon stands for, is said as the mouse is over it
                                            title={unavailable(exercise) ?? exercise.description}
                                            onClick={() =>
                                                toggle(exercise.id)}
                                        >
                                            <span className="practice-exercise-icon" aria-hidden>
                                                {exercise.icon
                                                    ? (
                                                        <span
                                                            className="practice-exercise-glyph"
                                                            style={{
                                                                maskImage: `url("${
                                                                    interfaceAddress(`${exercise.id}/ui/icon.svg`)
                                                                }")`,
                                                            }}
                                                        />
                                                    )
                                                    : exercise.title.charAt(0)}
                                            </span>
                                            <span className="practice-title">{exercise.title}</span>
                                        </button>
                                        {/* its settings, under it as it is chosen */}
                                        {configured.filter((each) =>
                                            each.exercise.id === exercise.id
                                        ).map((each) => (
                                            <ExerciseSettings
                                                key={exercise.id}
                                                chosen={each}
                                                onInstances={setInstances}
                                                onMinutes={setMinutes}
                                                onChange={setOption}
                                            />
                                        ))}
                                    </li>
                                ))}
                        </ul>
                    </section>
                </div>
                {error && <p className="practice-note error">{error}</p>}
            </div>
            <div className="practice-footer">
                <span className="practice-summary">
                    {lessonId
                        ? <strong>{lessonTitle(lessonId)}</strong>
                        : reviewed.length > 0
                        ? (
                            <strong title={reviewed.map(lessonTitle).join(", ")}>
                                {plural(
                                    reviewed.length,
                                    "Review of the last lesson",
                                    "Review of the last {count} lessons",
                                )}
                            </strong>
                        )
                        : <span className="practice-detail">{t("Choose a lesson")}</span>}
                    <span className="practice-detail">
                        {" · "}
                        {chosenTopics.length > 0 ? chosenTopics.map(topicTitle).join(" + ") : t("everyday life")}
                        {" · "}
                        {chosenCount > 0
                            ? Object.entries(chosen)
                                .map(([id, times]) => (isOnce(id) ? titleOf(id) : `${titleOf(id)} ×${times}`))
                                .join(", ")
                            : t("choose an exercise")}
                    </span>
                </span>
                <button
                    className="primary"
                    disabled={busy || (!lessonId && reviewed.length === 0) || chosenCount === 0}
                    onClick={begin}
                >
                    {busy ? t("Starting…") : t("Start")}
                </button>
            </div>
        </div>
    );
}
