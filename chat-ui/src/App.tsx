// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { BookList } from "./components/BookList";
import { BookReader } from "./components/BookReader";
import { Chat } from "./components/Chat";
import { ChatList } from "./components/ChatList";
import { Practice } from "./components/Practice";
import { SelectionTools } from "./components/SelectionTools";
import { SetEditor } from "./components/SetEditor";
import { SettingsPanel, type SettingsTab } from "./components/SettingsPanel";
import { SidePanel } from "./components/SidePanel";
import { SpeechPlayer } from "./components/SpeechPlayer";
import { SubChat } from "./components/SubChat";
import { TaskSign } from "./components/TaskSign";
import { UsagePanel } from "./components/UsagePanel";
import { VocabularyList } from "./components/VocabularyList";
import { WordList } from "./components/WordList";
import { WritingChecks } from "./components/WritingChecks";
import { fetchKnownWords, seesAnkiWords } from "./lib/anki";
import { useAnkiImport } from "./lib/ankiImport";
import {
    addBook,
    changeReading,
    chooseFolder,
    deleteBook,
    fetchBooks,
    fetchFolderSync,
    type FolderSync,
    type ListedBook,
    loadReading,
    syncFolder,
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
import { loadLayout, type Panel, saveLayout } from "./lib/layout";
import type { ChatMessage } from "./lib/openrouter";
import { fetchGenerationUsage } from "./lib/openrouter";
import { type Learner, practiceUsage, USAGE_ID as PRACTICE_USAGE_ID } from "./lib/practice";
import { logOut } from "./lib/session";
import { deleteSet, fetchSets, membersOf, newSet, saveSet, wordLists, type WordSet } from "./lib/sets";
import { applyAppearance, saveSettings, type Settings } from "./lib/settings";
import {
    bookSource,
    exerciseSource,
    messageSource,
    speechInstructions,
    type SpeechSource,
    type Voice,
} from "./lib/speaking";
import { type BackgroundTask, fetchTasks, TASKS_INTERVAL_MS, withTask } from "./lib/tasks";
import type { Asking, Translated } from "./lib/translate";
import {
    forgetLegacyUsage,
    legacyUsage,
    profileUsage,
    recordUsage,
    type UsageCategory,
    type UsageEntry,
} from "./lib/usage";
import { fetchVocabulary, type Vocabulary } from "./lib/vocabulary";
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

/** What the usage of each kind of background task is counted under. */
const TASK_CATEGORIES: Record<string, UsageCategory> = {
    words: "vocabulary",
    embeddings: "vocabulary",
    speech: "speech",
    icon: "practice",
};

export function App({ user, initialSettings, initialChats }: Props) {
    const [settings, setSettings] = useState<Settings>(initialSettings);
    // the panel on the left, with the words, the chats and the books
    const [libraryOpen, setLibraryOpen] = useState(() => loadLayout().libraryOpen);
    // the panels on the right share one place, so one is shown at a time
    const [openPanel, setOpenPanel] = useState<Panel | "subchat" | null>(() => loadLayout().panel);
    // The panels are found as they were left the next time the page is
    // opened, but for the chat about a selection, which is gone by then.
    useEffect(
        () => saveLayout({ libraryOpen, panel: openPanel === "subchat" ? null : openPanel }),
        [libraryOpen, openPanel],
    );
    // the selection the chat at the side is about, with a number that tells it from the one before
    const [asked, setAsked] = useState<{ translated: Translated; nonce: number } | null>(null);
    const [settingsTab, setSettingsTab] = useState<SettingsTab>("general");
    // where the chat puts the sentence checks, which are made of what it knows
    const [panelSlot, setPanelSlot] = useState<HTMLElement | null>(null);
    const [wordsState, setWordsState] = useState<WordsState>({ status: "loading" });
    // the Anki words are those of one user, and the tab with them is that user's alone
    const ankiWords = seesAnkiWords(user);
    // text a clicked word adds to the message being written
    const [picked, setPicked] = useState<{ word: string; nonce: number } | null>(null);
    // tells the usage the server has from what it had before something was recorded
    const [usageRevision, setUsageRevision] = useState(0);
    const [chatStore, setChatStore] = useState<ChatStore>(() =>
        storeOf(initialChats, initialSettings.defaultContextId, initialSettings.language)
    );
    const [sidebarTab, setSidebarTab] = useState<"words" | "vocabulary" | "chats" | "books">(
        "vocabulary",
    );
    // how many words the vocabulary has, once it has been listed
    const [vocabularyCount, setVocabularyCount] = useState<number | null>(null);
    const [activity, setActivity] = useState<"chat" | "books" | "practice">("chat");
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

    // The server takes the books of a folder by itself. It is asked how that
    // is going, often while it looks through the folder and seldom
    // otherwise, and the books are listed again when it has changed them.
    const [bookSync, setBookSync] = useState<FolderSync | null>(null);
    const syncRevision = useRef<number | null>(null);
    const followSync = useCallback((sync: FolderSync) => {
        setBookSync(sync);
        if (syncRevision.current !== null && syncRevision.current !== sync.revision) {
            fetchBooks().then((books) => setBooksState({ status: "ready", books }), () => undefined);
        }
        syncRevision.current = sync.revision;
    }, []);
    const syncing = bookSync?.state === "syncing";
    useEffect(() => {
        let stopped = false;
        const look = () => fetchFolderSync().then((sync) => stopped || followSync(sync), () => undefined);
        look();
        const timer = setInterval(look, syncing ? 1500 : 15000);
        return () => {
            stopped = true;
            clearInterval(timer);
        };
    }, [syncing, followSync]);

    function tellSync(asked: Promise<FolderSync>) {
        setBookError(null);
        asked.then(followSync, (error: Error) => setBookError(error.message));
    }

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
    }, [ankiWords]);

    useEffect(loadWords, [loadWords]);

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
            // Audio comes without what it cost, which is looked up
            // afterwards, by what each request for it goes by.
            const { apiKey, model } = latestVoice.current;
            for (const { generation } of task.result) {
                if (generation && apiKey) {
                    void fetchGenerationUsage(apiKey, generation).then((used) =>
                        addUsageEntry({
                            id: generation,
                            at: Date.now(),
                            category: "speech",
                            chatId: "speech",
                            model: used?.model ?? model,
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

    // the sentence checks belong to the chat, and the chat at the side to a selection
    const panel = (openPanel === "checks" && activity !== "chat") || (openPanel === "subchat" && !asked)
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
    const translating = useMemo<Asking>(
        () => ({ ...asking, model: settings.translationModel || asking.model }),
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
                <aside className="side-panel left" hidden={!libraryOpen}>
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
                                    <span className="count">{vocabularyCount ?? vocabulary?.words.length}</span>
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
                                sync={bookSync}
                                onFolder={(folder) => tellSync(chooseFolder(folder))}
                                onSync={() => tellSync(syncFolder())}
                                onSelect={openBook}
                                onAdd={takeBook}
                                onDelete={removeBook}
                                onReload={loadBooks}
                            />
                        </div>
                    </SidePanel>
                </aside>
                <main className="main">
                    <header className="topbar">
                        <button aria-pressed={libraryOpen} onClick={() => setLibraryOpen(!libraryOpen)}>Library</button>
                        <div className="switch" role="tablist" aria-label="Activity">
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
                        </div>
                        <TaskSign tasks={tasks} />
                        {activity === "chat" && (
                            <button
                                aria-pressed={panel === "checks"}
                                onClick={() => togglePanel("checks")}
                            >
                                Checks
                            </button>
                        )}
                        <button aria-pressed={panel === "usage"} onClick={() => togglePanel("usage")}>Usage</button>
                        <button aria-pressed={panel === "settings"} onClick={() => togglePanel("settings")}>
                            Settings
                        </button>
                        <button onClick={logOut} title={`Logged in as ${user}`}>Log out</button>
                    </header>
                    {/* stays in place while hidden, so a reply still arriving is not cut off */}
                    <div className="pane" hidden={activity !== "chat"}>
                        <Chat
                            key={chat.id}
                            settings={settings}
                            onSettingsChange={updateSettings}
                            checksSlot={panel === "checks" ? panelSlot : null}
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
                            onOpenSettings={() => openSettings("general")}
                            onReadAloud={(sessionId, exercise, number, text) =>
                                setListening({
                                    source: exerciseSource(sessionId, exercise, number, text),
                                    nonce: Date.now(),
                                })}
                        />
                    </div>
                </main>
                <aside
                    className="side-panel"
                    hidden={panel === null}
                    ref={setPanelSlot}
                >
                    {panel === "usage" && (
                        <UsagePanel
                            revision={usageRevision}
                            currentLabel={activity === "practice" ? "Practice" : "This chat"}
                            chatId={activity === "practice" ? PRACTICE_USAGE_ID : chat.id}
                            onClose={() => setOpenPanel(null)}
                        />
                    )}
                    {panel === "subchat" && asked && (
                        <SubChat
                            key={asked.nonce}
                            translated={asked.translated}
                            asking={asking}
                            onUsage={addUsageEntry}
                            onClose={() => setOpenPanel(null)}
                        />
                    )}
                    {panel === "settings" && (
                        <SettingsPanel
                            settings={settings}
                            ankiWords={ankiWords}
                            sets={sets}
                            tab={settingsTab}
                            onTab={setSettingsTab}
                            onChange={updateSettings}
                            onClose={() => setOpenPanel(null)}
                        />
                    )}
                </aside>
                <SelectionTools
                    translating={translating}
                    describing={asking}
                    decisionModel={settings.profileModel}
                    onUsage={addUsageEntry}
                    onTask={(task) => setTasks((current) => withTask(current, task))}
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
