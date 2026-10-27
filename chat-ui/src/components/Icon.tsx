// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

/** What each icon is drawn with, as lines on a square 24 wide. */
const ICONS = {
    library: (
        <>
            <path d="M4 19V5a2 2 0 0 1 2-2h13v18H6a2 2 0 0 1-2-2Z" />
            <path d="M4 19a2 2 0 0 1 2-2h13" />
        </>
    ),
    logs: (
        <>
            <path d="M9 6h11M9 12h11M9 18h11" />
            <path d="M4 6h.01M4 12h.01M4 18h.01" />
        </>
    ),
    tasks: (
        <>
            <circle cx="12" cy="12" r="9" />
            <path d="M12 7v5l3 2" />
        </>
    ),
    checks: <path d="M20 6 9 17l-5-5" />,
    chevron: <path d="m6 9 6 6 6-6" />,
    edit: (
        <>
            <path d="M12 20h9" />
            <path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z" />
        </>
    ),
    usage: <path d="M5 20v-8M12 20V4M19 20v-5" />,
    settings: (
        <>
            <path d="M4 6h9M17 6h3M4 12h3M11 12h9M4 18h11M19 18h1" />
            <circle cx="15" cy="6" r="2" />
            <circle cx="9" cy="12" r="2" />
            <circle cx="17" cy="18" r="2" />
        </>
    ),
    speak: (
        <>
            <path d="M11 5 6 9H3v6h3l5 4Z" />
            <path d="M15.5 8.5a5 5 0 0 1 0 7M18.5 5.5a9 9 0 0 1 0 13" />
        </>
    ),
    "sentence-checks": (
        <>
            <path d="M4 6h14M4 11h10M4 16h5" />
            <path d="m13 17 3 3 5-6" />
        </>
    ),
    "enter-sends": (
        <>
            <path d="M20 5v7a3 3 0 0 1-3 3H5" />
            <path d="m9 11-4 4 4 4" />
        </>
    ),
    "log-out": (
        <>
            <path d="M15 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3" />
            <path d="M10 17l-5-5 5-5M5 12h11" />
        </>
    ),
} as const;

export type IconName = keyof typeof ICONS;

/** An icon in the colour of the text around it, which is what says what it means: it says nothing itself. */
export function Icon({ name }: { name: IconName }) {
    return (
        <svg
            className="icon"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
        >
            {ICONS[name]}
        </svg>
    );
}
