# Il corredo — liste nominate e indicizzabili nei blocchi `let:`

Documento di design. Consolida le decisioni prese in sessione il 2026-08-01,
una per una, a partire da un'idea di sintassi appuntata a mano: poter dichiarare
liste dentro i `let:` e puntarne gli elementi da uno `spread`.

Ogni affermazione sul comportamento attuale è marcata **[eseguito]** (verificata
lanciando codice) o **[dedotto]** (letta nel codice, non eseguita).

---

## L'esito in breve

Un **corredo** è una lista nominata, dichiarata in un blocco `let:` e letta
**solo per indice** dalle espressioni.

```yaml
let:
  d: 1                                    # fondamentale: periodo 1 s = 60 bpm

streams:
  cugini:
    let:
      ratio: {list: [2, 3, 4, 7]}         # il corredo: quattro rapporti scelti
    spread:
      n: {expr: "len(ratio)"}
      let:
        r: {expr: "ratio[i]"}             # il rapporto di QUESTA voce
      over:
        base.pointer.start: {ramp: {start: 0.1, step: 0.2}}
    stack:
      density:
        unit: s
        base: {expr: "d * r"}             # periodi 2s, 3s, 4s, 7s
    axes:
      grain.duration:
        base: {expr: "d * ratio[0] / 40"} # riferito alla fondamentale del corredo
```

Quattro pezzi, tutti additivi:

1. **`list:`** — una nuova forma di valore nei `let:` di documento e di gruppo:
   una lista, non un `Env`.
2. **`cycle:`** — la politica del corredo: insieme finito (accordo) o pattern
   periodico.
3. **`nome[expr]`** — l'indicizzazione, una produzione nuova nella grammatica di
   `expr`.
4. **`len(nome)`** — una primitiva nuova, che accetta solo un corredo.

Cosa **non** si tocca: il vocabolario dei generatori (`values`/`ramp`/banda);
l'iniezione per nome; lo scoping e la guardia anti-ombreggiatura; i seed; il pad
stabile dei nomi generati. Uno `study.yml` che non usa `list:` produce documenti
identici.

---

## Il problema

### Il buco: un valore scelto a mano non si può condividere

Le manopole di voce hanno oggi due forme, e coprono due casi su tre:

| Il valore per voce è… | Come si scrive | Condivisibile fra più lettori? |
|---|---|---|
| **pescato** | banda in `spread.let` | sì |
| **calcolato** | `{expr: "…"}` con `i`/`n` | sì |
| **scelto a mano** | `values` in `spread.over` | **no** — scrive su un path solo |

`values`/`ramp` in `spread.let` sono rifiutati, e la ragione scritta nel
reference è corretta: *«possiederebbero un conteggio ridondante con `over`»*.
La conseguenza involontaria è che una serie **irregolare e decisa dall'autore**
— quattro rapporti scelti a orecchio, non una formula — non può essere letta da
due assi diversi.

Il corredo aggira l'obiezione invece di combatterla: la lista vive nel `let:` di
**gruppo**, dove non esiste nessun indice e quindi nessuna pretesa sul
conteggio. È lo `spread` a indicizzarla.

### Il nome mancante: la fondamentale

`ratio[0]` non ha oggi nessun sostituto. Si può scrivere `d0: 2` accanto alla
lista, ma è una duplicazione che **diverge in silenzio** appena si ritocca il
primo rapporto. `ratio[0]` dice «la fondamentale del corredo» una volta sola.

Non è un dettaglio ergonomico: in CONTEXT.md accordi e polimetrie nascono dai
*rapporti di density fra stream*, quindi poter nominare il riferimento di un
insieme di rapporti è materia centrale, non zucchero sintattico.

---

## La sintassi

### `list:` — la dichiarazione

```yaml
let:
  ratio: {list: [2, 3, 4, 7]}
```

**Perché non `values:`.** In un `let:` la chiave `values` è già occupata:
`document_let.resolve_knobs` (condiviso da documento e gruppo) passa qualunque
dict con `values`/`ramp`/`base` a `expand_env`. **[eseguito]**

```
expand_env({'values': [2, 3, 4, 7]})
  →  [[0.0, 2], [0.333, 3], [0.667, 4], [1.0, 7]]
```

Cioè un envelope: a `t = 0.5` il valore è `3.5`. Per un corredo di rapporti
`3.5` non è un rapporto sbagliato, è una domanda senza senso — fra il terzo e il
quarto rapporto non c'è nessuna voce. **Un corredo è discreto per natura, e per
questo non può essere un `Env`.**

