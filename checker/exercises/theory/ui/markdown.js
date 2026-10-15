// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

// Markdown as HTML, for the pages of a lesson and the answers about them:
// headings, paragraphs, lists, quotes, tables, rules, code, and bold,
// italic, struck and code within a line. Everything is escaped first, so
// that nothing written as HTML is taken for it.
//
// Besides, the parts of a sentence may be coloured by what they are, as
// `{v:stehe}`; a cell of a table that is all one such part is coloured as a
// whole, which makes a table a diagram of a sentence. A quote may be a box
// of its own, as `> [!merke]`. MARKS and BOXES say which there are.

export const MARKS = {
    v: "the conjugated verb",
    p: "a prefix",
    s: "the subject",
    i: "a verb at the end, such as an infinitive",
    e: "an ending",
    c: "a vowel that changes",
    x: "what is wrong",
    h: "anything to stand out",
};
export const BOXES = { merke: "Merke", tipp: "Tipp", achtung: "Achtung", beispiel: "Beispiel" };
const MARK = /\{([a-z]):([^{}]+)\}/g;
const WHOLE_MARK = /^\{([a-z]):[^{}]+\}$/;

function escape(text) {
    return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function inline(text) {
    // code first, so that nothing within it is read as anything else
    const codes = [];
    let html = escape(text).replace(/`([^`]+)`/g, (_, code) => {
        codes.push(code);
        return `\u0000${codes.length - 1}\u0000`;
    });
    // a gap to fill in, as `___`, is no emphasis
    html = html.replace(/_{3,}/g, (gap) => `\u0001${gap.length}\u0001`);
    html = html
        .replace(MARK, (whole, mark, marked) => (
            mark in MARKS ? `<span class="mark mark-${mark}">${marked}</span>` : whole
        ))
        .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
        .replace(/__(.+?)__/g, "<strong>$1</strong>")
        .replace(/~~(.+?)~~/g, "<del>$1</del>")
        .replace(/(^|[^*\w])\*(?!\s)(.+?)\*(?!\w)/g, "$1<em>$2</em>")
        .replace(/(^|[^_\w])_(?!\s)(.+?)_(?!\w)/g, "$1<em>$2</em>");
    return html
        .replace(/\u0001(\d+)\u0001/g, (_, length) => "_".repeat(Number(length)))
        .replace(/\u0000(\d+)\u0000/g, (_, number) => `<code>${codes[number]}</code>`);
}

function cells(line) {
    return line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((cell) => cell.trim());
}

/** A cell of a table, coloured as a whole if it is all one part of a sentence. */
function cell(tag, text) {
    const whole = text.match(WHOLE_MARK);
    const marked = whole && whole[1] in MARKS ? ` class="cell cell-${whole[1]}"` : "";
    return `<${tag}${marked}>${inline(text)}</${tag}>`;
}

const LIST_ITEM = /^\s*([-*+]|\d+[.)])\s+(.*)$/;
const TABLE_RULE = /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/;
const RULE = /^\s*([-*_])(\s*\1){2,}\s*$/;

export function render(text) {
    const lines = text.replace(/\r\n?/g, "\n").split("\n");
    const out = [];
    let at = 0;
    // whether the line at `index` starts a block other than a paragraph
    const startsBlock = (index) => {
        const line = lines[index];
        return /^\s*(#{1,6}\s|>|```)/.test(line) || LIST_ITEM.test(line) || RULE.test(line)
            || (line.trim().startsWith("|") && TABLE_RULE.test(lines[index + 1] ?? ""));
    };
    while (at < lines.length) {
        const line = lines[at];
        if (!line.trim()) {
            at++;
        } else if (line.trim().startsWith("```")) {
            const code = [];
            at++;
            while (at < lines.length && !lines[at].trim().startsWith("```")) {
                code.push(lines[at++]);
            }
            at++;
            out.push(`<pre><code>${escape(code.join("\n"))}</code></pre>`);
        } else if (/^\s*#{1,6}\s/.test(line)) {
            const [, hashes, title] = line.trim().match(/^(#{1,6})\s+(.*?)\s*#*$/);
            out.push(`<h${hashes.length}>${inline(title)}</h${hashes.length}>`);
            at++;
        } else if (RULE.test(line)) {
            out.push("<hr>");
            at++;
        } else if (line.trim().startsWith(">")) {
            const quoted = [];
            while (at < lines.length && lines[at].trim().startsWith(">")) {
                quoted.push(lines[at++].trim().replace(/^>\s?/, ""));
            }
            const box = quoted[0].match(/^\[!([a-z]+)\]\s*(.*)$/);
            if (box && box[1] in BOXES) {
                const title = box[2] ? inline(box[2]) : BOXES[box[1]];
                out.push(
                    `<aside class="box box-${box[1]}"><div class="box-title">${title}</div>`
                        + `${render(quoted.slice(1).join("\n"))}</aside>`,
                );
            } else {
                out.push(`<blockquote>${render(quoted.join("\n"))}</blockquote>`);
            }
        } else if (line.trim().startsWith("|") && TABLE_RULE.test(lines[at + 1] ?? "")) {
            const head = cells(line);
            at += 2;
            const rows = [];
            while (at < lines.length && lines[at].trim().startsWith("|")) {
                rows.push(cells(lines[at++]));
            }
            out.push(
                "<table><thead><tr>" + head.map((text) => cell("th", text)).join("")
                    + "</tr></thead><tbody>"
                    + rows.map((row) =>
                        "<tr>" + head.map((_, column) => cell("td", row[column] ?? "")).join("") + "</tr>"
                    ).join("")
                    + "</tbody></table>",
            );
        } else if (LIST_ITEM.test(line)) {
            const ordered = /^\d/.test(line.match(LIST_ITEM)[1]);
            const items = [];
            while (at < lines.length && lines[at].trim()) {
                const item = lines[at].match(LIST_ITEM);
                if (item) {
                    items.push(item[2]);
                } else if (startsBlock(at)) {
                    break;
                } else {
                    // a line that goes on with the item before it
                    items[items.length - 1] += " " + lines[at].trim();
                }
                at++;
            }
            const tag = ordered ? "ol" : "ul";
            out.push(`<${tag}>${items.map((item) => `<li>${inline(item)}</li>`).join("")}</${tag}>`);
        } else {
            const paragraph = [];
            while (at < lines.length && lines[at].trim() && (paragraph.length === 0 || !startsBlock(at))) {
                paragraph.push(lines[at++].trim());
            }
            out.push(`<p>${inline(paragraph.join(" "))}</p>`);
        }
    }
    return out.join("\n");
}
