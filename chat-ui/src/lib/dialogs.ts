// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { t } from "./i18n";

/**
 * What the app asks or tells the learner in a dialog of its own, over the
 * page, in place of those of the browser: one at a time, the others
 * waiting their turn.
 */
export interface Dialog {
    /** What is asked or told, in a sentence. */
    message: string;
    /** What it is about, such as the text of what would be removed, shown under the message. */
    detail?: string;
    /** What the button that agrees says, such as "Delete". */
    confirm: string;
    /** What the button that declines says, or null when there is only something to be told. */
    cancel: string | null;
    /** Whether agreeing removes something, which the button shows. */
    danger: boolean;
}

interface Waiting {
    dialog: Dialog;
    answer: (agreed: boolean) => void;
}

const waiting: Waiting[] = [];
const listeners = new Set<(shown: Dialog | null) => void>();

function shownChanged() {
    const shown = waiting[0]?.dialog ?? null;
    listeners.forEach((listener) => listener(shown));
}

function open(dialog: Dialog): Promise<boolean> {
    return new Promise((answer) => {
        waiting.push({ dialog, answer });
        if (waiting.length === 1) {
            shownChanged();
        }
    });
}

/**
 * Asks the learner to agree to something, such as removing what they
 * kept, and resolves with whether they did.
 */
export function ask(
    message: string,
    { detail, confirm = t("Delete"), cancel = t("Cancel"), danger = true }: Partial<Omit<Dialog, "message">> = {},
): Promise<boolean> {
    return open({ message, detail, confirm, cancel, danger });
}

/** Tells the learner something, such as what went wrong, and resolves once they have read it. */
export async function tell(message: string, detail?: string): Promise<void> {
    await open({ message, detail, confirm: t("OK"), cancel: null, danger: false });
}

/** Answers the dialog shown, which shows the next one if any is waiting. */
export function answer(agreed: boolean) {
    const answered = waiting.shift();
    answered?.answer(agreed);
    shownChanged();
}

/** Has `listener` told the dialog shown, now and whenever it changes, until what this returns is called. */
export function onDialog(listener: (shown: Dialog | null) => void): () => void {
    listeners.add(listener);
    listener(waiting[0]?.dialog ?? null);
    return () => listeners.delete(listener);
}
