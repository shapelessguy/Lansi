// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { useEffect, useState } from "react";

import { interfaceLanguage, t } from "../lib/i18n";
import {
    type ExerciseInfo,
    fetchExercises,
    fetchLessons,
    fetchPracticeSessions,
    type Lesson,
    type PracticeSession,
    sessionTitleOf,
} from "../lib/practice";
import { fetchTopics, type Topic } from "../lib/topics";
import { SessionHistory } from "./SessionHistory";

interface Props {
    /** Whether the tab is shown, which is when the sessions are listed. */
    active: boolean;
    /** The language learned, whose lessons the sessions are titled by. */
    language: string;
    /** Changes when a session may have ended or been logged, so that they are listed again. */
    revision: number;
    /** Takes up a session that is still running where it was left, in Practice. */
    onResume: (session: PracticeSession) => void;
}

interface Listed {
    sessions: PracticeSession[];
    lessons: Lesson[];
    topics: Topic[];
    exercises: ExerciseInfo[];
}

/**
 * The practice sessions, the latest first, each with how it went, in the
 * panel of the logs: listed again whenever the tab is shown and something
 * may have changed.
 */
export function PracticeSessions({ active, language, revision, onResume }: Props) {
    const [listed, setListed] = useState<Listed | null>(null);
    const [error, setError] = useState<string | null>(null);

    // listed again in the language of the interface when it changes
    const shownIn = interfaceLanguage();
    useEffect(() => {
        if (!active) {
            return;
        }
        let current = true;
        Promise.all([fetchPracticeSessions(), fetchLessons(language), fetchTopics(), fetchExercises()]).then(
            ([sessions, lessons, topics, exercises]) => {
                if (current) {
                    setListed({ sessions, lessons, topics, exercises });
                    setError(null);
                }
            },
            (failed: Error) => current && setError(failed.message),
        );
        return () => {
            current = false;
        };
    }, [active, language, revision, shownIn]);

    if (error) {
        return <p className="sidebar-note error">{error}</p>;
    }
    if (!listed) {
        return <p className="sidebar-note">{t("Loading…")}</p>;
    }
    if (listed.sessions.length === 0) {
        return <p className="sidebar-note">{t("No practice session yet.")}</p>;
    }
    const lessonTitle = (id: string) => listed.lessons.find((lesson) => lesson.id === id)?.title || id;
    const exerciseTitle = (id: string) => listed.exercises.find((each) => each.id === id)?.title || id;
    return (
        <div className="panel-body practice-sessions">
            <SessionHistory
                sessions={listed.sessions}
                sessionTitle={(session) => sessionTitleOf(session, lessonTitle, exerciseTitle)}
                topicTitle={(id) => listed.topics.find((topic) => topic.id === id)?.title || t("a topic")}
                exerciseTitle={exerciseTitle}
                onResume={onResume}
            />
        </div>
    );
}
