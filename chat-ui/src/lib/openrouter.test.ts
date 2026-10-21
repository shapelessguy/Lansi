// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { expect, test } from "vitest";

import { parseStream } from "./openrouter";

function event(content: string): string {
    return `data: ${JSON.stringify({ choices: [{ delta: { content } }] })}\n\n`;
}

test("text from each complete event is joined in order", () => {
    expect(parseStream(event("Hal") + event("lo"))).toEqual({ text: "Hallo", rest: "", done: false, usage: null });
});

test("the usage event gives tokens, cost and the model that answered", () => {
    const usageEvent = {
        model: "vendor/some-model",
        choices: [],
        usage: { prompt_tokens: 6012, completion_tokens: 87, total_tokens: 6099, cost: 0.00321 },
    };

    const parsed = parseStream(event("Hallo") + `data: ${JSON.stringify(usageEvent)}\n\n` + "data: [DONE]\n\n");

    expect(parsed.usage).toEqual({
        promptTokens: 6012,
        completionTokens: 87,
        cost: 0.00321,
        model: "vendor/some-model",
    });
    expect(parsed.text).toBe("Hallo");
});

test("usage without a cost reports the cost as unknown", () => {
    const usageEvent = { choices: [], usage: { prompt_tokens: 10, completion_tokens: 2 } };

    const parsed = parseStream(`data: ${JSON.stringify(usageEvent)}\n\n`);

    expect(parsed.usage).toEqual({ promptTokens: 10, completionTokens: 2, cost: null, model: null });
});

test("an event cut off mid-way is kept for the next chunk", () => {
    const whole = event("Hallo");
    const first = parseStream(whole.slice(0, 20));

    const second = parseStream(first.rest + whole.slice(20));

    expect(first.text).toBe("");
    expect(second.text).toBe("Hallo");
});

test("keep-alive comments and events without text are skipped", () => {
    const buffer = ": OPENROUTER PROCESSING\n\n" + "data: {\"choices\":[{\"delta\":{}}]}\n\n" + event("ok");

    expect(parseStream(buffer).text).toBe("ok");
});

test("the end marker stops the stream", () => {
    const parsed = parseStream(event("bye") + "data: [DONE]\n\n");

    expect(parsed).toEqual({ text: "bye", rest: "", done: true, usage: null });
});

test("an error sent part-way through a reply is thrown with its message", () => {
    const buffer = event("partial") + "data: {\"error\":{\"message\":\"Rate limit exceeded\"}}\n\n";

    expect(() => parseStream(buffer)).toThrow("Rate limit exceeded");
});
