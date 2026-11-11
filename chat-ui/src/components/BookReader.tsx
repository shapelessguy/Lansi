// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { memo, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

import {
    addBookNote,
    type Book,
    type BookBlock,
    type BookNote,
    type BookSection,
    bookWindows,
    changeBookNote,
    changeReading,
    deleteBookNote,
    doubleTap,
    fetchBook,
    fetchBookNotes,
    fetchPicture,
    FONTS,
    headings,
    liftOver,
    loadReading,
    MAX_FONT_SIZE,
    MIN_FONT_SIZE,
    type NoteBody,
    pageCount,
    pageOf,
    PAPERS,
    type Reading,
    resized,
    sectionAround,
    segments,
    shownSize,
    SPACINGS,
    swipeDrawn,
    swipeStep,
    swipeTurn,
    swipeUp,
    type Tap,
    windowAt,
} from "../lib/books";
import { t } from "../lib/i18n";
import { useMediaQuery } from "../lib/layout";
import type { Where } from "../lib/logs";
import { BLOCK_ATTRIBUTE, bookBlock, type BookPlace, type BookSelection, laidBlocks, placeOf } from "../lib/speaking";
import { BookContents } from "./BookContents";
import { BookNoteBox } from "./BookNoteBox";
import { Icon } from "./Icon";
import { PLAY_SECTION_EVENT, TRANSLATE_EVENT } from "./SelectionTools";
import { CONTROL_EVENT, LAID_OUT_EVENT, type SpeechControl, SPOKEN_EVENT, SPOKEN_HIGHLIGHT } from "./SpeechPlayer";

interface Props {
    /** The book to read, by its id, if one was chosen. */
    bookId: string | null;
    /** Whether the reader is on show. */
    active: boolean;
    /** What the book and the version are called as they are listed, which they may have been renamed to since. */
    names?: { title: string; version?: string };
    /** Told what of the book to read aloud, such as a section chosen in the contents. */
    onPlay: (selection: BookSelection, from?: BookPlace) => void;
    /**
     * Which panels are shown beside the reader, told apart by anything that
     * changes with them: the reader may be moved by them without changing
     * its width, as when one on the left gives way to one on the right.
     */
    besides?: string;
    /** The selection a note was last asked to be written on, which the box to write it opens for as it changes. */
    noteAsked?: NoteAsked | null;
}

/** A selection of the book in the reader that a note is to be written on, and the text it is. */
export interface NoteAsked {
    selection: BookSelection;
    quote: string;
    /** Changes each time a note is asked for. */
    nonce: number;
}

/** The note open in its box: one kept, or one to write on a selection. */
type NoteOpen = { note: BookNote } | { note: null; selection: BookSelection; quote: string };

/** What the stretches of text with a note on them are highlighted as (styles.css). */
const NOTE_HIGHLIGHT = "book-note";
/** How far, in pixels, a click may have been dragged and still open the note it is on. */
const CLICK_SLOP = 8;

type BookState =
    | { status: "loading" }
    | { status: "error"; message: string }
    | { status: "ready"; book: Book };