**Perché non la lista nuda.** `ratio: [2, 3, 4, 7]` sarebbe libera, ma solo a
certe lunghezze. **[eseguito]**, `eval_expr` con il nome in scope:

| Scritto | Oggi |
|---|---|
| `[2, 3, 4, 7]` | errore: *«forma non riconosciuta»* → slot libero |
| `[2, 3]` | `Env`, rampa 2→3 → **collisione silenziosa** |
| `[[0,1],[1,2]]` | `Env`, breakpoint → collisione |
| `[5]` | errore → libero |

La collisione a lunghezza 2 è del tipo peggiore: valida in entrambe le letture,
nessun errore, suono sbagliato. E due voci in rapporto 3:2 è materiale che si
scrive davvero.

`list:` inoltre non è in `Y_GENERATOR_KEYS`, quindi `is_generator_node` non lo
vede: nessuna collisione con la macchina esistente. **[dedotto]**

### Cosa può stare dentro `list:`

`list:` dichiara il **tipo**; come si producono gli elementi è una domanda
ortogonale, a cui risponde il vocabolario dei generatori già esistente. È la
stessa composizione che il sistema fa per i generatori annidati (*«i `points` di
un bordo si possono generare invece di scriverli a mano»*).

```yaml
let:
  scelto:  {list: [2, 3, 4, 7]}
  armonica: {list: {ramp: {start: 1, stop: 8, step: 1}}}   # [1..8]
  pescato:  {list: {n: 5, base: 2, range: 6, seed: 1988}}  # 5 rapporti in [2, 8]
```

La legge: **un corredo possiede la propria lunghezza**, quindi il suo generatore
deve possedere un conteggio.

| Forma | Ammessa | Perché |
|---|---|---|
| lista letterale | sì | possiede `len` |
| `{values: [...]}` | sì, ridondante | possiede `len` |
| `{ramp: {start, stop, step}}` | sì | la griglia possiede il conteggio |
| `{ramp: {start, step}}` | **no** | progressione infinita |
| `{ramp: {start, stop}}` | **no** | il conteggio andrebbe ereditato |
| banda `{n, base, range, seed}` | sì | `n` esplicito |
| banda senza `n` | **no** | nessun conteggio |

Le due forme di `ramp` escluse sono le stesse che in `spread.over` non
possiedono `n` e se lo fanno dare da fuori. Nel corredo non c'è nessun fuori.

**Il corredo pescato** apre un caso che oggi non esiste. La banda di
`spread.let` fa un pescaggio per voce, e l'insieme non esiste come oggetto: non
se ne può nominare la fondamentale, non si può ciclare, non si può misurare. Con
`{list: {n: 12, base: 2, range: 6, seed: 1988}}` l'insieme viene pescato **una
volta** e poi indicizzato, quindi `ratio[i] / ratio[0]` — ogni voce in rapporto
alla prima estratta — diventa scrivibile.

### `cycle:` — accordo o pattern

```yaml
let:
  ratio:  {list: [2, 3, 4, 7]}                # accordo: insieme finito
  durate: {list: [1, 1, 2], cycle: true}      # pattern: si ripete
```

Non è un flag di comodo: sono **due oggetti compositivi diversi**. Un accordo è
un insieme fisso di rapporti — se ne chiedi il quinto, la domanda è sbagliata.
Un pattern è periodico per natura — il quinto elemento *è* il primo, come in un
ciclo ritmico. Che il primo dia errore fuori range e il secondo si avvolga non è
una regola arbitraria: è la differenza fra i due oggetti.

Il valore di default è `false`: un corredo senza `cycle:` è un accordo.

### L'indicizzazione in `expr`

Una produzione nuova, `nome[expr]`. L'indice è un'espressione qualsiasi, purché
valuti a un intero.

- `i` è disponibile solo dove è già in scope, cioè negli `expr` dello spread
  (`spread.let` e le strategy di `over`);
- un **indice costante** funziona in ogni scope di `expr`, perché non dipende da
  `i`: `ratio[0]` in un `axes:` è legittimo e verificabile al load;
- gli **indici negativi** sono ammessi: `ratio[-1]` è l'ultimo. Servono a
  invertire il senso di lettura del corredo, e su un corredo ciclico cadono
  fuori gratis dal modulo (`-1 % 4 = 3`);
