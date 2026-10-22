// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { useEffect, useState } from "react";

import { interfaceLanguage, locale, t } from "../lib/i18n";
import {
    type ExerciseInfo,
    type ExerciseProgress,
    fetchExercises,
    fetchLessons,
    fetchSession,
    fetchSessions,
    type Grade,
    interfaceAddress,
    type Lesson,
    type PracticeSession,
    sessionTitleOf,
} from "../lib/practice";
import { fetchTopics, type Topic } from "../lib/topics";
import { GradeRound } from "./GradeRound";

interface Props {
    /** Whether the tab is shown, which is when the exercises are listed. */
    active: boolean;
    /** The language learned, whose lessons the exercises are told by. */
    language: string;
    /** Changes when an exercise may have been done or logged, so that they are listed again. */
    revision: number;
    /**
     * Does an exercise of a session that is over again, in Practice: exactly
     * as it was, or, if `fresh`, with the same settings and made anew.
     */
    onReplay: (session: PracticeSession, exercise: string, fresh?: boolean) => void;
}

interface Listed {
    sessions: PracticeSession[];
    lessons: Lesson[];
    topics: Topic[];
    exercises: ExerciseInfo[];
}

/** An exercise done in a session, as it is listed. */
interface Done {
    session: PracticeSession;
    exercise: string;
    progress: ExerciseProgress;
}

/** What was done in a session that was opened: the grades of its exercises and their logs. */
type Opened = { grades: Grade[]; logs: Record<string, string> } | "loading" | "failed";

/** The exercises done, the latest first: each that was started, of every session of practice. */
function doneOf(sessions: PracticeSession[]): Done[] {
    return sessions
        .flatMap((session) =>
            Object.entries(session.progress)
                .filter(([, progress]) => progress.status !== "pending")
                .map(([exercise, progress]) => ({ session, exercise, progress }))
        )
        .sort((one, other) =>
            (other.progress.started_at ?? other.session.started_at)
            - (one.progress.started_at ?? one.session.started_at)
        );
}

function dayOf(seconds: number): string {
    return new Date(seconds * 1000).toLocaleDateString(locale(), {
        weekday: "short",
        day: "numeric",
        month: "short",
        year: "numeric",
    });
}

function timeOf(seconds: number): string {
    return new Date(seconds * 1000).toLocaleTimeString(locale(), { hour: "2-digit", minute: "2-digit" });
}

/**
 * Every exercise done, the latest first and by day, in the panel of the
 * logs: what it was of and how it went, and, once opened, each round of it
 * as a card of its own, what it gave and what was answered, with its log.
 * One whose instances were kept can be done again as it was.
 */
