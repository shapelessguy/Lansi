// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { element, ratingsOf } from "../../kit.js";

const LABELS = { right: "Good", partial: "Partly there", wrong: "Not yet" };

/** How many words a text has. */
function wordsIn(text) {
    return text.split(/\s+/).filter(Boolean).length;
}

/** The task, as the learner reads it. */
function taskOf(task) {
    if (task.kind === "form") {
        return element(
            "article",
            { className: "card task" },
            ...task.text.split(/\n+/).map((line) => element("p", { textContent: line })),
        );
    }
    return element(
        "article",
        { className: "card task" },
        element("p", { textContent: task.situation }),
        element("ul", {}, ...task.points.map((point) => element("li", { textContent: point }))),
    );
}

export function mount(root, exercise) {
    const t = exercise.t;
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
        return element("div", { className: "progress", textContent: t("Task {at} of {total}", { at: Math.min(at + 1, total), total }),
        });
    }

    function writing(show) {
        // in an exam, nothing is rated before the end: it goes on to the next
        const last = show.at + 1 >= show.total;
        const done = element("button", {
            className: "primary",
            textContent: show.exam ? (last ? t("Done") : t("Next")) : t("Hand in"),
        });
        let fields;
        let message;
        let parts;
        if (show.task.kind === "form") {
            fields = show.task.fields.map(() => element("input", { type: "text", spellcheck: false }));
            message = () => ({ fields: fields.map((field) => field.value) });
            parts = [
                element(
                    "div",
                    { className: "card form" },
                    ...show.task.fields.map((label, number) =>
                        element("label", { className: "field" }, element("span", { textContent: label }), fields[number])
                    ),
                ),
            ];
        } else {
            const text = element("textarea", { placeholder: t("Write here"), spellcheck: false, rows: 8 });
            const counted = () => t("{count} of about {words} words", { count: wordsIn(text.value), words: show.words });
            const count = element("span", { className: "muted", textContent: counted() });
            text.oninput = () => (count.textContent = counted());
            fields = [text];
            message = () => ({ text: text.value });
            parts = [text, count];
        }
        done.onclick = () => {
            if (fields.some((field) => field.value.trim())) {
                send(message(), done, show.exam ? t("Next…") : t("Rating…"), fields);
            }
        };
        root.replaceChildren(
            progress(show.at, show.total),
            taskOf(show.task),
            ...parts,
            element("div", { className: "actions" }, done),
            error,
        );
    }

    function reviewing(show) {
        const go = element("button", { className: "primary", textContent: show.more ? t("Next task") : t("Done") });
        go.onclick = show.more ? () => send({ next: true }, go, t("Making the next task…")) : () => exercise.finish();
        const feedback = show.feedback;
        const parts = [];
        if (feedback.kind === "form") {
            parts.push(
                element(
                    "ol",
                    { className: "sentences" },
                    ...feedback.fields.map((field) =>
                        element(
                            "li",
                            { className: `feedback ${field.result}` },
                            element("div", { className: "muted", textContent: field.label }),
                            element("strong", { textContent: field.answer || t("(nothing written)") }),
                            field.result === "right"
                                ? null
                                : element("div", { textContent: t("In the text: {reference}", { reference: field.reference }) }),
                            field.note ? element("div", { className: "muted", textContent: field.note }) : null,
                        )
                    ),
                ),
            );
        } else {
            parts.push(
                element(
                    "div",
                    { className: `feedback ${feedback.result}` },
                    element("strong", { textContent: t(LABELS[feedback.result]) }),
                    ratingsOf(feedback.ratings, t),
                    feedback.note ? element("p", { textContent: feedback.note }) : null,
                ),
                element("h3", { textContent: t("What you wrote") }),
                element("p", { className: "written", textContent: feedback.answer }),
                feedback.correction ? element("h3", { textContent: t("Corrected") }) : null,
                feedback.correction ? element("p", { className: "written", textContent: feedback.correction }) : null,
            );
        }
        root.replaceChildren(
            progress(show.at - 1, show.total),
            taskOf(show.task),
            ...parts.filter((part) => part !== null),
            element("div", { className: "actions" }, go),
            error,
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
        root.replaceChildren(element("p", { className: "muted", textContent: t("Handing in…") }), error);
        const going = show.more ? exercise.act({ next: true }) : Promise.resolve(exercise.finish());
        going.catch((failed) => {
            error.textContent = failed.message;
        });
    }

    exercise.onShow((show) => (show.withheld ? withheld(show) : show.feedback ? reviewing(show) : writing(show)));
}
