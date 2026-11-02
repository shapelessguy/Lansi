// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import {
    type CSSProperties,
    type PointerEvent as ReactPointerEvent,
    type ReactNode,
    useEffect,
    useLayoutEffect,
    useRef,
    useState,
} from "react";

import { ask } from "../lib/dialogs";
import { type Message, plural, t } from "../lib/i18n";
import {
    drawStroke,
    keptPoint,
    loadPen,
    MAX_SIZE,
    MIN_SIZE,
    MOUSE_PRESSURE,
    type Pen,
    type PenChoice,
    PENS,
    savePen,
    type Stroke,
    touches,
} from "../lib/ink";
import { addPage, deletePage, fetchText, type HandwrittenPage, readPage, saveInk, type Text } from "../lib/texts";
import { Icon, type IconName } from "./Icon";

interface Props {
    textId: string;
    pages: HandwrittenPage[];
    /** Whether the text was corrected, after which it is only shown. */
    locked: boolean;
    visionKey: string;
    /** Told the text as the server has it after a page was added, removed or read. */
    onText: (text: Text) => void;
    onError: (message: string) => void;
}

/** How often the pages are taken again from the server, as another device may write on them, in milliseconds. */
const SYNC_EVERY_MS = 5000;
/** How long nothing must have been written here before the pages are taken again, in milliseconds. */
const IDLE_MS = 10_000;
/** How long after the last stroke the ink of a page is kept, in milliseconds. */
const SAVE_AFTER_MS = 3000;
/** How far apart the lines of a page are, in its units. */
const LINE_SPACING = 70;
/**
 * The steps of the slider of the size, finer among the thin sizes, which
 * are the ones written with, than among the thick.
 */
const SIZE_STEPS = 60;

function sizeOf(step: number): number {
    return Math.round(MIN_SIZE + (MAX_SIZE - MIN_SIZE) * (step / SIZE_STEPS) ** 2);
}

function stepOf(size: number): number {
    return Math.round(Math.sqrt((size - MIN_SIZE) / (MAX_SIZE - MIN_SIZE)) * SIZE_STEPS);
}

/** Where this browser keeps whether the pages are shown turned. */
const TURNED_KEY = "chat-ui.turned-pages";
/** How far a mouse moves, in pixels of the screen, before the next point of a stroke is kept. */
const MOUSE_STEP = 3;
/** How near a stroke the eraser takes it, in units of the page. */
const ERASER_REACH = 10;

const PEN_NAMES: Record<Pen, Message> = {
    pen: "Pen",
    fountain: "Fountain pen",
    pencil: "Pencil",
    highlighter: "Highlighter",
};

const SWATCHES = ["#1a1a1a", "#1f4fbf", "#c62828", "#2e7d32", "#f9a825"];

type Tool = "write" | "erase";

/**
 * The pages of a text written by hand, each written on with a pen, a finger
 * or the mouse, with the pen, its colour and its size chosen above them, or
 * an eraser, which takes away each stroke it rubs. The ink of a page is kept
 * on the server as it is written. Once a stylus has written, a finger
 * scrolls instead, so that the hand resting on the page leaves no mark.
 *
 * The pages are read on demand, with the key of Google Cloud Vision, and the
 * text then says what they were read to say; the box of each word read can
 * be shown on its page.
 */
