// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { describe, expect, it } from "vitest";

import { onOpenRouter } from "./models";
import {
    answeredOf,
    choosingOf,
    clampInstances,
    clock,
    DEFAULT_INSTANCES,
    defaultOptions,
    exerciseKit,
    interfaceAddress,
    lessonsRead,
    lessonsToReview,
    MAX_INSTANCES,
    optionsOf,
    type PracticeSession,
    practiceUsage,
    resumeAt,
    scoreOf,
    secondsLeft,
} from "./practice";
import { defaultSettings } from "./settings";

describe("clampInstances", () => {
    it("keeps the instances between one and the most there may be, in whole numbers", () => {
        expect(clampInstances(7)).toBe(7);
        expect(clampInstances(2.6)).toBe(3);
        expect(clampInstances(0)).toBe(1);
        expect(clampInstances(500)).toBe(MAX_INSTANCES);
        expect(clampInstances(NaN)).toBe(DEFAULT_INSTANCES);
    });
});

describe("practiceUsage", () => {
    it("counts what an exercise used under practice", () => {
        const used = { id: "gen-1", model: "some/model", input_tokens: 10, output_tokens: 4, cost: 0.002 };

        expect(practiceUsage(used, 5)).toEqual({
            id: "gen-1",
            at: 5,
            category: "practice",
            chatId: "practice",
            model: "some/model",
            promptTokens: 10,
            completionTokens: 4,
            cost: 0.002,
        });
    });
});

describe("choosingOf", () => {
    const settings = {
        ...defaultSettings(),
        exerciseMixTopics: true,
        embeddingModel: onOpenRouter("some/embedder"),
    };

    it("sends the words of a set, with how the topics and words are chosen", () => {
        expect(choosingOf(settings, "set-1", ["der Arzt", "krank"])).toEqual({
            mix_topics: true,
            vocabulary: "set",
            words: ["der Arzt", "krank"],
            topic_words: true,
            embedding_model: "some/embedder",
        });
    });

    it("leaves the words to the server for the whole vocabulary, or for none", () => {
        expect(choosingOf(settings, "all", null)).toMatchObject({ vocabulary: "all", words: [] });
        expect(choosingOf(settings, "none", null)).toMatchObject({ vocabulary: "none", words: [] });
    });

    it("names an embedding model at an address with the address", () => {
        const atHome = { model: "bge", url: "http://127.0.0.1:8000/v1", key: "" };

        expect(choosingOf({ ...settings, embeddingModel: atHome }, "all", null).embedding_model).toEqual(atHome);
    });

    it("takes a set that is gone for the whole vocabulary", () => {
        expect(choosingOf(settings, "deleted-set", null)).toMatchObject({ vocabulary: "all", words: [] });
    });
});

describe("resuming a session", () => {
    function session(statuses: Record<string, "pending" | "started" | "finished">): PracticeSession {
        return {
            id: "s",
            language: "German",
            lesson: "trennbare-verben",
            lessons: [],
            topics: [],
            started_at: 0,
            finished_at: null,
            status: "running",
            words: null,
            mix_topics: false,
            kind: "practice",
            exercises: Object.fromEntries(Object.keys(statuses).map((id) => [id, 5])),
            options: {},
            minutes: {},
            progress: Object.fromEntries(
                Object.entries(statuses).map(([id, status]) => {
                    const done = status === "pending" ? 0 : 1;
                    return [id, {
                        status,
                        answered: 2 * done,
                        results: { right: done, partial: done, wrong: 0 },
                        started_at: null,
                        scores: null,
                    }];
                }),
            ),
        };
    }

    it("is taken up at the first exercise that is not finished", () => {
        expect(resumeAt(session({ cloze: "finished", translation: "started" }))).toBe(1);
        expect(resumeAt(session({ cloze: "started", translation: "pending" }))).toBe(0);
        expect(resumeAt(session({ cloze: "finished", translation: "pending" }))).toBe(1);
    });

    it("is taken up at its last exercise when all are finished", () => {
        expect(resumeAt(session({ cloze: "finished", translation: "finished" }))).toBe(1);
    });

    it("says how many answers of each exercise were logged", () => {
        const one = session({ cloze: "started", translation: "pending" });

        expect([answeredOf(one, "cloze"), answeredOf(one, "translation")]).toEqual(["2 answered", "0 answered"]);
    });

    it("says nothing of answers for theory, which has no instances", () => {
        const one = session({ cloze: "started", translation: "pending" });
        one.exercises.translation = 0;

        expect(answeredOf(one, "translation")).toBe("");
    });

    it("scores what was answered, counting an answer almost right as half", () => {
        const one = session({ cloze: "finished", translation: "started" });
        one.progress.translation.results = { right: 0, partial: 0, wrong: 2 };

        expect(scoreOf(one)).toEqual({ right: 1, partial: 1, wrong: 2, total: 10, percent: 38 });
    });

    it("has no score while nothing was answered", () => {
        expect(scoreOf(session({ cloze: "pending" })).percent).toBeNull();
    });

    it("makes a lesson done once its theory is read to the end, in the language learned", () => {
        const read = session({ theory: "finished", cloze: "pending" });
        const begun = { ...session({ theory: "started" }), lesson: "dativ" };
        const other = { ...session({ theory: "finished" }), lesson: "artikel", language: "French" };

        expect(lessonsRead([read, begun, other], ["theory"], "German")).toEqual(new Set(["trennbare-verben"]));
    });
});

