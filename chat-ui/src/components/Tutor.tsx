// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { type KeyboardEvent, type ReactNode, useCallback, useEffect, useRef, useState } from "react";
import Markdown from "react-markdown";

import { isAtEnd } from "../lib/chats";
import type { ProfileUsage } from "../lib/checker";
import { newId } from "../lib/ids";
import { canAsk } from "../lib/models";
import { endSession, type Learner, type PracticeSession, stepExercise } from "../lib/practice";
import type { WordLists } from "../lib/sets";
import type { Settings } from "../lib/settings";
import { allowPlaying, speakMark } from "../lib/speaking";
import type { BackgroundTask } from "../lib/tasks";
import {
    askTutor,
    closeTutorChat,
    deleteTutorChat,
    doingNow,
    emptyTurn,
    type EvaluationOffer,
    fetchTutorChat,
    fetchTutorChats,
    keepOffer,
    keptMessages,
    keptTurn,
    type ListedTutorChat,
    type Offer,
    type Practised,
    thinkingAbout,
    type TutorAsking,
    type TutorEvent,
    type TutorMessage,
    type TutorTurn,
    withEvent,
} from "../lib/tutor";
import type { UsageEntry } from "../lib/usage";
import { CheckedTextarea } from "./CheckedTextarea";
import { ExerciseView } from "./ExerciseView";

interface Props {
    asking: TutorAsking;
    /** Who practises, and who is asked to make and check the exercises. */
    learner: Learner;
    /** Whether Enter sends, and Shift+Enter starts a new line, rather than the other way round. */
    enterSends: boolean;
    onUsage: (used: ProfileUsage[]) => void;
    /** Counts what the exercises done in the chat used, as practice. */
    onPracticeUsage: (used: ProfileUsage[]) => void;
    onTask: (task: BackgroundTask) => void;
    /** Starts a session of practice of an exercise the tutor offered. */
    startOffer: (offer: Offer) => Promise<PracticeSession & { usage: ProfileUsage[] }>;
    /** Has a text of an exercise read aloud, which the exercise numbers `number`. */
    onReadAloud: (sessionId: string, exercise: string, number: number, text: string) => void;
    onOpenSettings: () => void;
    /** Whether each answer is read aloud once it has arrived, as in the chat, and what changes that. */
    speakReplies: boolean;
    onSpeakReplies: (speak: boolean) => void;
    /** Starts a mock exam the tutor offered, which runs in the tab of evaluations. */
    onStartEvaluation: (exam: EvaluationOffer) => void;
    /** Has an answer read aloud, by the chat and its place among what is said in it, as the chat's are. */
    onSpeak: (chatId: string, place: number, text: string) => void;
    /** Told each request to the server as it starts, with what it was in a few words, and each of its events. */
    onExchange: (label: string) => void;
    onTrace: (event: TutorEvent) => void;
    /** Told when a new chat is started. */
    onNewChat: () => void;
    /** What the sentences written to the tutor are checked by, as in the chat, and what changes it. */
    settings: Settings;
    onSettingsChange: (settings: Settings) => void;
    /** What the keywords for words in the questions stand for. */
    words: WordLists;
    /** Where the checks of the sentence being written are shown, if they are open. */
    checksSlot: HTMLElement | null;
    onCloseChecks: () => void;
    onEditQuestions: () => void;
    /** Counts what checking the sentences used. */
    onCheckingUsage: (entry: UsageEntry) => void;
}

/** What the chat shows: what the learner wrote, and each turn of the tutor as it grows. */
type Shown = { role: "user"; text: string } | { role: "tutor"; turn: TutorTurn };

/** Where an exercise the tutor offered has got to, by the turn and the place of the offer in it. */
type Doing =
    | { status: "starting" }
    | { status: "running"; sessionId: string }
    | { status: "finishing" }
    | { status: "done"; abandoned?: boolean };

