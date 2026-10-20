// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { orModel } from "./lib/models";

import { BookList } from "./components/BookList";
import { BookReader } from "./components/BookReader";
import { Chat } from "./components/Chat";
import { ChatList } from "./components/ChatList";
import { Evaluations } from "./components/Evaluations";
import { Icon } from "./components/Icon";
import { Inspector } from "./components/Inspector";
import { LogsPanel } from "./components/LogsPanel";
import { MemoryList } from "./components/MemoryList";
import { Practice } from "./components/Practice";
import { SelectionTools } from "./components/SelectionTools";
import { SetEditor } from "./components/SetEditor";
import { SettingsPanel, type SettingsTab } from "./components/SettingsPanel";
import { SidePanel } from "./components/SidePanel";
import { SpeechPlayer } from "./components/SpeechPlayer";
import { SubChat } from "./components/SubChat";
import { TaskSign } from "./components/TaskSign";
import { TextEditor } from "./components/TextEditor";
import { TextList } from "./components/TextList";
import { Tutor } from "./components/Tutor";
import { UsagePanel } from "./components/UsagePanel";
import { VocabularyList } from "./components/VocabularyList";
import { WordList } from "./components/WordList";
import { WritingChecks } from "./components/WritingChecks";
import { type AnkiState, fetchAnkiState, fetchKnownWords } from "./lib/anki";
import { useAnkiImport } from "./lib/ankiImport";
import { addBook, changeReading, deleteBook, fetchBooks, type ListedBook, loadReading } from "./lib/books";
import {
    activeChat,
    type ChatStore,
    chatsToTell,
    deleteChat,
    listedChats,
    putChat,
    removeChat,
    selectChat,
    startChat,
    type StoredChat,
    storeOf,
    updateChat,
} from "./lib/chats";
import type { ProfileUsage } from "./lib/checker";
import { type Evaluation, evaluationUsage, startEvaluation, USAGE_ID as EVALUATION_USAGE_ID } from "./lib/evaluations";
import { newId } from "./lib/ids";
import { begun, EMPTY_TRACE, type Trace, traced } from "./lib/inspect";
import { type Activity, loadLayout, type Panel, saveLayout } from "./lib/layout";
import type { ChatMessage } from "./lib/openrouter";
import { fetchGenerationUsage } from "./lib/openrouter";
import { choosingOf, type Learner, practiceUsage, startSession, USAGE_ID as PRACTICE_USAGE_ID } from "./lib/practice";
import { logOut } from "./lib/session";
import { deleteSet, fetchSets, membersOf, newSet, saveSet, wordLists, type WordSet } from "./lib/sets";
import { applyAppearance, exerciseVocabularyOf, saveSettings, type Settings } from "./lib/settings";
import {
    bookSource,
    exerciseSource,
    messageSource,
    speechInstructions,
    type SpeechSource,
    type Voice,
} from "./lib/speaking";
import { type BackgroundTask, fetchTasks, TASKS_INTERVAL_MS, withTask } from "./lib/tasks";
import { deleteText, fetchTexts, saveText, type Text } from "./lib/texts";
import type { Asking, Translated } from "./lib/translate";
import { type EvaluationOffer, type Offer, type TutorAsking, USAGE_ID as TUTOR_USAGE_ID } from "./lib/tutor";
import {
    forgetLegacyUsage,
    legacyUsage,
    profileUsage,
    recordUsage,
    type UsageCategory,
    type UsageEntry,
} from "./lib/usage";
import { countWords, fetchVocabulary, type Vocabulary } from "./lib/vocabulary";
import type { Word } from "./lib/words";

export type WordsState =
    | { status: "loading" }
    | { status: "error"; message: string }
    | { status: "ready"; words: Word[] };

export type BooksState =
    | { status: "loading" }
    | { status: "error"; message: string }
    | { status: "ready"; books: ListedBook[] };

interface Props {
    /** Who is logged in. */
    user: string;
    /** The settings and the chats as the server had them when the user came in. */
    initialSettings: Settings;
    initialChats: StoredChat[];
}

/** The activities written in with a box whose sentences are checked, which have the panel of the checks. */
const CHECKED_ACTIVITIES: readonly Activity[] = ["chat", "tutor", "texts"];

/** What the usage of each kind of background task is counted under. */
const TASK_CATEGORIES: Record<string, UsageCategory> = {
    words: "vocabulary",
    embeddings: "vocabulary",
    speech: "speech",
    icon: "practice",
    log: "practice",
    questions: "translation",
    memories: "tutor",
};