- un indice **non intero** è errore: la quantizzazione si scrive, con `//` o
  `floor`, che sono già in grammatica.

**Buona notizia sull'implementazione.** `inject.expr_names` usa `ast.parse`, e
`ratio[i]` è un `ast.Subscript` i cui `Name` sono `ratio` e `i`. **[eseguito]**:
`expr_names("ratio[i]")` → `{'i', 'ratio'}`. Quindi l'iniezione per nome e la
guardia anti-refuso «manopola non referenziata» continuano a funzionare **senza
modifiche**. L'unico punto da toccare è la whitelist di `eval_expr`, che oggi
rifiuta `ast.Subscript`.

### `len()`

Una primitiva nuova. Accetta **solo un corredo**.

`len` di un envelope dev'essere errore, non «quanti breakpoint ha»: quello è un
dettaglio di rappresentazione — `expand_env` può produrne un numero diverso a
parità di intenzione — e farlo trapelare nel linguaggio renderebbe le
espressioni dipendenti dall'implementazione.

`len()` serve a due cose, entrambe necessarie:

```yaml
spread:
  n: {expr: "len(ratio)"}                    # legare la popolazione al corredo
  let:
    r:   {expr: "ratio[i % len(ratio)]"}     # il ciclo scritto a mano
    ott: {expr: "2 ** (i // len(ratio))"}    # ...e i giri contati
```

---

## Dove vive un corredo

| Blocco | Corredo ammesso |
|---|---|
| `let:` di documento | sì — condiviso da più gruppi, ognuno con il proprio `i` |
| `let:` di gruppo | sì — il caso tipico |
| `spread.let` | **no** |
| il `let` interno di un nodo-expr | corredo **letterale** sì; corredo **generato** no |

Il divieto in `spread.let` non è una restrizione prudenziale: a livello di voce
`i` è già fissato, quindi una lista lì non avrebbe nessun indice da cui essere
letta, se non costanti. Il significato di `spread.let` — *un valore per voce* —
resta intatto.

Nel `let` interno di un nodo-expr la riga si divide in due, e non per analogia
con il divieto dei nodi-generatore — un corredo *non è* un nodo-generatore, ed è
esattamente perché `list` non sta in `Y_GENERATOR_KEYS` che si è scelto quella
chiave. Le due metà hanno ragioni diverse:

- un corredo **letterale** è ammesso. È un valore statico come `[[0, 1], [1, 2]]`,
  che quel `let` accetta già: vietarlo sarebbe arbitrario;
- un corredo **generato** è errore, e la ragione è precisa: `resolve_knobs` fonde
  il `let` locale nello scope **grezzo** (`scope.update(node.get("let") or {})`),
  e nessuna seam lo espande — il generatore non verrebbe mai eseguito e non
  avrebbe un seed da cui pescare. È lo stesso motivo per cui un nodo-generatore
  lì è errore, non un'analogia con esso.

Il controllo va dove va quello dell'ombreggiatura, che ha lo stesso problema e lo
risolve così: **al load, sul documento grezzo**, prima che l'iniezione consumi i
nomi (`_check_shadowing`). Che dopo l'iniezione un corredo scritto a mano e uno
iniettato siano indistinguibili non impedisce il controllo — lo colloca. E non
produce falsi positivi rieseguito: l'iniezione mette in scope corredi già
*risolti*, cioè letterali.

**Più corredi nello stesso `let:` sono ammessi**, ed è lì che il meccanismo dà
il suo risultato più interessante (vedi «Isoritmo» sotto).

---

## Le regole

### Il corredo può *dare* `n`, non prenderlo

Il corredo non eredita mai il proprio conteggio dallo spread. La direzione
inversa — `spread.n: {expr: "len(ratio)"}` — è invece esplicitamente supportata.

Le ragioni, in ordine di gravità:

1. **Sarebbe circolare.** `spread.n: {expr: "len(ratio)"}` e un corredo che
   prende `n` dallo spread, insieme, sono un ciclo. E anche separatamente
   l'ordine si inverte: le manopole di gruppo sono *«risolte una volta per
   gruppo e iniettate prima dell'espansione»*, quindi al momento in cui il
   corredo si risolve `spread.n` non esiste ancora. **[dedotto]**
2. **Un corredo di documento non ha uno spread.** Letto da due gruppi con `n`
   diversi, non avrebbe una lunghezza. La feature potrebbe esistere solo nei
   `let` di gruppo che hanno uno `spread:` fratello — cioè il *tipo* del corredo
   dipenderebbe dal contesto, che è ciò che si è scartato tre volte in questo
   design.
