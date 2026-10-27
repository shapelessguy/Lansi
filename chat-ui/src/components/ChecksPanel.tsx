// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { createPortal } from "react-dom";

import { type LiveCheck, type Sentence, sentenceAtCaret, wordTint } from "../lib/checker";
import { t } from "../lib/i18n";
import type { ModelChoice } from "../lib/models";
import {
    answerFraction,
    answerStars,
    askedQuestions,
    describeAnswer,
    isAskable,
    isUnsure,
    type ProfileQuestion,
    type Stars,
} from "../lib/questions";
import type { Settings } from "../lib/settings";
import { correctorOf } from "../lib/writing";
import { SidePanel } from "./SidePanel";

interface Props {
    questions: ProfileQuestion[];
    /** Turns the question with that id on or off. */
    onToggle: (id: string) => void;
    /** Whether the words of each sentence are rated as well, and what to do when that is changed. */
    rateWords: boolean;
    onRateWords: (rateWords: boolean) => void;
    /** Whether each sentence is written as it should be by `corrector`, and what to do when that is changed. */
    correct: boolean;
    onCorrect: (correct: boolean) => void;
    corrector: ModelChoice;
    /** The sentence the caret is on, if any. */
    sentence: Sentence | null;
    /** Whether anything is written in the chat box. */
    hasText: boolean;
    /** Whether the checker server has answered at all. */
    checkerRunning: boolean;
    hasKey: boolean;
    /** The model that answers the questions. */
    model: ModelChoice;
    onEditQuestions: () => void;
    onClose: () => void;
}

/** Stars, each filled as far as `filled` reaches into it. */
function StarRow({ stars, filled }: Stars) {
    return (
        <span className="answer-stars" role="img" aria-label={t("{filled} of {stars} stars", { filled, stars })}>
            {Array.from({ length: stars }, (_, at) => (
                <span key={at} className="star">
                    ★
                    <span style={{ width: `${Math.min(1, Math.max(0, filled - at)) * 100}%` }}>★</span>
                </span>
            ))}
        </span>
    );
}

/** What the questions came back with for a sentence, or why there is nothing to show yet. */
function Answers({ sentence, questions }: { sentence: Sentence; questions: ProfileQuestion[] }) {
    const profile = sentence.profile;
    if (!profile) {
        if (sentence.profile_error) {
            return <p className="checks-note error">{sentence.profile_error}</p>;
        }
        return (
            <p className="checks-note">
                {sentence.profiling
                    ? t("Checking…")
                    : sentence.complete
                    ? t("Not checked.")
                    : t("It is checked once the cursor leaves the sentence.")}
            </p>
        );
    }
    return (
        <dl className="answers">
            {questions.map((question) => {
                const answer = profile.answers[question.id];
                // a fault the model is not sure enough of is shown faint, without stars or a bar
                const unsure = answer !== undefined && isUnsure(question, answer);
                const stars = answer && !unsure ? answerStars(question, answer) : null;
                const fraction = answer && !stars && !unsure ? answerFraction(question, answer) : null;
                return (
                    <div
                        key={question.id}
                        className={unsure ? "answer unsure" : "answer"}
                        title={unsure ? t("The model is not sure enough of this to count it as a fault") : undefined}
                    >
                        <dt>{question.title}</dt>
                        <dd>
                            <span className="answer-value">
                                {answer ? describeAnswer(question, answer) : t("No answer")}
                            </span>
                            {answer && answer.confidence !== null && (
                                <span className="answer-confidence" title={t("How sure the model is")}>
                                    {Math.round(answer.confidence * 100)}%
                                </span>
                            )}
                            {unsure && <span className="answer-unsure">{t("unsure")}</span>}
                            {stars && <StarRow {...stars} />}
                            {fraction !== null && (
                                <span className="answer-scale" aria-hidden="true">
                                    <span style={{ width: `${fraction * 100}%` }} />
                                </span>
                            )}
                        </dd>
                    </div>
                );
            })}
        </dl>
    );
}

