<!--
Copyright: Ankitects Pty Ltd and contributors
License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
-->
<script lang="ts">
    import "../deck-options/deck-options-base.scss";

    import * as tr from "@generated/ftl";
    import {
        complete,
        saveConnectionProfiles,
        setSelectedConnectionProfileId,
        setToken,
    } from "@tslib/llm";

    import TitledContainer from "$lib/components/TitledContainer.svelte";

    import type { PageData } from "./$types";
    import type { ConnectionProfile, ProfileDraft } from "./lib";
    import {
        applyDraft,
        DEFAULT_ENDPOINT,
        draftFromProfile,
        newDraft,
        toConfig,
    } from "./lib";

    export let data: PageData;

    let profiles: ConnectionProfile[] = data.profiles;
    let selectedId: number | null = data.selectedId;
    const usage = data.usage;

    let draft: ProfileDraft | null = null;
    let testing = false;
    let testResult: { ok: boolean; message: string } | null = null;

    $: selected = profiles.find((p) => p.id === selectedId) ?? null;

    document.documentElement.classList.add("system-font-size");

    async function select(id: number | null): Promise<void> {
        selectedId = id;
        testResult = null;
        await setSelectedConnectionProfileId(id);
    }

    async function saveDraft(): Promise<void> {
        if (!draft) {
            return;
        }
        const result = applyDraft(profiles, draft);
        profiles = result.profiles;
        draft = null;
        testResult = null;
        await saveConnectionProfiles(profiles.map(toConfig));
        await setToken(result.saved.id, result.saved.apiToken);
        // the first saved profile becomes the selected one
        if (selectedId === null) {
            await select(result.saved.id);
        }
    }

    async function remove(id: number): Promise<void> {
        profiles = profiles.filter((p) => p.id !== id);
        await saveConnectionProfiles(profiles.map(toConfig));
        await setToken(id, "");
        if (selectedId === id) {
            await select(null);
        }
    }

    async function testConnection(): Promise<void> {
        if (!selected) {
            return;
        }
        testing = true;
        testResult = null;
        try {
            await complete(
                { ...selected, apiEndpoint: selected.apiEndpoint || DEFAULT_ENDPOINT },
                [
                    {
                        role: "system",
                        content: "You are a test bot. Reply only with 'OK'.",
                    },
                    { role: "user", content: "ping" },
                ],
            );
            testResult = { ok: true, message: tr.llmConnectionSucceeded() };
        } catch (err) {
            const error = err instanceof Error ? err.message : String(err);
            testResult = { ok: false, message: tr.llmConnectionFailed({ error }) };
        } finally {
            testing = false;
        }
    }

    function formatCost(cost: number): string {
        return `$${cost.toFixed(4)}`;
    }
</script>

