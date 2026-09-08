# Riferimento: `study.yml`

Sintassi completa con tutti i campi. I campi marcati `*` sono obbligatori.

```yaml
 study_id: study01                # * etichetta per i documenti generati (fallback: nome cartella STUDY)
title: "Studio 01 — ..."          # libero, finisce nell'header dei file generati
seed: 1988                        # seed globale engine (finisce nei documenti generati)
# NIENTE `duration:` qui. La durata del *documento* non si dichiara: è dedotta,
# `max(onset + duration)` sugli stream. La durata di uno *stream* si scrive
# accanto allo stream (`base.duration`, vedi sotto). Un `duration:` top-level
# è un errore, con messaggio che indica dove spostarlo (issue #42).
samples_dir: samples              # path relativo alla root del repo (default: samples/)

let:                              # opzionale — manopole di documento: nomi condivisi,
  g0: 4                           #   dichiarati una volta e letti per nome da piu' expr.
  d0: 25                          #   Iniettate al load; versions/percorso le ombreggiano.
                                  #   Vedi la sezione "Manopole: i blocchi let:" sotto.

gain_compensation:                # opzionale — pareggia il mascheramento fra stream che
  alpha: 0.7                      #   leggono punti diversi dello stesso buffer.
  max_shift: 24                   #   Assente = nessuna compensazione (vedi sotto).

# Parametri fissi dello stream: tutto ciò che non è un asse.
base:                             # *
  onset: 0
  duration: 30                   # durata di default (s) di ogni stream: chi non ne
                                 #   dichiara una propria (override in `streams:`) eredita
                                 #   questa. Con `stack:` ogni stream deve risolverne una.
  sample: corpus.wav             # *
  time_mode: normalized
  volume: -6
  grain:
    envelope: hanning
  pointer:
    speed_ratio: 0
    start: 0.3

# Assi (parametri sotto osservazione). axes conosce solo Y: quali parametri si
# muovono, con che valori e con che curva. Il timing (plateau/transition) è del
# processo sweep e vive sotto `sweep:`.
axes:                             # * almeno un asse
  interpolation: linear          # linear | cubic | step (default studio, default linear)
                                 # step: nessuna rampa, ogni valore è tenuto e salta
                                 # netto al successivo. È il DEFAULT ereditato dagli assi
                                 # che non specificano un proprio `interpolation`.
                                 # Ogni asse può fare override (vedi sotto): nello stesso
                                 # file assi diversi possono avere forme diverse.
                                 # Collasso durata (plateau ignorato, stream = N*transition,
                                 # un solo punto per valore) SOLO se TUTTI gli assi mossi
                                 # del file sono step; in caso misto la durata resta piena
                                 # (N*plateau + (N-1)*transition) e l'asse step tiene-e-salta
                                 # sui confini di plateau, sincronizzato con gli altri.

  density:                       # nome dell'asse (libero). Se 'path' e' omesso,
                                 # la chiave stessa e' il path engine — anche in
                                 # dot-notation (es. 'grain.duration:').
    path: density                # path YAML nell'engine; opzionale, alias della chiave
    baseline: 20                 # valore a riposo; obbligatorio se l'engine non ha default
    values: [5, 10, 20, 50]      # * i valori di test. UNA sola chiave-generatore per asse
                                 # tra {values, ramp, base} (vedi "Generatori" sotto).
                                 # values = lista esplicita (rimpiazza, non concatena).
    interpolation: step          # opzionale: override per-asse (default = quello di studio)

  grain.duration:                # chiave dotted = path engine, niente 'path' esplicito;
                                 # i riferimenti in sweep.orderings/stack usano la
                                 # stessa stringa dotted
    # baseline omesso → risolto dal default engine
    n: 40                        # banda piatta: base/range/n/seed accanto alla chiave
    base: [[0, .001], [1, .05]]  # la banda [base, base+range] genera i valori
    range: .002
    interpolation: cubic         # es. density a scalini + grain morbido nello stesso file

# Configurazione dello sweep (il processo possiede X: timing e durata derivata).
sweep:
  mode: envelope                 # discrete | envelope | both (default discrete)
  plateau: 5                     # secondi di ascolto stabile per valore (default 5.0)
  transition: 5                  # secondi di transizione tra plateau (default 5.0)
                                 # Lo sweep fa SOLO il prodotto cartesiano (N^k plateau).
                                 # Per muovere assi INSIEME (accoppiati) si usa il
                                 # processo `stack:` (stessa strategy-X, stesso n).
  orders: [1, 2, 3]             # ordini automatici: 1=OAT, 2=coppie, 3=terzine…
                                 # DEFAULT condizionato se `orders` e' assente:
                                 #   - senza orderings -> [1..n] (copertura piena)
                                 #   - con orderings   -> [] (solo gli orderings)
                                 # `orders: []` esplicito + orderings vuoto = silenzio.
                                 # `orders` e' additivo agli orderings (dedup per
                                 # sequenza esatta); e' ERRORE se, con orderings
                                 # popolato, non aggiunge nessuna combinazione nuova.
  orderings:                     # permutazioni esplicite (min 2 assi per voce)
    - [density, grain.duration]                # primo = asse lento (outer), ultimo = veloce (inner)
    - [grain.duration, density]                # stessa coppia, ordine invertito

# Processo versions (attivo per presenza; richiede `stack:`): repliche dello
# stack distribuite nel tempo, una per combinazione delle variabili — di
# default concatenate, con le chiavi riservate `onset`/`duration` posizionate
# liberamente. Vedi la sezione "Il blocco versions" sotto.
versions:
  d: {values: [1, 2, 3]}          # variabile -> generatore Y (values | ramp | banda con n)
  onset: {values: [0, 10, 40]}    # chiave riservata (opzionale): posizioni assolute
  duration: 8                     # chiave riservata: passo di concatenazione E default
                                  #   degli stream della versione. Uno scalare vale per
                                  #   tutte le versioni; un generatore (values/ramp/banda)
                                  #   dà una durata per versione. Senza `versions.onset`
                                  #   né `versions.duration` non c'è un passo: errore.

# Processo percorso (attivo per presenza; richiede `stack:`): istanze di
# spread distribuite sul tempo reale — i valori cambiano insieme, appaiati,
# nessun prodotto cartesiano. Vedi la sezione "Il blocco percorso" sotto.
percorso:
  arco: 180                       # strategy camminata: estensione totale...
  passo: {base: [30, 8]}          #   ...e legge dell'intervallo (XOR: `onset:` enumerato)
  duration: 1.3                   # traiettoria riservata, unit factor (default) | s
  w: {base: [0, 1], range: .1}    # traiettoria -> iniettata nei let che la nominano

# Processo stack (attivo per presenza del blocco): tutti gli stream sommati in
# UN documento multi-stream. Vedi la sezione "Il blocco stack" sotto.
stack:
  seed: 42                       # seed-X globale (chiave riservata; opzionale)
  unit: s                        # unita' globale della banda (chiave riservata;
                                 #   hz = frequenza, default | s = periodo in
                                 #   secondi | bpm = battiti al minuto)
  nome_asse:                     # un asse con camminata-X: la X possiede n, la
    base:  [[0, 20], [1, 4]]     #   sua Y dev'essere una banda senza n. base/range
    range: [[0, 5], [1, 1]]      #   nell'unita' scelta (qui: secondi tra breakpoint)
    seed: 7                      # seed-X per-asse (vince sul globale)
    unit: s                      # unit per-asse (vince sul globale; opzionale)
  # asse assente dal blocco -> linear (n dai valori Y). Dettagli: sezione "stack".

# Stream: varianti di ascolto con override parziali sul documento sopra.
# Regole del merge: i dict si fondono ricorsivamente, le liste rimpiazzano.
# Le chiavi PUNTATE si espandono in dict annidati prima del merge, come in
# `spread.over`: `axes.density.base.expr: X` equivale a
# `axes: {density: {base: {expr: X}}}` (rami sovrapposti si fondono).
# Sotto `axes.`/`stack.` il primo identificatore è un NOME D'ASSE, che può
# essere a sua volta dotted (`axes.grain.duration.values` raggiunge l'asse
# `grain.duration`): il confine si risolve sugli assi dichiarati in `axes:`,
# poi sul registro parametri engine (un override può introdurre un asse
# dotted nuovo), altrimenti sul primo segmento. Due assi dichiarati con
# prefisso comune (`grain` + `grain.duration`) rendono la forma puntata
# ambigua → errore; lì si usa la forma annidata (`axes: {grain.duration:
# {...}}`, sempre valida). Se questa sezione è assente, sweep genera
# un'unica versione senza sotto-cartella.
streams:
  base: {}                       # nessun override — identica alla base

  fermo:                         # override in forma PUNTATA (equivale all'annidata)
    axes.density.base.expr: "env"  # cambia solo l'expr; il let si eredita dal merge

  nome_stream:                   # chiave libera → diventa la sotto-cartella dell'output
    duration: 60                 # durata propria (s): vince su base.duration
    onset: 5                     # posizione (s) dello stream nella timeline (default 0).
                                 # SOLO per-stream: `onset:` al top-level del documento
                                 # è rifiutato. Con `versions:` è relativo alla versione.
    base:                        # override parziale di base (deep-merge)
      volume: -3
      pointer:
        start: 0.7               # sovrascrive solo start; gli altri campi restano
    axes:                        # override parziale di axes
      density:
        values: [100, 200, 300]  # rimpiazza l'intera lista
    sweep:                       # override parziale di sweep
      orders: [1, 2]             # es. salta le terzine
      plateau: 10                # cambia il plateau per questa stream
    stack:                       # override parziale di stack (deep-merge)
      seed: 43                   # es. riseeda solo i tempi di questa stream

  ventaglio:                     # entry-spread: genera n stream con una regola
    spread:                      # (chiave riservata; vedi la sezione "spread")
      n: 8
      over:
        base.pointer.start:
          ramp: {start: 0.1, step: 0.1}
```

## Le quattro `duration` (issue #42)

Ogni `duration` sta **accanto alla cosa di cui è la durata**. Non esiste una
`duration:` al top-level del documento: si chiamava "durata del documento" e
non lo è mai stata — la durata del documento è sempre **dedotta**,
`max(onset + duration)` sugli stream costruiti.

| Cos'è | Dove si scrive | Chi la legge |
|---|---|---|
| durata di **uno stream** (default di documento) | `base.duration` | tutti i rami (stack/sweep/versions/percorso) |
| durata di **uno stream** (override) | `duration:` di una entry di `streams:` | vince su `base.duration` |
| durata / **passo** di una versione | `versions.duration` | `versions:` — passo di concatenazione *e* default degli stream della versione |
| durata di una **istanza** di percorso | `percorso.duration` (o dedotta da `arco`/`passo`) | `percorso:` — default degli stream dell'istanza |
| durata del **documento** | *non si scrive* | dedotta: `max(onset + duration)` |

Precedenza per la durata di uno stream: `duration:` di entry **>**
`base.duration`. Nei processi che posizionano repliche (`versions`/`percorso`),
la durata di versione/istanza è iniettata come `base.duration` del documento di
quella replica, quindi fa da default e una `duration:` di entry la scavalca.

Simmetrico con `onset`: `base.onset` è il default di documento, `onset:` di
entry è l'override, e `onset` al top-level è **vietato** allo stesso modo.

Un `duration:` al top-level del documento è un **errore**, con un messaggio che
indica dove spostare la chiave (`base.duration` per la durata di stream,
`versions.duration` per il passo delle versioni). Vale in **tutti** i rami:
anche uno studio con `versions:` o `percorso:`, dove la durata di replica viene
iniettata come `base.duration`, viene fermato allo stesso modo — il divieto non
dipende da quali altre chiavi sono presenti. Nota: i documenti *engine generati*
(`generated/.../yaml/...`) hanno un `duration:` di documento — è l'output
dedotto, quello che l'engine richiede, non l'input `study.yml`.

Concatenare le versioni richiede `versions.duration`: senza né
`versions.onset` né `versions.duration` è un **errore**, e `base.duration` non
vale come ripiego — è la durata di uno stream, non il passo delle versioni.
Nel blocco `versions:`, `onset` e `duration` accettano anche uno **scalare**
(broadcast su tutte le versioni): su `duration` è il passo costante, la forma
comune; su `onset` significa tutte le versioni allo stesso istante, cioè
sovrapposte.

## I due ruoli di una lista: `values:` e `linear_env:`

Una lista di numeri significa due cose diverse a seconda del **ruolo** che ha
nel punto in cui è scritta, e il vocabolario dei generatori
(`values` / `ramp` / banda) non lo dice: dice solo **da dove vengono i numeri**.

| Ruolo | Come si legge | Marcatore |
|---|---|---|
| **serie indicizzata** | la posizione *k* è l'elemento *k* — i valori di test di un asse, un valore per voce, una sequenza di versioni | `values:` (o `ramp`/banda) nella posizione che la ospita |
| **forma nel tempo** | i valori diventano i **breakpoint** di un envelope su tempi equispaziati, e il valore in mezzo esce dall'interpolazione | il wrapper `linear_env:` |

Nella maggior parte dei contesti la posizione disambigua da sola. In un `let:`
no: i due ruoli sono plausibili allo stesso livello di annidamento, con la
stessa forma, senza nessun indizio. `{values: [2, 3, 4, 7]}` in un `let:`
produceva un envelope — a `t = 0.5` il valore era `3.5` — mentre un lettore
ragionevole ci vedeva una lista. Di qui la separazione: **`values:` resta il
marcatore della serie indicizzata, la forma nel tempo si marca con
`linear_env:`.**

`linear_env:` è un **wrapper di ruolo**, non una chiave-generatore: dentro
accetta l'intero vocabolario, così anche le forme *generate* hanno il loro
marcatore invece di restare nude.

```yaml
let:
  sagoma:  {linear_env: [2, 3, 4, 7]}                        # lista esplicita
  identica: {linear_env: {values: [2, 3, 4, 7]}}             # la forma lunga
  curva:   {linear_env: {ramp: {start: 1, stop: 8, step: 1}}}
  pescata: {linear_env: {n: 6, base: 2, range: 6, seed: 42}}
  a_scatti: {linear_env: [0, 1, 0], type: step}              # type/curve ACCANTO
```

`type` e `curve` stanno **accanto** al wrapper, non dentro: descrivono
l'envelope prodotto, non il generatore — e una lista letterale non avrebbe
dove ospitarli. Metterli dentro è errore esplicito.

**Dove serve `linear_env:`** (i tre contesti in cui una lista si legge per
tempo):

| Contesto | Esempio |
|---|---|
| un bordo di `Env`: `base`/`range` di banda Y, `base`/`range` della camminata-X, `step` di `ramp`, `step` di `drift` | `base: {linear_env: [0, 10]}` |
| `let:` di documento e di gruppo | `respiro: {linear_env: {ramp: {...}}}` |
| un bundle di `versions:` Forma 2 | `caldo: {respiro: {linear_env: [20, 60]}}` |

**Dove `values:` resta `values:`** (la lista si legge per indice): i valori di
test di un asse, `spread.over.<path>`, le sequenze di `versions:` (Forma 1 e
forma piatta), `versions.onset`/`duration`, `percorso.onset` enumerato.

Sbagliare famiglia è errore in entrambe le direzioni, con il messaggio che
indica la forma giusta. Le forme **statiche** di `Env` (`[a, b]`,
`[[t, v], ...]`, `{type, points, curve}`, la forma compatta a cicli) non sono
generatori e non vogliono nessun wrapper: restano nude.

## Il corredo — `list:`, una lista letta per indice

Il terzo ruolo, accanto ai due di sopra. `values:` si legge per indice ma è
consumato dalla posizione che lo ospita; `linear_env:` si legge per tempo; un
**corredo** è una lista **nominata**, dichiarata in un `let:` e letta solo per
indice, dalle espressioni che la referenziano.

```yaml
let:
  d: 1                              # fondamentale: periodo 1 s = 60 bpm
  ratio: {list: [2, 3, 4, 7]}       # il corredo: quattro rapporti scelti

axes:
  grain.duration:
    base: {expr: "d * ratio[0] / 40"}   # riferito alla fondamentale del corredo
```

Colma il caso che le altre forme non coprivano: un valore **scelto a mano**.
Un valore *pescato* si condivide (banda in `spread.let`), uno *calcolato* pure
(`{expr}` con `i`/`n`), ma una serie **irregolare e decisa dall'autore** — dei
rapporti scelti a orecchio, non una formula — non poteva essere letta da due
assi diversi, perché `values` in `spread.over` scrive su un path solo. Il
corredo vive un livello sopra, nel `let:`, dove non esiste nessun indice e
quindi nessuna pretesa sul conteggio.

**Perché non `values:`.** In un `let:` quella chiave produce un envelope: a
`t = 0.5` il valore sarebbe `3.5`, che per un corredo di rapporti non è un
rapporto sbagliato — è una domanda senza senso, perché fra il terzo e il
quarto rapporto non c'è nessuna voce. **Un corredo è discreto per natura.**

**Perché non la lista nuda.** `ratio: [2, 3]` è già una forma statica di `Env`
(la rampa `[a, b]`): sarebbe una collisione silenziosa, valida in entrambe le
letture, senza errore e con il suono sbagliato — e due voci in rapporto 3:2 è
materiale che si scrive davvero.

### Cosa può stare dentro `list:`

`list:` dichiara il **tipo**; come si producono gli elementi è una domanda
ortogonale, a cui risponde il vocabolario dei generatori già esistente — la
stessa composizione che il sistema fa per i generatori annidati in un `Env`.

```yaml
let:
  scelto:   {list: [2, 3, 4, 7]}                          # a mano
  armonica: {list: {ramp: {start: 1, stop: 8, step: 1}}}  # [1..8]
  pescato:  {list: {n: 5, base: 2, range: 6, seed: 1988}} # 5 rapporti in [2, 8]
```

**La legge: un corredo possiede la propria lunghezza**, quindi il suo
generatore deve possedere un conteggio.

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
possiedono `n` e se lo fanno dare da fuori. Nel corredo **non c'è nessun
fuori**: non eredita mai `n` dallo spread — sarebbe circolare con
`spread.n: {expr: "len(ratio)"}`, impossibile per un corredo di documento che
uno spread non ce l'ha, e svuoterebbe l'oggetto (con `len == n` per
costruzione il fuori range non esiste e il warning `n < len` non si emette
mai).

**Il corredo pescato** apre un caso che prima non esisteva. La banda di
`spread.let` fa un pescaggio *per voce*, e l'insieme non esiste come oggetto:
non se ne può nominare la fondamentale, non si può misurare. Pescato una volta
e poi indicizzato, `ratio[i] / ratio[0]` — ogni voce in rapporto alla prima
estratta — diventa scrivibile. Senza `seed` esplicito il seed si deriva dalla
catena gerarchica, come per ogni altra manopola generata
(`stable_seed("<study>:let:<nome>")` a documento,
`stable_seed("<entry>:let:<nome>")` a gruppo).

I bordi `base`/`range` della banda restano `Env`: dentro ci va `linear_env:`
come sempre. `linear_env:` **direttamente** dentro `list:` è invece errore —
i due wrapper marcano ruoli opposti.

### `cycle:` — accordo o pattern

```yaml
let:
  ratio:  {list: [2, 3, 4, 7]}                # accordo: insieme finito
  durate: {list: [1, 1, 2], cycle: true}      # pattern: si ripete
```

Non è un flag di comodo: sono **due oggetti compositivi diversi**. Un accordo
è un insieme fisso di rapporti — se ne chiedi il quinto, la domanda è
sbagliata. Un pattern è periodico per natura — il quinto elemento *è* il
primo, come in un ciclo ritmico. Che il primo dia errore fuori range e il
secondo si avvolga non è una regola arbitraria: è la differenza fra i due
oggetti.

Il default è l'accordo: un corredo senza `cycle:` è un insieme finito.

La politica la decide il **corredo**, non il punto d'uso, e vale
uniformemente per gli indici costanti e per quelli calcolati. Su un corredo di
4 elementi `ratio[9]` è errore se è un accordo e vale `ratio[1]` se è un
pattern, esattamente come `ratio[i]` con `i = 9`. Se la regola dipendesse
dall'essere l'indice costante o calcolato, tornerebbe a dipendere dall'uso.

Su un pattern gli **indici negativi** restano coerenti senza un caso speciale:
il modulo di Python li porta con sé (`-1 % 4 == 3`).

`cycle:` senza `list:` è errore — è la politica di un corredo, non un valore a
sé. E `{list: [], cycle: true}` resta errore alla dichiarazione, come ogni
corredo vuoto: qui sarebbe anche un modulo per zero.

#### I due casi che rende scrivibili

**L'ispessimento.** Tre voci per rapporto, ognuna che legge un punto diverso
del buffer: stesso periodo, contenuto e fase diversi — l'accordo si
ispessisce senza cambiare le altezze.

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

**L'isoritmo.** Due corredi ciclici di lunghezze coprime scorrono uno contro
l'altro: il pattern (rapporto, durata) ha periodo `lcm(4, 3) = 12`. È **color
e talea**, e cade fuori da due `cycle: true` senza sintassi dedicata.

```yaml
let:
  ratio:  {list: [2, 3, 4, 7], cycle: true}   # color, len 4
  durate: {list: [1, 1, 2],    cycle: true}   # talea, len 3
spread:
  n: 12
  let:
    r: {expr: "ratio[i]"}
  over:
    duration: {expr: "durate[i] * 8"}
```

> Nota sullo scope: `spread.let` e `spread.over` sono **fratelli**, calcolati
> indipendentemente; le manopole di voce sono iniettate negli stream generati
> solo *dopo* che `over` è stato scritto sui path, quindi quando `over` viene
> valutato `spread.let` non esiste ancora. Il corredo di **gruppo** è invece
> già in scope lì — le manopole di gruppo si iniettano nelle espressioni
> dell'entry prima dell'espansione — quindi `over` lo legge direttamente.

Le singole coppie si ripetono prima della voce 12 (`(2, 1)` torna già alla voce
4), perché `durate` contiene due volte il valore `1`: è la **sequenza** ad avere
periodo `lcm`, cioè la relazione di fase fra color e talea. Nella talea i valori
si ripetono eccome — è la descrizione musicalmente corretta.

### Il warning `n < len`

Un corredo **sotto-consumato** — lo spread genera meno voci di quanti elementi
ha il corredo — è legittimo: si sta ascoltando un sottoinsieme dell'accordo. È
però anche il sintomo più comune di un refuso, quindi il sistema lo segnala
senza fermarsi:

```
[warn] corredo-sotto-consumato

  posizione:  studies/cugini/study.yml:14  (streams.cugini.let.ratio)
  contesto:   stream 'cugini'
  problema:   il corredo 'ratio' del gruppo 'cugini' ha 4 elementi, ma lo
              spread genera 2 voci: gli elementi da indice 2 non sono usati.
  rimedio:    è legittimo (un sottoinsieme dell'accordo); per consumarlo
              tutto scrivi "n: {expr: 'len(ratio)'}".
```

Caratteristiche:

- **per corredo**, non per gruppo: con due corredi di lunghezza diversa uno può
  essere sotto-consumato e l'altro no;
- solo per i corredi che quel gruppo legge **per voce** (con un indice che
  dipende da `i`). Un corredo letto con il solo indice costante — `ratio[0]`,
  la fondamentale — non è sotto-consumato da nessun `n`;
- si emette alla **generazione** (`sweep`/`stack`/`versions`/`percorso`), non
  al `render`: il corredo si risolve al load, e le posizioni nello YAML
  esistono solo lì;
- va su **stderr** e **non** cambia l'exit code.

Nessun warning quando `n == len`, né quando `n > len` — quello è errore su un
accordo e silenzio su un pattern, in nessuno dei due casi materia di questo
rilievo.

**Il limite, da conoscere.** Il controllo è statico solo nel caso semplice.
Con `spread.n` letterale, `{expr: "len(ratio)"}` o un'espressione sulle
manopole del `let:` è decidibile senza generare niente. Con `spread.n` mosso da
`versions:` o da `percorso:` dipende dal prodotto cartesiano o dalle istanze:
il rilievo si emette allora **una volta per combinazione**, con deduplica — due
combinazioni che dicono la stessa cosa danno un rilievo solo, ma due `n` diversi
restano due fatti diversi. Quando `n` dipende da qualcosa che il riposo non
conosce, il controllo tace invece di indovinare.

### Corredi mobili: `versions:` e `percorso:`

Un asse di `versions:` può sostituire un corredo, così da confrontare
all'ascolto due insiemi di rapporti — due intonazioni, due accordi, due tagli
dello stesso materiale:

```yaml
let:
  ratio: {list: [2, 3, 4, 7]}       # il riposo

versions:
  intonazione:
    giusta:  {ratio: {list: [2, 3, 4, 7]}}
    stretta: {ratio: {list: [2, 3, 4]}}
```

Con `spread.n: {expr: "len(ratio)"}` la popolazione **segue il corredo**:
quattro voci in una versione, tre nell'altra. Il pad dei nomi resta stabile
sull'intero prodotto cartesiano (`cugini_1 … cugini_4` e `cugini_1 …
cugini_3`), e la voce mancante consuma in silenzio una patch che la nomini.

**La regola: il tipo lo fissa la dichiarazione.** `versions:` muove il
*valore* di una manopola, mai il suo tipo né la sua politica. Uno stato che
sostituisce un corredo deve fornire un corredo, e della **stessa politica di
`cycle`** — altrimenti la validità dello studio cambierebbe da una versione
all'altra, e un fuori range comparirebbe solo in alcune combinazioni. Entrambe
le violazioni sono errore al load.

Vale identico per `percorso:`: una traiettoria è una legge sul tempo, non una
lista, quindi non può muovere un nome dichiarato come corredo. `spread.n` può
invece cambiare per istanza come sempre, e `{expr: "len(ratio)"}` continua a
seguire il corredo del riposo.

`make stack` continua a ignorare `versions:` — resta analisi — e usa il
corredo dichiarato in `let:`, cioè l'istanza di partenza.

### Dove vive

| Blocco | Corredo ammesso |
|---|---|
| `let:` di documento | sì — condiviso da più gruppi |
| `let:` di gruppo | sì — il caso tipico |
| `spread.let` | no |
| il `let` interno di un nodo-expr | corredo **letterale** sì, **generato** no |

Più corredi nello stesso `let:` sono ammessi.

Nel `let` **locale** di un nodo-expr la riga si divide in due. Un corredo
*letterale* è ammesso: è un valore statico come `[[0, 1], [1, 2]]`, che quel
`let` accetta già. Un corredo *generato* è errore, perché il `let` locale entra
nello scope com'è scritto — nessuna seam lo espande — quindi il generatore non
verrebbe mai eseguito e non avrebbe un seed da cui pescare. Va dichiarato in un
`let:` di documento o di gruppo, che lo risolve al load e lo inietta già fatto.

### L'indicizzazione

`nome[expr]` è una produzione della grammatica di `expr`. L'indice è
un'espressione qualsiasi purché valuti a un **intero**: un indice frazionario è
errore, e la quantizzazione si scrive con `//` o `floor()`, che sono già in
grammatica. Un indice **costante** funziona in ogni scope in cui il corredo è
visibile — `ratio[0]` in un `axes:` è legittimo e verificabile al load.

### L'indice della voce

Dentro uno `spread:` l'indice naturale è `i`, che lo spread già fornisce agli
`expr` di `spread.let` e delle strategy `expr` di `over`. È lì che il corredo
dà il suo risultato: **una voce, un elemento**.

```yaml
streams:
  accordo:
    let:
      ratio: {list: [2, 3, 4, 7]}
    spread:
      n: 4
      let:
        r: {expr: "ratio[i]"}          # il rapporto di QUESTA voce
      over:
        base.pointer.start: {values: [0.1, 0.3, 0.5, 0.7]}
    axes:
      density:
        base: {expr: "d * r"}          # periodi 2s, 3s, 4s, 7s
```

Un corredo di **documento** è leggibile da due gruppi diversi, ognuno con il
proprio `i`.

**Indici negativi**: `ratio[-1]` è l'ultimo, `ratio[-len]` il primo — servono a
invertire il senso di lettura (`ratio[-1 - i]`). Oltre la lunghezza, in
entrambi i versi, è errore.

**Il possesso di `n` non cambia.** Il corredo non possiede mai il conteggio
della popolazione, nemmeno quando è l'unico indicizzato: `n` resta di
`over`/`spread.n`. Ne segue che

- `spread.n > len` su corredo finito è **errore** alla voce che esce dal
  corredo, con la voce, il nome del corredo e la lunghezza nel messaggio;
- `spread.n < len` **non** è errore: un corredo sotto-consumato è legittimo —
  si sta ascoltando un sottoinsieme dell'accordo.

### `len(nome)`

Una primitiva a parte, che accetta **solo un corredo**, per nome. Serve a due
cose:

```yaml
spread:
  n: {expr: "len(ratio)"}                    # legare la popolazione al corredo
  let:
    r:   {expr: "ratio[i % len(ratio)]"}     # il ciclo scritto a mano
    ott: {expr: "2 ** (i // len(ratio))"}    # ...e i giri contati
```

La prima è l'unico modo di garantire che `n` e la lunghezza non si
disallineino, e va nella direzione ammessa — **il corredo può dare `n`, non
prenderlo**: non è circolare, perché il corredo si risolve al load, prima
dell'espansione dello spread. La seconda dà tre ottave dello stesso accordo in
due righe, con `%` e `//` che erano già in grammatica.

`len` di un envelope è **errore**, non «quanti breakpoint ha»: quello è un
dettaglio di rappresentazione — a parità di intenzione `expand_env` può
produrne un numero diverso — e farlo trapelare renderebbe le espressioni
dipendenti dall'implementazione. Errore anche su uno scalare, su un nome
inesistente e su un'espressione (`len(2 + 2)`): l'argomento è un nome.

**La linea di confine, dichiarata:** *una lista non è mai un valore*. Può
comparire **solo** come `nome[expr]` o `len(nome)`. Non si passa a una funzione, non ci si fa
aritmetica, non si restituisce — `ratio * 2` e `min(ratio, 2)` sono errore.
Due produzioni, non una famiglia aperta. Così
il tipo di ogni espressione resta `scalare | Env` come prima, e i corredi sono
un namespace di dichiarazione separato.

### Le guardie

- **corredo vuoto** (`{list: []}`) → errore alla dichiarazione, con il nome nel
  messaggio: non c'è niente da indicizzare;
- **elementi non scalari** → errore (i corredi di sagome sono rimandati);
- **indice fuori range** su un accordo → errore che nomina il corredo, la sua
  lunghezza e la forma per farne un pattern (su un pattern non c'è fuori
  range: l'indice si avvolge);
- **indicizzare un nome che non è un corredo** → errore che dice cos'è;
- **corredo non referenziato** → errore, per estensione della guardia
  anti-refuso esistente: `ratio[0]` registra `ratio` fra i nomi referenziati,
  quindi la guardia non ha richiesto modifiche;
- **ombreggiatura fra livelli** → errore, come per ogni manopola.

## Generatori di valori d'asse

I valori di test di un asse si danno con **esattamente una** chiave-generatore
tra `values`, `ramp`, `base` (mutuamente esclusive: zero o più di una è errore).
Il generatore si riconosce dalla **forma**, non più da un wrapper con nome: la
presenza di `base` marca la banda. In una stream, il generatore dell'override
rimpiazza quello ereditato sullo stesso asse (non si sommano); passare a
`values`/`ramp` toglie anche le chiavi della banda ereditate.

### `values` — lista esplicita

```yaml
values: [5, 10, 20, 50]        # i valori così come sono
```

### `ramp` — rampa aritmetica

```yaml
ramp: {start: 5, stop: 100, step: 5}   # 5, 10, 15, ..., 100
```

- `step` deve essere `> 0`. La direzione si deduce da `start`/`stop`
  (discendente se `start > stop`).
- Uno `stop` che cade sulla griglia è incluso; uno che non ci cade non viene
  mai oltrepassato (conteggio intero anti-drift float).
- `step` è un **`Env`** (le stesse forme di `base`/`range`, generatori annidati
  compresi): con un `step` mobile la rampa accelera o ritarda. È letto sul
  **progresso in valore** `|v − start| / |stop − start|`, non sull'indice: il
  numero di gradini emerge dall'integrazione. Un `step` che tocca `0` è errore;
  tetto anti-runaway sui punti generati. Il caso scalare resta identico.

```yaml
ramp: {start: 5, stop: 100, step: [10, 1]}   # accelerando: i passi si stringono
ramp: {start: 5, stop: 100, step: [1, 10]}   # ritardando: i passi si allargano
```

### `base` — banda, seeded (piatta sull'asse)

`n` valori estratti uniformemente dentro una banda `[base, base + range]` che
può essere fissa o mobile lungo la sequenza. Le chiavi stanno **piatte** nel
dict dell'asse (accanto a `path`/`baseline`/`interpolation`), non più sotto un
wrapper. Deterministico: stesso `seed` → stessa sequenza (serve al ciclo
rigenera-e-confronta).

> **Tre `base` diversi.** La parola compare in tre punti che non c'entrano tra
> loro: la chiave di banda `base` qui descritta (pavimento della banda, marca il
> generatore); il blocco engine `base:` di uno stream (override di parametri a
> riposo, es. `base: {volume: 0}` per mutarlo); e l'eventuale stream *chiamato*
> `base` in `streams:` (solo un id). Con i generatori annidati se ne aggiunge
> un quarto: il `base` **dentro** un bordo di banda (`base: {n: 6, base: 2, ...}`,
> il pavimento del pavimento — vedi «Generatori annidati» sotto). I livelli sono
> distinti nello YAML, ma leggendo un file conviene tenerli separati in testa.

```yaml
density:
  path: density
  n: 50                        # quanti valori (>= 1); OMESSO se la X è una camminata (vedi stack)
  base: .001                   # estremo inferiore della banda (vedi forme sotto)
  range: .009                  # ampiezza della banda; opzionale (default 0 = banda
                               # collassata: la sequenza segue `base` deterministicamente)
  seed: 1988                   # opzionale (default: `axes.seed`, poi auto per-stream)
  distribution: gaussian       # opzionale: come si pesca (uniform, il default | gaussian)
  drift: {step: 0.1}           # opzionale: pescaggio correlato (random walk, vedi sotto)
```

`n` appartiene a chi possiede il conteggio dei punti (*n-ownership*): con la
camminata-X del processo stack i tempi — e quindi `n` — emergono dalla frequenza
(o dal periodo, con `unit: s`), e la banda Y va dichiarata **senza** `n` (viene
campionata ai tempi reali dei breakpoint). Fuori da quel caso `n` è obbligatorio.

`base` e `range` sono un **envelope di 2° ordine** (una banda che genera
valori); un `range` negativo in un punto della sequenza è errore. Ognuno dei
due accetta queste forme:

| Forma | Significato |
|-------|-------------|
| scalare `.003` | banda a livello costante |
| `[a, b]` | rampa lineare `a → b` lungo la sequenza (esattamente due scalari) |
| `[[t, v], ...]` | breakpoint temporizzati, `t` in `[0, 1]`, interpolati **linear** (hold fuori dai bordi) |
| `{type, points, curve}` | breakpoint con `type` esplicito (`linear`/`step`) ed eventuale `curve` (vedi sotto) |
| nodo `{linear_env: ...}` (dentro: lista, `{values}`, `{ramp}` o `{n, base, range, seed}`; accanto: `type`/`curve` opzionali) | breakpoint **generati** invece che scritti a mano (vedi «Generatori annidati») |
| nodo-expr `{expr, let}` | Env **calcolato** da un'espressione aritmetica su sagome e scalari (vedi «Il nodo-expr») |

Esempio con banda mobile (si apre dopo il 60% della sequenza):

```yaml
density:
  n: 50
  base: [[0, 10], [.6, 2], [1, .1]]
  range: [[0, 10], [.6, 3], [1, 2.9]]
  seed: 1988
```

> Nel processo `stack` più assi generati con lo stesso `n` e la stessa strategy-X
> si muovono insieme (breakpoint agli stessi tempi): si sentono più modulazioni
> contemporaneamente, senza il prodotto cartesiano.

### `distribution` — come si pesca dentro la banda

Sibling di `base`/`range` (sia nella banda di Y sia nella camminata-X del
blocco `stack:`): governa **come** si estrae dentro `[base, base+range]`,
indipendentemente dal fatto che il pescaggio sia correlato (`drift`) o no.

- `uniform` (default) — il comportamento storico, ogni punto della banda è
  equiprobabile. Bit-identico ai file generati finora.
- `gaussian` — media al **centro banda**, deviazione standard pari a un sesto
  della larghezza (i bordi cadono a 3 sigma); il ~0.3% di estrazioni fuori
  banda si appiattisce sul bordo (clamp). I valori si addensano sul centro
  invece di riempire la banda uniformemente.

Con banda collassata (`range` 0) non c'è varianza: entrambe seguono `base`.

### `drift` — pescaggio correlato (random walk)

Marcatore sibling di `base`/`range`, valido negli stessi due registri di
`distribution`. Quando presente, il valore non è più un pescaggio indipendente
a ogni punto ma `precedente + passo_casuale` — il «passo dell'ubriaco»: niente
su-e-giù a scatti dentro la banda, ma una deriva organica.

```yaml
drift:
  step: 0.1        # frazione della banda per passo; è un Env: [[0,.02],[.5,.2]]
  seed: 7          # opzionale: deriva dal seed della banda se assente
```

Meccanica:

- **valore iniziale**: il pescaggio di sempre (`uniform`/`gaussian` secondo
  `distribution`), poi da lì in poi cammina;
- **passo**: `step(frac) * larghezza_banda(frac)` — `step` è **frazione della
  banda corrente**, si adatta da solo se la banda si allarga o si restringe.
  `step` è un `Env` (stesse forme di `base`/`range`, **nodi-generatore
  annidati compresi**), consultato a ogni passo sul dominio del registro:
  posizione sull'asse per la banda-Y, tempo reale normalizzato per la
  camminata-X. Negativo in un punto → errore; `0` congela il valore;
- **distribuzione del passo**: la stessa `distribution` della banda —
  `uniform` → passo uniforme in `[-s, +s]`, `gaussian` → passo gaussiano con
  sigma `s`;
- **bordo banda**: **riflessione** — il valore rimbalza su `[base, base+range]`
  invece di appiattirsi;
- **banda mobile**: se la banda trasla e il valore corrente resta fuori,
  clamp immediato dentro i nuovi limiti, poi si riparte a camminare;
- **seed**: l'RNG del passo è separato da quello della banda; senza `seed`
  proprio deriva dalla catena gerarchica (`stable_seed` del seed effettivo
  della banda con salt `:drift`, come per i nodi annidati): cambiare il seed
  della banda rigenera anche la deriva, fissare `drift.seed` congela solo la
  forma della camminata.

Design completo: `docs/plans/done/drift-distribution.md` (issue #16).

### `curve` — piega non lineare del segmento

`curve` vive nella **forma dict** di un `Env` (`base`/`range`) e piega la frazione
locale del segmento prima di interpolare (`u' = u^k`), cioè cambia *come* la banda
si muove tra i suoi breakpoint — non è l'`interpolation` dell'asse (che è come
l'engine unisce i breakpoint *già* generati).

```yaml
base: {points: [[0, 10], [1, 90]], curve: 2}   # sale lento, accelera in coda
```

- `curve: 1` = lineare (default); `> 1` parte lento e accelera; `< 1` parte ripido
  e si appiattisce. Deve essere `> 0`.
- Piega **ogni segmento** indipendentemente (la `u` locale di ciascun tratto).
- Con `type: step` non c'è rampa da piegare: `curve` diverso da 1 è un errore.
- Disponibile ovunque compaia un `Env` — `base`/`range` di X **e** di Y. Nota che
  il `[0, 1]` su cui l'`Env` è letto misura cose diverse: in Y è la posizione del
  punto sull'asse dello stream, in X è il tempo reale normalizzato della
  camminata. La piega è la stessa, il dominio no.
- **`curve` e override di stream.** La forma dict di un `Env` segue la regola
  generale del merge («i dict si fondono»): uno stream che sovrascrive
  `base: {points: [...]}` su una base che aveva `base: {points: [...], curve: 2}`
  **eredita** `curve: 2` — ridefinire i punti non azzera la piega. Per tornare
  alla rampa lineare dichiararlo esplicitamente (`curve: 1`); per rimpiazzare
  l'envelope in blocco usare una forma lista (`[a, b]` o `[[t, v], ...]`), che
  come tutte le liste rimpiazza invece di fondersi.

### Generatori annidati — un bordo di banda generato

I `points` di un bordo (`base`/`range` di banda Y, `base`/`range` della
camminata-X, `step` di `ramp`, `step` di `drift`) si possono **generare**
invece di scriverli a mano: al posto della forma statica si mette un **nodo**
`linear_env:`, che dentro parla la stessa grammatica piatta dell'asse —
`values`, `ramp`, oppure la banda (`n`/`base`/`range`/`seed`) — con le
opzionali `type` (`linear`/`step`) e `curve` **accanto** al wrapper. Il nodo si
compila in breakpoint su tempi equispaziati (X implicita lineare) e da lì in
poi si comporta esattamente come dei `points` scritti a mano. Ricorsivo: i
`base`/`range` del nodo accettano a loro volta nodi (guardia di profondità: 8).

Il wrapper è obbligatorio: qui la lista si legge **per tempo**, ed è
esattamente il ruolo che `linear_env:` marca. Un generatore nudo in questa
posizione è errore, con il rimedio nel messaggio.

```yaml
density:
  path: density
  n: 40
  base:                      # il pavimento vaga: 6 quote pescate tra 2 e 8
    linear_env: {n: 6, base: 2, range: 6}
  range:                     # la larghezza salta a plateau tra 4 e 14
    type: step               # accanto al wrapper: descrive l'envelope prodotto
    linear_env: {n: 6, base: 4, range: 10}
```

E nella camminata-X (frequenza di generazione essa stessa stocastica):

```yaml
stack:
  density:
    base: {linear_env: {n: 8, base: 2, range: 4}}   # la base salta tra 2 e 6 Hz
    range: 0.5
```

Regole:

- **`n` obbligatorio** nella banda annidata (dentro un `Env` non c'è coupling
  X/Y: il nodo deve produrre da solo la sua lista). `ramp` e `values` lo
  posseggono per costruzione.
- **Seed gerarchico.** Un nodo-banda senza `seed` deriva un seed stabile dal
  seed effettivo del generatore padre e dal percorso (`base`, `range`,
  `base.range`, ...): `base` e `range` si decorrelano da soli, cambiare il seed
  esterno rigenera l'intero sottoalbero coerentemente, un `seed` esplicito nel
  nodo congela solo quel sottoalbero.
- **Bordi correlati gratis**: banda che trasla a larghezza costante = `base`
  annidato + `range` scalare (nessun seed da coordinare).
- **`type`/`curve` accanto al wrapper** valgono come nella forma
  `{type, points, curve}`:
  `type: step` fa saltare il bordo tra le quote generate (plateau di banda),
  `curve` piega i segmenti. Solo `linear`/`step` (niente `cubic` nelle bande).
- Il nodo è un dict: negli override di stream **si fonde** come ogni dict
  (ridefinire `base` interno non azzera `type`/`curve` ereditati); per
  rimpiazzare in blocco usare una forma lista.
- Niente arriva all'engine: l'espansione è tutta in granstudies, nello YAML
  engine finisce il solito envelope dell'asse.

Design completo: `docs/plans/done/nested-generators.md`.

### Il nodo-expr — aritmetica su Env

`{expr, let}` è una forma di Env che **calcola** i breakpoint invece di
scriverli o generarli: fattorizza forma e livello di una sagoma, per riusarla
a livelli diversi.

```yaml
axes:
  density:
    n: 4
    base:
      expr: "env * 50"              # sempre tra virgolette
      let:
        env: [[0, 1], [0.1583, 1.5]]   # → [[0, 50], [0.1583, 75]]
    range: 0
```

- **Grammatica**: numeri, nomi, `+ - * / // % **`, meno unario, parentesi,
  l'indicizzazione di un corredo `nome[expr]` (vedi «Il corredo»), le chiamate
  alle **funzioni primitive** e le costanti `pi` / `e`. Niente confronti o
  argomenti keyword — ogni altro costrutto è errore.
- **Funzioni primitive** (whitelist — il set generatore da cui derivare le
  altre): `abs`, `floor`, `ceil`, `sqrt`, `exp`, `log` (naturale, o
  `log(x, b)` per la base), `sin`, `cos`, `tan`, `atan`, `min`, `max`
  (variadiche, almeno 2 argomenti), `mix` (vedi sotto) e `len` (vedi «Il
  corredo»: accetta **solo** un corredo, per nome). Una chiamata con un
  argomento-Env agisce
  **sulle y** come gli operatori — `min(env, 10)` è un clamp del livello,
  `floor(env)` quantizza — e due Env nella stessa chiamata sono errore
  (tranne `mix`, che di due Env vive).
  `%` è il resto con semantica Python (segno del divisore); `//` il
  quoziente intero: `i % 3` e `i // 3` trasformano l'indice dello spread in
  coordinate di griglia. Fuori dominio (`sqrt` di un negativo, `log` di zero,
  potenza frazionaria di un negativo) è errore chiaro, non un NaN.
- **`mix(A, B, w)`** — il morphing pesato `A*(1-w) + B*w` tra due forme:
  l'**unica porta Env⊙Env** del sistema (issue #29). Esattamente 3 argomenti
  posizionali. Uno scalare al posto di una forma diventa Env costante
  (broadcast); `w` può essere a sua volta un Env (il morphing evolve dentro
  il tempo dello stream); **niente clamp** su `w` — fuori `[0, 1]` si
  estrapola, il clamp si scrive con `min`/`max`; l'annidamento è libero
  (`mix(mix(A, B, w), C, v)`). Dove il risultato resta rappresentabile senza
  perdita il ricampionamento sull'unione dei tempi è **esatto**
  (linear/linear con `w` scalare; step/step; `w`-Env su scalari); altrove
  (forme `curve`, `w`-Env su forme mobili) interviene un campionamento
  adattivo con scarto massimo sotto una tolleranza proporzionale
  all'escursione — l'output resta un Env simbolico a pochi breakpoint.
  Le forme devono abitare lo stesso mondo: **step con continua è errore**
  (discontinuità pesata, fuori dal v1). Il morphing a scatti si scrive con
  forme step (o scalari) e `w` step.
- **`let`** dichiara i nomi in scope: scalari, forme **statiche** di Env
  (`[a, b]`, `[[t, v], ...]`, `{type, points, curve}`), corredi (iniettati per
  nome dal `let:` che li dichiara), oppure altri **nodi-expr** (issue #28) — così una sagoma calcolata si fattorizza senza
  pre-calcolare i breakpoint a mano. Un nodo-generatore dentro `let` resta
  errore: i due meccanismi non si annidano — con una sola eccezione, la
  **banda-let** della strategy `expr` dello spread (un pescaggio random per
  stream generato, vedi «La strategy `expr`»).
- **expr annidati in `let`** — le regole di scoping:
  - un expr annidato vede i **fratelli** dello stesso `let` e i nomi esterni
    (nella strategy `expr` dello spread anche `i`, `n` e le bande-let);
    l'**ordine di dichiarazione non conta** — la risoluzione è per
    dipendenze;
  - può avere il **proprio `let`**: scope lessicale, i nomi interni
    **ombreggiano** gli esterni (e un nome ridefinito non vede il nome che
    ombreggia: sarebbe un auto-riferimento, quindi ciclo);
  - un **ciclo** (`a` dipende da `b`, `b` da `a` — o un auto-riferimento) è
    errore di valutazione chiaro, con la catena nel messaggio;
  - guardia di **profondità 8**, come i generatori annidati: vale sia per i
    `let` dentro `let` sia per la catena di dipendenze tra variabili.

  ```yaml
  axes:
    density:
      n: 4
      base:
        expr: "shape * 50"
        let:
          env: [[0, 1], [0.1583, 1.5]]
          shape: {expr: "min(env, 1.2)"}   # sagoma calcolata, riferita a un fratello
      range: 0
  ```
- **Env ⊙ scalare** agisce **sulle y**, i tempi restano intatti; con la forma
  dict, `type`/`curve` si preservano. L'ordine conta dove deve
  (`100 - env`, `env / 2`). **Env ⊙ Env non è supportato** (errore).
- Vale ovunque c'è un Env: `base`/`range` (Y e camminata-X), `step` di
  ramp e di `drift`. Vale anche nei **parametri statici dello stream**
  (`base.volume`, `base.grain.duration`, ...): lì si valuta alla costruzione
  del documento engine e il risultato passa così come lo scriveresti a mano
  — l'engine accetta envelope diretti nei parametri stream, quindi il
  risultato deve essere una forma che l'engine capisce (scalare o envelope).
- Una **patch** di un generato di spread può rimpiazzare il valore calcolato
  con un altro nodo-expr: su un path-Env (`axes.*`/`stack.*`) la valutazione
  avviene alla seam degli assi, su un parametro statico alla costruzione del
  documento. In entrambi i casi mai nello spread.
- Le espressioni vanno **sempre quotate**: `expr: env * 50` senza virgolette
  è YAML valido ma fragile; con `{}` non lo è affatto.

Design completo: `docs/plans/expr-env-arithmetic.md`.

## Manopole: i blocchi `let:`

Una **manopola** è un nome dichiarato una volta e letto da più espressioni per
nome. Serve ad **accoppiare** parametri e gruppi: dici un valore (o una forma)
una volta, e più formule lo riferiscono, ognuna con la propria aritmetica. È il
`let` dei nodi-expr un livello sopra — nomi in scope, ma condivisi. Tre livelli,
per i tre livelli del pattern compositivo:

```yaml
let:                                  # 1. documento: default comuni
  g0: 4
  d0: 25

streams:
  cugini:
    let:                              # 2. gruppo: la forma DI QUESTO gruppo
      comune: {base: {expr: "d0"}, range: 1, n: 5, drift: {step: 0.2}}
    spread:
      n: 6
      let:                            # 3. voce: cosa distingue le voci
        divarico: {expr: "i * 0.8"}
      over:
        base.pointer.start: {values: [0.12, 0.25, 0.4, 0.55, 0.93, 1.1]}
    axes:
      density:
        base:  {expr: "comune + divarico"}   # forma comune + offset per voce
        range: {expr: "d0 * 0.6"}
```

- **Iniezione per nome.** Al load (documento) e prima dell'espansione (gruppo,
  voce), il valore risolto viene iniettato nel `let` di **ogni** nodo-expr che
  ne nomina la chiave — la stessa meccanica di `versions`. Un `let` locale che
  non nomina la manopola resta intatto.
- **`let:` di documento** (top-level). Valori: scalare, envelope disegnato
  (`[[t, v], ...]`), envelope **generato** `{linear_env: ...}` (pescato o
  costruito **una volta**, con seed `stable_seed("<study>:let:<nome>")`),
  **corredo** `{list: [...]}` (una lista nominata, letta per indice — vedi «Il
  corredo»), o nodo-expr derivato che referenzia altre manopole (risolto al
  load; i corredi si risolvono **prima**, così `{expr: "ratio[0] * 2"}` è una
  manopola derivata legittima qualunque sia l'ordine di dichiarazione). Un
  generatore *nudo* qui è errore: il `let:` è il contesto in cui la posizione
  non dice il ruolo, e il ruolo lo marca `linear_env:`. Iniettato **prima** di ogni
  processo: è il **riposo**, che `versions:`/`percorso:` poi **ombreggiano**
  (iniettano dopo e vincono — stessa manopola, riposo e movimento). Attivo
  anche in `make stack`.
- **`let:` di gruppo** (dentro una entry di `streams:`). Nomi locali al gruppo,
  risolti una volta per gruppo (seed `stable_seed("<entry>:let:<nome>")`) e
  iniettati nelle espressioni dell'entry — axes e blocco `spread` — **prima**
  dell'espansione, così tutte le voci del gruppo condividono il valore. È la
  traiettoria condivisa dalle voci (`comune`), disegnata o pescata — e se
  pescata, avvolta in `linear_env:` come nel `let:` di documento. Due gruppi
  diversi con lo stesso nome sono indipendenti (come i loro `axes:`).
- **`spread.let`** (dentro `spread:`, accanto a `n`/`over`). Manopole di
  **voce**: un valore per stream generato, iniettato per nome. Due forme, come
  le strategy: `expr` con `i`/`n` (deterministico per voce) o **banda** (un
  pescaggio per voce). `values`/`ramp` sono rifiutati (possiederebbero un
  conteggio ridondante con `over`: `n` resta di `over`/`spread.n`); un
  **corredo** è rifiutato per un'altra ragione — a livello di voce `i` è già
  fissato, quindi una lista qui non avrebbe nessun indice da cui essere letta:
  si dichiara nel `let:` di gruppo e si legge da qui con `{expr: "ratio[i]"}`.
  Vedi «Il blocco `spread:`».
- **Manopola derivata.** Un nodo-expr in un `let:` (documento o gruppo) che
  referenzia altre manopole; l'ordine di dichiarazione non conta, la
  risoluzione è per dipendenze. Vale l'intera grammatica di `expr`, **funzioni
  primitive comprese** (`{expr: "min(centro, 30)"}`): il nome di una funzione è
  un termine della grammatica, non una manopola da dichiarare.
- **Aritmetica inviluppo⊕scalare.** Una manopola-envelope combinata con uno
  scalare nell'espressione (`comune + divarico`, `comune * k`) agisce sulle y,
  i tempi restano — è l'aritmetica su Env del nodo-expr. Così la forma comune
  vive in una manopola e l'offset/scala per voce in un'altra, e l'asse le
  combina in una riga leggibile: **niente `base` annidato per avere uno slot
  scrivibile**.
- **Ombreggiare fra livelli è errore.** Un `let:` non può ridichiarare un nome
  già in scope in un livello superiore della propria linea: documento è antenato
  di ogni gruppo e di ogni `spread.let`; il gruppo è antenato del proprio
  `spread.let`. Due gruppi (o due `spread.let` di gruppi diversi) sono fratelli:
  lo stesso nome **non** collide. La regola cancella ogni domanda di precedenza —
  un valore diverso vuole un **nome** diverso. La guardia gira al load.
- **Non referenziata è errore.** Una manopola che nessuna espressione nomina è
  un refuso (stessa regola di `versions:`).
- **Additivo/opt-in.** Senza blocco `let:`, nessun cambiamento: i documenti
  generati sono identici.

## Il blocco `gain_compensation:`

```yaml
gain_compensation:
  alpha: 0.7        # 0 = niente, 1 = stream contemporanei appaiati (default 1)
  max_shift: 24     # limite in dB alla correzione del singolo stream (default 24)
```

Stream che granulano lo **stesso** sample in punti di lettura diversi arrivano
al mix con livelli molto diversi — il buffer ha punti forti e punti deboli — e
chi sta sotto viene mascherato. Con `pointer.speed_ratio: 0` quel livello è
prevedibile prima del render: l'RMS del buffer sulla finestra che il grano
legge davvero, `[pointer.start, pointer.start + grain.duration)`. Il blocco
attiva la stima e scrive un offset di `volume` per stream.

Vale solo sui documenti **multi-stream** (`stack`, `versions`, `percorso`): la
compensazione è relativa, uno stream da solo non maschera nessuno. Blocco
assente = nessuna compensazione, documenti identici a prima. Su `percorso` il
riferimento resta **locale** (la media si calcola per istanza, sugli stream che
si sovrappongono in quel momento) e lo shift in sottrazione è **unico** per
l'intero percorso.

Tre regole, tutte osservabili nei documenti generati:

- **Solo il differenziale, mai il livello d'insieme.** Il riferimento è la
  media degli stream contemporanei, non una costante: resta udibile che un
  grano più corto porta meno energia (percetto vero) e si appiattisce solo il
  mascheramento reciproco, che è artefatto del buffer.
- **Contemporanei = che si sovrappongono davvero** (`[onset, onset+duration)`).
  Le versioni concatenate non suonano insieme, quindi ognuna si normalizza da
  sé; su uno stack simultaneo la regola degenera nella media dei cugini.
- **Si attenua, non si alza.** Gli offset vengono traslati in blocco perché il
  massimo sia 0: il bound engine di `volume` è `[-120, +12]` dB e la base
  tipica è 0, quindi alzare finirebbe contro il tetto. Lo shift è **uno solo
  per studio**, non per documento, così i file di `versions` restano
  confrontabili fra loro all'ascolto.

`grain.duration` a envelope si riassume con la **mediana** dei breakpoint: una
costante per documento basta (sul sample dello studio lascia ~0.9 dB di
residuo su ~33 dB di mascheramento), mentre inseguire ogni breakpoint
produrrebbe un envelope di volume che si muove alla velocità della camminata —
un tremolo, non una correzione. Uno stream che legge silenzio non viene
corretto e non entra nel riferimento degli altri.

## Il blocco `stack:`

Il processo stack è il gemello verticale dello sweep: **collassa** tutti gli
stream di `streams:` in un solo documento engine (`yaml/stack/stack.yml`),
sommati. Parte solo se il blocco `stack:` è presente (anche vuoto: `stack: {}`);
ogni stream deve **risolvere una `duration`** — propria (override nello stream)
o ereditata da `base.duration`, che diventa opzionale se ogni stream dichiara
la sua. Camminate-X ed envelope `time_mode: normalized` si
normalizzano sulla duration *propria* dello stream; uno stream con `onset:`
proprio parte spostato nella timeline, e la durata documento copre tutto
(`max(onset + duration)`).
Per escludere uno stream dall'ascolto lo si muta con il suo `base.volume`
(meccanismo engine); il blocco `stack:` è solo config della camminata-X, non un
gate di partecipazione.

Schema piatto: `seed` (seed-X globale) e `unit` (unità globale della banda)
sono le chiavi riservate; ogni altra chiave è un **nome d'asse**. Non c'è più
un nome-strategy: la strategy-X si riconosce dalla **presenza** dell'asse nel
blocco.

| Strategy-X | Come si dichiara | Chi possiede `n` |
|------------|------------------|-------------------|
| `linear` | asse **assente** dal blocco | la **Y** (`values`/`ramp`/banda con `n`); tempi equispaziati `t_i = i/(n-1)`, estremo `t=1` incluso |
| camminata (`walk`, alla `rspline`) | asse **presente** con `{base: <env>, range?: <env>, seed?: int, unit?: hz\|s\|bpm, distribution?, drift?}` | la **X**: `n` emerge dalla banda integrata sulla durata |

Con la camminata a ogni punto si pesca un valore nella banda
`[base(t), base(t)+range(t)]` (`base`/`range` accettano le stesse forme della
banda di Y). Con `unit: hz` (default) il valore è una **frequenza di
generazione** e il punto successivo cade a `t + 1/f`; con `unit: s` è il
**periodo** in secondi e il punto cade a `t + p` — comodo quando gli intervalli
sono nell'ordine delle decine di secondi e le frequenze frazionarie (0.0x Hz)
diventano scomode; con `unit: bpm` sono **battiti al minuto** e il punto cade a
`t + 60/v` — comodo quando il gesto si pensa come pulsazione. Le unità vivono
nel registro `X_UNITS` di `x_strategies`: aggiungerne una nuova è una entry
(convertitore valore → passo in secondi) più doc e test. Anche
`distribution` e `drift` valgono qui, con la stessa
semantica della banda di Y (il dominio degli `Env` è il tempo reale
normalizzato): con `drift` la frequenza (o il periodo) di generazione deriva
invece di saltare — accelerandi/ritardandi stocastici ma organici. La Y
dev'essere una **banda senza** `n`, campionata ai tempi reali dei breakpoint.
`range` assente = camminata **deterministica** (segue `base`, il seed non
influisce sui tempi). Le due direzioni sbagliate (camminata-X con Y che
enumera; banda Y senza `n` con X lineare) sono errori di parse (*n-ownership*).

> **`unit` sceglie lo spazio della camminata, non una notazione.** Uniforme in
> periodo non è uniforme in frequenza: la banda `[10, 30]` s ha intervallo
> medio 20 s, la "equivalente" `[1/30, 1/10]` Hz produce intervalli sbilanciati
> verso il corto. E gli `Env` di `base`/`range` si interpolano nello spazio
> scelto: `base: [20, 2]` con `unit: s` è un accelerando lineare *nel periodo*,
> `base: [0.05, 0.5]` in Hz è lineare *nel rate* — curve percettive diverse.
> Anche `drift.step` (frazione della banda corrente) cammina nello spazio
> scelto. Le famiglie sono due: **rate** (`hz`, e `bpm` che è hz riscalato per
> 60 — la banda `[60, 120]` bpm è esattamente la banda `[1, 2]` Hz) e
> **periodo** (`s`). `bpm` è zucchero notazionale sullo spazio-rate; `s` è uno
> spazio davvero diverso.

> **Due equispaziati diversi.** «`base` costante = tempi equispaziati» vale per la
> **camminata** ed è un equispaziato *per frequenza*: `n` emerge da `durata × f` e
> l'ultimo punto non cade mai su `t = 1`. È cosa diversa dall'equispaziato della
> **X-linear** (assenza dal blocco): lì `n` viene dalla Y, `t_i = i/(n-1)` ed
> `t = 1` è incluso. Convivono — uno è la camminata, l'altro il default implicito.

Per riportare un asse a `linear` in una stream (annullando una camminata
ereditata) si **annulla l'entry**: `stack: {asse: null}`.

In stack gli assi **non si combinano** (niente prodotto cartesiano): ogni asse
diventa un envelope indipendente. Due assi con la stessa strategy-X e lo stesso
`n` restano accoppiati — è l'ex `combine: parallel` dello sweep. Un asse con un
solo valore resta **scalare** (stream statici/drone legittimi); l'interpolation
per-asse (`linear`/`cubic`/`step`) vale anche qui.

**Seed e unit, precedenza (il più specifico vince):**

- Y: `seed` della banda (per-asse) → `axes.seed` globale → auto-derivato per-stream;
- X: `stack.<asse>.seed` → `stack.seed` globale → auto-derivato per-stream;
- unit: `stack.<asse>.unit` → `stack.unit` globale (per-stream via il deep-merge
  di `streams.<id>.stack`) → default `hz` (retrocompatibile).

L'auto-derivazione è un hash stabile (CRC32) dell'id dello stream, con salt
distinti per Y e X: senza seed globali gli stream impilati si **decorrelano da
soli**, restando riproducibili tra run.

## Il blocco `versions:`

Il processo versions è un **processo indipendente** come sweep e stack:
richiede il blocco `stack:` (le versioni sono repliche dello stack) ma ha
sottocomando (`make versions`) e output propri, `yaml/versions/versions.yml`.
`make stack` resta **puro**: produce il materiale com'è scritto in
`yaml/stack/stack.yml`, ignorando il blocco `versions:` — è l'ascolto
dell'istanza di partenza (vedi `percorso`, issue #29). Dove lo stack collassa
gli stream in un documento, versions **replica quel collasso N volte nel
tempo**: una replica per combinazione delle variabili. Di default le versioni
si concatenano; con le chiavi riservate `onset`/`duration` si distanziano o
sovrappongono liberamente.

```yaml
versions:
  f: {values: [50, 100]}          # prima variabile = esterna (lenta)
  d: {values: [1, 2, 3]}          # ultima = interna (veloce)
  onset:    {ramp: {start: 0, stop: 100}}   # riservata: 6 posizioni assolute
  duration: {base: 15, range: 10}           # riservata: 6 durate in [15, 25]
```

- Ogni chiave è un **asse ortogonale** (identificatore libero; `i`, `n`,
  `pi`, `e` sono riservati agli scope expr e vengono rifiutati). La forma più
  semplice — valore un generatore Y (`values`/`ramp`/banda con **`n`**) — è un
  asse a **una manopola omonima**: la forma piatta storica, retro-compatibile.
  Un asse può però reggere più manopole (vedi Forma 1/2 sotto).
- Più assi → **prodotto cartesiano lessicografico** nell'ordine di
  dichiarazione (come gli `orderings` dello sweep): con l'esempio sopra le
  versioni sono (50,1) (50,2) (50,3) (100,1) (100,2) (100,3).

**Forma 1 — manopole parallele (co-varianti).** Un asse il cui valore è un dict
di manopole, ognuna una **sequenza** (`values`/`ramp`/banda con `n`/lista): le
manopole scorrono **insieme per indice**. La lunghezza dell'asse è la sequenza
**più lunga**; le più corte **tengono l'ultimo valore**.

```yaml
versions:
  grana:                      # un asse, due manopole che co-variano
    g0:  {ramp: {start: 4, stop: 50, step: 6}}   # 8 valori
    apr: [0, 2, 5]                                # 3 → tiene 5 dalla 4a all'8a
```

**Forma 2 — stati nominati.** Un asse il cui valore è un dict di **stati**,
ognuno un **bundle** di manopole. I valori di un bundle si scrivono come quelli
di un `let:` — scalare, breakpoint espliciti, o envelope generato
(`{linear_env: ...}`, con dentro `ramp`/banda/lista). La lunghezza dell'asse è
il numero di stati; un bundle **parziale** lascia le manopole non nominate al
**riposo di `let:`**.

```yaml
versions:
  densita:                    # un asse, due stati alternativi
    estrema:
      d0: 500
      comune: {linear_env: {ramp: {start: 20, stop: 60, step: 5}}}  # envelope
    minima:  {d0: 2}                              # bundle parziale
# grana × densita = 8 × 2 = 16 versioni
```

- **I due ruoli non dipendono più dalla posizione.** `{ramp: ...}` come figlio
  diretto dell'asse è una **sequenza di versioni** (Forma 1, letta per indice);
  dentro uno stato serve una **forma nel tempo**, e la si marca `linear_env:`.
  Un generatore nudo dentro un bundle è errore, e `linear_env:` come entry di
  un asse è l'errore simmetrico.
- **Discriminatore.** Un asse è Forma 1 se **tutte** le entry sono sequenze
  (generatore/lista), Forma 2 se **tutte** sono bundle (dict non-generatore).
  Mescolarle in un asse è errore; separale in due assi. Le etichette nello
  `stream_id`: `grana=<indice>` (Forma 1), `densita=<stato>` (Forma 2),
  `d=<valore>` (asse a manopola singola).
- Le manopole mosse sono le stesse di `let:`: un asse le **ombreggia** (riposo →
  movimento d'analisi). `versions:` resta solo analisi: `make stack` non lo vede.
- Per ogni combinazione i valori vengono **iniettati negli scope `let`** dei
  nodi-expr che *nominano* la variabile, ombreggiando il default dichiarato
  (`let: {d: 0}`). Il default tiene lo studio valido anche senza il blocco;
  una variabile che nessuna espressione referenzia è un errore di parse
  (guardia anti-refuso). L'iniezione vale ovunque un nodo-expr viva: bande di
  Y, camminate-X, parametri statici dello stream — anche **annidato** nel
  `let` di un altro nodo-expr (issue #28): il nodo annidato che nomina la
  variabile la riceve nel *proprio* `let`, ombreggiando il default locale.
- Ogni versione replica **tutti** gli stream dello stack, spostati sulla
  posizione della versione e con lo `stream_id` suffissato con l'etichetta
  della combinazione (`mobile__f=50__d=1`). Envelope, camminate e seed passano
  per il builder dello stack **identici**: tra una versione e l'altra cambia
  solo il valore delle variabili — è il confronto pulito del metodo. La durata
  documento è `max(onset + duration)` su tutti gli stream (nel caso classico
  concatenato coincide con `N * duration`).
- **`spread.n` mosso da una variabile** (issue #39). L'iniezione arriva anche
  dentro `spread.n`, quindi una variabile del blocco può cambiare il **numero
  di voci** di una entry-spread da una versione all'altra — basta nominarla
  lì, la guardia anti-refuso conta anche quel nodo-expr:

  ```yaml
  streams:
    cugini:
      spread:
        n: {expr: "k", let: {k: 3}}     # k: 3 voci a riposo (make stack)
        over: {base.pointer.start: {ramp: {start: 0.1, step: 0.1}}}
  versions:
    k: {values: [2, 4]}                 # 2 voci nella prima versione, 4 nella seconda
  ```

  È lo stesso meccanismo del percorso (`spread.n` come nodo-expr), ma **a
  gradini di versione** invece che per istanza sulla timeline reale: versions
  confronta popolazioni diverse affiancate, il percorso le fa evolvere. Come
  nel percorso la scelta ridistribuzione/accodamento emerge dalla forma del
  ramp in `over`: `ramp {start, stop}` suddivide su `n`, `ramp {start, step}`
  lascia ferme le voci esistenti e accoda le nuove.
- **Padding stabile dei nomi generati.** Con `n` variabile lo zero-padding è
  fissato sulla larghezza del **massimo `n` dell'intero prodotto cartesiano**:
  con `k: {values: [9, 11]}` le voci si chiamano `cugini_01 … cugini_09` nella
  prima versione e `cugini_01 … cugini_11` nella seconda — mai `cugini_1` di
  qua e `cugini_01` di là. Così una **patch** per nome (`cugini_03:`) si
  applica in ogni versione in cui la voce esiste, e dove non esiste viene
  consumata in silenzio (voce-fantasma) invece di restare uno stream spurio in
  più. Il massimo è sul prodotto intero e non per gruppo: i file separati di
  `versions.chunk` / della variabile esterna restano confrontabili fra loro.
  Con `n` costante il pad non allarga nulla (retrocompatibile).
  - Attenzione: il pad è **per processo**. `make stack` è l'istanza di
    partenza e ignora `versions:` (v. sopra), quindi lì `n` vale il default
    del `let` e i nomi sono stretti: una patch scritta per le versioni
    (`cugini_03:`) non corrisponde a nessun generato dello stack e vi resta
    uno stream ordinario. Vale identico per il percorso; se dà fastidio,
    scrivi la patch col nome stretto oppure ascolta quel materiale via
    `make versions`.
- **`onset` e `duration` come chiavi riservate** (issue #26): non sono
  variabili — non entrano nel prodotto cartesiano né negli scope `let` — ma
  generatori della **timeline**: producono una sequenza lunga N (numero di
  combinazioni) mappata **1:1** sull'ordine lessicografico delle versioni
  (funzioni di k). Il conteggio lo possiede il prodotto cartesiano: `values`
  deve avere esattamente N elementi; la banda deduce `n = N` (un `n` esplicito
  diverso è errore); `ramp` senza `step` distribuisce N valori equispaziati
  `start → stop`, con `step` la griglia deve contare esattamente N. Una banda
  senza `seed` deriva `stable_seed("<study>:versions:onset")` /
  `"...:duration"`.
  - `onset[k]` è la posizione **assoluta** della versione k. Non monotono è
    legittimo: sovrapposizioni e buchi emergono dai valori (il merge degli
    stem fa overlay-add con clip). L'`onset` per-stream resta **relativo alla
    propria versione**: `onset_finale = onset_versione + onset_stream`.
  - `versions.duration` accetta anche uno **scalare**, broadcastato su tutte
    le N versioni (`versions: {duration: 50}` = tutte lunghe 50): è il caso
    più comune. La forma generatore (`values`/`ramp`/banda) dà una durata per
    versione.
  - `duration[k]` fa da **default** degli stream della versione k, iniettato
    come `base.duration` del documento della combo prima del parse (issue #42):
    una `duration:` propria dello stream vince comunque.
  - Chiavi assenti → le versioni si **concatenano** sulle durate di versione
    (con `versions.duration` scalare è il classico `onset = k * duration`).
    Senza `versions.onset` e senza `versions.duration` non c'è un passo con cui
    posizionare le versioni: è un **errore**. `base.duration` non vale come
    passo — è la durata di uno stream, non il passo delle versioni (issue #42,
    che ha separato i due lavori che il vecchio `duration:` top-level di #26
    faceva insieme).
- Il confine tra versioni è un confine naturale di stream (l'engine chiude
  una granulazione e ne apre un'altra): nessuna transizione interpolata tra
  versioni. Per ammorbidire il bordo si lavora con gli envelope di volume
  degli stream, come sempre.
- **Onset in Sonic Visualiser.** Nel `.sv` del **mix** (`stack_to_sv`) l'onset
  è rispettato: l'audio è un unico file con gli onset già cotti nel buffer, e
  gli envelope sono ancorati al loro onset reale (`onset + t·durata_stream`,
  non stirati sulla durata totale). Nel `.sv` **per-stem**
  (`stack_stems_to_sv`) SV non sa offsettare un file audio nella timeline
  (il parser `.sv` ancora ogni wavefile al frame 0, nessun attributo di
  offset): per gli stream con `onset > 0` l'export genera quindi una **copia
  paddata** dello stem — `onset` secondi di silenzio prepesi — in
  `audio/versions/padded/`, e ancora lì gli envelope. Gli stem originali non
  vengono toccati; le copie si rigenerano solo se l'originale è più nuovo.
- **Stem accorpati per voce logica.** In STEMS mode ogni combinazione produce
  il proprio stem (`versions__fermo__d=1.aif`, `versions__fermo__d=2.aif`, ...):
  con molte combinazioni il `.sv` per-stem avrebbe un pane per file. Dopo la pass
  STEMS il render fa quindi un **post-merge per nome-base** (lo `stream_id`
  prima del primo `__`): le versioni di una stessa voce logica vengono sommate
  al proprio onset (overlay-add con clip: regge anche versioni sovrapposte) in
  un unico file `versions__{voce}.aif`, ancorato al tempo 0 del documento. `stack_stems_to_sv`
  consuma i file accorpati: **un pane per voce logica**, con gli envelope di
  ogni versione offsettati al proprio onset dentro il pane. Gli stem per
  combinazione restano su disco intatti; i file accorpati si rigenerano solo
  se uno stem sorgente è più nuovo.

Il caso d'uso fondativo (due stream con inviluppo condiviso e offset che
cresce di versione in versione) è in `studies/study_versions_test/study.yml`:
l'inviluppo si scrive una volta nel default di `axes:` (`expr: "env + d"`,
`let: {env: ..., d: 0}`), lo stream fermo ridefinisce solo `expr: "env"`
(il `let` si eredita via deep-merge), e `versions: {d: {values: [1, 2, 3]}}`
genera le tre coppie concatenate.

## Il blocco `percorso:`

Il quarto asse del sistema (issue #29), **gemello compositivo** di `versions`:
dove `versions` genera il prodotto cartesiano delle combinazioni (analisi —
una variabile si muove, le altre ferme, per osservare), `percorso` dispone K
**istanze** dello stack su una timeline e fa cambiare i valori **insieme**,
appaiati sul tempo reale — nessun prodotto cartesiano. Sta a `versions` come
`stack` sta a `sweep`. Processo indipendente, attivo per presenza: richiede
`stack:`, può coesistere con `versions:` (li esercitano target diversi), e
`make stack` resta l'ascolto dell'istanza di partenza.

```yaml
percorso:
  arco: 180                                        # camminata: estensione totale
  passo: {base: [30, 8]}                           # accelerando: IOI da 30s a 8s
  duration: 1.3                                    # factor: crossfade costante
  w: {base: [0, 1], range: .1, drift: {step: .2}}  # la manopola: sale 0→1 con deriva
```

- **Due strategy di timeline, mutuamente esclusive** (dichiararle insieme è
  errore; `k:` da solo non esiste):
  - **enumerata — `onset:`**: gli onset li dichiari tu, sull'indice, col
    vocabolario di sequenza (`values` = tempi assoluti uno per istanza,
    `ramp`, banda). Il conteggio `k` lo **possiede `onset`** (lunghezza di
    `values`, griglia del ramp con `step`, `n` della banda); `k:` esplicito è
    ammesso come cross-check (discordanza = errore) ed è obbligatorio solo
    quando `onset` non possiede un conteggio (`ramp {start, stop}` senza
    `step`, banda senza `n`).
  - **camminata — `arco:` + `passo:`** (obbligatori insieme): `arco` è
    l'estensione totale (scalare > 0), `passo` la legge dell'intervallo —
    `t_next = t + passo(t)`, con `passo` traiettoria campionata all'onset
    corrente, finché `t < arco`. **`k` emerge**, non si dichiara (dichiararlo
    è errore). L'equispaziato si scrive con passo costante
    (`arco: 180, passo: 22.5` → 8 istanze). È la camminata-X trasposta
    sull'asse delle istanze.
- **Le altre chiavi sono traiettorie**: la legge con cui una variabile cambia
  lungo il tempo reale del percorso. Si scrivono in **grammatica-Env**, come
  la `base` di un axis: banda (`base` + `range`/`drift`/`distribution`/`seed`
  opzionali), nodo-expr (`{expr, let}`), o scalare nudo = costante. **Mai
  `values`/`ramp`**: sono generatori di sequenze e appartengono ai contesti
  indicizzati (`onset` enumerato, `spread`, `versions`) — usarli in una
  traiettoria è errore con hint; per una forma disegnata dentro un bordo si
  usa `linear_env:` (`base: {linear_env: [0, 1, 0]}`). Una banda con `n` è
  errore: le traiettorie
  non possiedono mai il conteggio (sono leggi sul tempo: le campioni in 3 o
  300 istanze e sono le stesse). Una banda con `drift` è una traiettoria a
  **deriva correlata**: ogni istanza vicina alla precedente, il passo
  dell'ubriaco sull'asse delle istanze.
- **Nomi riservati**: `k`, `onset`, `arco`, `passo`, `duration` sono chiavi
  del blocco (mai variabili); `i`, `n`, `pi`, `e` sono riservati agli scope
  expr e vengono rifiutati come nomi di traiettoria. Una traiettoria che
  nessuna espressione del documento referenzia è errore (guardia
  anti-refuso, come `versions`).
- **`duration`** è una traiettoria riservata con **`unit: factor` (default) |
  `s`**, dichiarata accanto alla forma (`duration: {base: [30, 8], unit: s}`;
  lo scalare nudo è un factor costante). Assente = **legato**.
- **La timeline si risolve prima** (ordine a due fasi, per rompere la
  circolarità "le variabili si campionano sul tempo reale, ma il tempo reale
  lo creano onset e passo"): prima gli onset — sull'indice in enumerata,
  per accumulo `t += passo(t)` in camminata (con `passo` campionato all'onset
  corrente; un passo non positivo è errore) — poi tutto il resto, `duration`
  e traiettorie ordinarie, campionato **all'onset reale** di ogni istanza.
  "A metà" = a metà dell'ascolto, non del conteggio.
- **Normalizzazione del tempo delle traiettorie**: i tempi dei breakpoint
  sono normalizzati 0 → 1 sull'**estensione del percorso** — l'`arco` in
  camminata (l'ultima istanza cade *prima* di 1: campionamento onesto, come
  i grani campionano un envelope), l'**ultimo onset** in enumerata (l'ultima
  istanza cade esattamente a 1).
- **Semantica di `duration`**: campionata all'onset dell'istanza, identica
  nelle due strategy. Con `unit: factor`,
  `duration_k = factor(t_k) × intervallo verso la prossima istanza` — 1 =
  legato, > 1 sovrapposizione (crossfade), < 1 buchi: è il *duty* un asse più
  in alto, e mantiene la proporzione dentro un accelerando. L'intervallo di
  riferimento dell'ultima istanza è `passo(t_K)` in camminata (il passo che
  avrebbe seguito, già calcolato: l'ultima istanza può **sforare l'arco** con
  la propria durata — l'engine dimensiona su `max(onset + duration)`) e
  l'ultimo intervallo noto in enumerata. Assente = legato (factor 1).
  Con `unit: s` la durata è assoluta. Bordo: enumerata con `k = 1` e factor
  (anche implicito, il legato) è errore — non c'è intervallo di riferimento,
  serve `unit: s`.
- **Iniezione e istanze**: per ogni istanza i valori campionati vengono
  iniettati negli scope `let` dei nodi-expr che nominano la variabile (il
  meccanismo di `versions`), poi il parse di sempre: le strategy di spread si
  **rivalutano a ogni istanza** coi valori iniettati — l'istanza è lo spread
  che evolve. Il default nel `let` (`w: 0`) tiene lo studio valido senza il
  blocco: `axes:`/`stack:` come sono scritti *sono* l'istanza di partenza
  (`make stack` la suona), il percorso aggiunge solo il "verso dove".
  Nominare la stessa variabile in più registri (forma Y, banda X,
  `spread.n`) **accoppia** le evoluzioni; nominare diverso le decorrelava —
  nessuna sintassi dedicata, emerge dall'iniezione.
- **Seed invariato se non toccato**: ogni istanza eredita tutto via
  deep-merge, quindi la stessa camminata/pescaggio ritorna, trasformata dalle
  variabili — il gesto che ritorna. Il reseed è un override esplicito come
  un altro.
- **`spread.n` come nodo-expr**: `n: {expr: "floor(3 + 9 * w)", let: {w: 0}}`
  — valutato per istanza, deve dare un intero >= 1 (arrotonda con
  `floor`/`ceil`). Il coro cresce o decresce lungo il percorso. La scelta
  ridistribuzione/accodamento emerge dalla forma del ramp in `over`:
  `ramp {start, stop}` suddivide su `n` (il ventaglio si ridistribuisce),
  `ramp {start, step}` è progressione indipendente da `n` (le voci esistenti
  restano ferme, le nuove si accodano).
- **Padding stabile**: con `n` dinamico lo zero-padding dei nomi generati è
  fissato sulla **larghezza del massimo `n` lungo il percorso** — la stessa
  voce logica ha lo stesso nome ovunque esista, e il post-merge per
  nome-base la cuce nel tempo (le voci nate dopo hanno silenzio prima). La
  **patch di spread** (`coro_05:`) si applica in ogni istanza in cui la voce
  esiste — e può contenere nodi-expr che nominano variabili del percorso:
  l'eccezione evolve. Nelle istanze in cui la voce non esiste la patch viene
  consumata in silenzio. Il pad è per processo: sotto `make stack` i nomi
  restano stretti (vedi la nota nel blocco `versions:`). La patch di
  *istanza* ("il quinto passaggio fa
  eccezione") non esiste (parcheggiata): la scappatoia è la strategy
  enumerata con una traiettoria `{type: step}` su una finestra che contiene
  solo l'istanza da trattare.
- **Naming e output**: ogni stream di ogni istanza ha lo `stream_id`
  suffissato **`nome__k=NN`** (indice d'istanza 1-based, zero-padded sulla
  larghezza del K finale: in SV l'ordine alfabetico è quello cronologico).
  L'onset per-stream resta relativo alla propria istanza
  (`onset_finale = onset_istanza + onset_stream`); la `duration` d'istanza fa
  da default degli stream della singola istanza — iniettata come
  `base.duration` del suo documento (issue #42) — e una duration per-stream
  vince. Durata documento = `max(onset + duration)`. Output:
  `yaml/percorso/percorso.yml` via `make percorso`; il render generico e il
  ramo sv lo raccolgono come gli altri processi.

## Il blocco `spread:` (stream generati)

`spread` è il terzo asse del sistema, quello della **macro-forma**: Y
distribuisce valori nel tempo (micro-forma), la camminata-X distribuisce i
tempi, `spread` distribuisce valori **nella popolazione di stream**. Una entry
di `streams:` con la chiave riservata `spread` non descrive un solo stream ma
ne **genera** `n`, distribuendo i valori di uno o più parametri secondo una
strategy — con lo stesso vocabolario dei generatori Y.

```yaml
streams:
  base: {}

  ventaglio:
    base:
      pointer:
        speed_ratio: 0          # override normale: vale per tutti i generati
    spread:
      n: 8                      # opzionale se una strategy possiede il conteggio
      over:                     # {path puntato nel documento: strategy}
                                # sotto axes./stack. il primo identificatore è
                                # un nome d'asse, anche dotted: stesso boundary
                                # (assi dichiarati → registro engine) delle
                                # chiavi puntate in streams (vedi sopra)
        base.pointer.start:
          ramp: {start: 0.1, step: 0.1}    # 0.1, 0.2, ... 0.8
        base.onset:
          values: [0, 1, 2.5, 4, 6, 8, 10, 12]
        base.volume:
          base: -12             # banda: n estrazioni in [-12, -12+6]
          range: 6
          seed: 42              # opzionale (default stabile per-path)

  ventaglio_5:                  # patch: ritocca il quinto generato
    base:
      volume: -20
```

L'espansione avviene **prima** del merge delle stream: `ventaglio` sparisce e
al suo posto compaiono `ventaglio_1` … `ventaglio_8` (indice 1-based,
zero-padded alla larghezza di `n`: con `n: 12` si ha `ventaglio_01`; quando
`n` è mosso da `versions:`/`percorso:` la larghezza si fissa sul massimo —
vedi «Padding stabile» nelle rispettive sezioni), entry
ordinarie a tutti gli effetti (sotto-cartelle, seed per-stream, override). Lo
`study.yml` sorgente non viene riscritto: il dict espanso si può ispezionare
in `generated/<study>/yaml/streams_expanded.yml`, rigenerato da `sweep`/`stack`.

**Strategies e chi possiede `n`.** Una sola chiave-generatore per path, come
per gli assi:

| Strategy | Forma | Possiede `n`? | Valori |
|----------|-------|---------------|--------|
| `values` | lista esplicita | sì (`len`) | così com'è, anche non numerici (es. `sample`) |
| `ramp` | `{start, stop, step}` | sì (griglia) | il ramp pieno degli assi |
| `ramp` | `{start, step}` | no | progressione aritmetica `start + i·step` (offset additivo) |
| `ramp` | `{start, stop}` | no | suddivisione lineare in `n` punti |
| banda | `base`/`range`/`seed`/`distribution`/`drift` (+`n` opz.) | solo con `n` proprio | `n` estrazioni nella banda |
| `expr` | `{expr, let}` | no | un eval per stream: `i` (0-based), `n` e le bande-let in scope |

`spread.n` esplicito e conteggi posseduti devono **coincidere** (con `n` come
Env conta il suo picco, vedi sotto); se `n` è omesso lo definisce l'unico
conteggio posseduto; nessuna fonte → errore. Con
più path in `over` i valori si appaiano **per indice** (niente prodotto
cartesiano, come in stack): lo stream i-esimo prende il valore i-esimo di ogni
strategy. Le forme-Env dentro le strategy (banda che scorre, nodi-generatore
annidati) valgono anche qui: `frac` corre sulla popolazione di stream.

**La strategy `expr`** è il nodo-expr (vedi «Il nodo-expr») con due nomi in
più nello scope: `i`, l'indice 0-based dello stream generato, e `n`, il
conteggio totale (`i / (n - 1)` è il progresso normalizzato). Il risultato —
scalare o Env intero — va così com'è sul path. Ridefinire `i` o `n` in `let`
è errore; il conteggio non è mai posseduto da `expr` (serve `spread.n` o una
strategy sorella che lo possiede). Gli **expr annidati** in `let` (vedi «Il
nodo-expr») vedono anche `i`, `n` e le bande-let: convivono nello stesso
`let` — la banda pesca, l'expr annidato calcola, l'espressione principale
combina.

```yaml
spread:
  n: 4
  over:
    axes.density.base:
      expr: "env * a * (i + 1)"     # livelli 50, 100, 150, 200 — stessa sagoma
      let:
        env: [[0, 1], [0.1583, 1.5]]
        a: 50
```

**`n` come Env — il coro cresce e cala nel tempo.** Oltre a scalare e nodo-expr,
`spread.n` accetta un **envelope** nelle forme di sempre (`[[t, n], ...]`,
`[a, b]`, `{type, points, curve}`): il numero di voci *udibili* varia dentro la
singola versione, sul tempo normalizzato dello stream.

Uno stream nel documento engine è statico — il loro numero non può cambiare in
corsa. Quindi le voci si generano **tutte fino al picco** di `n(t)` (arrotondato
in su) e un gate su `base.volume` le accende e spegne:

```
gain(voce i) = clamp(n(t) - i, 0, 1)
```

la stessa regola che `num_voices` applica già dentro un singolo stream. **La
curva la decide l'interpolazione dell'Env di `n`**: con `type: step` la voce si
accende di scatto, con la rampa (`linear`, eventualmente piegata da `curve`)
entra sfumando.

```yaml
spread:
  n: [[0, 1], [1, 4]]                                  # 1 → 4 voci, entrano sfumando
  # n: {type: step, points: [[0,1],[0.5,2],[0.75,4]]}  # entrano di scatto
  over:
    base.pointer.start: {values: [0.12, 0.25, 0.4, 0.55]}
```

Il livello «voce accesa» è il `volume` scalare della entry, o in mancanza quello
di `base:` del documento. Un `volume` già **envelope**, o un `over.base.volume`
dichiarato insieme al gate, sono **errore esplicito**: si sovrascriverebbero.
Per un profilo di volume proprio, usa `n` scalare e scrivi gli envelope a mano
in `over.base.volume`.

Il gate esce come envelope `step` campionato su griglia uniforme: l'istante di
commutazione ha risoluzione 1/256 della durata dello stream.

**La banda-let (random per stream).** Solo nella strategy `expr` dello
spread, una variabile di `let` può essere una **banda**
(`{base, range?, seed?, distribution?, drift?}`): per ogni stream generato
viene pescato un valore nella banda, che entra nello scope dell'espressione
accanto a `i` e `n`. È l'unica eccezione al divieto di nodi-generatore in
`let`; `values`/`ramp` restano fuori (una progressione deterministica si
scrive con l'aritmetica su `i`/`n`). La banda non possiede mai il conteggio
(`n` dentro la banda-let è errore) e `frac` corre sulla popolazione di
stream, come nelle altre strategy: un `base`-Env fa scorrere la banda lungo
i generati (con `range` omesso la segue deterministicamente). Deterministico
via seed: senza `seed` esplicito ogni variabile deriva il proprio (vedi
«Seed» sotto), quindi variabili e path diversi si decorrelano da soli.

```yaml
spread:
  n: 8
  over:
    base.volume:
      expr: "v - 2 * i"             # pescaggio + gradino deterministico
      let:
        v: {base: -12, range: 6}    # banda-let: un random per stream in [-12, -6]
    axes.density.base:
      expr: "env * g"
      let:
        env: [[0, 1], [0.1583, 1.5]]
        g: {base: 40, range: 20, seed: 42}   # stessa sagoma, livello random
```

**`spread.let` — manopole di voce.** Accanto a `n`/`over`, la chiave `let`
dichiara nomi il cui valore vale **per voce**, iniettati per nome negli scope
`let` dei nodi-expr del generato — non scritti su un path, come fa `over`. Due
forme, stesso vocabolario delle strategy: `expr` con `i`/`n` (deterministico
per voce) e **banda** (un pescaggio per voce). `values`/`ramp` sono rifiutati:
possiederebbero un conteggio ridondante con `over` (il conteggio resta di
`over`/`spread.n`).

```yaml
spread:
  n: 6
  let:
    divarico: {expr: "i * 0.8"}                    # deterministico per voce
    env:     {base: {expr: "d0"}, range: 1.5}     # un pescaggio per voce
  over:
    base.pointer.start: {values: [0.12, 0.25, 0.4, 0.55, 0.93, 1.1]}
axes:
  density:
    base: {expr: "comune + divarico"}   # il gruppo LEGGE il nome della voce
  grain.duration:
    base: {expr: "env * 0.1"}           # stesso pescaggio, letto da un altro asse
```

`over` resta per le **destinazioni uniche** (un valore su un path) e i valori
**non numerici** (`sample`, `envelope`); `spread.let` per quando il valore ha
**più di un lettore** — un pescaggio condiviso da due parametri si scrive una
volta in `spread.let` e si legge per nome da due assi (dove prima serviva la
stessa banda-let copiata su due path con lo stesso `seed`). Il nome di una
manopola di voce non può ombreggiare una manopola di gruppo o di documento
(vedi «Manopole: i blocchi `let:`»).

**Ordine del merge** (il più specifico vince): override comune dell'entry →
valore della strategy → patch esplicita. Una entry esplicita omonima di un
generato è una **patch**: deep-merge sopra il generato e viene consumata (non
diventa uno stream in più), ovunque compaia nel documento. Una patch che è a
sua volta una spread è un errore (ambigua).

**Sweep spento di default.** Il senso di uno spread è l'ascolto verticale: i
generati entrano nel documento stack ma, se l'entry non dichiara un proprio
`sweep:`, ricevono `sweep: {orders: [], orderings: []}` e non moltiplicano le
varianti di sweep. Un `sweep:` esplicito nell'entry lo riattiva per tutti i
generati (una patch può riattivarlo per uno solo).

**Seed.** La banda senza `seed` deriva `stable_seed("<entry>:spread:<path>")`;
una banda-let senza `seed` deriva `stable_seed("<entry>:spread:<path>:let:<var>")`:
deterministico tra run, path e variabili diversi decorrelati da soli. I generati
hanno poi ciascuno il proprio `stream_id`, quindi i seed Y/X per-stream si
auto-decorrelano col meccanismo esistente.

## Il blocco `for_each:` — l'asse esterno

Gli `axes:` sono assi **interni**: scorrono nel tempo dentro lo stesso file.
`for_each:` è l'asse **esterno**: ogni combinazione dei suoi valori è una
**patch sullo `study.yml`** e produce un render intero a sé, in
`generated/<study_id>/<label>/`. Non moltiplica i gradini, moltiplica i file.

> Interno se il confronto sta nella **giustapposizione** (lo senti cambiare
> mentre suona). Esterno se sta nel **riascolto** (devi risentire la stessa
> cosa da capo per confrontare), o se la chiave definisce il file stesso —
> `seed`, `sample`, `arco`, la durata.

```yaml
for_each:
  base.distribution: {values: [0, 0.5, 1]}   # asse a manopola singola
  griglia:                                    # asse a stati nominati
    fitta: {axes.fill_factor.values: [0.5, 0.7, 0.85, 1, 2, 4, 8]}
    rada:  {axes.fill_factor.values: [0.5, 1, 4]}
```

3 × 2 = 6 render, in `generated/<study_id>/distribution=0.5__griglia=rada/` e
compagnia. Il blocco **assente** è la combinazione vuota —
`generated/<study_id>/` piatto, come uno studio senza assi esterni: è il caso
degenere, non un ramo speciale.

- Ogni chiave del blocco è un **asse ortogonale**; più assi danno il **prodotto
  cartesiano lessicografico** nell'ordine di dichiarazione (il primo asse è il
  più esterno), come gli `orderings` dello sweep e gli assi di `versions:`.
- **Forma 1 — manopola singola.** La chiave dell'asse *è* il path da patchare,
  il valore un generatore di sequenza (`values`/`ramp`/banda) o una lista nuda.
  I valori devono essere **scalari**: sono loro a nominare la cartella.
- **Forma 2 — stati nominati.** La chiave è un nome libero, ogni entry uno
  **stato**: un bundle di override `{path puntato: valore}`. È l'unica forma
  ammessa per gli override non scalari — un nome di cartella che non dice cosa
  contiene non serve a niente, quindi lo dà l'utente. Un bundle vuoto (`{}`) è
  lecito: è lo stato che non tocca niente.
- **I path sono su tutto il documento**, non solo su `base:`:
  `axes.fill_factor.values`, `stack.seed`, `percorso.arco`, `streams.x.volume`.
  Il valore viene **assegnato** al path, non fuso: `base.grain: {...}`
  sostituisce l'intero sotto-albero. Creare una chiave nuova è lecito
  (`base.pan_range` su un `base:` che non ce l'ha), creare una **sezione** no
  (`bse.pan_range` è un errore, non un refuso silenzioso).
- **Etichette.** `chiave=valore` per la Forma 1 (`base.` e `axes.`, e il nome
  del generatore in coda, vengono tolti: `axes.fill_factor.values` →
  `fill_factor`), `asse=stato` per la Forma 2. Due assi che danno la stessa
  etichetta, o che toccano lo stesso path, sono errore.
- Ogni combinazione ha il **suo albero completo** (`yaml/`, `audio/`, `sv/`,
  `cache/`, `score/`) più uno snapshot `study.yml` — il documento **patchato**,
  riscritto a ogni render, che dice da sé i valori di quella combinazione.
  I `.sv` portano la label nel basename
  (`<study_id>_<stream_id>_e1__density__distribution=0.5.sv`): Sonic Visualiser
  identifica la sessione dal nome, e con due `.sv` omonimi la seconda non si
  apre — proprio il confronto per cui gli assi esterni esistono.

### Perché serve a tutti i processi

Ci sono chiavi che non possono essere assi interni, per costruzione:

| Processo | Cosa diventa esterno |
|---|---|
| `sweep` | il parametro di contorno: lo stesso sweep dei due assi, rifatto con `distribution` diversa, invece di un file tre volte più lungo |
| `stack` | le camminate-X sono stocastiche: ascoltare cinque realizzazioni dello stesso impasto è cinque file, mai uno (`for_each: {stack.seed: [1, 2, 3, 4, 5]}`) |
| `versions` | la valvola di sfogo del cartesiano interno: `grana × densita` = 16 versioni concatenate, una terza variabile porta a 48 e il file diventa inascoltabile |
| `percorso` | la timeline *è* il file: «la stessa legge distesa su 90, 180, 360 secondi» esiste solo come asse esterno (`percorso.arco`) |

### Il filtro `COMBO`

`COMBO=<label>` restringe ogni comando a una combinazione sola — non
rirenderizzare sei varianti da venti minuti per sentirne una, e non aprire sei
sessioni di Sonic Visualiser insieme. È un filtro di sessione, non un
interruttore di modalità: senza, si fa tutto. Una label che non esiste è un
errore che elenca quelle dichiarate.

```zsh
make where STUDY=<id>                      # una root per combinazione
COMBO=distribution=1 study <id>            # genera e apre solo quella
```

### Combinazioni orfane

Togliere un valore da `for_each:` lascia la sua cartella con dentro l'audio
vecchio. Come per le varianti orfane dello sweep: **avviso, nessuna
cancellazione**. Una combinazione orfana è spesso proprio quella che si vuole
tenere — il «prima» da riascoltare.

## Layout di `generated/`

Primo livello = tipo di artefatto, secondo livello = **processo** (`sweep` /
`stack` / `versions` / `percorso`). Il nome dello studio e della stream sono
incorporati nel basename dei file sweep (non solo nella sotto-cartella) per
facilitare l'identificazione in Sonic Visualiser — audio e `.sv` condividono
lo stesso basename `<study>_<stream_id>_<variante>`; i documenti stack,
versions e percorso sono uno per processo (gli stream vi sono collassati).

```
generated/<study_id>/
  yaml/sweep/envelope/<stream_id>/e1__density.yml
  yaml/stack/stack.yml
  yaml/versions/versions.yml     # solo per studi con blocco versions
  yaml/percorso/percorso.yml     # solo per studi con blocco percorso
  yaml/streams_expanded.yml      # solo per studi con spread: il dict streams espanso
  audio/sweep/envelope/<stream_id>/<study_id>_<stream_id>_e1__density.aif
  audio/stack/stack.aif
  audio/versions/versions.aif
  audio/percorso/percorso.aif
  sv/sweep/envelope/<stream_id>/<study_id>_<stream_id>_e1__density.sv
```

`generated/` è rigenerabile: dopo un aggiornamento basta rilanciare
`make sweep` / `make stack` / `make versions` / `make percorso`.

Con un blocco `for_each:` lo stesso albero, identico in ogni sotto-cartella,
scende di un livello — `generated/<study_id>/<label>/` — più uno `study.yml`,
lo snapshot del documento patchato che ha prodotto quell'audio, riscritto a
ogni render. Là i `.sv` prendono la label in coda al basename
(`<study_id>_<stream_id>_e1__density__distribution=0.5.sv`): l'audio no, il suo
nome lo cerca `cmd_sv` ed è già unico dentro la sua cartella.

## Comandi Make

```bash
make where  STUDY=<id>                    # cartelle di output correnti (una per combinazione)
make sweep  STUDY=<id>                    # genera tutte le stream
make sweep  STUDY=<id> STREAM=nome        # genera solo quella stream
make stack  STUDY=<id>                    # genera il documento multi-stream (stack, puro)
make versions STUDY=<id>                  # genera il documento delle versioni (prodotto cartesiano)
make percorso STUDY=<id>                  # genera il documento del percorso (orchestrazione temporale)
make render STUDY=<id>                    # renderizza gli YAML cambiati (incrementale, in parallelo)
make render STUDY=<id> FORCE=1            # rirenderizza tutto (es. dopo update engine o sample)
make render STUDY=<id> JOBS=4             # limita i worker paralleli (default: min(8, cpu))
make sv     STUDY=<id>                    # genera .sv per tutte le stream
make sv     STUDY=<id> STREAM=nome        # genera .sv per una stream
```

### Flag del comando `sv`

| Flag | Valori | Default | Descrizione |
|------|--------|---------|-------------|
| `--layout` | `multi`, `single` | `multi` | `multi`: un pannello per asse; `single`: tutti in un pannello |
| `--markers-scope` | `waveform`, `all` | `waveform` | Dove appaiono i marker di plateau: solo nel pane waveform o in ogni pane |
| `--no-markers` | — | — | Disabilita completamente i marker di plateau |
| `--stream` | nome stream | tutte | Genera `.sv` solo per la stream indicata |

Il pane waveform di ogni sessione `.sv` include automaticamente uno strato
spectrogram (finestra 8192, overlap 75%, White on Black, scala logaritmica)
sovrapposto alla forma d'onda.
