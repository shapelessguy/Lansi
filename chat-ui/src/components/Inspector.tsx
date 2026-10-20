// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { useEffect, useMemo, useState } from "react";

import {
    amount,
    dollars,
    duration,
    type ModelFacts,
    modelFacts,
    type Part,
    type PartKind,
    partsOf,
    tokensOf,
    totalsOf,
    type Trace,
    type TracedCall,
    usageOf,
} from "../lib/inspect";

/** What each kind of part of the context is called. */
const KINDS: Record<PartKind, string> = {
    system: "System prompt",
    tools: "Tool definitions",
    user: "Learner",
    assistant: "Tutor",
    reasoning: "Reasoning handed back",
    tool: "Tool results",
};

/**
 * Every request the tutor made to its model in the chat, to be looked into:
 * what it was told, part by part with the tokens of each, what it answered
 * and reasoned, the tools it ran with what they gave back, and what each
 * request cost and how long it took.
 */
export function Inspector({ trace }: { trace: Trace }) {
    const calls = useMemo(
        () => trace.exchanges.flatMap((exchange, place) => exchange.calls.map((call) => ({ place, call }))),
        [trace],
    );
    // by the exchange and the request in it; the latest unless one was chosen
    const [chosen, setChosen] = useState<string | null>(null);
    const keyOf = (place: number, call: TracedCall) => `${place}:${call.id}`;
    const shown = calls.find(({ place, call }) => keyOf(place, call) === chosen) ?? calls.at(-1) ?? null;
    const totals = totalsOf(trace);

    return (
        <section className="inspector">
            <header className="chat-header inspector-header">
                <h2 className="tutor-title">Inspector</h2>
                <dl className="inspector-totals">
                    <Fact name="Requests" value={amount(totals.requests)} />
                    <Fact name="Tools run" value={amount(totals.tools)} />
                    <Fact name="Input" value={amount(totals.input)} />
                    <Fact name="Cached" value={amount(totals.cached)} />
                    <Fact name="Output" value={amount(totals.output)} />
                    <Fact name="Reasoning" value={amount(totals.reasoning)} />
                    <Fact name="Cost" value={dollars(totals.cost)} />
                    <Fact name="Time" value={duration(totals.ms)} />
                </dl>
            </header>
            {calls.length === 0
                ? (
                    <div className="empty">
                        <h2>Nothing asked yet</h2>
                        <p>
                            Each request the tutor sends to its model is shown here as it goes: the prompt, the messages
                            and the tools it was given, what came back, and the tokens and time of each.
                        </p>
                    </div>
                )
                : (
                    <div className="inspector-body">
                        <nav className="inspector-list" aria-label="Requests">
                            {trace.exchanges.map((exchange, place) => (
                                <div key={place} className="inspector-exchange">
                                    <div className="inspector-exchange-label" title={exchange.label}>
                                        {new Date(exchange.at).toLocaleTimeString()} · {exchange.label}
                                    </div>
                                    {exchange.calls.map((call) => {
                                        const usage = usageOf(call.reply);
                                        const key = keyOf(place, call);
                                        return (
                                            <button
                                                key={key}
                                                className="inspector-call"
                                                aria-pressed={shown !== null && keyOf(shown.place, shown.call) === key}
                                                onClick={() => setChosen(key)}
                                            >
                                                <span>
                                                    Request {call.id}
                                                    {call.reply === null && " …"}
                                                    {call.reply?.error && " ✗"}
                                                </span>
                                                <span className="inspector-call-numbers">
                                                    {amount(usage.input)} in · {amount(usage.output)} out ·{" "}
                                                    {duration(call.reply?.total_ms ?? null)}
                                                </span>
                                                {call.tools.length > 0 && (
                                                    <span className="inspector-call-tools">
                                                        → {call.tools.map((tool) => tool.name).join(", ")}
                                                    </span>
                                                )}
                                            </button>
                                        );
                                    })}
                                </div>
                            ))}
                        </nav>
                        {shown && <CallView key={keyOf(shown.place, shown.call)} call={shown.call} />}
                    </div>
                )}
        </section>
    );
}

function Fact({ name, value }: { name: string; value: string }) {
    return (
        <div>
            <dt>{name}</dt>
            <dd>{value}</dd>
        </div>
    );
}

