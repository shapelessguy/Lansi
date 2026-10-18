// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import type { ProfileUsage } from "./checker";
import { type ModelChoice, modelRequest } from "./models";
import { checkerFetch } from "./session";
import type { Settings } from "./settings";
import type { BackgroundTask } from "./tasks";
import { describeError } from "./translate";
import { profileUsage, type UsageEntry } from "./usage";

/** A grammar point of a lesson, with what it is there for. */
export interface LessonPoint {
    id: string;
    /** "new" is taught, "review" practised again, "preview" only shown ahead of time. */
    role: "new" | "review" | "preview";
}

export interface Lesson {
    id: string;
    level: string;
    title: string;
    points: LessonPoint[];
    more_info: string;
}

/** A setting of an exercise that is one of a few choices. */
export interface ChoiceOption {
    label: string;
    /** The labels of the choices by their values, the first the one taken unless another is. */
    choices: Record<string, string>;
}

/** A setting of an exercise that is a whole number from `min` to `max`. */
export interface NumberOption {
    label: string;
    min: number;
    max: number;
    /** The one taken unless another is. */
    default: number;
}

/** What the learner may set of an exercise besides how many times it is done. */
export type ExerciseOption = ChoiceOption | NumberOption;

/** What an option is set to. */
export type OptionValue = string | number;

/** An exercise there is, as its manifest describes it. */
export interface ExerciseInfo {
    id: string;
    title: string;
    description: string;
    /** Whether it teaches rather than asks: it comes first, is done once, and is graded on nothing. */
    theory: boolean;
    /** Its options, by their names. */
    options: Record<string, ExerciseOption>;
}

/** The value of an option that is taken unless another is chosen: its first choice, or its default. */
function defaultOf(option: ExerciseOption): OptionValue {
    return "choices" in option ? Object.keys(option.choices)[0] : option.default;
}

/** The value of each option of an exercise that is taken unless another is chosen. */
export function defaultOptions(exercise: ExerciseInfo): Record<string, OptionValue> {
    return optionsOf(exercise, {});
}

/**
 * The value of each option of an exercise, as `remembered` has it where it
 * is one the option can have, and else the one taken unless another is. A
 * number out of its bounds is brought within them.
 */
export function optionsOf(
    exercise: ExerciseInfo,
    remembered: Record<string, OptionValue> = {},
): Record<string, OptionValue> {
    return Object.fromEntries(
        Object.entries(exercise.options ?? {}).map(([name, option]) => {
            const value = remembered[name];
            if ("choices" in option) {
                return [name, typeof value === "string" && value in option.choices ? value : defaultOf(option)];
            }
            if (typeof value !== "number" || !Number.isFinite(value)) {
                return [name, defaultOf(option)];
            }
            return [name, Math.min(option.max, Math.max(option.min, Math.round(value)))];
        }),
    );
}

export interface ExerciseProgress {
    status: "pending" | "started" | "finished";
    /** How many grades it has kept, one for each instance done. */
    answered: number;
    /** How many of the grades are of each result. */
    results: Record<Grade["result"], number>;
    /** When it was first shown, in seconds since the epoch, or null if it was not yet. */
    started_at: number | null;
    /** What it scored, from 0 to 100 by what it shows, once it is finished, or null. */
    scores: Record<string, number> | null;
}

export interface PracticeSession {
    id: string;
    language: string;
    /** Empty for a review, which goes over `lessons`. */
    lesson: string;
    lessons: string[];
    topics: string[];
    /** In seconds since the epoch. */
    started_at: number;
    finished_at: number | null;
    status: "running" | "finished" | "abandoned";
    /** The words the exercises are given, those nearest the topics first, if any. */
    words: { mode: "only" | "prefer"; lemmas: string[] } | null;
    /** Whether the exercises bring the topics together. */
    mix_topics: boolean;
    /** The exercises, in the order they are done, with how many instances of each there are. */
    exercises: Record<string, number>;
    /** The options each exercise was chosen with, by exercise. */
    options: Record<string, Record<string, string>>;
    /** How many minutes each exercise may take, 0 for no limit, by exercise. */
    minutes: Record<string, number>;
    /** "evaluation" for a part of an evaluation, which is not listed with practice. */
    kind: "practice" | "evaluation";
    progress: Record<string, ExerciseProgress>;
}

