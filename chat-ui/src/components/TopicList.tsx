// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { type FormEvent, useEffect, useState } from "react";

import { t } from "../lib/i18n";
import { iconOf, matchesTopic, type Topic } from "../lib/topics";
import { Icon } from "./Icon";

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
    onChange: (id: string, title: string, description: string) => void;
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

interface FormProps {
    /** What the form starts with: nothing for a new topic, what a topic has for one changed. */
    initial?: Pick<Topic, "title" | "description">;
    submit: string;
    onSubmit: (title: string, description: string) => void;
    onCancel: () => void;
}

/** A title and what it is about, for a new topic or one changed. */
function TopicForm({ initial, submit, onSubmit, onCancel }: FormProps) {
    const [title, setTitle] = useState(initial?.title ?? "");
    const [description, setDescription] = useState(initial?.description ?? "");

    function send(event: FormEvent) {
        event.preventDefault();
        if (title.trim()) {
            onSubmit(title.trim(), description.trim());
        }
    }

    return (
        <form className="topic-form" onSubmit={send} onKeyDown={(event) => event.key === "Escape" && onCancel()}>
            <input
                type="text"
                placeholder={t("Title, such as At the doctor's")}
                aria-label={initial ? t("Title of the topic") : t("Title of the new topic")}
                autoFocus
                value={title}
                onChange={(event) => setTitle(event.target.value)}
            />
            <textarea
                rows={3}
                placeholder={t("What it is about (optional)")}
                aria-label={initial ? t("What the topic is about") : t("What the new topic is about")}
                value={description}
                onChange={(event) => setDescription(event.target.value)}
            />
            <span className="topic-form-actions">
                <button type="submit" className="primary" disabled={!title.trim()}>{submit}</button>
                <button type="button" onClick={onCancel}>{t("Cancel")}</button>
            </span>
        </form>
    );
}

/** The topics to choose from, with a search among them and a form to add one. */
export function TopicList(
    { topics, chosen, adding, revision, onToggle, onAdd, onChange, onDelete, onRemakeIcon }: Props,
) {
    // whether the form to add a topic is shown, rather than the button that shows it
    const [open, setOpen] = useState(false);
    // the topic whose title and what it is about are shown in full, and whether they are being changed
    const [shownInFull, setShownInFull] = useState<string | null>(null);
    const [editing, setEditing] = useState(false);
    const [query, setQuery] = useState("");
    // those chosen are listed whatever is looked for, so that they can be left out again
    const shown = topics.filter((topic) => chosen.includes(topic.id) || matchesTopic(topic, query.trim()));

    function showInFull(id: string) {
        setShownInFull((current) => (current === id ? null : id));
        setEditing(false);
    }

    return (
        <>
            {topics.length > 0 && (
                <input
                    type="search"
                    className="topic-search"
                    placeholder={t("Search topics")}
                    aria-label={t("Search topics")}
                    value={query}
                    onChange={(event) => setQuery(event.target.value)}
                    onKeyDown={(event) => event.key === "Escape" && setQuery("")}
                />
            )}
            <ul className="practice-list">
                {shown.map((topic) => {
                    const full = shownInFull === topic.id;
                    return (
                        <li key={topic.id} className={full ? "topic-item open" : "topic-item"}>
                            <div className="topic-row">
                                <button
                                    className="practice-choice topic-choice"
                                    aria-pressed={chosen.includes(topic.id)}
                                    title={topic.description || undefined}
                                    onClick={() => onToggle(topic.id)}
                                >
                                    <span className="topic-icon-wrap">
                                        <TopicIcon key={`${topic.id}:${revision}`} topic={topic} />
                                    </span>
                                    <span className="practice-title topic-title">{topic.title}</span>
                                </button>
                                <span className="topic-actions">
                                    <button
                                        className="icon-button topic-more"
                                        title={t("What it is about")}
                                        aria-label={t("What {name} is about", { name: topic.title })}
                                        aria-expanded={full}
                                        onClick={() => showInFull(topic.id)}
                                    >
                                        <Icon name="chevron" />
                                    </button>
                                    <button
                                        className="icon-button"
                                        title={t("Make the icon again")}
                                        aria-label={t("Make the icon of {name} again", { name: topic.title })}
                                        onClick={() => onRemakeIcon(topic.id)}
                                    >
                                        ↻
                                    </button>
                                    <button
                                        className="icon-button"
                                        title={t("Delete")}
                                        aria-label={t("Delete {name}", { name: topic.title })}
                                        onClick={() => onDelete(topic.id)}
                                    >
                                        ×
                                    </button>
                                </span>
                            </div>
                            {full && (editing
                                ? (
                                    <TopicForm
                                        initial={topic}
                                        submit={t("Save")}
                                        onSubmit={(title, description) => {
                                            onChange(topic.id, title, description);
                                            setEditing(false);
                                        }}
                                        onCancel={() => setEditing(false)}
                                    />
                                )
                                : (
                                    <div className="topic-details">
                                        <p className={topic.description ? "" : "topic-none"}>
                                            {topic.description || t("Nothing is said yet about what it is about.")}
                                        </p>
                                        <button
                                            className="icon-button"
                                            title={t("Edit")}
                                            aria-label={t("Edit {name}", { name: topic.title })}
                                            onClick={() => setEditing(true)}
                                        >
                                            <Icon name="edit" />
                                        </button>
                                    </div>
                                ))}
                        </li>
                    );
                })}
            </ul>
            {topics.length > 0 && shown.length === 0 && <p className="practice-note">{t("No topic is about that.")}</p>}
            {topics.length === 0 && (
                <p className="practice-note">
                    {t("Add a topic to talk about. Without one, exercises are about everyday life.")}
                </p>
            )}
            {open
                ? (
                    <TopicForm
                        submit={t("Add")}
                        onSubmit={(title, description) => {
                            onAdd(title, description);
                            setOpen(false);
                        }}
                        onCancel={() => setOpen(false)}
                    />
                )
                : (
                    <button className="topic-new" disabled={adding} onClick={() => setOpen(true)}>
                        {adding ? t("Adding topic…") : t("+ New topic")}
                    </button>
                )}
        </>
    );
}
