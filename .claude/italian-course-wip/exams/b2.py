from lib import listening, module, part, reading, text, write

ORAL = "Scriva come parlerebbe."
AB = ["Testo A", "Testo B"]

write(
    "B2",
    "CELI 3 (B2)",
    59,
    [
        "Il mondo del lavoro",
        "Istruzione e formazione",
        "Salute e stili di vita",
        "Ambiente e sostenibilità",
        "Vivere in città o in provincia",
        "Media, social network e informazione",
        "Consumi e pubblicità",
        "Turismo e patrimonio culturale",
        "Società e convivenza",
        "Scienza e tecnologia",
        "Arte, cinema e musica",
        "Generazioni e famiglia",
    ],
    [
        module("reading", "Comprensione della lettura e competenza linguistica", [
            part(
                "Prova A.1", "comprehension", reading(5, text="article"), 2, 30, 22,
                "Legga i testi e risponda alle domande. Scelga la risposta giusta: a, b, c o d.",
                "An article of 300 to 400 words from a newspaper or a magazine, on a matter of society, work or culture, with five questions in the order of the text, on its main idea, the view of the writer or of the people quoted, and details. The four options are all close to the text; the wrong ones are half true or say what the text does not. The real exam has two texts with five and four questions.",
                text("Il ritorno dei negozi di quartiere", "Per anni si è detto che i piccoli negozi sarebbero scomparsi, schiacciati dai centri commerciali e dagli acquisti online. Eppure, in molte città italiane, la tendenza sembra cambiare. A Bologna, nel quartiere Bolognina, negli ultimi due anni hanno aperto una libreria, una bottega di prodotti sfusi e un laboratorio di riparazione di biciclette. «La gente ha voglia di relazioni, non solo di prezzi bassi», spiega Elisa Monti, che gestisce la libreria. Secondo un'indagine della Camera di commercio, però, il fenomeno resta limitato: i nuovi negozi sono spesso aperti da giovani con poca esperienza e uno su tre chiude entro tre anni.", [
                    ("Che cosa sostiene l'articolo all'inizio?", [
                        "I piccoli negozi sono già scomparsi.",
                        "Si pensava che i piccoli negozi non avessero futuro.",
                        "I centri commerciali stanno chiudendo.",
                        "Gli acquisti online sono diminuiti.",
                    ], 1),
                    ("Secondo Elisa Monti, i clienti cercano soprattutto…", [
                        "prezzi più bassi.",
                        "prodotti sfusi.",
                        "contatti umani.",
                        "negozi grandi.",
                    ], 2),
                    ("Che cosa dice l'indagine della Camera di commercio?", [
                        "Che i nuovi negozi hanno molto successo.",
                        "Che molti nuovi negozi non durano a lungo.",
                        "Che i giovani non vogliono aprire negozi.",
                        "Che il fenomeno riguarda solo Bologna.",
                    ], 1),
                ]),
            ),
            part(
                "Prova A.2", "comprehension", reading(10, "match", text="article"), 1, 20, 8,
                "Legga i due testi. Poi legga le affermazioni e indichi a quale testo si riferiscono: Testo A o Testo B.",
                "Two texts of 150 to 200 words each, A and B, on the same theme from two points of view, such as two people telling how they work from home, or two reviews of the same place, given in the text with their letters. Ten statements, each true of one text only; the options of each are Testo A and Testo B.",
                text("Lavorare da casa", "Testo A – Marco, programmatore: Da quando lavoro da casa risparmio due ore al giorno di viaggio. Ho più tempo per i miei figli e sono più concentrato, perché in ufficio c'era sempre rumore. L'unico problema è che a volte non riesco a smettere di lavorare la sera.\nTesto B – Federica, grafica: Ho provato a lavorare da casa per sei mesi, ma mi mancavano i colleghi. Le idee migliori nascono parlando davanti alla macchinetta del caffè. Adesso vado in ufficio tre giorni a settimana e sono molto più contenta.", [
                    ("Questa persona ha bisogno del contatto con i colleghi.", AB, 1),
                    ("Questa persona fa fatica a separare lavoro e vita privata.", AB, 0),
                    ("Questa persona ha cambiato organizzazione dopo un periodo di prova.", AB, 1),
                    ("Questa persona lavora meglio nel silenzio.", AB, 0),
                ]),
            ),
            part(
                "Prova A.3", "comprehension", reading(4, text="article"), 1, 10, 10,
                "Legga il testo e risponda alle domande. Scelga la risposta giusta: a, b, c o d.",
                "A text of 250 to 300 words, such as an article or a page of a guide, with four questions that ask why, how or what follows from it, as open questions would; the options are four answers in other words than the text's, of which one says what it means. In the real exam the answers are open.",
                text("Lo spreco alimentare", "In Italia ogni famiglia butta via in media circa 30 chili di cibo all'anno. Il motivo più frequente non è la cattiva qualità dei prodotti, ma la cattiva organizzazione: si compra troppo, senza una lista, e si dimenticano gli alimenti in fondo al frigorifero. Alcuni comuni hanno avviato corsi gratuiti per insegnare a conservare e riutilizzare gli avanzi.", [
                    ("Perché, secondo il testo, si spreca tanto cibo?", [
                        "Perché i prodotti sono di bassa qualità.",
                        "Perché la spesa è fatta senza programmare.",
                        "Perché i frigoriferi sono troppo piccoli.",
                        "Perché il cibo costa poco.",
                    ], 1),
                ]),
            ),
            part(
                "Prova C.1", "comprehension", reading(10, text="article"), 2, 25, 12,
                "Legga il testo e lo completi. Per ogni spazio numerato scelga la parola giusta: a, b, c o d.",
                "A text of 200 to 250 words with ten numbered gaps, (1) to (10), in the text; the gaps take articles, prepositions, pronouns, connectors and verb forms in the tense and mood the sentence asks for, such as a subjunctive after a verb of opinion. Each question is the number of a gap with four options of the same kind. The real exam has two texts with 23 gaps, to fill in without options.",
                text("", "Molti pensano che la bicicletta (1) ___ un mezzo adatto solo all'estate. In realtà, (2) ___ si veste in modo adeguato, si può pedalare tutto l'anno. A Ferrara, per esempio, quasi un abitante su tre va al lavoro in bici, (3) ___ quando piove.", [
                    ("(1)", ["è", "sia", "sarà", "fosse"], 1),
                    ("(2)", ["benché", "se", "affinché", "quindi"], 1),
                    ("(3)", ["anche", "invece", "perciò", "magari"], 0),
                ]),
            ),
            part(
                "Prova C.2", "comprehension", reading(7, "match"), 1, 12, 5,
                "Ricostruisca le frasi. Abbini ogni prima parte alla seconda parte giusta.",
                "Seven beginnings of sentences, the prompts, and their ends, the list shown, each end starting with a connector, such as sebbene, purché, dal momento che, tanto che, nel caso in cui; one end only fits each beginning by its meaning and by the mood of its verb. The options of every question are the ends. In the real exam the learner joins two sentences into one.",
                text("", "Unisca le due parti di ogni frase.", [
                    ("Ti presto la macchina", ["a. sebbene non avesse studiato molto.", "b. purché tu me la riporti stasera.", "c. tanto che ha dovuto chiamare un tecnico."], 1),
                    ("Ha superato l'esame", ["a. sebbene non avesse studiato molto.", "b. purché tu me la riporti stasera.", "c. tanto che ha dovuto chiamare un tecnico."], 0),
                    ("Il computer era così lento", ["a. sebbene non avesse studiato molto.", "b. purché tu me la riporti stasera.", "c. tanto che ha dovuto chiamare un tecnico."], 2),
                ], shown="a. sebbene non avesse studiato molto. · b. purché tu me la riporti stasera. · c. tanto che ha dovuto chiamare un tecnico."),
            ),
            part(
                "Prova C.3", "comprehension", reading(5), 1, 8, 3,
                "Completi le frasi con la parola giusta, formata dalla parola tra parentesi. Scelga: a, b, c o d.",
                "Five separate sentences, each with a gap and a word in brackets, as the prompts; the gap takes a word made from it, such as a noun from a verb, an adjective from a noun or an adverb from an adjective. The four options are words of the same family, of which one fits. In the real exam the learner writes the word.",
                text("", "Completi ogni frase con la forma giusta della parola tra parentesi.", [
                    ("La ___ del nuovo ponte è durata tre anni. (costruire)", ["costruttore", "costruzione", "costruttivo", "costruito"], 1),
                    ("Ha risposto ___ a tutte le domande. (tranquillo)", ["tranquillità", "tranquillizzare", "tranquillamente", "tranquillo"], 2),
                ]),
            ),
        ]),
        module("writing", "Produzione di testi scritti", [
            part(
                "Prova B.1", "writing", {"kind": "opinion", "words": 150}, 1, 45, 20,
                "Scriva una breve composizione (120-180 parole) su uno dei due argomenti proposti.",
                "Two themes to choose from, given in the situation: personal experiences, situations, or matters of general interest, such as a trip that changed one's ideas, the use of the smartphone among young people, or living abroad. The points are what to tell or argue, with an example and the learner's own view.",
                {
                    "situation": "Scelga uno dei due argomenti. A) Racconti un'esperienza che L'ha fatta cambiare idea su qualcosa. B) Secondo Lei, è meglio vivere in una grande città o in un piccolo paese?",
                    "points": [
                        "Presenti l'argomento scelto.",
                        "Racconti un'esperienza o porti degli esempi.",
                        "Esprima e motivi la Sua opinione.",
                    ],
                },
            ),
            part(
                "Prova B.2", "writing", {"kind": "email", "words": 90}, 1, 30, 20,
                "Scriva una lettera o un'email (80-100 parole) su una delle situazioni proposte.",
                "A situation with a clear aim and addressee, to ask for or give information or advice, to complain or to give an opinion, such as writing to a newspaper, a school, a company or an acquaintance; three points to write about. The real exam lets the learner choose among three.",
                {
                    "situation": "Ha letto sul giornale locale che il Comune vuole chiudere la piscina pubblica del Suo quartiere. Scriva una lettera al direttore del giornale.",
                    "points": [
                        "Spieghi perché la piscina è importante per il quartiere.",
                        "Esprima la Sua opinione sulla decisione del Comune.",
                        "Proponga un'alternativa.",
                    ],
                },
            ),
        ]),
        module("listening", "Comprensione dell'ascolto", [
            part(
                "Prova D.1", "comprehension", listening(5, text="interview"), 2, 14, 30,
                "Ascolti i testi. Ascolta ogni testo due volte. Risponda alle domande scegliendo la risposta giusta: a, b, c o d.",
                "An interview or a programme of the radio of 300 to 400 words, on a matter of society, work, culture or science, with five questions in the order of what is said. The four options are close to each other and use words of the text.",
                text("", "Conduttrice: Oggi parliamo di orti urbani con Paolo Neri, agronomo. Paolo, perché a Milano ce ne sono sempre di più?\nNeri: Prima di tutto per ragioni sociali. Chi coltiva un orto in città lo fa raramente per risparmiare: lo fa per stare all'aria aperta e conoscere i vicini. Poi c'è il tema ambientale: un orto è uno spazio verde in più.\nConduttrice: E chi può averne uno?\nNeri: Il Comune assegna i terreni con un bando ogni due anni. Hanno la precedenza i pensionati e le scuole.", [
                    ("Secondo Neri, perché le persone coltivano un orto in città?", [
                        "Soprattutto per risparmiare sulla spesa.",
                        "Per passare tempo fuori e fare conoscenze.",
                        "Perché il Comune lo chiede.",
                        "Per vendere i prodotti.",
                    ], 1),
                    ("Chi ha la precedenza nell'assegnazione dei terreni?", [
                        "Le famiglie con bambini.",
                        "Gli agronomi.",
                        "I pensionati e le scuole.",
                        "Chi abita vicino all'orto.",
                    ], 2),
                ]),
            ),
            part(
                "Prova D.2", "comprehension", listening(10, text="announcement"), 1, 11, 10,
                "Ascolti il testo. Lo ascolta due volte. Completi le frasi scegliendo l'informazione giusta: a, b o c.",
                "A report, a guided tour or an announcement of 250 to 300 words with many facts, such as times, places, numbers and names. Ten sentences in the order of the text, each ending with a gap, as the prompts; the three options are what the text says and two near it. In the real exam the learner writes the words heard.",
                text("", "Benvenuti al Museo del Novecento. La visita guidata dura circa un'ora e mezza e comincia al secondo piano, dove si trovano le opere del Futurismo. Vi ricordiamo che è vietato fotografare con il flash. Alla fine della visita potete salire sulla terrazza, da cui si vede tutta piazza del Duomo. Il bar del museo chiude alle 18.", [
                    ("La visita dura circa ___", ["un'ora.", "un'ora e mezza.", "due ore."], 1),
                    ("Le opere del Futurismo sono ___", ["al primo piano.", "al secondo piano.", "sulla terrazza."], 1),
                    ("Il bar chiude ___", ["alle 17.", "alle 18.", "alle 19."], 1),
                ]),
            ),
        ]),
        module("speaking", "Produzione orale", [
            part(
                "Prova 1", "oral", {"kind": "present", "prompts": 3}, 1, 5, 20,
                "Descriva la foto e ne parli con l'esaminatore. " + ORAL,
                "A photo, described in words on the card in place of the picture, of a scene that opens a theme of society, such as commuters on a crowded train, a farmers' market or a classroom with tablets. The first prompt asks the learner to describe it; the others are questions of the examiner that take the theme further.",
                {
                    "card": "Foto: un gruppo di anziani in una sala di un centro civico segue un corso di computer; una ragazza giovane li aiuta.",
                    "prompts": [
                        "Descriva la foto.",
                        "Secondo Lei, perché molti anziani vogliono imparare a usare il computer?",
                        "Nel Suo Paese ci sono iniziative simili?",
                    ],
                },
            ),
            part(
                "Prova 2", "oral", {"kind": "discuss", "prompts": 3}, 1, 5, 20,
                "Riassuma il testo e ne discuta con l'esaminatore. " + ORAL,
                "A short text of 120 to 150 words on a matter of society, on the card, such as a news item on the four-day week or on cities without cars. The first prompt asks the learner to sum it up; the others are questions of the examiner that ask for their view and reasons.",
                {
                    "card": "Testo: In alcune aziende italiane si sperimenta la settimana corta: si lavora quattro giorni invece di cinque, con lo stesso stipendio. I primi risultati mostrano che i dipendenti sono meno stressati e che la produttività non è diminuita. Alcuni economisti, però, temono che il modello non sia applicabile a tutti i settori, per esempio alla sanità o ai negozi.",
                    "prompts": [
                        "Riassuma il testo con parole Sue.",
                        "Che cosa pensa della settimana corta?",
                        "In quali lavori sarebbe difficile applicarla?",
                    ],
                },
            ),
            part(
                "Prova 3", "oral", {"kind": "requests", "prompts": 3}, 1, 5, 20,
                "Role play. Legga la situazione e parli con l'esaminatore. " + ORAL,
                "A role play in a clearly set situation in which the learner must reach an aim, such as complaining about a service, asking for a change at work or persuading someone. The card says who the learner and the examiner are and what the learner wants; the prompts are the examiner's turns, who resists at first.",
                {
                    "card": "Lei ha prenotato un viaggio organizzato, ma l'agenzia ha cambiato l'albergo con uno più lontano dal centro. Parli con l'impiegato dell'agenzia e chieda un rimborso o un'altra soluzione.",
                    "prompts": [
                        "Buongiorno, in che cosa posso esserLe utile?",
                        "Capisco, ma l'albergo è della stessa categoria. Non possiamo rimborsarLa.",
                        "Potrei offrirLe un'escursione gratuita. Che ne dice?",
                    ],
                },
            ),
        ]),
    ],
)
