// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import type { ProfileUsage } from "./checker";
import { type Message, t } from "./i18n";
import { call, type Learner, posting, type PracticeSession } from "./practice";
import type { BackgroundTask } from "./tasks";
import { profileUsage, type UsageEntry } from "./usage";

/** A module of an exam, such as reading, with what the exam calls it and how much it counts. */
export interface ExamModule {
    id: string;
    title: string;
    weight: number;
}

/** The exam there is of a level, as its template has it. */
export interface ExamLevel {
    level: string;
    /** What the exam is called, as its template names it. */
    exam: string;
    /** How long it takes in full. */
    minutes: number;
    modules: (ExamModule & { minutes: number })[];
}

/** A part of an evaluation: an exercise, set as the exam has it, and how far it got. */
export interface EvaluationPart {
    module: string;
    title: string;
    exercise: string;
    options: Record<string, string | number>;
    instances: number;
    /** How long it takes, which is its limit when the evaluation is timed. */
    minutes: number;
    points: number;
    /** What the learner is told to do, in the language of the exam. */
    instructions: string;
    /** The session it is done in, once it was started. */
    session: string | null;
    status: "pending" | "running" | "done";
    /** What its exercise scored, once it is done. */
    scores: Record<string, number> | null;
}

/** What an evaluation came to, or has so far. */
export interface EvaluationResult {
    /** Each of `SCORES`, from 0 to 100, or null for what was not shown. */
    scores: Record<string, number | null>;
    /** Whether it was passed, or null while not every module was done. */
    passed: boolean | null;
}

export interface Evaluation {
    id: string;
    language: string;
    level: string;
    /** How long it was to take, in half hours. */
    length: number;
    timed: boolean;
    plan: { exam: string; pass: Record<string, number>; modules: ExamModule[] };
    status: "running" | "finished" | "abandoned";
    /** In seconds since the epoch. */
    started_at: number;
    finished_at: number | null;
    result: EvaluationResult;
    parts: EvaluationPart[];
}

/** The shortest and the longest an evaluation may take, in half hours. */
export const LENGTHS = { min: 1, max: 8 } as const;
/** What the requests of the evaluations are counted under. */
export const USAGE_ID = "evaluations";

/** The skills an exam is made of, which are its modules, with what each is called. */
export const MODULES: Record<string, Message> = {
    listening: "Listening",
    reading: "Reading",
    writing: "Writing",
    speaking: "Speaking",
};
/** How what is written or said is rated, with what each criterion is called. */
const CRITERIA: Record<string, Message> = {
    task: "task",
    coherence: "coherence",
    vocabulary: "vocabulary",
    structures: "structures",
    pronunciation: "pronunciation",
};
/** The modules that are rated by the criteria. */
const RATED = ["writing", "speaking"];

/** The scores an evaluation has, in order: each module, each criterion of those that are rated, and the total. */
export const SCORES: string[] = [
    ...Object.keys(MODULES),
    ...RATED.flatMap((module) => Object.keys(CRITERIA).map((criterion) => `${module}_${criterion}`)),
    "total",
];

/** A length of half hours, as it is said, such as "1 h 30 min". */
export function describeLength(length: number): string {
    const hours = Math.floor(length / 2);
    const minutes = (length % 2) * 30;
    return [hours ? `${hours} h` : "", minutes ? `${minutes} min` : ""].filter(Boolean).join(" ");
}

/** The part to be done next: the one running, or else the first not done, or null if all are. */
export function currentPart(evaluation: Evaluation): number | null {
    const running = evaluation.parts.findIndex((part) => part.status === "running");
    if (running !== -1) {
        return running;
    }
    const next = evaluation.parts.findIndex((part) => part.status === "pending");
    return next === -1 ? null : next;
}

/** What a module is called in the exam of its `modules`, or else in the language of the interface. */
export function moduleTitle(modules: ExamModule[], id: string): string {
    return modules.find((module) => module.id === id)?.title ?? (MODULES[id] ? t(MODULES[id]) : id);
}

/**
 * The scores that were shown, in the order of `SCORES`, each with what it is
 * called, a module as the exam of its `modules` calls it.
 */
export function shownScores(
    result: EvaluationResult,
    modules: ExamModule[] = [],
): { name: string; label: string; value: number }[] {
    return SCORES.flatMap((name) => {
        const value = result.scores[name];
        if (typeof value !== "number") {
            return [];
        }
        const [module, criterion] = name.split("_");
        const label = name === "total"
            ? t("Total")
            : criterion
            ? `${moduleTitle(modules, module)}: ${CRITERIA[criterion] ? t(CRITERIA[criterion]) : criterion}`
            : moduleTitle(modules, module);
        return [{ name, label, value }];
    });
}

export async function fetchLevels(language: string): Promise<ExamLevel[]> {
    const { levels } = await call<{ levels: ExamLevel[] }>(
        `/evaluations/levels?language=${encodeURIComponent(language)}`,
    );
    return levels;
}

/** Every evaluation, the latest first. */
export async function fetchEvaluations(): Promise<Evaluation[]> {
    const { evaluations } = await call<{ evaluations: Evaluation[] }>("/evaluations");
    return evaluations;
}

/** Starts an evaluation of `level`, of `length` half hours, each part in its time if `timed`. */
export function startEvaluation(language: string, level: string, length: number, timed: boolean): Promise<Evaluation> {
    return call("/evaluations", posting({ language, level, length, timed }));
}

/** Starts a part of an evaluation in a session of its own, or takes up the one it is in. */
export function startPart(id: string, position: number): Promise<{ evaluation: Evaluation; session: PracticeSession }> {
    return call(`/evaluations/${encodeURIComponent(id)}/parts/${position}/start`, posting({}));
}

/** Finishes the part that is running, and the evaluation with it if it was the last. */
export function finishPart(
    id: string,
    position: number,
    learner: Learner,
): Promise<{ evaluation: Evaluation; usage: ProfileUsage[]; tasks?: BackgroundTask[] }> {
    return call(`/evaluations/${encodeURIComponent(id)}/parts/${position}/finish`, posting({}, learner));
}

/** Ends an evaluation, after finishing the part that is running. */
export function endEvaluation(
    id: string,
    learner: Learner,
): Promise<{ evaluation: Evaluation; usage: ProfileUsage[]; tasks?: BackgroundTask[] }> {
    return call(`/evaluations/${encodeURIComponent(id)}/end`, posting({}, learner));
}

/** What a request of an evaluation used, as the usage is counted. */
export function evaluationUsage(used: ProfileUsage, at: number): UsageEntry {
    return profileUsage(used, at, "practice", USAGE_ID);
}
