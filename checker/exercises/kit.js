// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

// What the interface of an exercise is written with. The interface is
// `ui/index.js`, a module the app loads into its own page, with the styles
// of `ui/style.css`, if there is one. The module exports
//
//   mount(root, exercise)  -> a function that unmounts it, or nothing
//
// `root` is an element in a shadow root of its own, which is given kit.css
// and style.css alone: what the exercise styles stays its own, and the
// styles of the app stay out. The colours are those of the app all the
// same, as its CSS variables, such as --bg, --text and --accent, reach in.
// `exercise` is how the interface talks to the app:
//
//   exercise.onShow(handler)  has `handler` called with what the backend
//                             shows, at once and after each act
//   exercise.act(message)     has the backend act on `message`; resolves
//                             with what it shows then, once the handler was
//                             called with it, or rejects with why it could not
//   exercise.finish()         the learner is done with the exercise
//   exercise.readAloud(text, number)
//                             has `text`, in the language learned, read
//                             aloud by the voice the learner chose, in the
//                             player of the app; `number` tells the texts
//                             of the exercise apart, as the audio of each
//                             is kept, and is 0 if not given
//   exercise.ankiMedia(name)  resolves with an address, in the page, of the
//                             file `name` of the media of the learner's Anki
//                             collection, such as a picture of a card, or
//                             rejects with why there is none
//   exercise.language         the language the app is shown in, by its
//                             English name, such as "Italian"
//   exercise.t(text, values)  `text`, written in English, in that language,
//                             with each `{name}` in it given what `values`
//                             has for it: as the `messages` of the manifest
//                             have it, as kit.py describes, or else as the
//                             app has it, or else as it is
//
// What the interface shows the learner, as opposed to what the backend made
// in the language learned, is written in English and shown through
// `exercise.t`.
//
// Text the interface shows can be selected to have it translated or
// taken into the vocabulary, as anywhere in the app, without anything done
// for it here. So is the spelling of what is written in a <textarea>,
// unless it has the attribute data-no-check, and its sentences are checked
// by the sentence check model as the `sentence_checks` of the manifest
// say, as kit.py describes; boxes of one line, <input>, are left alone.
//
// What `mount` returns is called when the exercise is taken away, to undo
// what it did outside `root`, such as listening to the document. The
// interface runs in the page of the app, and is trusted, as the backend is,
// to be the user's own.

/** An element with `props` set on it and `children` in it, those that are null left out. */
export function element(tag, props = {}, ...children) {
    const made = Object.assign(document.createElement(tag), props);
    made.append(...children.filter((child) => child !== null));
    return made;
}

/** What the criteria of the kit are called, as `ratingsOf` shows them. */
const CRITERIA = {
    task: "Task",
    coherence: "Coherence",
    vocabulary: "Vocabulary",
    structures: "Structures",
    pronunciation: "Pronunciation",
};

/**
 * The ratings of what was written or said, each from 0 to 4 by a criterion
 * of the kit, as bars, named in the language of the app by `t`, the
 * `exercise.t` of the interface.
 */
export function ratingsOf(ratings, t = (text) => text) {
    return element(
        "dl",
        { className: "ratings" },
        ...Object.entries(ratings).flatMap(([name, value]) => [
            element("dt", { textContent: CRITERIA[name] ? t(CRITERIA[name]) : name }),
            element(
                "dd",
                {},
                element("span", { className: "meter" }, element("span", { style: `width: ${value * 25}%` })),
                element("span", { className: "muted", textContent: ` ${value} / 4` }),
            ),
        ]),
    );
}
