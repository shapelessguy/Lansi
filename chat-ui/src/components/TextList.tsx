// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { locale, plural, t } from "../lib/i18n";
import type { Text } from "../lib/texts";

interface Props {
    /** The texts and their corrections, or why they could not be listed. */
    texts: Text[] | string;
    selectedId: string | null;
    onSelect: (id: string) => void;
    onNew: () => void;
    onDelete: (text: Text) => void;
}

/**
 * The learner's texts, such as their homework, the one written in last
 * first. One that was corrected is locked, and opens with its corrections
 * worked in.
 */
export function TextList({ texts, selectedId, onSelect, onNew, onDelete }: Props) {
    const own = typeof texts === "string" ? [] : texts.filter((text) => text.kind === "text");

    return (
        <>
            <div className="sidebar-controls">
                <button className="primary" onClick={onNew}>{t("New text")}</button>
            </div>
            {typeof texts === "string" && <p className="sidebar-note error">{texts}</p>}
            {typeof texts !== "string" && own.length === 0 && (
                <p className="sidebar-note">
                    {t("Write your homework, or any text, here. The tutor can open one in an exercise that corrects it.")}
                </p>
            )}
            <ul className="chat-list">
                {own.map((text) => (
                    <li key={text.id} className={text.id === selectedId ? "chat-item active" : "chat-item"}>
                        <button
                            className="chat-open"
                            aria-current={text.id === selectedId ? "true" : undefined}
                            onClick={() =>
                                onSelect(text.id)}
                        >
                            <span className="chat-title">{text.title || t("Untitled")}</span>
                            <span className="chat-detail">
                                {plural(text.words ?? 0, "{count} word", "{count} words")} · {day(text.updatedAt)}
                                {text.lockedAt !== null && ` · ${t("corrected")}`}
                            </span>
                        </button>
                        <button
                            className="icon-button chat-delete"
                            onClick={() =>
                                onDelete(text)}
                            title={t("Delete")}
                            aria-label={t("Delete {name}", { name: text.title || t("the text") })}
                        >
                            ×
                        </button>
                    </li>
                ))}
            </ul>
        </>
    );
}

function day(seconds: number): string {
    return new Date(seconds * 1000).toLocaleDateString(locale(), { dateStyle: "medium" });
}
