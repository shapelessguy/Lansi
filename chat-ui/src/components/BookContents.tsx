// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { useState } from "react";

import { type BookSection, sectionsAt } from "../lib/books";
import { t } from "../lib/i18n";

interface Props {
    sections: BookSection[];
    /** The block the book is at, by its place among them. */
    place: number;
    /** Told the block a section starts with, by its place, when it is chosen. */
    onGoTo: (place: number) => void;
    /** Told a section to read aloud, with those under it. */
    onPlay: (section: BookSection) => void;
}

/** What tells a section from the others: where it starts and ends, as no two sections share both. */
function keyOf(section: BookSection): string {
    return `${section.start}-${section.end}`;
}

/**
 * The sections of a book as a tree, to go to one by choosing it. The
 * sections the book is at are marked, and open to show those under them.
 */
export function BookContents({ sections, place, onGoTo, onPlay }: Props) {
    const at = sectionsAt(sections, place);
    const [open, setOpen] = useState(() => new Set(at.map(keyOf)));

    function toggle(section: BookSection) {
        const next = new Set(open);
        if (!next.delete(keyOf(section))) {
            next.add(keyOf(section));
        }
        setOpen(next);
    }

    function tree(shown: BookSection[]) {
        return (
            <ul>
                {shown.map((section) => {
                    const key = keyOf(section);
                    const isOpen = open.has(key);
                    return (
                        <li key={key}>
                            <div className="contents-row">
                                {section.sections
                                    ? (
                                        <button
                                            className="contents-toggle"
                                            aria-expanded={isOpen}
                                            onClick={() => toggle(section)}
                                            aria-label={t(
                                                isOpen ? "Hide the sections under it" : "Show the sections under it",
                                            )}
                                        >
                                            {isOpen ? "▾" : "▸"}
                                        </button>
                                    )
                                    : <span className="contents-toggle" />}
                                <button
                                    className="contents-title"
                                    aria-current={at.includes(section) ? "location" : undefined}
                                    onClick={() => onGoTo(section.start)}
                                    title={section.title || t("Beginning")}
                                >
                                    {section.title || t("Beginning")}
                                </button>
                                <button
                                    className="contents-play"
                                    onClick={() => onPlay(section)}
                                    title={t("Read it aloud")}
                                    aria-label={t("Read {name} aloud", { name: section.title || t("Beginning") })}
                                >
                                    ▶
                                </button>
                            </div>
                            {section.sections && isOpen && tree(section.sections)}
                        </li>
                    );
                })}
            </ul>
        );
    }

    return (
        <nav className="reader-contents" aria-label={t("Contents")}>
            {tree(sections)}
        </nav>
    );
}
