// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { type ReactNode, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { t } from "../lib/i18n";

/** How far the popup keeps from the edges of the window, and from the question mark, in pixels. */
const MARGIN = 8;

/**
 * A question mark beside the name of a setting, which shows what the
 * setting is about, `children`, while the pointer is over it or it has the
 * focus, so that the settings can be read without it. The popup is over the
 * whole page, so that nothing the panel holds, nor its edges, cuts it off.
 */
export function Help({ children }: { children: ReactNode }) {
    const mark = useRef<HTMLSpanElement>(null);
    const popup = useRef<HTMLSpanElement>(null);
    const [open, setOpen] = useState(false);
    const [place, setPlace] = useState<{ left: number; top: number } | null>(null);

    // under the question mark, moved to the left or above it where there is no room
    useLayoutEffect(() => {
        if (!open || !mark.current || !popup.current) {
            setPlace(null);
            return;
        }
        const at = mark.current.getBoundingClientRect();
        const size = popup.current.getBoundingClientRect();
        const left = Math.max(MARGIN, Math.min(at.left - MARGIN, window.innerWidth - size.width - MARGIN));
        const below = at.bottom + MARGIN;
        const top = below + size.height + MARGIN > window.innerHeight
            ? Math.max(MARGIN, at.top - size.height - MARGIN)
            : below;
        setPlace({ left, top });
    }, [open]);

    return (
        <span
            ref={mark}
            className="help"
            tabIndex={0}
            aria-label={t("About this setting")}
            // inside a label, a click on it must not change what the label is for
            onClick={(event) => event.preventDefault()}
            onPointerEnter={() => setOpen(true)}
            onPointerLeave={() => setOpen(false)}
            onFocus={() => setOpen(true)}
            onBlur={() => setOpen(false)}
        >
            ?
            {open && createPortal(
                <span
                    ref={popup}
                    className="help-popup"
                    role="tooltip"
                    // measured where it is not seen before it is placed
                    style={place ?? { left: 0, top: 0, visibility: "hidden" }}
                >
                    {children}
                </span>,
                document.body,
            )}
        </span>
    );
}
