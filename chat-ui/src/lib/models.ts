// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { checkerFetch } from "./session";

/**
 * A model, and where it is asked: on OpenRouter, with the key of the
 * settings, or at the address of a server that takes OpenAI's requests, such
 * as one running on this machine. Every kind of model is chosen and asked
 * this same way.
 */
export interface ModelChoice {
    /** Its id where it is asked. Blank, for some, where another model stands in. */
    model: string;
    /** Where the paths of its requests go, such as `http://127.0.0.1:8000/v1`; blank for OpenRouter. */
    url: string;
    /** The key of the server at `url`, which may need none. */
    key: string;
}

/** The kinds of model there are, each with what OpenRouter lists them by. */
const KINDS = {
    text: "output_modalities=text",
    reasoning: "output_modalities=text&supported_parameters=reasoning",
    vision: "input_modalities=image&output_modalities=text",
    decisions: "output_modalities=decisions",
    speech: "output_modalities=speech",
    image: "output_modalities=image",
    embeddings: "output_modalities=embeddings",
} as const;

export type ModelKind = keyof typeof KINDS;

export const OPENROUTER_URL = "https://openrouter.ai/api/v1";

/** A model on OpenRouter. */
export function onOpenRouter(model: string): ModelChoice {
    return { model, url: "", key: "" };
}

/** A model as stored settings have it: as an id from before there were addresses, or with its address. */
export function readModelChoice(stored: unknown, usual: ModelChoice): ModelChoice {
    if (typeof stored === "string") {
        return onOpenRouter(stored.trim());
    }
    if (typeof stored !== "object" || stored === null) {
        return usual;
    }
    const { model, url, key } = stored as Partial<Record<keyof ModelChoice, unknown>>;
    return {
        model: typeof model === "string" ? model.trim() : usual.model,
        url: typeof url === "string" ? url.trim() : "",
        key: typeof key === "string" ? key.trim() : "",
    };
}

/** A model as the checker server is told it: by its id on OpenRouter, or with its address. */
export function modelRequest(choice: ModelChoice): string | ModelChoice {
    return choice.url ? choice : choice.model;
}

/** `choice`, or `instead` if it names no model. */
export function orModel(choice: ModelChoice, instead: ModelChoice): ModelChoice {
    return choice.model ? choice : instead;
}

/** Whether `choice` has what it is asked with: the OpenRouter key, if it is asked there. */
export function canAsk(choice: ModelChoice, apiKey: string): boolean {
    return Boolean(choice.url || apiKey);
}

/** A model OpenRouter has, with the voices it speaks in, if it speaks. */
export interface ListedModel {
    id: string;
    voices: string[];
}

/** The models OpenRouter has of a kind, by their ids. Needs no key. */
export async function fetchOpenRouterModels(kind: ModelKind): Promise<ListedModel[]> {
    const response = await fetch(`${OPENROUTER_URL}/models?${KINDS[kind]}`);
    if (!response.ok) {
        throw new Error(`OpenRouter answered ${response.status}.`);
    }
    const models: { id: string; supported_voices?: string[] }[] = (await response.json()).data;
    return models
        .map((model) => ({ id: model.id, voices: model.supported_voices ?? [] }))
        .sort((a, b) => a.id.localeCompare(b.id));
}

/** The ids of the models the server at `url` has, as it lists them; asked through the checker server. */
export async function fetchModelsAt(url: string, key: string): Promise<string[]> {
    const response = await checkerFetch("/models", { method: "POST", body: JSON.stringify({ url, key }) });
    const reply = await response.json();
    if (!response.ok) {
        throw new Error(typeof reply.error === "string" ? reply.error : `The server answered ${response.status}.`);
    }
    return reply.models;
}

/** What a model is told so that it answers without reasoning first, as the chat and text models do. */
export const NO_REASONING = { enabled: false };

/**
 * Sends a chat request to `choice`: to OpenRouter with `apiKey`, or, for a
 * model at an address, by way of the checker server, which a page may reach
 * where it may not reach the address itself. A request that does not say
 * how the model is to reason has it answer without reasoning, and a model
 * that cannot but reason is asked again as the request was.
 */
export async function sendChat(
    choice: ModelChoice,
    body: Record<string, unknown>,
    apiKey: string,
    signal?: AbortSignal,
): Promise<Response> {
    if ("reasoning" in body) {
        return postChat(choice, body, apiKey, signal);
    }
    const response = await postChat(choice, { ...body, reasoning: NO_REASONING }, apiKey, signal);
    return response.status === 400 ? postChat(choice, body, apiKey, signal) : response;
}

function postChat(
    choice: ModelChoice,
    body: Record<string, unknown>,
    apiKey: string,
    signal?: AbortSignal,
): Promise<Response> {
    if (choice.url) {
        return checkerFetch("/models/chat", {
            method: "POST",
            body: JSON.stringify({ ...body, model: choice }),
            signal,
        });
    }
    return fetch(`${OPENROUTER_URL}/chat/completions`, {
        method: "POST",
        headers: { Authorization: `Bearer ${apiKey}`, "Content-Type": "application/json" },
        body: JSON.stringify({ ...body, model: choice.model }),
        signal,
    });
}

/** What a model that failed said, or what there is to say of its answer. */
export async function errorMessage(response: Response, where: string): Promise<string> {
    const body = await response.text();
    try {
        const { error } = JSON.parse(body);
        return typeof error === "string" ? error : error.message;
    } catch {
        return body || `${where} answered ${response.status}.`;
    }
}
