// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { OPENROUTER_URL } from "./models";
import type { ModelReply, ModelRequest, TutorEvent, TutorMessage } from "./tutor";

/**
 * What the tutor was asked and what it cost, kept as the chat goes so that
 * every request to the model can be looked into: what it was told, what it
 * answered, the tools it ran, the tokens and the time.
 */
export interface Trace {
    exchanges: Exchange[];
}

/** A request to the server: something the learner wrote, or an exercise done, and the requests to the model it made. */
export interface Exchange {
    /** What it was, in a few words. */
    label: string;
    /** When it started, in milliseconds since the epoch. */
    at: number;
    calls: TracedCall[];
}

/** A request to the model, what it came to, and the tools it called that were run. */
export interface TracedCall {
    id: number;
    /** When it was sent, in milliseconds since the epoch. */
    at: number;
    request: ModelRequest;
    reply: ModelReply | null;
    tools: TracedTool[];
}

export interface TracedTool {
    id: string;
    name: string;
    doing: string;
    arguments: string;
    /** What the model was told it came to, once it is done. */
    content: string | null;
    ms: number | null;
    failed: boolean;
}

export const EMPTY_TRACE: Trace = { exchanges: [] };

/** `trace` with a new exchange begun, which the events after it belong to. */
export function begun(trace: Trace, label: string, at: number): Trace {
    return { exchanges: [...trace.exchanges, { label, at, calls: [] }] };
}

/** `trace` with `event` taken into its last exchange. */
export function traced(trace: Trace, event: TutorEvent): Trace {
    const exchange = trace.exchanges.at(-1);
    if (!exchange) {
        return trace;
    }
    const calls = exchange.calls;
    let changed: TracedCall[] | null = null;
    switch (event.type) {
        case "call":
            changed = [...calls, { id: event.id, at: event.at * 1000, request: event.request, reply: null, tools: [] }];
            break;
        case "call_done": {
            const { type: _, id, ...reply } = event;
            changed = calls.map((call) => call.id === id ? { ...call, reply } : call);
            break;
        }
        case "tool": {
            const last = calls.at(-1);
            if (last) {
                const tool: TracedTool = {
                    id: event.id,
                    name: event.name,
                    doing: event.doing,
                    arguments: event.arguments ?? "",
                    content: null,
                    ms: null,
                    failed: false,
                };
                changed = [...calls.slice(0, -1), { ...last, tools: [...last.tools, tool] }];
            }
            break;
        }
        case "tool_done":
            changed = calls.map((call) => ({
                ...call,
                tools: call.tools.map((tool) =>
                    tool.id === event.id
                        ? { ...tool, content: event.content ?? null, ms: event.ms ?? null, failed: event.failed }
                        : tool
                ),
            }));
            break;
    }
    return changed
        ? { exchanges: [...trace.exchanges.slice(0, -1), { ...exchange, calls: changed }] }
        : trace;
}

/** What a part of the context is, which it is coloured by. */
export type PartKind = "system" | "tools" | "user" | "assistant" | "reasoning" | "tool";

/** A part of what the model was given, with how long it is. */
export interface Part {
    kind: PartKind;
    label: string;
    text: string;
    chars: number;
}

/** About how many characters a token is, where the model said nothing of the tokens. */
export const CHARS_PER_TOKEN = 4;

/**
 * The parts of what a request gave the model, in order: the system prompt,
 * each message, the reasoning handed back with a message, and each tool it
 * was told of. Tools and calls of tools are counted as the JSON they are
 * sent as.
 */
export function partsOf(request: ModelRequest): Part[] {
    const parts: Part[] = [];
    let number = 0;
    for (const message of request.messages) {
        if (message.role === "system") {
            parts.push(part("system", "System prompt", message.content ?? ""));
            continue;
        }
        number += 1;
        parts.push(...messageParts(message, number));
    }
    for (const tool of request.tools ?? []) {
        parts.push(part("tools", `Tool: ${tool.function.name}`, JSON.stringify(tool, null, 2)));
    }
    return parts;
}

function messageParts(message: TutorMessage & { role: string }, number: number): Part[] {
    const content = message.content ?? "";
    if (message.role === "tool") {
        return [part("tool", `#${number} tool result`, content)];
    }
    if (message.role === "user") {
        return [part("user", `#${number} learner`, content)];
    }
    const parts: Part[] = [];
    const calls = message.tool_calls as { function: { name: string; arguments: string } }[] | undefined;
    const said = [
        content,
        ...(calls ?? []).map((call) => `→ ${call.function.name}(${call.function.arguments})`),
    ].filter(Boolean).join("\n");
    parts.push(part("assistant", `#${number} tutor${calls?.length ? ", calling tools" : ""}`, said));
    const details = message.reasoning_details;
    if (Array.isArray(details) && details.length > 0) {
        parts.push(part("reasoning", `#${number} reasoning handed back`, JSON.stringify(details, null, 2)));
    }
    return parts;
}

