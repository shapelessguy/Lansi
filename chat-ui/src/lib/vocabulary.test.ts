// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { describe, expect, it } from "vitest";

import {
    describeUses,
    detailRows,
    type FormTables,
    groupWords,
    layOutForms,
    listWords,
    type Vocabulary,
    type WordForm,
} from "./vocabulary";

const unused = { created_at: "2026-10-13 12:00:00", used: 0, seen: 0, first_used: null, last_used: null };

const vocabulary: Vocabulary = {
    categories: ["noun", "verb", "adjective"],
    tables: {},
    words: [
        { id: 3, category: "verb", lemma: "gehen", forms: 30, ...unused },
        { id: 1, category: "noun", lemma: "Apfel", forms: 6, ...unused },
        { id: 2, category: "noun", lemma: "Hund", forms: 5, ...unused },
    ],
};

describe("groupWords", () => {
    it("puts the words under their categories, in the order of the categories", () => {
        const groups = groupWords(vocabulary, "");

        expect(groups.map((group) => [group.category, group.words.map((word) => word.lemma)])).toEqual([
            ["noun", ["Apfel", "Hund"]],
            ["verb", ["gehen"]],
        ]);
    });

    it("keeps only the words that have the query in them, whatever its case", () => {
        const groups = groupWords(vocabulary, " HU ");

        expect(groups).toEqual([{ category: "noun", words: [vocabulary.words[2]] }]);
    });

    it("shows a category the server did not name after those it did", () => {
        const withAnother = {
            ...vocabulary,
            words: [{ id: 9, category: "idiom", lemma: "na ja", forms: 1, ...unused }, ...vocabulary.words],
        };

        expect(groupWords(withAnother, "").map((group) => group.category)).toEqual(["noun", "verb", "idiom"]);
    });
});

describe("detailRows", () => {
    it("gives each attribute as a row of text when it has a value", () => {
        const rows = detailRows({
            meanings: ["to go", "to walk"],
            auxiliary: "sein",
            separable: false,
            zu_infinitive: "zu gehen",
            uses: 3,
            note: "",
            cases: [],
        });

        expect(rows).toEqual([
            { label: "meanings", value: "to go, to walk" },
            { label: "auxiliary", value: "sein" },
            { label: "separable", value: "no" },
            { label: "zu infinitive", value: "zu gehen" },
            { label: "uses", value: "3" },
        ]);
    });

    it("gives a row to each of several things, such as the genders of a noun", () => {
        const rows = detailRows({
            genders: [
                { article: "der", meanings: ["volume"], plural: "Bände" },
                { article: "das", meanings: ["ribbon", "tape"], plural: "" },
            ],
        });

        expect(rows).toEqual([
            { label: "genders", value: "article: der · meanings: volume · plural: Bände" },
            { label: "genders", value: "article: das · meanings: ribbon, tape" },
        ]);
    });
});

function forms(...pairs: [tags: string, form: string][]): WordForm[] {
    return pairs.map(([tags, form], index) => ({ id: index + 1, tags, form }));
}

// tables of German, as the checker server tells them
const PERSONS = ["ich", "du", "er", "wir", "ihr", "sie"];
const CASES = ["nominativ", "genitiv", "dativ", "akkusativ"];
const NEBENSATZ = { tags: "{column} {row} nebensatz", title: "At the end of a subordinate clause" };
const TABLES: FormTables = {
    verb: [
        {
            title: "Indikativ",
            columns: ["präsens", "präteritum"],
            rows: PERSONS,
            tags: "{column} {row}",
            also: NEBENSATZ,
        },
        {
            title: "Konjunktiv",
            columns: ["konjunktiv I", "konjunktiv II"],
            rows: PERSONS,
            tags: "{column} {row}",
            also: NEBENSATZ,
        },
    ],
    noun: ["der", "die", "das"].map((article) => ({
        title: article,
        columns: ["singular", "plural"],
        rows: CASES,
        tags: `${article} {row} {column}`,
    })),
    adjective: [
        {
            title: "Endings",
            columns: ["positiv", "komparativ", "superlativ"],
            rows: ["-e", "-er", "-es", "-en", "-em"],
            tags: "{column} {row}",
        },
    ],
};

