// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
import {
    getConnectionProfiles,
    getReviewHistory,
    getSelectedConnectionProfileId,
    getTokens,
    usageTotals,
} from "@tslib/llm";

import type { PageLoad } from "./$types";
import { withTokens } from "./lib";

export const load = (async () => {
    const [configs, tokens, selectedId, history] = await Promise.all([
        getConnectionProfiles(),
        getTokens(),
        getSelectedConnectionProfileId(),
        getReviewHistory(),
    ]);
    return { profiles: withTokens(configs, tokens), selectedId, usage: usageTotals(history) };
}) satisfies PageLoad;
