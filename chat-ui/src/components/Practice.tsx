// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { useCallback, useEffect, useMemo, useState } from "react";

import type { ProfileUsage } from "../lib/checker";
import {
    answeredOf,
    choosingOf,
    clampInstances,
    DEFAULT_INSTANCES,
    defaultOptions,
    endSession,
    type ExerciseInfo,
    fetchExercises,
    fetchLessons,
    fetchSessions,
    type Learner,
    type Lesson,
    lessonsRead,
    lessonsToReview,
    MAX_INSTANCES,
    type PracticeSession,
    resumeAt,
    scoreOf,
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
import { ExerciseView } from "./ExerciseView";
import { LevelBadge } from "./Level";
import { SessionHistory } from "./SessionHistory";
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
    onOpenSettings: () => void;
    /** Has a text of an exercise of a session read aloud, which the exercise numbers `number`. */
    onReadAloud: (sessionId: string, exercise: string, number: number, text: string) => void;
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
        onOpenSettings,
        onReadAloud,
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
    // the options chosen for the exercises, by exercise, kept while an exercise is left out
    const [chosenOptions, setChosenOptions] = useState<Record<string, Record<string, string>>>({});
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
        fetchSessions().then(setHistory, () => undefined);
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
    }, [language]);

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
    const embedFor = active && settings.exerciseTopicWords && vocabulary !== "none" && learner.apiKey
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
            ({ task }) => (task ? onTask(task) : setError("Add your OpenRouter key to make icons.")),
            (failed: Error) => setError(failed.message),
        );
    }

    function topicTitle(id: string): string {
        return (topics.status === "ready" && topics.items.find((topic) => topic.id === id)?.title) || "a topic";
    }

    function lessonTitle(id: string): string {
        return (lessons.status === "ready" && lessons.items.find((lesson) => lesson.id === id)?.title) || id;
    }

    /** What a session is of: its lesson, or the lessons it reviews. */
    function sessionTitle(of: PracticeSession): string {
        if (of.lesson) {
            return lessonTitle(of.lesson);
        }
        const count = of.lessons?.length ?? 0;
        return `Review of ${count} ${count === 1 ? "lesson" : "lessons"}`;
    }

    function titleOf(id: string): string {
        return (exercises.status === "ready" && exercises.items.find((each) => each.id === id)?.title) || id;
    }

    function isTheory(id: string): boolean {
        return exercises.status === "ready" && exercises.items.some((each) => each.id === id && each.theory);
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
    function toggle(id: string) {
        setChosen(({ [id]: had, ...rest }) => {
            if (had !== undefined) {
                return rest;
            }
            return isTheory(id) ? { [id]: 1, ...rest } : { ...rest, [id]: DEFAULT_INSTANCES };
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
                chosenOptions,
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

    function end(current: PracticeSession) {
        setBusy(true);
        endSession(current.id, "finished", learner).then(
            ({ session: done, usage }) => {
                onUsage(usage);
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
            ({ usage }) => {
                onUsage(usage);
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
                        <strong>{sessionTitle(session)}</strong>
                        {" · "}
                        {info?.title ?? exercise} ({at + 1} of {order.length})
                        {/* theory is about the lesson alone, and has no topics or words */}
                        <span className="practice-detail" hidden={info?.theory}>
                            {session.topics.length > 0 && ` · ${session.topics.map(topicTitle).join(" + ")}`}
                            {session.words
                                && ` · ${
                                    session.words.mode === "only" ? "only" : "mostly"
                                } ${session.words.lemmas.length} of your words`}
                        </span>
                    </span>
                    {/* where the player of a story read aloud goes */}
                    <span className="speech-dock" data-speech-dock="practice" />
                    <span className="practice-actions">
                        {at + 1 < order.length && (
                            <button
                                disabled={busy}
                                title="Leave this exercise as it is and go on to the next. What you answered is kept."
                                onClick={() => next(session)}
                            >
                                Next exercise
                            </button>
                        )}
                        <button
                            disabled={busy}
                            title="Stop the whole session here. What you answered is kept."
                            onClick={() => end(session)}
                        >
                            End session
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
                    />
                </div>
            </div>
        );
    }

    const chosenCount = Object.keys(chosen).length;
    // what a session without a lesson goes over
    const reviewed = lessons.status === "ready" ? lessonsToReview(history, lessons.items, language) : [];
    return (
        <div className="practice">
            <div className="practice-body">
                {ended && (
                    <p className="practice-note">
                        Session over: {Object.entries(ended.progress)
                            .map(([id, progress]) =>
                                ended.exercises[id] ? `${titleOf(id)} ${progress.logs} answered` : `${titleOf(id)} read`
                            )
                            .join(", ")}
                        {scoreOf(ended).percent !== null && ` · ${scoreOf(ended).percent}%`}.
                    </p>
                )}
                {unfinished && (
                    <div className="practice-resume">
                        <span>
                            <strong>Not finished:</strong> {sessionTitle(unfinished)}
                            <span className="practice-detail">
                                {" · "}
                                {Object.keys(unfinished.exercises)
                                    .map((id) => `${titleOf(id)} ${answeredOf(unfinished, id)}`.trim())
                                    .join(", ")}
                            </span>
                        </span>
                        <span className="practice-actions">
                            <button className="primary" onClick={() => resume(unfinished)}>Continue</button>
                            <button disabled={busy} onClick={() => end(unfinished)}>End it</button>
                        </span>
                    </div>
                )}
                {!learner.apiKey && (
                    <p className="practice-note">
                        The exercises are made by a model.{" "}
                        <button onClick={onOpenSettings}>Add your OpenRouter key</button>
                    </p>
                )}
                <div className="practice-columns">
                    <section className="practice-column">
                        <h2>
                            Lesson <span className="practice-hint">one, or none to review</span>
                        </h2>
                        {lessons.status === "loading" && <p className="practice-note">Loading lessons…</p>}
                        {lessons.status === "error" && (
                            <div className="practice-note error">
                                <p>{lessons.message}</p>
                                <button onClick={load}>Try again</button>
                            </div>
                        )}
                        {lessons.status === "ready" && lessons.items.length === 0 && (
                            <p className="practice-note">There are no lessons for {language} yet.</p>
                        )}
                        <ul className="practice-list">
                            {lessons.status === "ready" && lessons.items.map((lesson, number) => (
                                <li key={lesson.id}>
                                    <button
                                        className="practice-choice practice-radio practice-lesson"
                                        aria-pressed={lesson.id === lessonId}
                                        title={lesson.id === lessonId ? "Click again to review instead" : undefined}
                                        onClick={() => chooseLesson(lesson.id)}
                                    >
                                        <span className="practice-number">{number + 1}</span>
                                        <span className="practice-title">{lesson.title}</span>
                                        {read.has(lesson.id)
                                            ? (
                                                <span
                                                    className="practice-read"
                                                    title="Theory read"
                                                    aria-label="Theory read"
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
                            Topics <span className="practice-hint">optional</span>
                        </h2>
                        {topics.status === "loading" && <p className="practice-note">Loading topics…</p>}
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
                                    ? "The topics are mixed."
                                    : "One of them is drawn for the session."}
                            </p>
                        )}
                        {embedding && (
                            <p className="practice-detail">
                                Embedding {embedding.title}, to find the words of each topic: {embedding.done} of{" "}
                                {embedding.total} batches.
                            </p>
                        )}
                    </section>
                    <section className="practice-column">
                        <h2>
                            Exercises <span className="practice-hint">one or more</span>
                        </h2>
                        {exercises.status === "loading" && <p className="practice-note">Loading exercises…</p>}
                        {exercises.status === "error" && <p className="practice-note error">{exercises.message}</p>}
                        <ul className="practice-list">
                            {exercises.status === "ready"
                                && exercises.items.map((exercise) => (
                                    <li key={exercise.id} className="practice-exercise">
                                        <button
                                            className="practice-choice"
                                            aria-pressed={chosen[exercise.id] !== undefined}
                                            disabled={exercise.theory && !lessonId}
                                            title={exercise.theory && !lessonId
                                                ? "Theory is that of a lesson: choose one"
                                                : undefined}
                                            onClick={() =>
                                                toggle(exercise.id)}
                                        >
                                            <span className="practice-title">{exercise.title}</span>
                                            <span className="practice-detail">{exercise.description}</span>
                                        </button>
                                        {chosen[exercise.id] !== undefined && !exercise.theory && (
                                            <label className="practice-instances">
                                                <input
                                                    type="number"
                                                    min={1}
                                                    max={MAX_INSTANCES}
                                                    value={chosen[exercise.id]}
                                                    onChange={(event) =>
                                                        setChosen((current) => ({
                                                            ...current,
                                                            [exercise.id]: clampInstances(event.target.valueAsNumber),
                                                        }))}
                                                />
                                                times
                                            </label>
                                        )}
                                        {chosen[exercise.id] !== undefined
                                            && Object.entries(exercise.options ?? {}).map(([name, option]) => (
                                                <label key={name} className="practice-instances">
                                                    {option.label}
                                                    <select
                                                        value={chosenOptions[exercise.id]?.[name]
                                                            ?? defaultOptions(exercise)[name]}
                                                        onChange={(event) =>
                                                            setChosenOptions((current) => ({
                                                                ...current,
                                                                [exercise.id]: {
                                                                    ...defaultOptions(exercise),
                                                                    ...current[exercise.id],
                                                                    [name]: event.target.value,
                                                                },
                                                            }))}
                                                    >
                                                        {Object.entries(option.choices).map(([value, label]) => (
                                                            <option key={value} value={value}>{label}</option>
                                                        ))}
                                                    </select>
                                                </label>
                                            ))}
                                    </li>
                                ))}
                        </ul>
                    </section>
                </div>
                {error && <p className="practice-note error">{error}</p>}
                <SessionHistory
                    sessions={history}
                    sessionTitle={sessionTitle}
                    topicTitle={topicTitle}
                    exerciseTitle={titleOf}
                    onResume={resume}
                />
            </div>
            <div className="practice-footer">
                <span className="practice-summary">
                    {lessonId
                        ? <strong>{lessonTitle(lessonId)}</strong>
                        : reviewed.length > 0
                        ? (
                            <strong title={reviewed.map(lessonTitle).join(", ")}>
                                Review of the last {reviewed.length} {reviewed.length === 1 ? "lesson" : "lessons"}
                            </strong>
                        )
                        : <span className="practice-detail">Choose a lesson</span>}
                    <span className="practice-detail">
                        {" · "}
                        {chosenTopics.length > 0 ? chosenTopics.map(topicTitle).join(" + ") : "everyday life"}
                        {" · "}
                        {chosenCount > 0
                            ? Object.entries(chosen)
                                .map(([id, times]) => (isTheory(id) ? titleOf(id) : `${titleOf(id)} ×${times}`))
                                .join(", ")
                            : "choose an exercise"}
                    </span>
                </span>
                <button
                    className="primary"
                    disabled={busy || (!lessonId && reviewed.length === 0) || chosenCount === 0}
                    onClick={begin}
                >
                    {busy ? "Starting…" : "Start"}
                </button>
            </div>
        </div>
    );
}
