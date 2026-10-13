// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { type FormEvent, useState } from "react";

import { logIn } from "../lib/session";

/** Asks for a name and a password. Shown until someone is logged in. */
export function Login() {
    const [user, setUser] = useState("");
    const [password, setPassword] = useState("");
    const [error, setError] = useState<string | null>(null);
    const [busy, setBusy] = useState(false);

    async function submit(event: FormEvent) {
        event.preventDefault();
        setBusy(true);
        setError(null);
        try {
            await logIn(user.trim(), password);
        } catch (failure) {
            setError((failure as Error).message);
            setBusy(false);
        }
    }

    return (
        <main className="login">
            <form onSubmit={submit}>
                <h1>
                    <img src="/lansi.svg" alt="" width={32} height={32} />
                    Lansi
                </h1>
                <label className="field">
                    <span>Name</span>
                    <input
                        type="text"
                        autoComplete="username"
                        autoFocus
                        spellCheck={false}
                        value={user}
                        onChange={(event) => setUser(event.target.value)}
                    />
                </label>
                <label className="field">
                    <span>Password</span>
                    <input
                        type="password"
                        autoComplete="current-password"
                        value={password}
                        onChange={(event) => setPassword(event.target.value)}
                    />
                </label>
                {error && <p className="error">{error}</p>}
                <button className="primary" disabled={busy || !user.trim() || !password}>
                    {busy ? "Logging in…" : "Log in"}
                </button>
            </form>
        </main>
    );
}
