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
