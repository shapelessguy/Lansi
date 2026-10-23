// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { useEffect, useRef, useState } from "react";

import { t } from "../lib/i18n";
import { type BackgroundTask, describeTask, mentioned, taskName } from "../lib/tasks";
import { Icon } from "./Icon";
import { PartsProgress } from "./PartsProgress";

interface Props {
    /** What the server does in the background, and has done of late, the newest first. */
    tasks: BackgroundTask[];
}

/**
 * The sign in the bar at the top that something is done in the background.
 * A click on it lists what is being done and what came of what was.
 */
export function TaskSign({ tasks }: Props) {
    const [open, setOpen] = useState(false);
    const sign = useRef<HTMLDivElement>(null);
    const running = tasks.filter((task) => task.state === "running").length;

    // a click anywhere else puts the list away
    useEffect(() => {
        if (!open) {
            return;
        }
        function onMouseDown(event: MouseEvent) {
            if (!(event.target instanceof Node && sign.current?.contains(event.target))) {
                setOpen(false);
            }
        }
        document.addEventListener("mousedown", onMouseDown);
        return () => document.removeEventListener("mousedown", onMouseDown);
    }, [open]);

    if (tasks.length === 0) {
        return null;
    }
    return (
        <div className="task-sign" ref={sign}>
            <button
                aria-pressed={open}
                aria-haspopup="true"
                onClick={() => setOpen(!open)}
                aria-label={t("Tasks")}
                title={running > 0 ? t("Work is being done in the background") : t("What was done in the background")}
            >
                {running > 0 ? <span className="spinner" aria-hidden="true" /> : <Icon name="tasks" />}
                {running > 0 && <span className="count">{running}</span>}
                {/* it opens a list over the page, not a panel */}
                <span className="caret" aria-hidden="true">▾</span>
            </button>
            {open && (
                <ul className="task-list" aria-label={t("Background tasks")}>
                    {tasks.map((task) => (
                        <li key={task.id} className={`task ${task.state}`}>
                            <span className="task-kind">{taskName(task)}</span>
                            <span className="task-title">{task.title}</span>
                            {task.state === "running" && <progress max={Math.max(1, task.total)} value={task.done} />}
                            <span className="task-state">{describeTask(task)}</span>
                            {task.state === "running" && task.progress && task.progress.length > 0 && (
                                <PartsProgress parts={task.progress} />
                            )}
                            {mentioned(task).length > 0 && (
                                <ul className="selection-words">
                                    {mentioned(task).map((word, index) => (
                                        <li
                                            key={index}
                                            className={word.status === "failed" ? "failed" : undefined}
                                            title={word.reason || undefined}
                                        >
                                            {word.word}
                                        </li>
                                    ))}
                                </ul>
                            )}
                        </li>
                    ))}
                </ul>
            )}
        </div>
    );
}
