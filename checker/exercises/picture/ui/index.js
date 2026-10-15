// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { element } from "../../kit.js";

const RESULTS = { right: "right", partial: "almost", wrong: "wrong" };

export function mount(root, exercise) {
    // the point being labelled, which stays open across what is shown
    let open = null;
    const error = element("p", { className: "error" });

    /** The next point after `after` that has no label, or null. */
    function nextBlank(show, after = -1) {
        const count = show.points.length;
        for (let step = 1; step <= count; step++) {
            const index = (after + step + count) % count;
            if (!show.points[index].label) {
                return index;
            }
        }
        return null;
    }

    /** Has the backend do `message`, showing what it shows then, or why it could not. */
    function send(message, button, busyText) {
        const idle = button?.textContent;
        if (button) {
            button.disabled = true;
            button.textContent = busyText;
        }
        error.textContent = "";
        return exercise.act(message).catch((failed) => {
            error.textContent = failed.message;
            if (button) {
                button.disabled = false;
                button.textContent = idle;
            }
            throw failed;
        });
    }

    function askBox(show, index, stage) {
        const point = show.points[index];
        const input = element("input", {
            autocomplete: "off",
            spellcheck: false,
            placeholder: "What is it?",
            value: point.label,
            "aria-label": "What the point is on",
        });
        const ok = element("button", { className: "primary", textContent: "OK" });
        const box = element("div", { className: "ask" }, input, ok);
        // beside the point, on whichever side there is room
        if (point.x < 600) {
            box.style.left = `calc(${point.x / 10}% + 18px)`;
        } else {
            box.style.right = `calc(${100 - point.x / 10}% + 18px)`;
        }
        box.style.top = `calc(${point.y / 10}% - 20px)`;
        const save = () => {
            input.disabled = ok.disabled = true;
            send({ point: index, label: input.value }).then(
                (shown) => {
                    open = nextBlank(shown, index);
                    render(shown);
                },
                () => {
                    input.disabled = ok.disabled = false;
                },
            );
        };
        ok.onclick = save;
        input.addEventListener("keydown", (event) => {
            if (event.key === "Enter") {
                event.preventDefault();
                save();
            } else if (event.key === "Escape") {
                open = null;
                render(show);
            }
        });
        stage.append(box);
        setTimeout(() => {
            input.focus();
            input.select();
        });
    }

    function labelOf(point) {
        const side = point.x > 820 ? "from-right" : point.x < 180 ? "from-left" : "";
        const label = element("span", { className: `label ${side}` });
        const { feedback } = point;
        if (feedback && feedback.result !== "right") {
            if (point.label) {
                label.append(element("s", { textContent: point.label }), " ");
            }
            label.append(feedback.correct);
        } else {
            label.append(point.label);
        }
        Object.assign(label.style, { left: `${point.x / 10}%`, top: `${point.y / 10}%` });
        return label;
    }

    function judgedList(show) {
        const list = element("ol", { className: "judged" });
        show.points.forEach((point, index) => {
            const { feedback } = point;
            const item = element("li");
            item.append(
                element("span", { className: "number", textContent: `${index + 1}.` }),
                element("strong", { className: feedback.result, textContent: RESULTS[feedback.result] }),
                " ",
                point.label ? element("span", { textContent: point.label }) : element("em", { className: "muted", textContent: "nothing" }),
            );
            if (feedback.result !== "right") {
                item.append(" → ", element("strong", { textContent: feedback.correct }));
            }
            if (feedback.translation) {
                item.append(element("span", { className: "muted", textContent: ` (${feedback.translation})` }));
            }
            if (feedback.note) {
                item.append(element("span", { className: "muted", textContent: ` · ${feedback.note}` }));
            }
            list.append(item);
        });
        return list;
    }

    function summary(show) {
        const labelled = show.points.filter((point) => point.label).length;
        if (!show.judged) {
            return element("span", {
                className: "muted",
                textContent: `${labelled} of ${show.points.length} labelled. Click a point to label it, and check when you are done.`,
            });
        }
        const count = (result) => show.points.filter((point) => point.feedback.result === result).length;
        return element("span", {
            textContent: `${count("right")} right · ${count("partial")} almost · ${count("wrong")} wrong`,
        });
    }

    function render(show) {
        root.replaceChildren();
        if (show.judged || (open !== null && !show.points[open])) {
            open = null;
        }
        const progress = show.pictures > 1 ? `picture ${show.picture} of ${show.pictures}` : "";
        root.append(
            element(
                "div",
                { className: "top" },
                summary(show),
                element("span", { className: "progress", textContent: progress }),
            ),
        );
        const stage = element("div", { className: "stage" });
        stage.append(element("img", { src: show.image, alt: "A picture with points to label" }));
        show.points.forEach((point, index) => {
            const state = point.feedback?.result ?? (point.label ? "labelled" : "");
            const dot = element("button", {
                className: `dot ${state} ${open === index ? "open" : ""}`,
                title: point.label || `Point ${index + 1}`,
                "aria-label": point.label ? `${index + 1}: ${point.label}` : `Point ${index + 1}`,
                disabled: show.judged,
            });
            Object.assign(dot.style, { left: `${point.x / 10}%`, top: `${point.y / 10}%` });
            dot.onclick = () => {
                open = index;
                render(show);
            };
            stage.append(dot);
            if (point.label || point.feedback) {
                stage.append(labelOf(point));
            }
        });
        root.append(stage);
        if (open !== null) {
            askBox(show, open, stage);
        }
        const actions = element("div", { className: "actions" });
        if (show.lost) {
            // the picture is kept: only where the things are is asked again
            const again = element("button", { className: "primary", textContent: "Look again" });
            again.onclick = () =>
                send({ look: true }, again, "Looking…").then((shown) => {
                    open = nextBlank(shown);
                    render(shown);
                }, () => undefined);
            actions.append(
                element("span", { className: "error", textContent: "No thing could be found on the picture." }),
                again,
            );
            root.append(actions, element("p", { className: "muted", textContent: show.lost }), error);
            return;
        }
        if (!show.judged) {
            const check = element("button", { className: "primary", textContent: "Check labels" });
            check.disabled = !show.points.some((point) => point.label);
            check.onclick = () => send({ check: true }, check, "Checking…").then(render, () => undefined);
            actions.append(check);
        } else if (show.more) {
            const next = element("button", { className: "primary", textContent: "Next picture" });
            next.onclick = () =>
                send({ next: true }, next, "Drawing the next picture…").then((shown) => {
                    open = nextBlank(shown);
                    render(shown);
                }, () => undefined);
            actions.append(next);
        } else {
            const done = element("button", { className: "primary", textContent: "Done" });
            done.onclick = () => exercise.finish();
            actions.append(done);
        }
        root.append(actions, error);
        if (show.judged) {
            root.append(judgedList(show));
        }
    }

    exercise.onShow((show) => {
        if (open === null && !show.judged && !show.points.some((point) => point.label)) {
            open = nextBlank(show);
        }
        render(show);
    });
}