export function HandwrittenPages({ textId, pages, locked, visionKey, onText, onError }: Props) {
    const [choice, setChoice] = useState<PenChoice>(loadPen);
    const [tool, setTool] = useState<Tool>("write");
    const [showWords, setShowWords] = useState(false);
    const [reading, setReading] = useState(false);
    // the page open on the whole screen, and whether its tools are shown
    const [openId, setOpenId] = useState<string | null>(null);
    const [toolsOpen, setToolsOpen] = useState(false);
    // whether the pages are shown turned, their long side across, as a wide screen is best written on
    const [turned, setTurned] = useState(() => {
        try {
            return localStorage.getItem(TURNED_KEY) === "true";
        } catch {
            return false;
        }
    });

    useEffect(() => {
        try {
            localStorage.setItem(TURNED_KEY, String(turned));
        } catch {
            // the choice then lasts as long as the page
        }
    }, [turned]);
    // the ink of each page as it is written here, which the server has once it is kept
    const [inks, setInks] = useState<Record<string, Stroke[]>>({});
    // the pages written on since they were read here
    const [changed, setChanged] = useState<Set<string>>(new Set());
    // what each change undoes, the last last
    const undo = useRef<{ pageId: string; before: Stroke[] }[]>([]);
    const [undoable, setUndoable] = useState(0);
    const timers = useRef(new Map<string, number>());
    // how many pages are being kept
    const unsaved = useRef(0);
    const saving = useRef(new Map<string, Promise<void>>());
    const latest = useRef<Record<string, Stroke[]>>({});

    const inkOf = (page: HandwrittenPage) => inks[page.id] ?? page.ink;

    useEffect(() => savePen(choice), [choice]);

    // and when the app is left, as a phone may stop it without closing it
    useEffect(() => {
        const leaving = () => {
            if (document.visibilityState === "hidden") {
                [...timers.current.keys()].forEach((pageId) => void keep(pageId));
            }
        };
        document.addEventListener("visibilitychange", leaving);
        return () => document.removeEventListener("visibilitychange", leaving);
    });

    // what is written and not kept yet is kept when the text is closed
    useEffect(() => () => {
        for (const [pageId, timer] of timers.current) {
            window.clearTimeout(timer);
            void saveInk(textId, pageId, latest.current[pageId]).catch(() => undefined);
        }
    }, [textId]);

    function keep(pageId: string) {
        window.clearTimeout(timers.current.get(pageId));
        timers.current.delete(pageId);
        unsaved.current += 1;
        const saved = saveInk(textId, pageId, latest.current[pageId])
            .catch((failed: Error) => onError(failed.message))
            .finally(() => (unsaved.current -= 1));
        saving.current.set(pageId, saved);
        return saved;
    }

    /**
     * Takes the pages as the server has them now, as another device may have
     * written on them, once nothing was written here for a while and all
     * that was is kept.
     */
    function sync() {
        const busy = () => timers.current.size || unsaved.current || inkDown || Date.now() - lastInk < IDLE_MS;
        if (busy()) {
            return;
        }
        fetchText(textId).then((text) => {
            if (busy()) {
                return;
            }
            latest.current = {};
            setInks({});
            if (JSON.stringify(text.pages) !== JSON.stringify(shown.current)) {
                onText(text);
            }
        }, () => undefined);
    }

    const shown = useRef(pages);
    shown.current = pages;
    const syncing = useRef(sync);
    syncing.current = sync;

    // as the app is come back to, and every few seconds while it is in view
    useEffect(() => {
        const now = () => document.visibilityState === "visible" && syncing.current();
        const every = window.setInterval(now, SYNC_EVERY_MS);
        window.addEventListener("focus", now);
        document.addEventListener("visibilitychange", now);
        return () => {
            window.clearInterval(every);
            window.removeEventListener("focus", now);
            document.removeEventListener("visibilitychange", now);
        };
    }, [textId]);

    // and as a page is opened
    useEffect(() => {
        if (openId) {
            syncing.current();
        }
    }, [openId]);

    function write(pageId: string, before: Stroke[], after: Stroke[]) {
        undo.current.push({ pageId, before });
        setUndoable(undo.current.length);
        put(pageId, after);
    }

    function put(pageId: string, ink: Stroke[]) {
        latest.current[pageId] = ink;
        setInks((current) => ({ ...current, [pageId]: ink }));
        setChanged((current) => new Set(current).add(pageId));
        later(pageId);
    }

    /**
     * Keeps the ink of a page once the pen has rested a while, and then when
     * the browser has nothing else to do, so that writing it out never holds
     * up a stroke being started.
     */
    function later(pageId: string) {
        window.clearTimeout(timers.current.get(pageId));
        timers.current.set(
            pageId,
            window.setTimeout(() => {
                const idle = window.requestIdleCallback ?? ((then: () => void) => window.setTimeout(then, 0));
                idle(() => {
                    if (!timers.current.has(pageId)) {
                        return;
                    }
                    if (inkDown || Date.now() - lastInk < SAVE_AFTER_MS) {
                        later(pageId);
                    } else {
                        void keep(pageId);
                    }
                }, { timeout: 1000 });
            }, SAVE_AFTER_MS),
        );
    }

    function undoLast() {
        const last = undo.current.pop();
        setUndoable(undo.current.length);
        if (last && pages.some((page) => page.id === last.pageId)) {
            put(last.pageId, last.before);
        }
    }

    function needsReading(page: HandwrittenPage) {
        return inkOf(page).length > 0
            && (page.words === null || changed.has(page.id) || page.inkedAt > (page.readAt ?? 0));
    }

    async function readAll() {
        setReading(true);
        try {
            for (const page of pages.filter(needsReading)) {
                if (timers.current.has(page.id)) {
                    await keep(page.id);
                }
                await saving.current.get(page.id);
                const text = await readPage(textId, page.id, visionKey);
                setChanged((current) => {
                    const left = new Set(current);
                    left.delete(page.id);
                    return left;
                });
                onText(text);
            }
            setShowWords(true);
        } catch (failed) {
            onError((failed as Error).message);
        } finally {
            setReading(false);
        }
    }

    function add(position: number) {
        addPage(textId, position).then(onText, (failed: Error) => onError(failed.message));
    }

    function remove(page: HandwrittenPage) {
        void ask(t("Remove this page?"), { confirm: t("Remove") }).then((agreed) => {
            if (!agreed) {
                return;
            }
            window.clearTimeout(timers.current.get(page.id));
            timers.current.delete(page.id);
            deletePage(textId, page.id).then(onText, (failed: Error) => onError(failed.message));
        });
    }

    const unread = pages.filter(needsReading).length;
    const at = pages.findIndex((page) => page.id === openId);
    const opened = at >= 0 ? pages[at] : null;

    const tools = (
        <div className="ink-toolbar" role="toolbar" aria-label={t("Pen")}>
            {!locked && (
                <>
                    <div className="ink-group">
                        {PENS.map((pen) => (
                            <ToolButton
                                key={pen}
                                icon={pen}
                                label={t(PEN_NAMES[pen])}
                                pressed={tool === "write" && choice.pen === pen}
                                onClick={() => {
                                    setTool("write");
                                    setChoice({ ...choice, pen });
                                }}
                            />
                        ))}
                        <ToolButton
                            icon="eraser"
                            label={t("Eraser")}
                            pressed={tool === "erase"}
                            onClick={() => setTool("erase")}
                        />
                    </div>
                    <div className="ink-group">
                        {SWATCHES.map((color) => (
                            <button
                                key={color}
                                type="button"
                                className="ink-swatch"
                                style={{ background: color }}
                                title={color}
                                aria-label={color}
                                aria-pressed={choice.color === color}
                                onClick={() => {
                                    setTool("write");
                                    setChoice({ ...choice, color });
                                }}
                            />
                        ))}
                        <label
                            className={SWATCHES.includes(choice.color)
                                ? "ink-swatch ink-custom"
                                : "ink-swatch ink-custom chosen"}
                            style={SWATCHES.includes(choice.color) ? undefined : { background: choice.color }}
                            title={t("Colour")}
                        >
                            <input
                                type="color"
                                aria-label={t("Colour")}
                                value={choice.color}
                                onChange={(event) => {
                                    setTool("write");
                                    setChoice({ ...choice, color: event.target.value });
                                }}
                            />
                        </label>
                    </div>
                    <div className="ink-group ink-size">
                        <span className="ink-size-preview" aria-hidden="true">
                            <span
                                className="ink-size-dot"
                                style={{
                                    width: Math.min(choice.size, 22),
                                    height: Math.min(choice.size, 22),
                                    background: choice.color,
                                }}
                            />
                        </span>
                        <input
                            type="range"
                            min={0}
                            max={SIZE_STEPS}
                            step={1}
                            title={t("Size")}
                            aria-label={t("Size")}
                            aria-valuetext={`${choice.size} px`}
                            value={stepOf(choice.size)}
                            onChange={(event) => setChoice({ ...choice, size: sizeOf(Number(event.target.value)) })}
                        />
                        <span className="ink-size-value">{choice.size} px</span>
                    </div>
                    <div className="ink-group">
                        <ToolButton icon="undo" label={t("Undo")} disabled={undoable === 0} onClick={undoLast} />
                    </div>
                </>
            )}
            <div className="ink-group">
                {!locked && (
                    <button
                        type="button"
                        className="icon-button ink-read"
                        disabled={reading || unread === 0 || !visionKey}
                        title={!visionKey
                            ? t("Set your Google Cloud Vision key in Settings, under Models, to read the pages.")
                            : unread
                            ? plural(unread, "Read {count} page", "Read {count} pages")
                            : t("Every page is read")}
                        aria-label={t("Read the pages")}
                        onClick={() => void readAll()}
                    >
                        {reading ? <span className="spinner" aria-hidden="true" /> : <Icon name="read" />}
                        {unread > 0 && !reading && <span className="ink-badge">{unread}</span>}
                    </button>
                )}
                <ToolButton
                    icon="word-boxes"
                    label={t("Show the words read")}
                    pressed={showWords}
                    onClick={() => setShowWords(!showWords)}
                />
            </div>
        </div>
    );

    return (
        <div className="handwritten">
            {/* not there behind an open page, which would draw each stroke twice */}
            {!opened && (
                <div className="ink-pages">
                    {pages.map((page, number) => (
                        <div key={page.id} className="ink-slot">
                            {!locked && <PageGap onAdd={() => add(number)} />}
                            <figure className="ink-page ink-thumb">
                                <button
                                    type="button"
                                    className="ink-open"
                                    title={t("Page {number}", { number: number + 1 })}
                                    aria-label={t("Page {number}", { number: number + 1 })}
                                    onClick={() => setOpenId(page.id)}
                                >
                                    <InkPage
                                        page={page}
                                        ink={inkOf(page)}
                                        choice={choice}
                                        tool={tool}
                                        locked
                                        turned={turned}
                                        showWords={false}
                                        onWrite={() => undefined}
                                    />
                                </button>
                                {!locked && pages.length > 1 && (
                                    <button
                                        type="button"
                                        className="icon-button ink-page-remove"
                                        title={t("Remove this page")}
                                        aria-label={t("Remove this page")}
                                        onClick={() => remove(page)}
                                    >
                                        <Icon name="trash" />
                                    </button>
                                )}
                            </figure>
                        </div>
                    ))}
                    {!locked && (
                        <div className="ink-slot ink-end-slot">
                            <PageGap onAdd={() => add(pages.length)} />
                        </div>
                    )}
                </div>
            )}
            {opened && (
                <FullPage onClose={() => setOpenId(null)}>
                    <div className="ink-full-bar">
                        <div className="ink-group">
                            <ToolButton icon="close" label={t("Close")} onClick={() => setOpenId(null)} />
                            <ToolButton
                                icon="turn"
                                label={t("Turn the pages")}
                                pressed={turned}
                                onClick={() => setTurned(!turned)}
                            />
                            {pages.length > 1 && (
                                <>
                                    <ToolButton
                                        icon="previous"
                                        label={t("Previous page")}
                                        disabled={at === 0}
                                        onClick={() => setOpenId(pages[at - 1].id)}
                                    />
                                    <span className="ink-count">{at + 1}/{pages.length}</span>
                                    <ToolButton
                                        icon="next"
                                        label={t("Next page")}
                                        disabled={at === pages.length - 1}
                                        onClick={() => setOpenId(pages[at + 1].id)}
                                    />
                                </>
                            )}
                        </div>
                        <div className="ink-controls">
                            {toolsOpen && tools}
                            <button
                                type="button"
                                className="icon-button ink-tools-toggle"
                                title={t("Pen")}
                                aria-label={t("Pen")}
                                aria-expanded={toolsOpen}
                                onClick={() => setToolsOpen(!toolsOpen)}
                            >
                                <Icon name={tool === "erase" ? "eraser" : choice.pen} />
                                {tool === "write" && (
                                    <span className="ink-tools-color" style={{ background: choice.color }} />
                                )}
                                {unread > 0 && !locked && <span className="ink-badge">{unread}</span>}
                            </button>
                        </div>
                    </div>
                    <figure
                        className="ink-page ink-full-page"
                        style={{
                            "--ink-aspect": turned ? opened.height / opened.width : opened.width / opened.height,
                        } as CSSProperties}
                    >
                        <InkPage
                            key={opened.id}
                            page={opened}
                            ink={inkOf(opened)}
                            choice={choice}
                            tool={tool}
                            locked={locked}
                            turned={turned}
                            showWords={showWords && !needsReading(opened)}
                            onWrite={(before, after) => write(opened.id, before, after)}
                        />
                    </figure>
                </FullPage>
            )}
        </div>
    );
}