<div class="page">
    <TitledContainer title={tr.llmConnectionProfiles()}>
        {#if profiles.length === 0}
            <p class="muted">{tr.llmNoProfiles()}</p>
        {/if}

        {#each profiles as profile (profile.id)}
            <div class="profile">
                <input
                    type="radio"
                    name="selected-profile"
                    aria-label={tr.llmUseThisProfile()}
                    title={tr.llmUseThisProfile()}
                    checked={profile.id === selectedId}
                    on:change={() => select(profile.id)}
                />
                <div class="profile-details">
                    <div>{profile.modelName || profile.apiEndpoint}</div>
                    {#if profile.modelName}
                        <div class="muted">{profile.apiEndpoint}</div>
                    {/if}
                    {#if !profile.apiToken}
                        <div class="warning">{tr.llmProfileNeedsToken()}</div>
                    {/if}
                </div>
                <button
                    type="button"
                    class="btn btn-secondary"
                    on:click={() => (draft = draftFromProfile(profile))}
                >
                    {tr.llmEdit()}
                </button>
                <button
                    type="button"
                    class="btn btn-secondary"
                    on:click={() => remove(profile.id)}
                >
                    {tr.actionsDelete()}
                </button>
            </div>
        {/each}

        {#if draft}
            <form class="draft" on:submit|preventDefault={saveDraft}>
                <label>
                    {tr.llmApiEndpoint()}
                    <input
                        type="text"
                        class="form-control"
                        bind:value={draft.apiEndpoint}
                    />
                </label>
                <label>
                    {tr.llmApiToken()}
                    <input
                        type="password"
                        class="form-control"
                        autocomplete="off"
                        bind:value={draft.apiToken}
                    />
                    <span class="muted">{tr.llmApiTokenStaysOnDevice()}</span>
                </label>
                <label>
                    {tr.llmModelName()}
                    <input
                        type="text"
                        class="form-control"
                        bind:value={draft.modelName}
                    />
                </label>
                <label>
                    {tr.llmInputCost()}
                    <input
                        type="number"
                        class="form-control"
                        min="0"
                        step="any"
                        bind:value={draft.inputPerMillion}
                    />
                </label>
                <label>
                    {tr.llmOutputCost()}
                    <input
                        type="number"
                        class="form-control"
                        min="0"
                        step="any"
                        bind:value={draft.outputPerMillion}
                    />
                </label>
                <div class="buttons">
                    <button type="submit" class="btn btn-primary">
                        {tr.actionsSave()}
                    </button>
                    <button
                        type="button"
                        class="btn btn-secondary"
                        on:click={() => (draft = null)}
                    >
                        {tr.actionsCancel()}
                    </button>
                </div>
            </form>
        {:else}
            <div class="buttons">
                <button
                    type="button"
                    class="btn btn-primary"
                    on:click={() => (draft = newDraft(profiles))}
                >
                    {tr.llmAddProfile()}
                </button>
                <button
                    type="button"
                    class="btn btn-secondary"
                    disabled={!selected || testing}
                    on:click={testConnection}
                >
                    {tr.llmTestConnection()}
                </button>
            </div>
        {/if}

        {#if testResult}
            <p class:warning={!testResult.ok} role="status">{testResult.message}</p>
        {/if}
    </TitledContainer>

    <TitledContainer title={tr.llmUsageStatistics()}>
        <table class="usage">
            <tbody>
                <tr>
                    <th>{tr.llmPromptTokens()}</th>
                    <td>{usage.promptTokens.toLocaleString()}</td>
                </tr>
                <tr>
                    <th>{tr.llmCompletionTokens()}</th>
                    <td>{usage.completionTokens.toLocaleString()}</td>
                </tr>
                <tr>
                    <th>{tr.llmTotalTokens()}</th>
                    <td>
                        {(usage.promptTokens + usage.completionTokens).toLocaleString()}
                    </td>
                </tr>
                <tr>
                    <th>{tr.llmTotalCost()}</th>
                    <td>{formatCost(usage.cost)}</td>
                </tr>
            </tbody>
        </table>
    </TitledContainer>
</div>

<style lang="scss">
    .page {
        display: flex;
        flex-direction: column;
        gap: 1em;
        max-width: 42em;
        margin: 1em auto;
        padding: 0 1em;
    }

    .profile {
        display: flex;
        align-items: center;
        gap: 0.75em;
        padding: 0.5em 0;
        border-bottom: 1px solid var(--border-subtle);
    }

    .profile-details {
        flex: 1;
        min-width: 0;
        overflow-wrap: anywhere;
    }

    .draft {
        display: flex;
        flex-direction: column;
        gap: 0.75em;
        margin-top: 1em;

        label {
            display: flex;
            flex-direction: column;
            gap: 0.25em;
        }
    }

    .buttons {
        display: flex;
        gap: 0.5em;
        margin-top: 1em;
    }

    .muted {
        color: var(--fg-subtle);
        font-size: 0.9em;
    }

    .warning {
        color: var(--fg-error, var(--accent-danger));
    }

    .usage {
        th {
            font-weight: normal;
            padding-inline-end: 2em;
        }

        td {
            text-align: end;
        }
    }
</style>
