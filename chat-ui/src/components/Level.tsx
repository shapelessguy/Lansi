// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { LEVELS } from "../lib/settings";

/** The class that gives a level its colour, the same wherever it is shown. */
function levelClass(level: string): string {
    return `level level-${level.toLowerCase()}`;
}

/** A level, such as A1, in a small circle of its colour. */
export function LevelBadge({ level }: { level: string }) {
    return (
        <span className={levelClass(level)} title={`Level ${level}`}>
            {level}
        </span>
    );
}

interface PickerProps {
    value: string;
    onChange: (level: string) => void;
    /** What the choice is called, for those who cannot see the label. */
    label: string;
}

/** One of the levels to choose, each in its circle, the one chosen filled with its colour. */
export function LevelPicker({ value, onChange, label }: PickerProps) {
    return (
        <span className="level-picker" role="radiogroup" aria-label={label}>
            {LEVELS.map((level) => (
                <button
                    key={level}
                    type="button"
                    role="radio"
                    aria-checked={level === value}
                    className={levelClass(level)}
                    onClick={() => onChange(level)}
                >
                    {level}
                </button>
            ))}
        </span>
    );
}