export function ExercisesDone({ active, language, revision, onReplay }: Props) {
    const [listed, setListed] = useState<Listed | null>(null);
    const [error, setError] = useState<string | null>(null);
    // what was done in each session opened, by its id
    const [opened, setOpened] = useState<Record<string, Opened>>({});
    // what is searched for, and the exercises chosen to be shown alone, none for all
    const [query, setQuery] = useState("");
    const [chosen, setChosen] = useState<Set<string>>(new Set());

    function choose(exercise: string) {
        setChosen((current) => {
            const next = new Set(current);
            if (!next.delete(exercise)) {
                next.add(exercise);
            }
            return next;
        });
    }

    // listed again in the language of the interface when it changes
    const shownIn = interfaceLanguage();
    useEffect(() => {
        if (!active) {
            return;
        }
        let current = true;
        Promise.all([fetchSessions(), fetchLessons(language), fetchTopics(), fetchExercises()]).then(
            ([sessions, lessons, topics, exercises]) => {
                if (current) {
                    setListed({ sessions, lessons, topics, exercises });
                    // what was done is had again as it is opened
                    setOpened({});
                    setError(null);
                }
            },
            (failed: Error) => current && setError(failed.message),
        );
        return () => {
            current = false;
        };
    }, [active, language, revision, shownIn]);

    function open(sessionId: string) {
        if (opened[sessionId] && opened[sessionId] !== "failed") {
            return;
        }
        setOpened((current) => ({ ...current, [sessionId]: "loading" }));
        fetchSession(sessionId).then(
            (found) =>
                setOpened((current) => ({ ...current, [sessionId]: { grades: found.grades, logs: found.logs } })),
            () => setOpened((current) => ({ ...current, [sessionId]: "failed" })),
        );
    }

    if (error) {
        return <p className="sidebar-note error">{error}</p>;
    }
    if (!listed) {
        return <p className="sidebar-note">{t("Loading…")}</p>;
    }
    const done = doneOf(listed.sessions);
    if (done.length === 0) {
        return <p className="sidebar-note">{t("No exercise done yet.")}</p>;
    }
    const lessonTitle = (id: string) => listed.lessons.find((lesson) => lesson.id === id)?.title || id;
    const info = (id: string) => listed.exercises.find((each) => each.id === id);
    const exerciseTitle = (id: string) => info(id)?.title || id;
    const topicTitle = (id: string) => listed.topics.find((topic) => topic.id === id)?.title || t("a topic");
    // a session of no lesson, such as a review of the Anki cards, is told by its exercise
    const ofSession = (session: PracticeSession) =>
        session.lesson || session.lessons?.length ? sessionTitleOf(session, lessonTitle, exerciseTitle) : "";
    // the exercises there were, each once, in the order they are listed in Practice
    const kinds = listed.exercises.filter((exercise) => done.some((each) => each.exercise === exercise.id));
    const words = query.toLowerCase().split(/\s+/).filter(Boolean);
    const shown = done.filter(({ session, exercise }) => {
        if (chosen.size > 0 && !chosen.has(exercise)) {
            return false;
        }
        const about = [exerciseTitle(exercise), ofSession(session), ...session.topics.map(topicTitle)]
            .join(" ")
            .toLowerCase();
        return words.every((word) => about.includes(word));
    });
    const days: { day: string; items: Done[] }[] = [];
    for (const each of shown) {
        const day = dayOf(each.progress.started_at ?? each.session.started_at);
        if (days.at(-1)?.day !== day) {
            days.push({ day, items: [] });
        }
        days.at(-1)!.items.push(each);
    }
    return (
        <>
            <div className="sidebar-controls">
                <input
                    type="search"
                    placeholder={t("Search the exercises")}
                    aria-label={t("Search the exercises")}
                    value={query}
                    onChange={(event) => setQuery(event.target.value)}
                />
                <div className="log-kinds" role="group" aria-label={t("Which exercises are shown")}>
                    {kinds.map((exercise) => (
                        <button
                            key={exercise.id}
                            aria-pressed={chosen.has(exercise.id)}
                            onClick={() => choose(exercise.id)}
                        >
                            {exercise.title}
                        </button>
                    ))}
                </div>
            </div>
            <div className="log-list exercises-done">
                {shown.length === 0 && <p className="sidebar-note">{t("No exercise is like that.")}</p>}
                {days.map(({ day, items }) => (
                    <section key={day} className="log-day">
                        <h3>{day}</h3>
                        <ul>
                            {items.map(({ session, exercise, progress }) => {
                                const about = info(exercise);
                                const got = opened[session.id];
                                const grades = typeof got === "object"
                                    ? got.grades.filter((grade) => grade.exercise === exercise)
                                    : [];
                                const log = typeof got === "object" ? got.logs[exercise] : undefined;
                                const of = ofSession(session);
                                return (
                                    <li key={`${session.id}:${exercise}`} className="log-entry done-exercise">
                                        <details onToggle={(event) => event.currentTarget.open && open(session.id)}>
                                            <summary>
                                                <span className="done-exercise-icon" aria-hidden>
                                                    {about?.icon
                                                        ? (
                                                            <span
                                                                className="practice-exercise-glyph"
                                                                style={{
                                                                    maskImage: `url("${
                                                                        interfaceAddress(`${exercise}/ui/icon.svg`)
                                                                    }")`,
                                                                }}
                                                            />
                                                        )
                                                        : exerciseTitle(exercise).charAt(0)}
                                                </span>
                                                <span className="done-exercise-what">
                                                    <span className="log-head">
                                                        <span className="log-subject">{exerciseTitle(exercise)}</span>
                                                        <span className="log-time">
                                                            {timeOf(progress.started_at ?? session.started_at)}
                                                        </span>
                                                    </span>
                                                    <span className="log-where">
                                                        {[
                                                            of,
                                                            ...session.topics.map(topicTitle),
                                                            progress.replays ? t("done again") : "",
                                                        ].filter(Boolean).join(" · ")}
                                                    </span>
                                                    <span className="done-foot">
                                                        <Results progress={progress} />
                                                        {
                                                            /* to do it again, always in sight; one that makes nothing, such
                                                        as reviewing the Anki cards, goes one way only */
                                                        }
                                                        {session.status !== "running" && about?.instance && (
                                                            <span className="done-again">
                                                                {(progress.kept ?? 0) > 0 && (
                                                                    <button
                                                                        className="chip accent"
                                                                        onClick={(event) => {
                                                                            // in the summary, it does not open the card
                                                                            event.preventDefault();
                                                                            onReplay(session, exercise);
                                                                        }}
                                                                        title={t(
                                                                            "Do it again exactly as it was, with nothing made anew",
                                                                        )}
                                                                    >
                                                                        ↻ {t("Same")}
                                                                    </button>
                                                                )}
                                                                <button
                                                                    className="chip"
                                                                    onClick={(event) => {
                                                                        event.preventDefault();
                                                                        onReplay(session, exercise, true);
                                                                    }}
                                                                    title={t(
                                                                        "Do it again with the same lesson, topics and settings, made anew",
                                                                    )}
                                                                >
                                                                    ✦ {t("New")}
                                                                </button>
                                                            </span>
                                                        )}
                                                    </span>
                                                </span>
                                            </summary>
                                            {got === "loading" && <p className="sidebar-note">{t("Loading…")}</p>}
                                            {got === "failed" && (
                                                <p className="sidebar-note error">
                                                    {t("What was done could not be had.")}
                                                </p>
                                            )}
                                            {typeof got === "object" && grades.length === 0 && (
                                                <p className="sidebar-note">{t("Nothing was answered.")}</p>
                                            )}
                                            {grades.length > 0 && (
                                                // each round of the exercise, as a card of its own
                                                <ol className="done-rounds">
                                                    {grades.map((grade, number) => (
                                                        <GradeRound
                                                            key={number}
                                                            grade={grade}
                                                            label={t("Round {number}", { number: number + 1 })}
                                                        />
                                                    ))}
                                                </ol>
                                            )}
                                            {log && (
                                                <details className="done-log">
                                                    <summary>{t("Log")}</summary>
                                                    <p>{log}</p>
                                                </details>
                                            )}
                                        </details>
                                    </li>
                                );
                            })}
                        </ul>
                    </section>
                ))}
            </div>
        </>
    );
}

/** How an exercise went, out of what was answered: a bar of its results. */
function Results({ progress }: { progress: ExerciseProgress }) {
    const { right, partial, wrong } = progress.results;
    const total = right + partial + wrong;
    if (total === 0) {
        return null;
    }
    const part = (count: number) => `${(100 * count) / total}%`;
    const told = t("{right} right · {partial} almost · {wrong} wrong", { right, partial, wrong });
    return (
        <span className="done-results" title={told} aria-label={told}>
            <span className="history-bar" aria-hidden="true">
                <span className="right" style={{ width: part(right) }} />
                <span className="partial" style={{ width: part(partial) }} />
                <span className="wrong" style={{ width: part(wrong) }} />
            </span>
            <span className="done-count">{right}/{total}</span>
        </span>
    );
}
