// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { element } from "../../kit.js";

const RESULTS = { right: "right", partial: "almost", wrong: "wrong" };

export function mount(root, exercise) {
    const t = exercise.t;
    // the points the learner marked on the picture shown, each with its
    // label, kept here until they are checked
    let points = [];
    // the point being labelled, which stays open across what is shown
    let open = null;
    // the picture the points are on, so that a new one starts with none
    let shownImage = null;
    let shown = null;
    const error = element("p", { className: "error" });

    /** Has the backend do `message`, showing what it shows then, or why it could not. */
    function send(message, button, busyText) {
        const idle = button.textContent;
        button.disabled = true;
        button.textContent = busyText;
        error.textContent = "";
        return exercise.act(message).catch((failed) => {
            error.textContent = failed.message;
            button.disabled = false;
            button.textContent = idle;
            throw failed;
        });
    }

    /** The point being labelled closed, and left out if it has no label. */
    function close() {
        if (open !== null && !points[open]?.label) {
            points.splice(open, 1);
        }
        open = null;
    }

    function askBox(point, stage) {
        const input = element("input", {
            autocomplete: "off",
            spellcheck: false,
            placeholder: t("What is it?"),
            value: point.label,
            "aria-label": t("What the point is on"),
        });
        const ok = element("button", { className: "primary", textContent: t("OK") });
        const remove = element("button", { textContent: t("Remove") });
        const box = element("div", { className: "ask" }, input, ok, remove);
        // beside the point, on whichever side there is room
        if (point.x < 600) {
            box.style.left = `calc(${point.x / 10}% + 18px)`;
        } else {
            box.style.right = `calc(${100 - point.x / 10}% + 18px)`;
        }
        box.style.top = `calc(${point.y / 10}% - 20px)`;
        const save = () => {
            point.label = input.value.split(/\s+/).filter(Boolean).join(" ");
            close();
            render();
        };
        ok.onclick = save;
        remove.onclick = () => {
            point.label = "";
            close();
            render();
        };
        input.addEventListener("keydown", (event) => {
            if (event.key === "Enter") {
                event.preventDefault();
                save();
            } else if (event.key === "Escape") {
                close();
                render();
            }
        });
        // a click in the box is not one on the picture
        box.addEventListener("click", (event) => event.stopPropagation());
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
            label.append(element("s", { textContent: point.label }), " ", feedback.correct);
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
                element("strong", { className: feedback.result, textContent: t(RESULTS[feedback.result]) }),
                " ",
                element("span", { textContent: point.label }),
            );
            if (feedback.result !== "right") {
                item.append(" → ", element("strong", { textContent: feedback.correct }));
            }
            if (feedback.alternatives?.length) {
                item.append(
                    element("span", {
                        className: "muted",
                        textContent: ` (${t("also {names}", { names: feedback.alternatives.join(", ") })})`,
                    }),
                );
            }
            if (feedback.translation) {
                item.append(element("span", { className: "muted", textContent: ` · ${feedback.translation}` }));
            }
            if (feedback.note) {
                item.append(element("span", { className: "muted", textContent: ` · ${feedback.note}` }));
            }
            if (feedback.hint) {
                // where the ring is, which does not count against the label
                item.append(element("span", { className: "hint", textContent: ` ⚠ ${feedback.hint}` }));
            }
            list.append(item);
        });
        return list;
    }

    function summary(show) {
        if (!show.judged) {
            const named = points.filter((point) => point.label).length;
            return element("span", {
                className: "muted",
                textContent: named
                    ? t("{count} named. Click on the picture to mark another thing, or on a point to change it.", {
                        count: named,
                    })
                    : t("Click on the picture where there is something you can name, and name it. Check when you are done."),
            });
        }
        const count = (result) => show.points.filter((point) => point.feedback.result === result).length;
        return element("span", {
            textContent: t("{right} right · {partial} almost · {wrong} wrong", {
                right: count("right"),
                partial: count("partial"),
                wrong: count("wrong"),
            }),
        });
    }

    function render() {
        const show = shown;
        root.replaceChildren();
        // what is shown once it is checked is what was checked
        const marks = show.judged ? show.points : points;
        if (show.judged) {
            open = null;
        }
        const progress = show.pictures > 1
            ? t("picture {at} of {total}", { at: show.picture, total: show.pictures })
            : "";
        root.append(
            element(
                "div",
                { className: "top" },
                summary(show),
                element("span", { className: "progress", textContent: progress }),
            ),
        );
        const stage = element("div", { className: `stage ${show.judged ? "" : "marking"}` });
        const image = element("img", { src: show.image, alt: t("A picture to mark things on") });
        stage.append(image);
        if (!show.judged) {
            stage.onclick = (event) => {
                if (event.target !== image) {
                    return;
                }
                close();
                if (points.length < show.most) {
                    const box = image.getBoundingClientRect();
                    const at = (offset, size) => Math.min(1000, Math.max(0, Math.round((offset / size) * 1000)));
                    points.push({
                        x: at(event.clientX - box.left, box.width),
                        y: at(event.clientY - box.top, box.height),
                        label: "",
                    });
                    open = points.length - 1;
                }
                render();
            };
        }
        marks.forEach((point, index) => {
            const state = point.feedback?.result ?? (point.label ? "labelled" : "");
            const dot = element("button", {
                className: `dot ${state} ${open === index ? "open" : ""}`,
                title: point.label || t("Point {number}", { number: index + 1 }),
                "aria-label": point.label ? `${index + 1}: ${point.label}` : t("Point {number}", { number: index + 1 }),
                disabled: show.judged,
            });
            Object.assign(dot.style, { left: `${point.x / 10}%`, top: `${point.y / 10}%` });
            dot.onclick = (event) => {
                event.stopPropagation();
                if (open !== index) {
                    const chosen = points[index];
                    close();
                    open = points.indexOf(chosen);
                }
                render();
            };
            stage.append(dot);
            if (point.label && open !== index) {
                stage.append(labelOf(point));
            }
        });
        root.append(stage);
        if (open !== null) {
            askBox(points[open], stage);
        }
        const actions = element("div", { className: "actions" });
        if (!show.judged) {
            const check = element("button", { className: "primary", textContent: t("Check labels") });
            check.disabled = !points.some((point) => point.label);
            check.onclick = () => {
                close();
                send({ check: true, points: points.filter((point) => point.label) }, check, t("Checking…")).then(
                    () => undefined,
                    () => undefined,
                );
            };
            actions.append(check);
        } else if (show.more) {
            const next = element("button", { className: "primary", textContent: t("Next picture") });
            next.onclick = () => send({ next: true }, next, t("Drawing the next picture…")).catch(() => undefined);
            actions.append(next);
        } else {
            const done = element("button", { className: "primary", textContent: t("Done") });
            done.onclick = () => exercise.finish();
            actions.append(done);
        }
        root.append(actions, error);
        if (show.judged) {
            root.append(judgedList(show));
        }
    }

    exercise.onShow((show) => {
        if (shown && show.image === shownImage && show.judged === shown.judged) {
            // nothing changed, as when the next picture was drawn ahead: the
            // label being written stays as it is
            shown = show;
            return;
        }
        if (show.image !== shownImage) {
            shownImage = show.image;
            points = [];
            open = null;
            if (!show.judged && show.picture < show.pictures) {
                // drawn while this one is labelled, so that it is there at once
                exercise.act({ prepare: true }).catch(() => undefined);
            }
        }
        shown = show;
        render();
    });
}
