// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { expect, test, vi } from "vitest";

import { canAsk, modelRequest, onOpenRouter, orModel, readModelChoice, sendChat } from "./models";

const AT_HOME = { model: "jev", url: "http://127.0.0.1:10000/v1", key: "" };

test("a model stored by its id, from before there were addresses, is one of OpenRouter", () => {
    expect(readModelChoice(" some/model ", onOpenRouter("usual"))).toEqual(onOpenRouter("some/model"));
});

test("a stored model keeps its address and key, and what is not one is the usual one", () => {
    expect(readModelChoice({ ...AT_HOME, key: "k" }, onOpenRouter("usual"))).toEqual({ ...AT_HOME, key: "k" });
    expect(readModelChoice(3, onOpenRouter("usual"))).toEqual(onOpenRouter("usual"));
});

test("the checker server is told a model of OpenRouter by its id, and one at an address with it", () => {
    expect(modelRequest(onOpenRouter("some/model"))).toBe("some/model");
    expect(modelRequest(AT_HOME)).toEqual(AT_HOME);
});

test("a model that names none stands aside for another", () => {
    expect(orModel(onOpenRouter(""), AT_HOME)).toEqual(AT_HOME);
    expect(orModel(onOpenRouter("mine"), AT_HOME)).toEqual(onOpenRouter("mine"));
});

test("only a model of OpenRouter needs the OpenRouter key to be asked", () => {
    expect(canAsk(onOpenRouter("some/model"), "")).toBe(false);
    expect(canAsk(onOpenRouter("some/model"), "sk-or")).toBe(true);
    expect(canAsk(AT_HOME, "")).toBe(true);
});

test("a chat model is asked to answer without reasoning, and asked again as it was if it refuses", async () => {
    const sent: Record<string, unknown>[] = [];
    const refusing = vi.fn(async (_url: string, init: RequestInit) => {
        const body = JSON.parse(String(init.body));
        sent.push(body);
        return new Response("{}", { status: "reasoning" in body ? 400 : 200 });
    });
    vi.stubGlobal("fetch", refusing);
    try {
        const response = await sendChat(onOpenRouter("some/model"), { messages: [] }, "sk-or");

        expect(response.status).toBe(200);
        expect(sent).toEqual([
            { messages: [], reasoning: { enabled: false }, model: "some/model" },
            { messages: [], model: "some/model" },
        ]);
    } finally {
        vi.unstubAllGlobals();
    }
});
