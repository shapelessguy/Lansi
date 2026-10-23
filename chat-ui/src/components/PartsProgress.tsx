// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { type Message, t } from "../lib/i18n";
import { amount } from "../lib/inspect";
import { type PartProgress, writtenShare } from "../lib/tasks";

// the radius of a ring, and how far round it is
const RADIUS = 9;
const ROUND = 2 * Math.PI * RADIUS;

/**
 * How much of a part is written, as a ring: full once the model has written
 * as many tokens as the part was sent in, and round again in another colour
 * for what it writes beyond, as a text written anew is seldom just as long.
 */
function WrittenRing({ share }: { share: number }) {
    const first = Math.min(share, 1);
    const beyond = Math.min(Math.max(share - 1, 0), 1);
    return (
        <svg className="written-ring" viewBox="0 0 24 24" aria-hidden="true">
            <circle className="ring-track" cx="12" cy="12" r={RADIUS} />
            <circle
                className="ring-written"
                cx="12"
                cy="12"
                r={RADIUS}
                strokeDasharray={`${first * ROUND} ${ROUND}`}
            />
            {beyond > 0 && (
                <circle
                    className="ring-beyond"
                    cx="12"
                    cy="12"
                    r={RADIUS}
                    strokeDasharray={`${beyond * ROUND} ${ROUND}`}
                />
            )}
        </svg>
    );
}

/** A count of tokens in a few letters: 685, 1.2k, 32k. */
function short(tokens: number): string {
    if (tokens < 1000) {
        return String(tokens);
    }
    return `${(tokens / 1000).toFixed(tokens < 10_000 ? 1 : 0).replace(/\.0$/, "")}k`;
}

/** What a part is at, in a word. */
const STATES = {
    waiting: "Waiting",
    thinking: "Thinking",
    writing: "Writing",
    done: "Done",
} as const satisfies Record<PartProgress["state"], Message>;

/** How the transforming of each part of a book is going: the tokens reasoned, and how much is written. */
export function PartsProgress({ parts }: { parts: PartProgress[] }) {
    return (
        <ul className="parts-progress">
            {parts.map((part, index) => {
                const share = writtenShare(part);
                const started = part.state !== "waiting";
                return (
                    <li key={index} className={`part-progress ${part.state}`}>
                        <WrittenRing share={share} />
                        <span className="part-progress-title" title={part.title}>
                            {part.title || t("Part {number}", { number: index + 1 })}
                        </span>
                        <span
                            className="part-progress-share"
                            title={t("{written} tokens written, of the {expected} the part was sent in", {
                                written: amount(part.written),
                                expected: amount(part.expected),
                            })}
                        >
                            {started ? `${Math.round(share * 100)}%` : t("Waiting")}
                        </span>
                        <span className="part-progress-detail">
                            <span>
                                {t(STATES[part.state])}
                                {part.round > 1 && (
                                    <span
                                        title={t("The answer was too long for one, and is taken up where it broke off")}
                                    >
                                        {" · "}
                                        {t("answer {number}", { number: part.round })}
                                    </span>
                                )}
                            </span>
                            {started && (
                                <span title={t("Tokens of reasoning")}>
                                    {t("Reasoning")} {short(part.reasoning)}
                                    {part.budget ? ` / ${short(part.budget)}` : ""}
                                </span>
                            )}
                        </span>
                    </li>
                );
            })}
        </ul>
    );
}
