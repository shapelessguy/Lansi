// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { useCallback, useEffect, useMemo, useState } from "react";

import {
    byDay,
    describeSource,
    fetchLogs,
    type Log,
    LOG_KINDS,
    type LogKind,
    LOGS_AT_A_TIME,
    matchesLog,
    shortened,
} from "../lib/logs";

interface Props {
    /** Whether the panel is shown: the logs are fetched again each time it is. */
    active: boolean;
    /** Changes when logs may have been kept since, to fetch them again. */
    revision: number;
    /** Opens the book a log was written in. */
    onOpenBook: (id: string) => void;
}

type State =
    | { status: "loading" }
    | { status: "error"; message: string }
    | { status: "ready"; logs: Log[]; more: boolean };

function time(seconds: number): string {
    return new Date(seconds * 1000).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}

/**
 * The logs of everything the learner did: the exercises of the sessions of
 * practice, what was translated and what was asked about it, the latest
 * first. They are written for the models that work out what the learner
 * can do, and are only read here: none can be changed or taken out.
 */
export function LogsPanel({ active, revision, onOpenBook }: Props) {
    const [state, setState] = useState<State>({ status: "loading" });
    const [kinds, setKinds] = useState<ReadonlySet<LogKind>>(() => new Set(Object.keys(LOG_KINDS) as LogKind[]));
    const [query, setQuery] = useState("");
    // the long logs shown whole, by their ids
    const [opened, setOpened] = useState<ReadonlySet<number>>(new Set());

    function toggleOpened(id: number) {
        const next = new Set(opened);
        if (!next.delete(id)) {
            next.add(id);
        }
        setOpened(next);
    }

    const load = useCallback(() => {
        let stopped = false;
        fetchLogs().then(
            (logs) => stopped || setState({ status: "ready", logs, more: logs.length === LOGS_AT_A_TIME }),
            (error: Error) => stopped || setState({ status: "error", message: error.message }),
        );
        return () => {
            stopped = true;
        };
    }, []);

    useEffect(() => (active ? load() : undefined), [active, revision, load]);

    function loadMore(logs: Log[]) {
        fetchLogs(logs.at(-1)?.id).then(
            (older) => setState({ status: "ready", logs: [...logs, ...older], more: older.length === LOGS_AT_A_TIME }),
            (error: Error) => setState({ status: "error", message: error.message }),
        );
    }

    function toggle(kind: LogKind) {
        const next = new Set(kinds);
        if (!next.delete(kind)) {
            next.add(kind);
        }
        setKinds(next);
    }

    const shown = useMemo(
        () => (state.status === "ready" ? state.logs.filter((log) => matchesLog(log, kinds, query.trim())) : []),
        [state, kinds, query],
    );

    return (
        <>
            <div className="sidebar-controls">
                <input
                    type="search"
                    placeholder="Search the logs"
                    aria-label="Search the logs"
                    value={query}
                    onChange={(event) => setQuery(event.target.value)}
                />
                <div className="log-kinds" role="group" aria-label="What the logs are of">
                    {(Object.keys(LOG_KINDS) as LogKind[]).map((kind) => (
                        <button
                            key={kind}
                            aria-pressed={kinds.has(kind)}
                            onClick={() => toggle(kind)}
                        >
                            {LOG_KINDS[kind]}
                        </button>
                    ))}
                </div>
            </div>
            {state.status === "loading" && <p className="sidebar-note">Loading the logs…</p>}
            {state.status === "error" && <p className="sidebar-note error">{state.message}</p>}
            {state.status === "ready" && state.logs.length === 0 && (
                <p className="sidebar-note">
                    What you do is logged here: the exercises you finish, what you translate and what you ask about it.
                </p>
            )}
            {state.status === "ready" && state.logs.length > 0 && (
                <div className="log-list">
                    {shown.length === 0 && <p className="sidebar-note">No log is like that.</p>}
                    {byDay(shown).map(({ day, logs }) => (
                        <section key={day} className="log-day">
                            <h3>{day}</h3>
                            <ul>
                                {logs.map((log) => {
                                    const where = describeSource(log);
                                    const { source } = log;
                                    const start = shortened(log.content);
                                    const whole = opened.has(log.id);
                                    return (
                                        <li
                                            key={log.id}
                                            className={`log-entry ${log.kind}${whole ? " opened" : ""}`}
                                        >
                                            <div className="log-head">
                                                <span className="log-kind">{LOG_KINDS[log.kind] ?? log.kind}</span>
                                                <span className="log-subject" title={log.subject}>
                                                    {log.subject}
                                                </span>
                                                <span className="log-time">{time(log.writtenAt)}</span>
                                            </div>
                                            <p className="log-content">{start && !whole ? start : log.content}</p>
                                            {start && (
                                                <button
                                                    className="link log-toggle"
                                                    aria-expanded={whole}
                                                    onClick={() => toggleOpened(log.id)}
                                                >
                                                    {whole ? "Show less" : "Show more"}
                                                </button>
                                            )}
                                            {where && (
                                                <p className="log-where">
                                                    {source.kind === "book" && source.id
                                                        ? (
                                                            <button
                                                                className="link"
                                                                onClick={() => onOpenBook(source.id!)}
                                                            >
                                                                {where}
                                                            </button>
                                                        )
                                                        : where}
                                                </p>
                                            )}
                                        </li>
                                    );
                                })}
                            </ul>
                        </section>
                    ))}
                    {state.more && (
                        <button className="log-more" onClick={() => loadMore(state.logs)}>Older logs</button>
                    )}
                </div>
            )}
        </>
    );
}