function part(kind: PartKind, label: string, text: string): Part {
    return { kind, label, text, chars: text.length };
}

/** The tokens of each part: shares of `promptTokens` by length, where the model said how many there were in all. */
export function tokensOf(parts: Part[], promptTokens: number | null): number[] {
    const chars = parts.reduce((sum, each) => sum + each.chars, 0);
    if (!promptTokens || chars === 0) {
        return parts.map((each) => Math.ceil(each.chars / CHARS_PER_TOKEN));
    }
    return parts.map((each) => Math.round((each.chars / chars) * promptTokens));
}

/** The usage of a request, as numbers, with those the model did not report as null. */
export interface Usage {
    input: number | null;
    cached: number | null;
    output: number | null;
    reasoning: number | null;
    cost: number | null;
}

export function usageOf(reply: ModelReply | null): Usage {
    const usage = reply?.usage ?? {};
    const inner = (name: string, field: string) => {
        const details = usage[name];
        return typeof details === "object" && details !== null
            ? count((details as Record<string, unknown>)[field])
            : null;
    };
    return {
        input: count(usage.prompt_tokens),
        cached: inner("prompt_tokens_details", "cached_tokens"),
        output: count(usage.completion_tokens),
        reasoning: inner("completion_tokens_details", "reasoning_tokens"),
        cost: count(usage.cost),
    };
}

function count(value: unknown): number | null {
    return typeof value === "number" && Number.isFinite(value) ? value : null;
}

/** The usage of every request of `trace`, added up, with how long they took and how many there were. */
export function totalsOf(trace: Trace): Usage & { requests: number; ms: number; tools: number } {
    const totals = { input: 0, cached: 0, output: 0, reasoning: 0, cost: 0, requests: 0, ms: 0, tools: 0 };
    for (const call of trace.exchanges.flatMap((exchange) => exchange.calls)) {
        const usage = usageOf(call.reply);
        totals.input += usage.input ?? 0;
        totals.cached += usage.cached ?? 0;
        totals.output += usage.output ?? 0;
        totals.reasoning += usage.reasoning ?? 0;
        totals.cost += usage.cost ?? 0;
        totals.requests += 1;
        totals.ms += call.reply?.total_ms ?? 0;
        totals.tools += call.tools.length;
    }
    return totals;
}

/** What OpenRouter says of a model: how much context it takes and what its tokens cost, in dollars each. */
export interface ModelFacts {
    contextLength: number | null;
    maxOutput: number | null;
    promptPrice: number | null;
    completionPrice: number | null;
}

let listed: Promise<Map<string, ModelFacts>> | null = null;

/** What OpenRouter says of the model `id`, or null if it lists no such model or cannot be reached. */
export async function modelFacts(id: string): Promise<ModelFacts | null> {
    listed ??= fetch(`${OPENROUTER_URL}/models`)
        .then((response) => response.json())
        .then(({ data }: { data: Record<string, unknown>[] }) =>
            new Map(data.map((model) => [String(model.id), factsOf(model)]))
        )
        .catch(() => {
            listed = null;
            return new Map();
        });
    return (await listed).get(id) ?? null;
}

function factsOf(model: Record<string, unknown>): ModelFacts {
    const pricing = (model.pricing ?? {}) as Record<string, unknown>;
    const top = (model.top_provider ?? {}) as Record<string, unknown>;
    const price = (value: unknown) => (typeof value === "string" && value !== "" ? Number(value) : null);
    return {
        contextLength: count(model.context_length),
        maxOutput: count(top.max_completion_tokens),
        promptPrice: price(pricing.prompt),
        completionPrice: price(pricing.completion),
    };
}

/** A whole number with its thousands marked, or a dash for one that is not known. */
export function amount(value: number | null): string {
    return value === null ? "—" : Math.round(value).toLocaleString("en-US");
}

/** A cost in dollars, to as many places as it needs. */
export function dollars(value: number | null): string {
    if (value === null) {
        return "—";
    }
    return value === 0 ? "$0" : value < 0.01 ? `$${value.toFixed(5)}` : `$${value.toFixed(3)}`;
}

/** A time in milliseconds, as seconds once it is longer than one. */
export function duration(ms: number | null): string {
    if (ms === null) {
        return "—";
    }
    return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`;
}
