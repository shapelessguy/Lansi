// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import type { ReactNode } from "react";

import { t } from "../lib/i18n";

interface Props {
    title: string;
    onClose: () => void;
    /** Shown between the title and the content, and kept in place when the content scrolls. */
    tabs?: ReactNode;
    /** For content that fills the panel and scrolls by itself, such as a list. */
    flush?: boolean;
    children: ReactNode;
}

/**
 * What every panel at the sides is made of: a title with a button to close
 * the panel, and content that scrolls under it. Where the panels go is laid
 * out by the app.
 */
export function SidePanel({ title, onClose, tabs, flush, children }: Props) {
    return (
        <>
            <header className="panel-header">
                <h2>{title}</h2>
                <button
                    className="icon-button"
                    onClick={onClose}
                    title={t("Close")}
                    aria-label={t("Close {name}", { name: title })}
                >
                    ×
                </button>
            </header>
            {tabs}
            <div className={flush ? "panel-body flush" : "panel-body"}>{children}</div>
        </>
    );
}