/**
 * A page open on the whole screen, as the browser can show it, and over
 * everything else where it cannot; closed with Escape, or as the browser
 * leaves its whole screen.
 */
function FullPage({ onClose, children }: { onClose: () => void; children: ReactNode }) {
    const shown = useRef<HTMLDivElement>(null);
    const close = useRef(onClose);
    close.current = onClose;

    useEffect(() => {
        const element = shown.current;
        let full = false;
        const left = () => {
            if (full && document.fullscreenElement === null) {
                close.current();
            }
            full = document.fullscreenElement !== null;
        };
        const escape = (event: KeyboardEvent) => event.key === "Escape" && close.current();
        document.addEventListener("fullscreenchange", left);
        window.addEventListener("keydown", escape);
        if (document.fullscreenEnabled && element) {
            element.requestFullscreen().catch(() => undefined);
        }
        return () => {
            document.removeEventListener("fullscreenchange", left);
            window.removeEventListener("keydown", escape);
            if (document.fullscreenElement) {
                document.exitFullscreen().catch(() => undefined);
            }
        };
    }, []);

    return (
        <div ref={shown} className="ink-full" role="dialog" aria-modal="true">
            {children}
        </div>
    );
}

/** The room between two pages, or before or after them all, with a button that adds a page there. */
function PageGap({ onAdd }: { onAdd: () => void }) {
    return (
        <div className="ink-gap">
            <button
                type="button"
                className="icon-button"
                title={t("Add a page here")}
                aria-label={t("Add a page here")}
                onClick={onAdd}
            >
                <Icon name="add" />
            </button>
        </div>
    );
}

