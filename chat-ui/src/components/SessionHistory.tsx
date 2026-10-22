// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { useState } from "react";

import { locale, type Message, t } from "../lib/i18n";
import { answeredOf, fetchSession, type Grade, type PracticeSession, scoreOf } from "../lib/practice";

interface Props {
    sessions: PracticeSession[];
    /** What a session was of: its lesson, or the lessons it reviewed. */
    sessionTitle: (session: PracticeSession) => string;
    topicTitle: (id: string) => string;
    exerciseTitle: (id: string) => string;
    /** Takes up a session that is still running where it was left. */
    onResume: (session: PracticeSession) => void;
}

/** How many sessions are listed, the latest first. */
const SHOWN = 20;
const STATUS = { running: "Not finished", finished: "Finished", abandoned: "Left" } as const satisfies Record<
    string,
    Message
>;
const RESULT = { right: "✓", partial: "~", wrong: "✗" } as const;
const RESULT_NAMES = { right: "right", partial: "partly right", wrong: "wrong" } as const satisfies Record<
    string,
    Message
>;

function when(seconds: number): string {
    return new Date(seconds * 1000).toLocaleString(locale(), {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
    });
}

/** How a session went, as a bar of its results with its score. */
function ScoreBar({ session }: { session: PracticeSession }) {
    const score = scoreOf(session);
    if (score.total === 0) {
        // nothing was there to answer, such as theory alone: it is done once read
        const done = session.status === "finished";
        const told = done ? t("Read") : t("Nothing to answer");
        return (
            <span className="history-score" title={told} aria-label={told}>
                <span className="history-bar" aria-hidden="true">
                    {done && <span className="read" style={{ width: "100%" }} />}
                </span>
                <span className="history-percent">{done ? "100%" : "–"}</span>
            </span>
        );
    }
    const part = (count: number) => `${(100 * count) / Math.max(1, score.total)}%`;
    const told = t("{right} right · {partial} almost · {wrong} wrong, of {total}", {
        right: score.right,
        partial: score.partial,
        wrong: score.wrong,
        total: score.total,
    });
    return (
        <span className="history-score" title={told} aria-label={told}>
            <span className="history-bar" aria-hidden="true">
                <span className="right" style={{ width: part(score.right) }} />
                <span className="partial" style={{ width: part(score.partial) }} />
                <span className="wrong" style={{ width: part(score.wrong) }} />
            </span>
            <span className="history-percent">{score.percent === null ? "–" : `${score.percent}%`}</span>
        </span>
    );
}

/** What was answered in a session, and the logs of its exercises by exercise. */
interface Done {
    grades: Grade[];
    logs: Record<string, string>;
}

/** The sessions there were, each with what was answered in it once it is opened. */
export function SessionHistory({ sessions, sessionTitle, topicTitle, exerciseTitle, onResume }: Props) {
    // what was done in each session that was opened, by its id
    const [done, setDone] = useState<Record<string, Done | "loading" | "failed">>({});

    function open(id: string) {
        if (done[id] && done[id] !== "failed") {
            return;
        }
        setDone((current) => ({ ...current, [id]: "loading" }));
        fetchSession(id).then(
            (found) => setDone((current) => ({ ...current, [id]: { grades: found.grades, logs: found.logs } })),
            () => setDone((current) => ({ ...current, [id]: "failed" })),
        );
    }

    if (sessions.length === 0) {
        return null;
    }
    return (
        <section className="history">
            <h2>{t("Sessions")}</h2>
            <ul className="history-list">
                {sessions.slice(0, SHOWN).map((session) => {
                    const shown = done[session.id];
                    return (
                        <li key={session.id} className={`history-item ${session.status}`}>
                            <details onToggle={(event) => event.currentTarget.open && open(session.id)}>
                                <summary>
                                    <span className="history-when">{when(session.started_at)}</span>
                                    <span className="history-what">
                                        <strong>{sessionTitle(session)}</strong>
                                        {session.topics.length > 0
                                            && ` · ${session.topics.map(topicTitle).join(" + ")}`}
                                        <span className="practice-detail">
                                            {" · "}
                                            {Object.keys(session.exercises)
                                                .map((id) => `${exerciseTitle(id)} ${answeredOf(session, id)}`.trim())
                                                .join(", ")}
                                        </span>
                                    </span>
                                    <ScoreBar session={session} />
                                    <span className="history-status">{t(STATUS[session.status])}</span>
                                </summary>
                                {shown === "loading" && <p className="practice-note">{t("Loading…")}</p>}
                                {shown === "failed" && (
                                    <p className="practice-note error">{t("The answers could not be had.")}</p>
                                )}
                                {typeof shown === "object" && shown.grades.length === 0 && (
                                    <p className="practice-note">{t("Nothing was answered.")}</p>
                                )}
                                {typeof shown === "object" && shown.grades.length > 0 && (
                                    <ol className="history-grades">
                                        {shown.grades.map((grade, number) => (
                                            <li key={number} className={grade.result}>
                                                <span className="history-result" title={t(RESULT_NAMES[grade.result])}>
                                                    {RESULT[grade.result]}
                                                </span>
                                                <span>
                                                    {grade.task && <span className="history-task">{grade.task}</span>}
                                                    {grade.answer}
                                                    {grade.correction && (
                                                        <span className="history-correction">→ {grade.correction}</span>
                                                    )}
                                                    {grade.note && (
                                                        <span className="practice-detail">{grade.note}</span>
                                                    )}
                                                </span>
                                            </li>
                                        ))}
                                    </ol>
                                )}
                                {typeof shown === "object"
                                    && Object.entries(shown.logs).map(([exercise, log]) => (
                                        // what the app keeps of the exercise for the models that profile the learner
                                        <div key={exercise} className="history-log">
                                            <strong>{t("Log of {name}", { name: exerciseTitle(exercise) })}</strong>
                                            <p>{log}</p>
                                        </div>
                                    ))}
                            </details>
                            {session.status === "running" && (
                                <button
                                    className="primary history-resume"
                                    onClick={() => onResume(session)}
                                >
                                    {t("Continue")}
                                </button>
                            )}
                        </li>
                    );
                })}
            </ul>
        </section>
    );
}