describe("interfaceAddress", () => {
    it("gives the files of an interface from the checker, each part of the path escaped", () => {
        expect(interfaceAddress("cloze/ui/index.js")).toBe("/lansi/checker/exercises/cloze/ui/index.js");
        expect(interfaceAddress("kit.css")).toBe("/lansi/checker/exercises/kit.css");
        expect(interfaceAddress("a b/ui/x.css")).toBe("/lansi/checker/exercises/a%20b/ui/x.css");
    });
});

describe("exerciseKit", () => {
    it("shows the interface what the backend shows, before the act resolves", async () => {
        const seen: unknown[] = [];
        const { kit, show } = exerciseKit(async (message) => ({ after: message }), () => undefined);
        kit.onShow((shown) => seen.push(shown));

        show({ first: true });
        const shown = await kit.act("auf");

        expect(seen).toEqual([{ first: true }, { after: "auf" }]);
        expect(shown).toEqual({ after: "auf" });
    });

    it("shows nothing when the backend could not act, and says why", async () => {
        const seen: unknown[] = [];
        const { kit } = exerciseKit(() => Promise.reject(new Error("no key")), () => undefined);
        kit.onShow((shown) => seen.push(shown));

        await expect(kit.act("auf")).rejects.toThrow("no key");
        expect(seen).toEqual([]);
    });

    it("tells the app when the learner is done", () => {
        let finished = 0;
        exerciseKit(async () => null, () => finished++).kit.finish();

        expect(finished).toBe(1);
    });

    it("has a text read aloud with its number, and nothing read that is not text", () => {
        const read: [string, number][] = [];
        const { kit } = exerciseKit(async () => null, () => undefined, (text, number) => read.push([text, number]));

        kit.readAloud("Anna steht auf.", 2);
        kit.readAloud("Ben kommt mit.");
        kit.readAloud("  ");
        kit.readAloud("Wer?", -1);

        expect(read).toEqual([["Anna steht auf.", 2], ["Ben kommt mit.", 0], ["Wer?", 0]]);
    });
});

describe("the options of an exercise", () => {
    const stories = {
        id: "stories",
        title: "Stories",
        description: "",
        theory: false,
        options: {
            then: { label: "Then", choices: { questions: "Answer questions", retell: "Retell it" } },
            questions: { label: "Questions", min: 1, max: 8, default: 3 },
        },
    };

    it("are the first choice of each, or its default, unless set otherwise", () => {
        expect(defaultOptions(stories)).toEqual({ then: "questions", questions: 3 });
        expect(defaultOptions({ ...stories, options: {} })).toEqual({});
    });

    it("are as they were remembered where they can be", () => {
        expect(optionsOf(stories, { then: "retell", questions: 5 })).toEqual({ then: "retell", questions: 5 });
        expect(optionsOf(stories, { then: "sing", questions: "5" })).toEqual({ then: "questions", questions: 3 });
    });

    it("bring a number remembered within the bounds of its option", () => {
        expect(optionsOf(stories, { questions: 12 })).toMatchObject({ questions: 8 });
        expect(optionsOf(stories, { questions: 2.6 })).toMatchObject({ questions: 3 });
    });
});

describe("lessonsToReview", () => {
    function of(lesson: string, language = "German"): PracticeSession {
        return {
            id: lesson,
            language,
            lesson,
            lessons: [],
            topics: [],
            started_at: 0,
            finished_at: null,
            status: "finished",
            words: null,
            mix_topics: false,
            kind: "practice",
            exercises: {},
            options: {},
            minutes: {},
            progress: {},
        };
    }
    const taught = Array.from({ length: 12 }, (_, number) => ({
        id: `l${number}`,
        level: "A1",
        title: `Lesson ${number}`,
        points: [],
        more_info: "",
    }));

    it("is the lessons practised last, in the order they are taught in", () => {
        // practised from the last lesson to the first, so the latest session is that of the first
        const sessions = taught.map((lesson) => of(lesson.id));
        sessions.unshift(of("l11"), { ...of(""), lessons: ["l3"] }, of("l5", "French"));

        expect(lessonsToReview(sessions, taught, "German")).toEqual(
            ["l0", "l1", "l2", "l3", "l4", "l5", "l6", "l7", "l8", "l11"],
        );
    });
});

describe("secondsLeft", () => {
    function timed(minutes: number, started: number | null): PracticeSession {
        return {
            id: "s",
            language: "German",
            lesson: "",
            lessons: [],
            topics: [],
            started_at: 0,
            finished_at: null,
            status: "running",
            words: null,
            mix_topics: false,
            kind: "practice",
            exercises: { cloze: 5 },
            options: {},
            minutes: { cloze: minutes },
            progress: {
                cloze: {
                    status: "started",
                    answered: 0,
                    results: { right: 0, partial: 0, wrong: 0 },
                    started_at: started,
                    scores: null,
                },
            },
        };
    }

    it("counts down from when the exercise was first shown", () => {
        expect(secondsLeft(timed(2, 100), "cloze", 130_000)).toBe(90);
        expect(secondsLeft(timed(2, 100), "cloze", 500_000)).toBe(0);
    });

    it("is none without a limit, or before the exercise was shown", () => {
        expect(secondsLeft(timed(0, 100), "cloze", 130_000)).toBeNull();
        expect(secondsLeft(timed(2, null), "cloze", 130_000)).toBeNull();
    });
});

describe("clock", () => {
    it("says minutes and seconds, and hours when there are any", () => {
        expect(clock(65)).toBe("1:05");
        expect(clock(3750)).toBe("1:02:30");
    });
});
