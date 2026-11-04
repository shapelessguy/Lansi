// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { orModel } from "./lib/models";

import { BookList, chosenVersion } from "./components/BookList";
import { BookReader, type NoteAsked } from "./components/BookReader";
import { BookVersionEditor } from "./components/BookVersionEditor";
import { Chat } from "./components/Chat";
import { ChatList } from "./components/ChatList";
import { Evaluations } from "./components/Evaluations";
import { EvaluationsDone } from "./components/EvaluationsDone";
import { ExercisesDone } from "./components/ExercisesDone";
import { Icon } from "./components/Icon";
import { LogsPanel } from "./components/LogsPanel";
import { MemoryList } from "./components/MemoryList";
import { Practice } from "./components/Practice";
import { PracticeSessions } from "./components/PracticeSessions";
import { SelectionTools } from "./components/SelectionTools";
import { SetEditor } from "./components/SetEditor";
import { SettingsPanel, type SettingsTab } from "./components/SettingsPanel";
import { SideList } from "./components/SideList";
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
import { type AnkiState, countKnownWords, fetchAnkiState, fetchKnownWords } from "./lib/anki";
import { useAnkiImport } from "./lib/ankiImport";
import { useBack } from "./lib/back";
import {
    addBook,
    type BookVersion,
    changeReading,
    deleteBook,
    fetchBooks,
    type ListedBook,
    loadReading,
    renameBook,
} from "./lib/books";
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
import { ask, tell } from "./lib/dialogs";
import { type Evaluation, evaluationUsage, startEvaluation, USAGE_ID as EVALUATION_USAGE_ID } from "./lib/evaluations";
import { interfaceLanguageOf, type Message, setInterfaceLanguage, t } from "./lib/i18n";
import { newId } from "./lib/ids";
import {
    type Activity,
    type LibraryTab,
    loadLayout,
    type LogsTab,
    type Panel,
    saveLayout,
    SIDES_FIT,
    useMediaQuery,
} from "./lib/layout";
import { LOGGED_EVENT } from "./lib/logs";
import type { ChatMessage } from "./lib/openrouter";
import {
    choosingOf,
    type Learner,
    type PracticeSession,
    practiceUsage,
    replayExercise,
    startSession,
    USAGE_ID as PRACTICE_USAGE_ID,
} from "./lib/practice";
import { logOut } from "./lib/session";
import { deleteSet, fetchSets, membersOf, newSet, saveSet, wordLists, type WordSet } from "./lib/sets";
import { applyAppearance, exerciseVocabularyOf, expandPrompt, saveSettings, type Settings } from "./lib/settings";
import { useShownOnce } from "./lib/shownOnce";
import { bookSource, exerciseSource, messageSource, type SpeechSource, type Voice } from "./lib/speaking";
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
import { useWordTranslations } from "./lib/wordTranslations";

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
/** The tabs of the activities, each with its icon, which is all that is shown of it on a narrow window. */
const ACTIVITY_TABS: readonly (readonly [Activity, Message])[] = [
    ["tutor", "Tutor"],
    ["books", "Books"],
    ["texts", "Texts"],
    ["practice", "Practice"],
    ["evaluations", "Evaluations"],
];
const CHECKED_ACTIVITIES: readonly Activity[] = ["tutor", "texts", "practice", "evaluations"];

/** What the usage of each kind of background task is counted under. */
const TASK_CATEGORIES: Record<string, UsageCategory> = {
    words: "vocabulary",
    embeddings: "vocabulary",
    speech: "speech",
    icon: "practice",
    log: "practice",
    correction: "practice",
    questions: "translation",
    memories: "tutor",
};

