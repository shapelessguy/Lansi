// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { element } from "../../kit.js";

/** A mistake as it is marked in the text: what was wrong struck through, what is right beside it, and why. */
function marked(part) {
    return element(
        "span",
        { className: "mistake" },
        part.wrong ? element("del", { textContent: part.wrong }) : null,
        part.right ? element("ins", { textContent: part.right }) : null,
        part.why ? element("span", { className: "why", textContent: part.why }) : null,
    );
}

/**
 * The text with its corrections, which the backend made as the exercise
 * started. There is nothing to answer: the exercise is finished at once, so
 * that the correction is kept and the log written.
 */
export function mount(root, exercise) {
    let finished = false;
    exercise.onShow((show) => {
        root.replaceChildren(
            element("h3", { textContent: show.title || "Untitled" }),
            element(
                "div",
                { className: "card corrected" },
                ...show.parts.map((part) => ("text" in part ? document.createTextNode(part.text) : marked(part))),
            ),
            show.parts.some((part) => "wrong" in part) ? null : element("p", { textContent: "No mistakes." }),
        );
        if (!finished) {
            finished = true;
            exercise.finish();
        }
    });
}
