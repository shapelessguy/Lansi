// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { element } from "../../kit.js";

const LABELS = { right: "Right", partial: "Almost", wrong: "Not quite" };
const MARKS = { right: "✓", partial: "~", wrong: "✗" };

/** How one translation of a set went, told with `t`. */
function feedbackOf(feedback, t) {
    const box = element("li", { className: `feedback ${feedback.result}` });
    box.append(element("div", { className: "muted", textContent: feedback.source }));
    box.append(element("strong", { textContent: `${MARKS[feedback.result]} ${feedback.answer || t("(nothing written)")}` }));
    if (feedback.correction && feedback.correction !== feedback.reference) {
        box.append(element("div", { textContent: t("Corrected: {text}", { text: feedback.correction }) }));
    }
    if (feedback.note) {
        box.append(element("div", { className: "muted", textContent: feedback.note }));
    }
    box.append(element("div", { className: "muted", textContent: t("Another way: {text}", { text: feedback.reference }) }));
    return box;
}

export function mount(root, exercise) {
    const t = exercise.t;
    const error = element("p", { className: "error" });

    /** Has the backend do `message`, saying on `button` that it is busy, or why it could not. */
    function send(message, button, busyText, fields = []) {
        const idle = button.textContent;
        button.disabled = true;
        fields.forEach((field) => (field.disabled = true));
        button.textContent = busyText;
        error.textContent = "";
        exercise.act(message).catch((failed) => {
            error.textContent = failed.message;
            button.disabled = false;
            fields.forEach((field) => (field.disabled = false));
            button.textContent = idle;
        });
    }

    function progress(at, total) {
        return element("div", { className: "progress", textContent: t("Set {at} of {total}", { at: Math.min(at + 1, total), total }),
        });
    }

    function answering(show) {
        // as tall as the translation of its source may be, a sentence or a whole text
        const answers = show.sources.map((source) =>
            element("textarea", {
                placeholder: t("Your translation"),
                spellcheck: false,
                rows: Math.min(12, Math.max(2, Math.ceil(String(source).length / 60))),
            })
        );
        const check = element("button", { className: "primary", textContent: t("Check") });
        const submit = () => {
            if (answers.some((answer) => answer.value.trim())) {
                send({ answers: answers.map((answer) => answer.value) }, check, t("Checking…"), answers);
            }
        };
        check.onclick = submit;
        answers.forEach((answer, number) =>
            answer.addEventListener("keydown", (event) => {
                if (event.key !== "Enter" || event.shiftKey) {
                    return;
                }
                event.preventDefault();
                if (number + 1 < answers.length) {
                    answers[number + 1].focus();
                } else if (!check.disabled) {
                    submit();
                }
            })
        );
        const sentences = element(
            "ol",
            { className: "sentences" },
            ...show.sources.map((source, number) =>
                element("li", { className: "card" }, element("div", { className: "source", textContent: source }), answers[number])
            ),
        );
        root.replaceChildren(
            progress(show.at, show.total),
            sentences,
            element("div", { className: "actions" }, check, element("span", { className: "muted", textContent: t("Enter goes to the next sentence") })),
            error,
        );
        answers[0]?.focus();
    }

    function reviewing(show) {
        const right = show.feedback.filter((each) => each.result === "right").length;
        const summary = element(
            "p",
            {},
            element("strong", { textContent: t(LABELS[show.result]) }),
            ` · ${t("{right} of {count} right", { right, count: show.feedback.length })}`,
        );
        const go = element("button", { className: "primary", textContent: show.more ? t("Next") : t("Done") });
        if (show.more) {
            go.onclick = () => send({ next: true }, go, t("Making the next sentences…"));
        } else {
            go.onclick = () => exercise.finish();
        }
        root.replaceChildren(
            progress(show.at - 1, show.total),
            summary,
            element("ol", { className: "sentences" }, ...show.feedback.map((each) => feedbackOf(each, t))),
            element("div", { className: "actions" }, go),
            error,
        );
        go.focus();
        if (show.more && !show.prepared) {
            // made while the learner reads this, so that the next is there at once
            exercise.act({ prepare: true }).catch(() => undefined);
        }
    }

    exercise.onShow((show) => (show.feedback ? reviewing(show) : answering(show)));
}