/**
 * The tutor: a chat with a model that reasons, and that looks up what the
 * learner has done and offers exercises with its tools. While it answers,
 * what it is doing and what it is thinking about are shown. An exercise it
 * offers is done in the chat, and once it is over the tutor is told how it
 * went and goes on from there. What the learner wrote and what the tutor
 * answered are kept on the server, chat by chat, and the latest chat is
 * found again when the page is opened; what the tutor looked up is not, as
 * it is looked up again whenever it is needed.
 */
export function Tutor(
    {
        asking,
        learner,
        enterSends,
        onUsage,
        onPracticeUsage,
        onTask,
        startOffer,
        onReadAloud,
        onOpenSettings,
        speakReplies,
        onSpeakReplies,
        onStartEvaluation,
        onSpeak,
        onExchange,
        onTrace,
        onNewChat,
        settings,
        words,
        onSettingsChange,
        checksSlot,
        onCloseChecks,
        onEditQuestions,
        onCheckingUsage,
    }: Props,
) {
    // the chat as the model was told it, which is sent back as a whole
    const [messages, setMessages] = useState<TutorMessage[]>([]);
    // the id the chat is kept under, and the chats kept before
    const [chatId, setChatId] = useState(newId);
    const [chats, setChats] = useState<ListedTutorChat[]>([]);
    // whether the chat shown is closed, after which nothing more is said in it
    const [closed, setClosed] = useState(false);
    const [shown, setShown] = useState<Shown[]>([]);
    // the exercises offered that were started, by `offerKey`
    const [doing, setDoing] = useState<Record<string, Doing>>({});
    const [draft, setDraft] = useState("");
    const [error, setError] = useState<string | null>(null);
    const [busy, setBusy] = useState(false);
    const request = useRef<AbortController | null>(null);
    const listRef = useRef<HTMLDivElement>(null);
    const usable = canAsk(asking.model, asking.apiKey);
    // one exercise at a time, and none while the tutor is answering
    const occupied = busy || Object.values(doing).some((each) => each.status !== "done");

    useEffect(() => () => request.current?.abort(), []);
    // the latest chat is taken up where it was left
    useEffect(() => {
        fetchTutorChats().then(
            (listed) => {
                setChats(listed);
                if (listed[0]) {
                    void open(listed[0].id);
                }
            },
            () => undefined,
        );
        // only when the page is opened
    }, []);

    /** Shows a chat that was kept, with what the learner wrote and what the tutor answered. */
    async function open(id: string) {
        let chat;
        try {
            chat = await fetchTutorChat(id);
        } catch (failed) {
            setError(failed instanceof Error ? failed.message : String(failed));
            return;
        }
        request.current?.abort();
        setChatId(chat.id);
        setClosed(chat.closedAt !== null);
        setMessages(keptMessages(chat.messages));
        setShown(
            chat.messages.map(({ role, content, turn }) =>
                role === "user" ? { role: "user", text: content } : { role: "tutor", turn: keptTurn(content, turn) }
            ),
        );
        // the exercises offered are where they were left, one still running taken up again
        setDoing(Object.fromEntries(
            chat.messages.flatMap(({ turn }, index) =>
                (turn?.offers ?? []).flatMap((offer, place): [string, Doing][] =>
                    offer.session && offer.status
                        ? [[
                            offerKey(index, place),
                            offer.status === "running"
                                ? { status: "running", sessionId: offer.session }
                                : { status: "done", abandoned: offer.status === "abandoned" },
                        ]]
                        : []
                )
            ),
        ));
        setError(null);
        onNewChat();
    }
    // What the chat keeps in view as what is in it grows, such as an exercise
    // as it loads: its end, the top of the exercise under way, or nothing
    // once the learner has scrolled away from the end.
    const follow = useRef<"end" | string | null>("end");
    // when the learner last did something that scrolls, which tells their
    // scrolling from that done here
    const touched = useRef(0);
    const keepInView = useCallback(() => {
        const list = listRef.current;
        if (!list || list.clientHeight === 0 || follow.current === null) {
            return;
        }
        const exercise = follow.current === "end"
            ? null
            : list.querySelector<HTMLElement>(`[data-offer="${follow.current}"]`);
        const top = exercise
            ? exercise.getBoundingClientRect().top - list.getBoundingClientRect().top + list.scrollTop - EXERCISE_MARGIN
            : list.scrollHeight;
        list.scrollTop = top;
    }, []);
    // an exercise under way is followed from its top, and the end otherwise
    const running = Object.entries(doing).find(([, each]) => each.status === "starting" || each.status === "running");
    const runningKey = running?.[0] ?? null;
    useEffect(() => {
        follow.current = runningKey ?? "end";
        keepInView();
    }, [runningKey, keepInView]);
    useEffect(keepInView, [shown, error, keepInView]);
    // what grows by itself, such as an exercise that is loading, is followed as it grows
    useEffect(() => {
        const list = listRef.current;
        if (!list) {
            return;
        }
        const watching = new ResizeObserver(keepInView);
        Array.from(list.children).forEach((child) => watching.observe(child));
        return () => watching.disconnect();
    }, [shown, doing, error, keepInView]);

    /** Changes the turn of the tutor being answered, which is the last thing shown. */
    function changeTurn(change: (turn: TutorTurn) => TutorTurn) {
        setShown((current) => {
            const last = current.at(-1);
            return last?.role === "tutor"
                ? [...current.slice(0, -1), { role: "tutor", turn: change(last.turn) }]
                : current;
        });
    }

    /**
     * Has the tutor answer `asked`, with what the learner `wrote` shown above
     * its turn, or tells it how an exercise went if it was `practised`.
     * Resolves with whether it answered.
     */
    async function ask(asked: TutorMessage[], wrote: string | null, practised?: Practised): Promise<boolean> {
        const before = shown;
        // what is asked, and what is answered, is followed as it comes
        follow.current = "end";
        // The answer is read aloud only once it is there, by when the click
        // or the key that asked no longer counts for the browser.
        if (speakReplies) {
            allowPlaying();
        }
        // where the answer is among what is said in the chat, as it is kept
        const place = before.length + (wrote === null ? 0 : 1);
        let answer = "";
        const controller = new AbortController();
        request.current = controller;
        setShown([
            ...before,
            ...(wrote === null ? [] : [{ role: "user", text: wrote } as const]),
            { role: "tutor", turn: emptyTurn() },
        ]);
        setError(null);
        setBusy(true);
        onExchange(wrote ?? `How “${practised?.exercise}” went`);
        try {
            const done = await askTutor(
                asked,
                asking,
                (event) => {
                    onTrace(event);
                    if (event.type === "text") {
                        answer += event.text;
                    }
                    changeTurn((turn) => withEvent(turn, event));
                },
                controller.signal,
                practised,
                chatId,
            );
            onUsage(done.usage);
            setMessages([...asked, ...done.messages]);
            fetchTutorChats().then(setChats, () => undefined);
            if (speakReplies && answer.trim()) {
                onSpeak(chatId, place, answer);
            }
            return true;
        } catch (caught) {
            setShown(before);
            if (!controller.signal.aborted) {
                setError(caught instanceof Error ? caught.message : String(caught));
            }
            return false;
        } finally {
            setBusy(false);
        }
    }

    async function send() {
        const text = draft.trim();
        if (!text || occupied || !usable || closed) {
            return;
        }
        setDraft("");
        if (!(await ask([...messages, { role: "user", content: text }], text))) {
            // what was not answered goes back into the box, to be sent again
            setDraft(text);
        }
    }

    /** Starts the exercise the tutor offered at `place` in its answer at `index` of the chat. */
    function start(index: number, place: number, offer: Offer) {
        const key = offerKey(index, place);
        setDoing((current) => ({ ...current, [key]: { status: "starting" } }));
        setError(null);
        startOffer(offer).then(
            ({ usage, id: sessionId }) => {
                onPracticeUsage(usage);
                setDoing((current) => ({ ...current, [key]: { status: "running", sessionId } }));
                // so that the chat, taken up again, takes up the exercise too
                keepOffer(chatId, index, place, sessionId, "running").catch(() => undefined);
            },
            (failed: Error) => {
                setDoing(({ [key]: _, ...rest }) => rest);
                setError(failed.message);
            },
        );
    }

    /**
     * Finishes the exercise and its session, and tells the tutor how it went
     * once its log is written. One the learner `abandoned` before its end is
     * ended as it is, with what was done of it kept.
     */
    async function finish(index: number, place: number, sessionId: string, offer: Offer, abandoned = false) {
        const key = offerKey(index, place);
        setDoing((current) => ({ ...current, [key]: { status: "finishing" } }));
        const tasks: string[] = [];
        try {
            // ending a session finishes what was started of it
            const finished = abandoned ? null : await stepExercise(sessionId, offer.exercise, "finish", null, learner);
            const ended = await endSession(sessionId, abandoned ? "abandoned" : "finished", learner);
            for (const { usage, tasks: started } of finished ? [finished, ended] : [ended]) {
                onPracticeUsage(usage);
                started?.forEach((task) => {
                    onTask(task);
                    tasks.push(task.id);
                });
            }
        } catch (failed) {
            setDoing((current) => ({ ...current, [key]: { status: "running", sessionId } }));
            setError(failed instanceof Error ? failed.message : String(failed));
            return;
        }
        setDoing((current) => ({ ...current, [key]: { status: "done", abandoned } }));
        keepOffer(chatId, index, place, sessionId, abandoned ? "abandoned" : "done").catch(() => undefined);
        if (!offer.theory) {
            await ask(messages, null, { session: sessionId, exercise: offer.exercise, tasks });
        }
    }

    /**
     * Starts a new chat, which closes the one that was open: nothing more is
     * said in it, and what the tutor is to remember of it is decided in the
     * background.
     */
    function startOver() {
        request.current?.abort();
        const open = chats.filter((chat) => chat.closedAt === null).map((chat) => chat.id);
        for (const id of open) {
            closeTutorChat(id, asking).then((started) => started.forEach(onTask), () => undefined);
        }
        const now = Date.now() / 1000;
        setChats((current) => current.map((chat) => (open.includes(chat.id) ? { ...chat, closedAt: now } : chat)));
        setClosed(false);
        setChatId(newId());
        setMessages([]);
        setShown([]);
        setDoing({});
        setError(null);
        onNewChat();
    }

    function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
        if (event.key === "Enter" && event.shiftKey !== enterSends && !event.nativeEvent.isComposing) {
            event.preventDefault();
            void send();
        }
    }

    return (
        <section className="chat tutor">
            <header className="chat-header">
                <h2 className="tutor-title">Tutor</h2>
                <label className="check" title="Reads each answer aloud once it has arrived. The audio is kept.">
                    <input
                        type="checkbox"
                        checked={speakReplies}
                        onChange={(event) => onSpeakReplies(event.target.checked)}
                    />
                    Speak replies
                </label>
                {chats.length > 0 && (
                    <select
                        aria-label="Chats with the tutor"
                        value={chats.some((chat) => chat.id === chatId) ? chatId : ""}
                        onChange={(event) => void open(event.target.value)}
                        disabled={occupied}
                    >
                        {!chats.some((chat) => chat.id === chatId) && <option value="">This chat</option>}
                        {chats.map((chat) => (
                            <option key={chat.id} value={chat.id}>
                                {new Date(chat.updatedAt * 1000).toLocaleString(undefined, {
                                    dateStyle: "short",
                                    timeStyle: "short",
                                })} · {chat.first.slice(0, 40) || "…"}
                            </option>
                        ))}
                    </select>
                )}
                <button
                    onClick={() => {
                        if (window.confirm("Delete this chat with the tutor?")) {
                            void deleteTutorChat(chatId).then(() => {
                                setChats((current) => current.filter((chat) => chat.id !== chatId));
                                startOver();
                            });
                        }
                    }}
                    disabled={occupied || !chats.some((chat) => chat.id === chatId)}
                >
                    Delete
                </button>
                <button onClick={startOver} disabled={shown.length === 0 || occupied}>New chat</button>
            </header>
            <div
                className="messages"
                data-selectable
                ref={listRef}
                onWheel={() => (touched.current = Date.now())}
                onTouchMove={() => (touched.current = Date.now())}
                onPointerDown={(event) => {
                    // on the scroll bar, which is the list's own, not on what is in it
                    if (event.target === event.currentTarget) {
                        touched.current = Date.now();
                    }
                }}
                onKeyDown={(event) => {
                    // where the key was pressed, inside the shadow root of an exercise too
                    const origin = event.nativeEvent.composedPath()[0];
                    const writing = origin instanceof HTMLElement
                        && (origin.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(origin.tagName));
                    if (SCROLL_KEYS.has(event.key) && !writing) {
                        touched.current = Date.now();
                    }
                }}
                onScroll={(event) => {
                    if (Date.now() - touched.current > USER_SCROLL_MS) {
                        return;
                    }
                    const list = event.currentTarget;
                    // nothing is shown, and so nothing scrolled, while another activity is
                    if (list.clientHeight > 0) {
                        follow.current = isAtEnd(list.scrollHeight, list.scrollTop, list.clientHeight)
                            ? "end"
                            : null;
                    }
                }}
            >
                {shown.length === 0 && (
                    <div className="empty">
                        <h2>Your tutor</h2>
                        <p>
                            Ask what to work on next, or how you are doing. The tutor looks at your lessons, your
                            practice and your logs before it answers, and offers you exercises to do here.
                        </p>
                    </div>
                )}
                {shown.map((each, index) =>
                    each.role === "user"
                        ? <div key={index} className="message user">{each.text}</div>
                        : (
                            <TurnView
                                key={index}
                                turn={each.turn}
                                speakMark={speakMark(chatId, index)}
                                onSpeak={() => onSpeak(chatId, index, each.turn.text)}
                            >
                                {each.turn.offers.map((offer, place) => {
                                    const key = offerKey(index, place);
                                    const state = doing[key];
                                    return (
                                        <div key={key} className="tutor-exercise" data-offer={key}>
                                            <OfferCard
                                                offer={offer}
                                                state={state}
                                                disabled={occupied || !usable || closed}
                                                onStart={() => start(index, place, offer)}
                                                onEnd={() => {
                                                    if (
                                                        state?.status === "running"
                                                        && window.confirm(
                                                            "End this exercise now? What you did of it is kept.",
                                                        )
                                                    ) {
                                                        void finish(index, place, state.sessionId, offer, true);
                                                    }
                                                }}
                                            />
                                            {state?.status === "running" && (
                                                <div className="tutor-exercise-body">
                                                    <ExerciseView
                                                        sessionId={state.sessionId}
                                                        exercise={offer.exercise}
                                                        theory={offer.theory}
                                                        learner={learner}
                                                        onUsage={onPracticeUsage}
                                                        onFinish={() =>
                                                            void finish(index, place, state.sessionId, offer)}
                                                        onReadAloud={(text, number) =>
                                                            onReadAloud(state.sessionId, offer.exercise, number, text)}
                                                        // once what it made is shown, after the
                                                        // page has taken it in
                                                        onStarted={() => setTimeout(keepInView, 0)}
                                                    />
                                                </div>
                                            )}
                                        </div>
                                    );
                                })}
                                {each.turn.exams.map((exam, place) => (
                                    <ExamCard
                                        key={`exam:${place}`}
                                        exam={exam}
                                        disabled={occupied || !usable || closed}
                                        onStart={() => onStartEvaluation(exam)}
                                    />
                                ))}
                            </TurnView>
                        )
                )}
                {error && <div className="message error" role="alert">{error}</div>}
            </div>
            {closed && (
                <div className="notice">
                    This chat is over, and what the tutor is to remember of it has been kept.{" "}
                    <button className="link" onClick={startOver}>Start a new chat</button> to talk with the tutor.
                </div>
            )}
            {!usable && (
                <div className="notice">
                    Add your OpenRouter API key in <button className="link" onClick={onOpenSettings}>Settings</button>
                    {" "}
                    to talk with the tutor.
                </div>
            )}
            <form
                className="composer"
                onSubmit={(event) => {
                    event.preventDefault();
                    void send();
                }}
            >
                <CheckedTextarea
                    className="composer-input"
                    rows={2}
                    placeholder={closed ? "This chat is over" : "Ask your tutor"}
                    disabled={closed}
                    aria-label="Message to the tutor"
                    title={enterSends
                        ? "Enter sends the message, and Shift+Enter starts a new line"
                        : "Enter starts a new line, and Shift+Enter sends the message"}
                    value={draft}
                    onChange={setDraft}
                    onKeyDown={onKeyDown}
                    settings={settings}
                    onSettingsChange={onSettingsChange}
                    words={words}
                    onUsage={onCheckingUsage}
                    // counted under the chat with the tutor
                    usageId={`tutor:${chatId}`}
                    checksSlot={checksSlot}
                    onCloseChecks={onCloseChecks}
                    onEditQuestions={onEditQuestions}
                />
                <div className="composer-send">
                    {busy
                        ? <button type="button" onClick={() => request.current?.abort()}>Stop</button>
                        : (
                            <button
                                type="submit"
                                className="primary"
                                disabled={!draft.trim() || occupied || !usable || closed}
                            >
                                Send
                            </button>
                        )}
                </div>
            </form>
        </section>
    );
}

