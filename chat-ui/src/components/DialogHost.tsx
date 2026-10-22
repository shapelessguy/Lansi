// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { useEffect, useState } from "react";

import { answer, type Dialog, onDialog } from "../lib/dialogs";

/**
 * Where the dialogs the app asks or tells something in are shown, over
 * the page, one at a time. Escape and a click outside it decline; the
 * button that agrees has the focus, so Enter agrees.
 */
export function DialogHost() {
    const [shown, setShown] = useState<Dialog | null>(null);
    // tells each dialog from the one before, for the one after to be given the focus
    const [count, setCount] = useState(0);
    useEffect(
        () =>
            onDialog((dialog) => {
                setShown(dialog);
                setCount((current) => current + 1);
            }),
        [],
    );
    useEffect(() => {
        if (!shown) {
            return;
        }
        const onKeyDown = (event: KeyboardEvent) => {
            if (event.key === "Escape") {
                event.stopPropagation();
                answer(false);
            }
        };
        // before anything else on the page that closes on Escape
        document.addEventListener("keydown", onKeyDown, true);
        return () => document.removeEventListener("keydown", onKeyDown, true);
    }, [shown]);

    if (!shown) {
        return null;
    }
    return (
        <div
            className="dialog-backdrop"
            onPointerDown={(event) => event.target === event.currentTarget && answer(false)}
        >
            <div
                key={count}
                className="dialog"
                role={shown.cancel === null ? "dialog" : "alertdialog"}
                aria-modal="true"
                aria-label={shown.message}
            >
                <p className="dialog-message">{shown.message}</p>
                {shown.detail && <p className="dialog-detail">{shown.detail}</p>}
                <div className="dialog-buttons">
                    {shown.cancel !== null && <button onClick={() => answer(false)}>{shown.cancel}</button>}
                    <button className={shown.danger ? "danger" : "primary"} autoFocus onClick={() => answer(true)}>
                        {shown.confirm}
                    </button>
                </div>
            </div>
        </div>
    );
}
