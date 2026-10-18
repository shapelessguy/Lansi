// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { element } from "../../kit.js";

const LETTERS = "abcdefghijklmnopqrstuvwxyz";

/** The paragraphs of a text, with its title and what goes with it. */
function textOf(text, heading = true) {
    return [
        heading && text.title ? element("h2", { textContent: text.title }) : null,
        ...text.text.split(/\n\s*\n|\n/).map((line) => element("p", { textContent: line.trim() })),
    ];
}

/** What is shown beside a text, such as a list to choose from. */
function besideOf(text) {
    return text.shown ? element("div", { className: "card beside", textContent: text.shown }) : null;
}

/** The label of the option at `place`: its letter, unless the options are words of their own. */
function labelOf(options, place) {
    return options.length > 2 && options.every((each) => each.length > 1)
        ? `${LETTERS[place]}) ${options[place]}`
        : options[place];
}

/** The button that has a text read aloud, as often as it may be. */
function listenerOf(show, exercise) {
    let left = show.plays;
    const button = element("button", { className: "listen primary" });
    function label() {
        button.textContent = show.plays === 0 ? "▶ Listen" : left > 0 ? `▶ Listen (${left} left)` : "Heard";
        button.disabled = show.plays !== 0 && left <= 0;
    }
    button.onclick = () => {
        exercise.readAloud(show.text.text, show.number);
        left -= 1;
        label();
    };
    label();
    return button;
}

/** How one answer went. */
function feedbackOf(each) {
    const box = element("li", { className: `feedback ${each.result}` });
    box.append(element("div", { textContent: each.prompt }));
    const chosen = each.chosen === null ? "(nothing chosen)" : labelOf(each.options, each.chosen);
    box.append(element("strong", { textContent: `${each.result === "right" ? "✓" : "✗"} ${chosen}` }));
    if (each.result !== "right") {
        box.append(element("div", { className: "muted", textContent: `Right: ${labelOf(each.options, each.answer)}` }));
    }
    return box;
}

export function mount(root, exercise) {
    const error = element("p", { className: "error" });

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
        return element("div", { className: "progress", textContent: `Text ${Math.min(at + 1, total)} of ${total}` });
    }

    function answering(show) {
        const heard = show.by === "listening";
        // the place of the option chosen for each question, or null
        const chosen = show.questions.map(() => null);
        const questions = show.questions.map((question, number) => {
            const name = `q${number}`;
            const options = question.options.map((option, place) => {
                const input = element("input", { type: "radio", name, value: String(place) });
                input.onchange = () => (chosen[number] = place);
                return element(
                    "label",
                    { className: "option" },
                    input,
                    element("span", { textContent: labelOf(question.options, place) }),
                );
            });
            const inline = question.options.every((each) => each.length <= 8);
            return element(
                "li",
                { className: "card" },
                element("div", { textContent: question.prompt }),
                element("div", { className: inline ? "options inline" : "options" }, ...options),
            );
        });
        const check = element("button", { className: "primary", textContent: "Check" });
        check.onclick = () => send({ answers: chosen }, check, "Checking…");
        // what is left out, such as what goes beside a text that has nothing beside it, is null
        root.replaceChildren(
            ...[
                progress(show.at, show.total),
                heard
                    ? element(
                        "div",
                        { className: "card heard" },
                        element("p", { className: "muted", textContent: "Listen to the text, then answer." }),
                        listenerOf(show, exercise),
                    )
                    : element("article", { className: "card text" }, ...textOf(show.text)),
                besideOf(show.text),
                element("ol", { className: "sentences" }, ...questions),
                element("div", { className: "actions" }, check),
                error,
            ].filter((part) => part !== null),
        );
    }

    function reviewing(show) {
        const go = element("button", { className: "primary", textContent: show.more ? "Next text" : "Done" });
        go.onclick = show.more ? () => send({ next: true }, go, "Writing the next text…") : () => exercise.finish();
        const right = show.feedback.filter((each) => each.result === "right").length;
        // what is left out, such as what goes beside a text that has nothing beside it, is null
        root.replaceChildren(
            ...[
                progress(show.at - 1, show.total),
                element("p", {}, element("strong", { textContent: `${right} of ${show.feedback.length} right` })),
                element("ol", { className: "sentences" }, ...show.feedback.map(feedbackOf)),
                element("div", { className: "actions" }, go),
                element(
                    "details",
                    {},
                    element("summary", { textContent: show.by === "listening" ? "What was said" : "The text" }),
                    element("article", { className: "card text" }, ...textOf(show.text)),
                    besideOf(show.text),
                ),
                error,
            ].filter((part) => part !== null),
        );
        go.focus();
        if (show.more && !show.prepared) {
            // written while the learner reads this, so that the next is there at once
            exercise.act({ prepare: true }).catch(() => undefined);
        }
    }

    exercise.onShow((show) => (show.feedback ? reviewing(show) : answering(show)));
}