/** A button that shows only its icon, and says what it does when the pointer rests on it. */
function ToolButton(
    { icon, label, pressed, disabled, onClick }: {
        icon: IconName;
        label: string;
        pressed?: boolean;
        disabled?: boolean;
        onClick: () => void;
    },
) {
    return (
        <button
            type="button"
            className="icon-button"
            title={label}
            aria-label={label}
            aria-pressed={pressed}
            disabled={disabled}
            onClick={onClick}
        >
            <Icon name={icon} />
        </button>
    );
}

interface PageProps {
    page: HandwrittenPage;
    ink: Stroke[];
    choice: PenChoice;
    tool: Tool;
    locked: boolean;
    /** Whether it is shown turned a quarter, its long side across, its top on the left. */
    turned: boolean;
    showWords: boolean;
    /** Told what the ink of the page was before a stroke or a rubbing of the eraser, and what it is after. */
    onWrite: (before: Stroke[], after: Stroke[]) => void;
}

// whether a stylus has written, after which a finger scrolls rather than writes
let stylusSeen = false;
// whether a stroke is being written, while which the pages are not taken again from the server
let inkDown = false;
// when the last stroke here was started or ended
let lastInk = 0;

/** A page to be written on: its ink drawn on one canvas, and the stroke being written on another above it. */
function InkPage({ page, ink, choice, tool, locked, turned, showWords, onWrite }: PageProps) {
    // how wide and high it is shown, in units of the page
    const wide = turned ? page.height : page.width;
    const high = turned ? page.width : page.height;
    const frame = useRef<HTMLDivElement>(null);
    const base = useRef<HTMLCanvasElement>(null);
    const live = useRef<HTMLCanvasElement>(null);
    const [shownWidth, setShownWidth] = useState(0);
    // the stroke being written, or what the eraser has left while it rubs
    const writing = useRef<{ stroke: Stroke | null; before: Stroke[]; left: Stroke[]; finger: number | null } | null>(
        null,
    );

    // how wide the page is shown, in pixels of the screen, exactly where the browser says
    useEffect(() => {
        const observer = new ResizeObserver(([entry]) => {
            const exact = entry.devicePixelContentBoxSize?.[0]?.inlineSize;
            setShownWidth(exact ?? Math.round(entry.contentRect.width * (window.devicePixelRatio || 1)));
        });
        if (base.current) {
            try {
                observer.observe(base.current, { box: "device-pixel-content-box" });
            } catch {
                // a browser that cannot say it is told the width in pixels of the page
                observer.observe(base.current);
            }
        }
        return () => observer.disconnect();
    }, []);

    /** Makes a canvas as sharp as the screen, its units those of the page. */
    function prepare(canvas: HTMLCanvasElement | null) {
        if (!canvas || !shownWidth) {
            return null;
        }
        // as many pixels as the screen shows it with, so that it is never scaled, which blurs it
        const scale = shownWidth / wide;
        const width = shownWidth;
        const height = Math.round(high * scale);
        if (canvas.width !== width || canvas.height !== height) {
            canvas.width = width;
            canvas.height = height;
        }
        const context = canvas.getContext("2d");
        if (turned) {
            // the page's x runs up the screen, and its y across it
            context?.setTransform(0, -scale, scale, 0, 0, page.width * scale);
        } else {
            context?.setTransform(scale, 0, 0, scale, 0, 0);
        }
        context?.clearRect(0, 0, page.width, page.height);
        return context;
    }

    function drawAll(strokes: Stroke[]) {
        const context = prepare(base.current);
        strokes.forEach((stroke) => context && drawStroke(context, stroke));
        // what was being written is now on the page, so it is cleared in the same frame
        if (!writing.current) {
            prepare(live.current);
        }
    }

    // what the page was last drawn with, to which a stroke written is only added
    const drawn = useRef<{ ink: Stroke[]; shownWidth: number; turned: boolean } | null>(null);

    // before the page is painted, so that a stroke just written is not missing from it for a moment
    useLayoutEffect(() => {
        const last = drawn.current;
        const context = base.current?.getContext("2d");
        drawn.current = { ink, shownWidth, turned };
        if (
            context && last && last.shownWidth === shownWidth && last.turned === turned
            && ink.length > last.ink.length && last.ink.every((stroke, at) => ink[at] === stroke)
        ) {
            ink.slice(last.ink.length).forEach((stroke) => drawStroke(context, stroke));
            if (!writing.current) {
                prepare(live.current);
            }
            return;
        }
        drawAll(ink);
    }, [ink, shownWidth, turned]);

    function pointOf(event: PointerEvent | ReactPointerEvent): [number, number, number] {
        const box = (live.current as HTMLCanvasElement).getBoundingClientRect();
        const pressure = event.pointerType === "pen" && event.pressure > 0 ? event.pressure : MOUSE_PRESSURE;
        const x = ((event.clientX - box.left) / box.width) * wide;
        const y = ((event.clientY - box.top) / box.height) * high;
        return turned ? keptPoint(page.width - y, x, pressure) : keptPoint(x, y, pressure);
    }

    function down(event: ReactPointerEvent<HTMLCanvasElement>) {
        if (locked || (event.pointerType === "mouse" && event.button !== 0)) {
            return;
        }
        if (event.pointerType === "pen") {
            stylusSeen = true;
        }
        event.preventDefault();
        event.currentTarget.setPointerCapture(event.pointerId);
        if (event.pointerType === "touch" && stylusSeen) {
            writing.current = { stroke: null, before: ink, left: ink, finger: event.clientY };
            return;
        }
        // the button on the side of some styluses rubs out too
        const erasing = tool === "erase" || (event.buttons & 32) !== 0;
        inkDown = true;
        lastInk = Date.now();
        writing.current = {
            stroke: erasing ? null : { ...choice, points: [pointOf(event)] },
            before: ink,
            left: ink,
            finger: null,
        };
        if (erasing) {
            rub(event);
        } else {
            drawLive();
        }
    }

    function rub(event: PointerEvent | ReactPointerEvent) {
        const now = writing.current;
        if (!now) {
            return;
        }
        const [x, y] = pointOf(event);
        const left = now.left.filter((stroke) => !touches(stroke, x, y, ERASER_REACH));
        if (left.length !== now.left.length) {
            now.left = left;
            drawAll(left);
        }
    }

    /** Draws the stroke being written. */
    function drawLive() {
        const context = prepare(live.current);
        const stroke = writing.current?.stroke;
        if (context && stroke) {
            drawStroke(context, stroke, false);
        }
    }

    /** Whether a point is far enough from the last of the stroke to be kept: a mouse, which moves by whole pixels, only every few of them, or its curves come out in steps. */
    function farEnough(stroke: Stroke, point: [number, number, number], pointerType: string) {
        if (pointerType !== "mouse") {
            return true;
        }
        const last = stroke.points[stroke.points.length - 1];
        const box = (live.current as HTMLCanvasElement).getBoundingClientRect();
        return Math.hypot(point[0] - last[0], point[1] - last[1]) >= MOUSE_STEP * (wide / box.width);
    }

    function move(event: ReactPointerEvent<HTMLCanvasElement>) {
        const now = writing.current;
        if (!now) {
            return;
        }
        if (now.finger !== null) {
            // a finger scrolls what the pages are in
            frame.current?.closest(".ink-full")?.scrollBy(0, now.finger - event.clientY);
            now.finger = event.clientY;
            return;
        }
        const moves = event.nativeEvent.getCoalescedEvents?.() ?? [event.nativeEvent];
        if (!now.stroke) {
            moves.forEach(rub);
            return;
        }
        for (const each of moves.length ? moves : [event.nativeEvent]) {
            const point = pointOf(each);
            // a stylus being lifted says it no longer presses
            if (event.pointerType === "pen" && each.pressure === 0) {
                continue;
            }
            if (farEnough(now.stroke, point, event.pointerType)) {
                now.stroke.points.push(point);
            }
        }
        drawLive();
    }

    function up(event: ReactPointerEvent<HTMLCanvasElement>) {
        const now = writing.current;
        writing.current = null;
        inkDown = false;
        lastInk = Date.now();
        // where a mouse was lifted, which it may not have moved far enough from the last point to give;
        // a stylus says no pressure as it is lifted, so its last point is the last it pressed
        if (now?.stroke && event.type === "pointerup" && event.pointerType === "mouse") {
            now.stroke.points.push(pointOf(event));
        }
        if (!now || now.finger !== null) {
            return;
        }
        if (!now.stroke) {
            prepare(live.current);
        }
        // a stroke written stays where it was drawn until the page is drawn again with it, which clears it
        if (now.stroke) {
            onWrite(now.before, [...now.before, now.stroke]);
        } else if (now.left !== now.before) {
            onWrite(now.before, now.left);
        }
    }

    return (
        <div
            ref={frame}
            className={turned ? "ink-frame turned" : "ink-frame"}
            style={{
                aspectRatio: `${wide} / ${high}`,
                // the lines of the page turn with it
                backgroundSize: turned
                    ? `${(LINE_SPACING / wide) * 100}% 100%`
                    : `100% ${(LINE_SPACING / high) * 100}%`,
            }}
        >
            <canvas ref={base} aria-hidden="true" />
            <canvas
                ref={live}
                className={tool === "erase" ? "ink-live erasing" : "ink-live"}
                aria-label={t("Page to write on")}
                onPointerDown={down}
                onPointerMove={move}
                onPointerUp={up}
                onPointerCancel={up}
            />
            {showWords && page.words && (
                <svg viewBox={`0 0 ${wide} ${high}`} preserveAspectRatio="none" aria-hidden="true">
                    <g transform={turned ? `matrix(0 -1 1 0 0 ${page.width})` : undefined}>
                        {page.words.map((word, place) => (
                            <polygon
                                key={place}
                                points={word.box.map(([x, y]) => `${x},${y}`).join(" ")}
                            >
                                <title>{word.text}</title>
                            </polygon>
                        ))}
                    </g>
                </svg>
            )}
        </div>
    );
}