/** Who practises, and who is asked for them. */
export interface Learner {
    apiKey: string;
    model: ModelChoice;
    /** What draws the pictures of an exercise. */
    imageModel: ModelChoice;
    /** What looks at the pictures of an exercise; naming none, it is `model`. */
    visionModel: ModelChoice;
    /** The language the learner reads explanations in. */
    into: string;
    level: string;
}

/** How many instances of an exercise there are unless the learner says otherwise. */
export const DEFAULT_INSTANCES = 5;
export const MAX_INSTANCES = 50;
/** The longest time limit an exercise may have, in minutes, as the server takes it. */
export const MAX_MINUTES = 240;
/** What the requests of the exercises are counted under. */
export const USAGE_ID = "practice";

/** Asks the checker server, and resolves with what it replied, or rejects with why it could not. */
export async function call<Reply>(path: string, init: RequestInit = {}): Promise<Reply> {
    let response: Response;
    try {
        response = await checkerFetch(path, init);
    } catch {
        throw new Error("The server cannot be reached.");
    }
    const reply = await response.json().catch(() => ({}));
    if (!response.ok) {
        throw new Error(describeError(reply.error, response.status));
    }
    return reply;
}

/** A POST of `body`, with the models of `learner` and who they are, if given. */
export function posting(body: object, learner?: Learner): RequestInit {
    return {
        method: "POST",
        // the server asks the model with the key; it is not kept there
        headers: learner?.apiKey ? { "X-OpenRouter-Key": learner.apiKey } : {},
        body: JSON.stringify(
            learner
                ? {
                    ...body,
                    model: modelRequest(learner.model),
                    image_model: modelRequest(learner.imageModel),
                    vision_model: modelRequest(learner.visionModel),
                    into: learner.into,
                    level: learner.level,
                }
                : body,
        ),
    };
}

export async function fetchLessons(language: string): Promise<Lesson[]> {
    const { lessons } = await call<{ lessons: Lesson[] }>(`/lessons?language=${encodeURIComponent(language)}`);
    return lessons;
}

export async function fetchExercises(): Promise<ExerciseInfo[]> {
    const { exercises } = await call<{ exercises: ExerciseInfo[] }>("/exercises");
    return exercises;
}

/** How the topics and the words of a session are chosen, as the server takes it. */
export interface Choosing {
    mix_topics: boolean;
    vocabulary: "none" | "all" | "set";
    /** The words of the set, when the vocabulary is a set. */
    words: string[];
    topic_words: boolean;
    embedding_model: string | ModelChoice;
}

/**
 * How the words of a session are chosen, as the settings say: `vocabulary`
 * is "none", "all", or a set, whose words are `setWords`. A set that is
 * gone, with no words to be had, is taken for the whole vocabulary.
 */
export function choosingOf(settings: Settings, vocabulary: string, setWords: string[] | null): Choosing {
    const chosen = vocabulary === "none" ? "none" : vocabulary === "all" || setWords === null ? "all" : "set";
    return {
        mix_topics: settings.exerciseMixTopics,
        vocabulary: chosen,
        words: chosen === "set" ? setWords ?? [] : [],
        topic_words: settings.exerciseTopicWords,
        embedding_model: modelRequest(settings.embeddingModel),
    };
}

/**
 * Starts a session of `lesson`, with the exercises chosen and how many
 * instances of each, with the `options` of each, about `topics`, with the
 * words `choosing` says. Without a lesson, the session reviews the
 * lessons practised last.
 */
export function startSession(
    language: string,
    lesson: string | null,
    exercises: Record<string, number>,
    topics: string[],
    choosing: Choosing,
    apiKey: string,
    options: Record<string, Record<string, OptionValue>> = {},
    minutes: Record<string, number> = {},
): Promise<PracticeSession & { usage: ProfileUsage[] }> {
    const chosenOptions = Object.fromEntries(Object.entries(options).filter(([id]) => id in exercises));
    const chosenMinutes = Object.fromEntries(Object.entries(minutes).filter(([id]) => id in exercises));
    const init = posting({
        language,
        lesson: lesson ?? "",
        topics,
        exercises,
        options: chosenOptions,
        minutes: chosenMinutes,
        ...choosing,
    });
    return call("/sessions", { ...init, headers: apiKey ? { "X-OpenRouter-Key": apiKey } : {} });
}

/**
 * Makes a step of an exercise of a session: `start` it, have it `act` on
 * what its interface sent, or `finish` it. Resolves with what it is to show.
 */
