// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { Icon, type IconName } from "./Icon";

interface Props {
    /** The icon that stands for what it turns on. */
    icon: IconName;
    /** What it turns on, in a few words, said by screen readers and at the start of the title. */
    label: string;
    /** What it does, shown after the label when the mouse is over it. */
    title?: string;
    on: boolean;
    onChange: (on: boolean) => void;
    disabled?: boolean;
}

/** An icon that turns something on and off, lit while it is on, which bars have in place of a checkbox with its words. */
export function Toggle({ icon, label, title, on, onChange, disabled }: Props) {
    return (
        <button
            type="button"
            className="toggle"
            aria-pressed={on}
            aria-label={label}
            title={title ? `${label}: ${title}` : label}
            disabled={disabled}
            onClick={() => onChange(!on)}
        >
            <Icon name={icon} />
        </button>
    );
}
