// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import type { ProfileUsage } from "./checker";
import { filled, type InterfaceLanguage, interfaceLanguage, plural, t, translated } from "./i18n";
import { announceLogged } from "./logs";
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
    /** Whether it is done once, with no time limit, such as correcting a text. */
    once?: boolean;
    /** Whether it practises a lesson; one that does not, such as correcting a text, needs none. */
    lesson?: boolean;
    /** Whether it is about the topics chosen; one that is about neither them nor a lesson is done on its own. */
    topics?: boolean;
    /** Whether it is listed before every other, such as reviewing the Anki cards. */
    first?: boolean;
    /** Whether the tutor offers it with a tool of its own. */
    own_tool?: boolean;
    /** Whether its interface has an icon, `ID/ui/icon.svg`, which it is shown with in place of its description. */
    icon?: boolean;
    /** The shape of one instance of what it makes, kept so that it can be done again; null if it makes nothing. */
    instance?: Record<string, unknown> | null;
    /** Its options, by their names. */
    options: Record<string, ExerciseOption>;
    /**
     * Whether the sentences written in its text boxes are checked by the
     * sentence check model: always, never, or as the learner chooses in the
     * bar of the session.
     */
    sentence_checks?: "always" | "optional" | "never";
    /** What it shows, in each language the interface is written in but English, by what it says in English. */
    messages?: ExerciseMessages;
}

/**
 * What an exercise shows, its manifest and its interface, in each language
 * the interface is written in but English, by what it says in English.
 */
export type ExerciseMessages = Partial<Record<InterfaceLanguage, Record<string, string>>>;

/** What each exercise shows in the other languages, by its id, as the server last listed them. */
const exerciseMessages = new Map<string, ExerciseMessages>();
/** Whether the sentences are checked in each exercise, by its id, as the server last listed them. */
const exerciseSentenceChecks = new Map<string, ExerciseInfo["sentence_checks"]>();

/**
 * Whether the sentences written in the exercise `id` are checked, as its
 * manifest says, or, if it leaves it to the learner, as they last chose in
 * `chosen`, off at first. Those of one not listed yet are not.
 */
export function sentencesChecked(id: string, chosen: Record<string, boolean>): boolean {
    switch (exerciseSentenceChecks.get(id)) {
        case "always":
            return true;
        case "optional":
            return chosen[id] ?? false;
        default:
            return false;
    }
}

/**
 * `text` of the exercise `id` in the language of the interface, with each
 * `{name}` in it given its value: as the exercise has it, or else as the app
 * has it, or else as it is.
 */
export function exerciseText(id: string, text: string, values: Record<string, string | number> = {}): string {
    const language = interfaceLanguage();
    const own = language === "English" ? undefined : exerciseMessages.get(id)?.[language]?.[text];
    return own === undefined ? translated(text, values) : filled(own, values);
}

