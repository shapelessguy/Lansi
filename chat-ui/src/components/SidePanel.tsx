// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { type ReactNode, useEffect, useRef, useState } from "react";

import { t } from "../lib/i18n";
import { Icon } from "./Icon";

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
 * out by the app. A panel at a side can also fill the window, as it always
 * does on a phone, until it is put back or closed.
 */
export function SidePanel({ title, onClose, tabs, flush, children }: Props) {
    const header = useRef<HTMLElement>(null);
    const [side, setSide] = useState<HTMLElement | null>(null);
    const [full, setFull] = useState(false);

    useEffect(() => {
        setSide(header.current?.closest<HTMLElement>(".side-panel") ?? null);
    }, []);

    useEffect(() => {
        if (!side || !full) {
            return;
        }
        side.classList.add("full");
        return () => side.classList.remove("full");
    }, [side, full]);

    return (
        <>
            <header className="panel-header" ref={header}>
                <h2>{title}</h2>
                <div className="panel-header-buttons">
                    {side && (
                        <button
                            className="icon-button panel-full-toggle"
                            // the button lets go of the focus, whose ring would stay on it after the switch
                            onClick={(event) => {
                                setFull(!full);
                                event.currentTarget.blur();
                            }}
                            title={full ? t("Put back at the side") : t("Fill the window")}
                            aria-label={full
                                ? t("Put {name} back at the side", { name: title })
                                : t("Fill the window with {name}", { name: title })}
                            aria-pressed={full}
                        >
                            <Icon name={full ? "leave-full-screen" : "full-screen"} />
                        </button>
                    )}
                    <button
                        className="icon-button"
                        onClick={() => {
                            setFull(false);
                            onClose();
                        }}
                        title={t("Close")}
                        aria-label={t("Close {name}", { name: title })}
                    >
                        ×
                    </button>
                </div>
            </header>
            {tabs}
            <div className={flush ? "panel-body flush" : "panel-body"}>{children}</div>
        </>
    );
}