3. **Svuoterebbe l'oggetto.** Con `len == n` per costruzione, `cycle` non scatta
   mai, il fuori range è impossibile, `len(ratio)` è un altro nome per `n`, e il
   warning `n < len` non può emettersi.
4. **Le due forme sono già esprimibili.** Banda senza `n` con `n` ereditato = la
   banda di `spread.let` (*«un pescaggio per voce»*). `ramp {start, stop}` con
   `n` ereditato = `spread.over` con quel ramp, o `spread.let` con l'aritmetica
   su `i`/`n`, che il reference prescrive alla lettera.

### Il possesso di `n` non dipende dall'uso

Un corredo non possiede mai il conteggio della popolazione, nemmeno quando è
l'unico indicizzato. La tentazione era di dire «lo possiede se qualcuno lo
indicizza con `i`», ma cade su questo:

```yaml
streams:
  dodici:
    let:
      ratio: {list: [2, 3, 4, 7]}          # len = 4
    spread:
      n: 12
      let:
        r: {expr: "2 ** (i / 12)"}         # rapporti calcolati: il corredo non c'entra
    axes:
      grain.duration:
        base: {expr: "ratio[0] * 0.01"}    # legge solo la fondamentale
```

Con il possesso dipendente dall'uso questo sarebbe un errore (4 ≠ 12) senza che
ci sia niente di sbagliato.

### Fuori range

La politica la decide il **corredo**, non il punto d'uso, e vale uniformemente
per gli indici costanti e per quelli calcolati:

- corredo **finito** → indice fuori range è **errore**, con messaggio che nomina
  versione (se pertinente), voce, nome del corredo e `len`;
- corredo **ciclico** → l'indice si avvolge (`i % len`).

Uniforme significa che `ratio[9]` su un corredo di 4 elementi è errore se il
corredo è finito e vale `ratio[1]` se è ciclico, esattamente come `ratio[i]`. Se
la regola dipendesse dall'essere l'indice costante o calcolato, tornerebbe a
dipendere dall'uso.

**Perché non tiene-l'ultimo.** Il precedente esiste (`versions` Forma 1: *«le
più corte tengono l'ultimo valore»*), ma lì le manopole co-varianti sono rampe
che si esauriscono. Su un insieme di rapporti darebbe `2,3,4,7,7,7,7,7` — che
non è né un accordo né un ciclo.

### `n < len`: warning, non errore

Un corredo sotto-consumato è legittimo — si sta ascoltando un sottoinsieme
dell'accordo — ma è anche il sintomo più comune di un refuso. Quindi warning,
con queste caratteristiche:

- **per corredo**, non per gruppo: con due corredi di lunghezza diversa uno può
  essere sotto-consumato e l'altro no;
- riporta **riga dello YAML, gruppo, nome del corredo, `len` e `n`**;
- si emette alla **generazione** (`sweep`/`stack`/`versions`/`percorso`), non al
  `render`. Il corredo si risolve al load, e `Locations` — la mappa
  `key-path → (riga, colonna)` che serve per dire *quale riga* — esiste solo lì;
  quando gira `render`, lo YAML engine non ha più traccia del corredo.

Oggi un canale di warning non esiste: la diagnostica non fatale è stampata
direttamente (`_warn_orphans` in `__main__.py`, un `warnings.warn` in
`render.py`). **[dedotto]** Serve un `WarnCtx` che riusi `format_block()` di
`SpecError` con prefisso `[warn]` invece di alzare.

Il controllo va scritto come **funzione pura**
`(documento parsato, Locations) → diagnostici strutturati`, con stderr e il
language server come due consumatori. Vedi issue #46.

### Le altre guardie

- **Corredo vuoto** (`{list: []}`) → errore alla dichiarazione. Con
  `cycle: true` sarebbe anche un modulo per zero.
- **Corredo non referenziato** → errore, per estensione della guardia
  anti-refuso esistente. Funziona senza modifiche (vedi sopra: `ast.walk`
  registra `ratio` da `ratio[i]`).
- **Ombreggiatura fra livelli** → invariata. Un corredo è una manopola come le
  altre, quindi `_check_shadowing` lo copre già.
