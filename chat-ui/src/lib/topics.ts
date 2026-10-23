// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { t } from "./i18n";
import { type ModelChoice, modelRequest } from "./models";
import { checkerFetch } from "./session";
import type { BackgroundTask } from "./tasks";
import { describeError } from "./translate";

/** A topic a session of practice can be about. */
export interface Topic {
    id: string;
    title: string;
    description: string;
    /** In seconds since the epoch. */
    created_at: number;
    /** Whether its icon has been made. */
    icon: boolean;
}

async function call<Reply>(path: string, init: RequestInit = {}, apiKey = ""): Promise<Reply> {
    let response: Response;
    try {
        response = await checkerFetch(path, {
            ...init,
            // the server asks the models with the key; it is not kept there
            headers: apiKey ? { "X-OpenRouter-Key": apiKey } : {},
        });
    } catch {
        throw new Error(t("The server cannot be reached."));
    }
    const reply = await response.json().catch(() => ({}));
    if (!response.ok) {
        throw new Error(describeError(reply.error, response.status));
    }
    return reply;
}

export async function fetchTopics(): Promise<Topic[]> {
    const { topics } = await call<{ topics: Topic[] }>("/topics");
    return topics;
}

/**
 * Makes a topic. Its icon is made by `imageModel` in the background, as the
 * task that comes back, or not at all without a key.
 */
export function createTopic(
    title: string,
    description: string,
    imageModel: ModelChoice,
    apiKey: string,
): Promise<{ topic: Topic; task: BackgroundTask | null }> {
    return call(
        "/topics",
        { method: "POST", body: JSON.stringify({ title, description, image_model: modelRequest(imageModel) }) },
        apiKey,
    );
}

/** Has the icon of a topic made again, in the background. */
export function remakeIcon(
    id: string,
    imageModel: ModelChoice,
    apiKey: string,
): Promise<{ task: BackgroundTask | null }> {
    icons.delete(id);
    return call(
        `/topics/${encodeURIComponent(id)}/icon`,
        { method: "POST", body: JSON.stringify({ image_model: modelRequest(imageModel) }) },
        apiKey,
    );
}

/** Changes the title of a topic and what it is about; its icon is kept. */
export async function updateTopic(id: string, title: string, description: string): Promise<Topic> {
    const { topic } = await call<{ topic: Topic }>(`/topics/${encodeURIComponent(id)}`, {
        method: "PUT",
        body: JSON.stringify({ title, description }),
    });
    return topic;
}

export async function deleteTopic(id: string): Promise<void> {
    icons.delete(id);
    await call(`/topics/${encodeURIComponent(id)}`, { method: "DELETE" });
}

// the icons that were fetched, each as an address the page can show
const icons = new Map<string, Promise<string>>();

/** The icon of a topic, as an address an image can be shown from. It is fetched once. */
export function iconOf(id: string): Promise<string> {
    let icon = icons.get(id);
    if (!icon) {
        icon = checkerFetch(`/topics/${encodeURIComponent(id)}/icon`).then(async (response) => {
            if (!response.ok) {
                throw new Error("no icon");
            }
            return URL.createObjectURL(await response.blob());
        });
        // one that could not be had is asked for again next time
        icon.catch(() => icons.delete(id));
        icons.set(id, icon);
    }
    return icon;
}

/** Forgets the icon of a topic, so that a new one is fetched. */
export function forgetIcon(id: string): void {
    icons.delete(id);
}

/**
 * Has the words of the vocabulary of `language` that `model` has not
 * embedded yet embedded in the background. Says how many there were, with
 * the task that embeds them, if one was started.
 */
export function embedVocabulary(
    language: string,
    model: ModelChoice,
    apiKey: string,
): Promise<{ missing: number; task: BackgroundTask | null }> {
    return call(
        "/embeddings",
        { method: "POST", body: JSON.stringify({ language, model: modelRequest(model) }) },
        apiKey,
    );
}

/** Whether a topic is one of those `query` looks for: its title or what it is about has each word of it. */
export function matchesTopic(topic: Pick<Topic, "title" | "description">, query: string): boolean {
    const text = `${topic.title} ${topic.description}`.toLocaleLowerCase();
    return query.toLocaleLowerCase().split(/\s+/).every((word) => text.includes(word));
}
