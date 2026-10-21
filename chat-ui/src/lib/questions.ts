// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { newId } from "./ids";
/** One of the answers a question can be given. */
export interface QuestionOption {
    /** What the answer is called, such as "none". */
    label: string;
    /** When the answer applies. */
    description: string;
}

/** A question asked about every sentence that is finished in the chat. */
export interface ProfileQuestion {
    /** Tells the question from the others, and its answer from theirs. Never shown. */
    id: string;
    title: string;
    /**
     * A choice is answered with one of the options; a score with a place on
     * the scale they form. Either way they are listed from the worst to the best.
     */
    kind: "choice" | "score";
    /** What the model is asked. */
    instructions: string;
    options: QuestionOption[];
    /** Whether the question is asked at present. */
    enabled: boolean;
}

/** The answer to one question, as the checker server sends it. */
export interface ProfileAnswer {
    kind: "choice" | "score";
    /** The label of the option picked, for a choice. */
    choice: string | null;
    /** The place on the scale, for a score, counted from 0. It can fall between two levels. */
    score: number | null;
    max_score: number | null;
    /** How sure the model is, from 0 to 1. */
    confidence: number | null;
}

/** Questions in the form the checker server, and the model behind it, take them. */
export type RequestQuestions = Record<
    string,
    { type: "choice" | "score"; instructions: string; criteria: Record<string, string> | string[] }
>;

export function defaultQuestions(): ProfileQuestion[] {
    return [
        {
            id: "grammar_errors",
            title: "Grammar errors",
            kind: "choice",
            instructions: "How many grammar errors does the sentence have? Judge it by the rules of {{language}}. "
                + "For each noun phrase, find its role in the sentence (subject, direct object, "
                + "indirect object, object of a preposition) and check that its articles, adjectives and pronouns "
                + "have the case, gender and number that the role and the noun need. Also check the form of each "
                + "verb and its agreement with its subject, word order, tense, and missing or extra words. Do not "
                + "count spelling or punctuation.",
            // from the worst to the best, so that the bar is full when there are none
            options: [
                { label: "several", description: "The sentence has two or more grammar errors." },
                {
                    label: "one",
                    description: "Exactly one word has the wrong form, such as an article in the wrong case, or is "
                        + "missing, extra or out of place.",
                },
                {
                    label: "none",
                    description: "Every word has the right form for its role, and the word order is right.",
                },
            ],
            enabled: true,
        },
        {
            id: "clarity",
            title: "Clarity",
            kind: "score",
            instructions: "How clear is the sentence? Consider only whether a reader can tell what the writer "
                + "means, not whether it is correct.",
            options: [
                { label: "Unclear", description: "It is not possible to tell what is meant." },
                { label: "Hard to follow", description: "The meaning can only be guessed." },
                { label: "Mostly clear", description: "The meaning comes across with some effort." },
                { label: "Clear", description: "The meaning is plain on first reading." },
            ],
            enabled: true,
        },
    ];
}

export function newQuestion(): ProfileQuestion {
    return {
        id: `question_${newId().slice(0, 8)}`,
        title: "New question",
        kind: "choice",
        instructions: "",
        options: [{ label: "yes", description: "" }, { label: "no", description: "" }],
        enabled: true,
    };
}

/** Whether something read from storage is a question. */
export function isQuestion(value: unknown): value is ProfileQuestion {
    if (typeof value !== "object" || value === null) {
        return false;
    }
    const question = value as Partial<ProfileQuestion>;
    return typeof question.id === "string" && question.id !== ""
        && typeof question.title === "string"
        && (question.kind === "choice" || question.kind === "score")
        && typeof question.instructions === "string"
        && typeof question.enabled === "boolean"
        && Array.isArray(question.options)
        && question.options.every((option) =>
            typeof option === "object" && option !== null
            && typeof option.label === "string" && typeof option.description === "string"
        );
}

/**
 * Whether the question can be asked: it says what to ask, and offers at least
 * two options with a name each, which no other option of it has.
 */
export function isAskable(question: ProfileQuestion): boolean {
    const labels = question.options.map((option) => option.label.trim());
    return question.instructions.trim() !== ""
        && labels.length >= 2
        && labels.every((label) => label !== "")
        && new Set(labels).size === labels.length;
}

/** The questions to ask: those that are enabled and can be asked. */
export function askedQuestions(questions: ProfileQuestion[]): ProfileQuestion[] {
    return questions.filter((question) => question.enabled && isAskable(question));
}

/**
 * The questions to ask, in the form the checker server takes them, with
 * `fill` done to what they ask and to what each option means, such as
 * filling in the language being learned.
 */
