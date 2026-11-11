// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import "./styles.css";

import { StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import { DialogHost } from "./components/DialogHost";
import { Login } from "./components/Login";
import { goBack } from "./lib/back";
import { fetchChats, type StoredChat } from "./lib/chats";
import { t } from "./lib/i18n";
import { dropBrowserCopies, nativeStore } from "./lib/offlineCache";
import { currentSession, logOut, onSessionChange } from "./lib/session";
import { fetchSettings, type Settings } from "./lib/settings";

/** What whoever is logged in has kept on the server, which the app starts from. */
interface Kept {
    user: string;
    settings: Settings;
    chats: StoredChat[];
}

/** The app for whoever is logged in, and the login for everyone else. */
function Root() {
    const [session, setSession] = useState(currentSession);
    const [kept, setKept] = useState<Kept | null>(null);
    const [error, setError] = useState<string | null>(null);
    useEffect(() => onSessionChange(setSession), []);

    const user = session?.user;
    useEffect(() => {
        setKept(null);
        setError(null);
        if (!user) {
            return;
        }
        let current = true;
        Promise.all([fetchSettings(), fetchChats()]).then(
            ([settings, chats]) => current && setKept({ user, settings, chats }),
            (failure: Error) => current && setError(failure.message),
        );
        return () => {
            current = false;
        };
    }, [user]);

    if (!session) {
        return <Login />;
    }
    if (error) {
        return (
            <main className="login">
                <form>
                    <p className="error">{error}</p>
                    <button type="button" onClick={() => window.location.reload()}>{t("Try again")}</button>
                    <button type="button" onClick={logOut}>{t("Log out")}</button>
                </form>
            </main>
        );
    }
    if (!kept || kept.user !== session.user) {
        return <main className="login">{t("Loading…")}</main>;
    }
    // a user who logs in after another starts with nothing of the other's on show
    return <App key={kept.user} user={kept.user} initialSettings={kept.settings} initialChats={kept.chats} />;
}

// the Back of the phone, in the Android app, closes what is open in the page before it leaves the app
window.lansiBack = goBack;

// The app is kept on the device, to open without a connection: by the
// Android app, once for both its addresses, and in a browser by a service
// worker (public/sw.js).
if (nativeStore()) {
    dropBrowserCopies().catch(() => undefined);
} else if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register(`${import.meta.env.BASE_URL}sw.js`).catch((caught: unknown) =>
        console.warn("the app cannot be kept offline:", caught)
    );
}

createRoot(document.getElementById("root")!).render(
    <StrictMode>
        <Root />
        <DialogHost />
    </StrictMode>,
);