/** The space between one page and the next, in pixels. It is not seen. */
const PAGE_GAP = 48;
/** How long a page turned to slides, in milliseconds (the transition of the columns). */
const SLIDE_MS = 250;
/** How long the wheel is not listened to after it has turned a page, in milliseconds. */
const WHEEL_PAUSE_MS = 250;
/** A window as narrow as a phone's, as the styles also say at this width. */
const NARROW = "(max-width: 720px)";
/** How long, in milliseconds, the bar on the full screen is shown once the page is tapped. */
const REVEAL_MS = 5000;
/** How far, in pixels, the bar on the full screen is from the edges of the screen and from the sentence read aloud. */
const BAR_MARGIN = 12;
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
export function BookReader({ bookId, active, names, onPlay, besides, noteAsked }: Props) {
    const [state, setState] = useState<BookState>({ status: "loading" });
    const [attempt, setAttempt] = useState(0);
    // how the text looks: its size, its font, its colours and how far apart its lines are
    const [look, setLook] = useState<Reading>(loadReading);
    const [optionsOpen, setOptionsOpen] = useState(false);
    // The text of the book alone on the whole screen, as the browser puts
    // the page there: the reader follows the browser's full screen, which
    // the browser's own way out, such as Escape or the Back of a phone, leaves.
    const [full, setFull] = useState(false);
    // On the full screen, and on a phone, where the bar has no room for it,
    // the player floats over the text, at the bottom right, with buttons
    // large enough for a finger.
    const narrow = useMediaQuery(NARROW);
    const floating = full || narrow;
    // On the full screen the bar is hidden, leaving the text alone, until
    // the page is tapped or clicked, and then shown for a while, again
    // from the start each time it is touched itself.
    const [revealed, setRevealed] = useState(false);
    const revealTimer = useRef(0);
    const reveal = useCallback(() => {
        setRevealed(true);
        window.clearTimeout(revealTimer.current);
        revealTimer.current = window.setTimeout(() => setRevealed(false), REVEAL_MS);
    }, []);
    useEffect(() => {
        if (full) {
            reveal();
        } else {
            window.clearTimeout(revealTimer.current);
            setRevealed(false);
        }
    }, [full, reveal]);
    useEffect(() => () => window.clearTimeout(revealTimer.current), []);
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
    // The book is laid out in parts (bookWindows): the one that is read, and
    // the one before it and the one after it, so that the pages turn on into
    // them as into any other. Each is laid out in columns of its own, beside
    // the one before it, so that it starts on a page of its own and its pages
    // stay as they are whichever parts are laid out beside it.
    const windows = useMemo(() => book ? bookWindows(book.blocks, book.sections) : [], [book]);
    const [chosenWindow, setChosenWindow] = useState<{ bookId: string; at: number } | null>(null);
    // the part where the book was left, as it was opened
    const opened = useMemo(
        () => windowAt(windows, book ? places.current[book.id] ?? 0 : 0),
        [windows, book],
    );
    const at = book && chosenWindow?.bookId === book.id ? chosenWindow.at : opened;
    const mounted = useMemo(() => {
        const from = Math.max(0, at - 1);
        const to = Math.min(windows.length - 1, at + 1);
        return {
            start: windows[from]?.start ?? 0,
            end: windows[to]?.end ?? 0,
            windows: windows.slice(from, to + 1),
        };
    }, [windows, at]);
    // The page each part laid out starts on, from 0, by its first block, as
    // the parts are counted; kept for what reads it at once as well.
    const [firstPages, setFirstPages] = useState<Record<number, number>>({});
    const counted = useRef<Record<number, number>>({});
    // whether the page last turned to slides there, as one turned by a hand does
    const [slides, setSlides] = useState(false);
    // counted up as the text laid out changes its size, as when a font comes, to count the pages again
    const [relaid, setRelaid] = useState(0);
    const title = names?.title ?? book?.title ?? "";
    // the notes written on the book, by the id of the book they are of
    const [notes, setNotes] = useState<{ bookId: string; notes: BookNote[] } | null>(null);
    const bookNotes = useMemo(() => book && notes?.bookId === book.id ? notes.notes : [], [book, notes]);
    const [noteOpen, setNoteOpen] = useState<NoteOpen | null>(null);
    // the stretch of the page each note is on, as it is laid out
    const noteRanges = useRef<{ note: BookNote; range: Range }[]>([]);
    // where the last click on the text was pressed, to tell it from a drag
    const pressed = useRef({ x: 0, y: 0 });

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
        fetchBookNotes(bookId).then(
            (fetched) => current && setNotes({ bookId, notes: fetched }),
            (error: Error) => console.warn("the notes on the book could not be had:", error),
        );
        return () => {
            current = false;
        };
    }, [bookId, attempt]);

    // the box to write a note in opens for each selection a note is asked for on
    const askedSeen = useRef(noteAsked?.nonce);
    useEffect(() => {
        if (!noteAsked || noteAsked.nonce === askedSeen.current) {
            return;
        }
        askedSeen.current = noteAsked.nonce;
        if (book) {
            window.getSelection()?.removeAllRanges();
            setNoteOpen({ note: null, selection: noteAsked.selection, quote: noteAsked.quote });
        }
    }, [noteAsked, book]);

    // The stretches of text with a note on them are highlighted, which
    // leaves the page as it is: the book is laid out once, so the stretches
    // are found again only as the notes change.
    useEffect(() => {
        const laid = columns.current;
        if (!book || !laid || typeof Highlight === "undefined") {
            return;
        }
        noteRanges.current = bookNotes.flatMap((note) => {
            const range = noteRange(laid, note);
            return range ? [{ note, range }] : [];
        });
        CSS.highlights?.set(NOTE_HIGHLIGHT, new Highlight(...noteRanges.current.map(({ range }) => range)));
        return () => {
            CSS.highlights?.delete(NOTE_HIGHLIGHT);
            noteRanges.current = [];
        };
    }, [book, bookNotes, mounted]);

    /** The note on the text at a point of the window, if one is there. */
    function noteAt(x: number, y: number): BookNote | null {
        const found = noteRanges.current.find(({ range }) =>
            [...range.getClientRects()].some((rect) =>
                rect.left <= x && x <= rect.right && rect.top <= y && y <= rect.bottom
            )
        );
        return found?.note ?? null;
    }

    // a note opens as the text it is on is clicked or tapped, as a link does
    function onTextClick(event: React.MouseEvent) {
        const dragged = Math.hypot(event.clientX - pressed.current.x, event.clientY - pressed.current.y);
        const selecting = !(window.getSelection()?.isCollapsed ?? true);
        if (dragged > CLICK_SLOP || selecting || (event.target as Element).closest("a")) {
            return;
        }
        const note = noteAt(event.clientX, event.clientY);
        if (note) {
            setNoteOpen({ note });
        }
    }

    async function saveNote(open: NoteOpen, body: NoteBody) {
        if (!book) {
            return;
        }
        const kept = open.note
            ? await changeBookNote(book.id, open.note.id, body)
            : await addBookNote(book.id, open.selection, open.quote, body);
        const others = bookNotes.filter((each) => each.id !== kept.id);
        setNotes({ bookId: book.id, notes: [...others, kept].sort(byPlace) });
        setNoteOpen(null);
    }

    async function deleteNote(note: BookNote) {
        if (!book) {
            return;
        }
        await deleteBookNote(book.id, note.id);
        setNotes({ bookId: book.id, notes: bookNotes.filter((each) => each.id !== note.id) });
        setNoteOpen(null);
    }

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

    /**
     * The page, from 0, among those laid out, of what is `x` from the left
     * of the window in the part of the book `inside` is in, which is where
     * the part starts and the page in it.
     */
    const pageAt = useCallback((x: number, inside: Element): number => {
        const part = inside.closest<HTMLElement>(".reader-window");
        const width = view.current?.clientWidth ?? 0;
        if (!part || width === 0) {
            return 0;
        }
        const first = counted.current[Number(part.dataset.start)] ?? 0;
        return first + pageOf(x - part.getBoundingClientRect().left, width, PAGE_GAP);
    }, []);

    /** The page, from 0, that a paragraph starts on, if it is laid out. */
    const pageOfBlock = useCallback((block: HTMLElement): number => {
        const part = block.closest<HTMLElement>(".reader-window");
        const width = view.current?.clientWidth ?? 0;
        if (!part || width === 0) {
            return 0;
        }
        return (counted.current[Number(part.dataset.start)] ?? 0) + pageOf(block.offsetLeft, width, PAGE_GAP);
    }, []);

    /** The page, from 0, that a paragraph starts on, by its place among the paragraphs, if it is laid out. */
    const pageWith = useCallback((place: number): number => {
        const block = columns.current && bookBlock(columns.current, place);
        return block ? pageOfBlock(block) : 0;
    }, [pageOfBlock]);

    // the pages are counted again as the text laid out changes its size, such as when its font has come
    useEffect(() => {
        const laid = columns.current;
        if (!laid) {
            return;
        }
        let frame = 0;
        let seen = false;
        const again = () => {
            cancelAnimationFrame(frame);
            frame = requestAnimationFrame(() => setRelaid((before) => before + 1));
        };
        const observer = new ResizeObserver(() => {
            // it is told of each paragraph as it starts to watch it, which is the size counted already
            if (seen) {
                again();
            }
            seen = true;
        });
        laidBlocks(laid).forEach((block) => observer.observe(block));
        document.fonts?.addEventListener("loadingdone", again);
        return () => {
            observer.disconnect();
            document.fonts?.removeEventListener("loadingdone", again);
            cancelAnimationFrame(frame);
        };
    }, [book, mounted, active]);

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
        // each part has as many pages as its columns, and starts after the one before it
        const firsts: Record<number, number> = {};
        let count = 0;
        for (const part of laid.children as HTMLCollectionOf<HTMLElement>) {
            firsts[Number(part.dataset.start)] = count;
            count += pageCount(part.scrollWidth, shown.clientWidth, PAGE_GAP);
        }
        counted.current = firsts;
        setFirstPages(firsts);
        setPages(Math.max(1, count));
        const block = bookBlock(laid, places.current[book.id] ?? 0);
        const left = block && leftOf(block, offsets.current[book.id] ?? 0);
        const wanted = !block ? 0 : left === null || left === undefined ? pageOfBlock(block) : pageAt(left, block);
        // the place is not kept again, so that it stays what was read however often the size changes
        setPage(Math.min(Math.max(1, count) - 1, wanted));
        // what is laid out anew is shown where it is, not slid to
        setSlides(false);
        window.dispatchEvent(new CustomEvent(LAID_OUT_EVENT));
    }, [book, active, look.fontSize, look.font, look.spacing, viewSize, pageAt, pageOfBlock, mounted, relaid]);

    // The part that is read is laid out with those beside it once the page
    // turned into it has slid there, as they are laid out anew.
    const settling = useRef<number | undefined>(undefined);
    useEffect(() => () => window.clearTimeout(settling.current), []);
    const settle = useCallback((place: number, now = false) => {
        if (!book) {
            return;
        }
        window.clearTimeout(settling.current);
        const wanted = windowAt(windows, place);
        if (wanted === at) {
            return;
        }
        const choose = () => setChosenWindow({ bookId: book.id, at: wanted });
        if (now) {
            choose();
        } else {
            settling.current = window.setTimeout(choose, SLIDE_MS + 50);
        }
    }, [book, windows, at]);

    const latestPage = useRef(page);
    latestPage.current = page;

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
        const next = Math.min(pages - 1, Math.max(0, wanted));
        setPage(next);
        // the next page or the one before slides there, one further off is shown at once
        setSlides(Math.abs(next - latestPage.current) <= 1);
        // The place is the first character on the page: in the paragraph the
        // page is in the middle of, or that ends on it, if one does, and
        // otherwise at the start of the first paragraph that starts on it.
        const blocks = laidBlocks(laid);
        let low = 0;
        let high = blocks.length - 1;
        while (low < high) {
            const middle = (low + high) >> 1;
            if (pageOfBlock(blocks[middle]) >= next) {
                high = middle;
            } else {
                low = middle + 1;
            }
        }
        const into = blocks[low] && pageOfBlock(blocks[low]) < next ? low : low - 1;
        const block = blocks[into];
        if (block) {
            const offset = firstWhere(block, (left) => pageAt(left, block) >= next);
            if (offset < (block.textContent?.length ?? 0)) {
                keepPlace(book.id, placeOf(block), offset);
                settle(placeOf(block));
                return;
            }
        }
        if (blocks[low]) {
            keepPlace(book.id, placeOf(blocks[low]));
            settle(placeOf(blocks[low]));
        }
    }, [book, pages, pageAt, pageOfBlock, keepPlace, settle]);

    /**
     * Shows the page a paragraph is on, and has the book left at that
     * paragraph: at once if it is laid out, and otherwise once its part is.
     */
    const goTo = useCallback((place: number) => {
        if (!book) {
            return;
        }
        keepPlace(book.id, place);
        setSlides(false);
        if (mounted.start <= place && place < mounted.end) {
            setPage(pageWith(place));
            settle(place);
        } else {
            settle(place, true);
        }
    }, [book, pageWith, keepPlace, mounted, settle]);

    // a section read aloud, from its contents or from the button on its heading, to the end of its last paragraph,
    // however long it is
    const playSection = useCallback((section: BookSection) => {
        onPlay({ startBlock: section.start, start: 0, endBlock: section.end - 1, end: Number.MAX_SAFE_INTEGER });
    }, [onPlay]);
    // what is selected is read aloud with the whole of the smallest section it is in, from where it starts
    useEffect(() => {
        if (!book) {
            return;
        }
        function onPlaySection(event: Event) {
            const { selection } = (event as CustomEvent<{ selection: BookSelection }>).detail;
            const around = sectionAround(book!.sections, selection.startBlock);
            const whole = around
                ? { startBlock: around.start, start: 0, endBlock: around.end - 1, end: Number.MAX_SAFE_INTEGER }
                : { ...selection, endBlock: book!.blocks.length - 1, end: Number.MAX_SAFE_INTEGER };
            onPlay(whole, { block: selection.startBlock, offset: selection.start });
        }
        window.addEventListener(PLAY_SECTION_EVENT, onPlaySection);
        return () => window.removeEventListener(PLAY_SECTION_EVENT, onPlaySection);
    }, [book, onPlay]);
    const headed = useMemo(() => book ? headings(book.blocks, book.sections) : new Map<number, BookSection>(), [
        book,
    ]);

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
    // The section the page shown is in, among those laid out, as the first
    // of its pages and how many it has: the page is told by its place in it.
    const starts = mounted.windows.map((each) => firstPages[each.start] ?? 0);
    let shownWindow = 0;
    while (shownWindow + 1 < starts.length && starts[shownWindow + 1] <= page) {
        shownWindow++;
    }
    const section = {
        first: starts[shownWindow] ?? 0,
        count: Math.max(1, (starts[shownWindow + 1] ?? pages) - (starts[shownWindow] ?? 0)),
    };
    const latestSection = useRef(section);
    latestSection.current = section;
    // the first page of the book and the last, which nothing is turned past
    const atStart = page === 0 && mounted.start === 0;
    const atEnd = page >= pages - 1 && mounted.end >= (book?.blocks.length ?? 0);
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
                // Home and End go to the first and the last page of the section
                const { first, count } = latestSection.current;
                const step = KEYS[event.key];
                turnTo(
                    step === -Infinity ? first : step === Infinity ? first + count - 1 : latestPage.current + step,
                );
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
            const { bookId: spoken, range, block } = (
                event as CustomEvent<{ bookId: string; range: Range | null; block: number }>
            ).detail;
            const shown = view.current;
            const laid = columns.current;
            if (spoken !== book?.id || !shown || !laid || shown.clientWidth === 0) {
                return;
            }
            // a sentence of a part that is not laid out is shown once its part is
            if (!range) {
                goTo(block);
                return;
            }
            const inside = range.startContainer instanceof Element
                ? range.startContainer
                : range.startContainer.parentElement;
            const wanted = inside ? pageAt(range.getBoundingClientRect().left, inside) : latestPage.current;
            if (wanted !== latestPage.current) {
                turnTo(wanted);
            }
        }
        window.addEventListener(SPOKEN_EVENT, onSpoken);
        return () => window.removeEventListener(SPOKEN_EVENT, onSpoken);
    }, [book, turnTo, goTo, pageAt]);

    // On the full screen the bar is at the bottom right, where a hand holding
    // a tablet reaches it, and goes up over the sentence read aloud, as far
    // as it takes to leave each line of it to be read.
    const bar = useRef<HTMLDivElement>(null);
    const [lift, setLift] = useState(0);
    const lifted = useRef(0);
    const placeBar = useCallback(() => {
        const shown = bar.current;
        const marked = CSS.highlights?.get(SPOKEN_HIGHLIGHT);
        let by = 0;
        if (floating && shown && marked) {
            const at = shown.getBoundingClientRect();
            // where it is with no lift
            const rest = {
                top: at.top + lifted.current,
                bottom: at.bottom + lifted.current,
                left: at.left,
                right: at.right,
            };
            const lines = [...marked].flatMap((range) => [...(range as Range).getClientRects()]);
            // never above the top of the reader, should the sentence take up all of it
            const top = shown.offsetParent?.getBoundingClientRect().top ?? 0;
            by = Math.max(0, Math.min(liftOver(lines, rest, BAR_MARGIN), rest.top - top - BAR_MARGIN));
        }
        lifted.current = by;
        setLift(by);
    }, [floating]);
    // placed again as the sentence, the page, the text or the bar change, and once the page turned to has slid in
    useEffect(() => {
        if (!floating) {
            placeBar();
            return;
        }
        let slid = 0;
        function again() {
            placeBar();
            window.clearTimeout(slid);
            slid = window.setTimeout(placeBar, SLIDE_MS + 50);
        }
        again();
        window.addEventListener(SPOKEN_EVENT, again);
        window.addEventListener("resize", again);
        const resized = new ResizeObserver(again);
        if (bar.current) {
            resized.observe(bar.current);
        }
        return () => {
            window.clearTimeout(slid);
            window.removeEventListener(SPOKEN_EVENT, again);
            window.removeEventListener("resize", again);
            resized.disconnect();
        };
    }, [floating, placeBar, page, look, viewSize]);

    // a turn of the wheel arrives as many small ones, which are to turn one page
    const wheelAt = useRef(0);
    function onWheel(event: React.WheelEvent) {
        if (event.deltaY !== 0 && event.timeStamp - wheelAt.current > WHEEL_PAUSE_MS) {
            wheelAt.current = event.timeStamp;
            turnTo(page + Math.sign(event.deltaY));
        }
    }

    // A swipe of a finger across the page turns it, as in a book: the page
    // follows the finger, once it has moved far enough to be more than one
    // that selects, and once it is let go slides on to the next or
    // back to where it was. A mouse turns none, as it selects by dragging,
    // and a finger held to select is taken by the browser, which cancels
    // the swipe.
    const swipe = useRef<{ x: number; y: number; at: number } | null>(null);
    // how far, in pixels, the page is drawn by the finger, while it is
    const [drawn, setDrawn] = useState(0);
    // The book read aloud is controlled by touches too: a double tap pauses
    // it or plays it on, a swipe of two fingers moves it on a sentence to
    // the left, as a page is turned, and back one to the right, and a swipe
    // up from the sentence that is heard has it translated.
    function control(wanted: SpeechControl) {
        if (book) {
            window.dispatchEvent(new CustomEvent(CONTROL_EVENT, { detail: { bookId: book.id, control: wanted } }));
        }
    }
    // where each finger on the page touched it, and whether those on it are two, or were, which they are until
    // all are lifted, and the first of them lifted has moved the reading
    const fingers = useRef(new Map<number, { x: number; y: number }>());
    const twoFingers = useRef<"down" | "done" | null>(null);
    // the tap before, for a double tap
    const lastTap = useRef<Tap | null>(null);
    // the sentence heard, if the finger on the page touched it
    const heardTouched = useRef<Range | null>(null);
    function onPointerDown(event: React.PointerEvent) {
        pressed.current = { x: event.clientX, y: event.clientY };
        heardTouched.current = event.pointerType === "touch" ? heardAt(event.clientX, event.clientY) : null;
        if (event.pointerType === "touch") {
            fingers.current.set(event.pointerId, { x: event.clientX, y: event.clientY });
        }
        if (fingers.current.size >= 2) {
            twoFingers.current ??= "down";
            lastTap.current = null;
            letGo();
            return;
        }
        swipe.current = event.pointerType === "touch"
            ? { x: event.clientX, y: event.clientY, at: event.timeStamp }
            : null;
    }
    function liftFinger(event: React.PointerEvent) {
        const from = fingers.current.get(event.pointerId);
        fingers.current.delete(event.pointerId);
        if (fingers.current.size === 0 && twoFingers.current) {
            twoFingers.current = null;
            // the last finger of two is lifted with nothing more to do
            return { from, two: true };
        }
        return { from, two: twoFingers.current !== null };
    }
    function onPointerMove(event: React.PointerEvent) {
        const from = swipe.current;
        if (!from || !(window.getSelection()?.isCollapsed ?? true)) {
            return;
        }
        const across = swipeDrawn(event.clientX - from.x, event.clientY - from.y);
        // past the first page or the last the page gives only a little
        const end = (atStart && across > 0) || (atEnd && across < 0);
        setDrawn(end ? across / 4 : across);
    }
    function letGo() {
        swipe.current = null;
        setDrawn(0);
    }
    function onPointerCancel(event: React.PointerEvent) {
        liftFinger(event);
        letGo();
    }
    function onPointerUp(event: React.PointerEvent) {
        if (full && Math.hypot(event.clientX - pressed.current.x, event.clientY - pressed.current.y) <= CLICK_SLOP) {
            reveal();
        }
        const from = swipe.current;
        letGo();
        const lifted = liftFinger(event);
        if (lifted.two) {
            if (twoFingers.current === "down" && lifted.from) {
                const step = swipeStep(event.clientX - lifted.from.x, event.clientY - lifted.from.y);
                if (step !== 0) {
                    twoFingers.current = "done";
                    control(step > 0 ? "next" : "previous");
                }
            }
            return;
        }
        if (!from || event.pointerType !== "touch") {
            return;
        }
        const heard = heardTouched.current;
        heardTouched.current = null;
        if (heard && swipeUp(event.clientX - from.x, event.clientY - from.y)) {
            lastTap.current = null;
            window.dispatchEvent(new CustomEvent(TRANSLATE_EVENT, { detail: { range: heard } }));
            return;
        }
        const tap = { x: event.clientX, y: event.clientY, at: event.timeStamp };
        const still = Math.hypot(tap.x - from.x, tap.y - from.y) <= CLICK_SLOP;
        if (still && book && !(event.target as Element).closest("button, a")) {
            if (doubleTap(lastTap.current, tap)) {
                lastTap.current = null;
                // and leaves the word the browser may have selected with it
                window.getSelection()?.removeAllRanges();
                control("toggle");
            } else {
                lastTap.current = tap;
            }
            return;
        }
        lastTap.current = null;
        if (!(window.getSelection()?.isCollapsed ?? true)) {
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
                <header
                    className={full ? `reader-bar big-player${revealed ? "" : " concealed"}` : "reader-bar"}
                    ref={full ? bar : undefined}
                    onPointerDown={full ? reveal : undefined}
                    style={full ? { bottom: BAR_MARGIN + lift } : undefined}
                >
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
                    {(full || !narrow) && <span className="speech-dock" data-speech-dock="book" />}
                    {trail.length > 0 && (
                        <button onClick={goBack} title={t("Back to where the link was")}>
                            ↩ {t("Back")}
                        </button>
                    )}
                    {/* the buttons that belong together are kept together, as on the bar of the app */}
                    <div className="switch" role="group" aria-label={t("Pages")}>
                        <button
                            className="icon-button page-turn"
                            onClick={() => turnTo(page - 1)}
                            disabled={!book || atStart}
                            title={t("Previous page")}
                            aria-label={t("Previous page")}
                        >
                            ‹
                        </button>
                        {book && (
                            <span className="count page-field" title={t("Page")}>
                                {page - section.first + 1}/{section.count}
                            </span>
                        )}
                        <button
                            className="icon-button page-turn"
                            onClick={() => turnTo(page + 1)}
                            disabled={!book || atEnd}
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
                            playSection(section);
                        }}
                    />
                )}
                {narrow && !full && (
                    <div className="reader-float big-player" ref={bar} style={{ bottom: BAR_MARGIN + lift }}>
                        <span className="speech-dock" data-speech-dock="book" />
                    </div>
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
                    onPointerCancel={onPointerCancel}
                >
                    <div className="reader-view" ref={view} style={{ marginLeft: -fromLeft }}>
                        <div
                            className="reader-columns"
                            data-selectable="book"
                            data-where={JSON.stringify(
                                { kind: "book", id: book.id, title, page: page - section.first } satisfies Where,
                            )}
                            ref={columns}
                            onClick={onTextClick}
                            onMouseMove={(event) =>
                                event.currentTarget.classList.toggle(
                                    "on-note",
                                    noteAt(event.clientX, event.clientY) !== null,
                                )}
                            style={{
                                // a picture is no higher than a page
                                ["--page-height" as string]: `${Number(viewSize.split("x")[1]) || 0}px`,
                                // the pages as high as they were counted, which the keyboard of a phone leaves as
                                // they are, rather than as high as the view
                                height: Number(viewSize.split("x")[1]) || undefined,
                                // a page further on is its own width and the gap to the left
                                // and one drawn by a finger is moved with it
                                transform: `translateX(calc(${-page} * (100% + ${PAGE_GAP}px) + ${drawn}px))`,
                                transition: slides && drawn === 0 ? `transform ${SLIDE_MS}ms ease-out` : "none",
                            }}
                        >
                            {mounted.windows.map((part) => (
                                <div
                                    key={part.start}
                                    className="reader-window"
                                    data-start={part.start}
                                    style={{
                                        // after the pages of the parts before it
                                        left: `calc(${firstPages[part.start] ?? 0} * (100% + ${PAGE_GAP}px))`,
                                        columnGap: `${PAGE_GAP}px`,
                                    }}
                                >
                                    <Blocks
                                        bookId={book.id}
                                        blocks={book.blocks}
                                        start={part.start}
                                        end={part.end}
                                        onFollow={follow}
                                        headings={headed}
                                        onPlay={playSection}
                                    />
                                </div>
                            ))}
                        </div>
                    </div>
                </div>
            )}
            {noteOpen && (
                <BookNoteBox
                    quote={noteOpen.note ? noteOpen.note.quote : noteOpen.quote}
                    note={noteOpen.note}
                    onSave={(body) => saveNote(noteOpen, body)}
                    onDelete={() => (noteOpen.note ? deleteNote(noteOpen.note) : Promise.resolve())}
                    onClose={() => setNoteOpen(null)}
                />
            )}
        </section>
    );
}

