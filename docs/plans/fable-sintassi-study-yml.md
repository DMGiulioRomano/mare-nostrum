# Prompt per Fable 5 — ergonomia e accoppiamento della sintassi `study.yml`

Documento da dare a Claude Fable 5 in una sessione con accesso a questo repo.
Scritto il 2026-07-22; nato da una sessione in cui la sintassi di
`studies/stack_1-50smp/study.yml` è risultata faticosa da scrivere e da rileggere.

**Come si usa:** apri una sessione in `granulation-studies/` con Fable 5
(effort `high` o `xhigh`) e incolla tutto ciò che sta sotto la riga.

---

## Perché ti sto chiedendo questo

Sto scrivendo uno studio sulla granulazione dove il repository *è* lo studio.
Il mio ciclo di lavoro è `study.yml → audio → ascolto → modifica → rigenera`, su
due soli parametri (`density` e `grain.duration`): tutto il resto — altezze,
accordi, polimetrie — deve **emergere** da quei due e dallo stacking di più
stream, mai da altri parametri.

Finora ho usato questa sintassi per l'**analisi**: muovo una variabile, tengo
ferme le altre, ascolto. Ma la stessa sintassi dovrà reggere la
**composizione** — molti gruppi di stream, ognuno con la propria evoluzione
formale nel tempo — e non voglio inventare un secondo linguaggio per comporre.

Il problema concreto: scrivere `stack_1-50smp/study.yml` è diventato contorto.
Per far dipendere un parametro da un valore devo scavare in path profondi, e lo
stesso numero compare in più punti senza essere collegato. Voglio poter dire una
cosa **una volta** e riferirla da più punti — manopole condivise da cui più
gruppi leggono, ognuno con la propria formula.

Quello che mi serve da te è capire se la superficie YAML può reggere questo, e
cosa andrebbe cambiato perché lo regga bene.

## L'obiettivo

Un documento di design che risponda a: **come dovrebbe essere fatta la sintassi
di `study.yml` perché parametri e gruppi si possano accoppiare attraverso
manopole dichiarate una sola volta, e perché scrivere uno studio composito resti
leggibile?**

L'asse portante è quello delle manopole globali. Ma il mandato è più largo:
tutto ciò che rende `stack_1-50smp/study.yml` faticoso rientra — inclusi i tre
`base` annidati, i path come `axes.density.base.base`, e il fatto che un nome
possa suggerire una cosa mentre il codice ne fa un'altra.

Voglio trade-off, non una raccomandazione sola. Dove proponi qualcosa che rompe
la sintassi esistente, va bene — ma dimmi cosa si guadagna e quanto costa
migrare (ci sono 9 cartelle-studio e un diario di ascolto ancorato a render
specifici).

Non scrivere codice di produzione: il documento è il deliverable.

## Cosa è già stato verificato eseguendo

Questi risultati vengono da test eseguiti, non da lettura del codice. Puoi
partire da qui invece di riderivarli — ma se qualcosa ti sembra sbagliato,
verificalo e dimmelo.

1. **`spread` accetta solo `n` e `over`** (`src/granstudies/spread.py:42`,
   `_SPREAD_KEYS`). Non c'è nessun altro slot.

2. **La banda-let dentro `spread.over` non è un envelope temporale.** In
   `_let_band` (`spread.py:149`) una variabile di `let` in forma banda produce
   **uno scalare per stream generato**, non una forma nel tempo. In
   `stack_1-50smp/study.yml:122-130` quella variabile si chiama `env`, il che
   suggerisce il contrario.

3. **Una entry-spread può portarsi il proprio `axes:`.** `proto`
   (`spread.py:650`) copia nei generati tutto ciò che non è la chiave `spread`,
   quindi un `axes:` scritto accanto a `spread:` arriva intatto a ogni generato
   e fa deep-merge sopra l'`axes:` globale. Ne emerge un pattern a tre livelli —
   `axes:` globale (default comuni) / `axes:` di gruppo (forma di quel gruppo) /
   `spread.over` (differenziazione per voce) — verificato anche con due gruppi
   che hanno camminate-X diverse nello stesso documento (0.5 Hz → 5 breakpoint,
   8 Hz → 80).