- **Ordine di risoluzione**: i corredi non sono mai derivati (una lista non è
  un valore), quindi si risolvono nella prima passata di `resolve_knobs`, prima
  del fixpoint delle manopole derivate — così `{expr: "ratio[0] * 2"}` è una
  manopola derivata legittima.
- **`versions` muove il valore, non il tipo.** Un asse di `versions:` può
  sostituire un corredo, ma con un corredo della stessa politica di `cycle`.
  Altrimenti la validità dello studio cambierebbe da una versione all'altra.

### La linea di confine sulla grammatica

Aprire `[]` riapre una grammatica chiusa per scelta (*«niente indici, confronti
o argomenti keyword»*). La linea dichiarata:

> **Una lista non è mai un valore.** Può comparire solo come `nome[expr]` o
> `len(nome)`. Non si passa a una funzione, non ci si fa aritmetica, non si
> restituisce.

Così il tipo di ogni *espressione* resta `scalare | Env` come oggi, e i corredi
sono un namespace di dichiarazione separato. Due produzioni nuove, non una
famiglia aperta.

---

## Esempi che motivano

### L'accordo

```yaml
let:
  d: 1
streams:
  accordo:
    let:
      ratio: {list: [2, 3, 4, 7]}
    spread:
      n: {expr: "len(ratio)"}
      let:
        r: {expr: "ratio[i]"}
      over:
        base.pointer.start: {values: [0.1, 0.3, 0.5, 0.7]}
    stack:
      density: {unit: s, base: {expr: "d * r"}}
```

Quattro voci, periodi 2s / 3s / 4s / 7s: una polimetria in rapporti scelti.

### L'accordo replicato per ottave

```yaml
    spread:
      n: 12
      let:
        r:   {expr: "ratio[i % len(ratio)]"}
        ott: {expr: "2 ** (i // len(ratio))"}
      over:
        base.pointer.start: {ramp: {start: 0.05, step: 0.075}}
    stack:
      density: {unit: s, base: {expr: "d * r / ott"}}
      # periodi: 2  3  4  7  |  1  1.5  2  3.5  |  .5  .75  1  1.75
```

`%` e `//` erano entrati per trasformare `i` in coordinate di griglia; qui danno
tre ottave dello stesso accordo in due righe.

### L'ispessimento

```yaml
    let:
      ratio: {list: [2, 3, 4, 7], cycle: true}
    spread:
      n: 12
      let:
        r: {expr: "ratio[i]"}          # 2,3,4,7, 2,3,4,7, 2,3,4,7
      over:
        base.pointer.start: {ramp: {start: 0.05, step: 0.075}}
```

Tre voci per rapporto, ognuna che legge un punto diverso del buffer. Stesso
periodo, contenuto e fase diversi: l'accordo si ispessisce senza cambiare le
altezze. È il caso che il nome `cugini` descrive.

### Isoritmo

```yaml
    let:
      ratio:  {list: [2, 3, 4, 7], cycle: true}   # len 4
      durate: {list: [1, 1, 2],    cycle: true}   # len 3
    spread:
      n: 12
      let:
        r: {expr: "ratio[i]"}
      over:
        duration: {expr: "durate[i] * 8"}   # il corredo di gruppo, non spread.let
    stack:
      density: {unit: s, base: {expr: "d * r"}}
```

Due corredi ciclici di lunghezze coprime scorrono uno contro l'altro: la
**sequenza** delle coppie (rapporto, durata) ha periodo `lcm(4, 3) = 12`. Le
singole coppie invece si ripetono prima — `(2, 1)` torna già alla voce 4 —
perché `durate` contiene due volte il valore `1`; ed è anche la descrizione
musicalmente corretta, perché nella talea i valori si ripetono eccome: quello
che cicla con periodo `lcm` è la **relazione di fase** fra color e talea. È
**color e talea**, e cade fuori da due `cycle: true` senza sintassi dedicata.

Nota sullo scope: `over` legge `durate[i]` direttamente invece di passare da una
manopola di `spread.let`. In `_plan_entry` i valori di `over` e quelli di
`spread.let` sono calcolati come **fratelli**, indipendenti; `expand_spreads`
scrive i primi sui path e solo dopo inietta i secondi nei nodi-expr del
generato, quindi quando `over` viene valutato `spread.let` non esiste ancora. Il
corredo di gruppo è invece già in scope lì — le manopole di gruppo sono iniettate
nelle espressioni dell'entry prima dell'espansione.

---

## Le strade scartate