/** How right each word of a sentence was rated, or that the rating is on its way. */
function Words({ sentence }: { sentence: Sentence }) {
    const words = sentence.words ?? [];
    if (words.length === 0) {
        return sentence.rating_words ? <p className="checks-note">{t("Rating the words…")}</p> : null;
    }
    return (
        <ul className="word-ratings" aria-label={t("How right each word is")}>
            {words.map((word, index) => (
                <li
                    key={index}
                    style={{ backgroundColor: wordTint(word.value) }}
                >
                    {word.word}
                    <small>{word.value.toFixed(2)}</small>
                </li>
            ))}
        </ul>
    );
}

/** The sentence as the language model wrote it, or that it is on its way. */
function Correction({ sentence }: { sentence: Sentence }) {
    let shown;
    if (sentence.correction) {
        shown = sentence.correction === sentence.text
            ? <p className="checks-note">{t("Nothing to correct.")}</p>
            : <blockquote className="checks-sentence checks-correction">{sentence.correction}</blockquote>;
    } else if (sentence.correction_error) {
        shown = <p className="checks-note error">{sentence.correction_error}</p>;
    } else {
        shown = (
            <p className="checks-note">
                {sentence.correcting
                    ? t("Correcting…")
                    : sentence.complete
                    ? t("Not corrected.")
                    : t("It is corrected once the cursor leaves the sentence.")}
            </p>
        );
    }
    return (
        <dl className="answers">
            <div className="answer">
                <dt>{t("Correction")}</dt>
                <dd className="correction">{shown}</dd>
            </div>
        </dl>
    );
}

export function ChecksPanel(
    {
        questions,
        onToggle,
        rateWords,
        onRateWords,
        correct,
        onCorrect,
        corrector,
        sentence,
        hasText,
        checkerRunning,
        hasKey,
        model,
        onEditQuestions,
        onClose,
    }: Props,
) {
    const asked = askedQuestions(questions);
    return (
        <SidePanel title={t("Sentence checks")} onClose={onClose}>
            <div className="usage checks">
                <section>
                    <h3>{t("Spelling")}</h3>
                    <label className="toggle">
                        <span>
                            {t("Correct each sentence")}
                            <small>
                                {t("Has the translation model write it as it should be, alongside the questions")}
                            </small>
                        </span>
                        <input
                            type="checkbox"
                            role="switch"
                            checked={correct}
                            onChange={(event) => onCorrect(event.target.checked)}
                        />
                    </label>
                    {questions.length === 0 && <p className="checks-note">{t("There are no questions.")}</p>}
                    {questions.map((question) => (
                        <label key={question.id} className="toggle">
                            <span>
                                {question.title || t("Untitled")}
                                {!isAskable(question) && <small>{t("Incomplete, so it is not asked")}</small>}
                            </span>
                            <input
                                type="checkbox"
                                role="switch"
                                checked={question.enabled}
                                onChange={() => onToggle(question.id)}
                            />
                        </label>
                    ))}
                    <button className="link" onClick={onEditQuestions}>{t("Edit questions")}</button>
                </section>
                <section>
                    <h3>{t("Then")}</h3>
                    <label className="toggle">
                        <span>
                            {t("Rate each word")}
                            <small>
                                {correct
                                    ? t("Asks, by the answers above and the correction, how right each word is")
                                    : t("Asks, by the answers above, how right each word is")}
                            </small>
                        </span>
                        <input
                            type="checkbox"
                            role="switch"
                            checked={rateWords}
                            onChange={(event) => onRateWords(event.target.checked)}
                        />
                    </label>
                </section>
                <section>
                    <h3>{t("Sentence under the cursor")}</h3>
                    {!sentence
                        ? (
                            <p className="checks-note">
                                {checkerRunning || !hasText
                                    ? t("Write in the chat to see what the questions say about each sentence.")
                                    : t("Nothing yet. The checker server may not be running.")}
                            </p>
                        )
                        : (
                            <>
                                <blockquote className="checks-sentence">{sentence.text}</blockquote>
                                {correct && (hasKey || corrector.url) && <Correction sentence={sentence} />}
                                {!hasKey && !model.url
                                    ? <p className="checks-note">{t("Add your OpenRouter API key in the settings.")}</p>
                                    : asked.length === 0
                                    ? <p className="checks-note">{t("No question is turned on.")}</p>
                                    : (
                                        <>
                                            <Answers sentence={sentence} questions={asked} />
                                            {rateWords && <Words sentence={sentence} />}
                                        </>
                                    )}
                            </>
                        )}
                </section>
                <section>
                    <h3>{t("Answered by")}</h3>
                    <p className="checks-model">
                        <span className={model.url ? "badge local" : "badge"} title={model.url || undefined}>
                            {model.url ? t("Own server") : "OpenRouter"}
                        </span>
                        {model.model}
                    </p>
                    {correct && (
                        <p className="checks-model">
                            <span
                                className={corrector.url ? "badge local" : "badge"}
                                title={corrector.url || undefined}
                            >
                                {corrector.url ? t("Own server") : "OpenRouter"}
                            </span>
                            {corrector.model || t("the usual model")}
                            <small>{t("corrects")}</small>
                        </p>
                    )}
                </section>
                <p className="usage-note">
                    {model.url
                        ? t("Turning a question on asks it about the finished sentences in the box, at {url}.", {
                            url: model.url,
                        })
                        : t("Turning a question on asks it about the finished sentences in the box, which is billed.")}
                </p>
            </div>
        </SidePanel>
    );
}