/** An exercise as it is shown: its title, description and options in the language of the interface. */
function shownExercise(exercise: ExerciseInfo): ExerciseInfo {
    const text = (said: string) => exerciseText(exercise.id, said);
    return {
        ...exercise,
        title: text(exercise.title),
        description: text(exercise.description),
        options: Object.fromEntries(
            Object.entries(exercise.options ?? {}).map(([name, option]) => [
                name,
                "choices" in option
                    ? {
                        ...option,
                        label: text(option.label),
                        choices: Object.fromEntries(
                            Object.entries(option.choices).map(([value, label]) => [value, text(label)]),
                        ),
                    }
                    : { ...option, label: text(option.label) },
            ]),
        ),
    };
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
    /** How many of the instances it made, or does again, are kept, which it can be done again with. */
    kept?: number;
    /** Whether it does again what an exercise of another session made. */
    replays?: boolean;
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
    /**
     * Whether it was left before anything was done in it, and is kept only
     * for what its exercises made, which can be done again: it is listed
     * among the exercises done, and nowhere else.
     */
    hidden?: boolean;
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
export const DEFAULT_INSTANCES = 1;
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
        throw new Error(t("The server cannot be reached."));
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

/** Has what the exercises show in the other languages known, if they were not listed yet. */
export async function knowExercises(): Promise<void> {
    if (exerciseMessages.size === 0) {
        await fetchExercises();
    }
}

/** The exercises there are, in the language of the interface as it is now. */
export async function fetchExercises(): Promise<ExerciseInfo[]> {
    const { exercises } = await call<{ exercises: ExerciseInfo[] }>("/exercises");
    exercises.forEach((exercise) => {
        exerciseMessages.set(exercise.id, exercise.messages ?? {});
        exerciseSentenceChecks.set(exercise.id, exercise.sentence_checks);
    });
    return exercises.map(shownExercise);
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
    guidance: Record<string, string> = {},
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
        // what each exercise is to aim at, as the tutor steers it
        guidance,
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
    const stepped = call<{ show: unknown; usage: ProfileUsage[]; tasks?: BackgroundTask[] }>(
        `/sessions/${encodeURIComponent(sessionId)}/exercises/${encodeURIComponent(exercise)}/${op}`,
        posting({ message }, learner),
    );
    // an exercise that writes its log itself has it as soon as it is finished
    return op === "finish" ? stepped.then((done) => (announceLogged(), done)) : stepped;
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
    /** Each answer of an instance of several, such as the questions on a text, as it was graded; empty for one. */
    parts?: GradePart[];
    /** What the learner had to go on, such as the text the questions were on; empty if nothing. */
    about?: string;
}

/** An answer of an instance of several, as it was graded. */
export interface GradePart {
    result: Grade["result"];
    task: string;
    answer: string;
    correction: string;
    note: string;
}

/**
 * What a session is of: its lesson, by its title as `lessonTitle` gives
 * it, the lessons it reviews, or, for one of none, such as a review of the
 * Anki cards, its exercises, by their titles as `exerciseTitle` gives them.
 */
export function sessionTitleOf(
    session: PracticeSession,
    lessonTitle: (id: string) => string,
    exerciseTitle: (id: string) => string,
): string {
    if (session.lesson) {
        return lessonTitle(session.lesson);
    }
    const count = session.lessons?.length ?? 0;
    if (count === 0) {
        return Object.keys(session.exercises).map(exerciseTitle).join(", ");
    }
    return plural(count, "Review of {count} lesson", "Review of {count} lessons");
}

/** Every session there was, the latest first, but those that are hidden, as only the exercises done list them. */
export async function fetchPracticeSessions(): Promise<PracticeSession[]> {
    return (await fetchSessions()).filter((session) => !session.hidden);
}

/** Every session there was, the latest first, those that are hidden too. */
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
    return t("{count} answered", { count: session.progress[exercise]?.answered ?? 0 });
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

/**
 * Starts a session that does an exercise of a session again exactly as it
 * was, with what it made kept, or, if `fresh`, with the same settings and
 * what it does made anew, and resolves with the session.
 */
export function replayExercise(
    sessionId: string,
    exercise: string,
    learner: Learner,
    fresh = false,
): Promise<PracticeSession> {
    return call(
        `/sessions/${encodeURIComponent(sessionId)}/exercises/${encodeURIComponent(exercise)}/replay`,
        posting({ fresh }, learner),
    );
}

/** An exercise of a session kept among the favourites, to be done again. */
export interface Favourite {
    session_id: string;
    exercise: string;
    /** When it was added, in seconds since the epoch. */
    added_at: number;
}

/** The favourite exercises, the latest added first. */
export async function fetchFavourites(): Promise<Favourite[]> {
    const { favourites } = await call<{ favourites: Favourite[] }>("/favourites");
    return favourites;
}

/**
 * Keeps an exercise of a session among the favourites, or, if not `kept`,
 * takes it out of them, and resolves with the favourites as they are then.
 */
export async function setFavourite(sessionId: string, exercise: string, kept: boolean): Promise<Favourite[]> {
    const { favourites } = await call<{ favourites: Favourite[] }>(
        `/favourites/${encodeURIComponent(sessionId)}/${encodeURIComponent(exercise)}`,
        { method: kept ? "PUT" : "DELETE" },
    );
    return favourites;
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
    /** The address of a file of the media of the learner's Anki collection, such as a picture of a card. */
    ankiMedia(name: string): Promise<string>;
    /** The language the app is shown in, by its English name, which the interface is shown in too. */
    language: InterfaceLanguage;
    /** `text`, what the interface shows, in that language, with each `{name}` in it given its value. */
    t(text: string, values?: Record<string, string | number>): string;
}

/** The interface of an exercise, ready to be mounted, as `exercises/kit.js` describes. */
export interface ExerciseInterface {
    mount(root: HTMLElement, exercise: ExerciseKit): (() => void) | void;
    /** kit.css, and the styles of the exercise if it has any. */
    sheets: CSSStyleSheet[];
}

/** The address of a file the interfaces of the exercises are made of, from the directory of the exercises. */
export function interfaceAddress(path: string): string {
    return `${import.meta.env.BASE_URL}checker/exercises/${path.split("/").map(encodeURIComponent).join("/")}`;
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
    ankiMedia: (name: string) => Promise<string> = () => Promise.reject(new Error(t("There is no Anki here."))),
    exercise = "",
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
        ankiMedia: (name) =>
            typeof name === "string" && name ? ankiMedia(name) : Promise.reject(new Error("A file has a name.")),
        language: interfaceLanguage(),
        t: (text, values = {}) => (typeof text === "string" ? exerciseText(exercise, text, values) : String(text)),
    };
    return { kit, show: (shown) => handler(shown) };
}