describe("layOutForms", () => {
    it("lays a verb out by person and tense, and lists its other forms", () => {
        const layout = layOutForms({
            category: "verb",
            lemma: "gehen",
            forms: forms(
                ["zu-infinitiv", "zu gehen"],
                ["präsens ich", "gehe"],
                ["präsens du", "gehst"],
                ["präteritum ich", "ging"],
                ["konjunktiv II ich", "ginge"],
                ["imperativ du", "geh"],
                ["", "gehen"],
            ),
        }, TABLES);

        expect(layout.tables.map((table) => [table.title, table.columns])).toEqual([
            ["Indikativ", ["präsens", "präteritum"]],
            ["Konjunktiv", ["konjunktiv I", "konjunktiv II"]],
        ]);
        const [indikativ, konjunktiv] = layout.tables;
        expect(indikativ.rows.map((row) => row.label)).toEqual(["ich", "du", "er", "wir", "ihr", "sie"]);
        expect(indikativ.rows[0].cells.map((cell) => cell.form)).toEqual(["gehe", "ging"]);
        expect(indikativ.rows[1].cells.map((cell) => cell.form)).toEqual(["gehst", ""]);
        expect(konjunktiv.rows[0].cells.map((cell) => cell.form)).toEqual(["", "ginge"]);
        expect(layout.others).toEqual([
            { label: "zu-infinitiv", form: "zu gehen" },
            { label: "imperativ du", form: "geh" },
            { label: "dictionary form", form: "gehen" },
        ]);
    });

    it("puts the form of a subordinate clause with the form it belongs to", () => {
        const layout = layOutForms({
            category: "verb",
            lemma: "anfangen",
            forms: forms(["präsens ich", "fange an"], ["präsens ich nebensatz", "anfange"]),
        }, TABLES);

        expect(layout.tables).toHaveLength(1);
        expect(layout.tables[0].rows[0].cells[0]).toEqual({ form: "fange an", also: "anfange" });
        expect(layout.others).toEqual([]);
    });

    it("lays a noun out by case and number, with a table for each gender it has", () => {
        const layout = layOutForms({
            category: "noun",
            lemma: "Band",
            forms: forms(
                ["der nominativ singular", "Band"],
                ["der dativ plural", "Bänden"],
                ["das dativ plural", "Bändern"],
            ),
        }, TABLES);

        expect(layout.tables.map((table) => table.title)).toEqual(["der", "das"]);
        expect(layout.tables[0].columns).toEqual(["singular", "plural"]);
        expect(layout.tables[0].rows.map((row) => row.label)).toEqual(["nominativ", "genitiv", "dativ", "akkusativ"]);
        expect(layout.tables[1].rows[2].cells.map((cell) => cell.form)).toEqual(["", "Bändern"]);
    });

    it("lays an adjective out by ending and degree", () => {
        const layout = layOutForms({
            category: "adjective",
            lemma: "hoch",
            forms: forms(["komparativ", "höher"], ["positiv -e", "hohe"], ["superlativ -en", "höchsten"]),
        }, TABLES);

        expect(layout.tables[0].columns).toEqual(["positiv", "komparativ", "superlativ"]);
        expect(layout.tables[0].rows[0].cells.map((cell) => cell.form)).toEqual(["hohe", "", ""]);
        expect(layout.tables[0].rows[3].cells[2].form).toBe("höchsten");
        expect(layout.others).toEqual([{ label: "komparativ", form: "höher" }]);
    });

    it("lists the forms of a word that has no tables", () => {
        const layout = layOutForms({
            category: "pronoun",
            lemma: "ich",
            forms: forms(["akkusativ", "mich"], ["", "ich"], ["", "meiner"]),
        }, TABLES);

        expect(layout.tables).toEqual([]);
        expect(layout.others).toEqual([
            { label: "akkusativ", form: "mich" },
            { label: "dictionary form", form: "ich" },
            { label: "–", form: "meiner" },
        ]);
    });
});

describe("describeUses", () => {
    it("says how often a word was used and seen, leaving out what it was not", () => {
        expect(describeUses({ used: 3, seen: 5 })).toBe("used 3× · seen 5×");
        expect(describeUses({ used: 0, seen: 2 })).toBe("seen 2×");
        expect(describeUses({ used: 1, seen: 0 })).toBe("used 1×");
        expect(describeUses({ used: 0, seen: 0 })).toBe("");
    });
});

describe("groupWords, in an order", () => {
    const words = [
        { ...unused, id: 1, category: "noun", lemma: "Hund", forms: 1, used: 2, seen: 1, last_used: 50 },
        { ...unused, id: 2, category: "noun", lemma: "Apfel", forms: 1, created_at: "2026-10-13 14:00:00" },
        { ...unused, id: 3, category: "noun", lemma: "Zug", forms: 1, used: 2, seen: 9, last_used: 90 },
        { ...unused, id: 4, category: "noun", lemma: "Ärger", forms: 1 },
    ];
    const lemmas = (sort: Parameters<typeof groupWords>[2]) =>
        groupWords({ categories: ["noun"], tables: {}, words: [...words] }, "", sort)[0].words.map((word) =>
            word.lemma
        );

    it("goes by the alphabet unless told otherwise, with ä next to a", () => {
        expect(lemmas(undefined)).toEqual(["Apfel", "Ärger", "Hund", "Zug"]);
    });

    it("puts the word stored last first", () => {
        expect(lemmas("newest")).toEqual(["Apfel", "Ärger", "Zug", "Hund"]);
    });

    it("puts the most used first, and words used as often by the alphabet", () => {
        expect(lemmas("used")).toEqual(["Hund", "Zug", "Apfel", "Ärger"]);
        expect(lemmas("seen")).toEqual(["Zug", "Hund", "Apfel", "Ärger"]);
    });

    it("puts the word used last first, and those never used at the end", () => {
        expect(lemmas("lastUsed")).toEqual(["Zug", "Hund", "Apfel", "Ärger"]);
    });
});

describe("listWords", () => {
    it("lists the words of every category together, by the alphabet", () => {
        expect(listWords(vocabulary, "").map((word) => word.lemma)).toEqual(["Apfel", "gehen", "Hund"]);
    });

    it("keeps to the words that match the filter", () => {
        expect(listWords(vocabulary, " E ").map((word) => word.lemma)).toEqual(["Apfel", "gehen"]);
    });
});
