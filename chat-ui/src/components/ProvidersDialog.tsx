// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";

import { t } from "../lib/i18n";
import { fetchProviders, type Provider } from "../lib/models";

/** What the providers can be sorted by. */
type SortKey = "name" | "promptPrice" | "completionPrice" | "latency" | "throughput" | "uptime" | "tools";

/** Those that are best high, which are sorted from the highest; the others from the lowest. */
const HIGHEST_FIRST: ReadonlySet<SortKey> = new Set(["throughput", "uptime", "tools"]);

interface Props {
    /** The id of the model on OpenRouter whose providers are listed. */
    model: string;
    /** The slugs of the providers that alone are to serve it; none for any. */
    chosen: string[];
    /** Whether it is shown which providers take tools, for a model that is called with them. */
    tools: boolean;
    /** The OpenRouter key, without which it is not known how quick the providers are. */
    apiKey: string;
    onChange: (chosen: string[]) => void;
    onClose: () => void;
}

/** A provider's figure to sort by, what is not known last whichever way it is sorted. */
function figure(provider: Provider, key: SortKey): number | string | null {
    if (key === "name") {
        return provider.name.toLowerCase();
    }
    if (key === "tools") {
        return provider.tools ? 1 : 0;
    }
    return provider[key];
}

function sorted(providers: Provider[], key: SortKey, reversed: boolean): Provider[] {
    const highest = HIGHEST_FIRST.has(key) !== reversed;
    return [...providers].sort((one, other) => {
        const [a, b] = [figure(one, key), figure(other, key)];
        if (a === null || b === null) {
            return a === b ? 0 : a === null ? 1 : -1;
        }
        const order = a < b ? -1 : a > b ? 1 : 0;
        return highest ? -order : order;
    });
}

/**
 * What tells an endpoint of a provider from its others: its slug after the
 * provider's, such as `fp8/flex` of `deepinfra/fp8/flex`, or else how its
 * weights are stored.
 */
function variantOf(provider: Provider): string {
    const rest = provider.slug.split("/").slice(1).join("/");
    if (rest) {
        return rest;
    }
    return provider.quantization && provider.quantization !== "unknown" ? provider.quantization : "";
}

/** Dollars a million tokens, from dollars a token. */
function perMillion(price: number | null): string {
    return price === null ? "–" : `$${(price * 1_000_000).toFixed(2)}`;
}

/**
 * The providers OpenRouter has serve a model, over the page: what each asks
 * for the tokens in and out, how soon it answers, how fast it writes, how
 * often it answered lately and, for a model called with tools, whether it
 * takes them. Those ticked alone serve the model; with none ticked, any may.
 */
