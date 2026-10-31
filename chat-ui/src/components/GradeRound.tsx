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

/** Only what was asked, without what was answered, as a favourite shows what it is of. */
function Asked({ graded }: { graded: GradePart }) {
    return graded.task ? <p className="round-task">{graded.task}</p> : null;
}

/** A round of an exercise as a favourite shows it: only the texts of what it asks, each on its own. */
export function AskedRound({ texts, label }: { texts: string[]; label: string }) {
    return (
        <li className="done-round asked">
            <span className="done-round-head">
                <span>{label}</span>
            </span>
            {texts.map((text, number) => <p key={number} className="round-task">{text}</p>)}
        </li>
    );
}

/**
 * A round of an exercise, as a card of its own, in the way the exercises
 * show what was answered: each answer under what it was asked, marked, with
 * the right one where it was not; one of several answers, such as the
 * questions on a text, each on its own, under what they were on. If
 * `asked`, only what was asked, unmarked, as a favourite is shown, being a
 * placeholder of the exercise rather than a record of how it went.
 */
export function GradeRound({ grade, label, asked = false }: { grade: Grade; label: string; asked?: boolean }) {
    const parts = grade.parts ?? [];
    const right = parts.filter((each) => each.result === "right").length;
    const Shown = asked ? Asked : Answered;
    return (
        <li className={`done-round ${asked ? "asked" : grade.result}`}>
            <span className="done-round-head">
                <span>{label}</span>
                {!asked && parts.length > 0 && (
                    <span>{t("{right} of {count} right", { right, count: parts.length })}</span>
                )}
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
                                <Shown graded={each} />
                            </li>
                        ))}
                    </ol>
                )
                : <Shown graded={grade} />}
        </li>
    );
}
