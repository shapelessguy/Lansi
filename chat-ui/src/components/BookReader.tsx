// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { memo, useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";

import {
    type Book,
    type BookBlock,
    changeReading,
    fetchBook,
    FONTS,
    loadReading,
    MAX_FONT_SIZE,
    MIN_FONT_SIZE,
    pageCount,
    pageOf,
    PAPERS,
    type Reading,
    resized,
    segments,
    shownSize,
    SPACINGS,
} from "../lib/books";
import { t } from "../lib/i18n";
import type { Where } from "../lib/logs";
import { SPOKEN_EVENT } from "./SpeechPlayer";

interface Props {
    /** The book to read, by its id, if one was chosen. */
    bookId: string | null;
    /** Whether the reader is on show. */
    active: boolean;
}

type BookState =
    | { status: "loading" }
    | { status: "error"; message: string }
    | { status: "ready"; book: Book };

/** The space between one page and the next, in pixels. It is not seen. */
const PAGE_GAP = 48;
/** How long the wheel is not listened to after it has turned a page, in milliseconds. */
const WHEEL_PAUSE_MS = 250;
/** How many pages each key turns. */
const KEYS: Record<string, number> = {
    ArrowRight: 1,
    PageDown: 1,
    " ": 1,
    ArrowLeft: -1,
    PageUp: -1,
    Home: -Infinity,
    End: Infinity,
};

