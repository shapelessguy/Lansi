// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { type ExerciseInfo, MAX_INSTANCES, type OptionValue } from "../lib/practice";

/** An exercise that was chosen, with how many times it is done and what its options are set to. */
export interface ChosenExercise {
    exercise: ExerciseInfo;
    instances: number;
    values: Record<string, OptionValue>;
}

interface Props {
    chosen: ChosenExercise[];
    onInstances: (exercise: ExerciseInfo, instances: number) => void;
    onChange: (exercise: ExerciseInfo, name: string, value: OptionValue) => void;
}

/** A whole number typed in a box, within its bounds, or nothing while it is not one. */
function typedNumber(typed: number, least: number, most: number): number | null {
    return Number.isFinite(typed) ? Math.min(most, Math.max(least, Math.round(typed))) : null;
}

/**
 * The settings of the exercises chosen: how many times each is done, and
 * the options its manifest has. They are remembered for the next time.
 */
export function ExerciseSettings({ chosen, onInstances, onChange }: Props) {
    return (
        <section className="history exercise-settings">
            <h2>
                Settings <span className="practice-hint">of the exercises chosen, remembered</span>
            </h2>
            <div className="exercise-settings-list">
                {chosen.map(({ exercise, instances, values }) => (
                    <fieldset key={exercise.id} className="exercise-settings-group">
                        <legend>{exercise.title}</legend>
                        <label className="exercise-setting">
                            <span>Times</span>
                            <span className="exercise-setting-number">
                                <input
                                    type="number"
                                    min={1}
                                    max={MAX_INSTANCES}
                                    value={instances}
                                    onChange={(event) => {
                                        const typed = typedNumber(event.target.valueAsNumber, 1, MAX_INSTANCES);
                                        if (typed !== null) {
                                            onInstances(exercise, typed);
                                        }
                                    }}
                                />
                                <span className="practice-detail">1 to {MAX_INSTANCES}</span>
                            </span>
                        </label>
                        {Object.entries(exercise.options ?? {}).map(([name, option]) => (
                            <label key={name} className="exercise-setting">
                                <span>{option.label}</span>
                                {"choices" in option
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
                                            <span className="practice-detail">{option.min} to {option.max}</span>
                                        </span>
                                    )}
                            </label>
                        ))}
                    </fieldset>
                ))}
            </div>
        </section>
    );
}
