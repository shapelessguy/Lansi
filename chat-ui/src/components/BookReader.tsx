// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { memo, useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";

import {
    type Book,
    type BookBlock,
    changeReading,
    fetchBook,
    fetchPicture,
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
    swipeTurn,
} from "../lib/books";
import { t } from "../lib/i18n";
import type { Where } from "../lib/logs";
import type { BookSelection } from "../lib/speaking";
import { BookContents } from "./BookContents";
import { Icon } from "./Icon";
import { SPOKEN_EVENT } from "./SpeechPlayer";

interface Props {
    /** The book to read, by its id, if one was chosen. */
    bookId: string | null;
    /** Whether the reader is on show. */
    active: boolean;
    /** What the book and the version are called as they are listed, which they may have been renamed to since. */
    names?: { title: string; version?: string };
    /** Told what of the book to read aloud, such as a section chosen in the contents. */
    onPlay: (selection: BookSelection) => void;
    /**
     * Which panels are shown beside the reader, told apart by anything that
     * changes with them: the reader may be moved by them without changing
     * its width, as when one on the left gives way to one on the right.
     */
    besides?: string;
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
export function BookReader({ bookId, active, names, onPlay, besides }: Props) {
    const [state, setState] = useState<BookState>({ status: "loading" });
    const [attempt, setAttempt] = useState(0);
    // how the text looks: its size, its font, its colours and how far apart its lines are
    const [look, setLook] = useState<Reading>(loadReading);
    const [optionsOpen, setOptionsOpen] = useState(false);
    // The text of the book alone on the whole screen, as the browser puts
    // the page there: the reader follows the browser's full screen, which
    // the browser's own way out, such as Escape or the Back of a phone, leaves.
    const [full, setFull] = useState(false);
    useEffect(() => {
        const follow = () => setFull(document.fullscreenElement !== null);
        document.addEventListener("fullscreenchange", follow);
        return () => document.removeEventListener("fullscreenchange", follow);
    }, []);
    // the text alone: what opens from the bar, which is not there to close it, is closed
    useEffect(() => {
        if (full) {
            setOptionsOpen(false);
            setContentsOpen(false);
        }
    }, [full]);
    function toggleFull() {
        if (document.fullscreenElement) {
            document.exitFullscreen().catch(() => {});
        } else {
            document.documentElement.requestFullscreen().catch(() => {});
        }
    }
    // nothing else of the app can be reached while it is on the screen, so it is left with the reader
    useEffect(() => {
        if (!active && document.fullscreenElement) {
            document.exitFullscreen().catch(() => {});
        }
    }, [active]);
    const [contentsOpen, setContentsOpen] = useState(false);
    // the paragraph at the top of the page of each book, and the character
    // of it the page starts at, by the id of the book
    const places = useRef(look.places);
    const offsets = useRef(look.offsets);
    // the places links were followed from, the last one last, to go back to
    const [trail, setTrail] = useState<number[]>([]);
    // what the pages are seen through, and the text, which is laid out in
    // columns as wide as that, one beside the other: each column is a page
    const view = useRef<HTMLDivElement>(null);
    // The pages are as wide as the window lets them be with no panel open
    // beside the reader (styles.css), so that a panel opened covers their
    // edge rather than having them counted again. They are kept where they
    // would be by how far the reader is from the left of the window.
    const area = useRef<HTMLDivElement>(null);
    const [fromLeft, setFromLeft] = useState(0);
    const columns = useRef<HTMLDivElement>(null);
    // the page that is shown, from 0, and how many there are
    const [page, setPage] = useState(0);
    const [pages, setPages] = useState(1);
    // how large the pages are, as text, to tell when it changes
    const [viewSize, setViewSize] = useState("");
    const book = state.status === "ready" && state.book.id === bookId ? state.book : null;
    const title = names?.title ?? book?.title ?? "";

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
        const observer = new ResizeObserver(() =>
            setViewSize((before) => {
                // The keyboard of a phone takes the foot of the window while
                // something is typed, such as the number of a page: the pages
                // keep their height under it rather than being counted again.
                const sameWidth = Number(before.split("x")[0]) === shown.clientWidth;
                return sameWidth && typing() ? before : `${shown.clientWidth}x${shown.clientHeight}`;
            })
        );
        observer.observe(shown);
        return () => observer.disconnect();
    }, [book]);

    // measured before the pages are shown where they were, so that they are never seen moved
    useLayoutEffect(() => {
        const shown = area.current;
        if (!shown) {
            return;
        }
        const measure = () => setFromLeft(shown.getBoundingClientRect().left);
        measure();
        const observer = new ResizeObserver(measure);
        observer.observe(shown);
        return () => observer.disconnect();
    }, [book, besides, active]);

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
        const block = laid.children[places.current[book.id] ?? 0] as HTMLElement | undefined;
        const left = block && leftOf(block, offsets.current[book.id] ?? 0);
        const wanted = left === undefined || left === null
            ? pageWith(places.current[book.id] ?? 0)
            : pageOf(left - laid.getBoundingClientRect().left, shown.clientWidth, PAGE_GAP);
        // the place is not kept again, so that it stays what was read however often the size changes
        setPage(Math.min(count - 1, wanted));
    }, [book, active, look.fontSize, look.font, look.spacing, viewSize, pageWith]);

    const keepPlace = useCallback((id: string, place: number, offset = 0) => {
        const kept = changeReading((before) => ({
            ...before,
            places: { ...before.places, [id]: place },
            offsets: { ...before.offsets, [id]: offset },
        }));
        places.current = kept.places;
        offsets.current = kept.offsets;
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
        // The place is the first character on the page: in the paragraph the
        // page is in the middle of, or that ends on it, if one does, and
        // otherwise at the start of the first paragraph that starts on it.
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
        const into = pageWith(low) < next ? low : low - 1;
        const block = laid.children[into] as HTMLElement | undefined;
        if (block) {
            const start = laid.getBoundingClientRect().left;
            const offset = firstWhere(block, (left) => pageOf(left - start, shown.clientWidth, PAGE_GAP) >= next);
            if (offset < (block.textContent?.length ?? 0)) {
                keepPlace(book.id, into, offset);
                return;
            }
        }
        keepPlace(book.id, low);
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

    // A swipe of a finger across the page turns it, as in a book: the page
    // follows the finger, and once it is let go slides on to the next or
    // back to where it was. A mouse turns none, as it selects by dragging,
    // and a finger held to select is taken by the browser, which cancels
    // the swipe.
    const swipe = useRef<{ x: number; y: number; at: number } | null>(null);
    // how far, in pixels, the page is drawn by the finger, while it is
    const [drawn, setDrawn] = useState(0);
    function onPointerDown(event: React.PointerEvent) {
        swipe.current = event.pointerType === "touch"
            ? { x: event.clientX, y: event.clientY, at: event.timeStamp }
            : null;
    }
    function onPointerMove(event: React.PointerEvent) {
        const from = swipe.current;
        if (!from || !(window.getSelection()?.isCollapsed ?? true)) {
            return;
        }
        const across = event.clientX - from.x;
        if (Math.abs(across) < 2 * Math.abs(event.clientY - from.y)) {
            return;
        }
        // past the first page or the last the page gives only a little
        const end = (page === 0 && across > 0) || (page === pages - 1 && across < 0);
        setDrawn(end ? across / 4 : across);
    }
    function letGo() {
        swipe.current = null;
        setDrawn(0);
    }
    function onPointerUp(event: React.PointerEvent) {
        const from = swipe.current;
        letGo();
        if (!from || event.pointerType !== "touch" || !(window.getSelection()?.isCollapsed ?? true)) {
            return;
        }
        const turned = swipeTurn(
            event.clientX - from.x,
            event.clientY - from.y,
            event.timeStamp - from.at,
            view.current?.clientWidth ?? window.innerWidth,
        );
        if (turned !== 0) {
            turnTo(page + turned);
        }
    }
    // A page turned to the next or the one before slides there, as one let go
    // by the finger does; one further off is shown at once.
    const shownPage = useRef(page);
    const slides = drawn === 0 && Math.abs(page - shownPage.current) <= 1;
    useEffect(() => {
        shownPage.current = page;
    }, [page]);

    function changeLook(change: Partial<Reading>) {
        setLook(changeReading((kept) => ({ ...kept, ...change })));
    }

    if (bookId === null) {
        return (
            <section className="reader">
                <p className="reader-note">
                    {t("Add an EPUB or PDF book under Books in the library, and choose it to read it here.")}
                </p>
            </section>
        );
    }

    const paper = PAPERS[look.paper];
    return (
        <section
            className={full ? "reader full" : "reader"}
            // the colours of the paper, which what floats over the text on the full screen takes after
            style={{
                ["--paper-background" as string]: paper.background || undefined,
                ["--paper-text" as string]: paper.color || undefined,
            }}
        >
            {/* how the book looks opens over the page, under the bar */}
            <div className="reader-top">
                <header className="reader-bar">
                    <button
                        className="icon-button"
                        aria-pressed={contentsOpen}
                        onClick={() => setContentsOpen(!contentsOpen)}
                        disabled={!book}
                        title={t("Contents")}
                        aria-label={t("Contents")}
                    >
                        ☰
                    </button>
                    <span className="reader-title">
                        {book
                            ? [title, book.version && (names?.version ?? book.version.name), book.author].filter(
                                Boolean,
                            ).join(" · ")
                            : ""}
                    </span>
                    {/* where the player of what is read aloud goes */}
                    <span className="speech-dock" data-speech-dock="book" />
                    {trail.length > 0 && (
                        <button onClick={goBack} title={t("Back to where the link was")}>
                            ↩ {t("Back")}
                        </button>
                    )}
                    {/* the buttons that belong together are kept together, as on the bar of the app */}
                    <div className="switch" role="group" aria-label={t("Pages")}>
                        <button
                            className="icon-button"
                            onClick={() => turnTo(page - 1)}
                            disabled={!book || page === 0}
                            title={t("Previous page")}
                            aria-label={t("Previous page")}
                        >
                            ‹
                        </button>
                        {book && <PageField page={page} pages={pages} onTurn={turnTo} />}
                        <button
                            className="icon-button"
                            onClick={() => turnTo(page + 1)}
                            disabled={!book || page >= pages - 1}
                            title={t("Next page")}
                            aria-label={t("Next page")}
                        >
                            ›
                        </button>
                    </div>
                    <div className="switch reader-view-tools" role="group" aria-label={t("How the book looks")}>
                        {document.fullscreenEnabled && (
                            <button
                                className="icon-button full-screen-toggle"
                                // the button lets go of the focus, whose ring would stay on it after the switch
                                onClick={(event) => {
                                    toggleFull();
                                    event.currentTarget.blur();
                                }}
                                title={full ? t("Leave full screen") : t("Full screen")}
                                aria-label={full ? t("Leave full screen") : t("Full screen")}
                            >
                                <Icon name={full ? "leave-full-screen" : "full-screen"} />
                            </button>
                        )}
                        <button
                            className="icon-button"
                            aria-pressed={optionsOpen}
                            onClick={() => setOptionsOpen(!optionsOpen)}
                            title={t("How the book looks")}
                            aria-label={t("How the book looks")}
                        >
                            Aa
                        </button>
                    </div>
                </header>
                {contentsOpen && book && (
                    <BookContents
                        sections={book.sections}
                        place={places.current[book.id] ?? 0}
                        onGoTo={(place) => {
                            goTo(place);
                            setContentsOpen(false);
                        }}
                        onPlay={(section) => {
                            goTo(section.start);
                            setContentsOpen(false);
                            // to the end of its last paragraph, however long it is
                            onPlay({
                                startBlock: section.start,
                                start: 0,
                                endBlock: section.end - 1,
                                end: Number.MAX_SAFE_INTEGER,
                            });
                        }}
                    />
                )}
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
                    ref={area}
                    style={{
                        fontSize: `${look.fontSize}px`,
                        fontFamily: FONTS[look.font].family,
                        lineHeight: SPACINGS[look.spacing].lineHeight,
                        background: paper.background || undefined,
                        color: paper.color || undefined,
                    }}
                    onWheel={onWheel}
                    onPointerDown={onPointerDown}
                    onPointerUp={onPointerUp}
                    onPointerMove={onPointerMove}
                    onPointerCancel={letGo}
                >
                    <div className="reader-view" ref={view} style={{ marginLeft: -fromLeft }}>
                        <div
                            className="reader-columns"
                            data-selectable="book"
                            data-where={JSON.stringify(
                                { kind: "book", id: book.id, title, page } satisfies Where,
                            )}
                            ref={columns}
                            style={{
                                // a picture is no higher than a page
                                ["--page-height" as string]: `${Number(viewSize.split("x")[1]) || 0}px`,
                                // the pages as high as they were counted, which the keyboard of a phone leaves as
                                // they are, rather than as high as the view
                                height: Number(viewSize.split("x")[1]) || undefined,
                                columnGap: `${PAGE_GAP}px`,
                                // a page further on is its own width and the gap to the left
                                // and one drawn by a finger is moved with it
                                transform: `translateX(calc(${-page} * (100% + ${PAGE_GAP}px) + ${drawn}px))`,
                                transition: slides ? "transform 0.25s ease-out" : "none",
                            }}
                        >
                            <Blocks bookId={book.id} blocks={book.blocks} onFollow={follow} />
                        </div>
                    </div>
                </div>
            )}
        </section>
    );
}