export function stepExercise(
    sessionId: string,
    exercise: string,
    op: "start" | "act" | "finish",
    message: unknown,
    learner: Learner,
): Promise<{ show: unknown; usage: ProfileUsage[]; tasks?: BackgroundTask[] }> {
    return call(
        `/sessions/${encodeURIComponent(sessionId)}/exercises/${encodeURIComponent(exercise)}/${op}`,
        posting({ message }, learner),
    );
}

/** What the learner answered once, as an exercise graded it. */
export interface Grade {
    exercise: string;
    result: "right" | "wrong" | "partial";
    /** What the exercise gave the learner to answer, written by a model. */
    task: string;
    /** Only what the learner wrote. */
    answer: string;
    correction: string;
    note: string;
}

/** Every session there was, the latest first. */
export async function fetchSessions(): Promise<PracticeSession[]> {
    const { sessions } = await call<{ sessions: PracticeSession[] }>("/sessions");
    return sessions;
}

/**
 * A session with what was answered in it, and the log of each exercise that
 * is over, by exercise: what worked and what did not, written by a model for
 * the app rather than for the learner.
 */
export function fetchSession(
    id: string,
): Promise<PracticeSession & { grades: Grade[]; logs: Record<string, string> }> {
    return call(`/sessions/${encodeURIComponent(id)}`);
}

/**
 * Where to take up a session again: the first of its exercises that is not
 * finished, or the last if all are.
 */
export function resumeAt(session: PracticeSession): number {
    const order = Object.keys(session.exercises);
    const at = order.findIndex((exercise) => session.progress[exercise]?.status !== "finished");
    return at === -1 ? Math.max(0, order.length - 1) : at;
}

/**
 * How many answers an exercise of a session has had graded, or nothing for
 * one with no instances, such as theory. It is not said out of how many
 * instances, as an instance may grade many answers, as a picture does.
 */
export function answeredOf(session: PracticeSession, exercise: string): string {
    if (!session.exercises[exercise]) {
        return "";
    }
    return `${session.progress[exercise]?.answered ?? 0} answered`;
}

/** How a session went: how many of its instances had each result, out of how many there were to be. */
export interface Score {
    right: number;
    partial: number;
    wrong: number;
    total: number;
    /** Out of 100, with an answer that was almost right counted as half, or null if nothing was answered. */
    percent: number | null;
}

export function scoreOf(session: PracticeSession): Score {
    const score: Score = { right: 0, partial: 0, wrong: 0, total: 0, percent: null };
    for (const [exercise, instances] of Object.entries(session.exercises)) {
        const results = session.progress[exercise]?.results;
        score.right += results?.right ?? 0;
        score.partial += results?.partial ?? 0;
        score.wrong += results?.wrong ?? 0;
        score.total += instances;
    }
    const answered = score.right + score.partial + score.wrong;
    score.total = Math.max(score.total, answered);
    if (answered > 0) {
        score.percent = Math.round((100 * (score.right + score.partial / 2)) / answered);
    }
    return score;
}

/**
 * The lessons of `language` whose theory has been read to the end in some
 * session, which is what makes a lesson done.
 */
export function lessonsRead(sessions: PracticeSession[], theories: string[], language: string): Set<string> {
    const read = new Set<string>();
    for (const session of sessions) {
        if (
            session.language === language
            && theories.some((theory) => session.progress[theory]?.status === "finished")
        ) {
            read.add(session.lesson);
        }
    }
    return read;
}

/** How many of the lessons practised last a session without a lesson reviews, as the server goes by. */
export const REVIEWED_LESSONS = 10;

/**
 * The ids of the lessons of `language` a session without a lesson would
 * review: the last `REVIEWED_LESSONS` practised in a session of their own,
 * in the order of `lessons`, which is the order they are taught in.
 */
export function lessonsToReview(sessions: PracticeSession[], lessons: Lesson[], language: string): string[] {
    // the sessions come the latest first
    const latestFirst = [
        ...new Set(
            sessions.filter((session) => session.language === language && session.lesson).map((session) =>
                session.lesson
            ),
        ),
    ];
    const last = new Set(latestFirst.slice(0, REVIEWED_LESSONS));
    return lessons.filter((lesson) => last.has(lesson.id)).map((lesson) => lesson.id);
}

/** Ends a session, after the server has finished the exercises of it that were started. */
export function endSession(
    sessionId: string,
    status: "finished" | "abandoned",
    learner: Learner,
): Promise<{ session: PracticeSession; usage: ProfileUsage[]; tasks?: BackgroundTask[] }> {
    return call(`/sessions/${encodeURIComponent(sessionId)}/end`, posting({ status }, learner));
}

