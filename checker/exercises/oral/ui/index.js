// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { element, ratingsOf } from "../../kit.js";

const LABELS = { right: "Good", partial: "Partly there", wrong: "Not yet" };

/** The card of a task, if it has one. */
function cardOf(task) {
    return task.card ? element("div", { className: "card speak-card", textContent: task.card }) : null;
}

export function mount(root, exercise) {
    const error = element("p", { className: "error" });

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
        return element("div", { className: "progress", textContent: `Task ${Math.min(at + 1, total)} of ${total}` });
    }

    function speaking(show) {
        const whole = show.task.prompts.length === 1;
        const fields = show.task.prompts.map(() =>
            element("textarea", { placeholder: "What you say", spellcheck: false, rows: whole ? 6 : 2 })
        );
        // in an exam, nothing is rated before the end: it goes on to the next
        const last = show.at + 1 >= show.total;
        const done = element("button", {
            className: "primary",
            textContent: show.exam ? (last ? "Done" : "Next") : "Hand in",
        });
        done.onclick = () => {
            if (fields.some((field) => field.value.trim())) {
                send({ answers: fields.map((field) => field.value) }, done, show.exam ? "Next…" : "Rating…", fields);
            }
        };
        // what is left out, such as a card a task has not, is null
        root.replaceChildren(
            ...[
                progress(show.at, show.total),
                element("p", { className: "muted", textContent: "Type what you would say, as you would say it." }),
                cardOf(show.task),
                element(
                    "ol",
                    { className: "sentences" },
                    ...show.task.prompts.map((prompt, number) =>
                        element("li", { className: "card" }, element("div", { textContent: prompt }), fields[number])
                    ),
                ),
                element("div", { className: "actions" }, done),
                error,
            ].filter((part) => part !== null),
        );
    }

    function reviewing(show) {
        const go = element("button", { className: "primary", textContent: show.more ? "Next task" : "Done" });
        go.onclick = show.more ? () => send({ next: true }, go, "Making the next task…") : () => exercise.finish();
        const feedback = show.feedback;
        // what is left out, such as a card a task has not, is null
        root.replaceChildren(
            ...[
                progress(show.at - 1, show.total),
                element(
                    "div",
                    { className: `feedback ${feedback.result}` },
                    element("strong", { textContent: LABELS[feedback.result] }),
                    ratingsOf(feedback.ratings),
                    feedback.note ? element("p", { textContent: feedback.note }) : null,
                ),
                cardOf(show.task),
                element(
                    "ol",
                    { className: "sentences" },
                    ...feedback.turns.map((turn) =>
                        element(
                            "li",
                            { className: "card" },
                            element("div", { className: "muted", textContent: turn.prompt }),
                            element("strong", { textContent: turn.answer || "(nothing said)" }),
                            turn.correction ? element("div", { textContent: `Better: ${turn.correction}` }) : null,
                        )
                    ),
                ),
                element("div", { className: "actions" }, go),
                error,
            ].filter((part) => part !== null),
        );
        go.focus();
        if (show.more && !show.prepared) {
            exercise.act({ prepare: true }).catch(() => undefined);
        }
    }

    /**
     * In an exam, what was answered last, which tells nothing of how it went:
     * the part is handed in at once, or, if more is to come, it goes on to it.
     */
    function withheld(show) {
        root.replaceChildren(element("p", { className: "muted", textContent: "Handing in…" }), error);
        const going = show.more ? exercise.act({ next: true }) : Promise.resolve(exercise.finish());
        going.catch((failed) => {
            error.textContent = failed.message;
        });
    }

    exercise.onShow((show) => (show.withheld ? withheld(show) : show.feedback ? reviewing(show) : speaking(show)));
}
