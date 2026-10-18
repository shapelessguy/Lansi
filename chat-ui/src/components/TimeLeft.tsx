// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { useEffect, useRef, useState } from "react";

import { clock, type PracticeSession, secondsLeft } from "../lib/practice";

interface Props {
    session: PracticeSession;
    exercise: string;
    /** The time is up: the exercise is to be finished. Called once. */
    onUp: () => void;
}

/** How long a minute is that is shown as the last, in seconds. */
const LAST_MINUTE = 60;

/**
 * The time left of an exercise of a session that has a limit, counting
 * down from when it was first shown; nothing for one without. Give it a key
 * of its own for each exercise.
 */
export function TimeLeft({ session, exercise, onUp }: Props) {
    const [now, setNow] = useState(() => Date.now());
    useEffect(() => {
        const timer = setInterval(() => setNow(Date.now()), 1000);
        return () => clearInterval(timer);
    }, []);
    const left = secondsLeft(session, exercise, now);
    const told = useRef(false);
    const latest = useRef(onUp);
    latest.current = onUp;
    useEffect(() => {
        if (left === 0 && !told.current) {
            told.current = true;
            latest.current();
        }
    }, [left]);
    if (left === null) {
        return null;
    }
    return (
        <span
            className={left < LAST_MINUTE ? "time-left low" : "time-left"}
            role="timer"
            title="Time left for this exercise"
        >
            {clock(left)}
        </span>
    );
}
