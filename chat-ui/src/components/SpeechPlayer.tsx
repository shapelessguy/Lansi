// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { useEffect, useRef, useState } from "react";

import {
    audioPlayer,
    fetchSentenceAudio,
    listenAt,
    loadSpeed,
    rangeOf,
    type Reading,
    saveSpeed,
    type SpeechSource,
    SPEEDS,
    type Spot,
    spotBeside,
    startReading,
    stepped,
    stopReading,
    type Voice,
    wanted,
} from "../lib/speaking";
import type { BackgroundTask } from "../lib/tasks";

interface Props {
    /** What is read aloud. Give the component a key of its own for each thing that is. */
    source: SpeechSource;
    voice: Voice;
    /** Told the task the server started to make the audio that was missing. */
    onTask: (task: BackgroundTask) => void;
    onClose: () => void;
}

/** What the sentence that is listened to is marked with in the book, and what tells the reader to show it. */
const HIGHLIGHT = "spoken";
export const SPOKEN_EVENT = "lansi:spoken";

/**
 * Plays the sentences of a book that were selected, or those of a message
 * of a chat, one after another, as
 * their audio arrives: the first is played while the others are still
 * being made. The sentence that is heard is marked in the book.
 */
export function SpeechPlayer({ source, voice, onTask, onClose }: Props) {
    const { base, bookId, beside } = source;
    // Where the player is, if it is shown beside something. Without that it
    // is at the foot of the window, as it also is while the thing is not on show.
    const [spot, setSpot] = useState<Spot | null>(null);
    const shown = useRef<HTMLDivElement>(null);
    useEffect(() => {
        if (beside === null) {
            return;
        }
        function place() {
            // something that is not laid out, as in a chat that is not shown, has no place
            const thing = document.querySelector(beside!);
            const rect = thing?.getClientRects()[0];
            const size = shown.current?.getBoundingClientRect();
            // the player keeps to the pane the thing is in, and off the panels at its sides
            const edge = thing?.closest(".pane")?.getBoundingClientRect().left ?? 0;
            const found = rect && size ? spotBeside(rect, size, edge) : null;
            // nothing is drawn anew while it stays where it is
            setSpot((current) => (JSON.stringify(current) === JSON.stringify(found) ? current : found));
        }
        place();
        // it follows the thing as the page is scrolled and laid out anew
        document.addEventListener("scroll", place, true);
        window.addEventListener("resize", place);
        const timer = setInterval(place, 300);
        return () => {
            document.removeEventListener("scroll", place, true);
            window.removeEventListener("resize", place);
            clearInterval(timer);
        };
    }, [beside]);
    const [reading, setReading] = useState<Reading | null>(null);
    const [error, setError] = useState<string | null>(null);
    // the sentence that is listened to, by its place among those of the reading
    const [index, setIndex] = useState(0);
    // the audio of each sentence that has arrived, or why it has not, by the place of the sentence
    const [clips, setClips] = useState<Record<number, { url: string } | { failed: string }>>({});
    // whether the listener wants to hear, rather than having paused
    const [playing, setPlaying] = useState(true);
    // whether the browser kept the audio from starting by itself
    const [held, setHeld] = useState(false);
    // how fast the audio is played, which is remembered for the next time
    const [speed, setSpeed] = useState(loadSpeed);
    const asked = useRef(new Set<number>());
    const urls = useRef<string[]>([]);
    const leaving = useRef(new AbortController());
    const readingId = reading?.task?.reading ?? null;
    const sentences = reading?.sentences ?? [];
    const sentence = sentences[index];
    const clip = clips[index];

    useEffect(() => {
        const controller = new AbortController();
        leaving.current = controller;
        let started: string | null = null;
        // A player that is put away at once, as one is while the app is
        // being worked on, asks for nothing.
        const timer = setTimeout(() =>
            startReading(source, voice).then(
                (begun) => {
                    started = begun.task?.reading ?? null;
                    if (controller.signal.aborted) {
                        // it was closed before the server answered
                        if (started) {
                            stopReading(base, started);
                        }
                        return;
                    }
                    setReading(begun);
                    if (begun.task) {
                        onTask(begun.task);
                    }
                },
                (caught: Error) => controller.signal.aborted || setError(caught.message),
            )
        );
        return () => {
            clearTimeout(timer);
            controller.abort();
            if (started) {
                stopReading(base, started);
            }
            urls.current.forEach((url) => URL.revokeObjectURL(url));
            CSS.highlights?.delete(HIGHLIGHT);
        };
        // the selection is read as it was when the player came up
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    // The audio of the sentence that is listened to and of the next few is
    // asked for, and the server is told where the listener is, so that it
    // makes the audio from there on first.
    useEffect(() => {
        if (!reading) {
            return;
        }
        if (readingId) {
            listenAt(base, readingId, index);
        }
        for (const place of wanted(index, reading.sentences.length)) {
            if (asked.current.has(place)) {
                continue;
            }
            asked.current.add(place);
            fetchSentenceAudio(base, reading.sentences[place].id, leaving.current.signal).then(
                (blob) => {
                    const url = URL.createObjectURL(blob);
                    urls.current.push(url);
                    setClips((current) => ({ ...current, [place]: { url } }));
                },
                (caught: Error) =>
                    leaving.current.signal.aborted
                    || setClips((current) => ({ ...current, [place]: { failed: caught.message } })),
            );
        }
    }, [base, reading, readingId, index]);

    // the sentence that is heard is marked in the book, and the reader told to show it
    useEffect(() => {
        if (!sentence || bookId === null) {
            return;
        }
        const block = document.querySelector(".reader-columns")?.children[sentence.block];
        const range = block ? rangeOf(block, sentence) : null;
        if (range) {
            CSS.highlights?.set(HIGHLIGHT, new Highlight(range));
            window.dispatchEvent(new CustomEvent(SPOKEN_EVENT, { detail: { bookId, range } }));
        } else {
            CSS.highlights?.delete(HIGHLIGHT);
        }
    }, [bookId, sentence]);

    const last = index >= sentences.length - 1;
    const clipUrl = clip && "url" in clip ? clip.url : null;
    // what the player does when a sentence is over, as things are now
    const whenOver = useRef(() => undefined as void);
    whenOver.current = () => {
        if (last) {
            setPlaying(false);
        } else {
            go(1);
        }
    };
    const wantsToHear = useRef(playing);
    wantsToHear.current = playing;
    const latestSpeed = useRef(speed);
    latestSpeed.current = speed;

    // The audio of the sentence that is listened to is put into the player
    // when it arrives, and played. If the browser does not let it play,
    // the player shows that it waits to be started.
    useEffect(() => {
        if (clipUrl === null) {
            return;
        }
        const audio = audioPlayer();
        const onEnded = () => whenOver.current();
        audio.addEventListener("ended", onEnded);
        audio.src = clipUrl;
        // a new recording would otherwise be played at the usual pace again
        audio.defaultPlaybackRate = latestSpeed.current;
        audio.playbackRate = latestSpeed.current;
        if (wantsToHear.current) {
            audio.play().then(() => setHeld(false), (refused: Error) => {
                if (refused.name === "NotAllowedError") {
                    setPlaying(false);
                    setHeld(true);
                }
            });
        }
        return () => {
            audio.removeEventListener("ended", onEnded);
            audio.pause();
        };
    }, [clipUrl, index]);

    useEffect(() => {
        audioPlayer().defaultPlaybackRate = speed;
        audioPlayer().playbackRate = speed;
    }, [speed]);
    const failed = clip && "failed" in clip ? clip.failed : null;

    // a sentence that could not be read is passed over
    useEffect(() => {
        if (failed !== null && !last) {
            const timer = setTimeout(() => setIndex((current) => stepped(current, 1, sentences.length)), 1200);
            return () => clearTimeout(timer);
        }
    }, [failed, last, sentences.length]);

    function go(step: number) {
        setIndex((current) => stepped(current, step, sentences.length));
        setPlaying(true);
    }

    function toggle() {
        if (playing) {
            audioPlayer().pause();
        } else {
            audioPlayer().play().catch(() => undefined);
        }
        setHeld(false);
        setPlaying(!playing);
    }

    const status = error
        ?? (!reading
            ? "Getting the sentences…"
            : failed !== null
            ? `Could not be read: ${failed}`
            : !clip
            ? "Making the audio…"
            : held
            ? "The browser did not let the audio start by itself. Press play."
            : null);

    // Beside a reply there is the reply to read, so the sentence is not
    // said again, but what is the matter is.
    const besideIt = beside !== null;
    const wrong = error !== null || failed !== null || held;
    return (
        <div
            ref={shown}
            className={besideIt ? "speech-player beside" : "speech-player"}
            // until it is known where it goes, it is laid out where it is not seen, to be measured
            style={besideIt
                ? (spot ? { left: spot.left, top: spot.top } : { left: 0, top: 0, visibility: "hidden" })
                : undefined}
            role="region"
            aria-label="Reading aloud"
        >
            <div className="speech-controls">
                <button
                    className="icon-button"
                    onClick={() => go(-1)}
                    disabled={index === 0}
                    title="Previous sentence"
                    aria-label="Previous sentence"
                >
                    ⏮
                </button>
                <button
                    className="icon-button"
                    onClick={toggle}
                    disabled={!clip || failed !== null}
                    title={playing ? "Pause" : "Play"}
                    aria-label={playing ? "Pause" : "Play"}
                >
                    {reading && !clip && !error ? <span className="spinner" aria-hidden="true" /> : playing ? "⏸" : "▶"}
                </button>
                <button
                    className="icon-button"
                    onClick={() => go(1)}
                    disabled={!reading || last}
                    title="Next sentence"
                    aria-label="Next sentence"
                >
                    ⏭
                </button>
                <button className="icon-button" onClick={onClose} title="Stop" aria-label="Stop">⏹</button>
                <select
                    className="speech-speed"
                    value={speed}
                    onChange={(event) => {
                        const chosen = Number(event.target.value);
                        setSpeed(chosen);
                        saveSpeed(chosen);
                    }}
                    title="Speed"
                    aria-label="Speed"
                >
                    {SPEEDS.map((each) => <option key={each} value={each}>{each}×</option>)}
                </select>
                {reading && <span className={wrong ? "count error" : "count"}>{index + 1} / {sentences.length}</span>}
            </div>
            {(!besideIt || wrong) && (
                <p className={wrong ? "speech-status error" : "speech-status"}>
                    {status ?? sentence?.text}
                </p>
            )}
        </div>
    );
}