/** Where a character of the text of `block` is, by its place in it, from 0, if it is laid out. */
function characterRange(block: HTMLElement, offset: number): Range | null {
    const walker = document.createTreeWalker(block, NodeFilter.SHOW_TEXT);
    let left = offset;
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
        const length = node.textContent?.length ?? 0;
        if (left < length) {
            const range = document.createRange();
            range.setStart(node, left);
            range.setEnd(node, left + 1);
            return range;
        }
        left -= length;
    }
    return null;
}

/**
 * How far from the left of the window a character of `block` is, or the
 * first after it that takes up room, as a space where a line breaks may not;
 * null if none does.
 */
function leftOf(block: HTMLElement, offset: number): number | null {
    const length = block.textContent?.length ?? 0;
    for (let at = offset; at < length; at++) {
        const rect = characterRange(block, at)?.getBoundingClientRect();
        if (rect && (rect.width > 0 || rect.height > 0)) {
            return rect.left;
        }
    }
    return null;
}

/**
 * The first character of `block`, by its place in it, whose left `reached`
 * holds for, as it holds for every one after it; the length of its text if
 * none.
 */
function firstWhere(block: HTMLElement, reached: (left: number) => boolean): number {
    let low = 0;
    let high = block.textContent?.length ?? 0;
    while (low < high) {
        const middle = (low + high) >> 1;
        const left = leftOf(block, middle);
        if (left === null || reached(left)) {
            high = middle;
        } else {
            low = middle + 1;
        }
    }
    return low;
}

