// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { useEffect, useState } from "react";

import {
    describeLength,
    type Evaluation,
    type EvaluationResult,
    type ExamModule,
    fetchEvaluations,
    moduleTitle,
    shownScores,
} from "../lib/evaluations";
import { locale, t } from "../lib/i18n";
import { fetchSession, type Grade } from "../lib/practice";
import { GradeRound } from "./GradeRound";
import { LevelBadge } from "./Level";

interface Props {
    /** Whether the tab is shown, which is when the evaluations are listed. */
    active: boolean;
    /** Changes when an evaluation may have ended, so that they are listed again. */
    revision: number;
}

/** Whether it was passed, in a word. */
export function passedOf(result: EvaluationResult): string {
    return result.passed === null ? t("not every module done") : result.passed ? t("passed") : t("not passed");
}

/** The scores of an evaluation, each with a bar. */
export function ScoreTable({ result, modules }: { result: EvaluationResult; modules: ExamModule[] }) {
    const shown = shownScores(result, modules);
    if (shown.length === 0) {
        return <p className="practice-detail">{t("Nothing was scored.")}</p>;
    }
    return (
        <dl className="evaluation-scores">
            {shown.map(({ name, label, value }) => (
                <div key={name} className={name.includes("_") ? "evaluation-score criterion" : "evaluation-score"}>
                    <dt>{label}</dt>
                    <dd>
                        <span className="evaluation-meter">
                            <span className={value >= 60 ? "pass" : ""} style={{ width: `${value}%` }} />
                        </span>
                        <span>{Math.round(value)}</span>
                    </dd>
                </div>
            ))}
        </dl>
    );
}

function dayOf(seconds: number): string {
    return new Date(seconds * 1000).toLocaleDateString(locale(), {
        weekday: "short",
        day: "numeric",
        month: "short",
        year: "numeric",
    });
}

/**
 * The evaluations that are over, the latest first, in the panel of the
 * logs: each with how it went, and, once opened, the scores and every part
 * with what was answered in it and what was not right, which an exam tells
 * only once it is over.
 */
export function EvaluationsDone({ active, revision }: Props) {
    const [evaluations, setEvaluations] = useState<Evaluation[] | null>(null);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        if (!active) {
            return;
        }
        let current = true;
        fetchEvaluations().then(
            (found) => {
                if (current) {
                    setEvaluations(found.filter((each) => each.status !== "running"));
                    setError(null);
                }
            },
            (failed: Error) => current && setError(failed.message),
        );
        return () => {
            current = false;
        };
    }, [active, revision]);

    if (error) {
        return <p className="sidebar-note error">{error}</p>;
    }
    if (!evaluations) {
        return <p className="sidebar-note">{t("Loading…")}</p>;
    }
    if (evaluations.length === 0) {
        return <p className="sidebar-note">{t("No evaluation is over yet.")}</p>;
    }
    return (
        <div className="log-list evaluations-done">
            <ul className="log-day">
                {evaluations.map((each) => (
                    <li key={each.id} className="log-entry done-exercise">
                        <details>
                            <summary>
                                <LevelBadge level={each.level} />
                                <span className="done-exercise-what">
                                    <span className="log-head">
                                        <span className="log-subject">{each.plan.exam}</span>
                                        {typeof each.result.scores.total === "number" && (
                                            <span className="done-count">{Math.round(each.result.scores.total)}</span>
                                        )}
                                    </span>
                                    <span className="log-where">
                                        {dayOf(each.started_at)} · {describeLength(each.length)}
                                        {each.timed ? `, ${t("timed")}` : ""} · {passedOf(each.result)}
                                    </span>
                                </span>
                            </summary>
                            <EvaluationReview evaluation={each} />
                        </details>
                    </li>
                ))}
            </ul>
        </div>
    );
}

/**
 * How an evaluation went, once it is over: its scores, and each part with
 * every round of it, what was answered and what was not right.
 */
export function EvaluationReview({ evaluation }: { evaluation: Evaluation }) {
    // the grades of each part that was done, by its session
    const [grades, setGrades] = useState<Record<string, Grade[] | "failed">>({});

    useEffect(() => {
        let current = true;
        for (const part of evaluation.parts) {
            if (!part.session) {
                continue;
            }
            const session = part.session;
            fetchSession(session).then(
                (found) => current && setGrades((had) => ({ ...had, [session]: found.grades })),
                () => current && setGrades((had) => ({ ...had, [session]: "failed" })),
            );
        }
        return () => {
            current = false;
        };
    }, [evaluation]);

    return (
        <div className="evaluation-review">
            <ScoreTable result={evaluation.result} modules={evaluation.plan.modules} />
            {evaluation.parts.map((part, number) => {
                const got = part.session ? grades[part.session] : undefined;
                const rounds = Array.isArray(got) ? got.filter((grade) => grade.exercise === part.exercise) : [];
                return (
                    <section key={number} className="evaluation-review-part">
                        <h4>
                            {moduleTitle(evaluation.plan.modules, part.module)} · {part.title}
                        </h4>
                        {!part.session && <p className="sidebar-note">{t("Not done.")}</p>}
                        {got === "failed" && (
                            <p className="sidebar-note error">{t("What was answered could not be had.")}</p>
                        )}
                        {Array.isArray(got) && rounds.length === 0 && (
                            <p className="sidebar-note">{t("Nothing was answered.")}</p>
                        )}
                        {rounds.length > 0 && (
                            <ol className="done-rounds">
                                {rounds.map((grade, round) => (
                                    <GradeRound
                                        key={round}
                                        grade={grade}
                                        label={t("Task {number}", { number: round + 1 })}
                                    />
                                ))}
                            </ol>
                        )}
                    </section>
                );
            })}
        </div>
    );
}
