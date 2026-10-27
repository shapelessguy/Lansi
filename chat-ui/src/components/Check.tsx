// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import type { ReactNode } from "react";

interface Props {
    checked: boolean;
    onChange: (checked: boolean) => void;
    /** What it turns on, written after the box. */
    children: ReactNode;
    /** What it does, shown when the mouse is over it. */
    title?: string;
    disabled?: boolean;
    /** The class of the label, "check" unless another is given; none if it is empty. */
    className?: string;
}

/** A checkbox with what it turns on beside it, as the bars and forms of the app have them. */
export function Check({ checked, onChange, children, title, disabled, className = "check" }: Props) {
    return (
        <label className={className || undefined} title={title}>
            <input
                type="checkbox"
                checked={checked}
                disabled={disabled}
                onChange={(event) => onChange(event.target.checked)}
            />
            {children}
        </label>
    );
}
