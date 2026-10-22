// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { useEffect, useState } from "react";
import { t } from "../lib/i18n";
import { fetchModelsAt, type ModelChoice } from "../lib/models";

/** What the list says in place of an id for a value that is typed, or asked at an address. */
const CUSTOM = "\0custom";
const ADDRESS = "\0address";
/** What it says for naming no model, where another stands in. */
const NONE = "\0none";

type Mode = "list" | "custom" | "address";

interface Props {
    /** What the model is for, which its controls are named by. */
    label: string;
    value: ModelChoice;
    onChange: (value: ModelChoice) => void;
    /** The models OpenRouter has of the kind, by their ids; empty until they are known. */
    listed: string[];
    /** What stands in for no model, such as "the chat model", where one may be named. */
    none?: string;
}

/**
 * Picks a model the one way every model is picked: a list that starts with
 * a model of OpenRouter typed by its id, and one asked at the address of a
 * server that takes OpenAI's requests, such as one on this machine, with
 * what OpenRouter has of the kind after them.
 */
export function ModelPicker({ label, value, onChange, listed, none }: Props) {
    const [mode, setMode] = useState<Mode>(() =>
        value.url ? "address" : !value.model || listed.length === 0 || listed.includes(value.model) ? "list" : "custom"
    );
    // a model that is not in the list, once the list is known, is one that was typed
    useEffect(() => {
        if (mode === "list" && value.model && listed.length > 0 && !listed.includes(value.model)) {
            setMode("custom");
        }
    }, [mode, value.model, listed]);

    function choose(picked: string) {
        if (picked === CUSTOM) {
            setMode("custom");
            onChange({ model: value.url ? "" : value.model, url: "", key: "" });
        } else if (picked === ADDRESS) {
            setMode("address");
            onChange({ ...value, model: value.url ? value.model : "" });
        } else {
            setMode("list");
            onChange({ model: picked === NONE ? "" : picked, url: "", key: "" });
        }
    }

    const selected = mode === "custom"
        ? CUSTOM
        : mode === "address"
        ? ADDRESS
        : value.model || (none ? NONE : "");
    return (
        <>
            <select aria-label={label} value={selected} onChange={(event) => choose(event.target.value)}>
                <option value={CUSTOM}>{t("Custom OpenRouter model…")}</option>
                <option value={ADDRESS}>{t("OpenAI-compatible server…")}</option>
                {none && <option value={NONE}>{t("Same as {name}", { name: none })}</option>}
                {/* the usual model, until the list is known */}
                {mode === "list" && value.model && !listed.includes(value.model) && (
                    <option value={value.model}>{value.model}</option>
                )}
                {!none && mode === "list" && !value.model && <option value="">{t("Choose a model")}</option>}
                {listed.map((id) => <option key={id} value={id}>{id}</option>)}
            </select>
            {mode === "custom" && (
                <input
                    type="text"
                    aria-label={t("{label}: its id on OpenRouter", { label })}
                    spellCheck={false}
                    placeholder="provider/model"
                    value={value.model}
                    onChange={(event) => onChange({ ...value, model: event.target.value.trim() })}
                />
            )}
            {mode === "address" && <AtAddress label={label} value={value} onChange={onChange} />}
        </>
    );
}

/** The address, key and model of one asked at a server of the learner's own. */
function AtAddress({ label, value, onChange }: Pick<Props, "label" | "value" | "onChange">) {
    const [models, setModels] = useState<string[]>([]);
    const [problem, setProblem] = useState("");

    // what the server has is asked once its address has been left alone for a moment
    useEffect(() => {
        setModels([]);
        setProblem("");
        if (!/^https?:\/\/./.test(value.url)) {
            return;
        }
        let stopped = false;
        const timer = setTimeout(() => {
            fetchModelsAt(value.url, value.key).then(
                (found) => stopped || setModels(found),
                (error: Error) => stopped || setProblem(error.message),
            );
        }, 500);
        return () => {
            stopped = true;
            clearTimeout(timer);
        };
    }, [value.url, value.key]);

    return (
        <>
            <input
                type="url"
                aria-label={t("{label}: address of the server", { label })}
                spellCheck={false}
                placeholder="http://127.0.0.1:8000/v1"
                value={value.url}
                onChange={(event) => onChange({ ...value, url: event.target.value.trim() })}
            />
            <input
                type="password"
                autoComplete="off"
                aria-label={t("{label}: key of the server", { label })}
                placeholder={t("Key, if the server needs one")}
                value={value.key}
                onChange={(event) => onChange({ ...value, key: event.target.value.trim() })}
            />
            <OpenChoice
                label={t("{label}: model on the server", { label })}
                options={models}
                placeholder={t("model")}
                value={value.model}
                onChange={(model) => onChange({ ...value, model })}
            />
            {problem && <small className="hint error">{problem}</small>}
        </>
    );
}

interface OpenChoiceProps {
    label: string;
    /** What can be chosen, once that is known. */
    options: string[];
    value: string;
    placeholder?: string;
    onChange: (value: string) => void;
}

/**
 * A list to choose from, which starts with a value that is typed. Until it
 * is known what there is to choose from, the value is typed.
 */
export function OpenChoice({ label, options, value, placeholder, onChange }: OpenChoiceProps) {
    const [typing, setTyping] = useState(false);
    const typed = typing || options.length === 0 || (value !== "" && !options.includes(value));
    return (
        <>
            {options.length > 0 && (
                <select
                    aria-label={label}
                    value={typed ? CUSTOM : value}
                    onChange={(event) => {
                        const custom = event.target.value === CUSTOM;
                        setTyping(custom);
                        if (!custom) {
                            onChange(event.target.value);
                        }
                    }}
                >
                    <option value={CUSTOM}>{t("Custom…")}</option>
                    {value === "" && !typing && <option value="">{t("Choose one")}</option>}
                    {options.map((option) => <option key={option} value={option}>{option}</option>)}
                </select>
            )}
            {typed && (
                <input
                    type="text"
                    aria-label={label}
                    spellCheck={false}
                    placeholder={placeholder}
                    value={value}
                    onChange={(event) => onChange(event.target.value.trim())}
                />
            )}
        </>
    );
}
