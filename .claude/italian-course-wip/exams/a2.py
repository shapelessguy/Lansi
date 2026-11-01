from lib import listening, module, part, reading, text, write

ORAL = "Scriva come parlerebbe."

write(
    "A2",
    "CELI 1 (A2)",
    61,
    [
        "Famiglia e rapporti",
        "Abitare e cercare casa",
        "Cibo e ristoranti",
        "Negozi e acquisti",
        "Lavoro e studio",
        "Tempo libero e sport",
        "Feste e tradizioni",
        "Vacanze e viaggi",
        "Trasporti in città",
        "Salute e medico",
        "Servizi: banca, posta, uffici",
        "Ricordi e esperienze",
    ],
    [
        module("reading", "Comprensione della lettura", [
            part(
                "Prova A.1", "comprehension", reading(1), 4, 8, 4,
                "Legga i testi. Per ogni testo scelga l'immagine giusta: a o b.",
                "A short text of two or three lines, such as a notice, a short message or an advert, and two pictures, a and b, described in a few words each in place of the picture. Both show the same kind of thing; only one fits the text. The prompt is the text; the two options are the pictures.",
                text("", "", [
                    ("Cerco una bicicletta da bambino, usata ma in buono stato, per mio figlio di sei anni. Telefonare a Marta, 333 4512789.", [
                        "a) Una piccola bicicletta rossa con le rotelle.",
                        "b) Una bicicletta da corsa grande e nuova.",
                    ], 0),
                ]),
            ),
            part(
                "Prova A.2", "comprehension", reading(5, "match"), 1, 10, 5,
                "Legga i testi. Abbini ogni testo all'immagine giusta. Ci sono più immagini del necessario.",
                "Five short texts of two to four lines, numbered, such as adverts or descriptions of places, things or people, and a list of seven pictures, described in a few words each, shown as the list to match. Each question is one of the texts; its options are the seven pictures, the same for every question.",
                text("", "1. Appartamento al terzo piano, con balcone e vista sul parco.\n2. Si vende divano in pelle, tre posti, colore marrone.\n3. Ristorante di pesce sul porto, aperto anche a pranzo.", [
                    ("Testo 1", ["A. un palazzo con balconi davanti a un parco", "B. un divano marrone", "C. una trattoria sul mare", "D. una camera d'albergo", "E. un letto matrimoniale"], 0),
                    ("Testo 2", ["A. un palazzo con balconi davanti a un parco", "B. un divano marrone", "C. una trattoria sul mare", "D. una camera d'albergo", "E. un letto matrimoniale"], 1),
                    ("Testo 3", ["A. un palazzo con balconi davanti a un parco", "B. un divano marrone", "C. una trattoria sul mare", "D. una camera d'albergo", "E. un letto matrimoniale"], 2),
                ], shown="A. un palazzo con balconi davanti a un parco · B. un divano marrone · C. una trattoria sul mare · D. una camera d'albergo · E. un letto matrimoniale"),
            ),
            part(
                "Prova A.3", "comprehension", reading(7, "match"), 1, 10, 7,
                "Unisca le due parti delle frasi. Abbini ogni inizio alla fine giusta.",
                "Seven beginnings of everyday sentences, the questions, and a list of their ends, shown, with one more than needed. Each end fits one beginning only, by its meaning and its grammar, such as a preposition, an agreement or a tense. The options of each question are the ends, the same for every question.",
                text("", "Unisca l'inizio di ogni frase con la sua fine.", [
                    ("Ogni mattina mi alzo", ["a. alle sette e faccio colazione.", "b. perché ho perso il treno.", "c. con i miei amici al mare."], 0),
                    ("Ieri sono arrivato tardi", ["a. alle sette e faccio colazione.", "b. perché ho perso il treno.", "c. con i miei amici al mare."], 1),
                    ("D'estate vado in vacanza", ["a. alle sette e faccio colazione.", "b. perché ho perso il treno.", "c. con i miei amici al mare."], 2),
                ], shown="a. alle sette e faccio colazione. · b. perché ho perso il treno. · c. con i miei amici al mare."),
            ),
            part(
                "Prova A.4", "comprehension", reading(7, "match"), 1, 12, 7,
                "Legga le domande e le risposte. Abbini ogni domanda alla risposta giusta.",
                "A short interview or conversation, such as with a shop assistant, a new neighbour or a hotel receptionist, cut into seven questions and their answers. The questions are the prompts; the answers are the list shown, mixed, with one more than needed, and are the options of every question.",
                text("Al telefono con l'albergo", "Un cliente telefona a un albergo per prenotare una camera.", [
                    ("Avete una camera doppia per il fine settimana?", ["a. Sì, è compresa nel prezzo.", "b. Sì, ce n'è ancora una libera.", "c. Novanta euro a notte."], 1),
                    ("Quanto costa?", ["a. Sì, è compresa nel prezzo.", "b. Sì, ce n'è ancora una libera.", "c. Novanta euro a notte."], 2),
                    ("E la colazione?", ["a. Sì, è compresa nel prezzo.", "b. Sì, ce n'è ancora una libera.", "c. Novanta euro a notte."], 0),
                ], shown="a. Sì, è compresa nel prezzo. · b. Sì, ce n'è ancora una libera. · c. Novanta euro a notte."),
            ),
            part(
                "Prova A.5", "comprehension", reading(1), 5, 15, 10,
                "Legga i testi e risponda alle domande. Scelga la risposta giusta: a, b o c.",
                "A short text of 40 to 70 words, such as an email, a notice, a short article or a page of a website, with one question on its main fact or purpose. The three options are all close to the text, and only one is what it says.",
                text("Avviso nel condominio", "Gentili condomini, giovedì 12 marzo, dalle 8 alle 13, manca l'acqua in tutto il palazzo per lavori. Vi consigliamo di prendere l'acqua la sera prima. L'ascensore funziona normalmente. Grazie per la comprensione. L'amministratore", [
                    ("Che cosa succede giovedì mattina?", [
                        "L'ascensore non funziona.",
                        "Nel palazzo non c'è acqua.",
                        "L'amministratore fa una riunione.",
                    ], 1),
                ]),
            ),
        ]),
        module("writing", "Produzione di testi scritti", [
            part(
                "Prova B.1", "writing", {"kind": "form"}, 1, 20, 10,
                "Legga il testo. Completi il modulo con le informazioni del testo.",
                "A short text of five to seven sentences about a person who signs up for something, such as a gym, a course, a library or a trip, and a form of up to ten fields for the facts the text gives: names, a date, an address, a number of people, a way to pay, a choice between two. Each answer is a word or a short group of words.",
                {
                    "text": "Mi chiamo Ahmed Benali, sono nato il 3 maggio 1995 e abito a Torino, in via Garibaldi 18. Vorrei iscrivermi al corso di nuoto del martedì e del giovedì sera. Lavoro tutto il giorno, quindi preferisco le 19. Pago con la carta di credito.",
                    "fields": [
                        {"label": "Cognome:", "answer": "Benali"},
                        {"label": "Data di nascita:", "answer": "3 maggio 1995"},
                        {"label": "Indirizzo:", "answer": "via Garibaldi 18, Torino"},
                        {"label": "Corso:", "answer": "nuoto"},
                        {"label": "Giorni:", "answer": "martedì e giovedì"},
                        {"label": "Orario (mattina / sera):", "answer": "sera"},
                        {"label": "Pagamento (contanti / carta):", "answer": "carta"},
                    ],
                },
            ),
            part(
                "Prova B.2", "writing", {"kind": "message", "words": 80}, 1, 45, 10,
                "Scriva un breve testo (circa 80 parole) seguendo la traccia. Scriva a tutti i punti.",
                "A situation of one or two sentences in which the learner writes to a friend about something they did or will do, such as a weekend, a party, a new home or a holiday, with four points to write about, as the outline to expand: what, where, with whom, and an impression or a plan. The past tense is often needed.",
                {
                    "situation": "Lo scorso fine settimana è stato in una città che non conosceva. Scriva un'email a un'amica, Chiara.",
                    "points": [
                        "Dove è andato e con chi?",
                        "Che cosa ha visto?",
                        "Che cosa le è piaciuto di più?",
                        "Inviti Chiara a venire con Lei la prossima volta.",
                    ],
                },
            ),
        ]),
        module("listening", "Comprensione dell'ascolto", [
            part(
                "Prova C.1", "comprehension", listening(1, plays="2", text="dialogue"), 5, 6, 10,
                "Ascolti i dialoghi. Ascolta ogni dialogo due volte. Scelga la risposta giusta: a o b.",
                "Short everyday dialogues of four to six turns, with the speakers named, such as Donna, Uomo, Commesso. The question asks for one fact the dialogue gives, a time, a price, a place or a thing; both options are said in it, and only one is what the speakers agree on.",
                text("", "Donna: Scusi, quanto costano queste scarpe?\nCommesso: Sessanta euro, ma oggi c'è lo sconto del venti per cento.\nDonna: Allora quarantotto euro?\nCommesso: Esatto, quarantotto.", [
                    ("Quanto paga la donna?", ["48 euro.", "60 euro."], 0),
                ]),
            ),
            part(
                "Prova C.2", "comprehension", listening(6, "match", plays="2"), 1, 4, 6,
                "Ascolti i testi. Ascolta ogni testo due volte. Abbini ogni testo all'immagine giusta.",
                "Six short monologues of two or three sentences, numbered in one text, each of a person saying what they do, buy, want or where they are, and a list of seven pictures, described in a few words each, shown. Each question is one of the monologues; its options are the pictures.",
                text("", "1. Prendo sempre l'autobus numero 5 per andare in ufficio.\n2. Oggi compro un chilo di mele e del formaggio.\n3. La domenica gioco a tennis con mio fratello.", [
                    ("Testo 1", ["A. un autobus in città", "B. un banco del mercato", "C. un campo da tennis", "D. una piscina"], 0),
                    ("Testo 2", ["A. un autobus in città", "B. un banco del mercato", "C. un campo da tennis", "D. una piscina"], 1),
                    ("Testo 3", ["A. un autobus in città", "B. un banco del mercato", "C. un campo da tennis", "D. una piscina"], 2),
                ], shown="A. un autobus in città · B. un banco del mercato · C. un campo da tennis · D. una piscina"),
            ),
            part(
                "Prova C.3", "comprehension", listening(10, "yesno", plays="2"), 1, 6, 10,
                "Ascolti cinque brevi testi. Ascolta i testi due volte. Le informazioni della lista sono nei testi? Scelga: Sì o No.",
                "Five short monologues, one after another in the text, each of a person speaking of their day, home, work or holidays, of three or four sentences, with the name of who speaks. The statements are a list of facts; each is or is not said by one of them.",
                text("", "Laura: Lavoro in una farmacia vicino alla stazione. Comincio alle otto e finisco alle quattro.\nGiorgio: Abito in campagna con mia moglie e due cani. Vado in città solo il sabato.", [
                    ("Laura lavora vicino alla stazione.", [], 0),
                    ("Laura finisce di lavorare alle sei.", [], 1),
                    ("Giorgio ha due cani.", [], 0),
                    ("Giorgio va in città ogni giorno.", [], 1),
                ]),
            ),
            part(
                "Prova C.4", "comprehension", listening(1, plays="2"), 5, 4, 5,
                "Ascolti i testi. Ascolta ogni testo due volte. Scelga la risposta giusta: a o b.",
                "Short monologues of two to four sentences, such as a message on the phone, an announcement or a person telling a plan. The question asks for one fact; the two options are both likely.",
                text("", "Ciao Elena, sono Matteo. Stasera non posso venire al cinema, devo lavorare fino a tardi. Possiamo andare domani alle nove?", [
                    ("Quando vuole andare al cinema Matteo?", ["Stasera.", "Domani sera."], 1),
                ]),
            ),
        ]),
        module("speaking", "Produzione orale", [
            part(
                "Prova 1", "oral", {"kind": "introduce", "prompts": 3}, 1, 3, 10,
                "Si presenti e risponda alle domande dell'esaminatore. " + ORAL,
                "A short conversation in which the learner introduces themselves and gives simple facts about their life: family, home, work or study, free time. The card lists the points; the first prompt asks for the introduction, the others are questions of the examiner on it.",
                {
                    "card": "Nome · Paese e città · Famiglia · Lavoro o studio · Tempo libero",
                    "prompts": [
                        "Si presenti, per favore.",
                        "Con chi abita?",
                        "Che cosa fa nel fine settimana?",
                    ],
                },
            ),
            part(
                "Prova 2", "oral", {"kind": "talk", "prompts": 2}, 1, 3, 15,
                "Guardi le vignette e racconti che cosa succede. " + ORAL,
                "A sequence of four pictures that tell a short everyday story, described in words on the card in place of the pictures: getting up late, missing the bus, running, arriving in time. The first prompt asks the learner to tell the story, the second a question about it or about their own life.",
                {
                    "card": "Vignetta 1: Anna dorme, la sveglia segna le 8. · Vignetta 2: Anna corre alla fermata, l'autobus parte. · Vignetta 3: Anna prende un taxi. · Vignetta 4: Anna arriva in ufficio, i colleghi sorridono.",
                    "prompts": [
                        "Racconti la storia di Anna.",
                        "E a Lei è mai successo di arrivare in ritardo?",
                    ],
                },
            ),
            part(
                "Prova 3", "oral", {"kind": "requests", "prompts": 3}, 1, 3, 15,
                "Role play. Legga la situazione e parli con l'esaminatore. " + ORAL,
                "A role play in an everyday situation, set by a picture that is not to be described: at a ticket office, in a shop, at the doctor's, at a hotel. The card says who the learner is and what they want; the prompts are the turns of the examiner, who plays the other person.",
                {
                    "card": "Lei è alla stazione e vuole comprare un biglietto per Napoli per domani mattina. Chieda l'orario, il prezzo e il binario.",
                    "prompts": [
                        "Buongiorno, mi dica.",
                        "C'è un treno alle 7 e uno alle 9. Quale preferisce?",
                        "Sono 45 euro. Paga in contanti o con la carta?",
                    ],
                },
            ),
        ]),
    ],
)
