// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { element } from "../../kit.js";

/** The words a correction is about, as they were written. */
function wordsOf(words, correction) {
    if ("id" in correction) {
        return words[correction.id];
    }
    if ("from_id" in correction) {
        return words.slice(correction.from_id, correction.to_id + 1).join(" ");
    }
    return "";
}

/** A correction as a line: what was written, what it is to be, and why. */
function line(words, correction) {
    const was = wordsOf(words, correction);
    return element(
        "li",
        { className: `correction ${correction.type}` },
        was ? element("del", { textContent: was }) : null,
        correction.text ? element("ins", { textContent: correction.text }) : null,
        correction.explanation ? element("span", { className: "why", textContent: correction.explanation }) : null,
    );
}

/**
 * The corrections of the text, which the backend made as the exercise
 * started. The app runs this exercise itself and shows the corrections in
 * the text; here they are listed. There is nothing to answer: the exercise is
 * finished at once, so that the correction is kept and the log written.
 */
export function mount(root, exercise) {
    const t = exercise.t;
    let finished = false;
    exercise.onShow((show) => {
        const listed = show.corrections.filter((each) => each.type !== "misread");
        root.replaceChildren(
            element("h3", { textContent: show.title || t("Untitled") }),
            show.summary ? element("p", { textContent: show.summary }) : null,
            listed.length
                ? element("ul", { className: "card corrected" }, ...listed.map((each) => line(show.words, each)))
                : element("p", { textContent: t("No mistakes.") }),
        );
        if (!finished) {
            finished = true;
            exercise.finish();
        }
    });
}
