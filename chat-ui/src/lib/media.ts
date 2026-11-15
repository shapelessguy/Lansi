// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { useEffect, useRef } from "react";

/** What the buttons of the system for what is played, as those of headphones, ask the player to do. */
export type MediaAction = "play" | "pause" | "next" | "previous" | "stop";

/**
 * What the Android app does for what the page reads aloud: it shows it as
 * what the phone plays, with its buttons, and keeps the page fetching and
 * playing it while the screen is off.
 */
interface NativeMedia {
    state(playing: boolean, title: string): void;
    end(): void;
}

declare global {
    interface Window {
        lansiMedia?: NativeMedia;
        /** What the Android app calls with the buttons of the phone and of headphones. */
        lansiMediaAction?: (action: MediaAction) => void;
    }
}

const ACTIONS: [MediaAction, MediaSessionAction][] = [
    ["play", "play"],
    ["pause", "pause"],
    ["next", "nexttrack"],
    ["previous", "previoustrack"],
    ["stop", "stop"],
];

/**
 * Has the buttons of the system for what is played, on the keyboard, on
 * headphones or on the screen of a locked phone, work the player that is
 * on show, told whether it plays and what it plays as `title`; `act` is
 * told what they ask.
 */
export function useMediaControls(playing: boolean, title: string, act: (action: MediaAction) => void) {
    const latest = useRef(act);
    latest.current = act;
    useEffect(() => {
        const asked = (action: MediaAction) => latest.current(action);
        window.lansiMediaAction = asked;
        const session = "mediaSession" in navigator ? navigator.mediaSession : null;
        for (const [action, name] of ACTIONS) {
            try {
                session?.setActionHandler(name, () => asked(action));
            } catch {
                // a browser that does not know of this button
            }
        }
        return () => {
            if (window.lansiMediaAction === asked) {
                delete window.lansiMediaAction;
            }
            window.lansiMedia?.end();
            for (const [, name] of ACTIONS) {
                try {
                    session?.setActionHandler(name, null);
                } catch {
                    // as above
                }
            }
            if (session) {
                session.metadata = null;
                session.playbackState = "none";
            }
        };
    }, []);
    useEffect(() => {
        window.lansiMedia?.state(playing, title);
        if ("mediaSession" in navigator && typeof MediaMetadata !== "undefined") {
            navigator.mediaSession.metadata = new MediaMetadata({ title, artist: "Lansi" });
            navigator.mediaSession.playbackState = playing ? "playing" : "paused";
        }
    }, [playing, title]);
}
