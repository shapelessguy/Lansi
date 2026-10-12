// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

/**
 * Storage for the AI exercise/chat feature.
 *
 * Everything except API tokens lives in the collection config under the same
 * keys and JSON shapes AnkiDroid uses, so it syncs between devices. AnkiDroid
 * decodes these values strictly: an unknown key or a missing required one makes
 * it discard the whole value. The normalize* functions below therefore emit
 * exactly the fields AnkiDroid knows about, and nothing else may be written.
 */

import { getConfigJson, llmChat, setConfigJson } from "@generated/backend";

import { getProfileConfig, setProfileConfig } from "./profile";

const KEY_EXERCISES = "llm.exercises";
const KEY_NOTETYPE_DEFAULTS = "llm.notetypeDefaults";
const KEY_REVIEW_HISTORY = "llm.reviewHistory";
const KEY_KNOWN_VOCAB = "llm.knownVocab";
const KEY_QUICK_PROMPTS = "llm.quickPrompts";
const KEY_CONNECTION_PROFILES = "llm.connectionProfiles";
const KEY_SELECTED_CONNECTION_PROFILE = "llm.selectedConnectionProfileId";
/** Profile config, so tokens stay on this device instead of syncing. */
const KEY_TOKENS = "llmTokens";

export const MAX_REVIEW_HISTORY_ENTRIES = 500;
export const MAX_KNOWN_VOCAB_ENTRIES = 2000;
export const DEFAULT_VOCAB_WORD_BUDGET = 200;

/** Reserved exercise ids for usage that isn't tied to a saved exercise. */
export const HINT_PSEUDO_EXERCISE_ID = -1;
export const MORE_INFO_PSEUDO_EXERCISE_ID = -2;
export const TRANSLATION_PSEUDO_EXERCISE_ID = -3;

export type VocabSelectionMode = "RANDOM" | "TEMPORAL" | "RECENTLY_REVIEWED";
export type QuickPromptType = "HINT" | "MORE_INFO";
export type CardStatus = "ok" | "not_ok" | "pending";

/** $/1M tokens, used only to estimate cost in the usage summary. */
export interface Pricing {
    inputPerMillion: number;
    outputPerMillion: number;
}

export interface ExerciseConfig {
    id: number;
    notetypeId: number;
    exerciseName: string;
    systemPrompt: string;
    /** Note fields used to build the reference vocabulary list. */
    vocabularyFields: string[];
    vocabularySelectionMode: VocabSelectionMode;
    /** A free-form chat that isn't linked to a specific card. */
    cardUnrelated: boolean;
    vocabularyWordBudget: number;
    /** Blank disables word-by-word translation in the chat. */
    translationLanguage: string;
    /** Blank lets the model infer it from the system prompt. */
    practiceLanguage: string;
    aiStartsFirst: boolean;
}

export interface ReviewHistoryEntry {
    dayCode: number;
    exerciseId: number;
    /** Null for a chat that isn't linked to a card. */
    noteId: number | null;
    cardStatus: CardStatus;
    promptTokens: number;
    completionTokens: number;
    /** Snapshot of the price in effect when the call was made. */
    pricing: Pricing;
}

export interface KnownVocabEntry {
    notetypeId: number;
    noteId: number;
    consecutiveOkCount: number;
    lastReviewedDayCode: number;
}

export interface QuickPromptConfig {
    notetypeId: number;
    type: QuickPromptType;
    taskDescription: string;
}

/** A saved connection, minus its token. */
export interface ConnectionProfileConfig {
    id: number;
    apiEndpoint: string;
    modelName: string;
    pricing: Pricing;
}

export interface LlmConfig {
    apiEndpoint: string;
    apiToken: string;
    modelName: string;
    pricing: Pricing;
}

export interface LlmMessage {
    role: "system" | "user" | "assistant";
    content: string;
}

export interface LlmReply {
    text: string;
    promptTokens: number;
    completionTokens: number;
}

export interface UsageTotals {
    promptTokens: number;
    completionTokens: number;
    cost: number;
}

// Decoding
// AnkiDroid omits fields that hold their default value, so they are filled back
// in here.

function asArray(value: unknown): any[] {
    return Array.isArray(value) ? value : [];
}

