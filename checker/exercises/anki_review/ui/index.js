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
                    : `<button class="replay" data-side="${letter}" data-number="${number}" title="Play">▶</button>`,
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
 * review is over.
 */
export function mount(root, exercise) {
    let show = null;
    let revealed = false;
    let busy = false;
    let error = "";
    let shownAt = Date.now();
    let finished = false;
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
            .map(([name, number]) => `${name} ${number}`)
            .join(", ");
        return element(
            "div",
            { className: "card anki-over" },
            element("p", {
                textContent: show.reviewed === 1
                    ? `1 card reviewed${said ? `: ${said}` : ""}.`
                    : `${show.reviewed} cards reviewed${said ? `: ${said}` : ""}.`,
            }),
            show.done_for_today
                ? element("p", { className: "muted", textContent: "Nothing more is due in this deck today." })
                : null,
            element("p", { className: "muted", textContent: "Your answers are synced to Anki." }),
            element(
                "div",
                { className: "actions" },
                element("button", {
                    className: "primary",
                    textContent: "Finish",
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
                element("button", { className: "primary", textContent: "Show answer", disabled: busy, onclick: reveal }),
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
                        title: `${name} (${rating})`,
                        onclick: () => answer(rating),
                    },
                    card.settings.show_intervals_on_buttons && card.labels[index]
                        ? element("span", { className: "anki-due", textContent: card.labels[index] })
                        : null,
                    element("span", { textContent: name }),
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
                    textContent: `${show.deck}${show.over || !show.reviewed ? "" : ` · ${show.reviewed} reviewed`}`,
                }),
                card?.settings.show_remaining_due_counts ? counts() : null,
                card?.settings.show_timer ? timer : null,
            ),
            show.notice ? element("p", { className: "muted", textContent: show.notice }) : null,
            card
                ? cardSide(exercise, card, revealed ? card.answer : card.question, revealed ? "a" : "q", replay)
                : summary(),
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
