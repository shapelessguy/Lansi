// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { useEffect, useState } from "react";

import {
    fetchUsage,
    formatCost,
    formatTokens,
    startOfDay,
    USAGE_CATEGORIES,
    type UsageSummary,
    type UsageTotals,
} from "../lib/usage";
import { SidePanel } from "./SidePanel";

interface Props {
    /** The chat or text whose totals are shown first, and what to call it; none where nothing is open that is counted on its own, such as a book. */
    chatId: string;
    currentLabel: string | null;
    /** Changes whenever usage is recorded, so that the totals are asked for again. */
    revision: number;
    onClose: () => void;
}

function Cost({ totals }: { totals: UsageTotals }) {
    return (
        <>
            {totals.costIncomplete && "≥ "}
            {formatCost(totals.cost)}
        </>
    );
}

function Totals({ title, totals }: { title: string; totals: UsageTotals }) {
    return (
        <section className="usage-totals">
            <h3>{title}</h3>
            <p className="usage-cost">
                <Cost totals={totals} />
            </p>
            <dl>
                <dt>Tokens in</dt>
                <dd>{formatTokens(totals.promptTokens)}</dd>
                <dt>Tokens out</dt>
                <dd>{formatTokens(totals.completionTokens)}</dd>
                <dt>Requests</dt>
                <dd>{formatTokens(totals.requests)}</dd>
            </dl>
        </section>
    );
}

function categoryLabel(category: string): string {
    return USAGE_CATEGORIES[category as keyof typeof USAGE_CATEGORIES] ?? category;
}

/** Everything, by the kind of work it was and the model that did it. */
function ByModel({ rows }: { rows: UsageSummary["byModel"] }) {
    if (rows.length === 0) {
        return null;
    }
    return (
        <section className="usage-totals">
            <h3>By category and model</h3>
            <table className="usage-by-model">
                <thead>
                    <tr>
                        <th>Model</th>
                        <th>Requests</th>
                        <th>Cost</th>
                    </tr>
                </thead>
                {/* the server sends the rows of a category together */}
                {[...new Set(rows.map((row) => row.category))].map((category) => (
                    <tbody key={category}>
                        <tr>
                            <th colSpan={3} scope="rowgroup">{categoryLabel(category)}</th>
                        </tr>
                        {rows.filter((row) => row.category === category).map((row) => (
                            <tr
                                key={row.model}
                                title={`${row.model}: ${formatTokens(row.promptTokens)} tokens in, ${
                                    formatTokens(row.completionTokens)
                                } out`}
                            >
                                <td>{row.model}</td>
                                <td>{formatTokens(row.requests)}</td>
                                <td>
                                    <Cost totals={row} />
                                </td>
                            </tr>
                        ))}
                    </tbody>
                ))}
            </table>
        </section>
    );
}

export function UsagePanel({ chatId, currentLabel, revision, onClose }: Props) {
    const [summary, setSummary] = useState<UsageSummary | null>(null);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        let current = true;
        fetchUsage(chatId, startOfDay(Date.now())).then(
            (fetched) => {
                if (current) {
                    setSummary(fetched);
                    setError(null);
                }
            },
            (caught: Error) => current && setError(caught.message),
        );
        return () => {
            current = false;
        };
    }, [chatId, revision]);

    return (
        <SidePanel title="Usage" onClose={onClose}>
            <div className="usage">
                {error && <p className="usage-note">The usage could not be loaded: {error}</p>}
                {summary && (
                    <>
                        {currentLabel !== null && <Totals title={currentLabel} totals={summary.chat} />}
                        <Totals title="Today" totals={summary.since} />
                        <Totals title="Everything" totals={summary.everything} />
                        <ByModel rows={summary.byModel} />
                    </>
                )}
                <p className="usage-note">
                    As reported by OpenRouter for the replies made for this account, on any device. A reply you stop
                    early is still billed but may not be counted here. The cost of speech is looked up a few seconds
                    after the audio arrives.
                </p>
            </div>
        </SidePanel>
    );
}
