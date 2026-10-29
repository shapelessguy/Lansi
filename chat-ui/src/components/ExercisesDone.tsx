// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { type DragEvent, type ReactNode, useEffect, useState } from "react";

import { ask } from "../lib/dialogs";
import { interfaceLanguage, locale, t } from "../lib/i18n";
import {
    addFavouriteFolder,
    changeFavouriteFolder,
    deleteFavouriteFolder,
    type ExerciseInfo,
    type ExerciseProgress,
    type Favourite,
    type FavouriteFolder,
    type Favourites,
    fetchExercises,
    fetchFavourites,
    fetchLessons,
    fetchSession,
    fetchSessions,
    fileFavourite,
    type Grade,
    interfaceAddress,
    type Lesson,
    type PracticeSession,
    sessionTitleOf,
    setFavourite,
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
    /**
     * Whether only the favourites are listed, in the folders the learner
     * keeps them in, which they make, rename, move and delete, each
     * favourite moved into one by dragging it there or choosing it, and
     * taken out of the favourites with its star; otherwise every exercise
     * done is, by day, each with a star that adds it.
     */
    favouritesOnly?: boolean;
}

interface Listed {
    sessions: PracticeSession[];
    lessons: Lesson[];
    topics: Topic[];
    exercises: ExerciseInfo[];
    favourites: Favourite[];
    folders: FavouriteFolder[];
}

/** What is being dragged among the favourites: a favourite, or a folder. */
type Dragged = { session: string; exercise: string } | { folder: number };

