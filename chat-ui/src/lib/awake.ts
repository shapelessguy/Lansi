// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { useEffect } from "react";

/** What the Android app lets the page do with the screen of the phone. */
interface NativeScreen {
    keepOn(on: boolean): void;
}

declare global {
    interface Window {
        lansiScreen?: NativeScreen;
    }
}

/**
 * Keeps the screen from going dark while `on`, as while a book is read: in
 * the Android app the app keeps it on, whose WebView has no lock of its
 * own; elsewhere the browser does, with the lock it lets go of whenever the
 * page is out of sight and that is taken again once it is back.
 */
export function useAwake(on: boolean) {
    useEffect(() => {
        if (!on) {
            return;
        }
        const native = window.lansiScreen;
        if (native) {
            native.keepOn(true);
            return () => native.keepOn(false);
        }
        if (!("wakeLock" in navigator)) {
            return;
        }
        let lock: WakeLockSentinel | null = null;
        let done = false;
        const take = () => {
            if (done || document.visibilityState !== "visible" || (lock && !lock.released)) {
                return;
            }
            navigator.wakeLock
                .request("screen")
                .then((taken) => {
                    if (done) {
                        taken.release().catch(() => {});
                    } else {
                        lock = taken;
                    }
                })
                // refused, as on a battery saver: the screen goes dark as it would
                .catch(() => {});
        };
        take();
        document.addEventListener("visibilitychange", take);
        return () => {
            done = true;
            document.removeEventListener("visibilitychange", take);
            lock?.release().catch(() => {});
        };
    }, [on]);
}
