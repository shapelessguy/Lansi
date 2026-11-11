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
    // the activities
    tutor: <path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12Z" />,
    books: (
        <>
            <path d="M2 5h6a4 4 0 0 1 4 4v11a3 3 0 0 0-3-3H2Z" />
            <path d="M22 5h-6a4 4 0 0 0-4 4v11a3 3 0 0 1 3-3h7Z" />
        </>
    ),
    texts: (
        <>
            <path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9Z" />
            <path d="M14 3v6h6M8 13h8M8 17h5" />
        </>
    ),
    practice: (
        <>
            <circle cx="12" cy="12" r="9" />
            <circle cx="12" cy="12" r="5" />
            <circle cx="12" cy="12" r="1" />
        </>
    ),
    evaluations: (
        <>
            <path d="m2 9 10-5 10 5-10 5Z" />
            <path d="M6 11v5c0 1.5 2.7 3 6 3s6-1.5 6-3v-5M22 9v6" />
        </>
    ),
    chevron: <path d="m6 9 6 6 6-6" />,
    edit: (
        <>
            <path d="M12 20h9" />
            <path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z" />
        </>
    ),
    usage: <path d="M5 20v-8M12 20V4M19 20v-5" />,
    "full-screen": <path d="M4 9V4h5M15 4h5v5M20 15v5h-5M9 20H4v-5" />,
    "leave-full-screen": <path d="M9 4v5H4M20 9h-5V4M15 20v-5h5M4 15h5v5" />,
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
    // the pens of a page written by hand, and what is done with it
    pen: (
        <>
            <path d="M12 20h9" />
            <path d="M16.4 3.6a2.1 2.1 0 0 1 3 3L7.4 18.6a2 2 0 0 1-.9.5l-2.9.9.9-2.9a2 2 0 0 1 .5-.9Z" />
        </>
    ),
    fountain: (
        <>
            <path d="m12 19 7-7 3 3-7 7Z" />
            <path d="m18 13-1.5-7.5L2 2l3.5 14.5L13 18Z" />
            <path d="m2 2 7.6 7.6" />
            <circle cx="11" cy="11" r="2" />
        </>
    ),
    pencil: (
        <>
            <path d="M17 3a2.8 2.8 0 0 1 4 4L7.5 20.5 2 22l1.5-5.5Z" />
            <path d="m15 5 4 4" />
        </>
    ),
    highlighter: (
        <>
            <path d="m9 11-6 6v3h9l3-3" />
            <path d="m22 12-4.6 4.6a2 2 0 0 1-2.8 0l-5.2-5.2a2 2 0 0 1 0-2.8L14 4" />
        </>
    ),
    eraser: (
        <>
            <path d="M21 21H8a2 2 0 0 1-1.4-.6l-4-4a2 2 0 0 1 0-2.8l10-10a2 2 0 0 1 2.8 0l6 6a2 2 0 0 1 0 2.8L12.8 21" />
            <path d="m5.1 11.1 8.8 8.8" />
        </>
    ),
    undo: (
        <>
            <path d="M9 14 4 9l5-5" />
            <path d="M4 9h10.5a5.5 5.5 0 0 1 0 11H11" />
        </>
    ),
    close: <path d="M18 6 6 18M6 6l12 12" />,
    previous: <path d="m15 18-6-6 6-6" />,
    next: <path d="m9 18 6-6-6-6" />,
    turn: (
        <>
            <rect x="3" y="9" width="12" height="12" rx="1" />
            <path d="M12 3h3a6 6 0 0 1 6 6v3" />
            <path d="m18 9 3 3 3-3" />
        </>
    ),
    words: <path d="M4 7V5h16v2M9 19h6M12 5v14" />,
    add: <path d="M12 5v14M5 12h14" />,
    "new-text": (
        <>
            <path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9Z" />
            <path d="M14 3v6h6M8 13h8M8 17h5" />
        </>
    ),
    "new-handwritten": (
        <>
            <path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h4" />
            <path d="M14 3v6h6" />
            <path d="M19.4 12.6a1.9 1.9 0 0 1 2.7 2.7L16 21.4l-3.5.9.9-3.5Z" />
        </>
    ),
    read: (
        <>
            <path d="M3 7V5a2 2 0 0 1 2-2h2M17 3h2a2 2 0 0 1 2 2v2M21 17v2a2 2 0 0 1-2 2h-2M7 21H5a2 2 0 0 1-2-2v-2" />
            <path d="M7 8h8M7 12h10M7 16h6" />
        </>
    ),
    "word-boxes": (
        <>
            <rect x="3" y="5" width="7" height="6" rx="1" />
            <rect x="13" y="5" width="8" height="6" rx="1" />
            <rect x="3" y="14" width="11" height="6" rx="1" />
        </>
    ),
    trash: <path d="M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14" />,
    // those of a player, filled
    play: <path d="M7 4.5v15l12-7.5Z" fill="currentColor" />,
    pause: (
        <>
            <rect x="6" y="4.5" width="4" height="15" rx="1" fill="currentColor" />
            <rect x="14" y="4.5" width="4" height="15" rx="1" fill="currentColor" />
        </>
    ),
    "skip-back": (
        <>
            <path d="M6 5v14" />
            <path d="M19 5.5v13L9 12Z" fill="currentColor" />
        </>
    ),
    "skip-forward": (
        <>
            <path d="M18 5v14" />
            <path d="M5 5.5v13L15 12Z" fill="currentColor" />
        </>
    ),
    "play-section": (
        <>
            <path d="M3 5v14l9-7Z" fill="currentColor" />
            <path d="M15 6h6M15 12h6M15 18h6" />
        </>
    ),
    translate: (
        <>
            <path d="m5 8 6 6M4 14l6-6 2-3M2 5h12M7 2h1" />
            <path d="m22 22-5-10-5 10M14 18h6" />
        </>
    ),
    "add-words": (
        <>
            <path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1 0-5H20" />
            <path d="M12 7v6M9 10h6" />
        </>
    ),
    stop: <rect x="6" y="6" width="12" height="12" rx="2" fill="currentColor" />,
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
