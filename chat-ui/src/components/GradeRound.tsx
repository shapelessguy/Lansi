// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { type Message, t } from "../lib/i18n";
import type { Grade, GradePart } from "../lib/practice";

const MARKS = { right: "✓", partial: "~", wrong: "✗" } as const;

/** What each mark means, for those who cannot see it. */
const RESULTS: Record<keyof typeof MARKS, Message> = { right: "right", partial: "partly right", wrong: "wrong" };

/** One answer as it was graded: what was asked, what was answered, and what was right where it was not. */
function Answered({ graded }: { graded: GradePart }) {
    return (
        <>
            {graded.task && <p className="round-task">{graded.task}</p>}
            <p className={`round-answer ${graded.result}`}>
                <span className="round-mark" aria-label={t(RESULTS[graded.result])}>{MARKS[graded.result]}</span>
                {graded.answer || <span className="practice-detail">{t("nothing answered")}</span>}
            </p>
            {graded.result !== "right" && graded.correction && <p className="round-correct">{graded.correction}</p>}
            {graded.note && <p className="round-note">{graded.note}</p>}
        </>
    );
}

/**
 * A round of an exercise, as a card of its own, in the way the exercises
 * show what was answered: each answer under what it was asked, marked, with
 * the right one where it was not; one of several answers, such as the
 * questions on a text, each on its own, under what they were on.
 */
export function GradeRound({ grade, label }: { grade: Grade; label: string }) {
    const parts = grade.parts ?? [];
    const right = parts.filter((each) => each.result === "right").length;
    return (
        <li className={`done-round ${grade.result}`}>
            <span className="done-round-head">
                <span>{label}</span>
                {parts.length > 0 && <span>{t("{right} of {count} right", { right, count: parts.length })}</span>}
            </span>
            {/* what it was on, such as the text the questions were on, without which they are not understood */}
            {grade.about && (
                <details className="round-about">
                    <summary>{t("The text")}</summary>
                    <p>{grade.about}</p>
                </details>
            )}
            {parts.length > 0
                ? (
                    <ol className="round-parts">
                        {parts.map((each, number) => (
                            <li key={number}>
                                <Answered graded={each} />
                            </li>
                        ))}
                    </ol>
                )
                : <Answered graded={grade} />}
        </li>
    );
}