/** Shows a book a page at a time: its text, each part in its size, and nothing else. */
export function BookReader({ bookId, active }: Props) {
    const [state, setState] = useState<BookState>({ status: "loading" });
    const [attempt, setAttempt] = useState(0);
    // how the text looks: its size, its font, its colours and how far apart its lines are
    const [look, setLook] = useState<Reading>(loadReading);
    const [optionsOpen, setOptionsOpen] = useState(false);
    // the paragraph at the top of the page of each book, by the id of the book
    const places = useRef(look.places);
    // the places links were followed from, the last one last, to go back to
    const [trail, setTrail] = useState<number[]>([]);
    // what the pages are seen through, and the text, which is laid out in
    // columns as wide as that, one beside the other: each column is a page
    const view = useRef<HTMLDivElement>(null);
    const columns = useRef<HTMLDivElement>(null);
    // the page that is shown, from 0, and how many there are
    const [page, setPage] = useState(0);
    const [pages, setPages] = useState(1);
    // how large the pages are, as text, to tell when it changes
    const [viewSize, setViewSize] = useState("");
    const book = state.status === "ready" && state.book.id === bookId ? state.book : null;

    useEffect(() => {
        setTrail([]);
        if (bookId === null) {
            return;
        }
        let current = true;
        setState({ status: "loading" });
        fetchBook(bookId).then(
            (fetched) => current && setState({ status: "ready", book: fetched }),
            (error: Error) => current && setState({ status: "error", message: error.message }),
        );
        return () => {
            current = false;
        };
    }, [bookId, attempt]);

    useEffect(() => {
        const shown = view.current;
        if (!shown) {
            return;
        }
        const observer = new ResizeObserver(() => setViewSize(`${shown.clientWidth}x${shown.clientHeight}`));
        observer.observe(shown);
        return () => observer.disconnect();
    }, [book]);

    /** The page, from 0, that a paragraph starts on, by its place among the paragraphs. */
    const pageWith = useCallback((place: number): number => {
        const block = columns.current?.children[place] as HTMLElement | undefined;
        return block && view.current ? pageOf(block.offsetLeft, view.current.clientWidth, PAGE_GAP) : 0;
    }, []);

    // The book is opened where it was left. The pages are counted again, and
    // the place found among them, whenever the text is laid out anew: when
    // its look changes, when the pages do, and when the reader comes back on
    // show, as nothing is laid out while it is not shown.
    useLayoutEffect(() => {
        const shown = view.current;
        const laid = columns.current;
        if (!book || !shown || !laid || !active || shown.clientWidth === 0) {
            return;
        }
        const count = pageCount(laid.scrollWidth, shown.clientWidth, PAGE_GAP);
        setPages(count);
        setPage(Math.min(count - 1, pageWith(places.current[book.id] ?? 0)));
    }, [book, active, look.fontSize, look.font, look.spacing, viewSize, pageWith]);

    const keepPlace = useCallback((id: string, place: number) => {
        places.current = changeReading((kept) => ({ ...kept, places: { ...kept.places, [id]: place } })).places;
    }, []);

    const turnTo = useCallback((wanted: number) => {
        const shown = view.current;
        const laid = columns.current;
        if (!book || !shown || !laid) {
            return;
        }
        const count = pageCount(laid.scrollWidth, shown.clientWidth, PAGE_GAP);
        const next = Math.min(count - 1, Math.max(0, wanted));
        setPage(next);
        // The place is the first paragraph that starts on the page, or the
        // one the page is in the middle of if none does.
        let low = 0;
        let high = laid.children.length - 1;
        while (low < high) {
            const middle = (low + high) >> 1;
            if (pageWith(middle) >= next) {
                high = middle;
            } else {
                low = middle + 1;
            }
        }
        keepPlace(book.id, low > 0 && pageWith(low) > next ? low - 1 : low);
    }, [book, pageWith, keepPlace]);

    /** Shows the page a paragraph is on, and has the book left at that paragraph. */
    const goTo = useCallback((place: number) => {
        if (book) {
            setPage(pageWith(place));
            keepPlace(book.id, place);
        }
    }, [book, pageWith, keepPlace]);

    // a link in the book leads to another paragraph of it, and back from there
    const follow = useCallback((to: number) => {
        if (book) {
            const from = places.current[book.id] ?? 0;
            setTrail((before) => [...before, from]);
            goTo(to);
        }
    }, [book, goTo]);

    function goBack() {
        if (trail.length > 0) {
            goTo(trail[trail.length - 1]);
            setTrail(trail.slice(0, -1));
        }
    }

    // the keys turn the pages while the reader is on show
    const latestPage = useRef(page);
    latestPage.current = page;
    useEffect(() => {
        if (!active || !book) {
            return;
        }
        function onKeyDown(event: KeyboardEvent) {
            const target = event.target instanceof Element ? event.target : null;
            // a key that is typed somewhere, presses a button or is part of a shortcut is not for the book
            const typed = target?.closest("input, textarea, select, [contenteditable]");
            const pressed = event.key === " " && target?.closest("button, a");
            if (typed || pressed || event.ctrlKey || event.metaKey || event.altKey) {
                return;
            }
            if (event.key in KEYS) {
                event.preventDefault();
                turnTo(latestPage.current + KEYS[event.key]);
            }
        }
        window.addEventListener("keydown", onKeyDown);
        return () => window.removeEventListener("keydown", onKeyDown);
    }, [active, book, turnTo]);

    // the page with the sentence that is being read aloud is shown as it comes up
    useEffect(() => {
        if (!book) {
            return;
        }
        function onSpoken(event: Event) {
            const { bookId: spoken, range } = (event as CustomEvent<{ bookId: string; range: Range }>).detail;
            const shown = view.current;
            const laid = columns.current;
            if (spoken !== book?.id || !shown || !laid || shown.clientWidth === 0) {
                return;
            }
            const from = range.getBoundingClientRect().left - laid.getBoundingClientRect().left;
            const wanted = pageOf(from, shown.clientWidth, PAGE_GAP);
            if (wanted !== latestPage.current) {
                turnTo(wanted);
            }
        }
        window.addEventListener(SPOKEN_EVENT, onSpoken);
        return () => window.removeEventListener(SPOKEN_EVENT, onSpoken);
    }, [book, turnTo]);

    // a turn of the wheel arrives as many small ones, which are to turn one page
    const wheelAt = useRef(0);
    function onWheel(event: React.WheelEvent) {
        if (event.deltaY !== 0 && event.timeStamp - wheelAt.current > WHEEL_PAUSE_MS) {
            wheelAt.current = event.timeStamp;
            turnTo(page + Math.sign(event.deltaY));
        }
    }

    function changeLook(change: Partial<Reading>) {
        setLook(changeReading((kept) => ({ ...kept, ...change })));
    }

    if (bookId === null) {
        return (
            <section className="reader">
                <p className="reader-note">
                    {t("Add an EPUB book under Books in the library, and choose it to read it here.")}
                </p>
            </section>
        );
    }

    const paper = PAPERS[look.paper];
    return (
        <section className="reader">
            {/* how the book looks opens over the page, under the bar */}
            <div className="reader-top">
                <header className="reader-bar">
                    <span className="reader-title">
                        {book ? [book.title, book.author].filter(Boolean).join(" · ") : ""}
                    </span>
                    {/* where the player of what is read aloud goes */}
                    <span className="speech-dock" data-speech-dock="book" />
                    {trail.length > 0 && (
                        <button onClick={goBack} title={t("Back to where the link was")}>
                            ↩ {t("Back")}
                        </button>
                    )}
                    <button
                        className="icon-button"
                        onClick={() => turnTo(page - 1)}
                        disabled={!book || page === 0}
                        title={t("Previous page")}
                        aria-label={t("Previous page")}
                    >
                        ‹
                    </button>
                    <span className="count" title={t("Page")}>{book ? `${page + 1} / ${pages}` : ""}</span>
                    <button
                        className="icon-button"
                        onClick={() => turnTo(page + 1)}
                        disabled={!book || page >= pages - 1}
                        title={t("Next page")}
                        aria-label={t("Next page")}
                    >
                        ›
                    </button>
                    <button
                        className="icon-button"
                        aria-pressed={optionsOpen}
                        onClick={() => setOptionsOpen(!optionsOpen)}
                        title={t("How the book looks")}
                        aria-label={t("How the book looks")}
                    >
                        Aa
                    </button>
                </header>
                {optionsOpen && (
                    <div className="reader-options">
                        <label>
                            {t("Size")}
                            <button
                                className="icon-button"
                                onClick={() => changeLook({ fontSize: resized(look.fontSize, -1) })}
                                disabled={look.fontSize <= MIN_FONT_SIZE}
                                title={t("Smaller text")}
                                aria-label={t("Smaller text")}
                            >
                                A−
                            </button>
                            <span className="count" title={t("Size of the text, in pixels")}>{look.fontSize}</span>
                            <button
                                className="icon-button"
                                onClick={() => changeLook({ fontSize: resized(look.fontSize, 1) })}
                                disabled={look.fontSize >= MAX_FONT_SIZE}
                                title={t("Larger text")}
                                aria-label={t("Larger text")}
                            >
                                A+
                            </button>
                        </label>
                        <label>
                            {t("Font")}
                            <select
                                value={look.font}
                                onChange={(event) => changeLook({ font: event.target.value as Reading["font"] })}
                            >
                                {Object.entries(FONTS).map(([id, font]) => (
                                    <option key={id} value={id} style={{ fontFamily: font.family }}>
                                        {t(font.label)}
                                    </option>
                                ))}
                            </select>
                        </label>
                        <label>
                            {t("Lines")}
                            <select
                                value={look.spacing}
                                onChange={(event) => changeLook({ spacing: event.target.value as Reading["spacing"] })}
                            >
                                {Object.entries(SPACINGS).map(([id, spacing]) => (
                                    <option key={id} value={id}>{t(spacing.label)}</option>
                                ))}
                            </select>
                        </label>
                        <div className="swatches" role="radiogroup" aria-label={t("Background")}>
                            {Object.entries(PAPERS).map(([id, each]) => (
                                <button
                                    key={id}
                                    role="radio"
                                    aria-checked={look.paper === id}
                                    className="swatch"
                                    title={t(each.label)}
                                    aria-label={t("Background: {name}", { name: t(each.label) })}
                                    style={{
                                        background: each.background || "var(--bg)",
                                        color: each.color || "var(--text)",
                                    }}
                                    onClick={() => changeLook({ paper: id as Reading["paper"] })}
                                >
                                    A
                                </button>
                            ))}
                        </div>
                    </div>
                )}
            </div>
            {state.status === "loading" && <p className="reader-note">{t("Loading the book…")}</p>}
            {state.status === "error" && (
                <div className="reader-note error">
                    <p>{state.message}</p>
                    <button onClick={() => setAttempt(attempt + 1)}>{t("Try again")}</button>
                </div>
            )}
            {book && (
                <div
                    className="reader-page"
                    style={{
                        fontSize: `${look.fontSize}px`,
                        fontFamily: FONTS[look.font].family,
                        lineHeight: SPACINGS[look.spacing].lineHeight,
                        background: paper.background || undefined,
                        color: paper.color || undefined,
                    }}
                    onWheel={onWheel}
                >
                    <div className="reader-view" ref={view}>
                        <div
                            className="reader-columns"
                            data-selectable="book"
                            data-where={JSON.stringify(
                                { kind: "book", id: book.id, title: book.title, page } satisfies Where,
                            )}
                            ref={columns}
                            style={{
                                columnGap: `${PAGE_GAP}px`,
                                // a page further on is its own width and the gap to the left
                                transform: `translateX(calc(${-page} * (100% + ${PAGE_GAP}px)))`,
                            }}
                        >
                            <Blocks blocks={book.blocks} onFollow={follow} />
                        </div>
                    </div>
                </div>
            )}
        </section>
    );
}

interface BlocksProps {
    blocks: BookBlock[];
    /** Told the paragraph a link in the book leads to, by its place among them, when it is followed. */
    onFollow: (to: number) => void;
}

/** The paragraphs of a book, which are many, and are not gone through again when a page is turned. */
const Blocks = memo(function Blocks({ blocks, onFollow }: BlocksProps) {
    return (
        <>
            {blocks.map((block, index) => (
                <p key={index} style={block.size === 1 ? undefined : { fontSize: `${shownSize(block)}em` }}>
                    {block.links
                        ? segments(block).map((segment, at) =>
                            typeof segment.to === "number"
                                ? (
                                    <a
                                        key={at}
                                        role="link"
                                        tabIndex={-1}
                                        onClick={() => onFollow(segment.to as number)}
                                    >
                                        {segment.text}
                                    </a>
                                )
                                : segment.to
                                ? (
                                    // a link out of the book opens beside the app
                                    <a
                                        key={at}
                                        href={segment.to}
                                        target="_blank"
                                        rel="noreferrer noopener"
                                        tabIndex={-1}
                                    >
                                        {segment.text}
                                    </a>
                                )
                                : segment.text
                        )
                        : block.text}
                </p>
            ))}
        </>
    );
});