/** The keys that scroll the chat, outside a box being written in. */
const SCROLL_KEYS = new Set(["ArrowUp", "ArrowDown", "PageUp", "PageDown", "Home", "End", " "]);
/** How long after the learner turned the wheel, touched or pressed a key a scroll is taken for theirs. */
const USER_SCROLL_MS = 1000;
/** How far below the top of the chat an exercise under way is kept, in pixels. */
const EXERCISE_MARGIN = 12;

function offerKey(turn: number, place: number): string {
    return `${turn}:${place}`;
}

/**
 * A turn of the tutor: what it is doing while it answers, the tools it
 * called and what it thought, its answer, and under it the exercises it
 * offered, which are its `children`.
 */
function TurnView(
    { turn, speakMark, onSpeak, children }: {
        turn: TutorTurn;
        /** What tells its button that has it read aloud from the others. */
        speakMark: string;
        onSpeak: () => void;
        children: ReactNode;
    },
) {
    const doing = doingNow(turn);
    const about = doing === "Thinking" ? thinkingAbout(turn.thinking) : "";
    return (
        <div className="message assistant tutor-turn">
            {/* to the left of the answer, as in the chat; one that is still arriving is not read yet */}
            <button
                className="icon-button message-speak"
                data-speak={speakMark}
                onClick={onSpeak}
                disabled={!turn.text.trim() || turn.busy}
                title="Read aloud"
                aria-label="Read this answer aloud"
            >
                🔊
            </button>
            <div className="tutor-turn-body">
                {(turn.thinking || turn.steps.length > 0) && (
                    <details className="tutor-trace">
                        <summary>
                            {turn.busy ? "Working" : "Worked"}
                            {turn.steps.length > 0
                                && ` · ${turn.steps.length} ${turn.steps.length === 1 ? "step" : "steps"}`}
                        </summary>
                        {turn.steps.length > 0 && (
                            <ul className="tutor-steps">
                                {turn.steps.map((step) => (
                                    <li key={step.id} className={step.status}>
                                        <span aria-hidden="true">
                                            {step.status === "running" ? "…" : step.status === "done" ? "✓" : "✗"}
                                        </span>{" "}
                                        {step.doing}
                                    </li>
                                ))}
                            </ul>
                        )}
                        {turn.thinking && <p className="tutor-thinking">{turn.thinking}</p>}
                    </details>
                )}
                {turn.text && (
                    <div className="message-text">
                        <Markdown>{turn.text}</Markdown>
                    </div>
                )}
                {children}
                {doing && (
                    <div className="tutor-doing" role="status">
                        <span className="tutor-pulse" aria-hidden="true" />
                        <span className="tutor-doing-what">{doing}…</span>
                        {about && <span className="tutor-doing-about">{about}</span>}
                    </div>
                )}
            </div>
        </div>
    );
}

