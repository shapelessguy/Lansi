// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { element } from "../../kit.js";

const LABELS = { right: "Right", partial: "Almost", wrong: "Not quite" };
const MARKS = { right: "✓", partial: "~", wrong: "✗" };

/** How one translation of a set went. */
function feedbackOf(feedback) {
    const box = element("li", { className: `feedback ${feedback.result}` });
    box.append(element("div", { className: "muted", textContent: feedback.source }));
    box.append(element("strong", { textContent: `${MARKS[feedback.result]} ${feedback.answer || "(nothing written)"}` }));
    if (feedback.correction && feedback.correction !== feedback.reference) {
        box.append(element("div", { textContent: `Corrected: ${feedback.correction}` }));
    }
    if (feedback.note) {
        box.append(element("div", { className: "muted", textContent: feedback.note }));
    }
    box.append(element("div", { className: "muted", textContent: `Another way: ${feedback.reference}` }));
    return box;
}

export function mount(root, exercise) {
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
        return element("div", { className: "progress", textContent: `Set ${Math.min(at + 1, total)} of ${total}` });
    }

    function answering(show) {
        const answers = show.sources.map(() =>
            element("textarea", { placeholder: "Your translation", spellcheck: false, rows: 2 })
        );
        const check = element("button", { className: "primary", textContent: "Check" });
        const submit = () => {
            if (answers.some((answer) => answer.value.trim())) {
                send({ answers: answers.map((answer) => answer.value) }, check, "Checking…", answers);
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
            element("div", { className: "actions" }, check, element("span", { className: "muted", textContent: "Enter goes to the next sentence" })),
            error,
        );
        answers[0]?.focus();
    }

    function reviewing(show) {
        const right = show.feedback.filter((each) => each.result === "right").length;
        const summary = element("p", {}, element("strong", { textContent: LABELS[show.result] }), ` · ${right} of ${show.feedback.length} right`);
        const go = element("button", { className: "primary", textContent: show.more ? "Next" : "Done" });
        if (show.more) {
            go.onclick = () => send({ next: true }, go, "Making the next sentences…");
        } else {
            go.onclick = () => exercise.finish();
        }
        root.replaceChildren(
            progress(show.at - 1, show.total),
            summary,
            element("ol", { className: "sentences" }, ...show.feedback.map(feedbackOf)),
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