/** What a request of an exercise used, as the usage is counted. */
export function practiceUsage(used: ProfileUsage, at: number): UsageEntry {
    return profileUsage(used, at, "practice", USAGE_ID);
}

/**
 * How many seconds are left of the time an exercise of a session has, at
 * `now` in milliseconds, or null if it has no limit or has not started.
 */
export function secondsLeft(session: PracticeSession, exercise: string, now: number): number | null {
    const limit = session.minutes?.[exercise] ?? 0;
    const started = session.progress[exercise]?.started_at ?? null;
    if (!limit || started === null) {
        return null;
    }
    return Math.max(0, Math.round(started + 60 * limit - now / 1000));
}

/** A time left, such as 4:05 or 1:02:30. */
export function clock(seconds: number): string {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const rest = String(seconds % 60).padStart(2, "0");
    return hours ? `${hours}:${String(minutes).padStart(2, "0")}:${rest}` : `${minutes}:${rest}`;
}

/** The number of instances that can be had, from what was typed. */
export function clampInstances(typed: number): number {
    return Number.isFinite(typed) ? Math.min(MAX_INSTANCES, Math.max(1, Math.round(typed))) : DEFAULT_INSTANCES;
}

/** How the interface of an exercise talks to the app, as `exercises/kit.js` describes. */
export interface ExerciseKit {
    onShow(handler: (show: unknown) => void): void;
    act(message: unknown): Promise<unknown>;
    finish(): void;
    /** Has `text` read aloud; `number` tells the texts of the exercise apart. */
    readAloud(text: string, number?: number): void;
}

/** The interface of an exercise, ready to be mounted, as `exercises/kit.js` describes. */
export interface ExerciseInterface {
    mount(root: HTMLElement, exercise: ExerciseKit): (() => void) | void;
    /** kit.css, and the styles of the exercise if it has any. */
    sheets: CSSStyleSheet[];
}

/** The address of a file the interfaces of the exercises are made of, from the directory of the exercises. */
export function interfaceAddress(path: string): string {
    return `/checker/exercises/${path.split("/").map(encodeURIComponent).join("/")}`;
}

/** A stylesheet the interface of an exercise is given, or null if there is none to be had. */
async function sheetAt(path: string): Promise<CSSStyleSheet | null> {
    const response = await fetch(interfaceAddress(path));
    if (!response.ok) {
        return null;
    }
    const sheet = new CSSStyleSheet();
    sheet.replaceSync(await response.text());
    return sheet;
}

// the interfaces that were loaded, by exercise, which are loaded once
const interfaces = new Map<string, Promise<ExerciseInterface>>();

/** The interface of `exercise`: its module, with kit.css and its own styles. */
export function loadInterface(exercise: string): Promise<ExerciseInterface> {
    let loading = interfaces.get(exercise);
    if (!loading) {
        loading = Promise.all([
            import(/* @vite-ignore */ interfaceAddress(`${exercise}/ui/index.js`)) as Promise<Record<string, unknown>>,
            sheetAt("kit.css"),
            sheetAt(`${exercise}/ui/style.css`),
        ]).then(([module, kit, own]) => {
            if (typeof module.mount !== "function") {
                throw new Error(`The interface of ${exercise} has no mount.`);
            }
            return {
                mount: module.mount as ExerciseInterface["mount"],
                sheets: [kit, own].filter((sheet) => sheet !== null),
            };
        });
        // one that failed is loaded again when it is asked for next
        loading.catch(() => interfaces.delete(exercise));
        interfaces.set(exercise, loading);
    }
    return loading;
}

/**
 * The kit an interface talks to the app with: `act` has the backend act on
 * a message, and the interface is shown what the backend shows then before
 * the act resolves. Returns it with `show`, which shows the interface what
 * the backend showed first.
 */
export function exerciseKit(
    act: (message: unknown) => Promise<unknown>,
    finish: () => void,
    readAloud: (text: string, number: number) => void = () => undefined,
): { kit: ExerciseKit; show: (show: unknown) => void } {
    let handler: (show: unknown) => void = () => undefined;
    const kit: ExerciseKit = {
        onShow(given) {
            handler = given;
        },
        act: (message) =>
            act(message).then((shown) => {
                handler(shown);
                return shown;
            }),
        finish,
        readAloud(text, number = 0) {
            if (typeof text === "string" && text.trim()) {
                readAloud(text, Number.isSafeInteger(number) && number >= 0 ? number : 0);
            }
        },
    };
    return { kit, show: (shown) => handler(shown) };
}