/**
 * An exercise the tutor offered, with what it was chosen with, and a button
 * that starts it here; once it is under way, one that ends it before it is
 * done.
 */
function OfferCard(
    { offer, state, disabled, onStart, onEnd }: {
        offer: Offer;
        state: Doing | undefined;
        disabled: boolean;
        onStart: () => void;
        onEnd: () => void;
    },
) {
    const said = [
        offer.practises_lesson === false
            ? ""
            : offer.lesson
            ? offer.lesson_title || offer.lesson
            : "Review of the lessons practised last",
        offer.theory || offer.instances === 1 ? "" : `${offer.instances} times`,
        offer.topic_titles?.length ? offer.topic_titles.join(", ") : "",
        ...Object.entries(offer.options).map(([name, value]) => `${name}: ${offer.labels?.[name] ?? value}`),
    ].filter(Boolean);
    return (
        <div className="tutor-offer">
            <div className="tutor-offer-about">
                <strong>{offer.title}</strong>
                <div className="tutor-offer-what">{said.join(" · ")}</div>
                {offer.focus && <div className="tutor-offer-focus">Aimed at: {offer.focus}</div>}
                {offer.words && offer.words.length > 0 && (
                    <div className="tutor-offer-what">With the words: {offer.words.join(", ")}</div>
                )}
            </div>
            {state === undefined && <button className="primary" disabled={disabled} onClick={onStart}>Start</button>}
            {state?.status === "starting" && <span className="tutor-offer-state">Preparing…</span>}
            {state?.status === "running" && (
                <button onClick={onEnd} title="End the exercise here, without doing the rest of it">
                    End exercise
                </button>
            )}
            {state?.status === "finishing" && <span className="tutor-offer-state">Finishing…</span>}
            {state?.status === "done" && (
                <span className="tutor-offer-state">{state.abandoned ? "Ended early" : "Done ✓"}</span>
            )}
        </div>
    );
}

/** A mock exam the tutor offered, with how it is set, and a button that starts it in the tab of evaluations. */
function ExamCard({ exam, disabled, onStart }: { exam: EvaluationOffer; disabled: boolean; onStart: () => void }) {
    const [started, setStarted] = useState(false);
    const hours = exam.length / 2;
    return (
        <div className="tutor-offer">
            <div className="tutor-offer-about">
                <strong>Mock exam: {exam.exam}</strong>
                <div className="tutor-offer-what">
                    {[
                        exam.level,
                        hours < 1 ? "half an hour" : `${hours} ${hours === 1 ? "hour" : "hours"}`,
                        exam.timed ? "timed" : "untimed",
                    ].join(" · ")}
                </div>
            </div>
            {started
                ? <span className="tutor-offer-state">Started in Evaluations</span>
                : (
                    <button
                        className="primary"
                        disabled={disabled}
                        onClick={() => {
                            setStarted(true);
                            onStart();
                        }}
                    >
                        Start
                    </button>
                )}
        </div>
    );
}
