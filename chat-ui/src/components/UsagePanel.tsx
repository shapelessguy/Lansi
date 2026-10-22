// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { type ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { T } from "./T";

import { locale, t } from "../lib/i18n";
import {
    binOf,
    binStarts,
    byCategoryAndModel,
    fetchUsage,
    formatCost,
    formatTokens,
    loadUsageView,
    type Measure,
    type Period,
    PERIODS,
    periodStart,
    saveUsageView,
    seriesColour,
    type Stacked,
    stacked,
    USAGE_CATEGORIES,
    type UsageSummary,
    type UsageTotals,
    type UsageView,
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

/** A number of tokens, short: 1.2M, 35k. */
function shortTokens(tokens: number): string {
    if (tokens >= 1_000_000) {
        return `${(tokens / 1_000_000).toFixed(tokens >= 10_000_000 ? 0 : 1)}M`;
    }
    if (tokens >= 1_000) {
        return `${(tokens / 1_000).toFixed(tokens >= 10_000 ? 0 : 1)}k`;
    }
    return String(Math.round(tokens));
}

function shown(value: number, measure: Measure): string {
    return measure === "cost" ? formatCost(value) : t("{count} tokens", { count: shortTokens(value) });
}

function categoryLabel(category: string): string {
    const label = USAGE_CATEGORIES[category as keyof typeof USAGE_CATEGORIES];
    return label ? t(label) : category;
}

/** When a bar starts, as the learner reads it: the hour of a day, or the day. */
function binLabel(at: number, hourly: boolean): string {
    return hourly
        ? new Date(at).toLocaleTimeString(locale(), { hour: "2-digit", minute: "2-digit" })
        : new Date(at).toLocaleDateString(locale(), { day: "numeric", month: "short" });
}

/** Where the pointer is on the page. */
type Pointer = { x: number; y: number };

/**
 * What a part of a chart pointed at is, by the pointer, over the whole
 * page, so that nothing the panel holds, nor its edges, cuts it off: on the
 * side of the pointer there is room on.
 */
function Tooltip({ at, children }: { at: Pointer; children: ReactNode }) {
    const box = useRef<HTMLDivElement>(null);
    const [size, setSize] = useState({ width: 0, height: 0 });
    useEffect(() => {
        if (box.current) {
            setSize({ width: box.current.offsetWidth, height: box.current.offsetHeight });
        }
    }, [children]);
    const margin = 14;
    const left = at.x + margin + size.width > window.innerWidth ? at.x - margin - size.width : at.x + margin;
    const top = Math.min(at.y + margin, window.innerHeight - size.height - 4);
    return createPortal(
        <div className="usage-tooltip" ref={box} style={{ left: Math.max(4, left), top: Math.max(4, top) }}>
            {children}
        </div>,
        document.body,
    );
}

/** The usage of the period as bars of time, stacked by model, with what each holds on hover. */
function UsageChart({ data, measure, hourly }: { data: Stacked; measure: Measure; hourly: boolean }) {
    const frame = useRef<HTMLDivElement>(null);
    const [width, setWidth] = useState(380);
    const [hovered, setHovered] = useState<number | null>(null);
    const [pointer, setPointer] = useState<Pointer>({ x: 0, y: 0 });
    useEffect(() => {
        const element = frame.current;
        if (!element) {
            return;
        }
        const watching = new ResizeObserver(([entry]) => setWidth(Math.max(200, entry.contentRect.width)));
        watching.observe(element);
        return () => watching.disconnect();
    }, []);

    const height = 150;
    const left = 44;
    const bottom = 20;
    const plot = height - bottom - 6;
    const count = Math.max(1, data.bars.length);
    const step = (width - left) / count;
    const gap = step > 6 ? 2 : step > 3 ? 1 : 0;
    const highest = Math.max(...data.bars.map((bar) => bar.total), 0);
    const top = highest > 0 ? niceCeiling(highest) : 1;
    const y = (value: number) => (value / top) * plot;
    const ticks = [0, top / 2, top];
    // a label for the first, the middle and the last bars, where there is room for them
    const labelled = new Set([0, Math.floor((count - 1) / 2), count - 1]);
    const bar = hovered === null ? null : data.bars[hovered];

    return (
        <div
            className="usage-chart"
            ref={frame}
            onPointerLeave={() => setHovered(null)}
            onPointerMove={(event) => setPointer({ x: event.clientX, y: event.clientY })}
        >
            <svg width={width} height={height} role="img" aria-label={t("The usage of the period, by model")}>
                {ticks.map((tick) => (
                    <g key={tick}>
                        <line
                            className="usage-grid"
                            x1={left}
                            x2={width}
                            y1={6 + plot - y(tick)}
                            y2={6 + plot - y(tick)}
                        />
                        <text className="usage-axis" x={left - 6} y={6 + plot - y(tick)} dy="0.32em" textAnchor="end">
                            {measure === "cost" ? axisCost(tick) : shortTokens(tick)}
                        </text>
                    </g>
                ))}
                {data.bars.map((each, index) => {
                    const x = left + index * step + gap / 2;
                    const barWidth = Math.max(1, step - gap);
                    let base = 6 + plot;
                    return (
                        <g key={each.at} className={hovered === index ? "usage-bar hovered" : "usage-bar"}>
                            {each.values.map((value, place) => {
                                if (value <= 0) {
                                    return null;
                                }
                                const tall = y(value);
                                base -= tall;
                                return (
                                    <rect
                                        key={place}
                                        x={x}
                                        y={base}
                                        width={barWidth}
                                        height={Math.max(tall, 0.5)}
                                        fill={seriesColour(place)}
                                    />
                                );
                            })}
                            {labelled.has(index) && (
                                <text
                                    className="usage-axis"
                                    x={x + barWidth / 2}
                                    y={height - 4}
                                    textAnchor={index === 0 ? "start" : index === count - 1 ? "end" : "middle"}
                                >
                                    {binLabel(each.at, hourly)}
                                </text>
                            )}
                            {/* the whole height of the bin, which is easier to point at than the bar */}
                            <rect
                                className="usage-hit"
                                x={left + index * step}
                                y={0}
                                width={step}
                                height={6 + plot}
                                onPointerEnter={() => setHovered(index)}
                            />
                        </g>
                    );
                })}
            </svg>
            {bar && (
                <Tooltip at={pointer}>
                    <strong>{binLabel(bar.at, hourly)}</strong>
                    <span className="usage-tooltip-total">{shown(bar.total, measure)}</span>
                    {bar.total > 0 && (
                        <ul>
                            {bar.values.map((value, place) =>
                                value > 0 && (
                                    <li key={place}>
                                        <span
                                            className="usage-swatch"
                                            style={{ background: seriesColour(place) }}
                                        />
                                        <span className="usage-tooltip-model">{data.models[place]}</span>
                                        <span>{shown(value, measure)}</span>
                                    </li>
                                )
                            )}
                        </ul>
                    )}
                </Tooltip>
            )}
        </div>
    );
}

/** A round number at or above `value`, for the top of the axis: 1, 2 or 5 times a power of ten. */
function niceCeiling(value: number): number {
    const power = 10 ** Math.floor(Math.log10(value));
    return [1, 2, 5, 10].map((each) => each * power).find((each) => each >= value) ?? value;
}

function axisCost(value: number): string {
    if (value === 0) {
        return "$0";
    }
    return value >= 1 ? `$${value.toFixed(value >= 10 ? 0 : 1)}` : `$${value.toPrecision(1)}`;
}

/** A part of a pie, with what it stands for. */
interface Slice {
    key: string;
    label: string;
    colour: string;
    totals: UsageTotals;
}

const PIE_SIZE = 124;
const OUTER = 58;
const INNER = 36;

/** The path of a ring's arc from `from` to `to`, as shares of the way round from the top. */
function arc(from: number, to: number): string {
    const centre = PIE_SIZE / 2;
    const point = (share: number, radius: number) => {
        const angle = share * 2 * Math.PI - Math.PI / 2;
        return `${centre + radius * Math.cos(angle)} ${centre + radius * Math.sin(angle)}`;
    };
    // a whole ring is drawn as two halves, as an arc cannot end where it starts
    if (to - from >= 0.9999) {
        return `${arc(from, from + 0.5)} ${arc(from + 0.5, from + 1)}`;
    }
    const large = to - from > 0.5 ? 1 : 0;
    return `M ${point(from, OUTER)} A ${OUTER} ${OUTER} 0 ${large} 1 ${point(to, OUTER)}`
        + ` L ${point(to, INNER)} A ${INNER} ${INNER} 0 ${large} 0 ${point(from, INNER)} Z`;
}

/**
 * What a period cost, as a pie split by what it went to, `title` under it:
 * what the part pointed at is, what it cost and how much of the whole it
 * is, with its tokens and requests, shown on hover.
 */
function Pie({ title, slices }: { title: string; slices: Slice[] }) {
    const [hovered, setHovered] = useState<string | null>(null);
    const [pointer, setPointer] = useState<Pointer>({ x: 0, y: 0 });
    const whole = slices.reduce((sum, each) => sum + each.totals.cost, 0);
    const incomplete = slices.some((each) => each.totals.costIncomplete);
    let start = 0;
    const parts = slices
        .filter((each) => each.totals.cost > 0)
        .map((each) => {
            const from = start;
            start += whole > 0 ? each.totals.cost / whole : 0;
            return { ...each, from, to: start };
        });
    const pointed = slices.find((each) => each.key === hovered) ?? null;
    return (
        <figure
            className="usage-pie"
            onPointerLeave={() => setHovered(null)}
            onPointerMove={(event) => setPointer({ x: event.clientX, y: event.clientY })}
        >
            <svg width={PIE_SIZE} height={PIE_SIZE} role="img" aria-label={t("{name}, by cost", { name: title })}>
                <circle className="usage-pie-track" cx={PIE_SIZE / 2} cy={PIE_SIZE / 2} r={(OUTER + INNER) / 2} />
                {parts.map((each) => (
                    <path
                        key={each.key}
                        d={arc(each.from, each.to)}
                        fill={each.colour}
                        className={hovered === each.key ? "hovered" : hovered ? "dimmed" : undefined}
                        onPointerEnter={() => setHovered(each.key)}
                    />
                ))}
                <text className="usage-pie-centre" x={PIE_SIZE / 2} y={PIE_SIZE / 2} dy="0.35em" textAnchor="middle">
                    {pointed && whole > 0
                        ? `${Math.round((pointed.totals.cost / whole) * 100)}%`
                        : `${incomplete ? "≥ " : ""}${formatCost(whole)}`}
                </text>
            </svg>
            <figcaption>{title}</figcaption>
            {pointed && (
                <Tooltip at={pointer}>
                    <span className="usage-tooltip-head">
                        <span className="usage-swatch" style={{ background: pointed.colour }} />
                        <strong>{pointed.label}</strong>
                    </span>
                    <span className="usage-tooltip-total">
                        <Cost totals={pointed.totals} />
                        {whole > 0 && ` · ${Math.round((pointed.totals.cost / whole) * 100)}%`}
                    </span>
                    <span>
                        {t("{in} tokens in · {out} out", {
                            in: formatTokens(pointed.totals.promptTokens),
                            out: formatTokens(pointed.totals.completionTokens),
                        })}
                    </span>
                    <span>{t("{count} requests", { count: formatTokens(pointed.totals.requests) })}</span>
                </Tooltip>
            )}
        </figure>
    );
}

/** Totals of `rows` added up. */
function added(rows: UsageTotals[]): UsageTotals {
    return rows.reduce<UsageTotals>(
        (sum, each) => ({
            requests: sum.requests + each.requests,
            promptTokens: sum.promptTokens + each.promptTokens,
            completionTokens: sum.completionTokens + each.completionTokens,
            cost: sum.cost + each.cost,
            costIncomplete: sum.costIncomplete || each.costIncomplete,
        }),
        { requests: 0, promptTokens: 0, completionTokens: 0, cost: 0, costIncomplete: false },
    );
}

/**
 * What the period cost by the kind of work it went to, as a pie, and for
 * each kind of work, the costliest first, by the models that did it, each
 * in its colour of the bars.
 */
function ByCategory({ rows, models }: { rows: UsageSummary["byModel"]; models: string[] }) {
    if (rows.length === 0) {
        return null;
    }
    // each kind of work has a colour of its own, by the order the app lists them in
    const known = Object.keys(USAGE_CATEGORIES);
    const categories = [...new Set(rows.map((row) => row.category))]
        .map((category) => ({
            category,
            rows: rows.filter((row) => row.category === category),
            totals: added(rows.filter((row) => row.category === category)),
        }))
        .sort((a, b) => b.totals.cost - a.totals.cost || a.category.localeCompare(b.category));
    const colourOfCategory = (category: string) =>
        seriesColour(
            known.includes(category) ? known.indexOf(category) : known.length + categories.findIndex(
                (each) => each.category === category,
            ),
        );
    return (
        <section className="usage-section">
            <h3>{t("By kind of work")}</h3>
            <div className="usage-pies">
                <Pie
                    title={t("All of it")}
                    slices={categories.map((each) => ({
                        key: each.category,
                        label: categoryLabel(each.category),
                        colour: colourOfCategory(each.category),
                        totals: each.totals,
                    }))}
                />
                {categories.map((each) => (
                    <Pie
                        key={each.category}
                        title={categoryLabel(each.category)}
                        slices={each.rows.map((row) => ({
                            key: row.model,
                            label: row.model,
                            colour: seriesColour(models.indexOf(row.model)),
                            totals: row,
                        }))}
                    />
                ))}
            </div>
            <ul className="usage-legend usage-categories-legend">
                {categories.map((each) => (
                    <li key={each.category}>
                        <span className="usage-swatch" style={{ background: colourOfCategory(each.category) }} />
                        <span>{categoryLabel(each.category)}</span>
                        <span className="usage-legend-value">
                            <Cost totals={each.totals} />
                        </span>
                    </li>
                ))}
            </ul>
        </section>
    );
}

/**
 * What the requests to the models cost, over a period the learner picks,
 * which is kept as they left it: the whole of it, that of what is open, the
 * bars of its hours or days stacked by model, and the table of it by the
 * kind of work and the model.
 */
export function UsagePanel({ chatId, currentLabel, revision, onClose }: Props) {
    const [view, setView] = useState<UsageView>(loadUsageView);
    const [summary, setSummary] = useState<UsageSummary | null>(null);
    const [error, setError] = useState<string | null>(null);
    // when the bins were worked out from, which is when the usage was fetched
    const [now, setNow] = useState(Date.now);

    function changeView(next: UsageView) {
        setView(next);
        saveUsageView(next);
    }

    useEffect(() => {
        let current = true;
        const at = Date.now();
        fetchUsage(chatId, periodStart(view.period, at), binOf(view.period)).then(
            (fetched) => {
                if (current) {
                    setSummary(fetched);
                    setNow(at);
                    setError(null);
                }
            },
            (caught: Error) => current && setError(caught.message),
        );
        return () => {
            current = false;
        };
    }, [chatId, revision, view.period]);

    const series = useMemo(() => summary?.series ?? [], [summary]);
    const data = useMemo(
        () => stacked(series, binStarts(view.period, now, series), view.measure),
        [series, view.period, view.measure, now],
    );
    const rows = useMemo(() => byCategoryAndModel(series), [series]);

    return (
        <SidePanel title={t("Usage")} onClose={onClose}>
            <div className="usage">
                <div className="usage-periods" role="radiogroup" aria-label={t("Period")}>
                    {(Object.keys(PERIODS) as Period[]).map((period) => (
                        <button
                            key={period}
                            role="radio"
                            aria-checked={view.period === period}
                            onClick={() => changeView({ ...view, period })}
                        >
                            {t(PERIODS[period])}
                        </button>
                    ))}
                </div>
                {error && <p className="usage-note">{t("The usage could not be loaded: {error}", { error })}</p>}
                {summary && (
                    <>
                        <section className="usage-hero">
                            <p className="usage-cost">
                                <Cost totals={summary.since} />
                            </p>
                            <p className="usage-facts">
                                {t("{in} tokens in · {out} out", {
                                    in: formatTokens(summary.since.promptTokens),
                                    out: formatTokens(summary.since.completionTokens),
                                })} · {t("{count} requests", { count: formatTokens(summary.since.requests) })}
                            </p>
                            {currentLabel !== null && (
                                <p className="usage-facts">
                                    <T
                                        message="{name}, all of it: {cost}"
                                        values={{ name: currentLabel, cost: <Cost totals={summary.chat} /> }}
                                    />{" "}
                                    · {t("{count} requests", { count: formatTokens(summary.chat.requests) })}
                                </p>
                            )}
                        </section>
                        <section className="usage-section">
                            <div className="usage-section-head">
                                <h3>
                                    {binOf(view.period) === "hour" ? t("By hour and model") : t("By day and model")}
                                </h3>
                                <div
                                    className="usage-measure"
                                    role="radiogroup"
                                    aria-label={t("What the bars measure")}
                                >
                                    {(["cost", "tokens"] as Measure[]).map((measure) => (
                                        <button
                                            key={measure}
                                            role="radio"
                                            aria-checked={view.measure === measure}
                                            onClick={() => changeView({ ...view, measure })}
                                        >
                                            {measure === "cost" ? t("Cost") : t("Tokens")}
                                        </button>
                                    ))}
                                </div>
                            </div>
                            {series.length === 0
                                ? <p className="usage-note">{t("Nothing was asked of the models in this period.")}</p>
                                : (
                                    <>
                                        <UsageChart
                                            data={data}
                                            measure={view.measure}
                                            hourly={binOf(view.period) === "hour"}
                                        />
                                        <ul className="usage-legend">
                                            {data.models.map((model, place) => (
                                                <li key={model}>
                                                    <span
                                                        className="usage-swatch"
                                                        style={{ background: seriesColour(place) }}
                                                    />
                                                    <span className="usage-legend-model" title={model}>{model}</span>
                                                    <span className="usage-legend-value">
                                                        {shown(data.totals[place], view.measure)}
                                                    </span>
                                                </li>
                                            ))}
                                        </ul>
                                    </>
                                )}
                        </section>
                        <ByCategory rows={rows} models={data.models} />
                    </>
                )}
                <p className="usage-note">
                    {t(
                        "As reported by OpenRouter for the requests made for this account, on any device. A reply stopped early is looked up on OpenRouter afterwards, as the cost of speech is, a few seconds after it ends.",
                    )}
                </p>
            </div>
        </SidePanel>
    );
}
