"""Pad the pages under 400 px: a row after the last row of the page's
first table group ("row"), or a box at the end of the page ("box").
Edits the lesson scripts, which are then run again."""

import re
import subprocess
from pathlib import Path

HERE = Path(__file__).parent
SCRIPTS = {}
for path in sorted(HERE.glob("l[0-9]*.py")):
    SCRIPTS[re.search(r'save_lesson\("([^"]+)"', path.read_text()).group(1)] = path

# (lesson, heading, kind, text)
PADS = [
 ("ausiliari-casi-speciali", "# Modali e riflessivi", "row", "| **Si sono** dovuti sposare in fretta. | **Hanno** dovuto sposar**si** in fretta. |\n| **Mi sono** potuto lavare. | **Ho** potuto lavar**mi**. |"),
 ("ci-e-ne", "# Ci vado, ne prendo due", "row", "| **ci** | a + cosa | Pensi all'esame? Sì, **ci** penso. |"),
 ("ci-e-ne", "# Ne o lo?", "row", "| Hai delle sorelle? Sì, **ne** ho due. | Conosci le mie sorelle? Sì, **le** conosco. |"),
 ("ci-e-ne", "# Ne con il passato prossimo", "row", "| Quanti libri hai letto quest'anno? | **Ne** ho lett{e:i} dieci. |"),
 ("comparativi", "# Più alto, meno caro, alto come", "box", "> [!tipp] Consiglio\n> **di** si unisce all'articolo: *più alto **del** padre, meno caro **dell'**aereo, più bella **della** foto*."),
 ("comparativi", "# Di o che? Un confronto", "row", "| Sara è più giovane **di** sua sorella. | È più facile parlare **che** scrivere. |\n| Il caffè è più forte **del** tè. | Bevo più caffè **che** tè. |"),
 ("condizionale-passato", "# Futuro nel passato: un confronto", "row", "| Credo che **finirà** presto. | Credevo che **avrebbe finito** presto. |\n| Scrive che **arriverà** lunedì. | Ha scritto che **sarebbe arrivato** lunedì. |"),
 ("congiuntivo-congiunzioni", "# Senza che e senza", "row", "| Ha preso la macchina **senza che** il padre lo **sapesse**. | Ha preso la macchina **senza** chiedere. |"),
 ("congiuntivo-congiunzioni", "# Senza che e senza", "box", "> [!beispiel] Esempi\n> Luca è uscito di casa **senza** salutare, **senza che** sua madre se ne **accorgesse**."),
 ("congiuntivo-passato", "# Penso che sia già partito", "row", "| È possibile che Luca **sia** in ufficio. | È possibile che Luca **sia** già **uscito**. |"),
 ("congiuntivo-presente", "# Penso che sia vero", "row", "| **Sono sicuro** che **arriva** presto. | **Ho paura** che **arrivi** tardi. |"),
 ("domande-negazione", "# Dove abiti? Non lo so.", "row", "| Sara lavora oggi. | Sara lavora oggi? | Sara **non** lavora oggi. |"),
 ("futuro", "# Futuri irregolari (2)", "row", "| mantenere | {c:manterr}ò | rifare | {c:rifar}ò |"),
 ("futuro", "# Il futuro per fare ipotesi", "row", "| Di chi è questa borsa? | **Sarà** di Giulia. | It's probably Giulia's. |"),
 ("imperativo-pronomi", "# Dimmi! Prendilo! Si accomodi!", "row", "| tu, con *non* | prima **o** dopo | Non **lo** prendere! / Non prender**lo**! | Don't take it! |"),
 ("imperativo", "# Imperativo in pratica", "row", "| a tavola | **Prendi** ancora un po'! | **Prenda** ancora un po'! |"),
 ("partitivo-quantita", "# Le quantità precise", "row", "| un pezzo **di** | un pezzo di formaggio | una tazza **di** | una tazza di tè |"),
 ("passato-prossimo-o-imperfetto", "# Abitudine o una volta?", "row", "| D'estate **dormivamo** in campagna. | L'estate scorsa **abbiamo dormito** in tenda. |\n| **Prendeva** spesso l'autobus. | Stamattina **ha preso** un taxi. |"),
 ("passato-prossimo-o-imperfetto", "# Quanto tempo? Una durata precisa", "row", "| **Ho dormito** otto ore. | **Dormivo** quando hai chiamato. |"),
 ("passato-prossimo-o-imperfetto", "# Le parole che aiutano", "row", "| tutti i giorni, la domenica | domenica scorsa, stamattina |"),
 ("passato-prossimo-o-imperfetto", "# Una storia completa", "box", "> [!tipp] Consiglio\n> Imperfetto = la **scena**: com'era, che cosa succedeva. Passato prossimo = i **fatti** che fanno andare avanti la storia."),
 ("piacere", "# Mi piace la pizza", "row", "| **Gli piace** cucinare. | To him is pleasing to cook. | He likes cooking. |"),
 ("piacere", "# Anche a me, neanche a me", "row", "| Mi piacciono i film gialli. | **Anche a me.** | **A me no.** |\n| Non mi piace alzarmi presto. | **Neanche a me.** | **A me sì.** |"),
 ("possessivi", "# Suo o Suo formale?", "row", "| Com'è **la tua** casa? | Com'è **la Sua** casa? | your house |"),
 ("preposizioni-semplici", "# Luoghi che finiscono in -ia", "row", "| panetteria | Il pane? **In** panetteria. | banca | Lavoro **in** banca. |"),
 ("presente-regolare", "# Parlo, scrivo, dormo", "row", "| 3° con -isc- | -**ire** | finire, capire, pulire | to finish, understand, clean |"),
 ("pronomi-combinati", "# Me lo dai? Glielo porto.", "row", "| Vi spiego **la regola**. | **Ve la** spiego. | I'll explain it to you. |"),
 ("pronomi-combinati", "# Con il passato prossimo", "row", "| Chi vi ha detto **la notizia**? | **Ce l'**ha dett{e:a} Giulia. |"),
 ("pronomi-diretti", "# Dove va il pronome?", "row", "| passato prossimo | prima dell'ausiliare | **L'**ho comprato. |"),
 ("pronomi-indiretti", "# Gli telefono, le scrivo", "row", "| Rispondo **alla professoressa**. | **Le** rispondo. |"),
 ("pronomi-relativi", "# La ragazza che parla, la città in cui abito", "row", "| Ecco il ragazzo. Parlo **con** il ragazzo. | Ecco il ragazzo **con cui** parlo. |"),
 ("pronomi-relativi", "# Il cui: di chi", "row", "| Una città **la cui** storia è antica … | whose history |"),
 ("superlativi", "# Senza il nome", "row", "| Qual è la stagione più calda? | Qual è **la più calda**? |"),
 ("trapassato-futuro-anteriore", "# Prima di prima, dopo di dopo", "row", "| trapassato prossimo | Avevo fame perché non **avevo mangiato**. | hadn't eaten |\n| futuro anteriore | Ti chiamo appena **sarò arrivato**. | as soon as I've arrived |"),
 ("concordanza-tempi", "# Pensavo che fosse già partito", "row", "| È strano che non **abbia chiamato**. | Era strano che non **avesse chiamato**. |"),
 ("gerundio-infinito-passato", "# Ho imparato leggendo", "row", "| **Se studi** di più, passerai l'esame. | **Studiando** di più, passerai l'esame. |"),
 ("gerundio-infinito-passato", "# Errori tipici", "row", "| {x:Avendo arrivato tardi, ha perso il treno.} | {v:Essendo} {i:arrivato} tardi, … | arrivare: essere |"),
 ("passato-remoto", "# Remoto o prossimo?", "row", "| *Ieri **ho incontrato** Marco.* | *Quel giorno il principe **incontrò** il re.* |\n| *Dante? L'**ho letto** a scuola.* | *Dante **scrisse** la Commedia.* |"),
 ("passato-remoto", "# Remoto e imperfetto", "row", "| Il giorno dopo il sole splendeva. | Il vecchio **ringraziò** e **partì**. |"),
 ("passato-remoto", "# Errori tipici", "row", "| {x:Lui dicé la verità.} | Lui {c:disse} la verità. | dire: dissi, disse |"),
 ("passato-remoto", "# Errori tipici", "box", "> [!tipp] Consiglio\n> Quando leggi, riconosci il remoto dall'**accento finale** (*parlò, partì*) e dalle forme in **-ssi, -si, -nni** (*disse, prese, venne*)."),
 ("passivo", "# La casa è stata costruita", "row", "| Molti italiani **leggono** questo giornale. | Questo giornale **è letto** da molti italiani. |"),
 ("passivo", "# Venire invece di essere", "row", "| I biglietti **sono controllati** sul treno. | I biglietti **vengono controllati** sul treno. |"),
 ("passivo", "# Errori tipici", "row", "| {x:Il ladro è stato arrestato per la polizia.} | … {h:dalla} polizia. | chi fa: da + articolo |"),
 ("passivo", "# Errori tipici", "box", "> [!tipp] Consiglio\n> Controlla sempre tre cose: il tempo di **essere**, l'accordo del **participio**, **da** per chi fa l'azione."),
 ("periodo-ipotetico-irreale", "# Se l'avessi saputo …", "row", "| irreale | Se l'avessi saputo, te l'avrei detto. | non lo sapevo, non te l'ho detto |"),
 ("periodo-ipotetico-irreale", "# Nel parlato: l'imperfetto", "row", "| Se **studiavi**, **passavi** l'esame. | Se **avessi studiato**, **avresti passato** l'esame. |"),
 ("periodo-ipotetico-irreale", "# Errori tipici", "row", "| {x:Se ero partito prima, sarei arrivato.} | Se {v:fossi partito} prima, … | se + congiuntivo trapassato |"),
 ("periodo-ipotetico", "# Se piove, resto a casa", "row", "| Se domani fa bel tempo, | andiamo al mare. | reale: è probabile |"),
 ("si-impersonale-passivante", "# Ci si alza presto", "row", "| Loro **si** vestono bene. | **Ci si** veste bene. |"),
 ("si-impersonale-passivante", "# Si è contenti: aggettivi e nomi", "row", "| Da bambini **si è** curiosi. | As children, you're curious. |"),
 ("si-impersonale-passivante", "# Errori tipici", "row", "| {x:Qui si parla molte lingue.} | Qui si {v:parlano} molte lingue. | oggetto plurale |"),
 ("verbi-infinito", "# Ho deciso di partire", "row", "| **Sa** nuotare. | **Ha smesso di** nuotare. | **Ha imparato a** nuotare. |"),
 ("verbi-infinito", "# Errori tipici", "row", "| {x:Ho imparato di nuotare.} | Ho imparato {h:a} nuotare. | imparare a |"),
 ("verbi-infinito", "# Errori tipici", "box", "> [!tipp] Consiglio\n> Quando impari un verbo nuovo, scrivilo con la sua preposizione: *decidere **di**, riuscire **a***."),
]

touched = set()
for lesson, heading, kind, text in PADS:
    path = SCRIPTS[lesson]
    src = path.read_text()
    start = src.index("\n" + heading + "\n") + 1
    end = src.find("\n---\n", start)
    if end < 0:
        end = src.index('\n""")', start)
    page = src[start:end]
    if text in page:
        continue
    if kind == "row":
        lines = page.split("\n")
        # end of the first table
        first = next(n for n, l in enumerate(lines) if l.startswith("|"))
        last = first
        while last + 1 < len(lines) and lines[last + 1].startswith("|"):
            last += 1
        lines.insert(last + 1, text)
        page = "\n".join(lines)
    else:
        page = page.rstrip("\n") + "\n\n" + text + "\n"
    src = src[:start] + page + src[end:]
    path.write_text(src)
    touched.add(path)

for path in sorted(touched):
    subprocess.run(["python3", path.name], cwd=HERE, check=True)