function asInt(value: unknown, fallback = 0): number {
    return typeof value === "number" && Number.isFinite(value) ? Math.round(value) : fallback;
}

function asNumber(value: unknown): number {
    return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function asString(value: unknown): string {
    return typeof value === "string" ? value : "";
}

function normalizePricing(raw: any): Pricing {
    return {
        inputPerMillion: asNumber(raw?.inputPerMillion),
        outputPerMillion: asNumber(raw?.outputPerMillion),
    };
}

export function normalizeExercise(raw: any): ExerciseConfig {
    const mode = raw?.vocabularySelectionMode;
    return {
        id: asInt(raw?.id),
        notetypeId: asInt(raw?.notetypeId),
        exerciseName: asString(raw?.exerciseName),
        systemPrompt: asString(raw?.systemPrompt),
        vocabularyFields: asArray(raw?.vocabularyFields).filter((f) => typeof f === "string"),
        vocabularySelectionMode: mode === "TEMPORAL" || mode === "RECENTLY_REVIEWED" ? mode : "RANDOM",
        cardUnrelated: raw?.cardUnrelated === true,
        vocabularyWordBudget: asInt(raw?.vocabularyWordBudget, DEFAULT_VOCAB_WORD_BUDGET),
        translationLanguage: asString(raw?.translationLanguage),
        practiceLanguage: asString(raw?.practiceLanguage),
        aiStartsFirst: raw?.aiStartsFirst !== false,
    };
}

export function normalizeReviewHistoryEntry(raw: any): ReviewHistoryEntry {
    const status = raw?.cardStatus;
    return {
        dayCode: asInt(raw?.dayCode),
        exerciseId: asInt(raw?.exerciseId),
        noteId: typeof raw?.noteId === "number" ? asInt(raw.noteId) : null,
        cardStatus: status === "ok" || status === "not_ok" ? status : "pending",
        promptTokens: asInt(raw?.promptTokens),
        completionTokens: asInt(raw?.completionTokens),
        pricing: normalizePricing(raw?.pricing),
    };
}

export function normalizeKnownVocabEntry(raw: any): KnownVocabEntry {
    return {
        notetypeId: asInt(raw?.notetypeId),
        noteId: asInt(raw?.noteId),
        consecutiveOkCount: asInt(raw?.consecutiveOkCount),
        lastReviewedDayCode: asInt(raw?.lastReviewedDayCode),
    };
}

export function normalizeQuickPrompt(raw: any): QuickPromptConfig {
    return {
        notetypeId: asInt(raw?.notetypeId),
        type: raw?.type === "MORE_INFO" ? "MORE_INFO" : "HINT",
        taskDescription: asString(raw?.taskDescription),
    };
}

export function normalizeConnectionProfile(raw: any): ConnectionProfileConfig {
    return {
        id: asInt(raw?.id),
        apiEndpoint: asString(raw?.apiEndpoint),
        modelName: asString(raw?.modelName),
        pricing: normalizePricing(raw?.pricing),
    };
}

// Pure helpers

/** One greater than the highest existing id; 1 if there are none yet. */
export function nextId(items: { id: number }[]): number {
    return Math.max(0, ...items.map((item) => item.id)) + 1;
}

export function upsertExercise(exercises: ExerciseConfig[], exercise: ExerciseConfig): ExerciseConfig[] {
    return [...exercises.filter((e) => e.id !== exercise.id), exercise];
}

/**
 * Drops defaults that point at a deleted or chat-only exercise, so a stale
 * entry can never become what the reviewer picks for a note type.
 */
export function validNotetypeDefaults(
    stored: Record<string, number>,
    exercises: ExerciseConfig[],
): Record<string, number> {
    const cardExerciseIds = new Set(exercises.filter((e) => !e.cardUnrelated).map((e) => e.id));
    return Object.fromEntries(Object.entries(stored).filter(([, exerciseId]) => cardExerciseIds.has(exerciseId)));
}

function sameSession(a: ReviewHistoryEntry, b: ReviewHistoryEntry): boolean {
    return a.dayCode === b.dayCode && a.exerciseId === b.exerciseId && a.noteId === b.noteId;
}

/** Replaces any entry for the same day, exercise and note, and caps the log. */
export function upsertReviewHistory(history: ReviewHistoryEntry[], entry: ReviewHistoryEntry): ReviewHistoryEntry[] {
    return [...history.filter((e) => !sameSession(e, entry)), entry].slice(-MAX_REVIEW_HISTORY_ENTRIES);
}

export function upsertKnownVocab(vocab: KnownVocabEntry[], entry: KnownVocabEntry): KnownVocabEntry[] {
    const others = vocab.filter((e) => !(e.notetypeId === entry.notetypeId && e.noteId === entry.noteId));
    return [...others, entry].slice(-MAX_KNOWN_VOCAB_ENTRIES);
}

/** A blank description clears the override, restoring the built-in guidance. */
export function withQuickPrompt(
    prompts: QuickPromptConfig[],
    notetypeId: number,
    type: QuickPromptType,
    taskDescription: string,
): QuickPromptConfig[] {
    const others = prompts.filter((p) => !(p.notetypeId === notetypeId && p.type === type));
    const trimmed = taskDescription.trim();
    return trimmed ? [...others, { notetypeId, type, taskDescription: trimmed }] : others;
}

/** Each entry is priced at the rate recorded with it, not the current one. */
export function usageTotals(history: ReviewHistoryEntry[]): UsageTotals {
    const totals = { promptTokens: 0, completionTokens: 0, cost: 0 };
    for (const entry of history) {
        totals.promptTokens += entry.promptTokens;
        totals.completionTokens += entry.completionTokens;
        totals.cost += (entry.promptTokens * entry.pricing.inputPerMillion
            + entry.completionTokens * entry.pricing.outputPerMillion) / 1_000_000;
    }
    return totals;
}

/**
 * The connection to make API calls with, or null if no profile is selected,
 * the selected one no longer exists, or this device has no token for it.
 */
export function resolveLlmConfig(
    profiles: ConnectionProfileConfig[],
    selectedId: number | null,
    tokens: Record<string, string>,
): LlmConfig | null {
    const profile = profiles.find((p) => p.id === selectedId);
    const apiToken = (profile && tokens[profile.id]) ?? "";
    if (!profile || !apiToken.trim()) {
        return null;
    }
    return { apiEndpoint: profile.apiEndpoint, apiToken, modelName: profile.modelName, pricing: profile.pricing };
}

/** Days since the Unix epoch, the unit review history is keyed on. */
export function currentDayCode(nowMillis: number = Date.now()): number {
    return Math.floor(nowMillis / 86_400_000);
}

// Collection config

async function getConfig(key: string): Promise<unknown> {
    const json = new TextDecoder().decode((await getConfigJson({ val: key })).json);
    return JSON.parse(json);
}

/** Not undoable, so usage bookkeeping doesn't end up in the undo queue. */
async function setConfig(key: string, value: unknown): Promise<void> {
    const valueJson = new TextEncoder().encode(JSON.stringify(value));
    await setConfigJson({ key, valueJson, undoable: false });
}

export async function getExercises(): Promise<ExerciseConfig[]> {
    return asArray(await getConfig(KEY_EXERCISES)).map(normalizeExercise);
}

export async function saveExercise(exercise: ExerciseConfig): Promise<void> {
    await setConfig(KEY_EXERCISES, upsertExercise(await getExercises(), normalizeExercise(exercise)));
}

export async function deleteExercise(id: number): Promise<void> {
    const remaining = (await getExercises()).filter((e) => e.id !== id);
    await setConfig(KEY_EXERCISES, remaining);
    await setConfig(KEY_NOTETYPE_DEFAULTS, validNotetypeDefaults(await getStoredNotetypeDefaults(), remaining));
}

async function getStoredNotetypeDefaults(): Promise<Record<string, number>> {
    const stored = await getConfig(KEY_NOTETYPE_DEFAULTS);
    if (stored === null || typeof stored !== "object" || Array.isArray(stored)) {
        return {};
    }
    return Object.fromEntries(Object.entries(stored).filter(([, id]) => typeof id === "number"));
}

/** Map of note type id to the exercise the reviewer should use for it. */
export async function getNotetypeDefaults(): Promise<Record<string, number>> {
    return validNotetypeDefaults(await getStoredNotetypeDefaults(), await getExercises());
}

/** Ignored for a chat-only exercise, which isn't tied to any card. */
export async function setDefaultExercise(notetypeId: number, exerciseId: number): Promise<void> {
    const exercises = await getExercises();
    if (!exercises.some((e) => e.id === exerciseId && !e.cardUnrelated)) {
        return;
    }
    const defaults = validNotetypeDefaults(await getStoredNotetypeDefaults(), exercises);
    await setConfig(KEY_NOTETYPE_DEFAULTS, { ...defaults, [notetypeId]: exerciseId });
}

export async function getReviewHistory(): Promise<ReviewHistoryEntry[]> {
    return asArray(await getConfig(KEY_REVIEW_HISTORY)).map(normalizeReviewHistoryEntry);
}

/**
 * Call after every LLM reply rather than only when a session ends, so usage is
 * not lost if the user leaves partway through.
 */
export async function recordReview(entry: ReviewHistoryEntry): Promise<void> {
    const updated = upsertReviewHistory(await getReviewHistory(), normalizeReviewHistoryEntry(entry));
    await setConfig(KEY_REVIEW_HISTORY, updated);
}

export async function getKnownVocab(): Promise<KnownVocabEntry[]> {
    return asArray(await getConfig(KEY_KNOWN_VOCAB)).map(normalizeKnownVocabEntry);
}

export async function recordKnownVocab(entry: KnownVocabEntry): Promise<void> {
    await setConfig(KEY_KNOWN_VOCAB, upsertKnownVocab(await getKnownVocab(), normalizeKnownVocabEntry(entry)));
}

export async function getQuickPrompts(): Promise<QuickPromptConfig[]> {
    return asArray(await getConfig(KEY_QUICK_PROMPTS)).map(normalizeQuickPrompt);
}

export async function setQuickPrompt(
    notetypeId: number,
    type: QuickPromptType,
    taskDescription: string,
): Promise<void> {
    await setConfig(KEY_QUICK_PROMPTS, withQuickPrompt(await getQuickPrompts(), notetypeId, type, taskDescription));
}

export async function getConnectionProfiles(): Promise<ConnectionProfileConfig[]> {
    return asArray(await getConfig(KEY_CONNECTION_PROFILES)).map(normalizeConnectionProfile);
}

export async function saveConnectionProfiles(profiles: ConnectionProfileConfig[]): Promise<void> {
    await setConfig(KEY_CONNECTION_PROFILES, profiles.map(normalizeConnectionProfile));
}

export async function getSelectedConnectionProfileId(): Promise<number | null> {
    const id = await getConfig(KEY_SELECTED_CONNECTION_PROFILE);
    return typeof id === "number" ? id : null;
}

export async function setSelectedConnectionProfileId(id: number | null): Promise<void> {
    await setConfig(KEY_SELECTED_CONNECTION_PROFILE, id);
}

// Device-local tokens

/** API tokens keyed by connection profile id. */
export async function getTokens(): Promise<Record<string, string>> {
    const stored = await getProfileConfig(KEY_TOKENS);
    if (stored === null || typeof stored !== "object" || Array.isArray(stored)) {
        return {};
    }
    return Object.fromEntries(Object.entries(stored).filter(([, token]) => typeof token === "string")) as Record<
        string,
        string
    >;
}

/** A blank token removes the entry. */
export async function setToken(profileId: number, token: string): Promise<void> {
    const tokens = await getTokens();
    if (token.trim()) {
        tokens[profileId] = token;
    } else {
        delete tokens[profileId];
    }
    await setProfileConfig(KEY_TOKENS, tokens);
}

export async function getActiveLlmConfig(): Promise<LlmConfig | null> {
    return resolveLlmConfig(
        await getConnectionProfiles(),
        await getSelectedConnectionProfileId(),
        await getTokens(),
    );
}

// Requests

/** Rejects with the provider's error message if the request fails. */
export async function complete(
    config: Pick<LlmConfig, "apiEndpoint" | "apiToken" | "modelName">,
    messages: LlmMessage[],
    temperature?: number,
): Promise<LlmReply> {
    const reply = await llmChat(
        {
            apiEndpoint: config.apiEndpoint,
            apiToken: config.apiToken,
            modelName: config.modelName,
            messages,
            temperature,
        },
        { alertOnError: false },
    );
    return { text: reply.text, promptTokens: reply.promptTokens, completionTokens: reply.completionTokens };
}
