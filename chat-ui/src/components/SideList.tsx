// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { type ReactNode, useState } from "react";

/**
 * A list, such as that of the chats, in the empty space on the left of
 * what is open, over it. Where there is no room for it there, it is a
 * button with its `label` that opens it, and closes it again once
 * something in it is picked.
 */
export function SideList({ label, children }: { label: string; children: ReactNode }) {
    const [open, setOpen] = useState(false);
    return (
        <div className={`side-list${open ? " open" : ""}`}>
            <button className="side-list-toggle" aria-expanded={open} onClick={() => setOpen(!open)}>
                {label}
            </button>
            <div
                className="side-list-body"
                onClick={(event) => (event.target as HTMLElement).closest("li") && setOpen(false)}
            >
                {children}
            </div>
        </div>
    );
}
