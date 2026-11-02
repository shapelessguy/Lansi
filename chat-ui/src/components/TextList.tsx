// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { locale, plural, t } from "../lib/i18n";
import type { Text } from "../lib/texts";
import { Icon } from "./Icon";

interface Props {
    /** The texts and their corrections, or why they could not be listed. */
    texts: Text[] | string;
    selectedId: string | null;
    onSelect: (id: string) => void;
    /** Starts a text, typed or written by hand. */
    onNew: (handwritten: boolean) => void;
    onDelete: (text: Text) => void;
}

/**
 * The learner's texts, such as their homework, the one started last first,
 * each kept in its place as it is written in. A text that was corrected is
 * locked, and its correction shown under it as it is opened, not listed.
 */
export function TextList({ texts, selectedId, onSelect, onNew, onDelete }: Props) {
    const all = typeof texts === "string" ? [] : texts;
    const byStart = (a: Text, b: Text) => b.createdAt - a.createdAt;
    const own = all.filter((text) => text.kind === "text").sort(byStart);
    // a correction whose text was deleted is listed on its own, last
    const listed = [
        ...own,
        ...all.filter((each) => each.kind === "correction" && !own.some((text) => text.id === each.corrects))
            .sort(byStart),
    ];

    return (
        <>
            <div className="sidebar-controls new-texts">
                <button
                    title={t("New text")}
                    aria-label={t("New text")}
                    onClick={() => onNew(false)}
                >
                    <Icon name="new-text" />
                </button>
                <button
                    title={t("New handwritten text")}
                    aria-label={t("New handwritten text")}
                    onClick={() => onNew(true)}
                >
                    <Icon name="new-handwritten" />
                </button>
            </div>
            {typeof texts === "string" && <p className="sidebar-note error">{texts}</p>}
            {typeof texts !== "string" && own.length === 0 && (
                <p className="sidebar-note">
                    {t("Write your homework, or any text, here, and correct it once it is done.")}
                </p>
            )}
            <ul className="chat-list">
                {listed.map((text) => (
                    <li key={text.id} className={`chat-item${text.id === selectedId ? " active" : ""}`}>
                        <button
                            className="chat-open"
                            aria-current={text.id === selectedId ? "true" : undefined}
                            onClick={() =>
                                onSelect(text.id)}
                        >
                            <span className="chat-title">{text.title || t("Untitled")}</span>
                            <span className="chat-detail text-detail">
                                {text.kind === "correction" && (
                                    <span className="text-mark" title={t("correction")}>
                                        <Icon name="checks" />
                                    </span>
                                )}
                                {text.handwritten && (
                                    <span className="text-mark" title={t("handwritten")}>
                                        <Icon name="pen" />
                                    </span>
                                )}
                                {text.kind === "text" && (
                                    <span title={plural(text.words ?? 0, "{count} word", "{count} words")}>
                                        <Icon name="words" />
                                        {text.words ?? 0}
                                    </span>
                                )}
                                <span>{day(text.updatedAt)}</span>
                                {text.kind === "text" && text.lockedAt !== null && (
                                    <span className="text-mark" title={t("corrected")}>
                                        <Icon name="checks" />
                                    </span>
                                )}
                            </span>
                        </button>
                        <button
                            className="icon-button chat-delete"
                            onClick={() =>
                                onDelete(text)}
                            title={t("Delete")}
                            aria-label={t("Delete {name}", { name: text.title || t("the text") })}
                        >
                            <Icon name="close" />
                        </button>
                    </li>
                ))}
            </ul>
        </>
    );
}

function day(seconds: number): string {
    const date = new Date(seconds * 1000);
    const thisYear = date.getFullYear() === new Date().getFullYear();
    return date.toLocaleDateString(locale(), {
        day: "numeric",
        month: "short",
        year: thisYear ? undefined : "2-digit",
    });
}