/** A request to the model, all of it. */
function CallView({ call }: { call: TracedCall }) {
    const { request, reply } = call;
    const usage = usageOf(reply);
    const parts = useMemo(() => partsOf(request), [request]);
    const tokens = tokensOf(parts, usage.input);
    const counted = usage.input ?? tokens.reduce((sum, each) => sum + each, 0);
    const [facts, setFacts] = useState<ModelFacts | null>(null);
    const modelId = request.model;
    useEffect(() => {
        let current = true;
        modelFacts(modelId).then((found) => current && setFacts(found));
        return () => {
            current = false;
        };
    }, [modelId]);
    const settings = Object.fromEntries(
        Object.entries(request).filter(([name]) => !["messages", "tools"].includes(name)),
    );
    const byKind = (Object.keys(KINDS) as PartKind[])
        .map((kind) => ({
            kind,
            tokens: parts.reduce((sum, each, index) => sum + (each.kind === kind ? tokens[index] : 0), 0),
        }))
        .filter((each) => each.tokens > 0);
    const window = facts?.contextLength ?? null;

    return (
        <div className="inspector-call-view">
            {reply?.error && <p className="message error">{reply.error}</p>}
            <section>
                <h3>Overview</h3>
                <dl className="inspector-facts">
                    <Fact name="Model asked" value={request.model} />
                    <Fact name="Model that answered" value={reply?.model ?? "—"} />
                    <Fact name="Provider" value={reply?.provider ?? "—"} />
                    <Fact name="Generation" value={reply?.generation ?? "—"} />
                    <Fact name="Finished because" value={reply?.finish_reason ?? (reply ? "—" : "still running")} />
                    <Fact name="Sent at" value={new Date(call.at).toLocaleTimeString()} />
                    <Fact name="First token after" value={duration(reply?.first_ms ?? null)} />
                    <Fact name="Whole answer after" value={duration(reply?.total_ms ?? null)} />
                    <Fact name="Input tokens" value={amount(usage.input)} />
                    <Fact name="of which cached" value={amount(usage.cached)} />
                    <Fact name="Output tokens" value={amount(usage.output)} />
                    <Fact name="of which reasoning" value={amount(usage.reasoning)} />
                    <Fact name="Cost" value={dollars(usage.cost)} />
                    <Fact
                        name="Context window"
                        value={window ? `${amount(counted)} of ${amount(window)} (${percent(counted, window)})` : "—"}
                    />
                    <Fact name="Most output" value={amount(facts?.maxOutput ?? null)} />
                    <Fact
                        name="Price per million"
                        value={facts?.promptPrice !== null && facts
                            ? `${dollars((facts.promptPrice ?? 0) * 1e6)} in · ${
                                dollars((facts.completionPrice ?? 0) * 1e6)
                            } out`
                            : "—"}
                    />
                </dl>
                {window !== null && (
                    <div className="inspector-window" title="How much of the context window this request took">
                        <span style={{ width: `${Math.min(100, (counted / window) * 100)}%` }} />
                    </div>
                )}
            </section>

            <section>
                <h3>Context, {amount(counted)} tokens</h3>
                <p className="inspector-note">
                    {usage.input === null
                        ? `The model has not said how many tokens it was given yet: each part is counted as a token for every ${4} characters.`
                        : "The model said how many tokens it was given in all; each part is given its share of them by its length, so the parts are close, not exact."}
                </p>
                <div className="inspector-bar" role="img" aria-label="The context by kind">
                    {byKind.map((each) => (
                        <span
                            key={each.kind}
                            className={`part-${each.kind}`}
                            style={{ flexGrow: each.tokens }}
                            title={`${KINDS[each.kind]}: ${amount(each.tokens)}`}
                        />
                    ))}
                </div>
                <ul className="inspector-legend">
                    {byKind.map((each) => (
                        <li key={each.kind}>
                            <span className={`inspector-swatch part-${each.kind}`} aria-hidden="true" />
                            {KINDS[each.kind]} {amount(each.tokens)} ({percent(each.tokens, counted)})
                        </li>
                    ))}
                </ul>
                <table className="inspector-parts">
                    <thead>
                        <tr>
                            <th>Part</th>
                            <th>Characters</th>
                            <th>≈ Tokens</th>
                            <th>Share</th>
                        </tr>
                    </thead>
                    <tbody>
                        {parts.map((each, index) => (
                            <PartRow key={index} part={each} tokens={tokens[index]} of={counted} />
                        ))}
                    </tbody>
                </table>
            </section>

            <section>
                <h3>Answer</h3>
                {reply === null && <p className="inspector-note">Still coming.</p>}
                {reply?.reasoning && (
                    <details>
                        <summary>Reasoning, {amount(reply.reasoning.length)} characters</summary>
                        <pre className="inspector-text">{reply.reasoning}</pre>
                    </details>
                )}
                {reply?.message?.content && <pre className="inspector-text">{reply.message.content}</pre>}
                {call.tools.map((tool) => (
                    <details key={tool.id} className="inspector-tool">
                        <summary>
                            {tool.failed ? "✗" : tool.content === null ? "…" : "✓"}{" "}
                            {tool.name}({tool.arguments || "{}"}) · {duration(tool.ms)} ·{" "}
                            {amount(tool.content?.length ?? null)} characters, ≈{" "}
                            {amount(tool.content === null ? null : Math.ceil(tool.content.length / 4))} tokens
                        </summary>
                        <pre className="inspector-text">{prettyJson(tool.content ?? "")}</pre>
                    </details>
                ))}
            </section>

            <section>
                <h3>Settings of the request</h3>
                <pre className="inspector-text">{JSON.stringify(settings, null, 2)}</pre>
            </section>

            <section>
                <h3>Raw</h3>
                <details>
                    <summary>The request as it was sent</summary>
                    <pre className="inspector-text">{JSON.stringify(request, null, 2)}</pre>
                </details>
                <details>
                    <summary>What came back</summary>
                    <pre className="inspector-text">{JSON.stringify(reply, null, 2)}</pre>
                </details>
            </section>
        </div>
    );
}

/** A part of the context, which opens to show what it says. */
function PartRow({ part, tokens, of }: { part: Part; tokens: number; of: number }) {
    const [open, setOpen] = useState(false);
    return (
        <>
            <tr className="inspector-part" onClick={() => setOpen(!open)} aria-expanded={open}>
                <td>
                    <span className={`inspector-swatch part-${part.kind}`} aria-hidden="true" /> {open ? "▾" : "▸"}{" "}
                    {part.label}
                </td>
                <td>{amount(part.chars)}</td>
                <td>{amount(tokens)}</td>
                <td>{percent(tokens, of)}</td>
            </tr>
            {open && (
                <tr>
                    <td colSpan={4}>
                        <pre className="inspector-text">{prettyJson(part.text)}</pre>
                    </td>
                </tr>
            )}
        </>
    );
}

function percent(part: number, whole: number): string {
    return whole > 0 ? `${((part / whole) * 100).toFixed(1)}%` : "—";
}

/** Text that is JSON, laid out to be read; any other text as it is. */
function prettyJson(text: string): string {
    try {
        return JSON.stringify(JSON.parse(text), null, 2);
    } catch {
        return text;
    }
}
