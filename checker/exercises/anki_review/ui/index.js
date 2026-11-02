// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { element } from "../../kit.js";

/** The buttons of the reviewer, by the ratings they give, which are also their keys. */
const BUTTONS = [
    [1, "Again", "again"],
    [2, "Hard", "hard"],
    [3, "Good", "good"],
    [4, "Easy", "easy"],
];
/** Where a card plays a sound, or has a text read aloud: the side, and the place of it in that side's list. */
const PLAY = /\[anki:play:([qa]):(\d+)\]/g;
/** A box an answer is typed in, which is not asked for here. */
const TYPED = /\[\[type:[^\]]*\]\]/g;
/** An address that is not the name of a file of the media, such as one on the web or a picture in a data URL. */
const NOT_MEDIA = /^(?:[a-z][a-z0-9+.-]*:|\/\/|#)/i;
/** What every card is shown with, before the styles of its notetype, as the reviewer of Anki has it. */
const CARD_BASE = `
:host { display: block; }
.card { padding: 20px 16px; border-radius: 12px; overflow-wrap: anywhere; }
.card img { max-width: 100%; height: auto; }
.replay { display: inline-flex; vertical-align: middle; width: 1.6em; height: 1.6em; margin: 0 4px;
    align-items: center; justify-content: center; padding: 0; border: 1px solid currentColor;
    border-radius: 50%; background: none; color: inherit; cursor: pointer; font-size: 0.8em; opacity: 0.7; }
.replay:hover { opacity: 1; }
`;
/**
 * What every card is shown with after the styles of its notetype: the
 * colours and the font of the app, in place of those of the notetype, which
 * are most often black on white, so that the card is in the style of the app.
 * The custom properties of the app reach into the shadow root.
 */
const CARD_APP = `
.card { background: var(--panel) !important; color: var(--text) !important;
    font-family: inherit !important; }
.card a { color: var(--accent); }
`;

/** What is in a side but is not seen: its styles and scripts. */
const HIDDEN = /<(style|script)\b[\s\S]*?<\/\1\s*>/gi;
/** What ends a line of a side. */
const BREAK = /<br\s*\/?>|<\/(?:div|p|li|tr|h\d)\s*>|<hr\b[^>]*>/gi;
/** Where the answer of a side that shows the question too starts, as Anki marks it. */
const ANSWER_START = /<hr\b[^>]*\bid\s*=\s*["']?answer\b[^>]*>/i;

/** A side of a card as text, its lines without markup, sounds or the boxes an answer is typed in, as the backend has it. */
function plain(side) {
    const template = document.createElement("template");
    template.innerHTML = side.replace(HIDDEN, " ").replace(BREAK, "\n").replace(PLAY, "").replace(TYPED, "");
    return (template.content.textContent ?? "")
        .split("\n")
        .map((line) => line.split(/\s+/).filter(Boolean).join(" "))
        .filter(Boolean)
        .join("\n");
}

/** The question of a card and its answer, as text, the answer without the question that its side most often shows again. */
function cardText(card) {
    const start = card.answer.search(ANSWER_START);
    const answer = start < 0 ? card.answer : card.answer.slice(start).replace(ANSWER_START, "");
    return { question: plain(card.question), answer: plain(answer) || plain(card.answer) };
}

/** What the model that writes a hint is told, with the learner's prompt for it as the main instruction. */
function hintSystem({ question, answer }, guidance) {
    return `This is a hint for someone reviewing a flashcard, who has seen its question but not its answer. \
Help them find the answer themselves: do not give it away, nor any word of it.

---- Question ----
${question}
---- Answer, which they have not seen ----
${answer}
---- End of the card ----

Follow the guidance below closely for how to write the hint: it is the main instruction.

---- Hint guidance ----
${guidance}
---- End of the guidance ----

Reply with the hint alone.`;
}

/** What the model of the chat about a card is told, with the learner's prompt for it as the main instruction. */
function moreInfoSystem({ question, answer }, hint, guidance) {
    return `The user just revealed the answer to a flashcard and wants more information about it. This is the start \
of a short back-and-forth chat, not a single reply: be ready to answer whatever they ask next about this card.

---- Card ----
Question shown to the user:
${question}
${hint ? `\nHint already given to the user:\n${hint}\n` : ""}
Answer revealed to the user:
${answer}
---- End of the card ----

Follow the guidance below closely for what kind of information to focus on: it is the main instruction.

---- Guidance ----
${guidance}
---- End of the guidance ----`;
}

/** Whether the app is dark, as the class nightMode of the cards says it is in Anki. */
function isDark() {
    const theme = document.documentElement.dataset.theme;
    return theme ? theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
}

/** A file of the media of a card by its name as the HTML has it, which may be written as an address. */
function mediaName(source) {
    try {
        return decodeURIComponent(source);
    } catch {
        return source;
    }
}

/**
 * A side of a card, in a shadow root of its own, with the styles of its
 * notetype and nothing of the exercise's, but for the colours and the font
 * of the app.
 */
function cardSide(exercise, card, html, side, onPlay) {
    const host = element("div", { className: "anki-side" });
    const shadow = host.attachShadow({ mode: "open" });
    const style = document.createElement("style");
    style.textContent = CARD_BASE + card.css + CARD_APP;
    const template = document.createElement("template");
    // parsed in a template, which fetches nothing, before the media are found
    template.innerHTML = html
        .replace(TYPED, "")
        .replace(
            PLAY,
            (_, letter, number) =>
                card.settings.hide_audio_play_buttons
                    ? ""
                    : `<button class="replay" data-side="${letter}" data-number="${number}" title="${exercise.t("Play")}">▶</button>`,
        );
    for (const media of template.content.querySelectorAll("[src]")) {
        const source = media.getAttribute("src") ?? "";
        if (!source || NOT_MEDIA.test(source)) {
            continue;
        }
        media.removeAttribute("src");
        exercise.ankiMedia(mediaName(source)).then(
            (url) => media.setAttribute("src", url),
            () => media.setAttribute("alt", media.getAttribute("alt") || source),
        );
    }
    const body = element("div", { className: `card card${card.ord}${isDark() ? " nightMode night_mode" : ""}` });
    body.append(template.content);
    body.addEventListener("click", (event) => {
        const button = event.target.closest?.(".replay");
        if (button) {
            onPlay(button.dataset.side, Number(button.dataset.number));
        }
    });
    shadow.append(style, body);
    host.dataset.side = side;
    return host;
}

/** Minutes and seconds, as the timer of the reviewer shows them. */
function clock(millis) {
    const seconds = Math.floor(millis / 1000);
    return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

/**
 * The reviewer of Anki: the question of a card, then its answer, and the
 * four buttons, each with when the card would be due again. The keys are
 * those of Anki: Space or Enter shows the answer and then answers Good, and
 * 1 to 4 answer Again to Easy. What the backend shows is a card, or that the
 * review is over. On the question, Hint has the chat model write a hint at
 * the answer, which stays under the card; on the answer, More info opens a
 * chat about the card. Each is asked as the learner's prompt of that name
 * says.
 */
export function mount(root, exercise) {
    const t = exercise.t;
    let show = null;
    let revealed = false;
    let busy = false;
    let error = "";
    let shownAt = Date.now();
    let finished = false;
    // the hint at the answer of the card shown, while it is asked for and once it came
    let hint = "";
    let hinting = false;
    let hintError = "";
    // whether the app this runs in can ask the chat model, which one before it could not
    const helps = typeof exercise.ask === "function" && typeof exercise.chat === "function";
    // the texts read aloud, by the numbers that tell them apart
    const numbers = new Map();
    // counted up whenever what was being played is to stop
    let playing = 0;
    let audio = null;
    const timer = element("span", { className: "progress anki-timer" });
    const ticking = setInterval(() => {
        timer.textContent = clock(Date.now() - shownAt);
    }, 1000);

    function stopPlaying() {
        playing++;
        audio?.pause();
        audio = null;
    }

    async function play(tags) {
        stopPlaying();
        const mine = playing;
        for (const tag of tags) {
            if (mine !== playing) {
                return;
            }
            if (tag.kind === "tts") {
                if (!numbers.has(tag.text)) {
                    numbers.set(tag.text, numbers.size + 1);
                }
                exercise.readAloud(tag.text, numbers.get(tag.text));
                continue;
            }
            const url = await exercise.ankiMedia(tag.file).catch(() => null);
            if (!url || mine !== playing) {
                continue;
            }
            await new Promise((done) => {
                audio = new Audio(url);
                audio.onended = done;
                audio.onerror = done;
                audio.play().catch(done);
            });
        }
    }

    function replay(letter, number) {
        const tags = letter === "q" ? show.card.question_av : show.card.answer_av;
        if (tags[number]) {
            play([tags[number]]);
        }
    }

    function reveal() {
        if (!show?.card || revealed || busy) {
            return;
        }
        revealed = true;
        render();
        if (show.card.settings.autoplay) {
            play(show.card.answer_av);
        }
    }

    function answer(rating) {
        if (!show?.card || !revealed || busy) {
            return;
        }
        busy = true;
        error = "";
        stopPlaying();
        render();
        exercise.act({ rating, millis: Date.now() - shownAt }).catch((failed) => {
            busy = false;
            error = failed.message;
            render();
        });
    }

    function askHint() {
        const card = show?.card;
        if (!card || revealed || hinting || hint) {
            return;
        }
        hinting = true;
        hintError = "";
        render();
        exercise.ask([
            { role: "system", content: hintSystem(cardText(card), exercise.prompts.hint ?? "") },
            { role: "user", content: "Give me a hint." },
        ]).then(
            (given) => {
                if (show?.card === card) {
                    hint = given;
                }
            },
            (failed) => {
                if (show?.card === card) {
                    hintError = failed.message;
                }
            },
        ).finally(() => {
            if (show?.card === card) {
                hinting = false;
                render();
            }
        });
    }

    function moreInfo() {
        const card = show?.card;
        if (!card || !revealed) {
            return;
        }
        exercise.chat({
            title: t("Ask about this card"),
            system: moreInfoSystem(cardText(card), hint, exercise.prompts.more_info ?? ""),
            opening: "Tell me more about this card.",
        });
    }

    /** The hint, if there is one, and the button that asks for it on the question, or for more on the answer. */
    function help() {
        if (!helps) {
            return null;
        }
        return element(
            "div",
            { className: "anki-help" },
            hint ? element("div", { className: "anki-hint", textContent: hint }) : null,
            hintError ? element("p", { className: "error", textContent: hintError }) : null,
            revealed
                ? element("button", { textContent: t("More info"), disabled: busy, onclick: moreInfo })
                : hint
                ? null
                : element("button", {
                    textContent: hinting ? t("Thinking of a hint…") : t("Hint"),
                    disabled: busy || hinting,
                    onclick: askHint,
                }),
        );
    }

    function counts() {
        const { new: fresh = 0, learning = 0, review = 0 } = show.counts;
        const queue = show.card?.queue;
        const count = (number, kind) =>
            element("span", {
                className: `anki-count ${kind}${queue === kind ? " current" : ""}`,
                textContent: String(number),
            });
        return element("span", { className: "anki-counts" }, count(fresh, "new"), " ", count(learning, "learning"), " ", count(review, "review"));
    }

    function summary() {
        const said = BUTTONS.map(([, name]) => [name, show.ratings[name] ?? 0])
            .filter(([, number]) => number)
            .map(([name, number]) => `${t(name)} ${number}`)
            .join(", ");
        return element(
            "div",
            { className: "card anki-over" },
            element("p", {
                textContent: said
                    ? t(show.reviewed === 1 ? "{count} card reviewed: {ratings}." : "{count} cards reviewed: {ratings}.", {
                        count: show.reviewed,
                        ratings: said,
                    })
                    : t(show.reviewed === 1 ? "{count} card reviewed." : "{count} cards reviewed.", {
                        count: show.reviewed,
                    }),
            }),
            show.done_for_today
                ? element("p", { className: "muted", textContent: t("Nothing more is due in this deck today.") })
                : null,
            element("p", { className: "muted", textContent: t("Your answers are synced to Anki.") }),
            element(
                "div",
                { className: "actions" },
                element("button", {
                    className: "primary",
                    textContent: t("Finish"),
                    disabled: finished,
                    onclick: () => {
                        finished = true;
                        exercise.finish();
                        render();
                    },
                }),
            ),
        );
    }

    function buttons() {
        const card = show.card;
        if (!revealed) {
            return element(
                "div",
                { className: "actions anki-buttons" },
                element("button", { className: "primary", textContent: t("Show answer"), disabled: busy, onclick: reveal }),
            );
        }
        return element(
            "div",
            { className: "actions anki-buttons" },
            ...BUTTONS.map(([rating, name, kind], index) =>
                element(
                    "button",
                    {
                        className: `anki-button ${kind}`,
                        disabled: busy,
                        title: `${t(name)} (${rating})`,
                        ariaLabel: t(name),
                        onclick: () => answer(rating),
                    },
                    // the button says when the card would be due again, its colour which it is; its
                    // name only where the deck shows no intervals, so that the four fit a phone
                    card.settings.show_intervals_on_buttons && card.labels[index] ? card.labels[index] : t(name),
                ),
            ),
        );
    }

    function render() {
        if (!show) {
            return;
        }
        const card = show.card;
        const parts = [
            element(
                "div",
                { className: "anki-head" },
                element("span", {
                    className: "progress",
                    textContent: `${show.deck}${
                        show.over || !show.reviewed ? "" : ` · ${t("{count} reviewed", { count: show.reviewed })}`
                    }`,
                }),
                card?.settings.show_remaining_due_counts ? counts() : null,
                card?.settings.show_timer ? timer : null,
            ),
            show.notice ? element("p", { className: "muted", textContent: show.notice }) : null,
            card
                ? cardSide(exercise, card, revealed ? card.answer : card.question, revealed ? "a" : "q", replay)
                : summary(),
            card ? help() : null,
            card ? buttons() : null,
            error ? element("p", { className: "error", textContent: error }) : null,
        ];
        root.replaceChildren(...parts.filter((part) => part !== null));
    }

    function onKey(event) {
        if (event.ctrlKey || event.metaKey || event.altKey || !show?.card) {
            return;
        }
        const target = event.composedPath()[0];
        if (target instanceof HTMLElement && (target.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName))) {
            return;
        }
        if (event.key === " " || event.key === "Enter") {
            event.preventDefault();
            if (revealed) {
                answer(3);
            } else {
                reveal();
            }
        } else if (revealed && /^[1-4]$/.test(event.key)) {
            event.preventDefault();
            answer(Number(event.key));
        } else if (event.key === "r" || event.key === "R") {
            play(revealed ? show.card.answer_av : show.card.question_av);
        }
    }

    exercise.onShow((given) => {
        show = given;
        revealed = false;
        busy = false;
        error = "";
        hint = "";
        hinting = false;
        hintError = "";
        shownAt = Date.now();
        timer.textContent = clock(0);
        render();
        if (show.card?.settings.autoplay) {
            play(show.card.question_av);
        } else {
            stopPlaying();
        }
    });
    document.addEventListener("keydown", onKey);
    return () => {
        document.removeEventListener("keydown", onKey);
        clearInterval(ticking);
        stopPlaying();
    };
}
