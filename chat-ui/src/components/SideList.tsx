// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { type ReactNode, useEffect, useState } from "react";

import { Icon } from "./Icon";

/**
 * A list, such as that of the chats, in the empty space on the left of
 * what is open, over it. Where there is no room for it there, it is a
 * button with its `label` that opens it, and closes it again once
 * something in it is picked. While nothing of it is open, the list is
 * opened by itself, since then it is what there is to do.
 */
export function SideList(
    { label, nothingOpen = false, children }: { label: string; nothingOpen?: boolean; children: ReactNode },
) {
    const [open, setOpen] = useState(nothingOpen);
    // and is put away again once something is opened, such as a new one
    useEffect(() => setOpen(nothingOpen), [nothingOpen]);
    return (
        <div className={`side-list${open ? " open" : ""}`}>
            <button className="side-list-toggle" aria-expanded={open} onClick={() => setOpen(!open)}>
                <Icon name="logs" />
                {label}
                <Icon name="chevron" />
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
