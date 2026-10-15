// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { type FormEvent, useEffect, useState } from "react";

import { iconOf, matchesTopic, type Topic } from "../lib/topics";

interface Props {
    topics: Topic[];
    /** The topics chosen for the next session, by their ids. */
    chosen: string[];
    /** Whether a topic is being made. */
    adding: boolean;
    /** Tells the icons from those before them, which are fetched again when it changes. */
    revision: number;
    onToggle: (id: string) => void;
    onAdd: (title: string, description: string) => void;
    onDelete: (id: string) => void;
    onRemakeIcon: (id: string) => void;
}

/** The icon of a topic, once it has been made and fetched, or its first letter until then. */
function TopicIcon({ topic }: { topic: Topic }) {
    const [source, setSource] = useState<string | null>(null);

    useEffect(() => {
        let current = true;
        setSource(null);
        if (topic.icon) {
            iconOf(topic.id).then((url) => current && setSource(url), () => undefined);
        }
        return () => {
            current = false;
        };
    }, [topic.id, topic.icon]);

    return source
        ? <img className="topic-icon" src={source} alt="" />
        : <span className="topic-icon empty" aria-hidden="true">{topic.title.slice(0, 1).toUpperCase()}</span>;
}

/** The topics to choose from, with a search among them and a form to add one. */
export function TopicList({ topics, chosen, adding, revision, onToggle, onAdd, onDelete, onRemakeIcon }: Props) {
    const [title, setTitle] = useState("");
    const [description, setDescription] = useState("");
    // whether the form to add a topic is shown, rather than the button that shows it
    const [open, setOpen] = useState(false);
    const [query, setQuery] = useState("");
    // those chosen are listed whatever is looked for, so that they can be left out again
    const shown = topics.filter((topic) => chosen.includes(topic.id) || matchesTopic(topic, query.trim()));

    function add(event: FormEvent) {
        event.preventDefault();
        if (title.trim()) {
            onAdd(title.trim(), description.trim());
            close();
        }
    }

    function close() {
        setTitle("");
        setDescription("");
        setOpen(false);
    }

    return (
        <>
            {topics.length > 0 && (
                <input
                    type="search"
                    className="topic-search"
                    placeholder="Search topics"
                    aria-label="Search topics"
                    value={query}
                    onChange={(event) => setQuery(event.target.value)}
                    onKeyDown={(event) => event.key === "Escape" && setQuery("")}
                />
            )}
            <ul className="practice-list">
                {shown.map((topic) => (
                    <li key={topic.id} className="topic-item">
                        <button
                            className="practice-choice topic-choice"
                            aria-pressed={chosen.includes(topic.id)}
                            onClick={() => onToggle(topic.id)}
                        >
                            <span className="topic-icon-wrap">
                                <TopicIcon key={`${topic.id}:${revision}`} topic={topic} />
                            </span>
                            <span className="topic-text">
                                <span className="practice-title">{topic.title}</span>
                                {topic.description && <span className="practice-detail">{topic.description}</span>}
                            </span>
                        </button>
                        <span className="topic-actions">
                            <button
                                className="icon-button"
                                title="Make the icon again"
                                aria-label={`Make the icon of ${topic.title} again`}
                                onClick={() => onRemakeIcon(topic.id)}
                            >
                                ↻
                            </button>
                            <button
                                className="icon-button"
                                title="Delete"
                                aria-label={`Delete ${topic.title}`}
                                onClick={() => onDelete(topic.id)}
                            >
                                ×
                            </button>
                        </span>
                    </li>
                ))}
            </ul>
            {topics.length > 0 && shown.length === 0 && <p className="practice-note">No topic is about that.</p>}
            {topics.length === 0 && (
                <p className="practice-note">
                    Add a topic to talk about. Without one, exercises are about everyday life.
                </p>
            )}
            {open
                ? (
                    <form
                        className="topic-form"
                        onSubmit={add}
                        onKeyDown={(event) => event.key === "Escape" && close()}
                    >
                        <input
                            type="text"
                            placeholder="Title, such as Beim Arzt"
                            aria-label="Title of the new topic"
                            autoFocus
                            value={title}
                            onChange={(event) => setTitle(event.target.value)}
                        />
                        <input
                            type="text"
                            placeholder="What it is about (optional)"
                            aria-label="What the new topic is about"
                            value={description}
                            onChange={(event) => setDescription(event.target.value)}
                        />
                        <span className="topic-form-actions">
                            <button type="submit" className="primary" disabled={!title.trim()}>Add</button>
                            <button type="button" onClick={close}>Cancel</button>
                        </span>
                    </form>
                )
                : (
                    <button className="topic-new" disabled={adding} onClick={() => setOpen(true)}>
                        {adding ? "Adding topic…" : "+ New topic"}
                    </button>
                )}
        </>
    );
}
