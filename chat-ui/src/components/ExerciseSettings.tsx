// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { type ExerciseInfo, MAX_INSTANCES, MAX_MINUTES, type OptionValue } from "../lib/practice";

/** An exercise that was chosen, with how many times it is done and what its options are set to. */
export interface ChosenExercise {
    exercise: ExerciseInfo;
    instances: number;
    /** How many minutes it may take, 0 for no limit. */
    minutes: number;
    values: Record<string, OptionValue>;
}

interface Props {
    chosen: ChosenExercise;
    onInstances: (exercise: ExerciseInfo, instances: number) => void;
    onMinutes: (exercise: ExerciseInfo, minutes: number) => void;
    onChange: (exercise: ExerciseInfo, name: string, value: OptionValue) => void;
}

/** A whole number typed in a box, within its bounds, or nothing while it is not one. */
function typedNumber(typed: number, least: number, most: number): number | null {
    return Number.isFinite(typed) ? Math.min(most, Math.max(least, Math.round(typed))) : null;
}

/**
 * The settings of an exercise chosen, shown under it as it is chosen: how
 * many times it is done, how long it may take, and the options its
 * manifest has. They are remembered for the next time.
 */
export function ExerciseSettings({ chosen, onInstances, onMinutes, onChange }: Props) {
    const { exercise, instances, minutes, values } = chosen;
    if (exercise.once && Object.keys(exercise.options ?? {}).length === 0) {
        return null;
    }
    return (
        <div className="exercise-settings">
            {/* one done once has neither how many times nor a time limit to choose */}
            {!exercise.once && (
                <>
                    <label className="exercise-setting">
                        <span>Times</span>
                        <span className="exercise-setting-number">
                            <input
                                type="number"
                                min={1}
                                max={MAX_INSTANCES}
                                title={`1 to ${MAX_INSTANCES}`}
                                value={instances}
                                onChange={(event) => {
                                    const typed = typedNumber(event.target.valueAsNumber, 1, MAX_INSTANCES);
                                    if (typed !== null) {
                                        onInstances(exercise, typed);
                                    }
                                }}
                            />
                        </span>
                    </label>
                    <label className="exercise-setting">
                        <span>Time limit</span>
                        <span className="exercise-setting-number">
                            <input
                                type="number"
                                min={0}
                                max={MAX_MINUTES}
                                title="Minutes, 0 for no limit"
                                value={minutes}
                                onChange={(event) => {
                                    const typed = typedNumber(event.target.valueAsNumber, 0, MAX_MINUTES);
                                    if (typed !== null) {
                                        onMinutes(exercise, typed);
                                    }
                                }}
                            />
                            <span className="practice-detail">min</span>
                        </span>
                    </label>
                </>
            )}
            {Object.entries(exercise.options ?? {}).map(([name, option]) => (
                <label key={name} className="exercise-setting">
                    <span>{option.label}</span>
                    {"choices" in option && Object.keys(option.choices).length === 0
                        ? (
                            <span className="practice-detail">
                                {"texts" in option
                                    ? "None left to correct: write one in the Texts tab"
                                    : "None to choose"}
                            </span>
                        )
                        : "choices" in option
                        ? (
                            <select
                                value={values[name]}
                                onChange={(event) => onChange(exercise, name, event.target.value)}
                            >
                                {Object.entries(option.choices).map(([value, label]) => (
                                    <option key={value} value={value}>{label}</option>
                                ))}
                            </select>
                        )
                        : (
                            <span className="exercise-setting-number">
                                <input
                                    type="number"
                                    min={option.min}
                                    max={option.max}
                                    title={`${option.min} to ${option.max}`}
                                    value={values[name]}
                                    onChange={(event) => {
                                        const typed = typedNumber(
                                            event.target.valueAsNumber,
                                            option.min,
                                            option.max,
                                        );
                                        if (typed !== null) {
                                            onChange(exercise, name, typed);
                                        }
                                    }}
                                />
                            </span>
                        )}
                </label>
            ))}
        </div>
    );
}
