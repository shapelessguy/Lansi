// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { useState } from "react";

import { type BookSection, sectionsAt } from "../lib/books";
import { t } from "../lib/i18n";
import { type OfflineState, sizeOf } from "../lib/offline";
import { Icon } from "./Icon";

interface Props {
    sections: BookSection[];
    /** The block the book is at, by its place among them. */
    place: number;
    /** Told the block a section starts with, by its place, when it is chosen. */
    onGoTo: (place: number) => void;
    /** Told a section to read aloud, with those under it. */
    onPlay: (section: BookSection) => void;
    /** How much of the book is kept on the device. */
    offline: OfflineState | null;
    /** Told whether the book is to be kept on the device. */
    onKeepOffline: (keep: boolean) => void;
}

/** What tells a section from the others: where it starts and ends, as no two sections share both. */
function keyOf(section: BookSection): string {
    return `${section.start}-${section.end}`;
}

/**
 * The sections of a book as a tree, to go to one by choosing it. The
 * sections the book is at are marked, and open to show those under them.
 */
export function BookContents({ sections, place, onGoTo, onPlay, offline, onKeepOffline }: Props) {
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
                                            <Icon name="chevron" />
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
                                    <Icon name="play" />
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
            <div className="contents-heading">{t("Contents")}</div>
            <div className="contents-tree">{tree(sections)}</div>
            {offline && <OfflineBox state={offline} onKeep={onKeepOffline} />}
        </nav>
    );
}

/** The box that has a book kept on the device, with how much of it is. */
function OfflineBox({ state, onKeep }: { state: OfflineState; onKeep: (keep: boolean) => void }) {
    const { kept, syncing, audio, made, total, bytes } = state;
    const status = !kept
        ? t("Keeps the text and all its audio on this device, to read and listen without a connection.")
        : syncing && made !== null && audio < made
        ? t("Downloading the audio… {done} / {count}", { done: audio, count: made })
        : made === 0
        ? t("The text is on this device. No audio has been made of it yet.")
        : total !== null
        ? t("Audio of {done} of {total} sentences on this device · {size}", {
            done: audio,
            total,
            size: sizeOf(bytes),
        })
        : syncing
        ? t("Downloading…")
        : t("Waiting for the connection…");
    const progress = kept && made ? audio / made : 0;
    return (
        <label className={kept ? "contents-offline kept" : "contents-offline"}>
            <input type="checkbox" checked={kept} onChange={(event) => onKeep(event.target.checked)} />
            <span className="contents-offline-text">
                <span className="contents-offline-name">
                    <Icon name="download" />
                    {t("Available offline")}
                </span>
                <span className="contents-offline-status">{status}</span>
                {kept && made !== null && made > 0 && (
                    <span className="contents-offline-bar" aria-hidden="true">
                        <span style={{ width: `${Math.round(progress * 100)}%` }} />
                    </span>
                )}
            </span>
        </label>
    );
}