export function ProvidersDialog({ model, chosen, tools, apiKey, onChange, onClose }: Props) {
    const [providers, setProviders] = useState<Provider[] | null>(null);
    const [problem, setProblem] = useState("");
    const [sortKey, setSortKey] = useState<SortKey>(tools ? "tools" : "promptPrice");
    const [reversed, setReversed] = useState(false);

    useEffect(() => {
        let stopped = false;
        fetchProviders(model, apiKey).then(
            (found) => stopped || setProviders(found),
            (error: Error) => stopped || setProblem(error.message),
        );
        return () => {
            stopped = true;
        };
    }, [model, apiKey]);

    useEffect(() => {
        const onKeyDown = (event: KeyboardEvent) => {
            if (event.key === "Escape") {
                event.stopPropagation();
                onClose();
            }
        };
        document.addEventListener("keydown", onKeyDown, true);
        return () => document.removeEventListener("keydown", onKeyDown, true);
    }, [onClose]);

    function toggle(slug: string) {
        onChange(chosen.includes(slug) ? chosen.filter((each) => each !== slug) : [...chosen, slug]);
    }

    function sortBy(key: SortKey) {
        if (key === sortKey) {
            setReversed((current) => !current);
        } else {
            setSortKey(key);
            setReversed(false);
        }
    }

    const listed = providers ?? [];
    // what OpenRouter gives no figure of for any provider is not shown
    const timed = listed.some((provider) => provider.latency !== null || provider.throughput !== null);
    const columns = 5 + (timed ? 2 : 0) + (tools ? 1 : 0);
    // those chosen that are no longer listed, so that they can be taken out
    const gone = chosen.filter((slug) => !listed.some((provider) => provider.slug === slug));
    const header = (key: SortKey, label: string) => (
        <th aria-sort={sortKey === key ? (HIGHEST_FIRST.has(key) !== reversed ? "descending" : "ascending") : "none"}>
            <button
                className="providers-sort"
                onClick={() =>
                    sortBy(key)}
            >
                {label}
                {sortKey === key && <span aria-hidden>{HIGHEST_FIRST.has(key) !== reversed ? " ↓" : " ↑"}</span>}
            </button>
        </th>
    );
    return createPortal(
        <div className="dialog-backdrop" onPointerDown={(event) => event.target === event.currentTarget && onClose()}>
            <div className="dialog providers-dialog" role="dialog" aria-modal="true" aria-label={t("Providers")}>
                <p className="dialog-message">{t("Providers of {model}", { model })}</p>
                <p className="hint">
                    {chosen.length === 0
                        ? t("Any of them may serve it. Tick those that alone are to serve it.")
                        : t("Only those ticked serve it.")}
                </p>
                {providers && !timed && (
                    <p className="hint">{t("OpenRouter gives no latency or speed for these providers now.")}</p>
                )}
                {problem && <p className="hint error">{problem}</p>}
                {!providers && !problem && <p className="hint">{t("Loading…")}</p>}
                {providers && (
                    <div className="providers-table">
                        <table>
                            <thead>
                                <tr>
                                    <th />
                                    {header("name", t("Provider"))}
                                    {header("promptPrice", t("In / 1M"))}
                                    {header("completionPrice", t("Out / 1M"))}
                                    {timed && header("latency", t("Latency"))}
                                    {timed && header("throughput", t("Speed"))}
                                    {header("uptime", t("Uptime"))}
                                    {tools && header("tools", t("Tools"))}
                                </tr>
                            </thead>
                            <tbody>
                                {gone.map((slug) => (
                                    <tr key={slug} className="providers-gone">
                                        <td>
                                            <input
                                                type="checkbox"
                                                checked
                                                aria-label={slug}
                                                onChange={() => toggle(slug)}
                                            />
                                        </td>
                                        <td colSpan={columns - 1}>
                                            {t("{slug}: not listed now", { slug })}
                                        </td>
                                    </tr>
                                ))}
                                {sorted(listed, sortKey, reversed).map((provider) => (
                                    <tr
                                        key={provider.slug}
                                        className={chosen.includes(provider.slug) ? "chosen" : undefined}
                                        onClick={() => toggle(provider.slug)}
                                    >
                                        <td>
                                            <input
                                                type="checkbox"
                                                checked={chosen.includes(provider.slug)}
                                                aria-label={provider.name}
                                                onClick={(event) => event.stopPropagation()}
                                                onChange={() => toggle(provider.slug)}
                                            />
                                        </td>
                                        <td>
                                            {provider.name}
                                            {variantOf(provider) && (
                                                <small className="providers-variant">{variantOf(provider)}</small>
                                            )}
                                        </td>
                                        <td>{perMillion(provider.promptPrice)}</td>
                                        <td>{perMillion(provider.completionPrice)}</td>
                                        {timed && (
                                            <td>
                                                {provider.latency === null ? "–" : `${provider.latency.toFixed(2)} s`}
                                            </td>
                                        )}
                                        {timed && (
                                            <td>
                                                {provider.throughput === null
                                                    ? "–"
                                                    : t("{count} tok/s", { count: Math.round(provider.throughput) })}
                                            </td>
                                        )}
                                        <td>{provider.uptime === null ? "–" : `${provider.uptime.toFixed(1)}%`}</td>
                                        {tools && (
                                            <td
                                                className={provider.tools ? "providers-yes" : "providers-no"}
                                                aria-label={provider.tools ? t("takes tools") : t("takes no tools")}
                                            >
                                                {provider.tools ? "✓" : "✗"}
                                            </td>
                                        )}
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
                <div className="dialog-buttons">
                    <button disabled={chosen.length === 0} onClick={() => onChange([])}>
                        {t("Any provider")}
                    </button>
                    <button className="primary" autoFocus onClick={onClose}>
                        {t("Done")}
                    </button>
                </div>
            </div>
        </div>,
        document.body,
    );
}
