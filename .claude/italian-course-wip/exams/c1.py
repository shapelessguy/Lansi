from lib import listening, module, part, reading, text, write

ORAL = "Scriva come parlerebbe."
AB = ["Testo A", "Testo B"]

write(
    "C1",
    "CELI 4 (C1)",
    59,
    [
        "Lavoro, precarietà e nuove professioni",
        "Scuola, università e merito",
        "Salute pubblica e medicina",
        "Clima, energia e territorio",
        "Migrazioni e identità",
        "Informazione, fake news e libertà di stampa",
        "Economia, consumi e disuguaglianze",
        "Patrimonio artistico e turismo di massa",
        "Diritti, istituzioni e partecipazione",
        "Innovazione, ricerca e intelligenza artificiale",
        "Letteratura, cinema e lingua italiana",
        "Invecchiamento e rapporti tra generazioni",
    ],
    [
        module("reading", "Comprensione della lettura e competenza linguistica", [
            part(
                "Prova A.1", "comprehension", reading(5, text="article"), 2, 30, 15,
                "Legga i testi e risponda alle domande. Scelga la risposta giusta: a, b, c o d.",
                "An article of 450 to 550 words from a newspaper, a magazine or an essay, on a matter of society, science or culture, written in a high register, with five questions on its argument, the stance of the writer, what a phrase means in context and what is implied. The four options are near each other; the wrong ones are half true, too strong or the view of someone quoted.",
                text("Il paradosso della lentezza", "Viviamo in un'epoca che celebra la velocità: consegne in giornata, risposte immediate, aggiornamenti continui. Eppure, da qualche anno, cresce il numero di chi rivendica il diritto alla lentezza. Non si tratta, come vorrebbero alcuni critici, di una moda per pochi privilegiati che possono permettersi di rallentare. Il movimento nato a Bra con lo Slow Food ha mostrato, anzi, che la lentezza può diventare un modello economico: piccoli produttori che rinunciano alla quantità per puntare sulla qualità, e che proprio per questo riescono a sopravvivere alla concorrenza globale.", [
                    ("Qual è la tesi principale dell'autore?", [
                        "La lentezza è un lusso per pochi.",
                        "La velocità è necessaria all'economia moderna.",
                        "Rallentare può essere anche una scelta economicamente valida.",
                        "Lo Slow Food è una moda passeggera.",
                    ], 2),
                    ("Che cosa pensa l'autore dei critici citati?", [
                        "Che hanno ragione.",
                        "Che la loro obiezione non regge.",
                        "Che sono piccoli produttori.",
                        "Che parlano solo di cibo.",
                    ], 1),
                ]),
            ),
            part(
                "Prova A.2", "comprehension", reading(4, text="article"), 1, 15, 10,
                "Legga il testo e risponda alle domande. Scelga la risposta giusta: a, b, c o d.",
                "An article or an essay of 400 to 500 words, with four questions that ask why, what the writer means or what follows, as open questions would. The four options say it in other words than the text's, and only one renders its meaning fully. In the real exam the answers are open.",
                text("Dialetti e scuola", "Per decenni la scuola italiana ha considerato il dialetto un ostacolo da eliminare: parlare italiano significava appartenere alla nazione. Oggi molti linguisti invitano a ripensare questa impostazione. Il bambino che parla dialetto in famiglia, sostengono, non ha una lingua di meno, ma una in più, e la riflessione sulle differenze tra i due codici può rafforzare la sua competenza in italiano.", [
                    ("Perché, secondo i linguisti citati, il dialetto può aiutare a scuola?", [
                        "Perché è più facile dell'italiano.",
                        "Perché confrontarlo con l'italiano sviluppa la consapevolezza linguistica.",
                        "Perché la famiglia lo preferisce.",
                        "Perché è la lingua della nazione.",
                    ], 1),
                ]),
            ),
            part(
                "Prova A.3", "comprehension", reading(10, "match", text="article"), 1, 20, 10,
                "Legga i due testi. Poi legga le affermazioni e indichi a quale testo si riferiscono: Testo A o Testo B.",
                "Two texts of 250 to 300 words each, A and B, on the same matter from opposed or different points of view, such as two editorials on tourism in historic cities, given in the text with their letters. Ten statements, each true of one text only, often of its reasoning rather than its facts; the options are Testo A and Testo B.",
                text("Il turismo nelle città d'arte", "Testo A: Il ticket d'ingresso a Venezia è una misura necessaria. Una città che conta meno di cinquantamila residenti non può accogliere ogni giorno decine di migliaia di visitatori senza perdere la propria identità. Il contributo serve a finanziare i servizi e a scoraggiare il turismo mordi e fuggi.\nTesto B: Far pagare l'ingresso a una città significa trasformarla definitivamente in un museo. Il problema non sono i turisti, ma la mancanza di politiche per la casa: i residenti se ne vanno perché gli affitti brevi rendono più delle locazioni tradizionali.", [
                    ("L'autore individua la causa del problema nel mercato degli affitti.", AB, 1),
                    ("L'autore ritiene che una tassa possa ridurre le visite brevi.", AB, 0),
                    ("L'autore teme che la città perda la sua vita normale a causa della misura.", AB, 1),
                ]),
            ),
            part(
                "Prova C.1", "comprehension", reading(10, text="article"), 1, 18, 7,
                "Legga il testo e lo completi. Per ogni spazio numerato scelga la parola giusta: a, b, c o d.",
                "A text of 250 to 300 words in a formal register with ten numbered gaps, (1) to (10), in the text; the gaps take connectors, relative pronouns, prepositions and verbs in the mood and tense the sentence asks for, including the subjunctive, the conditional and the passive. Each question is the number of a gap with four options of the same kind. The real exam has fourteen gaps, open.",
                text("", "Il progetto, (1) ___ obiettivo è ridurre il traffico in centro, è stato approvato ieri dal consiglio comunale. (2) ___ le proteste dei commercianti, la giunta ha deciso di procedere, a condizione che i lavori (3) ___ entro la fine dell'anno.", [
                    ("(1)", ["il cui", "che", "del quale il", "cui il"], 0),
                    ("(2)", ["Nonostante", "Sebbene", "Benché", "Malgrado che"], 0),
                    ("(3)", ["finiscono", "finiscano", "finirebbero", "finiranno"], 1),
                ]),
            ),
            part(
                "Prova C.2", "comprehension", reading(10, "match", text="article"), 1, 17, 7,
                "Legga il testo e lo completi. Per ogni spazio scelga dalla lista la parte mancante.",
                "A text of 250 to 300 words with ten numbered gaps, (1) to (10), each for a missing phrase or clause, and the list of the phrases shown, lettered, with two more than needed. Each question is the number of a gap; its options are the letters of the list.",
                text("", "La dieta mediterranea è stata riconosciuta dall'UNESCO (1) ___. Non si tratta soltanto di un modo di mangiare, (2) ___. Eppure, paradossalmente, proprio in Italia (3) ___.", [
                    ("(1)", ["a", "b", "c", "d"], 1),
                    ("(2)", ["a", "b", "c", "d"], 3),
                    ("(3)", ["a", "b", "c", "d"], 0),
                ], shown="a. i bambini sono tra i più sovrappeso d'Europa · b. come patrimonio immateriale dell'umanità · c. a causa dei prezzi troppo alti · d. ma di un insieme di pratiche sociali e culturali"),
            ),
            part(
                "Prova C.3", "comprehension", reading(10, text="message"), 1, 20, 7,
                "Nel testo ci sono degli errori. Per ogni parte numerata scelga la forma corretta: a, b, c o d.",
                "A text of 200 to 250 words, such as a formal letter or a report, in which ten numbered words or phrases, marked (1) to (10) in the text, are written wrongly: an agreement, a preposition, a pronoun, a mood or a tense, a connector. Each question is the number with the wrong form; the four options are corrections, of which one is right, and none is the wrong form again. In the real exam the learner finds and corrects fourteen errors.",
                text("", "Gentile direttore,\nLe scrivo (1) a segnalarLe un problema che ho avuto la settimana scorsa. Benché (2) ho prenotato con largo anticipo, all'arrivo mi è stato detto che la camera non era disponibile. Ho chiesto spiegazioni all'impiegata, ma (3) lui non mi ha risposto.", [
                    ("(1) a → ?", ["per", "di", "da", "con"], 0),
                    ("(2) ho prenotato → ?", ["avevo prenotato", "abbia prenotato", "prenotavo", "avrei prenotato"], 1),
                    ("(3) lui → ?", ["lei", "la", "le", "lo"], 0),
                ]),
            ),
            part(
                "Prova C.4", "comprehension", reading(10), 1, 20, 7,
                "Legga gli appunti. Per ogni appunto scelga la frase che lo sviluppa meglio nel testo: a, b, c o d.",
                "Ten notes of a few words each, in order, the outline of a short report or article, as the prompts; the text gives its theme. The four options of each are full sentences that expand the note, and only one is correct and joined coherently to what comes before, with the right connector, pronouns and mood. In the real exam the learner writes the text.",
                text("Relazione: il volontariato giovanile", "Appunti per una breve relazione sul volontariato tra i giovani.", [
                    ("giovani volontari – aumento – ultimi 5 anni", [
                        "Negli ultimi cinque anni il numero dei giovani volontari è aumentato.",
                        "Negli ultimi cinque anni i giovani volontari ha aumentato.",
                        "I giovani volontari sono aumentati da ultimi cinque anni.",
                        "Negli ultimi cinque anni si aumentano i giovani volontari.",
                    ], 0),
                    ("motivi – desiderio di sentirsi utili", [
                        "Perciò il desiderio di sentirsi utili.",
                        "Tra i motivi, il più citato è il desiderio di sentirsi utili.",
                        "I motivi, che sono il desiderio di sentirsi utili.",
                        "Il motivo è che sentirsi utili desiderano.",
                    ], 1),
                ]),
            ),
        ]),
        module("writing", "Produzione di testi scritti", [
            part(
                "Prova B.1", "writing", {"kind": "essay", "words": 180}, 1, 45, 20,
                "Legga il testo e ne scriva un riassunto (150-200 parole), seguendo la traccia.",
                "A text of 400 to 500 words on a matter of society or culture, given in full in the situation, to be summed up; the points are the outline the summary must follow: the main thesis, the arguments, the examples, the conclusion. The summary is in the learner's own words, formal, without their own opinion.",
                {
                    "situation": "Riassuma il seguente articolo. «Negli ultimi vent'anni i piccoli borghi dell'Appennino hanno perso quasi un terzo degli abitanti. I giovani partono per studiare e non tornano, le scuole chiudono, i servizi si spostano a valle. Alcuni comuni, però, stanno tentando una strada diversa: offrono case a un euro, incentivi a chi apre un'attività, connessioni internet veloci per attirare chi lavora a distanza. I risultati sono ancora incerti: in certi paesi la popolazione è tornata a crescere, in altri le case vendute restano vuote per gran parte dell'anno, abitate solo in estate. Gli esperti concordano su un punto: senza scuole, trasporti e servizi sanitari, nessun incentivo basterà a far rinascere le aree interne.»",
                    "points": [
                        "Il problema dello spopolamento e le sue cause.",
                        "Le iniziative di alcuni comuni.",
                        "I risultati finora.",
                        "La conclusione degli esperti.",
                    ],
                },
            ),
            part(
                "Prova B.2", "writing", {"kind": "essay", "words": 240}, 1, 55, 20,
                "Scriva una composizione (220-250 parole) su uno dei due argomenti proposti.",
                "Two themes to choose from, given in the situation: a report on a problem or a phenomenon of today's society, a story of events and personal experiences, or a formal letter. The points are what the text must do: present the matter, develop it with reasons and examples, weigh other views and conclude.",
                {
                    "situation": "Scelga uno dei due argomenti. A) «Il lavoro a distanza sta cambiando il rapporto tra le persone e le città.» Scriva una relazione sul fenomeno. B) Racconti un'esperienza in cui ha dovuto adattarsi a una cultura diversa dalla Sua.",
                    "points": [
                        "Introduca l'argomento.",
                        "Lo sviluppi con argomenti ed esempi.",
                        "Consideri anche punti di vista diversi dal Suo.",
                        "Concluda in modo coerente.",
                    ],
                },
            ),
        ]),
        module("listening", "Comprensione dell'ascolto", [
            part(
                "Prova D.1", "comprehension", listening(8, text="interview"), 1, 8, 8,
                "Ascolti il testo. Lo ascolta due volte. Completi le frasi scegliendo l'informazione giusta: a, b, c o d.",
                "An interview or a talk of the radio of 400 to 500 words on a matter of culture, science or work, with eight sentences in the order of what is said, each ending in a gap, as the prompts. The four options are close in meaning; one is what is said. In the real exam the learner writes the words.",
                text("", "Conduttore: Professoressa Ricci, Lei studia da anni il sonno degli adolescenti. Che cosa ha scoperto?\nRicci: Che i ragazzi non sono pigri, come spesso si pensa. Durante l'adolescenza l'orologio biologico si sposta in avanti di circa due ore: un quindicenne ha sonno naturalmente verso mezzanotte. Se la scuola comincia alle otto, dorme in media sei ore e mezza, mentre ne avrebbe bisogno di almeno otto.", [
                    ("Secondo la professoressa, gli adolescenti ___", ["sono pigri.", "hanno un ritmo biologico diverso.", "dormono troppo.", "si svegliano presto naturalmente."], 1),
                    ("Un quindicenne avrebbe bisogno di dormire ___", ["sei ore e mezza.", "sette ore.", "almeno otto ore.", "dieci ore."], 2),
                ]),
            ),
            part(
                "Prova D.2", "comprehension", listening(10, "yesno", text="interview"), 1, 8, 11,
                "Ascolti il testo. Lo ascolta due volte. Le affermazioni sono presenti nel testo? Scelga: Sì o No.",
                "A discussion or a report of the radio of 400 to 500 words, with ten statements; each is or is not said, the absent ones likely and close to what is said. The real exam has eleven.",
                text("", "Giornalista: In Italia si legge poco? I dati dell'ISTAT dicono che solo quattro italiani su dieci leggono almeno un libro all'anno. Ma l'editore Lorenzo Fabbri non è pessimista: «Le librerie indipendenti stanno crescendo, soprattutto al Sud, e i gruppi di lettura si moltiplicano. Il problema sono gli adulti tra i trenta e i cinquant'anni, che dicono di non avere tempo».", [
                    ("Meno della metà degli italiani legge un libro all'anno.", [], 0),
                    ("Le librerie indipendenti stanno chiudendo.", [], 1),
                    ("Gli adulti di mezza età giustificano la scarsa lettura con la mancanza di tempo.", [], 0),
                ]),
            ),
            part(
                "Prova D.3", "comprehension", listening(10, text="announcement"), 1, 9, 12,
                "Ascolti il testo. Lo ascolta due volte. Completi la scheda scegliendo l'informazione giusta: a, b, c o d.",
                "A presentation of 350 to 450 words full of facts, such as the programme of a festival, the rules of a competition or a report with figures. A form of ten fields, each a prompt ending in a colon; the four options are what is said and three facts near it, such as other dates, numbers or names heard. The real exam has twelve fields, open.",
                text("", "Il Festival della Scienza di Genova si terrà dal 23 ottobre al 3 novembre. Quest'anno il tema è «Equilibri». Sono previsti oltre trecento eventi, tra conferenze, laboratori e mostre, distribuiti in quaranta sedi della città. Il biglietto giornaliero costa 12 euro; per gli studenti è ridotto a 8. Le scuole possono prenotare i laboratori sul sito entro il 30 settembre.", [
                    ("Durata del festival:", ["dal 23 settembre al 3 ottobre", "dal 23 ottobre al 3 novembre", "dal 3 al 23 ottobre", "dal 30 settembre al 3 novembre"], 1),
                    ("Biglietto ridotto per studenti:", ["6 euro", "8 euro", "10 euro", "12 euro"], 1),
                    ("Scadenza prenotazioni per le scuole:", ["23 ottobre", "3 novembre", "30 settembre", "1 ottobre"], 2),
                ]),
            ),
        ]),
        module("speaking", "Produzione orale", [
            part(
                "Prova 1", "oral", {"kind": "present", "prompts": 3}, 1, 7, 20,
                "Confronti le due foto e ne parli con l'esaminatore. " + ORAL,
                "Two photos to compare, described in words on the card in place of the pictures, that open a theme of society, such as an office full of people and a person working alone at home. The first prompt asks the learner to describe and compare them; the others are questions of the examiner that widen the theme.",
                {
                    "card": "Foto 1: una grande aula universitaria piena di studenti che ascoltano un professore. · Foto 2: una ragazza segue una lezione online dalla sua camera, con le cuffie, davanti al computer.",
                    "prompts": [
                        "Descriva e confronti le due foto.",
                        "Quali vantaggi e svantaggi vede nelle due situazioni?",
                        "Come pensa che cambierà l'università nei prossimi anni?",
                    ],
                },
            ),
            part(
                "Prova 2", "oral", {"kind": "discuss", "prompts": 3}, 1, 7, 20,
                "Riassuma il testo e ne discuta con l'esaminatore. " + ORAL,
                "A text of 200 to 250 words on a matter of society, on the card. The first prompt asks the learner to sum it up; the others are questions of the examiner that challenge their view.",
                {
                    "card": "Testo: Sempre più comuni italiani vietano l'uso dello smartphone nelle scuole, anche durante l'intervallo. I sostenitori del divieto parlano di maggiore concentrazione e di più dialogo tra i ragazzi. I critici ricordano che il telefono è anche uno strumento di studio e che la scuola dovrebbe insegnare a usarlo con responsabilità, non vietarlo.",
                    "prompts": [
                        "Riassuma il testo.",
                        "Lei è favorevole o contrario al divieto? Perché?",
                        "Non crede che vietare sia più semplice che educare?",
                    ],
                },
            ),
            part(
                "Prova 3", "oral", {"kind": "present", "prompts": 2}, 1, 6, 20,
                "Illustri il grafico e ne parli con l'esaminatore. " + ORAL,
                "A chart or a table of figures, given in words on the card, such as how people go to work in five cities, or what share of the young live with their parents in several countries. The first prompt asks the learner to present the figures and what they show; the second asks them to explain or comment on them.",
                {
                    "card": "Grafico: giovani tra 18 e 34 anni che vivono con i genitori (percentuale). Italia 68% · Spagna 64% · Francia 42% · Germania 38% · Svezia 15%.",
                    "prompts": [
                        "Illustri i dati del grafico.",
                        "Come spiega le differenze tra i Paesi?",
                    ],
                },
            ),
        ]),
    ],
)