interface PageFieldProps {
    /** The page that is shown, from 0, and how many there are. */
    page: number;
    pages: number;
    /** Told the page to turn to, from 0. */
    onTurn: (page: number) => void;
}

/**
 * The page that is shown, as a number that can be written over to turn to
 * another: Enter or leaving it turns there, Escape leaves it as it was.
 */
function PageField({ page, pages, onTurn }: PageFieldProps) {
    // what is written in it while it is being written in
    const [draft, setDraft] = useState<string | null>(null);

    function turn() {
        const wanted = Number.parseInt(draft ?? "", 10);
        setDraft(null);
        if (Number.isFinite(wanted)) {
            onTurn(Math.min(pages, Math.max(1, wanted)) - 1);
        }
    }

    return (
        <span className="count page-field">
            <input
                type="text"
                inputMode="numeric"
                value={draft ?? String(page + 1)}
                size={Math.max(2, String(pages).length)}
                title={t("Page")}
                aria-label={t("Page")}
                onFocus={(event) => event.target.select()}
                onChange={(event) => setDraft(event.target.value.replace(/\D/g, ""))}
                onBlur={turn}
                onKeyDown={(event) => {
                    if (event.key === "Enter") {
                        event.currentTarget.blur();
                    } else if (event.key === "Escape") {
                        setDraft(null);
                        // the number that was there is put back before it is left
                        requestAnimationFrame(() => (event.target as HTMLInputElement).blur());
                    }
                }}
            />
            {` / ${pages}`}
        </span>
    );
}

