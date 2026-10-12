// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { useCallback, useEffect, useRef, useState } from "react";

import { Chat } from "./components/Chat";
import { ChatList } from "./components/ChatList";
import { SettingsPanel } from "./components/SettingsPanel";
import { TextList } from "./components/TextList";
import { TextStudio } from "./components/TextStudio";
import { UsagePanel } from "./components/UsagePanel";
import { WordList } from "./components/WordList";
import { fetchKnownWords } from "./lib/anki";
import {
    activeChat,
    type ChatStore,
    deleteChat,
    listedChats,
    loadChats,
    saveChats,
    selectChat,
    startChat,
    updateChat,
} from "./lib/chats";
import type { ChatMessage } from "./lib/openrouter";
import { loadSettings, saveSettings, type Settings } from "./lib/settings";
import { fetchTexts, type SavedText } from "./lib/texts";
import { addUsage, loadUsage, saveUsage, type UsageEntry } from "./lib/usage";
import type { Word } from "./lib/words";

export type WordsState =
    | { status: "loading" }
    | { status: "error"; message: string }
    | { status: "ready"; words: Word[] };

export type TextsState =
    | { status: "loading" }
    | { status: "error"; message: string }
    | { status: "ready"; texts: SavedText[] };

export function App() {
    const [settings, setSettings] = useState<Settings>(loadSettings);
    const [settingsOpen, setSettingsOpen] = useState(false);
    const [wordsState, setWordsState] = useState<WordsState>({ status: "loading" });
    // text a clicked word adds to the message being written
    const [picked, setPicked] = useState<{ word: string; nonce: number } | null>(null);
    const [usage, setUsage] = useState<UsageEntry[]>(loadUsage);
    // on a narrow window the panel would cover the chat
    const [usageOpen, setUsageOpen] = useState(() => window.innerWidth > 1000);
    const [chatStore, setChatStore] = useState<ChatStore>(() => loadChats(settings.defaultContextId));
    const [sidebarTab, setSidebarTab] = useState<"words" | "chats" | "texts">("words");
    const [activity, setActivity] = useState<"chat" | "texts">("chat");
    const [textsState, setTextsState] = useState<TextsState>({ status: "loading" });
    const [selectedTextId, setSelectedTextId] = useState<string | null>(null);
    const chat = activeChat(chatStore);
    const chats = listedChats(chatStore);
    const words = wordsState.status === "ready" ? wordsState.words : [];
    const texts = textsState.status === "ready" ? textsState.texts : [];
    const selectedText = texts.find((text) => text.id === selectedTextId) ?? null;

    useEffect(() => saveUsage(usage), [usage]);

    // A reply changes the chats many times a second while it arrives, so they
    // are written once it pauses, and when the page is left.
    const latestChats = useRef(chatStore);
    latestChats.current = chatStore;
    useEffect(() => {
        const timer = setTimeout(() => saveChats(chatStore), 300);
        return () => clearTimeout(timer);
    }, [chatStore]);
    useEffect(() => {
        const save = () => saveChats(latestChats.current);
        window.addEventListener("pagehide", save);
        return () => window.removeEventListener("pagehide", save);
    }, []);

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
        setChatStore((store) => startChat(store, settings.defaultContextId));
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

    function updateSettings(next: Settings) {
        setSettings(next);
        saveSettings(next);
    }

    return (
        <div className={usageOpen ? "app with-usage" : "app"}>
            <aside className="sidebar">
                <div className="tabs" role="tablist">
                    <button
                        role="tab"
                        aria-selected={sidebarTab === "words"}
                        onClick={() => setSidebarTab("words")}
                    >
                        Known words
                        <span className="count">{wordsState.status === "ready" && wordsState.words.length}</span>
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
                {/* kept in place while hidden, so the word filter and sort order survive a visit to the chats */}
                <div className="tab-panel" role="tabpanel" hidden={sidebarTab !== "words"}>
                    <WordList
                        state={wordsState}
                        onReload={loadWords}
                        onPick={(word) => setPicked({ word: word.word, nonce: Date.now() })}
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
                        onDelete={(id) => setChatStore((store) => deleteChat(store, id, settings.defaultContextId))}
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
            </aside>
            <main className="main">
                <header className="topbar">
                    <div className="switch" role="tablist" aria-label="Activity">
                        <button role="tab" aria-selected={activity === "chat"} onClick={() => setActivity("chat")}>
                            Chat
                        </button>
                        <button role="tab" aria-selected={activity === "texts"} onClick={() => setActivity("texts")}>
                            Texts
                        </button>
                    </div>
                    <span className="model" title="Model">{settings.model}</span>
                    <button onClick={() => setUsageOpen(!usageOpen)}>Usage</button>
                    <button onClick={() => setSettingsOpen(true)}>Settings</button>
                </header>
                {/* both stay in place while hidden, so a reply or a text still arriving is not cut off */}
                <div className="pane" hidden={activity !== "chat"}>
                    <Chat
                        key={chat.id}
                        settings={settings}
                        words={words}
                        picked={activity === "chat" ? picked : null}
                        onOpenSettings={() => setSettingsOpen(true)}
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
                        picked={activity === "texts" ? picked : null}
                        selected={selectedText}
                        onSelect={setSelectedTextId}
                        onTextsChange={changeTexts}
                        onUsage={addUsageEntry}
                        onOpenSettings={() => setSettingsOpen(true)}
                        storageError={textsState.status === "error" ? textsState.message : null}
                    />
                </div>
            </main>
            {usageOpen && (
                <UsagePanel
                    entries={usage}
                    currentLabel={activity === "chat" ? "This chat" : "This text"}
                    chatId={activity === "chat" ? chat.id : `text:${selectedTextId}`}
                    onClose={() => setUsageOpen(false)}
                />
            )}
            {settingsOpen && (
                <SettingsPanel
                    settings={settings}
                    onChange={updateSettings}
                    onClose={() => setSettingsOpen(false)}
                />
            )}
        </div>
    );
}
