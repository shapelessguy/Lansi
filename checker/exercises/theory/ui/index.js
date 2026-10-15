// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { element } from "../../kit.js";
import { render as markdownOf } from "./markdown.js";

export function mount(root, exercise) {
    root.classList.add("theory");
    // the page on show, which is turned here alone, without the backend
    let page = null;
    let shown = null;
    let asking = false;
    let error = "";
    // what is being written to ask, kept when the page is turned
    let draft = "";

    function markdown(text, className) {
        const made = element("div", { className: `rendered ${className}` });
        made.innerHTML = markdownOf(text);
        return made;
    }

    /** What a page is called in the list: its first heading, as plain text. */
    function titleOf(text, number) {
        const heading = text.match(/^\s*#{1,6}\s+(.*)$/m);
        if (!heading) {
            return `Page ${number + 1}`;
        }
        return heading[1].replace(/\{[a-z]:([^{}]+)\}/g, "$1").replace(/[*_~`]/g, "").trim();
    }

    function turnTo(number) {
        page = Math.max(0, Math.min(shown.pages.length - 1, number));
        render();
    }

    function ask(question) {
        if (asking || !question.trim()) {
            return;
        }
        asking = true;
        error = "";
        render();
        exercise.act({ question, page }).then(
            () => {
                draft = "";
                asking = false;
                render();
                root.querySelector("textarea")?.focus();
            },
            (failed) => {
                error = failed.message;
                asking = false;
                render();
            },
        );
    }

    function contents() {
        const list = element("ol", { className: "contents", ariaLabel: "Pages" });
        shown.pages.forEach((text, number) => {
            const go = element(
                "button",
                { title: titleOf(text, number) },
                element("span", { className: "number", textContent: String(number + 1) }),
                element("span", { textContent: titleOf(text, number) }),
            );
            if (number === page) {
                go.setAttribute("aria-current", "page");
            }
            go.onclick = () => turnTo(number);
            list.append(element("li", {}, go));
        });
        return element("nav", {}, list);
    }

    /**
     * Every page, one over the other, with only the one on show seen:
     * they all take the room of the tallest, so that the buttons below
     * stay where they are as the pages are turned.
     */
    function pages() {
        const stack = element("div", { className: "pages" });
        shown.pages.forEach((text, number) => {
            const made = markdown(text, number === page ? "card page" : "card page away");
            stack.append(made);
        });
        return stack;
    }

    function navigation() {
        const last = page === shown.pages.length - 1;
        const back = element("button", { textContent: "← Back", disabled: page === 0 });
        back.onclick = () => turnTo(page - 1);
        const forward = element("button", { className: "primary", textContent: last ? "Done" : "Next →" });
        forward.onclick = () => (last ? exercise.finish() : turnTo(page + 1));
        return element(
            "div",
            { className: "nav" },
            back,
            element("span", { className: "progress", textContent: `Page ${page + 1} of ${shown.pages.length}` }),
            forward,
        );
    }

    function chat() {
        const box = element("section", { className: "chat" });
        box.append(element("h2", { textContent: "Ask about the lesson" }));
        if (shown.chat.length === 0) {
            box.append(element("p", {
                className: "muted",
                textContent: "Ask anything that is not clear, or write your answers to the exercise at the end of a page to have them checked.",
            }));
        }
        for (const turn of shown.chat) {
            box.append(element(
                "div",
                { className: "turn" },
                element(
                    "div",
                    { className: "question" },
                    element("span", { className: "on", textContent: `Page ${turn.page + 1}` }),
                    turn.question,
                ),
                markdown(turn.answer, "answer"),
            ));
        }
        if (asking) {
            box.append(element("p", { className: "muted", textContent: "Thinking…" }));
        }
        const input = element("textarea", {
            value: draft,
            placeholder: "Your question (Enter to send, Shift+Enter for a new line)",
            disabled: asking,
        });
        // questions about the lesson may be asked in any language, so their spelling is not checked
        input.dataset.noCheck = "";
        input.oninput = () => (draft = input.value);
        input.onkeydown = (event) => {
            if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                ask(input.value);
            }
        };
        const send = element("button", { className: "primary", textContent: "Ask", disabled: asking });
        send.onclick = () => ask(input.value);
        box.append(input, element("div", { className: "actions" }, send));
        if (error) {
            box.append(element("p", { className: "error", textContent: error }));
        }
        return box;
    }

    function render() {
        const focused = root.getRootNode().activeElement?.tagName === "TEXTAREA";
        root.replaceChildren(
            contents(),
            element("div", {}, pages(), navigation()),
            chat(),
        );
        if (focused) {
            root.querySelector("textarea")?.focus();
        }
    }

    // the pages are turned with the arrow keys, wherever nothing is being written
    function turnByKey(event) {
        const target = event.composedPath()[0];
        if (!shown || target.closest?.("textarea, input, select, [contenteditable]")) {
            return;
        }
        if (event.key === "ArrowRight" && page < shown.pages.length - 1) {
            turnTo(page + 1);
        } else if (event.key === "ArrowLeft") {
            turnTo(page - 1);
        }
    }

    document.addEventListener("keydown", turnByKey);

    exercise.onShow((show) => {
        if (page === null) {
            page = show.page ?? 0;
        }
        shown = show;
        render();
    });
    return () => document.removeEventListener("keydown", turnByKey);
}
