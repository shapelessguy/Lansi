from lib import listening, module, part, reading, text, write

ORAL = "Scriva come parlerebbe."

write(
    "B1",
    "CELI 2 (B1)",
    59,
    [
        "Lavoro e colleghi",
        "Scuola, università e corsi",
        "Salute e benessere",
        "Ambiente e natura",
        "Città e campagna",
        "Mezzi di comunicazione e internet",
        "Consumi e pubblicità",
        "Viaggi e turismo",
        "Feste, tradizioni e cucina italiana",
        "Amicizia e vita in famiglia",
        "Sport e tempo libero",
        "Volontariato e vita di quartiere",
    ],
    [
        module("reading", "Comprensione della lettura", [
            part(
                "Prova A.1", "comprehension", reading(1, text="any"), 7, 20, 14,
                "Legga i testi e risponda alle domande. Scelga la risposta giusta: a, b o c.",
                "A short text of 60 to 100 words, such as an email, an advert, a notice, the page of a website or a short news item, with one question on its purpose or a key fact. The three options are all close to the text; the wrong ones take up its words with a different meaning.",
                text("Biblioteca comunale", "Da lunedì 3 ottobre la biblioteca cambia orario: sarà aperta dal lunedì al venerdì dalle 9 alle 19 e il sabato solo la mattina. Il prestito dei libri è gratuito per tutti i residenti; chi non abita in città deve pagare una quota di 10 euro all'anno. Per i bambini sotto i 12 anni ci sono letture ad alta voce ogni mercoledì pomeriggio.", [
                    ("Che cosa devono fare le persone che non abitano in città?", [
                        "Venire solo il sabato mattina.",
                        "Pagare per prendere in prestito i libri.",
                        "Portare i bambini il mercoledì.",
                    ], 1),
                ]),
            ),
            part(
                "Prova A.2", "comprehension", reading(10, "yesno", text="article"), 1, 15, 10,
                "Legga il testo. Poi legga le affermazioni. Le informazioni sono presenti nel testo? Scelga: Sì o No.",
                "A text of 250 to 300 words, such as an article of a magazine or a story of someone's experience, on a theme of everyday life. Ten statements; each is or is not said in the text, in other words than the text's, and those that are not said are likely ones that the text leaves out or says otherwise.",
                text("Un anno in Sicilia", "Quando Katrin è arrivata a Palermo da Monaco, non parlava una parola di italiano. Lavorava come ingegnere e la sua azienda l'aveva mandata a seguire un progetto per un anno. «All'inizio era difficile: al mercato tutti parlavano velocemente e io capivo solo i numeri», racconta. Dopo tre mesi ha cominciato un corso serale e ha trovato una coinquilina siciliana che le ha insegnato a cucinare la caponata. Oggi Katrin vive ancora a Palermo: il progetto è finito, ma lei ha deciso di restare e lavora per una ditta locale.", [
                    ("Katrin è andata a Palermo per lavoro.", [], 0),
                    ("Katrin aveva già studiato italiano in Germania.", [], 1),
                    ("Katrin ha frequentato un corso di sera.", [], 0),
                    ("Katrin è tornata a Monaco dopo un anno.", [], 1),
                ]),
            ),
            part(
                "Prova A.3", "comprehension", reading(5), 1, 8, 5,
                "Completi le frasi. Scelga la parola o l'espressione giusta: a, b, c o d.",
                "Five separate sentences of everyday life, each with a gap, ___, as the prompts; the text only says to complete them. The four options of each are words of the same kind, such as prepositions, pronouns, verb forms or connectors, and only one fits by grammar and meaning.",
                text("", "Completi ogni frase con la parola giusta.", [
                    ("Se domani piove, ___ a casa e guardiamo un film.", ["restiamo", "restavamo", "restassimo", "restati"], 0),
                    ("Ho incontrato Paola e ___ ho dato il tuo numero.", ["la", "le", "gli", "lo"], 1),
                ]),
            ),
            part(
                "Prova A.4", "comprehension", reading(10, text="message"), 1, 12, 10,
                "Legga il testo e lo completi. Per ogni spazio scelga la parola giusta: a, b o c.",
                "A text of 150 to 200 words, such as an email to a friend or a short article, with ten numbered gaps, (1) to (10), in the text. Each question is the number of a gap; its three options are words of the same kind, of which one fits by grammar and meaning: articles, prepositions, pronouns, verb forms, connectors.",
                text("", "Cara Silvia,\nscusa (1) ___ non ti ho scritto prima, ma questo mese sono stata molto impegnata. (2) ___ settimana scorsa ho cominciato il nuovo lavoro in banca. I colleghi sono gentili e (3) ___ ufficio è vicino a casa mia.", [
                    ("(1)", ["perché", "se", "quando"], 0),
                    ("(2)", ["Il", "La", "Lo"], 1),
                    ("(3)", ["l'", "il", "lo"], 0),
                ]),
            ),
            part(
                "Prova A.5", "comprehension", reading(5), 1, 8, 5,
                "Completi le frasi con le informazioni del testo. Scelga la risposta giusta: a, b o c.",
                "A short text of 100 to 150 words, such as a notice or a short article, and five sentences about it, each ending in a gap, as the prompts. The three options are short endings, all words of the text; one completes the sentence as the text says. In the real exam the gaps are open; here they are chosen.",
                text("Corso di fotografia", "L'associazione Obiettivo organizza un corso di fotografia per principianti. Le lezioni si tengono ogni giovedì dalle 20 alle 22, da ottobre a dicembre, nella sala del centro civico. È necessario avere una macchina fotografica, anche semplice; non serve il computer. Il corso costa 80 euro e alla fine ci sarà una mostra con le foto dei partecipanti.", [
                    ("Le lezioni sono il ___", ["martedì.", "giovedì.", "sabato."], 1),
                    ("Alla fine del corso c'è ___", ["un esame.", "una festa.", "una mostra."], 2),
                ]),
            ),
        ]),
        module("writing", "Produzione di testi scritti", [
            part(
                "Prova B.1", "writing", {"kind": "form"}, 1, 15, 5,
                "Legga il testo. Risponda alle domande del questionario con le informazioni del testo.",
                "A text of five to eight sentences in which a person tells about their habits on a theme of general interest, such as reading, sport, travel or the use of the internet, and a questionnaire of up to nine questions on it. Each answer is a short phrase the text gives. In the real exam the learner answers about themselves; here the answers come from the text.",
                {
                    "text": "Mi chiamo Davide e ho 34 anni. Leggo molto, soprattutto gialli, e compro i libri in libreria perché non mi piace leggere sullo schermo. Leggo di solito la sera prima di dormire, circa un'ora. Il mio scrittore preferito è Andrea Camilleri. Una volta al mese vado a un gruppo di lettura in biblioteca.",
                    "fields": [
                        {"label": "Che genere di libri legge?", "answer": "gialli"},
                        {"label": "Dove compra i libri?", "answer": "in libreria"},
                        {"label": "Quando legge?", "answer": "la sera, prima di dormire"},
                        {"label": "Per quanto tempo?", "answer": "circa un'ora"},
                        {"label": "Scrittore preferito:", "answer": "Andrea Camilleri"},
                        {"label": "Quante volte va al gruppo di lettura?", "answer": "una volta al mese"},
                    ],
                },
            ),
            part(
                "Prova B.2", "writing", {"kind": "message", "words": 50}, 1, 25, 15,
                "Scriva un breve annuncio (circa 50 parole), oppure risponda all'annuncio. Scriva a tutti i punti.",
                "A short advert or notice on a matter of everyday life, given in the situation, such as someone selling a bike, looking for a flatmate or offering lessons, to write or to answer; three points to write about.",
                {
                    "situation": "Sul sito del Suo quartiere ha letto questo annuncio: «Studente cerca persona per scambio di conversazione italiano-inglese, due ore alla settimana». Risponda all'annuncio.",
                    "points": [
                        "Si presenti brevemente.",
                        "Dica perché l'annuncio La interessa.",
                        "Proponga un giorno e un luogo per incontrarvi.",
                    ],
                },
            ),
            part(
                "Prova B.3", "writing", {"kind": "email", "words": 100}, 1, 40, 20,
                "Scriva una lettera o un'email (90-100 parole) seguendo la traccia. Scriva a tutti i punti.",
                "A situation in which the learner writes a formal letter or email, to an office, a school, a company or a landlord, to ask, complain or explain, with three or four points to write about.",
                {
                    "situation": "Ha comprato online una lampada, ma è arrivata rotta. Scriva un'email al servizio clienti del negozio.",
                    "points": [
                        "Dica che cosa ha comprato e quando.",
                        "Descriva il problema.",
                        "Chieda di cambiare la lampada o di avere i soldi indietro.",
                        "Chieda quando avrà una risposta.",
                    ],
                },
            ),
        ]),
        module("listening", "Comprensione dell'ascolto", [
            part(
                "Prova C.1", "comprehension", listening(1, text="phone"), 4, 5, 8,
                "Ascolti i messaggi. Ascolta ogni messaggio due volte. Scelga la risposta giusta: a, b o c.",
                "Short messages left on the phone, of four to six sentences: who calls, what they want and when or where. The question asks for its purpose or a key fact; all options are said or likely.",
                text("", "Buongiorno, signora Rossi, sono Marina dello studio dentistico Bianchi. Purtroppo il dottore domani mattina non c'è, quindi dobbiamo spostare il suo appuntamento. Le va bene venerdì alle 15? Mi richiami, per favore, allo 06 4458921. Grazie.", [
                    ("Perché telefona Marina?", [
                        "Per cambiare un appuntamento.",
                        "Per chiedere un pagamento.",
                        "Per confermare la visita di domani.",
                    ], 0),
                ]),
            ),
            part(
                "Prova C.2", "comprehension", listening(1, text="announcement"), 4, 5, 8,
                "Ascolti le notizie. Ascolta ogni notizia due volte. Scelga la risposta giusta: a, b o c.",
                "Short news items or announcements of the radio, of four to six sentences: the weather, the traffic, an event in town, a change of a service. The question asks what is said; the options are close to each other.",
                text("", "Notizie dalla città. Questa domenica il centro storico sarà chiuso alle auto dalle 10 alle 18 per la festa dei fiori. Gli autobus delle linee 3 e 7 non passeranno per piazza Duomo, ma per viale Roma. Il parcheggio della stazione sarà gratuito tutto il giorno.", [
                    ("Che cosa succede domenica?", [
                        "Gli autobus sono gratis.",
                        "Le auto non possono entrare in centro.",
                        "Piazza Duomo è chiusa per lavori.",
                    ], 1),
                ]),
            ),
            part(
                "Prova C.3", "comprehension", listening(10, "yesno", text="interview"), 2, 10, 25,
                "Ascolti i testi. Ascolta ogni testo due volte. Le informazioni sono presenti nel testo? Scelga: Sì o No.",
                "An interview or a talk of the radio of 250 to 300 words, on a person's work, studies or a place, with ten statements; each is or is not said. The real exam has two texts with 25 statements in all.",
                text("", "Intervistatore: Signor Galli, Lei fa la guida in montagna da vent'anni. Come ha cominciato?\nGalli: Da ragazzo andavo in montagna con mio padre ogni estate. Poi ho studiato scienze naturali a Torino e, dopo la laurea, ho fatto il corso per diventare guida.\nIntervistatore: Che cosa le piace del suo lavoro?\nGalli: Conoscere persone diverse. D'inverno accompagno soprattutto stranieri a fare sci di fondo.", [
                    ("Galli andava in montagna con il padre.", [], 0),
                    ("Galli ha studiato medicina.", [], 1),
                    ("D'inverno Galli lavora soprattutto con stranieri.", [], 0),
                ]),
            ),
        ]),
        module("speaking", "Produzione orale", [
            part(
                "Prova 1", "oral", {"kind": "talk", "prompts": 4}, 1, 4, 13,
                "Conversazione con l'esaminatore. Si presenti e risponda alle domande. " + ORAL,
                "An interview in which the learner introduces themselves and speaks of matters of their own life, such as their work, studies, home town, habits or plans. The first prompt asks them to introduce themselves; the others are questions of the examiner that ask for reasons and experiences.",
                {
                    "card": "Conversazione: Lei, la Sua città, il lavoro o lo studio, i Suoi progetti",
                    "prompts": [
                        "Si presenti, per favore.",
                        "Che cosa le piace della città dove abita?",
                        "Perché studia l'italiano?",
                        "Che progetti ha per l'estate?",
                    ],
                },
            ),
            part(
                "Prova 2", "oral", {"kind": "present", "prompts": 2}, 1, 4, 13,
                "Descriva la foto e risponda alle domande dell'esaminatore. " + ORAL,
                "A photo of a scene of everyday life, described in words on the card in place of the picture, such as people at a market, a family moving house or students in a library. The first prompt asks the learner to describe it and say what happens; the second is a question of the examiner on the theme.",
                {
                    "card": "Foto: in un parco, alcune persone di età diverse puliscono il prato e raccolgono la plastica in grandi sacchi. Un bambino aiuta la nonna.",
                    "prompts": [
                        "Descriva la foto: chi sono queste persone e che cosa fanno?",
                        "Nella Sua città ci sono iniziative di questo tipo?",
                    ],
                },
            ),
            part(
                "Prova 3", "oral", {"kind": "requests", "prompts": 3}, 1, 4, 14,
                "Role play. Legga la situazione e parli con l'esaminatore. " + ORAL,
                "A role play in a situation of everyday life, set by a picture that is not to be described: a complaint in a shop, a booking, asking for information at an office, settling something with a neighbour. The card says who the learner is and what they want; the prompts are the turns of the examiner.",
                {
                    "card": "Lei è in un albergo. La camera è rumorosa e il riscaldamento non funziona. Parli con il receptionist e chieda una soluzione.",
                    "prompts": [
                        "Buonasera, posso aiutarLa?",
                        "Mi dispiace. Purtroppo stasera l'albergo è pieno. Che cosa possiamo fare?",
                        "Domani possiamo darLe un'altra camera. Le va bene?",
                    ],
                },
            ),
        ]),
    ],
)
