// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { doubt, type Sentence } from "../lib/checker";
import type { ModelChoice } from "../lib/models";
import { answerFraction, askedQuestions, describeAnswer, isAskable, type ProfileQuestion } from "../lib/questions";
import { SidePanel } from "./SidePanel";

interface Props {
    questions: ProfileQuestion[];
    /** Turns the question with that id on or off. */
    onToggle: (id: string) => void;
    /** Whether the words of each sentence are rated as well, and what to do when that is changed. */
    rateWords: boolean;
    onRateWords: (rateWords: boolean) => void;
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
                    ? "Checking…"
                    : sentence.complete
                    ? "Not checked."
                    : "It is checked once the cursor leaves the sentence."}
            </p>
        );
    }
    return (
        <dl className="answers">
            {questions.map((question) => {
                const answer = profile.answers[question.id];
                const fraction = answer ? answerFraction(question, answer) : null;
                return (
                    <div key={question.id} className="answer">
                        <dt>{question.title}</dt>
                        <dd>
                            <span className="answer-value">
                                {answer ? describeAnswer(question, answer) : "No answer"}
                            </span>
                            {answer && answer.confidence !== null && (
                                <span className="answer-confidence" title="How sure the model is">
                                    {Math.round(answer.confidence * 100)}%
                                </span>
                            )}
                        </dd>
                        {fraction !== null && (
                            <div className="answer-scale" aria-hidden="true">
                                <span style={{ width: `${fraction * 100}%` }} />
                            </div>
                        )}
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
        return sentence.rating_words ? <p className="checks-note">Rating the words…</p> : null;
    }
    return (
        <ul className="word-ratings" aria-label="How right each word is">
            {words.map((word, index) => (
                <li
                    key={index}
                    style={{ backgroundColor: `rgb(var(--doubt) / ${(doubt(word.value) * 0.6).toFixed(2)})` }}
                >
                    {word.word}
                    <small>{word.value.toFixed(2)}</small>
                </li>
            ))}
        </ul>
    );
}

export function ChecksPanel(
    {
        questions,
        onToggle,
        rateWords,
        onRateWords,
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
        <SidePanel title="Sentence checks" onClose={onClose}>
            <div className="usage checks">
                <section>
                    <h3>Questions</h3>
                    {questions.length === 0 && <p className="checks-note">There are no questions.</p>}
                    {questions.map((question) => (
                        <label key={question.id} className="toggle">
                            <span>
                                {question.title || "Untitled"}
                                {!isAskable(question) && <small>Incomplete, so it is not asked</small>}
                            </span>
                            <input
                                type="checkbox"
                                role="switch"
                                checked={question.enabled}
                                onChange={() => onToggle(question.id)}
                            />
                        </label>
                    ))}
                    <button className="link" onClick={onEditQuestions}>Edit questions</button>
                </section>
                <section>
                    <h3>Then</h3>
                    <label className="toggle">
                        <span>
                            Rate each word
                            <small>Asks, by the answers above, how right each word is</small>
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
                    <h3>Sentence under the cursor</h3>
                    {!sentence
                        ? (
                            <p className="checks-note">
                                {checkerRunning || !hasText
                                    ? "Write in the chat to see what the questions say about each sentence."
                                    : "Nothing yet. The checker server may not be running."}
                            </p>
                        )
                        : (
                            <>
                                <blockquote className="checks-sentence">{sentence.text}</blockquote>
                                {!hasKey && !model.url
                                    ? <p className="checks-note">Add your OpenRouter API key in the settings.</p>
                                    : asked.length === 0
                                    ? <p className="checks-note">No question is turned on.</p>
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
                    <h3>Answered by</h3>
                    <p className="checks-model">
                        <span className={model.url ? "badge local" : "badge"} title={model.url || undefined}>
                            {model.url ? "Own server" : "OpenRouter"}
                        </span>
                        {model.model}
                    </p>
                </section>
                <p className="usage-note">
                    {model.url
                        ? `Turning a question on asks it about the finished sentences in the box, at ${model.url}.`
                        : "Turning a question on asks it about the finished sentences in the box, which is billed."}
                </p>
            </div>
        </SidePanel>
    );
}
