// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { useEffect, useMemo, useState } from "react";

import {
    amount,
    arcsOf,
    byKind,
    lastCall,
    modelFacts,
    PART_KINDS,
    partsOf,
    tokensOf,
    type Trace,
    usageOf,
} from "../lib/inspect";

const RADIUS = 9;
const ROUND = 2 * Math.PI * RADIUS;

/**
 * How much of the context window of its model the last request of the
 * tutor took, as a ring that goes round as far, coloured by the kinds of
 * the parts of the context, as the inspector colours them. Clicking it
 * opens the inspector. It is not shown before the tutor is asked anything,
 * nor while the request took less than half a percent of the window.
 */
export function ContextRing({ trace, onOpen }: { trace: Trace; onOpen: () => void }) {
    const call = lastCall(trace);
    const request = call?.request ?? null;
    const input = usageOf(call?.reply ?? null).input;
    const kinds = useMemo(() => {
        if (!request) {
            return [];
        }
        const parts = partsOf(request);
        return byKind(parts, tokensOf(parts, input));
    }, [request, input]);
    const [contextWindow, setContextWindow] = useState<number | null>(null);
    const modelId = request?.model ?? null;
    useEffect(() => {
        let current = true;
        setContextWindow(null);
        if (modelId) {
            modelFacts(modelId).then((facts) => current && setContextWindow(facts?.contextLength ?? null));
        }
        return () => {
            current = false;
        };
    }, [modelId]);
    const counted = kinds.reduce((sum, each) => sum + each.tokens, 0);
    const share = contextWindow ? counted / contextWindow : null;
    // nothing to show before a request, or of one that took next to none of the window
    if (call === null || (share !== null && Math.round(share * 100) === 0)) {
        return null;
    }
    const told = [
        contextWindow
            ? `${amount(counted)} of ${amount(contextWindow)} tokens of context (${Math.round((share ?? 0) * 100)}%)`
            : `${amount(counted)} tokens of context`,
        ...kinds.map((each) => `${PART_KINDS[each.kind]}: ${amount(each.tokens)}`),
    ].join("\n");

    return (
        <button
            className="context-ring"
            onClick={onOpen}
            title={`${told}\n\nClick to inspect the requests`}
            aria-label={`Inspector. ${told}`}
        >
            <svg viewBox="0 0 24 24" aria-hidden="true">
                <circle className="context-ring-track" cx="12" cy="12" r={RADIUS} />
                {arcsOf(kinds, contextWindow).map((arc) => (
                    <circle
                        key={arc.kind}
                        className={`part-${arc.kind}`}
                        cx="12"
                        cy="12"
                        r={RADIUS}
                        strokeDasharray={`${arc.length * ROUND} ${ROUND}`}
                        strokeDashoffset={-arc.start * ROUND}
                    />
                ))}
            </svg>
            {share !== null && <span>{Math.round(share * 100)}%</span>}
        </button>
    );
}
