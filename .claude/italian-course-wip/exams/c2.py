from lib import listening, module, part, reading, text, write

ORAL = "Scriva come parlerebbe."

write(
    "C2",
    "CELI 5 (C2)",
    59,
    [
        "Etica del lavoro e futuro delle professioni",
        "Sapere, scuola e cultura umanistica",
        "Corpo, salute e bioetica",
        "Crisi climatica e responsabilità",
        "Identità, appartenenza e cittadinanza",
        "Potere dei media e opinione pubblica",
        "Globalizzazione e economie locali",
        "Memoria storica e patrimonio",
        "Giustizia, legalità e istituzioni",
        "Scienza, tecnologia e limiti umani",
        "Letteratura, arte e lingua italiana",
        "Felicità, tempo e stili di vita",
    ],
    [
        module("reading", "Comprensione della lettura e competenza linguistica", [
            part(
                "Prova A.1", "comprehension", reading(5, text="article"), 2, 30, 15,
                "Legga i testi e risponda alle domande. Scelga la risposta giusta: a, b, c o d.",
                "A text of 550 to 700 words of high register, such as an essay, a literary page, an editorial or a piece of criticism, with five questions on its argument, its irony or tone, the meaning of an image or an idiom in context, and what the writer implies without saying. The four options are subtle; the wrong ones are a literal reading, half true or the opposite nuance.",
                text("Elogio della noia", "C'è stato un tempo in cui ci si annoiava. Le domeniche pomeriggio d'estate, le attese dal medico, i lunghi viaggi in treno senza altro da fare che guardare fuori dal finestrino. Oggi quel tempo vuoto è stato colonizzato: ogni minuto libero è un'occasione per scorrere, rispondere, aggiornarsi. Non sarò io a rimpiangere ingenuamente un passato che aveva i suoi difetti; mi limito a osservare che la noia, come la terra lasciata a riposo, era il luogo in cui germogliavano le idee.", [
                    ("Che cosa intende l'autore con «colonizzato»?", [
                        "Che il tempo libero è aumentato.",
                        "Che il tempo vuoto è stato occupato da attività continue.",
                        "Che si viaggia di più all'estero.",
                        "Che le domeniche sono più noiose.",
                    ], 1),
                    ("Quale atteggiamento assume l'autore verso il passato?", [
                        "Lo rimpiange senza riserve.",
                        "Lo condanna del tutto.",
                        "Ne riconosce i limiti, ma ne apprezza un aspetto.",
                        "Non ne parla.",
                    ], 2),
                ]),
            ),
            part(
                "Prova A.2", "comprehension", reading(5, text="article"), 1, 15, 15,
                "Legga il testo e risponda alle domande. Scelga la risposta giusta: a, b, c o d.",
                "An essay or an article of 500 to 600 words, with five questions that ask for the reasoning, the purpose of a passage or the writer's stance, as open questions would. The four options paraphrase it closely; only one renders its full meaning. In the real exam the answers are open.",
                text("La lingua che cambia", "Ogni generazione denuncia il declino della lingua: i giovani non sanno più scrivere, il congiuntivo muore, gli anglicismi invadono tutto. Eppure la storia dell'italiano è fatta di continui prestiti e semplificazioni, e la lingua di Manzoni appariva, ai puristi del suo tempo, sciatta e troppo vicina al parlato. Ciò non significa che ogni cambiamento sia neutro: significa piuttosto che il giudizio va sospeso finché non si distingue l'evoluzione dall'impoverimento.", [
                    ("Perché l'autore cita Manzoni?", [
                        "Per mostrare che anche lui usava molti anglicismi.",
                        "Per dimostrare che ciò che oggi è modello fu criticato come trascuratezza.",
                        "Per affermare che la sua lingua era povera.",
                        "Per invitare a scrivere come lui.",
                    ], 1),
                ]),
            ),
            part(
                "Prova C.1", "comprehension", reading(10, text="article"), 1, 18, 5,
                "Legga il testo e lo completi. Per ogni spazio numerato scelga la parola giusta: a, b, c o d.",
                "A text of 300 to 350 words in a formal or literary register with ten numbered gaps, (1) to (10), in the text, for connectors, prepositions, pronouns, idioms and fixed phrases. Each question is the number of a gap with four options of the same kind, all plausible to a learner. The real exam has thirteen gaps, open.",
                text("", "La riforma, (1) ___ da più parti come necessaria, ha incontrato fin da subito forti resistenze. Non (2) ___ la prima volta che un governo tenta di intervenire sul tema; tuttavia, mai prima d'ora si era arrivati (3) ___ un passo dall'approvazione.", [
                    ("(1)", ["invocata", "invocando", "invocante", "invocasse"], 0),
                    ("(2)", ["è", "sia", "fosse", "sarebbe"], 0),
                    ("(3)", ["a", "di", "da", "in"], 0),
                ]),
            ),
            part(
                "Prova C.2", "comprehension", reading(10, text="article"), 1, 18, 5,
                "Legga il testo. Per ogni spazio numerato scelga la forma giusta del verbo indicato: a, b, c o d.",
                "A narrative or argumentative text of 250 to 300 words with ten numbered gaps, (1) to (10), each with the infinitive of a verb in brackets, to be put in the right tense and mood: subjunctive after conjunctions and verbs of feeling, conditional past of the future in the past, remote past in narration, concordance of tenses. Each question is the number with the verb; the four options are forms of it. In the real exam the learner writes the forms.",
                text("", "Quando mia nonna (1) (arrivare) ___ a Torino, nel 1956, non conosceva nessuno. Pensava che la città (2) (essere) ___ fredda e ostile, e invece trovò subito lavoro. Mi raccontò che, se non (3) (incontrare) ___ mio nonno, (4) (tornare) ___ in Calabria.", [
                    ("(1) arrivare", ["arrivava", "arrivò", "sarebbe arrivata", "arrivi"], 1),
                    ("(2) essere", ["era", "sia", "fosse", "sarà"], 2),
                    ("(3) incontrare", ["avesse incontrato", "aveva incontrato", "incontrasse", "avrebbe incontrato"], 0),
                    ("(4) tornare", ["tornerebbe", "sarebbe tornata", "fosse tornata", "tornava"], 1),
                ]),
            ),
            part(
                "Prova C.3", "comprehension", reading(10, text="message"), 1, 20, 5,
                "Nel testo ci sono degli errori. Per ogni parte numerata scelga la forma corretta: a, b, c o d.",
                "A text of 250 to 300 words, such as a formal letter, a report or a review, in which ten numbered words or phrases, marked (1) to (10), are wrong: a mood, a concordance of tenses, a pronoun, a preposition, a wrong word or register. Each question is the number with the wrong form; the four options are corrections, none of them the wrong form again, and one right. In the real exam the learner finds and corrects fourteen errors.",
                text("", "Egregio Direttore,\nmi permetto di scriverLe in merito all'articolo apparso ieri, (1) per cui si sostiene che i giovani non leggono. Credo che l'autore (2) ha generalizzato in modo eccessivo: i dati che (3) gli ho consultato dicono altro.", [
                    ("(1) per cui → ?", ["nel quale", "il quale", "che", "di cui"], 0),
                    ("(2) ha generalizzato → ?", ["generalizzasse", "abbia generalizzato", "generalizzerebbe", "avrà generalizzato"], 1),
                    ("(3) gli ho consultato → ?", ["ne ho consultato", "ho consultato", "li ho consultati", "le ho consultati"], 1),
                ]),
            ),
            part(
                "Prova C.4", "comprehension", reading(10, text="article"), 1, 19, 5,
                "Legga il testo e lo completi. Per ogni spazio numerato scelga la risposta giusta: a, b, c o d.",
                "A text of 300 to 350 words with ten numbered gaps, (1) to (10), for words of meaning rather than grammar: the precise verb, noun or adjective, a collocation, an idiom or a connector of the right register. Each question is the number of a gap with four options close in meaning, of which one fits the context. The real exam has twelve.",
                text("", "Il nuovo romanzo di Bianchi ha (1) ___ un vivace dibattito tra i critici. Alcuni lo considerano un'opera di (2) ___, altri lo giudicano una semplice operazione commerciale. Resta il fatto che, a un mese dall'uscita, il libro ha già (3) ___ le centomila copie.", [
                    ("(1)", ["suscitato", "eccitato", "commosso", "agitato"], 0),
                    ("(2)", ["pesantezza", "spessore", "densità", "grossezza"], 1),
                    ("(3)", ["superato", "oltrepassato di", "vinto", "ecceduto a"], 0),
                ]),
            ),
        ]),
        module("writing", "Produzione di testi scritti", [
            part(
                "Prova B.1", "writing", {"kind": "essay", "words": 350}, 1, 75, 35,
                "Scriva una composizione (330-360 parole) su uno dei tre argomenti proposti.",
                "Three themes to choose from, given in the situation: a report or an essay on a question of society or culture, a short story of invention, or an account of personal experiences, also in relation to aspects of Italian culture. The points are what the text must do: take a clear stance or build a story, develop it with depth and nuance, and conclude.",
                {
                    "situation": "Scelga uno dei tre argomenti. A) «Il progresso tecnologico ci ha reso più liberi o più dipendenti?» Scriva un saggio. B) Scriva un racconto che cominci con la frase: «Quella mattina il treno non si fermò alla solita stazione.» C) Descriva un aspetto della cultura italiana che L'ha sorpresa e rifletta sul perché.",
                    "points": [
                        "Presenti il tema o la situazione iniziale.",
                        "Sviluppi il testo con argomenti, esempi o eventi ben collegati.",
                        "Usi un registro adatto al tipo di testo.",
                        "Concluda in modo efficace.",
                    ],
                },
            ),
            part(
                "Prova B.2", "writing", {"kind": "email", "words": 180}, 1, 45, 25,
                "Scriva due lettere o email formali collegate (circa 180 parole in tutto): la prima e la risposta alla prima.",
                "A situation with a clear aim and addressees, in which the learner writes a formal letter or email and then the reply to it in the role of the addressee, such as a complaint to a company and the company's answer, or a request to an institution and its reply. The points say what each must contain.",
                {
                    "situation": "Lei è il presidente di un'associazione culturale e scrive all'assessore alla cultura del Comune per chiedere l'uso gratuito di una sala per un ciclo di conferenze. Poi scriva la risposta dell'assessore.",
                    "points": [
                        "Prima lettera: presenti l'associazione e il progetto.",
                        "Prima lettera: formuli la richiesta e la motivi.",
                        "Risposta: accetti a certe condizioni o rifiuti, spiegando perché.",
                        "Risposta: proponga un incontro o un'alternativa.",
                    ],
                },
            ),
        ]),
        module("listening", "Comprensione dell'ascolto", [
            part(
                "Prova D.1", "comprehension", listening(5, text="interview"), 2, 12, 30,
                "Ascolti i testi. Ascolta ogni testo due volte. Risponda alle domande scegliendo la risposta giusta: a, b, c o d.",
                "An interview, a debate or a lecture of the radio of 500 to 600 words, at natural speed, on a matter of culture, science or society, with five questions on the speakers' views, their reasons, what they imply and their tone. The four options are close and use words heard.",
                text("", "Conduttore: Professor Conti, Lei sostiene che la memoria collettiva sia sempre una costruzione. Che cosa intende?\nConti: Che nessuna comunità ricorda il passato così com'è stato. Ricorda ciò che le serve per raccontarsi: sceglie, omette, a volte inventa. Pensi alle feste nazionali: celebrano un evento, ma ne lasciano in ombra altri, magari altrettanto decisivi ma più scomodi.", [
                    ("Secondo Conti, la memoria collettiva…", [
                        "riproduce fedelmente gli eventi.",
                        "seleziona il passato in funzione dell'identità presente.",
                        "dipende soltanto dagli storici.",
                        "cancella le feste nazionali.",
                    ], 1),
                ]),
            ),
            part(
                "Prova D.2", "comprehension", listening(10, "yesno", text="interview"), 1, 9, 10,
                "Ascolti il testo. Lo ascolta due volte. Le affermazioni sono presenti nel testo? Scelga: Sì o No.",
                "A discussion of the radio of 500 to 600 words among two or three speakers, with ten statements of what is or is not said, often of a nuance of a view; the absent ones are close and likely. The real exam has eleven.",
                text("", "Moderatrice: Il turismo enogastronomico salva i borghi o li trasforma in vetrine? Ne parliamo con la sindaca Marta Lodi e con il sociologo Ivo Sarti.\nLodi: Nel nostro comune ha portato lavoro: sono nate dodici aziende agricole in cinque anni.\nSarti: Non lo nego. Ma il rischio è che il paese viva tre mesi l'anno e resti vuoto per gli altri nove.", [
                    ("Secondo la sindaca, sono nate nuove aziende agricole.", [], 0),
                    ("Il sociologo nega che il turismo abbia portato lavoro.", [], 1),
                    ("Il sociologo teme una vita del paese limitata ad alcuni mesi.", [], 0),
                ]),
            ),
            part(
                "Prova D.3", "comprehension", listening(10, text="announcement"), 1, 9, 10,
                "Ascolti il testo. Lo ascolta due volte. Completi le frasi scegliendo l'informazione giusta: a, b, c o d.",
                "A lecture, a report or a presentation of 450 to 550 words full of facts and reasoning, with ten sentences in the order of the text, each ending in a gap, as the prompts. The four options are close; one is what is said. In the real exam the learner writes the words.",
                text("", "La Biblioteca Malatestiana di Cesena, inaugurata nel 1454, è la prima biblioteca civica d'Europa: apparteneva non al signore della città, ma al Comune, che ne garantiva la conservazione. Ancora oggi i codici sono incatenati ai banchi originali, come voleva Malatesta Novello. Dal 2005 è iscritta nel registro della Memoria del mondo dell'UNESCO.", [
                    ("La biblioteca fu inaugurata nel ___", ["1405.", "1454.", "1545.", "2005."], 1),
                    ("La biblioteca apparteneva ___", ["al signore della città.", "alla Chiesa.", "al Comune.", "all'UNESCO."], 2),
                ]),
            ),
        ]),
        module("speaking", "Produzione orale", [
            part(
                "Prova 1", "oral", {"kind": "present", "prompts": 3}, 1, 7, 17,
                "Descriva la foto e ne parli con l'esaminatore. " + ORAL,
                "A photo, described in words on the card in place of the picture, that opens an abstract theme, such as an empty piazza at dawn, a crowded museum or a protest. The first prompt asks the learner to describe and interpret it; the others are questions of the examiner that go deeper.",
                {
                    "card": "Foto: in una sala del Louvre, decine di visitatori fotografano la Gioconda con lo smartphone; quasi nessuno guarda il quadro direttamente.",
                    "prompts": [
                        "Descriva e interpreti la foto.",
                        "Che cosa ci dice questa scena del nostro rapporto con l'arte?",
                        "Crede che la tecnologia possa avvicinare il pubblico ai musei?",
                    ],
                },
            ),
            part(
                "Prova 2", "oral", {"kind": "discuss", "prompts": 3}, 1, 7, 17,
                "Riassuma il testo e ne discuta con l'esaminatore. " + ORAL,
                "A text of 250 to 300 words of an essay or an editorial, on the card, on a matter of culture or society. The first prompt asks the learner to sum it up; the others are questions of the examiner that challenge their view and ask for nuance.",
                {
                    "card": "Testo: Si dice spesso che viviamo nell'epoca della post-verità: i fatti contano meno delle emozioni, e ciascuno sceglie le notizie che confermano ciò che già pensa. Ma è davvero una novità? Già nel Seicento le gazzette erano piene di notizie false. Forse ciò che è cambiato non è la natura dell'informazione, ma la velocità con cui circola e la difficoltà di sapere chi ne è responsabile.",
                    "prompts": [
                        "Riassuma il testo.",
                        "È d'accordo con la tesi dell'autore?",
                        "Chi dovrebbe essere responsabile della qualità dell'informazione?",
                    ],
                },
            ),
            part(
                "Prova 3", "oral", {"kind": "discuss", "prompts": 2}, 1, 6, 16,
                "Commenti l'espressione o la massima e ne discuta con l'esaminatore. " + ORAL,
                "A saying, a proverb or a quotation of an Italian or a European writer, on the card, to explain and comment. The first prompt asks what it means and what the learner thinks of it; the second is a question of the examiner that challenges it.",
                {
                    "card": "«Chi va piano va sano e va lontano.» (proverbio)",
                    "prompts": [
                        "Che cosa significa questo proverbio? È d'accordo?",
                        "In un mondo che premia la velocità, è ancora un buon consiglio?",
                    ],
                },
            ),
        ]),
    ],
)
