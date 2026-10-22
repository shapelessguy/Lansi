// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { afterEach, describe, expect, it } from "vitest";

import { setInterfaceLanguage } from "./i18n";
import {
    countWords,
    describeUses,
    detailRows,
    formsOf,
    type FormTables,
    groupWords,
    labelOf,
    layOutForms,
    listWords,
    shownIn,
    translationRow,
    type Vocabulary,
    type VocabularyEntry,
    type WordForm,
} from "./vocabulary";

afterEach(() => setInterfaceLanguage("English"));

const unused = { created_at: "2026-10-13 12:00:00", used: 0, seen: 0, first_used: null, last_used: null };

const vocabulary: Vocabulary = {
    categories: ["noun", "verb", "adjective"],
    details: {},
    labels: {},
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

    it("names the attributes, and the values they are limited to, in the language of the interface", () => {
        setInterfaceLanguage("Italian");
        const names = {
            details: { meanings: [], reflexive: ["never", "always"], genders: [], article: ["der"] },
            labels: {
                meanings: { Italian: "significati" },
                reflexive: { Italian: "riflessivo" },
                always: { Italian: "sempre" },
                article: { Italian: "articolo" },
                der: {},
            },
        };

        const rows = detailRows({
            meanings: ["always"],
            reflexive: "always",
            genders: [{ article: "der", meanings: ["dog"] }],
            zu_infinitive: "zu gehen",
        }, names);

        expect(rows).toEqual([
            { label: "significati", value: "always" },
            { label: "riflessivo", value: "sempre" },
            { label: "genders", value: "articolo: der · significati: dog" },
            { label: "zu infinitive", value: "zu gehen" },
        ]);
    });
});

describe("the variants of a word", () => {
    // die Bank, a bank with the plural Banken and a bench with Bänke
    const bank: Pick<VocabularyEntry, "variants" | "forms"> = {
        variants: [
            { id: 1, details: {}, translations: { English: ["bank"], Italian: ["banca"] } },
            { id: 2, details: {}, translations: { English: ["bench"] } },
        ],
        forms: [
            { id: 1, form: "Banken", tags: "die nominativ plural", variant: 1 },
            { id: 2, form: "Bänke", tags: "die nominativ plural", variant: 2 },
            { id: 3, form: "bank", tags: "", variant: 0 },
        ],
    };

    it("are translated into the language asked for, or else into one the word has", () => {
        expect(shownIn(bank, "Italian")).toBe("Italian");
        expect(shownIn(bank, "German")).toBe("English");
        expect(shownIn({ variants: [] }, "German")).toBe("German");
    });

    it("give their translations as a row, saying the language where it is not the one asked for", () => {
        expect(translationRow(bank.variants[0], "Italian", "Italian", {})).toEqual({
            label: "translations",
            value: "banca",
        });
        expect(translationRow(bank.variants[1], "English", "German", {})).toEqual({
            label: "translations",
            value: "bench",
            language: "English",
        });
        expect(translationRow(bank.variants[1], "Italian", "Italian", {})).toBeNull();
    });

    it("each have their own forms, and those of the whole word only where there is one variant", () => {
        expect(formsOf(bank, bank.variants[1]).map((form) => form.form)).toEqual(["Bänke"]);
        const alone = { variants: [bank.variants[0]], forms: bank.forms };
        expect(formsOf(alone, bank.variants[0]).map((form) => form.form)).toEqual(["Banken", "bank"]);
    });
});

describe("labelOf", () => {
    it("gives a name as it is where it has no text in the language of the interface", () => {
        setInterfaceLanguage("German");
        const labels = { noun: { German: "Substantiv" }, der: {} };

        expect([labelOf("noun", labels), labelOf("der", labels), labelOf("idiom", labels)]).toEqual([
            "Substantiv",
            "der",
            "idiom",
        ]);
    });
});

function forms(...pairs: [tags: string, form: string][]): WordForm[] {
    return pairs.map(([tags, form], index) => ({ id: index + 1, tags, form, variant: 0 }));
}

// tables of German, as the checker server tells them
const PERSONS = ["ich", "du", "er", "wir", "ihr", "sie"];
const CASES = ["nominativ", "genitiv", "dativ", "akkusativ"];
const NEBENSATZ = { tags: "{column} {row} nebensatz", title: "im Nebensatz" };
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
        groupWords({ categories: ["noun"], details: {}, labels: {}, tables: {}, words: [...words] }, "", sort)[0].words
            .map((word) => word.lemma);

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

describe("countWords", () => {
    it("counts the words spelt alike once, whatever their categories and capitals", () => {
        const words = [{ lemma: "der" }, { lemma: "der" }, { lemma: "Essen" }, { lemma: "essen" }, { lemma: "Hund" }];

        expect(countWords(words)).toBe(3);
    });
});