| Proposta | Perché no |
|---|---|
| lista nuda `[2, 3, 4, 7]` | collisione silenziosa a lunghezza 2 con la rampa `[a, b]` **[eseguito]** |
| riusare `values:` | già occupato in `let:`: produce un envelope **[eseguito]** |
| tiene-l'ultimo fuori range | dà `2,3,4,7,7,7,7` — non è l'idioma di niente |
| il corredo possiede `n` | rompe il corredo letto solo con indice costante (vedi sopra) |
| il corredo eredita `n` dallo spread | circolare, impossibile a livello di documento, svuota l'oggetto, ridondante |
| `at(sagoma, u)` invece del tipo lista | nessun tipo nuovo, ma interpola dove serve una scelta discreta: `at(ratio, 0.3) = 3.4` non è un rapporto |
| elementi non scalari (sagome) | rimandato → issue #44 |

---

## Lavoro collegato

- **#45 — bug, prerequisito bloccante.** Una manopola derivata che chiama una
  primitiva non risolve mai: `expr_names` restituisce anche i nomi delle
  funzioni, e il fixpoint di `resolve_knobs` li tratta come manopole mancanti.
  **[eseguito]** `len()` è una primitiva e finisce esattamente lì, quindi
  `spread.n: {expr: "len(ratio)"}` nascerebbe rotto. **Da chiudere prima.**
- **#44 — scopo rimandato.** Corredi di sagome e di valori non numerici, con le
  ragioni del rinvio (riaprirebbero `Env ⊙ Env`, che oggi ha in `mix` l'unica
  porta dichiarata).
- **#46 — language server.** I dieci diagnostici del corredo, e il confine fra
  ciò che è decidibile staticamente e ciò che dipende dal prodotto cartesiano
  delle versioni. Da spostare su `gl-ls`.
- **#47 — `values:` / `linear_env:`.** Separazione dei due ruoli di `values`.
  Indipendente, ma conviene farla **prima**: introduce `linear_env:` come
  wrapper di ruolo, simmetrico a `list:`, e fatta dopo costringerebbe a
  riscrivere due volte doc e test.
- **#39 — pad stabile dei nomi.** Già risolto lì il caso di `spread.n` variabile
  per versione, che è il meccanismo su cui poggia `n: {expr: "len(ratio)"}`
  quando `versions` muove il corredo.

---

## Implementazione

Il design è scomposto in sette fette verticali: ognuna attraversa tutti gli
strati — dichiarazione, risoluzione delle manopole, valutazione
dell'espressione, iniezione, espansione, documento engine generato — ed è
verificabile da sola con uno `study.yml` che la esercita. I criteri di
accettazione stanno nelle issue.

| Issue | Fetta | Bloccata da |
|---|---|---|
| #48 | `list:` letterale e indice costante | #47 |
| #49 | indicizzazione per voce: `i`, negativi, fuori range | #48 |
| #50 | `cycle: true` — accordo vs pattern | #49 |
| #51 | la primitiva `len()` | #48, #45 |
| #52 | generatori dentro `list:` — corredo generato e pescato | #48 |
| #53 | warning `n < len` come diagnostico strutturato | #49 |
| #54 | corredi sotto `versions:` e `percorso:` | #49, #50 |

L'ordine non è una catena: dopo #48 partono in parallelo #49, #51 e #52; dopo
#49 si sbloccano #50 e #53; #54 chiude. I due prerequisiti fuori dalla serie
sono #45 (bug, blocca #51) e #47 (`linear_env:`, blocca #48).

---

## Retrocompatibilità

Additivo e opt-in. Senza `list:` nei `let:`, nessun cambiamento: i documenti
generati sono identici e i render esistenti restano ancorati al diario
d'ascolto.

L'unica modifica a comportamento esistente è la whitelist di `eval_expr`, che
smette di rifiutare `ast.Subscript`. Espressioni che oggi sono errore diventano
valide; nessuna espressione oggi valida cambia significato.

## Fuori scopo, deliberatamente

- **Etichette nei nomi generati.** Una voce da corredo si chiama `cugini_03`, e
  per sapere che ha rapporto 7 bisogna contare, mentre `versions` etichetta
  (`__d=1`). Valutato e lasciato com'è: non è una decisione di sintassi.
- **Corredi di sagome e valori non numerici.** Issue #44.
- **`values`/`ramp` in `spread.let`.** Restano rifiutati: il corredo risolve il
  caso d'uso da un livello sopra, senza toccare quel divieto.
