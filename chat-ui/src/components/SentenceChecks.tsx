// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { t } from "../lib/i18n";
import { type ExerciseInfo, sentencesChecked } from "../lib/practice";
import type { Settings } from "../lib/settings";
import { type CheckedPlace, placeChecked, withPlaceChecked } from "../lib/writing";
import { Toggle } from "./Toggle";

/** The icon that turns the checks of the sentences on and off, as every place where something is written has it. */
function SentenceChecksToggle(
    { on, onChange, title, disabled }: {
        on: boolean;
        onChange: (on: boolean) => void;
        title: string;
        disabled?: boolean;
    },
) {
    return (
        <Toggle
            icon="sentence-checks"
            label={t("Sentence checks")}
            on={on}
            title={title}
            disabled={disabled}
            onChange={onChange}
        />
    );
}

/**
 * Turns the checks of the sentences written in `place`, the chat, the
 * tutor or the texts, on and off; the choice is remembered for the place.
 * The spelling is checked either way.
 */
export function PlaceSentenceChecks(
    { place, settings, onChangeSettings }: {
        place: CheckedPlace;
        settings: Settings;
        onChangeSettings: (settings: Settings) => void;
    },
) {
    return (
        <SentenceChecksToggle
            on={placeChecked(place, settings)}
            title={t(
                "The sentence check model checks each sentence you finish here, with the questions of your settings.",
            )}
            onChange={(checked) => onChangeSettings(withPlaceChecked(settings, place, checked))}
        />
    );
}

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
 * next time. Where the manifest decides, the icon says what it decided and
 * cannot be changed. The spelling is checked either way.
 */
export function SentenceChecks({ exercise, settings, onChangeSettings }: Props) {
    if (!exercise) {
        return null;
    }
    const checked = sentencesChecked(exercise.id, settings.exerciseSentenceChecks);
    const optional = exercise.sentence_checks === "optional";
    return (
        <SentenceChecksToggle
            on={checked}
            disabled={!optional}
            title={optional
                ? t(
                    "The sentence check model checks each sentence you finish here, as in the chat, with the questions of your settings.",
                )
                : checked
                ? t("This exercise always has its sentences checked.")
                : t("This exercise does not have its sentences checked.")}
            onChange={(on) =>
                onChangeSettings({
                    ...settings,
                    exerciseSentenceChecks: { ...settings.exerciseSentenceChecks, [exercise.id]: on },
                })}
        />
    );
}
