// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { Fragment, type ReactNode } from "react";

import { type Message, t } from "../lib/i18n";

/**
 * `message` in the language of the interface, with each `{name}` in it
 * given what `values` has for it, which may be an element, such as a
 * button in the middle of a sentence.
 */
export function T({ message, values }: { message: Message; values: Record<string, ReactNode> }) {
    // the names are left in place by `t`, to be split at
    return (
        <>
            {t(message).split(/\{(\w+)\}/).map((piece, place) => (
                <Fragment key={place}>
                    {place % 2 === 1 ? (piece in values ? values[piece] : `{${piece}}`) : piece}
                </Fragment>
            ))}
        </>
    );
}
