from lib import listening, module, part, reading, text, write

ORAL = "Scriva come parlerebbe."

write(
    "A1",
    "CELI Impatto (A1)",
    50,
    [
        "Famiglia e amici",
        "La casa",
        "Mangiare e bere",
        "Fare la spesa",
        "Il lavoro",
        "Il tempo libero",
        "Orari, giorni e appuntamenti",
        "Viaggi e mezzi di trasporto",
        "Il tempo atmosferico",
        "Il corpo e la salute",
        "La scuola e il corso",
        "La città",
    ],
    [
        module("reading", "Comprensione della lettura", [
            part(
                "Prova A.1", "comprehension", reading(4, "truefalse"), 1, 10, 4,
                "Legga il testo. Poi legga le frasi e scelga: Vero o Falso.",
                "One short personal text of 50 to 70 words, such as a postcard, a note or a message in which someone tells about themselves, their family or their day, in the present tense and with everyday words. Each statement takes up one fact of the text, rightly or with one detail changed, in other words than the text.",
                text("Una cartolina", "Cara Giulia,\nsono a Rimini con la mia famiglia. L'albergo è piccolo ma molto carino ed è vicino al mare. La mattina andiamo in spiaggia e il pomeriggio facciamo una passeggiata in centro. Mio fratello Marco gioca a pallavolo con i ragazzi dell'albergo. Torniamo a Milano sabato.\nUn abbraccio,\nSara", [
                    ("Sara è in vacanza con la famiglia.", [], 0),
                    ("L'albergo è lontano dal mare.", [], 1),
                    ("Il pomeriggio Sara va in spiaggia.", [], 1),
                    ("Sara torna a casa sabato.", [], 0),
                ]),
            ),
            part(
                "Prova A.2", "comprehension", reading(1), 8, 15, 4,
                "Legga i testi. Per ogni testo scelga l'immagine giusta: a o b.",
                "A short text of one or two lines, such as a sign, a notice, an advert, a timetable or an instruction, and two pictures, a and b, described in a few words each in place of the picture. Both pictures are of the same kind of thing, and only one fits what the text says. The prompt is the text; the two options are the pictures.",
                text("", "", [
                    ("CHIUSO PER FERIE dal 10 al 24 agosto. Il negozio riapre lunedì 25.", [
                        "a) Una porta di negozio chiusa con un cartello sulle vacanze.",
                        "b) Una porta di negozio aperta con un cartello sugli sconti.",
                    ], 0),
                ]),
            ),
        ]),
        module("writing", "Produzione di testi scritti", [
            part(
                "Prova B.1", "writing", {"kind": "form"}, 1, 20, 4,
                "Legga la scheda. Completi il testo con le parole giuste.",
                "A card with facts about a person, such as their name, age, town, job, family and what they like, and a short text in which that person introduces themselves, with eight gaps. Each field is a part of the text with its gap, as ___, and its answer is the one word, or a short group of words, the card says goes there.",
                {
                    "text": "Nome: Lucia Ferri · Età: 28 anni · Città: Bologna · Lavoro: infermiera · Famiglia: sposata, un figlio · Sport: nuoto",
                    "fields": [
                        {"label": "Ciao! Mi chiamo ___ Ferri.", "answer": "Lucia"},
                        {"label": "Ho ___ anni.", "answer": "28"},
                        {"label": "Abito a ___.", "answer": "Bologna"},
                        {"label": "Faccio l'___ in un ospedale.", "answer": "infermiera"},
                        {"label": "Sono ___ e ho un figlio.", "answer": "sposata"},
                        {"label": "Il mio sport preferito è il ___.", "answer": "nuoto"},
                    ],
                },
            ),
            part(
                "Prova B.2", "writing", {"kind": "message", "words": 20}, 1, 25, 4,
                "Scriva una cartolina (15-20 parole). Scriva a tutti i punti. Non dimentichi il saluto all'inizio e alla fine.",
                "A situation of one sentence in which the learner is on holiday or away and writes a postcard to a friend, and three points to write about, such as where they are, what the weather or the place is like, and what they do. The points are short and in the present tense.",
                {
                    "situation": "È in vacanza al mare. Scriva una cartolina a un amico, Paolo.",
                    "points": [
                        "Dove è?",
                        "Com'è il tempo?",
                        "Che cosa fa ogni giorno?",
                    ],
                },
            ),
        ]),
        module("listening", "Comprensione dell'ascolto", [
            part(
                "Prova 1", "comprehension", listening(1), 6, 5, 4,
                "Ascolti le domande e le richieste dell'esaminatore. Ascolta ogni testo due volte. Scelga la risposta giusta: a, b o c.",
                "A question or a request of one or two sentences that the examiner says to the learner, as in the oral exam: where they come from, to show or give a thing, to say a number, a time or a colour. The question asks which answer or reaction is right; the options are three short answers, of which only one fits.",
                text("", "Scusi, che ore sono? Ha un orologio?", [
                    ("Che cosa risponde?", [
                        "Sono di Roma.",
                        "Sono le dieci e mezza.",
                        "Ho venti anni.",
                    ], 1),
                ]),
            ),
            part(
                "Prova 2", "comprehension", listening(1, plays="2", text="announcement"), 3, 4, 4,
                "Ascolti tre brevi annunci. Ascolta ogni annuncio due volte. Scelga la risposta giusta: a, b o c.",
                "Short announcements of two or three sentences, as heard at a station, in a supermarket, at school or on the radio, with a time, a place, a platform or a price. The question asks for one fact; the three options are of the same kind and all likely.",
                text("", "Attenzione, il treno regionale per Firenze delle ore 10 e 15 parte dal binario 4, e non dal binario 2. Ripetiamo: binario 4.", [
                    ("Da quale binario parte il treno per Firenze?", [
                        "Dal binario 2.",
                        "Dal binario 4.",
                        "Dal binario 10.",
                    ], 1),
                ]),
            ),
        ]),
        module("speaking", "Produzione orale", [
            part(
                "Prova 1", "oral", {"kind": "introduce", "prompts": 1}, 1, 2, 4,
                "Si presenti. " + ORAL,
                "The learner introduces themselves in a short monologue. The card lists the points to speak about; the one prompt asks them to say something on every point.",
                {
                    "card": "Nome? · Età? · Paese? · Città? · Lingue? · Lavoro o studio? · Tempo libero?",
                    "prompts": ["Parli di sé: dica qualcosa su tutti i punti."],
                },
                sized=False,
            ),
            part(
                "Prova 2", "oral", {"kind": "talk", "prompts": 3}, 1, 3, 6,
                "Guardi la foto e risponda alle domande dell'esaminatore. " + ORAL,
                "A photo of an everyday scene, described in words on the card in place of the picture: a family at the table, a market, a street, a beach. The prompts are simple questions of the examiner about the photo and about the learner's own life on the same theme.",
                {
                    "card": "Foto: una famiglia mangia insieme in cucina. Ci sono un papà, una mamma e due bambini. Sul tavolo ci sono pasta, pane e frutta.",
                    "prompts": [
                        "Che cosa vede nella foto?",
                        "Che cosa mangiano?",
                        "E Lei, con chi mangia di solito?",
                    ],
                },
            ),
            part(
                "Prova 3", "oral", {"kind": "requests", "prompts": 3}, 1, 2, 6,
                "Ascolti tre brevi annunci e risponda alle domande dell'esaminatore. " + ORAL,
                "Three short notices or announcements, each of one or two sentences, that the examiner reads, on the card; each prompt asks a short question about one of them that the learner answers in a few words.",
                {
                    "card": "1. Il museo è aperto dal martedì alla domenica, dalle 9 alle 19. · 2. Oggi al bar: cappuccino e cornetto a 2 euro. · 3. La lezione di yoga è alle 18 nella sala grande.",
                    "prompts": [
                        "Il museo è aperto il lunedì?",
                        "Quanto costano cappuccino e cornetto?",
                        "A che ora è la lezione di yoga?",
                    ],
                },
            ),
        ]),
    ],
)
