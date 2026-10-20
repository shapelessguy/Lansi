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
 * learner here. What was removed is listed apart, with why and by whom.
 */
export function MemoryList({ revision, onCount }: Props) {
    const [loaded, setLoaded] = useState<Loaded>({ status: "loading" });
    const load = useCallback(() => {
        fetchMemories().then(
            ({ memories, removed }) => {
                setLoaded({ status: "ready", memories, removed });
                onCount(memories.length);
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
    return (
        <div className="panel-body memories">
            {loaded.memories.length === 0
                ? (
                    <p className="sidebar-note">
                        The tutor remembers nothing yet. When you start a new chat with the tutor, the one before is
                        closed, and what matters of it for the next lessons is kept here.
                    </p>
                )
                : (
                    <ul className="memory-list">
                        {[...loaded.memories].reverse().map((memory) => (
                            <li key={memory.id} className="memory">
                                <p>{memory.content}</p>
                                <div className="memory-meta">
                                    <span>{day(memory.createdAt)}</span>
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
                )}
            {loaded.removed.length > 0 && (
                <details className="memory-removed">
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