interface SettingsProps {
    /** What the sentences are checked by, which the panel changes. */
    settings: Settings;
    onSettingsChange: (settings: Settings) => void;
    /** What is known about the text box the checks are of, and what is written in it. */
    check: LiveCheck | null;
    lastCaret: number | null;
    text: string;
    onEditQuestions: () => void;
    onClose: () => void;
}

/**
 * The checks of the sentence under the caret of a text box, with the
 * questions, the rating of words and the corrections turned on and off in
 * the settings, wherever the box is: the chat, the tutor, a text or an
 * exercise.
 */
export function SettingsChecksPanel(
    { settings, onSettingsChange, check, lastCaret, text, onEditQuestions, onClose }: SettingsProps,
) {
    return (
        <ChecksPanel
            questions={settings.questions}
            onToggle={(question) =>
                onSettingsChange({
                    ...settings,
                    questions: settings.questions.map((each) =>
                        each.id === question ? { ...each, enabled: !each.enabled } : each
                    ),
                })}
            rateWords={settings.rateWords}
            onRateWords={(rateWords) => onSettingsChange({ ...settings, rateWords })}
            corrector={correctorOf(settings)}
            correct={settings.correctSentences}
            onCorrect={(correctSentences) => onSettingsChange({ ...settings, correctSentences })}
            // the panel goes on showing the sentence the caret was on after a click in it
            sentence={text ? sentenceAtCaret(check, lastCaret) : null}
            hasText={text.trim() !== ""}
            checkerRunning={check !== null}
            hasKey={settings.apiKey !== ""}
            model={settings.profileModel}
            onEditQuestions={onEditQuestions}
            onClose={onClose}
        />
    );
}

/**
 * What the panel of the checks says in `slot`, while it is open, where no
 * text box is being written in yet, such as before an exercise starts.
 */
export function NoChecks({ slot, onClose }: { slot: HTMLElement | null; onClose: () => void }) {
    return slot && createPortal(
        <SidePanel title={t("Sentence checks")} onClose={onClose}>
            <p className="checks-note">
                {t("The checks of the sentence you write are shown here once an exercise starts.")}
            </p>
        </SidePanel>,
        slot,
    );
}
