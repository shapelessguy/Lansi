// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { element } from "../../kit.js";

const LABELS = { right: "Right", partial: "Almost", wrong: "Not quite" };
const MARKS = { right: "✓", partial: "~", wrong: "✗" };

/** How one sentence of a set went. */
function feedbackOf(feedback) {
    const box = element("li", { className: `feedback ${feedback.result}` });
    box.append(element("strong", { textContent: `${MARKS[feedback.result]} ${feedback.answer}` }));
    if (feedback.result !== "right") {
        box.append(element("div", { textContent: `Correct: ${feedback.correct}` }));
    }
    if (feedback.note) {
        box.append(element("div", { className: "muted", textContent: feedback.note }));
    }
    return box;
}

export function mount(root, exercise) {
    const error = element("p", { className: "error" });

    /** Has the backend do `message`, saying on `button` that it is busy, or why it could not. */
    function send(message, button, busyText) {
        const idle = button.textContent;
        button.disabled = true;
        button.textContent = busyText;
        error.textContent = "";
        exercise.act(message).catch((failed) => {
            error.textContent = failed.message;
            button.disabled = false;
            button.textContent = idle;
        });
    }

    function progress(at, total) {
        return element("div", { className: "progress", textContent: `Set ${Math.min(at + 1, total)} of ${total}` });
    }

    function answering(show) {
        // the inputs of each sentence, in turn
        const inputs = [];
        const all = [];
        const sentences = element("ol", { className: "sentences" });
        for (const item of show.items) {
            const own = [];
            const sentence = element("div", { className: "sentence" });
            for (const part of item.parts) {
                if (part === null) {
                    // the hint of the gap is shown in it until something is typed
                    const hint = item.hints?.[own.length] ?? "";
                    const input = element("input", { autocomplete: "off", spellcheck: false, placeholder: hint });
                    input.style.width = `${Math.max(9, hint.length + 3)}ch`;
                    own.push(input);
                    all.push(input);
                    sentence.append(input);
                } else {
                    sentence.append(part);
                }
            }
            inputs.push(own);
            sentences.append(element(
                "li",
                { className: "card" },
                sentence,
                item.hint ? element("div", { className: "hint muted", textContent: `(${item.hint})` }) : null,
                item.translation ? element("div", { className: "muted", textContent: item.translation }) : null,
            ));
        }
        const check = element("button", { className: "primary", textContent: "Check" });
        const submit = () => send({ answers: inputs.map((own) => own.map((input) => input.value)) }, check, "Checking…");
        check.onclick = submit;
        all.forEach((input, number) =>
            input.addEventListener("keydown", (event) => {
                if (event.key !== "Enter") {
                    return;
                }
                event.preventDefault();
                if (number + 1 < all.length) {
                    all[number + 1].focus();
                } else if (!check.disabled) {
                    submit();
                }
            })
        );
        root.replaceChildren(progress(show.at, show.total), sentences, element("div", { className: "actions" }, check), error);
        all[0]?.focus();
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