export function App({ user, initialSettings, initialChats }: Props) {
    const [settings, setSettings] = useState<Settings>(initialSettings);
    // the panel on the left, with the words, the chats and the books
    const [libraryOpen, setLibraryOpen] = useState(() => loadLayout().libraryOpen);
    // the logs, which take the place of the library on the left while they are open
    const [logsOpen, setLogsOpen] = useState(false);
    // tells the logs from those before something more was logged
    const [logsRevision, setLogsRevision] = useState(0);
    // the panels on the right share one place, so one is shown at a time
    const [openPanel, setOpenPanel] = useState<Panel | "subchat" | null>(() => loadLayout().panel);
    // The panels are found as they were left the next time the page is
    // opened, but for the chat about a selection, which is gone by then.
    // the tab shown last is shown again when the page is opened, and the text open last
    const [activity, setActivity] = useState<Activity>(() => loadLayout().activity);
    const [textId, setTextId] = useState<string | null>(() => loadLayout().text);
    useEffect(
        () => saveLayout({ libraryOpen, panel: openPanel === "subchat" ? null : openPanel, activity, text: textId }),
        [libraryOpen, openPanel, activity, textId],
    );
    // the selection the floating chat is about, with a number that tells it from the one before
    const [asked, setAsked] = useState<{ translated: Translated; nonce: number } | null>(null);
    const [settingsTab, setSettingsTab] = useState<SettingsTab>("general");
    // where the chat puts the sentence checks, which are made of what it knows
    const [panelSlot, setPanelSlot] = useState<HTMLElement | null>(null);
    const [wordsState, setWordsState] = useState<WordsState>({ status: "loading" });
    // the Anki account the user may link, whose words have a tab of their own
    const [anki, setAnki] = useState<AnkiState | null>(null);
    const ankiWords = anki?.linked ?? false;
    // goes up when other Anki decks are chosen, for their words to be fetched
    const [decksRevision, setDecksRevision] = useState(0);
    // text a clicked word adds to the message being written
    const [picked, setPicked] = useState<{ word: string; nonce: number } | null>(null);
    // tells the usage the server has from what it had before something was recorded
    const [usageRevision, setUsageRevision] = useState(0);
    const [chatStore, setChatStore] = useState<ChatStore>(() =>
        storeOf(initialChats, initialSettings.defaultContextId, initialSettings.language)
    );
    const [sidebarTab, setSidebarTab] = useState<"words" | "vocabulary" | "memories" | "texts" | "chats" | "books">(
        "vocabulary",
    );
    // the learner's texts and their corrections, or why they could not be listed
    const [texts, setTexts] = useState<Text[] | string>([]);
    const [textsRevision, setTextsRevision] = useState(0);
    useEffect(() => {
        fetchTexts().then(setTexts, (failed: Error) => setTexts(failed.message));
    }, [textsRevision]);
    // how many memories the tutor has, and what has them listed again once more may have been made
    const [memoryCount, setMemoryCount] = useState<number | null>(null);
    const [memoriesRevision, setMemoriesRevision] = useState(0);
    // how many words the vocabulary has, once it has been listed
    const [vocabularyCount, setVocabularyCount] = useState<number | null>(null);

    // every request the tutor made in its chat, for the inspector
    const [trace, setTrace] = useState<Trace>(EMPTY_TRACE);
    const [booksState, setBooksState] = useState<BooksState>({ status: "loading" });
    // the book in the reader, which is the one that was read last
    const [bookId, setBookId] = useState<string | null>(() => loadReading().bookId);
    const [addingBook, setAddingBook] = useState(false);
    const [bookError, setBookError] = useState<string | null>(null);
    const chat = activeChat(chatStore);
    const chats = listedChats(chatStore);
    // The words a prompt is given come from the vocabulary of the language
    // being learned, by the sets picked out of it.
    const [vocabulary, setVocabulary] = useState<Vocabulary | null>(null);
    const [sets, setSets] = useState<WordSet[]>([]);
    // the set in the editor, if it is open
    const [editedSet, setEditedSet] = useState<WordSet | null>(null);
    const activeSetId = settings.activeSets[settings.language];
    const words = useMemo(
        () => wordLists(sets, activeSetId, vocabulary?.words ?? []),
        [sets, activeSetId, vocabulary],
    );

    // Usage was kept in the browser before the server kept it for each user.
    // What is left of it goes to the first user to log in here.
    useEffect(() => {
        const left = legacyUsage();
        if (left.length > 0) {
            recordUsage(left).then(() => {
                forgetLegacyUsage();
                setUsageRevision((revision) => revision + 1);
            }, () => {
                // it is sent again the next time the page is opened
            });
        }
    }, []);
    useEffect(() => applyAppearance(settings), [settings.theme, settings.accent, settings.textSize]);

    // The server is told of the chats that change, and of those that are
    // deleted. A reply changes its chat many times a second while it
    // arrives, so the telling waits until it pauses, or the page is left.
    const told = useRef(new Map(initialChats.map((kept) => [kept.id, kept])));
    const latestChats = useRef(chatStore);
    latestChats.current = chatStore;
    const tellServer = useCallback((leaving: boolean) => {
        const { changed, removed } = chatsToTell(told.current, latestChats.current);
        for (const changedChat of changed) {
            told.current.set(changedChat.id, changedChat);
            // one that could not be told is told again with the next change
            putChat(changedChat, leaving).catch(() => told.current.delete(changedChat.id));
        }
        for (const id of removed) {
            told.current.delete(id);
            removeChat(id).catch(() => undefined);
        }
    }, []);
    useEffect(() => {
        const timer = setTimeout(() => tellServer(false), 300);
        return () => clearTimeout(timer);
    }, [chatStore, tellServer]);
    useEffect(() => {
        const tell = () => tellServer(true);
        window.addEventListener("pagehide", tell);
        return () => window.removeEventListener("pagehide", tell);
    }, [tellServer]);

    const changeMessages = useCallback(
        (chatId: string, change: (messages: ChatMessage[]) => ChatMessage[]) =>
            setChatStore((store) =>
                updateChat(store, chatId, (current) => ({
                    ...current,
                    messages: change(current.messages),
                    updatedAt: Date.now(),
                }))
            ),
        [],
    );

    function newChat() {
        setChatStore((store) => startChat(store, settings.defaultContextId, settings.language));
        setActivity("chat");
    }

    const loadBooks = useCallback(() => {
        setBooksState({ status: "loading" });
        fetchBooks().then(
            (books) => setBooksState({ status: "ready", books }),
            (error: Error) => setBooksState({ status: "error", message: error.message }),
        );
    }, []);

    useEffect(loadBooks, [loadBooks]);

    function openBook(id: string | null) {
        setBookId(changeReading((reading) => ({ ...reading, bookId: id })).bookId);
        if (id !== null) {
            setActivity("books");
        }
    }

    function takeBook(file: File) {
        setAddingBook(true);
        setBookError(null);
        addBook(file).then(
            (added) => {
                setBooksState((state) => ({
                    status: "ready",
                    books: [added, ...(state.status === "ready" ? state.books : [])],
                }));
                openBook(added.id);
            },
            (error: Error) => setBookError(error.message),
        ).finally(() => setAddingBook(false));
    }

    function removeBook(id: string) {
        setBookError(null);
        deleteBook(id).then(
            () => {
                setBooksState((state) =>
                    state.status === "ready"
                        ? { status: "ready", books: state.books.filter((book) => book.id !== id) }
                        : state
                );
                // how far it was read is forgotten with it
                changeReading(({ places: { [id]: _, ...places }, ...reading }) => ({ ...reading, places }));
                if (id === bookId) {
                    openBook(null);
                }
            },
            (error: Error) => setBookError(error.message),
        );
    }

    const addUsageEntry = useCallback(
        (entry: UsageEntry) =>
            void recordUsage([entry]).then(() => setUsageRevision((revision) => revision + 1), () => {
                // the server is not running, so there is nowhere to count it
            }),
        [],
    );

    const loadWords = useCallback(() => {
        if (!ankiWords) {
            return;
        }
        setWordsState({ status: "loading" });
        fetchKnownWords().then(
            (words) => setWordsState({ status: "ready", words }),
            (error: Error) => setWordsState({ status: "error", message: error.message }),
        );
        // the words are fetched again once the first sync has brought them
    }, [ankiWords, anki?.last_sync, decksRevision]);

    useEffect(loadWords, [loadWords]);

    // Whether an Anki account is linked is asked once, and again every few
    // seconds while its first sync runs.
    const firstSync = ankiWords && anki?.last_sync === null && !anki.error;
    useEffect(() => {
        let stopped = false;
        const ask = () => fetchAnkiState().then((state) => stopped || setAnki(state), () => undefined);
        ask();
        const timer = firstSync ? setInterval(ask, 5000) : undefined;
        return () => {
            stopped = true;
            clearInterval(timer);
        };
    }, [firstSync]);

    // The checker server takes the Anki words into the vocabulary by itself,
    // with the key and the models it is handed here.
    const [vocabularyRevision, setVocabularyRevision] = useState(0);
    useEffect(() => {
        let current = true;
        fetchVocabulary(settings.language).then(
            (fetched) => current && setVocabulary(fetched),
            () => undefined,
        );
        return () => {
            current = false;
        };
    }, [settings.language, vocabularyRevision]);
    useEffect(() => {
        let current = true;
        setSets([]);
        fetchSets(settings.language).then((fetched) => current && setSets(fetched), () => undefined);
        return () => {
            current = false;
        };
    }, [settings.language]);

    // Before a prompt is sent, the words are fetched again, so that a set is
    // made of what is known about each word then.
    const latestSets = useRef({ sets, activeSetId, language: settings.language });
    latestSets.current = { sets, activeSetId, language: settings.language };
    const freshWordLists = useCallback(async () => {
        const { sets: current, activeSetId: active, language } = latestSets.current;
        const fetched = await fetchVocabulary(language);
        setVocabulary(fetched);
        return wordLists(current, active, fetched.words);
    }, []);

    // the words of a set as the vocabulary is now, for the exercises
    const wordsOfSet = useCallback(async (id: string) => {
        const { sets: current, language } = latestSets.current;
        const set = current.find((each) => each.id === id);
        if (!set) {
            return null;
        }
        const fetched = await fetchVocabulary(language);
        return [...new Set(membersOf(set, fetched.words).map((word) => word.lemma))];
    }, []);

    function pickSet(id: string) {
        updateSettings({ ...settings, activeSets: { ...settings.activeSets, [settings.language]: id } });
    }

    function keepSet(set: WordSet) {
        setSets((current) =>
            current.some((each) => each.id === set.id)
                ? current.map((each) => (each.id === set.id ? set : each))
                : [...current, set]
        );
        saveSet(set, settings.language).catch(() => undefined);
        // a set that has just been made is the one to use
        if (!sets.some((each) => each.id === set.id)) {
            pickSet(set.id);
        }
        setEditedSet(null);
    }

    function removeSet(id: string) {
        setSets((current) => current.filter((each) => each.id !== id));
        deleteSet(id, settings.language).catch(() => undefined);
        setEditedSet(null);
    }
    const importing = useAnkiImport({
        enabled: settings.importAnki && ankiWords,
        apiKey: settings.apiKey,
        model: settings.model,
        decisionModel: settings.profileModel,
        language: settings.language,
        ankiLanguage: settings.ankiLanguage,
        onUsage: useCallback(
            (used) => addUsageEntry(profileUsage(used, Date.now(), "vocabulary")),
            [addUsageEntry],
        ),
        onImported: useCallback(() => setVocabularyRevision((revision) => revision + 1), []),
    });

    // What the server does in the background is asked after while any of
    // it is still running, and once at the start, as it goes on while the
    // page is away. What a task used is counted when it is done, and the
    // words are listed again, as it may have added some.
    const [tasks, setTasks] = useState<BackgroundTask[]>([]);
    const addTask = useCallback((task: BackgroundTask) => setTasks((current) => withTask(current, task)), []);
    // tells the topics from those before an icon was made
    const [topicsRevision, setTopicsRevision] = useState(0);
    const embeddingTask = tasks.find((task) => task.kind === "embeddings" && task.state === "running") ?? null;
    const finished = useRef(new Set<string>());
    // who reads the sentences of a book aloud, and how
    const voice = useMemo<Voice>(
        () => ({
            apiKey: settings.apiKey,
            model: settings.speechModel,
            voice: settings.speechVoice,
            instructions: speechInstructions(settings.speechDirection, settings.language, settings.level),
        }),
        [
            settings.apiKey,
            settings.speechModel,
            settings.speechVoice,
            settings.speechDirection,
            settings.language,
            settings.level,
        ],
    );
    const latestVoice = useRef(voice);
    latestVoice.current = voice;
    const followTasks = useCallback((fetched: BackgroundTask[]) => {
        setTasks(fetched);
        for (const task of fetched) {
            if (task.state === "running" || finished.current.has(task.id)) {
                continue;
            }
            finished.current.add(task.id);
            const category = TASK_CATEGORIES[task.kind] ?? "vocabulary";
            task.usage.forEach((used) => addUsageEntry(profileUsage(used, Date.now(), category, `task:${task.kind}`)));
            if (task.kind === "words") {
                setVocabularyRevision((revision) => revision + 1);
            }
            if (task.kind === "icon") {
                setTopicsRevision((revision) => revision + 1);
            }
            if (task.kind === "log" || task.kind === "questions") {
                setLogsRevision((revision) => revision + 1);
            }
            if (task.kind === "log") {
                // an exercise is over, which may have corrected a text
                setTextsRevision((revision) => revision + 1);
            }
            if (task.kind === "memories") {
                setMemoriesRevision((revision) => revision + 1);
            }
            // Audio comes without what it cost, which is looked up
            // afterwards, by what each request for it goes by.
            const { apiKey, model } = latestVoice.current;
            for (const { generation } of task.result) {
                // only OpenRouter keeps what a request used
                if (generation && apiKey && !model.url) {
                    void fetchGenerationUsage(apiKey, generation).then((used) =>
                        addUsageEntry({
                            id: generation,
                            at: Date.now(),
                            category: "speech",
                            chatId: "speech",
                            model: used?.model ?? model.model,
                            promptTokens: used?.promptTokens ?? 0,
                            completionTokens: used?.completionTokens ?? 0,
                            cost: used?.cost ?? null,
                        })
                    );
                }
            }
        }
    }, [addUsageEntry]);
    // what is read aloud, with a number that tells it from what was read before
    const [listening, setListening] = useState<{ source: SpeechSource; nonce: number } | null>(null);
    const speakMessage = useCallback(
        (chatId: string, place: number, text: string) =>
            setListening({ source: messageSource(chatId, place, text), nonce: Date.now() }),
        [],
    );
    const tasksRunning = tasks.some((task) => task.state === "running");
    useEffect(() => {
        let stopped = false;
        const look = () => fetchTasks().then((fetched) => stopped || followTasks(fetched), () => undefined);
        look();
        const timer = tasksRunning ? setInterval(look, TASKS_INTERVAL_MS) : undefined;
        return () => {
            stopped = true;
            clearInterval(timer);
        };
    }, [tasksRunning, followTasks]);

    // the sentence checks belong to the chat, and the floating chat to a selection
    // the checks are of what is written in the chat, to the tutor or in a text
    const panel = (openPanel === "checks" && !CHECKED_ACTIVITIES.includes(activity))
            || (openPanel === "subchat" && !asked)
        ? null
        : openPanel;
    // who answers what is asked about a selection, and who translates it, which may be a quicker model
    const asking = useMemo<Asking>(
        () => ({
            apiKey: settings.apiKey,
            model: settings.model,
            language: settings.language,
            into: settings.translateInto,
        }),
        [settings.apiKey, settings.model, settings.language, settings.translateInto],
    );
    // who practises, and who makes and checks the exercises for them
    const learner = useMemo<Learner>(
        () => ({
            apiKey: settings.apiKey,
            model: settings.model,
            imageModel: settings.imageModel,
            visionModel: settings.visionModel,
            into: settings.translateInto,
            level: settings.level,
        }),
        [
            settings.apiKey,
            settings.model,
            settings.imageModel,
            settings.visionModel,
            settings.translateInto,
            settings.level,
        ],
    );
    const addPracticeUsage = useCallback(
        (used: ProfileUsage[]) => used.forEach((each) => addUsageEntry(practiceUsage(each, Date.now()))),
        [addUsageEntry],
    );
    const addEvaluationUsage = useCallback(
        (used: ProfileUsage[]) => used.forEach((each) => addUsageEntry(evaluationUsage(each, Date.now()))),
        [addUsageEntry],
    );
    // the tutor thinks with the model that reasons, or with that of the chat if none is chosen
    const tutorAsking = useMemo<TutorAsking>(
        () => ({
            apiKey: settings.apiKey,
            model: orModel(settings.reasoningModel, settings.model),
            language: settings.language,
            into: settings.translateInto,
            level: settings.level,
            tone: settings.tutorTone,
        }),
        [
            settings.apiKey,
            settings.reasoningModel,
            settings.model,
            settings.language,
            settings.translateInto,
            settings.level,
            settings.tutorTone,
        ],
    );
    // an exercise the tutor offered is started as a session of its own, with no time limit
    const startOffer = useCallback(
        async (offer: Offer) => {
            // the words the tutor chose, if it chose any, and else those the settings say
            const vocabulary = offer.words?.length ? "set" : exerciseVocabularyOf(settings, settings.language);
            const setWords = offer.words?.length
                ? offer.words
                : vocabulary === "all" || vocabulary === "none"
                ? null
                : await wordsOfSet(vocabulary);
            const choosing = choosingOf(settings, vocabulary, setWords);
            return startSession(
                settings.language,
                offer.lesson || null,
                { [offer.exercise]: offer.instances },
                offer.topics,
                // the words the tutor chose are those, not the nearest to the topics
                offer.words?.length ? { ...choosing, topic_words: false } : choosing,
                settings.apiKey,
                { [offer.exercise]: offer.options },
                { [offer.exercise]: 0 },
                offer.focus ? { [offer.exercise]: offer.focus } : {},
            );
        },
        [settings, wordsOfSet],
    );
    // a mock exam the tutor offered is started, and opened in the tab of evaluations
    const [openingEvaluation, setOpeningEvaluation] = useState<{ evaluation: Evaluation; nonce: number } | null>(
        null,
    );
    const startOfferedEvaluation = useCallback(
        (exam: EvaluationOffer) => {
            startEvaluation(settings.language, exam.level, exam.length, exam.timed).then(
                (evaluation) => {
                    setOpeningEvaluation({ evaluation, nonce: Date.now() });
                    setActivity("evaluations");
                },
                (failed: Error) => window.alert(`The mock exam could not be started: ${failed.message}`),
            );
        },
        [settings.language],
    );
    const addTutorUsage = useCallback(
        (used: ProfileUsage[]) =>
            used.forEach((each) => addUsageEntry(profileUsage(each, Date.now(), "tutor", TUTOR_USAGE_ID))),
        [addUsageEntry],
    );
    const translating = useMemo<Asking>(
        () => ({ ...asking, model: orModel(settings.translationModel, asking.model) }),
        [asking, settings.translationModel],
    );

    function togglePanel(wanted: Panel) {
        setOpenPanel(panel === wanted ? null : wanted);
    }

    function openSettings(tab: SettingsTab) {
        setSettingsTab(tab);
        setOpenPanel("settings");
    }

    function updateSettings(next: Settings) {
        setSettings(next);
        saveSettings(next);
    }

    return (
        <WritingChecks language={settings.language}>
            <div className="app">
                <aside className="side-panel left" hidden={!logsOpen}>
                    <SidePanel title="Logs" onClose={() => setLogsOpen(false)} flush>
                        <LogsPanel active={logsOpen} revision={logsRevision} onOpenBook={openBook} />
                    </SidePanel>
                </aside>
                <aside className="side-panel left" hidden={!libraryOpen || logsOpen}>
                    <SidePanel
                        title="Library"
                        onClose={() => setLibraryOpen(false)}
                        flush
                        tabs={
                            <div className="tabs" role="tablist">
                                <button
                                    role="tab"
                                    aria-selected={sidebarTab === "vocabulary"}
                                    onClick={() => setSidebarTab("vocabulary")}
                                >
                                    Words
                                    <span className="count">
                                        {vocabularyCount ?? (vocabulary && countWords(vocabulary.words))}
                                    </span>
                                </button>
                                {ankiWords && (
                                    <button
                                        role="tab"
                                        aria-selected={sidebarTab === "words"}
                                        onClick={() => setSidebarTab("words")}
                                    >
                                        Anki
                                        <span className="count">
                                            {wordsState.status === "ready" && wordsState.words.length}
                                        </span>
                                    </button>
                                )}
                                <button
                                    role="tab"
                                    aria-selected={sidebarTab === "memories"}
                                    onClick={() => setSidebarTab("memories")}
                                >
                                    Memories
                                    <span className="count">{memoryCount || ""}</span>
                                </button>
                                <button
                                    role="tab"
                                    aria-selected={sidebarTab === "texts"}
                                    onClick={() => setSidebarTab("texts")}
                                >
                                    Texts
                                    <span className="count">
                                        {typeof texts !== "string"
                                                && texts.filter((text) => text.kind === "text").length || ""}
                                    </span>
                                </button>
                                <button
                                    role="tab"
                                    aria-selected={sidebarTab === "chats"}
                                    onClick={() => setSidebarTab("chats")}
                                >
                                    Chats
                                    <span className="count">{chats.length > 0 && chats.length}</span>
                                </button>
                                <button
                                    role="tab"
                                    aria-selected={sidebarTab === "books"}
                                    onClick={() => setSidebarTab("books")}
                                >
                                    Books
                                    <span className="count">
                                        {booksState.status === "ready" && booksState.books.length > 0
                                            && booksState.books.length}
                                    </span>
                                </button>
                            </div>
                        }
                    >
                        {/* kept in place while hidden, so the word filter and sort order survive a visit to the chats */}
                        {ankiWords && (
                            <div className="tab-panel" role="tabpanel" hidden={sidebarTab !== "words"}>
                                <WordList
                                    state={wordsState}
                                    onReload={loadWords}
                                    onPick={(word) => setPicked({ word: word.word, nonce: Date.now() })}
                                />
                            </div>
                        )}
                        <div className="tab-panel" role="tabpanel" hidden={sidebarTab !== "vocabulary"}>
                            <VocabularyList
                                active={libraryOpen && sidebarTab === "vocabulary"}
                                language={settings.language}
                                ankiLanguage={settings.ankiLanguage}
                                revision={vocabularyRevision}
                                sets={sets}
                                activeSetId={activeSetId}
                                onActiveSet={pickSet}
                                onEditSet={(set) => setEditedSet(set ?? newSet())}
                                onCount={setVocabularyCount}
                                importing={ankiWords ? importing : null}
                            />
                        </div>
                        <div className="tab-panel" role="tabpanel" hidden={sidebarTab !== "memories"}>
                            <MemoryList revision={memoriesRevision} onCount={setMemoryCount} />
                        </div>
                        <div className="tab-panel" role="tabpanel" hidden={sidebarTab !== "texts"}>
                            <TextList
                                texts={texts}
                                selectedId={activity === "texts" ? textId : null}
                                onSelect={(id) => {
                                    setTextId(id);
                                    setActivity("texts");
                                }}
                                onNew={() => {
                                    const id = newId();
                                    void saveText(id, "", "", settings.language).then(() => {
                                        setTextsRevision((revision) => revision + 1);
                                        setTextId(id);
                                        setActivity("texts");
                                    });
                                }}
                                onDelete={(text) => {
                                    if (window.confirm(`Delete “${text.title || "Untitled"}”?`)) {
                                        void deleteText(text.id).then(() => {
                                            setTextsRevision((revision) => revision + 1);
                                            setTextId((open) => (open === text.id ? null : open));
                                        });
                                    }
                                }}
                            />
                        </div>
                        <div className="tab-panel" role="tabpanel" hidden={sidebarTab !== "chats"}>
                            <ChatList
                                chats={chats}
                                activeId={chat.id}
                                onSelect={(id) => {
                                    setChatStore((store) => selectChat(store, id));
                                    setActivity("chat");
                                }}
                                onDelete={(id) =>
                                    setChatStore((store) =>
                                        deleteChat(store, id, settings.defaultContextId, settings.language)
                                    )}
                                onNewChat={newChat}
                            />
                        </div>
                        <div className="tab-panel" role="tabpanel" hidden={sidebarTab !== "books"}>
                            <BookList
                                state={booksState}
                                selectedId={bookId}
                                adding={addingBook}
                                addError={bookError}
                                onSelect={openBook}
                                onAdd={takeBook}
                                onDelete={removeBook}
                                onReload={loadBooks}
                            />
                        </div>
                    </SidePanel>
                </aside>
                <main className="main">
                    {
                        /* Buttons that take each other's place are kept together: the panels on the left,
                        the activities, and the panels on the right. */
                    }
                    <header className="topbar">
                        <div className="topbar-side">
                            <div className="switch" role="group" aria-label="Panel on the left">
                                <button
                                    className="icon-only"
                                    aria-pressed={libraryOpen && !logsOpen}
                                    onClick={() => {
                                        setLibraryOpen(logsOpen || !libraryOpen);
                                        setLogsOpen(false);
                                    }}
                                    title="Library"
                                    aria-label="Library"
                                >
                                    <Icon name="library" />
                                </button>
                                <button
                                    className="icon-only"
                                    aria-pressed={logsOpen}
                                    onClick={() => setLogsOpen(!logsOpen)}
                                    title="Logs"
                                    aria-label="Logs"
                                >
                                    <Icon name="logs" />
                                </button>
                            </div>
                            <TaskSign tasks={tasks} />
                        </div>
                        <div className="switch activities" role="tablist" aria-label="Activity">
                            <button
                                role="tab"
                                aria-selected={activity === "tutor"}
                                onClick={() => setActivity("tutor")}
                            >
                                Tutor
                            </button>
                            <button
                                role="tab"
                                aria-selected={activity === "inspector"}
                                onClick={() => setActivity("inspector")}
                            >
                                Inspector
                            </button>
                            <button role="tab" aria-selected={activity === "chat"} onClick={() => setActivity("chat")}>
                                Chat
                            </button>
                            <button
                                role="tab"
                                aria-selected={activity === "books"}
                                onClick={() => setActivity("books")}
                            >
                                Books
                            </button>
                            <button
                                role="tab"
                                aria-selected={activity === "practice"}
                                onClick={() => setActivity("practice")}
                            >
                                Practice
                            </button>
                            <button
                                role="tab"
                                aria-selected={activity === "evaluations"}
                                onClick={() => setActivity("evaluations")}
                            >
                                Evaluations
                            </button>
                        </div>
                        <div className="topbar-side end">
                            <div className="switch" role="group" aria-label="Panel on the right">
                                {CHECKED_ACTIVITIES.includes(activity) && (
                                    <button
                                        className="icon-only"
                                        aria-pressed={panel === "checks"}
                                        onClick={() => togglePanel("checks")}
                                        title="Checks"
                                        aria-label="Checks"
                                    >
                                        <Icon name="checks" />
                                    </button>
                                )}
                                <button
                                    className="icon-only"
                                    aria-pressed={panel === "usage"}
                                    onClick={() => togglePanel("usage")}
                                    title="Usage"
                                    aria-label="Usage"
                                >
                                    <Icon name="usage" />
                                </button>
                                <button
                                    className="icon-only"
                                    aria-pressed={panel === "settings"}
                                    onClick={() => togglePanel("settings")}
                                    title="Settings"
                                    aria-label="Settings"
                                >
                                    <Icon name="settings" />
                                </button>
                            </div>
                            <button
                                className="log-out icon-only"
                                onClick={logOut}
                                title={`Log out (logged in as ${user})`}
                                aria-label="Log out"
                            >
                                <Icon name="log-out" />
                            </button>
                        </div>
                    </header>
                    {/* each stays in place while hidden, so a reply still arriving is not cut off */}
                    <div className="pane" hidden={activity !== "tutor"}>
                        <Tutor
                            asking={tutorAsking}
                            learner={learner}
                            enterSends={settings.enterSends}
                            onUsage={addTutorUsage}
                            onPracticeUsage={addPracticeUsage}
                            onTask={addTask}
                            startOffer={startOffer}
                            onReadAloud={(sessionId, exercise, number, text) =>
                                setListening({
                                    source: exerciseSource(sessionId, exercise, number, text),
                                    nonce: Date.now(),
                                })}
                            onOpenSettings={() => openSettings("general")}
                            onStartEvaluation={startOfferedEvaluation}
                            speakReplies={settings.speakReplies}
                            onSpeakReplies={(speakReplies) => updateSettings({ ...settings, speakReplies })}
                            onSpeak={speakMessage}
                            onExchange={(label) => setTrace((current) => begun(current, label, Date.now()))}
                            onTrace={(event) => setTrace((current) => traced(current, event))}
                            onNewChat={() => setTrace(EMPTY_TRACE)}
                            settings={settings}
                            onSettingsChange={updateSettings}
                            checksSlot={panel === "checks" && activity === "tutor" ? panelSlot : null}
                            onCloseChecks={() => setOpenPanel(null)}
                            onEditQuestions={() => openSettings("questions")}
                            onCheckingUsage={addUsageEntry}
                        />
                    </div>
                    <div className="pane" hidden={activity !== "inspector"}>
                        <Inspector trace={trace} />
                    </div>
                    <div className="pane" hidden={activity !== "chat"}>
                        <Chat
                            key={chat.id}
                            settings={settings}
                            onSettingsChange={updateSettings}
                            checksSlot={panel === "checks" && activity === "chat" ? panelSlot : null}
                            onCloseChecks={() => setOpenPanel(null)}
                            onEditQuestions={() => openSettings("questions")}
                            words={words}
                            loadWords={freshWordLists}
                            picked={activity === "chat" ? picked : null}
                            onOpenSettings={() => openSettings("general")}
                            onUsage={addUsageEntry}
                            onSpeak={speakMessage}
                            chat={chat}
                            onMessages={changeMessages}
                            onContext={(contextId) =>
                                setChatStore((store) =>
                                    updateChat(store, chat.id, (current) => ({ ...current, contextId }))
                                )}
                            onNewChat={newChat}
                        />
                    </div>
                    <div className="pane" hidden={activity !== "texts"}>
                        {textId
                            ? (
                                <TextEditor
                                    // loaded again once it is corrected, which locks it
                                    key={`${textId}:${
                                        typeof texts === "string"
                                            ? ""
                                            : texts.find((text) => text.id === textId)?.lockedAt ?? ""
                                    }`}
                                    id={textId}
                                    language={settings.language}
                                    settings={settings}
                                    onSettingsChange={updateSettings}
                                    onUsage={addUsageEntry}
                                    checksSlot={panel === "checks" && activity === "texts" ? panelSlot : null}
                                    onCloseChecks={() => setOpenPanel(null)}
                                    onEditQuestions={() => openSettings("questions")}
                                    correctionId={typeof texts === "string"
                                        ? null
                                        : texts.find((text) => text.corrects === textId)?.id ?? null}
                                    onSaved={() => setTextsRevision((revision) => revision + 1)}
                                />
                            )
                            : <p className="practice-note">Open a text from the Texts tab of the library.</p>}
                    </div>
                    <div className="pane" hidden={activity !== "books"}>
                        <BookReader bookId={bookId} active={activity === "books"} />
                    </div>
                    <div className="pane" hidden={activity !== "practice"}>
                        <Practice
                            active={activity === "practice"}
                            settings={settings}
                            learner={learner}
                            wordsOfSet={wordsOfSet}
                            topicsRevision={topicsRevision}
                            embedding={embeddingTask}
                            onUsage={addPracticeUsage}
                            onTask={addTask}
                            onChangeSettings={updateSettings}
                            onOpenSettings={() => openSettings("general")}
                            onReadAloud={(sessionId, exercise, number, text) =>
                                setListening({
                                    source: exerciseSource(sessionId, exercise, number, text),
                                    nonce: Date.now(),
                                })}
                        />
                    </div>
                    <div className="pane" hidden={activity !== "evaluations"}>
                        <Evaluations
                            opening={openingEvaluation}
                            settings={settings}
                            learner={learner}
                            onUsage={addEvaluationUsage}
                            onTask={addTask}
                            onChangeSettings={updateSettings}
                            onOpenSettings={() => openSettings("general")}
                            onReadAloud={(sessionId, exercise, number, text) =>
                                setListening({
                                    source: exerciseSource(sessionId, exercise, number, text, "evaluation"),
                                    nonce: Date.now(),
                                })}
                            onEnded={() => setLogsRevision((revision) => revision + 1)}
                        />
                    </div>
                </main>
                <aside
                    className="side-panel"
                    hidden={panel === null || panel === "subchat"}
                    ref={setPanelSlot}
                >
                    {panel === "usage" && (
                        <UsagePanel
                            revision={usageRevision}
                            currentLabel={activity === "tutor" || activity === "inspector"
                                ? "Tutor"
                                : activity === "books" || activity === "texts"
                                ? null
                                : activity === "practice"
                                ? "Practice"
                                : activity === "evaluations"
                                ? "Evaluations"
                                : "This chat"}
                            chatId={activity === "tutor" || activity === "inspector"
                                ? TUTOR_USAGE_ID
                                : activity === "practice"
                                ? PRACTICE_USAGE_ID
                                : activity === "evaluations"
                                ? EVALUATION_USAGE_ID
                                : chat.id}
                            onClose={() => setOpenPanel(null)}
                        />
                    )}
                    {panel === "settings" && (
                        <SettingsPanel
                            settings={settings}
                            anki={anki}
                            onAnki={setAnki}
                            onDecks={() => setDecksRevision((revision) => revision + 1)}
                            sets={sets}
                            tab={settingsTab}
                            onTab={setSettingsTab}
                            onChange={updateSettings}
                            onClose={() => setOpenPanel(null)}
                        />
                    )}
                </aside>
                {/* floats over the page, which keeps its width */}
                {panel === "subchat" && asked && (
                    <section className="floating-window" aria-label="Ask about it">
                        <SubChat
                            key={asked.nonce}
                            translated={asked.translated}
                            asking={asking}
                            onUsage={addUsageEntry}
                            onTask={addTask}
                            onClose={() => setOpenPanel(null)}
                        />
                    </section>
                )}
                <SelectionTools
                    translating={translating}
                    describing={asking}
                    decisionModel={settings.profileModel}
                    onUsage={addUsageEntry}
                    onTask={(task) => setTasks((current) => withTask(current, task))}
                    onLogged={() => setLogsRevision((revision) => revision + 1)}
                    onPlay={(selection) =>
                        bookId && setListening({ source: bookSource(bookId, selection), nonce: Date.now() })}
                    onChat={(translated) => {
                        setAsked({ translated, nonce: Date.now() });
                        setOpenPanel("subchat");
                    }}
                />
                {listening && (
                    <SpeechPlayer
                        key={listening.nonce}
                        source={listening.source}
                        voice={voice}
                        onTask={(task) => setTasks((current) => withTask(current, task))}
                        onClose={() => setListening(null)}
                    />
                )}
                {editedSet && vocabulary && (
                    <SetEditor
                        key={editedSet.id}
                        set={editedSet}
                        kept={sets.some((set) => set.id === editedSet.id)}
                        vocabulary={vocabulary}
                        onSave={keepSet}
                        onDelete={() => removeSet(editedSet.id)}
                        onClose={() => setEditedSet(null)}
                    />
                )}
            </div>
        </WritingChecks>
    );
}
