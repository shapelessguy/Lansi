<!--
Copyright: Ankitects Pty Ltd and contributors
License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
-->
<script lang="ts">
    import * as tr from "@generated/ftl";

    import type { PageData } from "./$types";

    export let data: PageData;
</script>

<main>
    <table>
        <thead>
            <tr>
                <th class="name">{tr.decksDeck()}</th>
                <th>{tr.actionsNew()}</th>
                <th>{tr.decksLearnHeader()}</th>
                <th>{tr.decksReviewHeader()}</th>
            </tr>
        </thead>
        <tbody>
            {#each data.decks as deck (deck.deckId)}
                <tr>
                    <td class="name" style:padding-inline-start="{deck.depth * 1.5}em">
                        {deck.name}
                    </td>
                    <td class="new" class:zero={!deck.newCount}>{deck.newCount}</td>
                    <td class="learn" class:zero={!deck.learnCount}>
                        {deck.learnCount}
                    </td>
                    <td class="review" class:zero={!deck.reviewCount}>
                        {deck.reviewCount}
                    </td>
                </tr>
            {/each}
        </tbody>
    </table>
</main>

<style lang="scss">
    main {
        max-width: 40em;
        margin: 2em auto;
        padding: 0 1em;
    }

    table {
        width: 100%;
        border-collapse: collapse;
    }

    th,
    td {
        padding: 0.4em 0.75em;
        text-align: end;
    }

    th {
        border-bottom: 1px solid var(--border);
    }

    .name {
        width: 100%;
        text-align: start;
    }

    tbody tr:hover {
        background: var(--canvas-elevated);
    }

    .new {
        color: var(--state-new);
    }

    .learn {
        color: var(--state-learn);
    }

    .review {
        color: var(--state-review);
    }

    .zero {
        color: var(--fg-disabled);
    }
</style>
