// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { element } from "../../kit.js";

const LABELS = { right: "Right", partial: "Almost", wrong: "Not quite" };
const MARKS = { right: "✓", partial: "~", wrong: "✗" };
const DOING = {
    questions: "Checking…",
    retell: "Checking…",
    read: "…",
};

/** A story, with its title, its paragraphs and a button that has it read aloud. */
function storyOf(story, exercise, number) {
    const t = exercise.t;
    const listen = element("button", {
        className: "listen",
        textContent: `▶ ${t("Listen")}`,
        title: t("Have the story read aloud"),
    });
    listen.onclick = () => exercise.readAloud([story.title, story.text].filter(Boolean).join("\n\n"), number);
    return element(
        "article",
        { className: "card story" },
        element("div", { className: "story-head" }, element("h2", { textContent: story.title || t("Story") }), listen),
        ...story.text.split(/\n\s*\n/).map((paragraph) => element("p", { textContent: paragraph.trim() })),
    );
}

/** How one answer to a question went, told with `t`. */
function answerFeedbackOf(feedback, t) {
    const box = element("li", { className: `feedback ${feedback.result}` });
    box.append(element("div", { className: "muted", textContent: feedback.question }));
    box.append(element("strong", { textContent: `${MARKS[feedback.result]} ${feedback.answer || t("(nothing written)")}` }));
    if (feedback.correction && feedback.correction !== feedback.reference) {
        box.append(element("div", { textContent: t("Corrected: {text}", { text: feedback.correction }) }));
    }
    if (feedback.note) {
        box.append(element("div", { className: "muted", textContent: feedback.note }));
    }
    box.append(element("div", { className: "muted", textContent: t("In the story: {text}", { text: feedback.reference }) }));
    return box;
}

/** How the retelling went, told with `t`. */
function retellingFeedbackOf(feedback, t) {
    const box = element("li", { className: `feedback ${feedback.result}` });
    box.append(element("strong", { textContent: `${MARKS[feedback.result]} ${t(LABELS[feedback.result])}` }));
    box.append(element("p", { className: "muted", textContent: feedback.answer }));
    if (feedback.correction) {
        box.append(element("p", { textContent: t("Corrected: {text}", { text: feedback.correction }) }));
    }
    if (feedback.note) {
        box.append(element("div", { className: "muted", textContent: feedback.note }));
    }
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
        return element("div", { className: "progress", textContent: t("Story {at} of {total}", { at: Math.min(at + 1, total), total }),
        });
    }

    function reading(show) {
        const done = element("button", { className: "primary", textContent: show.mode === "read" ? t("Read") : t("Check") });
        const parts = [];
        let fields = [];
        let message = () => ({ read: true });
        if (show.mode === "questions") {
            fields = show.questions.map(() =>
                element("textarea", { placeholder: t("Your answer"), spellcheck: false, rows: 2 })
            );
            message = () => ({ answers: fields.map((field) => field.value) });
            parts.push(
                element("h3", { textContent: t("Questions") }),
                element(
                    "ol",
                    { className: "sentences" },
                    ...show.questions.map((question, number) =>
                        element("li", { className: "card" }, element("div", { textContent: question }), fields[number])
                    ),
                ),
            );
        } else if (show.mode === "retell") {
            fields = [element("textarea", { placeholder: t("Tell the story in your own words"), spellcheck: false, rows: 6 })];
            message = () => ({ retelling: fields[0].value });
            parts.push(element("h3", { textContent: t("Retell it") }), fields[0]);
        }
        done.onclick = () => {
            if (show.mode === "read" || fields.some((field) => field.value.trim())) {
                send(message(), done, t(DOING[show.mode]), fields);
            }
        };
        root.replaceChildren(
            progress(show.at, show.total),
            storyOf(show.story, exercise, show.number),
            ...parts,
            element("div", { className: "actions" }, done),
            error,
        );
    }

    function reviewing(show) {
        const go = element("button", { className: "primary", textContent: show.more ? t("Next story") : t("Done") });
        if (show.more) {
            go.onclick = () => send({ next: true }, go, t("Writing the next story…"));
        } else {
            go.onclick = () => exercise.finish();
        }
        const parts = [];
        if (show.mode === "questions") {
            const right = show.feedback.filter((each) => each.result === "right").length;
            parts.push(
                element(
                    "p",
                    {},
                    element("strong", { textContent: t(LABELS[show.result]) }),
                    ` · ${t("{right} of {count} right", { right, count: show.feedback.length })}`,
                ),
                element("ol", { className: "sentences" }, ...show.feedback.map((each) => answerFeedbackOf(each, t))),
            );
        } else if (show.mode === "retell") {
            parts.push(element("ol", { className: "sentences" }, ...show.feedback.map((each) => retellingFeedbackOf(each, t))));
        }
        root.replaceChildren(
            progress(show.at - 1, show.total),
            ...parts,
            element("div", { className: "actions" }, go),
            element("details", {}, element("summary", { textContent: t("The story") }), storyOf(show.story, exercise, show.at - 1)),
            error,
        );
        go.focus();
        if (show.more && !show.prepared) {
            // written while the learner reads this, so that the next is there at once
            exercise.act({ prepare: true }).catch(() => undefined);
        }
    }

    exercise.onShow((show) => (show.feedback ? reviewing(show) : reading(show)));
}