/** A folder whose name is being written: a new one in `parent`, or one being renamed. */
type Naming = { parent: number | null } | { folder: number };

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
export function ExercisesDone({ active, language, revision, onReplay, favouritesOnly = false }: Props) {
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
        Promise.all([fetchSessions(), fetchLessons(language), fetchTopics(), fetchExercises(), fetchFavourites()]).then(
            ([sessions, lessons, topics, exercises, favourites]) => {
                if (current) {
                    setListed({ sessions, lessons, topics, exercises, ...favourites });
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

    // what went wrong with the last change of the favourites, said above them
    const [changeError, setChangeError] = useState("");
    const [naming, setNaming] = useState<Naming | null>(null);
    const [dragged, setDragged] = useState<Dragged | null>(null);
    const [dropOn, setDropOn] = useState<number | "top" | null>(null);
    // the folders folded shut; the others are open
    const [shut, setShut] = useState<Set<number>>(new Set());

    function fold(folder: number, open: boolean) {
        setShut((current) => {
            if (current.has(folder) !== open) {
                return current;
            }
            const next = new Set(current);
            if (open) {
                next.delete(folder);
            } else {
                next.add(folder);
            }
            return next;
        });
    }

    function changed(change: Promise<Favourites>) {
        change.then(
            (favourites) => {
                setListed((current) => current && { ...current, ...favourites });
                setChangeError("");
            },
            (failed: Error) => setChangeError(failed.message),
        );
    }

    function favour(session: PracticeSession, exercise: string, kept: boolean) {
        changed(setFavourite(session.id, exercise, kept));
    }

    /** Puts what is dragged, or `moved`, into `folder`, or at the top with null. */
    function moveInto(folder: number | null, moved: Dragged | null = dragged) {
        setDragged(null);
        setDropOn(null);
        if (!moved) {
            return;
        }
        if ("folder" in moved) {
            if (moved.folder !== folder) {
                changed(changeFavouriteFolder(moved.folder, { parent: folder }));
            }
        } else {
            changed(fileFavourite(moved.session, moved.exercise, folder));
        }
    }

    function named(name: string | null) {
        const was = naming;
        setNaming(null);
        if (!was || !name) {
            return;
        }
        changed("folder" in was ? changeFavouriteFolder(was.folder, { name }) : addFavouriteFolder(name, was.parent));
    }

    function removeFolder(folder: FavouriteFolder, count: number) {
        void ask(t("Delete the folder {name}?", { name: folder.name }), {
            detail: count > 0
                ? t("The folders in it are deleted too, and its {count} exercises are taken out of the favourites.", {
                    count,
                })
                : t("The folders in it are deleted too."),
            confirm: t("Delete"),
        }).then((agreed) => agreed && changed(deleteFavouriteFolder(folder.id)));
    }

    /** What a place in the tree does as something is dragged over it and dropped on it. */
    function dropTarget(folder: number | null) {
        const key = folder ?? "top";
        return {
            onDragOver: (event: DragEvent) => {
                if (dragged) {
                    event.preventDefault();
                    event.stopPropagation();
                    setDropOn(key);
                }
            },
            onDragLeave: () => setDropOn((current) => current === key ? null : current),
            onDrop: (event: DragEvent) => {
                event.preventDefault();
                event.stopPropagation();
                moveInto(folder);
            },
        };
    }

    if (error) {
        return <p className="sidebar-note error">{error}</p>;
    }
    if (!listed) {
        return <p className="sidebar-note">{t("Loading…")}</p>;
    }
    const isFavourite = (session: PracticeSession, exercise: string) =>
        listed.favourites.some((each) => each.session_id === session.id && each.exercise === exercise);
    const done = doneOf(listed.sessions).filter(({ session, exercise }) =>
        !favouritesOnly || isFavourite(session, exercise)
    );
    if (done.length === 0) {
        return (
            <p className="sidebar-note">
                {favouritesOnly
                    ? t("No favourite exercise yet: add one with its star under Exercises.")
                    : t("No exercise done yet.")}
            </p>
        );
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
    // the folders of the favourites, and what is in each
    const folderOf = (sessionId: string, exercise: string) =>
        listed.favourites.find((each) => each.session_id === sessionId && each.exercise === exercise)?.folder ?? null;
    const foldersIn = (parent: number | null) => listed.folders.filter((folder) => folder.parent === parent);
    const itemsIn = (folder: number | null) =>
        shown.filter(({ session, exercise }) => folderOf(session.id, exercise) === folder);
    const countIn = (folder: number): number =>
        itemsIn(folder).length + foldersIn(folder).reduce((sum, each) => sum + countIn(each.id), 0);
    const pathOf = (folder: number): string => {
        const names: string[] = [];
        for (let at: number | null = folder; at !== null;) {
            const found: FavouriteFolder | undefined = listed.folders.find((each) => each.id === at);
            if (!found || names.length > listed.folders.length) {
                break;
            }
            names.unshift(found.name);
            at = found.parent;
        }
        return names.join(" / ");
    };
    // the folders something can be moved into, but for `except` and those in it
    const folderChoices = (except?: number) => {
        const inside = (folder: number | null): boolean =>
            folder !== null
            && (folder === except || inside(listed.folders.find((each) => each.id === folder)?.parent ?? null));
        return listed.folders
            .filter((folder) => except === undefined || !inside(folder.id))
            .map((folder) => ({ id: folder.id, path: pathOf(folder.id) }))
            .sort((one, other) => one.path.localeCompare(other.path, locale()));
    };
    // every folder is shown, however it is searched, so that one just made is in sight
    const folderNode = (folder: FavouriteFolder): ReactNode => {
        const count = countIn(folder.id);
        const renaming = naming !== null && "folder" in naming && naming.folder === folder.id;
        return (
            <li
                key={`folder:${folder.id}`}
                className={`favourite-folder${dropOn === folder.id ? " drop-on" : ""}`}
                draggable
                onDragStart={(event) => {
                    event.stopPropagation();
                    event.dataTransfer.effectAllowed = "move";
                    setDragged({ folder: folder.id });
                }}
                onDragEnd={() => {
                    setDragged(null);
                    setDropOn(null);
                }}
                {...dropTarget(folder.id)}
            >
                <details
                    open={!shut.has(folder.id)}
                    onToggle={(event) => fold(folder.id, event.currentTarget.open)}
                >
                    <summary>
                        <span className="favourite-folder-chevron" aria-hidden />
                        <FolderGlyph />
                        <span className="favourite-folder-title">{folder.name}</span>
                        <span className="favourite-folder-count">{count}</span>
                        <span className="favourite-folder-actions">
                            <button
                                className="favourite-action"
                                title={t("New folder in it")}
                                aria-label={t("New folder in it")}
                                onClick={(event) => {
                                    event.preventDefault();
                                    // what is made in it is written where it can be seen
                                    fold(folder.id, true);
                                    setNaming({ parent: folder.id });
                                }}
                            >
                                +
                            </button>
                            <button
                                className="favourite-action"
                                title={t("Rename")}
                                aria-label={t("Rename")}
                                onClick={(event) => {
                                    event.preventDefault();
                                    fold(folder.id, true);
                                    setNaming({ folder: folder.id });
                                }}
                            >
                                ✎
                            </button>
                            <MoveTo
                                folders={folderChoices(folder.id)}
                                at={folder.parent}
                                onMove={(parent) => moveInto(parent, { folder: folder.id })}
                            />
                            <button
                                className="favourite-action danger"
                                title={t("Delete the folder")}
                                aria-label={t("Delete the folder")}
                                onClick={(event) => {
                                    event.preventDefault();
                                    removeFolder(folder, countIn(folder.id));
                                }}
                            >
                                ✕
                            </button>
                        </span>
                    </summary>
                    <ul className="favourite-folder-items">
                        {renaming && (
                            <li>
                                <NameField initial={folder.name} onDone={named} />
                            </li>
                        )}
                        {naming && "parent" in naming && naming.parent === folder.id && (
                            <li>
                                <NameField initial="" onDone={named} />
                            </li>
                        )}
                        {foldersIn(folder.id).map(folderNode)}
                        {itemsIn(folder.id).map(entry)}
                    </ul>
                </details>
            </li>
        );
    };
    const entry = ({ session, exercise, progress }: Done) => {
        const about = info(exercise);
        const got = opened[session.id];
        const grades = typeof got === "object"
            ? got.grades.filter((grade) => grade.exercise === exercise)
            : [];
        const log = typeof got === "object" ? got.logs[exercise] : undefined;
        const of = ofSession(session);
        return (
            <li
                key={`${session.id}:${exercise}`}
                className="log-entry done-exercise"
                draggable={favouritesOnly}
                onDragStart={(event) => {
                    event.stopPropagation();
                    event.dataTransfer.effectAllowed = "move";
                    setDragged({ session: session.id, exercise });
                }}
                onDragEnd={() => {
                    setDragged(null);
                    setDropOn(null);
                }}
            >
                <details onToggle={(event) => event.currentTarget.open && open(session.id)}>
                    <summary>
                        <span className="done-exercise-icon" aria-hidden>
                            {about?.icon
                                ? (
                                    <span
                                        className="practice-exercise-glyph"
                                        style={{
                                            maskImage: `url("${interfaceAddress(`${exercise}/ui/icon.svg`)}")`,
                                        }}
                                    />
                                )
                                : exerciseTitle(exercise).charAt(0)}
                        </span>
                        <span className="done-exercise-what">
                            <span className="log-head">
                                <span className="log-subject">{exerciseTitle(exercise)}</span>
                                <span className="log-time">
                                    {favouritesOnly
                                        ? `${dayOf(progress.started_at ?? session.started_at)}, ${
                                            timeOf(progress.started_at ?? session.started_at)
                                        }`
                                        : timeOf(progress.started_at ?? session.started_at)}
                                </span>
                                <FavouriteStar
                                    favourite={isFavourite(session, exercise)}
                                    removing={favouritesOnly}
                                    onChange={(kept) => favour(session, exercise, kept)}
                                />
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
                                {favouritesOnly && (
                                    <MoveTo
                                        folders={folderChoices()}
                                        at={folderOf(session.id, exercise)}
                                        onMove={(folder) => moveInto(folder, { session: session.id, exercise })}
                                    />
                                )}
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
    };
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
            {favouritesOnly
                ? (
                    <div
                        className={`log-list exercises-done favourite-tree${dropOn === "top" ? " drop-on" : ""}`}
                        {...dropTarget(null)}
                    >
                        <div className="favourite-tree-bar">
                            <button className="favourite-new" onClick={() => setNaming({ parent: null })}>
                                <FolderGlyph /> {t("New folder")}
                            </button>
                        </div>
                        {changeError && <p className="sidebar-note error">{changeError}</p>}
                        {shown.length === 0 && <p className="sidebar-note">{t("No exercise is like that.")}</p>}
                        <ul className="favourite-folder-items">
                            {naming && "parent" in naming && naming.parent === null && (
                                <li>
                                    <NameField initial="" onDone={named} />
                                </li>
                            )}
                            {foldersIn(null).map(folderNode)}
                            {itemsIn(null).map(entry)}
                        </ul>
                    </div>
                )
                : (
                    <div className="log-list exercises-done">
                        {shown.length === 0 && <p className="sidebar-note">{t("No exercise is like that.")}</p>}
                        {days.map(({ day, items }) => (
                            <section key={day} className="log-day">
                                <h3>{day}</h3>
                                <ul>
                                    {items.map(entry)}
                                </ul>
                            </section>
                        ))}
                    </div>
                )}
        </>
    );
}

/** A folder's name being written, kept on Enter or as the field is left, given up on Escape or when empty. */
function NameField({ initial, onDone }: { initial: string; onDone: (name: string | null) => void }) {
    const [name, setName] = useState(initial);
    const [done, setDone] = useState(false);
    function finish(kept: string | null) {
        if (!done) {
            setDone(true);
            onDone(kept?.trim() || null);
        }
    }
    return (
        <input
            className="favourite-folder-name"
            autoFocus
            value={name}
            placeholder={t("Name of the folder")}
            aria-label={t("Name of the folder")}
            onChange={(event) => setName(event.target.value)}
            onKeyDown={(event) => {
                if (event.key === "Enter") {
                    finish(name);
                } else if (event.key === "Escape") {
                    finish(null);
                }
            }}
            onBlur={() => finish(name)}
        />
    );
}

/** A folder, drawn as an outline in the colour of the text around it. */
function FolderGlyph() {
    return (
        <svg className="folder-glyph" viewBox="0 0 16 16" aria-hidden>
            <path
                d="M1.5 4.5a1 1 0 0 1 1-1h3.6l1.4 1.5h6a1 1 0 0 1 1 1v6.5a1 1 0 0 1-1 1h-11a1 1 0 0 1-1-1z"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.2"
                strokeLinejoin="round"
            />
        </svg>
    );
}

/** A choice of the folder to move something into, the top first, each folder by its path. */
function MoveTo(
    { folders, at, onMove }: {
        folders: { id: number; path: string }[];
        at: number | null;
        onMove: (folder: number | null) => void;
    },
) {
    return (
        <select
            className="favourite-move"
            value={at ?? ""}
            title={t("Move to a folder")}
            aria-label={t("Move to a folder")}
            // in a summary, it does not open the card
            onClick={(event) => event.stopPropagation()}
            onChange={(event) => onMove(event.target.value === "" ? null : Number(event.target.value))}
        >
            <option value="">{t("Top")}</option>
            {folders.map((folder) => <option key={folder.id} value={folder.id}>{folder.path}</option>)}
        </select>
    );
}

/**
 * The star of an exercise done: under Exercises it adds it to the
 * favourites, and is lit once it is among them; among the favourites, it
 * takes it out.
 */
function FavouriteStar(
    { favourite, removing, onChange }: { favourite: boolean; removing: boolean; onChange: (kept: boolean) => void },
) {
    const told = removing
        ? t("Take it out of the favourites")
        : favourite
        ? t("Among the favourites")
        : t("Add it to the favourites");
    return (
        <button
            className={`favourite-star${favourite ? " lit" : ""}`}
            aria-pressed={favourite}
            aria-label={told}
            title={told}
            disabled={favourite && !removing}
            onClick={(event) => {
                // in the summary, it does not open the card
                event.preventDefault();
                onChange(!removing);
            }}
        >
            {favourite ? "★" : "☆"}
        </button>
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
