// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { useCallback, useEffect, useState } from "react";

import { deleteMemory, fetchMemories, type Memory } from "../lib/tutor";

interface Props {
    /** Changes when memories may have been made or removed, so that they are listed again. */
    revision: number;
    onCount: (count: number) => void;
}

type Loaded =
    | { status: "loading" }
    | { status: "error"; message: string }
    | { status: "ready"; memories: Memory[]; removed: Memory[] };

/**
 * What the tutor remembers of the learner from one chat to the next, the
 * newest first, as it is told it in every chat: made when a chat is
 * closed, and removed by the tutor when it is no longer true, or by the
 * learner here. The general ones are of the learner, and the tutor is
 * told them in every chat. The strategy, how the tutor and the learner
 * agreed to hold the lessons, and the calendar, what they planned to do on
 * a day, the tutor writes down as soon as they agree, and looks up, as it
 * does the recap of a few lines every chat leaves. The calendar goes by
 * day, the days gone by greyed. What was removed is listed apart, with why
 * and by whom.
 */
export function MemoryList({ revision, onCount }: Props) {
    const [loaded, setLoaded] = useState<Loaded>({ status: "loading" });
    const load = useCallback(() => {
        fetchMemories().then(
            ({ memories, removed }) => {
                setLoaded({ status: "ready", memories, removed });
                onCount(memories.filter((memory) => memory.kind !== "recap").length);
            },
            (failed: Error) => setLoaded({ status: "error", message: failed.message }),
        );
    }, [onCount]);
    useEffect(load, [load, revision]);

    function forget(memory: Memory) {
        if (window.confirm(`Have the tutor forget this?\n\n${memory.content}`)) {
            void deleteMemory(memory.id).then(load);
        }
    }

    if (loaded.status === "loading") {
        return <p className="sidebar-note">Loading…</p>;
    }
    if (loaded.status === "error") {
        return <p className="sidebar-note error">{loaded.message}</p>;
    }
    const facts = loaded.memories.filter((memory) => memory.kind === "fact");
    const strategies = loaded.memories.filter((memory) => memory.kind === "strategy");
    const calendar = loaded.memories
        .filter((memory) => memory.kind === "calendar")
        .sort((one, other) => (one.day ?? "").localeCompare(other.day ?? "") || one.id - other.id);
    const today = localDay(new Date());
    const recaps = loaded.memories.filter((memory) => memory.kind === "recap");
    const listed = (memories: Memory[]) => (
        <ul className="memory-list">
            {memories.map((memory) => (
                <li
                    key={memory.id}
                    className={["memory", memory.kind, memory.day && memory.day < today && "past"]
                        .filter(Boolean)
                        .join(" ")}
                >
                    <p>{memory.content}</p>
                    <div className="memory-meta">
                        <span>
                            {memory.day
                                ? memory.day === today ? "Today" : dayOf(memory.day)
                                : day(memory.createdAt)}
                        </span>
                        <button
                            className="link"
                            onClick={() => forget(memory)}
                            title="Have the tutor forget this"
                        >
                            Forget
                        </button>
                    </div>
                </li>
            ))}
        </ul>
    );
    return (
        <div className="panel-body memories">
            <details className="memory-group" open>
                <summary>General, {facts.length}</summary>
                {facts.length === 0
                    ? (
                        <p className="sidebar-note">
                            The tutor remembers nothing yet. When you start a new chat with the tutor, the one before is
                            closed, and what matters of it for the next lessons is kept here.
                        </p>
                    )
                    : listed([...facts].reverse())}
            </details>
            <details className="memory-group" open>
                <summary>Strategy, {strategies.length}</summary>
                {strategies.length === 0
                    ? (
                        <p className="sidebar-note">
                            You and the tutor have not agreed yet on how to hold the lessons, such as Anki first, then a
                            chapter of a book. The tutor will ask you, and what you agree on is kept here.
                        </p>
                    )
                    : listed([...strategies].reverse())}
            </details>
            <details className="memory-group" open>
                <summary>Calendar, {calendar.length}</summary>
                {calendar.length === 0
                    ? (
                        <p className="sidebar-note">
                            Nothing is planned. When you and the tutor agree to do something on a day, such as a mock
                            exam, it is put here.
                        </p>
                    )
                    : listed(calendar)}
            </details>
            {recaps.length > 0 && (
                <details className="memory-group">
                    <summary>Recaps of the lessons, {recaps.length}</summary>
                    {listed([...recaps].reverse())}
                </details>
            )}
            {loaded.removed.length > 0 && (
                <details className="memory-group">
                    <summary>Forgotten, {loaded.removed.length}</summary>
                    <ul className="memory-list">
                        {[...loaded.removed].reverse().map((memory) => (
                            <li key={memory.id} className="memory removed">
                                <p>{memory.content}</p>
                                <div className="memory-meta">
                                    <span>
                                        {day(memory.createdAt)} – {memory.removedAt ? day(memory.removedAt) : ""}, by
                                        {" "}
                                        {memory.removedBy === "learner" ? "you" : "the tutor"}
                                        {memory.removedWhy && `: ${memory.removedWhy}`}
                                    </span>
                                </div>
                            </li>
                        ))}
                    </ul>
                </details>
            )}
        </div>
    );
}

function day(seconds: number): string {
    return new Date(seconds * 1000).toLocaleDateString(undefined, { dateStyle: "medium" });
}

/** A day given as YYYY-MM-DD, as the learner reads dates. */
function dayOf(iso: string): string {
    const [year, month, date] = iso.split("-").map(Number);
    return new Date(year, month - 1, date).toLocaleDateString(undefined, { dateStyle: "medium" });
}

/** The day of `moment` where the learner is, as YYYY-MM-DD. */
function localDay(moment: Date): string {
    const pad = (value: number) => String(value).padStart(2, "0");
    return `${moment.getFullYear()}-${pad(moment.getMonth() + 1)}-${pad(moment.getDate())}`;
}
