// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { t } from "../lib/i18n";
import {
    INTO_PLACEHOLDER,
    LANGUAGE_PLACEHOLDER,
    LEVEL_PLACEHOLDER,
    type Settings,
    WORDS_PLACEHOLDER,
} from "../lib/settings";

/** The keywords a prompt can have, each with what it is replaced by for this learner. */
export function PromptKeywords({ settings }: { settings: Settings }) {
    return (
        <dl className="keywords">
            <div>
                <dt>
                    <code>{LANGUAGE_PLACEHOLDER}</code>
                </dt>
                <dd>{t("the language you are learning ({language})", { language: settings.language })}</dd>
            </div>
            <div>
                <dt>
                    <code>{LEVEL_PLACEHOLDER}</code>
                </dt>
                <dd>{t("your level in it ({level})", { level: settings.level })}</dd>
            </div>
            <div>
                <dt>
                    <code>{INTO_PLACEHOLDER}</code>
                </dt>
                <dd>
                    {t("the language things are translated into for you ({language})", {
                        language: settings.translateInto,
                    })}
                </dd>
            </div>
            <div>
                <dt>
                    <code>{WORDS_PLACEHOLDER}</code>
                </dt>
                <dd>{t("the words of the set in use, picked in the Vocabulary tab")}</dd>
            </div>
            <div>
                <dt>
                    <code>{t("{{words:Name}}")}</code>
                </dt>
                <dd>{t("the words of the set of that name")}</dd>
            </div>
        </dl>
    );
}
