// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { Chat } from "./components/Chat";
import { ChatList } from "./components/ChatList";
import { SetEditor } from "./components/SetEditor";
import { SettingsPanel, type SettingsTab } from "./components/SettingsPanel";
import { SidePanel } from "./components/SidePanel";
import { TextList } from "./components/TextList";
import { TextStudio } from "./components/TextStudio";
import { UsagePanel } from "./components/UsagePanel";
import { VocabularyList } from "./components/VocabularyList";
import { WordList } from "./components/WordList";
import { fetchKnownWords } from "./lib/anki";
import { useAnkiImport } from "./lib/ankiImport";
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
import { loadLayout, type Panel, saveLayout } from "./lib/layout";
import type { ChatMessage } from "./lib/openrouter";
import { logOut } from "./lib/session";
import { deleteSet, fetchSets, newSet, saveSet, wordLists, type WordSet } from "./lib/sets";
import { saveSettings, type Settings } from "./lib/settings";
import { fetchTexts, type SavedText } from "./lib/texts";
import { addUsage, loadUsage, saveUsage, type UsageEntry } from "./lib/usage";
import { fetchVocabulary, type Vocabulary } from "./lib/vocabulary";
import type { Word } from "./lib/words";

export type WordsState =
    | { status: "loading" }
    | { status: "error"; message: string }
    | { status: "ready"; words: Word[] };

export type TextsState =
    | { status: "loading" }
    | { status: "error"; message: string }
    | { status: "ready"; texts: SavedText[] };

interface Props {
    /** Who is logged in. */
    user: string;
    /** The settings and the chats as the server had them when the user came in. */
    initialSettings: Settings;
    initialChats: StoredChat[];
}