4. **Le variabili globali esistono già, ma legate al processo sbagliato.**
   `versions:` con un valore unico (`versions: {G: {values: [25]}}`) è di fatto
   una costante globale: dichiarata una volta, iniettata in ogni `let` che la
   nomina, con ogni stream libero di usarla nella propria formula (`expr: "G"`
   → 25, `expr: "G * 4"` → 100, nello stesso documento). Il prezzo è che gli
   `stream_id` si portano il suffisso `__G=25` e il documento passa da
   `make versions` invece di `make stack`.

5. **Vincolo di n-ownership fra livelli:** se l'`axes:` globale dichiara `n` e
   un gruppo usa una camminata-X propria, `n` eredita e collide (il conteggio ha
   un solo proprietario). In composizione il padre globale va tenuto magro.

6. **Con la camminata-X i valori non stanno nello spec:** nascono al build dello
   stack (`band_at` sui tempi reali, `src/granstudies/stack.py:46`). Per
   ispezionarli va costruito il documento engine, non basta `resolve_streams`.

Non è stato verificato: come `gain_compensation` si comporta su gruppi con
livelli molto diversi (serve audio vero, non solo struttura).

## Come voglio che tu lavori

Verifica eseguendo. Oggi ho scoperto due cose solo perché ho lanciato del
codice — che `env` era uno scalare, e che `n` nel padre collide con la
camminata — e in entrambi i casi la lettura della documentazione mi aveva
portato altrove. Scrivi test usa-e-getta in scratchpad per provare ogni
affermazione che fai sul comportamento attuale del sistema.

Nel documento, separa esplicitamente **quello che hai verificato eseguendo** da
**quello che hai dedotto leggendo**. Un'affermazione non verificata va marcata
come tale, non arrotondata a certezza.

I test girano con `PYTHONPATH=src python3.11 -m pytest`. La suite del repo è in
`tests/` ed era verde al 2026-07-22.

## Confini

Nel repo ci sono moduli — `states.py`, `kinship.py`, `walk.py`, `compose.py`,
`descriptors.py`, `curation.py` — generati da un comando e mai vagliati né usati.
Le fasi corrispondenti sono commentate in `make/studies.mk`. Non sono design
consolidato e non fanno parte di questo lavoro: non costruirci sopra e non
trattarli come scelte mie.

Quando descrivi il problema attuale, la domanda è come dovrebbe essere fatta la
sintassi — non come riscrivere un singolo file. Se proponi una forma nuova,
mostrala su `stack_1-50smp` come dimostrazione, ma il punto è la superficie, non
quel file.

Se una modifica che proponi cambia la sintassi osservabile dello YAML, includi
una sezione su cosa implica per [gl-ls](https://github.com/DMGiulioRomano/gl-ls),
il language server che valida questi documenti: quali diagnostiche diventano
obsolete, quali regole nuove servirebbero. Non aprire issue — segnala e basta.

## Dove guardare

- `studies/stack_1-50smp/study.yml` — il caso concreto
- `docs/study-yml-reference.md` — la reference della sintassi (lunga; è la fonte
  su intenzioni e vocabolario, ma il codice è la fonte sul comportamento)
- `src/granstudies/` — in particolare `spread.py`, `versions.py`, `stack.py`,
  `expr.py`, `value_generators.py`, `study_spec.py`
- `CLAUDE.md` e `CONTEXT.md` — stato reale del progetto e glossario

## Come scrivere il documento

Apri con l'esito: cosa proponi e perché, prima di qualunque analisi. Chi legge
deve capire la proposta dalla prima pagina e poi decidere se scendere nei
dettagli.

Scrivilo in italiano. Niente emoji.

Salvalo in `docs/plans/`.