interface BlocksProps {
    /** The book the blocks are of, for their pictures. */
    bookId: string;
    blocks: BookBlock[];
    /** Told the paragraph a link in the book leads to, by its place among them, when it is followed. */
    onFollow: (to: number) => void;
}

/** The paragraphs of a book, which are many, and are not gone through again when a page is turned. */
const Blocks = memo(function Blocks({ bookId, blocks, onFollow }: BlocksProps) {
    return (
        <>
            {blocks.map((block, index) =>
                block.image
                    ? (
                        // a paragraph of its own, as each block is one child of the columns
                        <p key={index} className="book-picture">
                            <BookPicture bookId={bookId} block={block} />
                        </p>
                    )
                    : (
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
                    )
            )}
        </>
    );
});

/**
 * A picture in the text of a book, as large as the book has it but never
 * wider or higher than a page. It takes its room before it has come, so
 * that the pages are laid out once, and is only shown while it is on the
 * page or on one beside it: a browser has every page of the book laid out,
 * and would otherwise keep every picture of it drawn.
 */
function BookPicture({ bookId, block }: { bookId: string; block: BookBlock }) {
    const [near, setNear] = useState(false);
    const [source, setSource] = useState<string | null>(null);
    const shown = useRef<HTMLImageElement>(null);

    useEffect(() => {
        const picture = shown.current;
        const view = picture?.closest(".reader-view");
        if (!picture || !view) {
            return;
        }
        // a page on either side of the one that is shown
        const observer = new IntersectionObserver(
            (entries) => setNear(entries.some((entry) => entry.isIntersecting)),
            { root: view, rootMargin: "0px 100%" },
        );
        observer.observe(picture);
        return () => observer.disconnect();
    }, []);

    useEffect(() => {
        let current = true;
        if (near && block.image) {
            fetchPicture(bookId, block.image).then((url) => current && setSource(url), () => undefined);
        } else {
            setSource(null);
        }
        return () => {
            current = false;
        };
    }, [bookId, block.image, near]);

    return (
        <img
            ref={shown}
            src={source ?? undefined}
            alt={block.alt ?? ""}
            width={block.width}
            height={block.height}
            decoding="async"
            draggable={false}
        />
    );
}

/** Whether what has the focus is typed in, which brings up the keyboard on a phone. */
function typing(): boolean {
    const focused = document.activeElement;
    return focused instanceof HTMLElement
        && (focused.matches("input:not([type=checkbox], [type=radio], [type=range], [type=button]), textarea")
            || focused.isContentEditable);
}