/** The notes on a book in the order of its text. */
function byPlace(a: BookNote, b: BookNote): number {
    return a.startBlock - b.startBlock || a.start - b.start || a.createdAt - b.createdAt;
}

/** Where a character of the text of `block` is, by its place in it, from 0, as a point of a range; its end if it is past it. */
function pointIn(block: Element, offset: number): [Node, number] {
    const walker = document.createTreeWalker(block, NodeFilter.SHOW_TEXT);
    let left = offset;
    let last: Text | null = null;
    for (let node = walker.nextNode() as Text | null; node; node = walker.nextNode() as Text | null) {
        if (left <= node.data.length) {
            return [node, left];
        }
        left -= node.data.length;
        last = node;
    }
    return last ? [last, last.data.length] : [block, block.childNodes.length];
}

/**
 * The stretch of the page a note is on, among the paragraphs laid out in
 * `laid`, as much of it as is laid out, if any is.
 */
function noteRange(laid: Element, note: BookNote): Range | null {
    const blocks = laidBlocks(laid);
    const first = blocks[0];
    const last = blocks[blocks.length - 1];
    if (!first || !last || note.endBlock < placeOf(first) || note.startBlock > placeOf(last)) {
        return null;
    }
    const from = bookBlock(laid, note.startBlock);
    const to = bookBlock(laid, note.endBlock);
    // a note that starts before what is laid out, or ends after it, is cut where it is
    const range = document.createRange();
    if (from) {
        range.setStart(...pointIn(from, note.start));
    } else {
        range.setStartBefore(first);
    }
    if (to) {
        range.setEnd(...pointIn(to, note.end));
    } else {
        range.setEndAfter(last);
    }
    return range;
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

/** How far, in pixels, a finger may touch from the sentence that is heard to touch it. */
const HEARD_SLOP = 12;

/** The sentence that is heard, marked in the book, if it is at a point of the window, or near it. */
function heardAt(x: number, y: number): Range | null {
    for (const range of CSS.highlights?.get(SPOKEN_HIGHLIGHT) ?? []) {
        const near = [...(range as Range).getClientRects()].some((rect) =>
            x >= rect.left - HEARD_SLOP && x <= rect.right + HEARD_SLOP && y >= rect.top - HEARD_SLOP
            && y <= rect.bottom + HEARD_SLOP
        );
        if (near) {
            return range as Range;
        }
    }
    return null;
}

interface BlocksProps {
    /** The book the blocks are of, for their pictures. */
    bookId: string;
    blocks: BookBlock[];
    /** The blocks laid out, from the first to the one after the last. */
    start: number;
    end: number;
    /** Told the paragraph a link in the book leads to, by its place among them, when it is followed. */
    onFollow: (to: number) => void;
    /** The sections by the paragraph that is their heading, which has a button to read the section aloud. */
    headings: Map<number, BookSection>;
    onPlay: (section: BookSection) => void;
}

/** The paragraphs of a book, which are many, and are not gone through again when a page is turned. */
const Blocks = memo(function Blocks({ bookId, blocks, start, end, onFollow, headings, onPlay }: BlocksProps) {
    return (
        <>
            {blocks.slice(start, end).map((block, at) => {
                // each says its place in the book, as only some parts of it are laid out
                const place = { [BLOCK_ATTRIBUTE]: start + at };
                const heading = headings.get(start + at);
                return block.image
                    ? (
                        // a paragraph of its own, as each block is one
                        <p key={at} className="book-picture" {...place}>
                            <BookPicture bookId={bookId} block={block} />
                        </p>
                    )
                    : (
                        <p
                            key={at}
                            {...place}
                            style={block.size === 1 ? undefined : { fontSize: `${shownSize(block)}em` }}
                        >
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
                            {heading && (
                                // with no text of its own, so that the places in the text of the paragraph are as
                                // they were
                                <button
                                    className="heading-play"
                                    onClick={(event) => {
                                        event.stopPropagation();
                                        onPlay(heading);
                                    }}
                                    title={t("Read it aloud")}
                                    aria-label={t("Read {name} aloud", { name: heading.title })}
                                >
                                    <Icon name="play" />
                                </button>
                            )}
                        </p>
                    );
            })}
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
            // An empty picture until it comes, of the size it will be: one with
            // nothing to show takes no room, and the pages would move as it came.
            src={source ?? BLANK_PICTURE}
            alt={block.alt ?? ""}
            width={block.width}
            height={block.height}
            style={block.width && block.height ? { aspectRatio: `${block.width} / ${block.height}` } : undefined}
            decoding="async"
            draggable={false}
        />
    );
}

/** A picture of a single pixel that cannot be seen. */
const BLANK_PICTURE = "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7";

/** Whether what has the focus is typed in, which brings up the keyboard on a phone. */
function typing(): boolean {
    const focused = document.activeElement;
    return focused instanceof HTMLElement
        && (focused.matches("input:not([type=checkbox], [type=radio], [type=range], [type=button]), textarea")
            || focused.isContentEditable);
}