export function App({ user, initialSettings, initialChats }: Props) {
    const [settings, setSettings] = useState<Settings>(initialSettings);
    // all that is rendered is in the language of the interface the settings say
    setInterfaceLanguage(interfaceLanguageOf(settings.translateInto));
    // the panel on the left, with the words and the books
    const [libraryOpen, setLibraryOpen] = useState(() => loadLayout().libraryOpen);
    // the logs, which take the place of the library on the left while they are open
    const [logsOpen, setLogsOpen] = useState(() => loadLayout().logsOpen);
    // tells the logs from those before something more was logged
    const [logsRevision, setLogsRevision] = useState(0);
    // which of the logs, the memories and the practice sessions the panel of the logs shows
    const [logsTab, setLogsTab] = useState<LogsTab>(() => loadLayout().logsTab);
    // a session left unfinished taken up from the practice sessions, for Practice to go on with
    const [resuming, setResuming] = useState<{ session: PracticeSession; nonce: number } | null>(null);
    // what was logged that no task tells of, such as the log an exercise wrote itself
    useEffect(() => {
        const listAgain = () => setLogsRevision((revision) => revision + 1);
        window.addEventListener(LOGGED_EVENT, listAgain);
        return () => window.removeEventListener(LOGGED_EVENT, listAgain);
    }, []);
    // The panels on the right share one place, so one is shown at a time,
    // and are found as they were left the next time the page is opened.
    // The chat about a selection floats over them, and leaves them as they are.
    const [panel, setOpenPanel] = useState<Panel | null>(() => loadLayout().panel);
    // the tab shown last is shown again when the page is opened, and the text open last
    const [activity, setActivity] = useState<Activity>(() => loadLayout().activity);
    const [textId, setTextId] = useState<string | null>(() => loadLayout().text);
    const [sidebarTab, setSidebarTab] = useState<LibraryTab>(() => loadLayout().libraryTab);
    // what a pane or a tab lists is fetched the first time it is shown, rather than as the page opens
    const practiceShown = useShownOnce(activity === "practice");
    const evaluationsShown = useShownOnce(activity === "evaluations");
    const memoriesShown = useShownOnce(logsOpen && logsTab === "memories");
    const ankiWordsShown = useShownOnce(libraryOpen && sidebarTab === "words");
    // Where the window has no room for a panel on each side, only the side
    // opened last is shown, and the other one, still open, behind it comes
    // back when it is closed.
    const sidesFit = useMediaQuery(SIDES_FIT);
    const [front, setFront] = useState<"left" | "right">("left");
    const behind = sidesFit || !(libraryOpen || logsOpen) || panel === null
        ? null
        : front === "left"
        ? "right"
        : "left";
    useEffect(
        () =>
            saveLayout({
                libraryOpen,
                logsOpen,
                libraryTab: sidebarTab,
                logsTab,
                panel,
                activity,
                text: textId,
            }),
        [libraryOpen, logsOpen, sidebarTab, logsTab, panel, activity, textId],
    );
    // the selection the floating chat is about, with a number that tells it from the one
    // before, or null while it is closed
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
    // the learner's texts and their corrections, or why they could not be listed
    const [texts, setTexts] = useState<Text[] | string>([]);
    const [textsRevision, setTextsRevision] = useState(0);
    useEffect(() => {
        fetchTexts().then(
            (listed) => {
                setTexts(listed);
                // the text open last may have been deleted since, and is not opened then
                setTextId((open) => (open && !listed.some((text) => text.id === open) ? null : open));
            },
            (failed: Error) => setTexts(failed.message),
        );
    }, [textsRevision]);
    // what has the memories of the tutor listed again once more may have been made
    const [memoriesRevision, setMemoriesRevision] = useState(0);
    // how many words the vocabulary has, once it has been listed
    const [vocabularyCount, setVocabularyCount] = useState<number | null>(null);

    const [booksState, setBooksState] = useState<BooksState>({ status: "loading" });
    // the book in the reader, which is the one that was read last
    const [bookId, setBookId] = useState<string | null>(() => loadReading().bookId);
    // the version of each book chosen last, and the book a version is being made of
    const [chosenVersions, setChosenVersions] = useState(() => loadReading().versions);
    const [editingBook, setEditingBook] = useState<ListedBook | null>(null);
    const [addingBook, setAddingBook] = useState(false);
    const [bookError, setBookError] = useState<string | null>(null);
    // what the book in the reader and its version are called as they are listed, renamed or not
    const readBook = booksState.status === "ready"
        ? booksState.books.find((book) => book.id === bookId || book.versions?.some((version) => version.id === bookId))
        : undefined;
    const readNames = readBook && {
        title: readBook.title,
        version: readBook.versions?.find((version) => version.id === bookId)?.name,
    };
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
        openChat();
    }

    /** Shows the chat, in the library. */
    function openChat() {
        setLibraryOpen(true);
        setLogsOpen(false);
        setSidebarTab("chat");
        setFront("left");
    }

    const loadBooks = useCallback(() => {
        setBooksState({ status: "loading" });
        fetchBooks().then(
            (books) => setBooksState({ status: "ready", books }),
            (error: Error) => setBooksState({ status: "error", message: error.message }),
        );
    }, []);

    useEffect(loadBooks, [loadBooks]);

    /**
     * Has the reader show a book or a version, by its id. With `book`, the
     * book it is of, which is remembered to be shown the next time the book
     * is chosen.
     */
    function openBook(id: string | null, book?: ListedBook) {
        const reading = changeReading((kept) => {
            const versions = { ...kept.versions };
            if (book && id === book.id) {
                delete versions[book.id];
            } else if (book && id !== null) {
                versions[book.id] = id;
            }
            return { ...kept, bookId: id, versions };
        });
        setBookId(reading.bookId);
        setChosenVersions(reading.versions);
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

    /** Removes a book with its versions, or one of its versions, by its id, with the book it is of. */
    function removeBook(id: string, of: ListedBook) {
        setBookError(null);
        deleteBook(id).then(
            () => {
                const isBook = id === of.id;
                setBooksState((state) =>
                    state.status === "ready"
                        ? {
                            status: "ready",
                            books: isBook
                                ? state.books.filter((book) => book.id !== id)
                                : state.books.map((book) =>
                                    book.id === of.id
                                        ? { ...book, versions: book.versions?.filter((version) => version.id !== id) }
                                        : book
                                ),
                        }
                        : state
                );
                // how far each was read, and which was chosen, is forgotten with it
                const gone = new Set(isBook ? [id, ...(of.versions ?? []).map((version) => version.id)] : [id]);
                const reading = changeReading((kept) => ({
                    ...kept,
                    places: Object.fromEntries(Object.entries(kept.places).filter(([place]) => !gone.has(place))),
                    versions: Object.fromEntries(
                        Object.entries(kept.versions).filter(([book, version]) =>
                            !gone.has(book) && !gone.has(version)
                        ),
                    ),
                }));
                setChosenVersions(reading.versions);
                if (bookId !== null && gone.has(bookId)) {
                    // a version that is gone leaves the book it was of open
                    openBook(isBook ? null : of.id, isBook ? undefined : of);
                }
            },
            (error: Error) => setBookError(error.message),
        );
    }

    /** Calls a book, with its versions, or one of its versions, by its id, what the learner named it. */
    function nameBook(id: string, name: string) {
        setBookError(null);
        renameBook(id, name).then(
            (books) => setBooksState({ status: "ready", books }),
            (error: Error) => setBookError(error.message),
        );
    }

    /** Lists a version that was made under its book, and has it read. */
    function takeVersion(version: BookVersion, of: ListedBook) {
        setEditingBook(null);
        setBooksState((state) =>
            state.status === "ready"
                ? {
                    status: "ready",
                    books: state.books.map((book) =>
                        book.id === of.id ? { ...book, versions: [...(book.versions ?? []), version] } : book
                    ),
                }
                : state
        );
        openBook(version.id, of);
    }

    const addUsageEntry = useCallback(
        (entry: UsageEntry) =>
            void recordUsage([entry]).then(() => setUsageRevision((revision) => revision + 1), () => {
                // the server is not running, so there is nowhere to count it
            }),
        [],
    );

    // how many Anki words there are, for the tab, which is all that is wanted of them until it is opened
    const [ankiWordCount, setAnkiWordCount] = useState<number | null>(null);
    const loadWords = useCallback(() => {
        if (!ankiWords) {
            return;
        }
        if (!ankiWordsShown) {
            countKnownWords().then(setAnkiWordCount, () => undefined);
            return;
        }
        setWordsState({ status: "loading" });
        fetchKnownWords().then(
            (words) => {
                setWordsState({ status: "ready", words });
                setAnkiWordCount(words.length);
            },
            (error: Error) => setWordsState({ status: "error", message: error.message }),
        );
        // the words are fetched again once the first sync has brought them
    }, [ankiWords, ankiWordsShown, anki?.last_sync, decksRevision]);

    useEffect(loadWords, [loadWords]);

    // Whether an Anki account is linked is asked once, and again every few
    // seconds while its first sync runs, or until the checker server answers,
    // as it may still be starting when the page is opened.
    const firstSync = ankiWords && anki?.last_sync === null && !anki.error;
    useEffect(() => {
        let stopped = false;
        let retry: ReturnType<typeof setTimeout> | undefined;
        const ask = () =>
            fetchAnkiState().then(
                (state) => stopped || setAnki(state),
                () => {
                    if (!stopped) {
                        retry = setTimeout(ask, 5000);
                    }
                },
            );
        ask();
        const timer = firstSync ? setInterval(ask, 5000) : undefined;
        return () => {
            stopped = true;
            clearInterval(timer);
            clearTimeout(retry);
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
        watching: (libraryOpen && sidebarTab === "vocabulary") || panel === "usage",
        onUsage: useCallback(
            (used) => addUsageEntry(profileUsage(used, Date.now(), "vocabulary")),
            [addUsageEntry],
        ),
        onImported: useCallback(() => setVocabularyRevision((revision) => revision + 1), []),
    });
    const wordTranslations = useWordTranslations({
        active: libraryOpen && sidebarTab === "vocabulary",
        apiKey: settings.apiKey,
        model: settings.model,
        language: settings.language,
        into: settings.translateInto,
        onUsage: useCallback(
            (used) => addUsageEntry(profileUsage(used, Date.now(), "vocabulary")),
            [addUsageEntry],
        ),
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
            instructions: expandPrompt(
                settings.speechDirection,
                words,
                settings.language,
                settings.level,
                settings.translateInto,
            ).trim(),
        }),
        [
            settings.apiKey,
            settings.speechModel,
            settings.speechVoice,
            settings.speechDirection,
            words,
            settings.language,
            settings.level,
        ],
    );
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
            if (task.kind === "log" || task.kind === "correction") {
                // a text was corrected, or an exercise is over, which may have corrected one
                setTextsRevision((revision) => revision + 1);
            }
            if (task.kind === "memories") {
                setMemoriesRevision((revision) => revision + 1);
            }
            if (task.kind === "transform" && task.state === "done") {
                // the version it made is listed under its book
                fetchBooks().then((books) => setBooksState({ status: "ready", books }), () => undefined);
            }
        }
    }, [addUsageEntry]);
    // what is read aloud, with a number that tells it from what was read before
    const [listening, setListening] = useState<{ source: SpeechSource; nonce: number } | null>(null);
    // the selection of the book in the reader a note was last asked to be written on
    const [noteAsked, setNoteAsked] = useState<NoteAsked | null>(null);
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

    // The chat is shown in the library, beside the activity. The checks are
    // of what is written in the activity, or, where nothing is written in
    // it, as in a book, in the chat.
    const chatShown = libraryOpen && !logsOpen && sidebarTab === "chat";
    const chatChecked = chatShown && !CHECKED_ACTIVITIES.includes(activity);
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
            visionKey: settings.visionKey,
        }),
        [
            settings.apiKey,
            settings.visionKey,
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
            // one the learner did, done again as it was, settings and all
            if (offer.again) {
                const { session, exercise, fresh } = offer.again;
                return { ...(await replayExercise(session, exercise, learner, fresh)), usage: [] };
            }
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
                // one made from the tutor's brief alone reviews no lessons
                offer.practises_lesson === false ? [] : undefined,
            );
        },
        [settings, wordsOfSet, learner],
    );
    // a mock exam the tutor offered is started, and opened in the tab of evaluations
    const [openingEvaluation, setOpeningEvaluation] = useState<{ evaluation: Evaluation; nonce: number } | null>(
        null,
    );
    const startOfferedEvaluation = useCallback(
        (exam: EvaluationOffer) => {
            startEvaluation(settings.language, exam.level, exam.size, exam.timed).then(
                (evaluation) => {
                    setOpeningEvaluation({ evaluation, nonce: Date.now() });
                    setActivity("evaluations");
                },
                (failed: Error) => void tell(t("The mock exam could not be started."), failed.message),
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

    /** Opens a panel on the right, or closes it if it is shown; one behind the left is brought forward. */
    function togglePanel(wanted: Panel) {
        if (panel === wanted && behind !== "right") {
            setOpenPanel(null);
        } else {
            setOpenPanel(wanted);
            setFront("right");
        }
    }

    // Back closes the side in front, the one opened last, and then the other one
    const leftOpen = libraryOpen || logsOpen;
    useBack("panel", () => {
        if (panel !== null && (!leftOpen || front === "right")) {
            setOpenPanel(null);
            setFront("left");
        } else {
            setLogsOpen(false);
            setLibraryOpen(false);
            setFront("right");
        }
    }, leftOpen || panel !== null);
    useBack("window", () => setAsked(null), asked !== null);

    /** Opens the library or the logs on the left, or closes it if it is shown, as `togglePanel` does on the right. */
    function toggleLeft(logs: boolean) {
        const shown = (logs ? logsOpen : libraryOpen && !logsOpen) && behind !== "left";
        if (logs) {
            setLogsOpen(!shown);
        } else {
            setLibraryOpen(!shown);
            setLogsOpen(false);
        }
        if (!shown) {
            setFront("left");
        }
    }

    /**
     * Does an exercise of a session that is over again, in Practice: exactly
     * as it was, or, if `fresh`, with the same settings and made anew.
     */
    function replay(session: PracticeSession, exercise: string, fresh = false) {
        replayExercise(session.id, exercise, learner, fresh).then(
            (again) => {
                setResuming({ session: again, nonce: Date.now() });
                setActivity("practice");
                setLogsRevision((revision) => revision + 1);
            },
            (failed: Error) => void tell(t("The exercise could not be done again."), failed.message),
        );
    }

    function openSettings(tab: SettingsTab) {
        setSettingsTab(tab);
        setOpenPanel("settings");
        setFront("right");
    }

    function updateSettings(next: Settings) {
        setSettings(next);
        saveSettings(next);
    }

    return (
        <WritingChecks language={settings.language}>
            <div className="app">
                <aside className="side-panel left" hidden={!logsOpen || behind === "left"}>
                    <SidePanel
                        title={t("Logs")}
                        // the logs take the place of the library, and closing them closes the left side
                        onClose={() => {
                            setLogsOpen(false);
                            setLibraryOpen(false);
                        }}
                        flush
                        tabs={
                            <div className="tabs" role="tablist">
                                <button
                                    role="tab"
                                    aria-selected={logsTab === "logs"}
                                    onClick={() => setLogsTab("logs")}
                                >
                                    {t("Logs")}
                                </button>
                                <button
                                    role="tab"
                                    aria-selected={logsTab === "memories"}
                                    onClick={() => setLogsTab("memories")}
                                >
                                    {t("Memories")}
                                </button>
                                <button
                                    role="tab"
                                    aria-selected={logsTab === "exercises"}
                                    onClick={() => setLogsTab("exercises")}
                                >
                                    {t("Exercises")}
                                </button>
                                <button
                                    role="tab"
                                    aria-selected={logsTab === "favourites"}
                                    onClick={() => setLogsTab("favourites")}
                                >
                                    {t("Favourites")}
                                </button>
                                <button
                                    role="tab"
                                    aria-selected={logsTab === "sessions"}
                                    onClick={() => setLogsTab("sessions")}
                                >
                                    {t("Practices")}
                                </button>
                                <button
                                    role="tab"
                                    aria-selected={logsTab === "evaluations"}
                                    onClick={() => setLogsTab("evaluations")}
                                >
                                    {t("Evaluations")}
                                </button>
                            </div>
                        }
                    >
                        <div className="tab-panel" role="tabpanel" hidden={logsTab !== "logs"}>
                            <LogsPanel
                                active={logsOpen && logsTab === "logs"}
                                revision={logsRevision}
                                onOpenBook={openBook}
                            />
                        </div>
                        <div className="tab-panel" role="tabpanel" hidden={logsTab !== "memories"}>
                            {memoriesShown && <MemoryList revision={memoriesRevision} />}
                        </div>
                        <div className="tab-panel" role="tabpanel" hidden={logsTab !== "exercises"}>
                            <ExercisesDone
                                active={logsOpen && logsTab === "exercises"}
                                language={settings.language}
                                revision={logsRevision}
                                onReplay={replay}
                            />
                        </div>
                        <div className="tab-panel" role="tabpanel" hidden={logsTab !== "favourites"}>
                            <ExercisesDone
                                active={logsOpen && logsTab === "favourites"}
                                language={settings.language}
                                revision={logsRevision}
                                onReplay={replay}
                                favouritesOnly
                            />
                        </div>
                        <div className="tab-panel" role="tabpanel" hidden={logsTab !== "evaluations"}>
                            <EvaluationsDone active={logsOpen && logsTab === "evaluations"} revision={logsRevision} />
                        </div>
                        <div className="tab-panel" role="tabpanel" hidden={logsTab !== "sessions"}>
                            <PracticeSessions
                                active={logsOpen && logsTab === "sessions"}
                                language={settings.language}
                                revision={logsRevision}
                                onResume={(session) => {
                                    setResuming({ session, nonce: Date.now() });
                                    setActivity("practice");
                                }}
                            />
                        </div>
                    </SidePanel>
                </aside>
                <aside className="side-panel left" hidden={!libraryOpen || logsOpen || behind === "left"}>
                    <SidePanel
                        title={t("Library")}
                        onClose={() => setLibraryOpen(false)}
                        flush
                        tabs={
                            <div className="tabs" role="tablist">
                                <button
                                    role="tab"
                                    aria-selected={sidebarTab === "vocabulary"}
                                    onClick={() => setSidebarTab("vocabulary")}
                                >
                                    {t("Words")}
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
                                            {ankiWordCount}
                                        </span>
                                    </button>
                                )}
                                <button
                                    role="tab"
                                    aria-selected={sidebarTab === "books"}
                                    onClick={() => setSidebarTab("books")}
                                >
                                    {t("Books")}
                                    <span className="count">
                                        {booksState.status === "ready" && booksState.books.length > 0
                                            && booksState.books.length}
                                    </span>
                                </button>
                                <button
                                    role="tab"
                                    aria-selected={sidebarTab === "chat"}
                                    onClick={() => setSidebarTab("chat")}
                                >
                                    {t("Chat")}
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
                                    onDecks={() => setDecksRevision((revision) => revision + 1)}
                                />
                            </div>
                        )}
                        <div className="tab-panel" role="tabpanel" hidden={sidebarTab !== "vocabulary"}>
                            <VocabularyList
                                active={libraryOpen && sidebarTab === "vocabulary"}
                                language={settings.language}
                                into={settings.translateInto}
                                translations={wordTranslations}
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
                        <div className="tab-panel" role="tabpanel" hidden={sidebarTab !== "books"}>
                            <BookList
                                state={booksState}
                                selectedId={bookId}
                                chosenVersions={chosenVersions}
                                adding={addingBook}
                                addError={bookError}
                                onSelect={openBook}
                                onAdd={takeBook}
                                onDelete={removeBook}
                                onRename={nameBook}
                                onEdit={setEditingBook}
                                onReload={loadBooks}
                            />
                            {editingBook && (
                                <BookVersionEditor
                                    sourceId={chosenVersion(editingBook, chosenVersions)}
                                    settings={settings}
                                    expand={(prompt) =>
                                        expandPrompt(
                                            prompt,
                                            words,
                                            settings.language,
                                            settings.level,
                                            settings.translateInto,
                                        )}
                                    onSettingsChange={updateSettings}
                                    sourceName={[
                                        editingBook.title,
                                        editingBook.versions?.find((version) =>
                                            version.id === chosenVersion(editingBook, chosenVersions)
                                        )?.name ?? t("Original"),
                                    ].join(" · ")}
                                    onClose={() => setEditingBook(null)}
                                    onMade={(version) => takeVersion(version, editingBook)}
                                    onStarted={(task) => {
                                        addTask(task);
                                        setEditingBook(null);
                                    }}
                                />
                            )}
                        </div>
                        {/* kept in place while hidden, so a reply still arriving is not cut off */}
                        <div className="tab-panel" role="tabpanel" hidden={sidebarTab !== "chat"}>
                            <Chat
                                list={
                                    <ChatList
                                        chats={chats}
                                        activeId={chat.id}
                                        onSelect={(id) => setChatStore((store) => selectChat(store, id))}
                                        onDelete={(id) =>
                                            setChatStore((store) =>
                                                deleteChat(store, id, settings.defaultContextId, settings.language)
                                            )}
                                        onNewChat={newChat}
                                    />
                                }
                                key={chat.id}
                                settings={settings}
                                onSettingsChange={updateSettings}
                                checksSlot={panel === "checks" && chatChecked ? panelSlot : null}
                                onCloseChecks={() => setOpenPanel(null)}
                                onEditQuestions={() => openSettings("questions")}
                                words={words}
                                loadWords={freshWordLists}
                                picked={picked}
                                onOpenSettings={() => openSettings("models")}
                                onUsage={addUsageEntry}
                                onReplied={() => setUsageRevision((revision) => revision + 1)}
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
                    </SidePanel>
                </aside>
                <main className="main">
                    {
                        /* Buttons that take each other's place are kept together: the panels on the left,
                        the activities, and the panels on the right. */
                    }
                    <header className="topbar-frame">
                        <div className="topbar">
                            <div className="topbar-side">
                                <div className="switch" role="group" aria-label={t("Panel on the left")}>
                                    <button
                                        className="icon-only"
                                        aria-pressed={libraryOpen && !logsOpen && behind !== "left"}
                                        onClick={() => toggleLeft(false)}
                                        title={t("Library")}
                                        aria-label={t("Library")}
                                    >
                                        <Icon name="library" />
                                    </button>
                                    <button
                                        className="icon-only"
                                        aria-pressed={logsOpen && behind !== "left"}
                                        onClick={() => toggleLeft(true)}
                                        title={t("Logs")}
                                        aria-label={t("Logs")}
                                    >
                                        <Icon name="logs" />
                                    </button>
                                </div>
                                <TaskSign tasks={tasks} />
                            </div>
                            <div className="switch activities" role="tablist" aria-label={t("Activity")}>
                                {ACTIVITY_TABS.map(([name, label]) => (
                                    <button
                                        key={name}
                                        role="tab"
                                        aria-selected={activity === name}
                                        onClick={() => setActivity(name)}
                                        title={t(label)}
                                    >
                                        <Icon name={name} />
                                        <span className="label">{t(label)}</span>
                                    </button>
                                ))}
                            </div>
                            <div className="topbar-side end">
                                <div className="switch" role="group" aria-label={t("Panel on the right")}>
                                    <button
                                        className="icon-only"
                                        aria-pressed={panel === "checks" && behind !== "right"}
                                        onClick={() => togglePanel("checks")}
                                        title={t("Checks")}
                                        aria-label={t("Checks")}
                                    >
                                        <Icon name="checks" />
                                    </button>
                                    <button
                                        className="icon-only"
                                        aria-pressed={panel === "usage" && behind !== "right"}
                                        onClick={() => togglePanel("usage")}
                                        title={t("Usage")}
                                        aria-label={t("Usage")}
                                    >
                                        <Icon name="usage" />
                                    </button>
                                    <button
                                        className="icon-only"
                                        aria-pressed={panel === "settings" && behind !== "right"}
                                        onClick={() => togglePanel("settings")}
                                        title={t("Settings")}
                                        aria-label={t("Settings")}
                                    >
                                        <Icon name="settings" />
                                    </button>
                                </div>
                                <button
                                    className="log-out icon-only"
                                    onClick={logOut}
                                    title={t("Log out (logged in as {user})", { user })}
                                    aria-label={t("Log out")}
                                >
                                    <Icon name="log-out" />
                                </button>
                            </div>
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
                            onOpenSettings={() => openSettings("models")}
                            onStartEvaluation={startOfferedEvaluation}
                            onOpenText={(id) => {
                                setTextId(id);
                                setActivity("texts");
                            }}
                            speakReplies={settings.speakReplies}
                            onSpeakReplies={(speakReplies) => updateSettings({ ...settings, speakReplies })}
                            onSpeak={speakMessage}
                            onTrace={(event) => {
                                // the tutor may have written down a strategy or an entry of its calendar
                                if (event.type === "done") {
                                    setMemoriesRevision((revision) => revision + 1);
                                }
                            }}
                            settings={settings}
                            onSettingsChange={updateSettings}
                            words={words}
                            checksSlot={panel === "checks" && activity === "tutor" ? panelSlot : null}
                            onCloseChecks={() => setOpenPanel(null)}
                            onEditQuestions={() => openSettings("questions")}
                            onCheckingUsage={addUsageEntry}
                        />
                    </div>
                    <div className="pane texts-pane" hidden={activity !== "texts"}>
                        <SideList label={t("Texts")} nothingOpen={textId === null}>
                            <TextList
                                texts={texts}
                                selectedId={textId}
                                onSelect={setTextId}
                                onNew={(handwritten) => {
                                    const id = newId();
                                    void saveText(id, "", "", settings.language, handwritten).then(() => {
                                        setTextsRevision((revision) => revision + 1);
                                        setTextId(id);
                                    });
                                }}
                                onDelete={(text) => {
                                    void ask(t("Delete “{name}”?", { name: text.title || t("Untitled") })).then(
                                        async (agreed) => {
                                            if (agreed) {
                                                await deleteText(text.id);
                                                setTextsRevision((revision) => revision + 1);
                                                // a correction deleted leaves its text open, to be corrected again
                                                setTextId((open) => (open === text.id ? text.corrects : open));
                                            }
                                        },
                                    );
                                }}
                            />
                        </SideList>
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
                                    words={words}
                                    onUsage={addUsageEntry}
                                    checksSlot={panel === "checks" && activity === "texts" ? panelSlot : null}
                                    onCloseChecks={() => setOpenPanel(null)}
                                    onEditQuestions={() => openSettings("questions")}
                                    correctionId={typeof texts === "string"
                                        ? null
                                        : texts.find((text) => text.corrects === textId)?.id ?? null}
                                    onSaved={() => setTextsRevision((revision) => revision + 1)}
                                    onOpenText={setTextId}
                                    onCorrected={() => setTextsRevision((revision) => revision + 1)}
                                    onTask={addTask}
                                    onDeleteCorrection={(correction) => {
                                        void ask(t("Delete the correction?")).then(async (agreed) => {
                                            if (agreed) {
                                                await deleteText(correction.id);
                                                setTextsRevision((revision) => revision + 1);
                                            }
                                        });
                                    }}
                                />
                            )
                            : (
                                <div className="empty">
                                    <h2>{t("No text open")}</h2>
                                    <p>{t("Open one of your texts, or start a new one.")}</p>
                                </div>
                            )}
                    </div>
                    <div className="pane" hidden={activity !== "books"}>
                        <BookReader
                            bookId={bookId}
                            active={activity === "books"}
                            besides={`${libraryOpen || logsOpen}:${panel}:${behind}:${sidesFit}`}
                            names={readNames}
                            onPlay={(selection) =>
                                bookId && setListening({ source: bookSource(bookId, selection), nonce: Date.now() })}
                            noteAsked={noteAsked}
                        />
                    </div>
                    <div className="pane" hidden={activity !== "practice"}>
                        {practiceShown && (
                            <Practice
                                resuming={resuming}
                                active={activity === "practice"}
                                settings={settings}
                                words={words}
                                checksSlot={panel === "checks" && activity === "practice" ? panelSlot : null}
                                onCloseChecks={() => setOpenPanel(null)}
                                onEditQuestions={() => openSettings("questions")}
                                learner={learner}
                                wordsOfSet={wordsOfSet}
                                topicsRevision={topicsRevision}
                                embedding={embeddingTask}
                                onUsage={addPracticeUsage}
                                onTask={addTask}
                                onChangeSettings={updateSettings}
                                onOpenSettings={() => openSettings("models")}
                                onReadAloud={(sessionId, exercise, number, text) =>
                                    setListening({
                                        source: exerciseSource(sessionId, exercise, number, text),
                                        nonce: Date.now(),
                                    })}
                            />
                        )}
                    </div>
                    <div className="pane" hidden={activity !== "evaluations"}>
                        {evaluationsShown && (
                            <Evaluations
                                opening={openingEvaluation}
                                settings={settings}
                                words={words}
                                checksSlot={panel === "checks" && activity === "evaluations" ? panelSlot : null}
                                onCloseChecks={() => setOpenPanel(null)}
                                onEditQuestions={() => openSettings("questions")}
                                learner={learner}
                                onUsage={addEvaluationUsage}
                                onTask={addTask}
                                onChangeSettings={updateSettings}
                                onOpenSettings={openSettings}
                                onReadAloud={(sessionId, exercise, number, text) =>
                                    setListening({
                                        source: exerciseSource(sessionId, exercise, number, text, "evaluation"),
                                        nonce: Date.now(),
                                    })}
                                onEnded={() => setLogsRevision((revision) => revision + 1)}
                            />
                        )}
                    </div>
                </main>
                <aside
                    className="side-panel"
                    hidden={panel === null || behind === "right"}
                    ref={setPanelSlot}
                >
                    {panel === "checks" && !CHECKED_ACTIVITIES.includes(activity) && !chatChecked && (
                        <SidePanel
                            title={t("Sentence checks")}
                            onClose={() => setOpenPanel(null)}
                        >
                            <p className="checks-note">
                                {t("Nothing is written here. Open the chat in the library to see the checks of what you write in it.")}
                            </p>
                        </SidePanel>
                    )}
                    {panel === "usage" && (
                        <UsagePanel
                            revision={usageRevision}
                            currentLabel={activity === "tutor"
                                ? t("Tutor")
                                : activity === "practice"
                                ? t("Practice")
                                : activity === "evaluations"
                                ? t("Evaluations")
                                : chatShown
                                ? t("This chat")
                                : null}
                            chatId={activity === "tutor"
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
                            sets={sets}
                            tab={settingsTab}
                            onTab={setSettingsTab}
                            onChange={updateSettings}
                            onClose={() => setOpenPanel(null)}
                        />
                    )}
                </aside>
                {/* floats over the page, which keeps its width */}
                {asked && (
                    <section
                        className={panel === null || behind === "right"
                            ? "floating-window"
                            : "floating-window beside-panel"}
                        aria-label={t("Ask about it")}
                    >
                        <SubChat
                            key={asked.nonce}
                            translated={asked.translated}
                            asking={asking}
                            onUsage={addUsageEntry}
                            onTask={addTask}
                            onClose={() => setAsked(null)}
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
                    onNote={(selection, quote) => setNoteAsked({ selection, quote, nonce: Date.now() })}
                    onChat={(translated) => {
                        setAsked({ translated, nonce: Date.now() });
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
