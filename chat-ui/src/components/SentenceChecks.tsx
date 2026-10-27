// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { t } from "../lib/i18n";
import { type ExerciseInfo, sentencesChecked } from "../lib/practice";
import type { Settings } from "../lib/settings";
import { Check } from "./Check";

interface Props {
    /** The exercise being done, if it is known yet. */
    exercise: ExerciseInfo | undefined;
    settings: Settings;
    onChangeSettings: (settings: Settings) => void;
}

/**
 * Turns the checks of the sentences written in an exercise by the sentence
 * check model on and off, in the bar of the session, for an exercise whose
 * manifest leaves them to the learner; the choice is remembered for the
 * next time. The spelling is checked either way.
 */
export function SentenceChecks({ exercise, settings, onChangeSettings }: Props) {
    if (exercise?.sentence_checks !== "optional") {
        return null;
    }
    return (
        <Check
            checked={sentencesChecked(exercise.id, settings.exerciseSentenceChecks)}
            title={t(
                "The sentence check model checks each sentence you finish here, as in the chat, with the questions of your settings.",
            )}
            onChange={(checked) =>
                onChangeSettings({
                    ...settings,
                    exerciseSentenceChecks: { ...settings.exerciseSentenceChecks, [exercise.id]: checked },
                })}
        >
            {t("Sentence checks")}
        </Check>
    );
}
