// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { t } from "./i18n";
import { errorMessage, type ModelChoice, sendChat } from "./models";

export interface ChatMessage {
    role: "system" | "user" | "assistant";
    content: string;
}

/** What a reply used. OpenRouter sends it in the last event of the reply. */
export interface ReplyUsage {
    promptTokens: number;
    completionTokens: number;
    /** In US dollars; null if not reported. */
    cost: number | null;
    /** The model that answered, which differs from the one asked for when routing is automatic. */
    model: string | null;
}

export interface StreamParse {
    /** Text the model produced in the complete events seen so far. */
    text: string;
    /** A partial line to prepend to the next chunk. */
    rest: string;
    done: boolean;
    usage: ReplyUsage | null;
}

/**
 * Reads the server-sent events in `buffer`. Throws if the provider reports an
 * error part-way through a reply.
 */
export function parseStream(buffer: string): StreamParse {
    const lines = buffer.split("\n");
    const rest = lines.pop() ?? "";
    let text = "";
    let done = false;
    let usage: ReplyUsage | null = null;
    for (const line of lines) {
        // other lines are blank separators or keep-alive comments
        if (!line.startsWith("data:")) {
            continue;
        }
        const data = line.slice("data:".length).trim();
        if (data === "[DONE]") {
            done = true;
            break;
        }
        const event = JSON.parse(data);
        if (event.error) {
            throw new Error(event.error.message ?? t("The model returned an error."));
        }
        text += event.choices?.[0]?.delta?.content ?? "";
        if (event.usage) {
            usage = {
                promptTokens: event.usage.prompt_tokens ?? 0,
                completionTokens: event.usage.completion_tokens ?? 0,
                cost: typeof event.usage.cost === "number" ? event.usage.cost : null,
                model: typeof event.model === "string" ? event.model : null,
            };
        }
    }
    return { text, rest, done, usage };
}

/**
 * Sends the conversation to `model`, by way of the checker server, and calls
 * `onText` with each piece of the reply as it arrives. Returns what the
 * reply used, or null if that was not reported.
 */
export async function streamChat(options: {
    apiKey: string;
    model: ModelChoice;
    messages: ChatMessage[];
    signal: AbortSignal;
    /** The chat what the reply used is counted under, which the server counts. */
    usageId: string;
    onText: (text: string) => void;
}): Promise<ReplyUsage | null> {
    const response = await sendChat(
        options.model,
        { messages: options.messages, stream: true, usage_id: options.usageId },
        options.apiKey,
        options.signal,
    );
    if (!response.ok || !response.body) {
        throw new Error(await errorMessage(response, options.model.url || "OpenRouter"));
    }
    const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
    let buffer = "";
    let usage: ReplyUsage | null = null;
    for (;;) {
        const { value, done } = await reader.read();
        if (done) {
            return usage;
        }
        const parsed = parseStream(buffer + value);
        buffer = parsed.rest;
        usage = parsed.usage ?? usage;
        if (parsed.text) {
            options.onText(parsed.text);
        }
        if (parsed.done) {
            return usage;
        }
    }
}
