// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { expect, test } from "vitest";

import { arcsOf, begun, byKind, EMPTY_TRACE, lastCall, partsOf, tokensOf, totalsOf, traced, usageOf } from "./inspect";
import type { ModelRequest, TutorEvent } from "./tutor";

const REQUEST: ModelRequest = {
    model: "thinker",
    messages: [
        { role: "system", content: "Be a tutor." },
        { role: "user", content: "Hi" },
        {
            role: "assistant",
            content: "",
            tool_calls: [{ id: "a", type: "function", function: { name: "logs", arguments: "{}" } }],
            reasoning_details: [{ type: "reasoning.text", text: "Hm." }],
        },
        { role: "tool", tool_call_id: "a", content: "[]" },
    ],
    tools: [{ type: "function", function: { name: "logs", description: "The logs.", parameters: {} } }],
};

function traceOf(...events: TutorEvent[]) {
    return events.reduce(
        (trace, event) => traced(trace, event),
        begun(EMPTY_TRACE, "Hi", 1000),
    );
}

test("the parts of a request are the prompt, each message, the reasoning handed back and each tool", () => {
    expect(partsOf(REQUEST).map((part) => [part.kind, part.label])).toEqual([
        ["system", "System prompt"],
        ["user", "#1 learner"],
        ["assistant", "#2 tutor, calling tools"],
        ["reasoning", "#2 reasoning handed back"],
        ["tool", "#3 tool result"],
        ["tools", "Tool: logs"],
    ]);
});

test("the tokens of the parts are shares of those the model reported, by their length", () => {
    const parts = partsOf({
        model: "m",
        messages: [{ role: "system", content: "aaaa" }, { role: "user", content: "aaaaaaaaaaaa" }],
    });

    expect(tokensOf(parts, 100)).toEqual([25, 75]);
    expect(tokensOf(parts, null)).toEqual([1, 3]);
});

test("a request, what came of it and the tools it ran are kept together", () => {
    const trace = traceOf(
        { type: "call", id: 1, at: 2, request: REQUEST },
        { type: "tool", id: "a", name: "logs", doing: "Reading", arguments: "{}" },
        {
            type: "call_done",
            id: 1,
            first_ms: 300,
            total_ms: 900,
            usage: {
                prompt_tokens: 120,
                completion_tokens: 40,
                cost: 0.002,
                prompt_tokens_details: { cached_tokens: 100 },
                completion_tokens_details: { reasoning_tokens: 30 },
            },
        },
        { type: "tool_done", id: "a", failed: false, shown: null, content: "[]", ms: 12 },
    );
    const [call] = trace.exchanges[0].calls;

    expect(call.at).toBe(2000);
    expect(call.tools).toEqual([
        { id: "a", name: "logs", doing: "Reading", arguments: "{}", content: "[]", ms: 12, failed: false },
    ]);
    expect(usageOf(call.reply)).toEqual({ input: 120, cached: 100, output: 40, reasoning: 30, cost: 0.002 });
    expect(totalsOf(trace)).toMatchObject({ requests: 1, input: 120, output: 40, ms: 900, tools: 1 });
});

test("events before any exchange has begun are left out", () => {
    expect(traced(EMPTY_TRACE, { type: "call", id: 1, at: 2, request: REQUEST })).toBe(EMPTY_TRACE);
});

test("the ring of a request goes round as far as the context window it took, a kind after the other", () => {
    const arcs = arcsOf([{ kind: "system", tokens: 100 }, { kind: "user", tokens: 300 }], 1000);

    expect(arcs).toEqual([
        { kind: "system", start: 0, length: 0.1 },
        { kind: "user", start: 0.1, length: 0.3 },
    ]);
});

test("the ring of a request is full when the context window is not known", () => {
    const arcs = arcsOf([{ kind: "system", tokens: 100 }, { kind: "user", tokens: 300 }], null);

    expect(arcs.map((arc) => arc.length)).toEqual([0.25, 0.75]);
});

test("the tokens of a request are added up by kind, leaving out the kinds it has none of", () => {
    const parts = partsOf(REQUEST);

    const kinds = byKind(parts, parts.map(() => 1));

    expect(kinds.map((each) => each.kind)).toEqual(["system", "tools", "user", "assistant", "reasoning", "tool"]);
    expect(byKind(parts.slice(0, 1), [5])).toEqual([{ kind: "system", tokens: 5 }]);
});

test("the last call of a trace is that of its last exchange, and none before a request is made", () => {
    const trace = traceOf(
        { type: "call", id: 1, at: 1, request: REQUEST },
        { type: "call", id: 2, at: 2, request: REQUEST },
    );

    expect(lastCall(trace)?.id).toBe(2);
    expect(lastCall(begun(trace, "Again", 3000))?.id).toBe(2);
    expect(lastCall(EMPTY_TRACE)).toBeNull();
});
