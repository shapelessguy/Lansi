// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { formatCost, formatTokens, totalUsage, type UsageEntry, usageOnDay } from "../lib/usage";
import { SidePanel } from "./SidePanel";

interface Props {
    entries: UsageEntry[];
    /** The chat or text whose totals are shown first, and what to call it. */
    chatId: string;
    currentLabel: string;
    onClose: () => void;
}

function Totals({ title, entries }: { title: string; entries: UsageEntry[] }) {
    const totals = totalUsage(entries);
    return (
        <section className="usage-totals">
            <h3>{title}</h3>
            <p className="usage-cost">
                {totals.costIncomplete && "≥ "}
                {formatCost(totals.cost)}
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

export function UsagePanel({ entries, chatId, currentLabel, onClose }: Props) {
    return (
        <SidePanel title="Usage" onClose={onClose}>
            <div className="usage">
                <Totals title={currentLabel} entries={entries.filter((entry) => entry.chatId === chatId)} />
                <Totals title="Today" entries={usageOnDay(entries, Date.now())} />
                <Totals title="Everything" entries={entries} />
                <p className="usage-note">
                    As reported by OpenRouter for replies made in this browser. A reply you stop early is still billed
                    but may not be counted here. The cost of speech is looked up a few seconds after the audio arrives.
                </p>
            </div>
        </SidePanel>
    );
}