export function requestQuestions(
    questions: ProfileQuestion[],
    fill: (text: string) => string = (text) => text,
): RequestQuestions {
    const request: RequestQuestions = {};
    for (const question of askedQuestions(questions)) {
        const options = question.options.map((option) => ({
            label: option.label.trim(),
            description: fill(option.description).trim(),
        }));
        request[question.id] = {
            type: question.kind,
            instructions: fill(question.instructions).trim(),
            criteria: question.kind === "choice"
                ? Object.fromEntries(options.map((option) => [option.label, option.description || option.label]))
                : options.map((option) => option.description ? `${option.label}: ${option.description}` : option.label),
        };
    }
    return request;
}

/** An answer in words, such as "none" or "Mostly clear (2.4 of 3)". */
export function describeAnswer(question: ProfileQuestion, answer: ProfileAnswer): string {
    if (answer.kind === "choice" || answer.score === null) {
        return answer.choice ?? "No answer";
    }
    const highest = answer.max_score ?? question.options.length - 1;
    const level = question.options[Math.round(answer.score)]?.label.trim();
    const place = `${answer.score.toFixed(1)} of ${highest}`;
    return level ? `${level} (${place})` : place;
}

/**
 * How good an answer is, from 0 to 1, which is how full its bar is drawn. A
 * score is as good as it is far up its scale. A choice is as good as the
 * option picked is far down the list, as options are listed from the worst
 * to the best. Null if the answer cannot be placed.
 */
export function answerFraction(question: ProfileQuestion, answer: ProfileAnswer): number | null {
    if (answer.kind === "score") {
        if (answer.score === null || !answer.max_score) {
            return null;
        }
        return Math.min(1, Math.max(0, answer.score / answer.max_score));
    }
    const place = question.options.findIndex((option) => option.label.trim() === answer.choice);
    return place < 0 || question.options.length < 2 ? null : place / (question.options.length - 1);
}

/** How an answer to a choice is drawn: so many stars, of which so many are filled. */
export interface Stars {
    stars: number;
    filled: number;
}

/** The most stars drawn, and the steps a star can be cut into, coarsest first; a choice of more options has a bar. */
const MOST_STARS = 5;
const STEPS_PER_STAR = [1, 2, 4];

/**
 * The stars an answer to a choice is drawn with, or null for a score, or a
 * choice that cannot be placed or has too many options. Each option is a
 * step of a whole, half or quarter star, the coarsest that lets the options
 * fit in five stars; there are as few stars as the steps need, and the best
 * option fills them all, so that the worst still fills a step.
 */
export function answerStars(question: ProfileQuestion, answer: ProfileAnswer): Stars | null {
    const count = question.options.length;
    const place = question.options.findIndex((option) => option.label.trim() === answer.choice);
    const steps = STEPS_PER_STAR.find((each) => count <= MOST_STARS * each);
    if (answer.kind !== "choice" || place < 0 || count < 2 || steps === undefined) {
        return null;
    }
    const stars = Math.ceil(count / steps);
    return { stars, filled: stars - (count - 1 - place) / steps };
}

// What earlier versions asked of the grammar question, which missed errors
// of case such as "Ich habe ein Hund", or named the language only as the
// checker server gave it.
const OLD_GRAMMAR_INSTRUCTIONS = [
    "How many grammar errors does the sentence have? Judge it by the rules of the language it is written in. Count "
    + "mistakes in grammar only, such as word order, agreement, case, tense and missing or extra words. Do not count "
    + "spelling or punctuation.",
    "How many grammar errors does the sentence have? Judge it by the rules of the `language`, if one is given, and "
    + "else of the language it is written in. For each noun phrase, find its role in the sentence (subject, direct "
    + "object, indirect object, object of a preposition) and check that its articles, adjectives and pronouns have "
    + "the case, gender and number that the role and the noun need. Also check the form of each verb and its "
    + "agreement with its subject, word order, tense, and missing or extra words. Do not count spelling or "
    + "punctuation.",
];

/**
 * Questions as they are now asked, made from ones stored by an earlier
 * version: the grammar question used to list its options from the best to
 * the worst, which would draw its bar the wrong way round, and one that was
 * never edited is given the instructions and options asked now.
 */
export function upToDateQuestions(questions: ProfileQuestion[]): ProfileQuestion[] {
    return questions.map((question) => {
        if (question.id !== "grammar_errors") {
            return question;
        }
        if (OLD_GRAMMAR_INSTRUCTIONS.includes(question.instructions)) {
            const [grammar] = defaultQuestions();
            return { ...question, instructions: grammar.instructions, options: grammar.options };
        }
        const labels = question.options.map((option) => option.label);
        const outdated = labels.join() === "none,one,several";
        return outdated ? { ...question, options: [...question.options].reverse() } : question;
    });
}