export function App({ user, initialSettings, initialChats }: Props) {
    const [settings, setSettings] = useState<Settings>(initialSettings);
    // the panel on the left, with the words, the chats and the texts
    const [libraryOpen, setLibraryOpen] = useState(() => loadLayout().libraryOpen);
    // the panels on the right share one place, so one is shown at a time
    const [openPanel, setOpenPanel] = useState<Panel | null>(() => loadLayout().panel);
    // the panels are found as they were left the next time the page is opened
    useEffect(() => saveLayout({ libraryOpen, panel: openPanel }), [libraryOpen, openPanel]);
    const [settingsTab, setSettingsTab] = useState<SettingsTab>("models");
    // where the chat puts the sentence checks, which are made of what it knows
    const [panelSlot, setPanelSlot] = useState<HTMLElement | null>(null);
    const [wordsState, setWordsState] = useState<WordsState>({ status: "loading" });
    // text a clicked word adds to the message being written
    const [picked, setPicked] = useState<{ word: string; nonce: number } | null>(null);
    const [usage, setUsage] = useState<UsageEntry[]>(loadUsage);
    const [chatStore, setChatStore] = useState<ChatStore>(() =>
        storeOf(initialChats, initialSettings.defaultContextId, initialSettings.language)
    );
    const [sidebarTab, setSidebarTab] = useState<"words" | "vocabulary" | "chats" | "texts">("vocabulary");
    // how many words the vocabulary has, once it has been listed
    const [vocabularyCount, setVocabularyCount] = useState<number | null>(null);
    const [activity, setActivity] = useState<"chat" | "texts">("chat");
    const [textsState, setTextsState] = useState<TextsState>({ status: "loading" });
    const [selectedTextId, setSelectedTextId] = useState<string | null>(null);
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
    const texts = textsState.status === "ready" ? textsState.texts : [];
    const selectedText = texts.find((text) => text.id === selectedTextId) ?? null;

    useEffect(() => saveUsage(usage), [usage]);

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

    const loadTexts = useCallback(() => {
        setTextsState({ status: "loading" });
        fetchTexts().then(
            (loaded) => setTextsState({ status: "ready", texts: loaded }),
            (error: Error) => setTextsState({ status: "error", message: error.message }),
        );
    }, []);

    useEffect(loadTexts, [loadTexts]);

    const changeTexts = useCallback(
        (change: (texts: SavedText[]) => SavedText[]) =>
            setTextsState((state) => ({
                status: "ready",
                texts: change(state.status === "ready" ? state.texts : []),
            })),
        [],
    );

    const addUsageEntry = useCallback(
        (entry: UsageEntry) => setUsage((current) => addUsage(current, entry)),
        [],
    );

    const loadWords = useCallback(() => {
        setWordsState({ status: "loading" });
        fetchKnownWords().then(
            (words) => setWordsState({ status: "ready", words }),
            (error: Error) => setWordsState({ status: "error", message: error.message }),
        );
    }, []);

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
        enabled: settings.importAnki,
        apiKey: settings.apiKey,
        model: settings.model,
        decisionModel: settings.profileModel,
        language: settings.language,
        ankiLanguage: settings.ankiLanguage,
        onUsage: useCallback(
            (used) =>
                addUsageEntry({
                    id: used.id,
                    at: Date.now(),
                    chatId: "vocabulary",
                    model: used.model,
                    promptTokens: used.input_tokens,
                    completionTokens: used.output_tokens,
                    cost: used.cost,
                }),
            [addUsageEntry],
        ),
        onImported: useCallback(() => setVocabularyRevision((revision) => revision + 1), []),
    });

    // the sentence checks belong to the chat
    const panel = openPanel === "checks" && activity !== "chat" ? null : openPanel;

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
                                Vocabulary
                                <span className="count">{vocabularyCount ?? vocabulary?.words.length}</span>
                            </button>
                            <button
                                role="tab"
                                aria-selected={sidebarTab === "words"}
                                onClick={() => setSidebarTab("words")}
                            >
                                Anki words
                                <span className="count">
                                    {wordsState.status === "ready" && wordsState.words.length}
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
                                aria-selected={sidebarTab === "texts"}
                                onClick={() => setSidebarTab("texts")}
                            >
                                Texts
                                <span className="count">{texts.length > 0 && texts.length}</span>
                            </button>
                        </div>
                    }
                >
                    {/* kept in place while hidden, so the word filter and sort order survive a visit to the chats */}
                    <div className="tab-panel" role="tabpanel" hidden={sidebarTab !== "words"}>
                        <WordList
                            state={wordsState}
                            onReload={loadWords}
                            onPick={(word) => setPicked({ word: word.word, nonce: Date.now() })}
                        />
                    </div>
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
                            importing={importing}
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
                    <div className="tab-panel" role="tabpanel" hidden={sidebarTab !== "texts"}>
                        <TextList
                            state={textsState}
                            selectedId={selectedTextId}
                            onSelect={(id) => {
                                setSelectedTextId(id);
                                setActivity("texts");
                            }}
                            onReload={loadTexts}
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
                        <button role="tab" aria-selected={activity === "texts"} onClick={() => setActivity("texts")}>
                            Texts
                        </button>
                    </div>
                    <span className="model" title="Model">{settings.model}</span>
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
                {/* both stay in place while hidden, so a reply or a text still arriving is not cut off */}
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
                        onOpenSettings={() => openSettings("models")}
                        onUsage={addUsageEntry}
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
                    <TextStudio
                        settings={settings}
                        words={words}
                        loadWords={freshWordLists}
                        picked={activity === "texts" ? picked : null}
                        selected={selectedText}
                        onSelect={setSelectedTextId}
                        onTextsChange={changeTexts}
                        onUsage={addUsageEntry}
                        onOpenSettings={() => openSettings("models")}
                        storageError={textsState.status === "error" ? textsState.message : null}
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
                        entries={usage}
                        currentLabel={activity === "chat" ? "This chat" : "This text"}
                        chatId={activity === "chat" ? chat.id : `text:${selectedTextId}`}
                        onClose={() => setOpenPanel(null)}
                    />
                )}
                {panel === "settings" && (
                    <SettingsPanel
                        settings={settings}
                        tab={settingsTab}
                        onTab={setSettingsTab}
                        onChange={updateSettings}
                        onClose={() => setOpenPanel(null)}
                    />
                )}
            </aside>
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
    );
}
