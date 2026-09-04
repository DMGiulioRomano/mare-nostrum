# Manopole e ergonomia della sintassi `study.yml` — documento di design

Revisione del 2026-07-23, esito di una sessione di grilling sul documento
originale (risposta di Fable a `docs/plans/fable-sintassi-study-yml.md`). Le
decisioni qui sono state prese con l'utente, una per una; questo file le
consolida. Ogni affermazione sul comportamento attuale è marcata **[eseguito]**
(verificata lanciando codice in scratchpad) o **[dedotto]** (letta nel codice,
non eseguita).

> **Nota di aggiornamento (issue #47).** Gli esempi di questo documento che
> mettono una banda, un `ramp` o `values` **dentro un `let:`** sono scritti con
> la sintassi precedente alla separazione dei due ruoli di `values`. Da #47
> quella posizione vuole il wrapper di ruolo: `respiro: {linear_env: {ramp:
> {...}}}`. Il vocabolario dei generatori e le decisioni di design qui prese
> non cambiano — cambia solo il marcatore della *forma nel tempo*. Vedi la
> sezione «I due ruoli di una lista» in `docs/study-yml-reference.md`.

---

## L'esito in breve

Il problema vero non è "la sintassi è verbosa": è che ci sono **due assi di
variazione** — il tempo (l'inviluppo) e la voce (lo spread) — e la sintassi ha
un **collo di bottiglia scalare** fra i due. `spread.over` produce uno scalare
per voce; `expr` calcola scalari; nessuno dei due sa combinare un inviluppo con
un valore per voce. Il pattern `axes.density.base.base` (il "base annidato") non
è una scelta di stile: è la cicatrice di quel vincolo — per avere uno slot
scrivibile *dentro* la forma di un asse bisogna annidare un generatore solo per
usarne il `base` come slot.

La proposta scioglie il collo di bottiglia con quattro pezzi, tutti **additivi e
opt-in**:

1. **`let:` a tre livelli** — manopole nominate a livello documento, gruppo e
   voce. Un valore vive in un posto solo e più formule lo leggono per nome.
   Ombreggiare un nome già in scope è **errore**: niente regole di precedenza da
   ricordare.

2. **Aritmetica inviluppo⊕scalare** — un nome può valere un inviluppo; `expr` lo
   combina con scalari (tutti gli operatori). È la parte che elimina davvero il
   `base.base`: forma comune in una manopola, offset/scala per voce in un'altra,
   l'asse le combina in una riga leggibile.

3. **`spread.let`** — manopole di voce. Scalari per voce, deterministici
   (`expr` con `i`) o pescati (una banda = un pescaggio per voce). La
   differenziazione per voce diventa dichiarazione di nomi, non scrittura su
   path profondi.

4. **`versions:` ripensato** — resta il blocco della **sola analisi**
   (comparazione, ascolto). Da dizionario piatto di sequenze scalari a **assi
   ortogonali** in prodotto cartesiano, dove ogni asse è o un fascio di manopole
   parallele o un insieme di stati nominati con bundle ed envelope.

`let:` è per la **composizione** (lo stato di riposo del materiale);
`versions:` è per l'**analisi** (muovere quel materiale su una griglia). Restano
due blocchi distinti con lo stesso vocabolario di valori.

Cosa **non** si tocca: il vocabolario dei generatori (`values`/`ramp`/banda); i
moduli non vagliati (`states`/`kinship`/`walk`/`compose`/`descriptors`/
`curation`); il blocco engine `base:` (la rinomina che scioglierebbe l'ultima
ambiguità di `base` va rimandata alla svolta template). Nessun wrapper `band:`.

Uno `study.yml` che non usa nulla di tutto questo produce documenti identici: i
render esistenti e il diario di ascolto restano validi senza rigenerare niente.

---

## Il problema, visto da vicino

`studies/stack_1-50smp/study.yml` è il caso concreto.

### 1. Il collo di bottiglia scalare, e il `base.base` che ne nasce

`spread.over` scrive **un valore** su un path, per voce. `expr` calcola
**scalari** — un nome legato a una lista di breakpoint esplode
(`TypeError: '<' not supported between instances of 'str' and 'float'`,
**[eseguito]**). Quindi non esiste il modo diretto di dire "la voce *i* ha
*questo* inviluppo": l'unica leva è far sì che il pezzo scalare siano i
**parametri** di un inviluppo. E per avere un parametro scalare scrivibile
*dentro* la forma di un asse, bisogna annidare un generatore così che il suo
`base` diventi lo slot:

```yaml
axes:
  density:
    base:                     # il pavimento della banda...
      range: 1                # ...e' esso stesso una banda
      n: 5
      drift: {step: 0.2}
      # il suo `base` (base.base) e' lo slot che lo spread scrive per voce
    range: {expr: "d * 0.6"}
```

`axes.density.base.base` è il pavimento del pavimento. È leggibile solo se tieni
a mente lo spread (che scrive da fuori) e la forma dell'asse (che lo ospita)
contemporaneamente. Ed è fragile: se la forma dell'asse cambia, il path punta
nel vuoto.

L'utente ci era arrivato per una ragione precisa: gli serviva **sia** una
modifica per voce (valori diversi per ciascun cugino) **sia** una traiettoria
comune dello stesso parametro attraverso i cugini. Il `base.base` è l'unico
modo, oggi, di avere le due cose insieme — ed è illeggibile.

### 2. La traiettoria comune, di fatto, oggi non c'è

Verificato **[eseguito]** sul file reale (con `g=10, d=5` iniettati), il
pavimento della banda density per i primi tre cugini:

```
cugini_1  seed=3137670575  [6.370, 6.272, 6.370, 6.347, 6.238]
cugini_2  seed=3108221942  [6.315, 6.291, 6.217, 6.072, 6.008]
cugini_3  seed=3095517633  [6.412, 6.241, 6.214, 6.103, 5.990]
```

Tre camminate **diverse**, non una traiettoria comune traslata. Motivo
(`study_spec.py:126-128`): senza `axes.seed` esplicito il seed si auto-deriva
dallo `stream_id`, e lo spread clona l'intero `axes:` in ogni voce, quindi ogni
cugino ripesca la propria banda da zero. La "traiettoria comune" che l'utente
credeva di aver scritto non esiste: la condivisione della forma andrebbe
ottenuta con un `seed` fisso — cioè per effetto collaterale di un numero magico,
non per dichiarazione.

C'è anche uno squilibrio di scala: i livelli per voce iniettati distano ~0.25
fra voci vicine, ma la banda attorno ha `range: 1` — l'escursione della forma è
quattro volte la separazione delle voci, che infatti finiscono sovrapposte. La
differenziazione è sotto il rumore della forma.

### 3. Nomi che mentono

La banda-let `env` (riga 169) produce **uno scalare per voce**, non un envelope
(**[eseguito]**, dal mandato originale). Il nome suggerisce una forma nel tempo;
la sintassi non offre nessun posto dove il ruolo "un pescaggio per voce" sia
leggibile. Inoltre `env + i/(10-i)` mescola un pescaggio casuale (`env`, range
1.5) con un offset d'indice (~0.1 sui primi indici): l'utente voleva voci
**ordinate**, ottiene voci **sparse** perché la parte casuale domina. È un
refuso (confermato dall'utente).

### 4. Lo stesso numero, sciolto, in più punti

La manopola "grana" (`g`) compare in tre `let` con tre default diversi: `g: 25`
(riga 124, fallback), `g: 3` (riga 125, nel range), `g: 4` (riga 179, nello
spread) — **[eseguito]**. Con `make versions` i tre vengono ombreggiati e la
divergenza sparisce; con `make stack` convivono. Confermato refuso dall'utente:
unificarli su una manopola sola cambia il materiale a riposo (il pavimento del
range passa da 0.9 a 1.2), quindi la migrazione va fatta a orecchio, non a
regex. Stesso discorso per `d: 25` (righe 119 e 172).

### 5. `versions:` occupata dal ruolo di costante, e limitata

Una costante globale oggi si ottiene con `versions: {G: {values: [25]}}`
(**[eseguito]**, dal mandato): funziona, ma sequestra il processo d'analisi —
suffissi `__G=25`, `make versions` obbligatorio. E `versions:` è comunque
limitato: valori solo scalari (niente envelope), ogni variabile un asse a sé
(non puoi muovere due parametri insieme come un unico punto d'enumerazione).

---

## La proposta, pezzo per pezzo

### 1. `let:` a tre livelli

Il pattern compositivo a tre livelli esiste già ed è verificato senza modifiche
al codice (`tests/test_composizione.py`): una entry-spread può portarsi il
proprio `axes:`/`stack:` accanto a `spread:`, perché `proto` in `spread.py:650`
clona nei generati tutto ciò che non è la chiave `spread`. I `let:` seguono
esattamente quei tre livelli:

```yaml
# --- Livello 1: manopole di documento (lo stato di riposo comune)
let:
  d0: 25
  g0: 4

streams:
  cugini:
    # --- Livello 2: manopole di QUESTO gruppo (la sua forma nel tempo)
    let:
      respiro: {base: {ref: d0}, range: 1, n: 5, drift: {step: 0.2}}

    # --- Livello 3: manopole di voce
    spread:
      n: 6
      let:
        livello: {expr: "i * 0.8"}
      over:
        base.pointer.start: {values: [0.12, 0.25, 0.4, 0.55, 0.93, 1.1]}

    axes:
      density:
        base:  {expr: "respiro + livello"}    # forma comune + offset per voce
        range: {expr: "d0 * 0.6"}
```

Le chiavi mosse sono **manopole nominate**: dichiarate una volta, lette per nome
dalle formule. Ogni gruppo si porta le proprie (`respiro` in `cugini` e
`respiro` in un altro gruppo sono cose diverse e non si vedono a vicenda,
esattamente come gli `axes:` di gruppo già oggi).

**Regola cardine: ombreggiare un nome è errore.** Un `let:` non può ridichiarare
un nome già in scope in un livello superiore. Se un gruppo vuole un valore
diverso, gli dà un nome diverso — e a quel punto è ovvio, leggendo, che non
segue la manopola di documento. Questo **cancella** (invece di risolvere) la
decisione di precedenza `let`-di-gruppo vs `versions:` che il documento
originale aveva lasciato aperta, e doma la "cattura per nome": senza collisioni
possibili non c'è niente da catturare per sbaglio.

**Valori di `let:`.** Scalare, envelope disegnato (`[[t,v],...]`), o
pescato/generato (banda, `ramp`, `values`). Un nome vale quello che ci scrivi
dentro, con il solito riconoscimento per forma.

**Verificato [eseguito] (D):** l'iniezione per nome raggiunge un expr-node
dentro l'`axes:` di gruppo e sopravvive al deep-merge col padre magro *e*
all'espansione dello spread. Iniettando `d0=40` in `base: {expr: "d0 + i_off"}`
di gruppo: `cugini_1` centrato ~40, `cugini_2` ~45 (con `i_off = i*5`). Il
motore che alimenterebbe un blocco `let:` di gruppo — l'iniezione ricorsiva
negli scope `let` per nome — arriva a profondità di gruppo. (Testato che
raggiunge un expr-node *esistente*; il blocco `let:` come costrutto è nuovo, ma
il meccanismo è quello.)

### 2. Aritmetica inviluppo⊕scalare

Un nome può valere un inviluppo, e `expr` lo combina con scalari con **tutti gli
operatori** (broadcast dello scalare su ogni breakpoint):

```yaml
let:
  respiro: [[0, 5], [.3, 6.4], [.7, 5.8], [1, 6.1]]   # forma comune, disegnata

axes:
  density:
    base: {expr: "respiro + livello"}    # traslazione: stessa melodia, altezza per voce
    # oppure "respiro * (1 + i*0.3)"     # scala: la voce i respira piu' ampio
```

È la risposta diretta al problema 1/2: la forma comune sta in una manopola,
l'offset (o il fattore di scala) per voce in un'altra, e l'asse le combina in
una riga. Il `base.base` sparisce non perché l'annidamento sia vietato, ma
perché non serve più annidare un generatore solo per avere uno slot.

La forma comune può essere **disegnata** (lista di breakpoint) o **pescata**
(banda + drift, risolta *una volta* a livello di manopola invece che clonata per
voce): sono le due strategie che l'utente vuole entrambe, ed è di nuovo solo
riconoscimento per forma. La versione pescata è anche il modo pulito di dire
quello che oggi si direbbe con un `seed` fisso — "questa forma è comune", detto
invece che ottenuto per effetto collaterale.

**Costo:** sommare due inviluppi con breakpoint a tempi diversi richiede
allineamento (unione dei tempi + interpolazione). Decisione presa: partire da
**inviluppo⊕scalare soltanto**, che copre il caso reale e non apre il problema
dell'allineamento inviluppo⊕inviluppo.

### 3. `spread.let` — manopole di voce

La chiave `let` accanto a `n`/`over` nel blocco spread. Un nome vale un valore
**per voce**, in due forme (riconoscimento per forma):

```yaml
spread:
  n: 6
  let:
    livello: {expr: "d0 + i * 0.8"}                       # (a) deterministico per voce
    pesca:   {base: {ref: d0}, range: 1.5, drift: {step: .15}}  # (b) un pescaggio per voce
  over:
    base.pointer.start: {values: [0.12, 0.25, 0.4, 0.55, 0.93, 1.1]}
```

- **(a) `expr` con `i`** → numero funzione dell'indice: voci ordinate,
  ripetibili. È la differenziazione *composta*.
- **(b) banda** → un pescaggio casuale per voce (non dipende da `i`): voci
  sparse. È la differenziazione *pescata*. È ciò che oggi è `env`, ma col ruolo
  dichiarato dalla posizione invece che nascosto in un nome.

`over` **resta**: è la forma giusta per "scrivi questo valore su quel path"
(punti di lettura, pan, e valori non numerici come `sample`/`envelope`, che
`let`/`expr` non gestiscono). La divisione:

- `over` → destinazione unica, o valore non numerico;
- `spread.let` → il valore ha **più di un lettore** (un pescaggio condiviso da
  due parametri: oggi richiede la stessa banda-let copiata su due path con lo
  stesso `seed` a mano, che diverge comunque per arrotondamento — **[eseguito]**,
  E6 del mandato). L'utente conferma che il pescaggio condiviso gli serve.

**Ordine/precedenza — verificato [eseguito] (C).** La pipeline è
`inject_combo(raw)` **poi** `resolve_streams`→`expand_spreads`
(`versions.py:424-427`): versions inietta *prima* che lo spread espanda. Quindi
le variabili di `spread.let` (che nascono durante l'espansione) sono invisibili
a versions — coerente col modello: `versions:` opera a livello documento/gruppo,
`spread.let` a livello voce, i due piani non si toccano. Su collisione di nome,
oggi la scrittura per voce vince meccanicamente (iniettato `z=999`, poi lo
spread scrive `z=0/100` per voce → vince il per-voce). **Ma per la regola
"ombreggiare è errore" questa collisione dev'essere una guardia di validazione,
non una risoluzione silenziosa per ordine:** l'implementazione aggiunge la
guardia, non si affida all'ordine.

### 4. `versions:` ripensato — assi ortogonali

`versions:` resta il blocco della **sola analisi**. Ripensato da dizionario
piatto di sequenze scalari a **assi ortogonali** in prodotto cartesiano
lessicografico. Un asse ha **due forme, mutuamente esclusive**:

**Forma 1 — manopole parallele (co-varianti).** Una o più manopole che scorrono
insieme per indice. Ogni manopola è una **sequenza di scalari**, prodotta come
si vuole (`ramp`, `values`, banda: tutte danno una lista). La lunghezza
dell'asse è la **lista più lunga**; le più corte **tengono l'ultimo valore**.

**Forma 2 — stati nominati.** Il dizionario ha stati (`estrema`/`minima`),
ognuno un **bundle** di manopole, e lì i valori possono essere **envelope**
prodotti da qualunque generatore (`ramp`, banda, breakpoint espliciti). La
lunghezza dell'asse è il numero di stati. Uno stato è un **override parziale**:
le manopole non nominate restano al riposo di `let:`.

```yaml
versions:
  grana:                    # Forma 1: manopole parallele
    g0:  {ramp: {start: 4, stop: 50, step: 6}}   # 8 valori
    apr: [0, 2, 5]                                # 3 -> tiene 5 dalla 4a all'8a
  densita:                  # Forma 2: stati nominati
    estrema: {d0: 500, respiro: {ramp: {start: 20, stop: 60, step: 5}}}  # respiro = envelope
    minima:  {d0: 2}                              # bundle parziale: respiro -> riposo di let
# grana: lunghezza = max(8, 3) = 8 ; densita: 2 stati ; prodotto = 8 x 2 = 16 versioni
```

Le chiavi mosse sono le **stesse manopole di `let:`**: un asse le ombreggia
(riposo→movimento), e questo è il ponte fra analisi e composizione senza cambiare
linguaggio. Gli `stream_id` migliorano invece di peggiorare: da `__g=25` a
`__densita=estrema` (per gli assi a stati).

**Attenzione — lo stesso generatore ha due significati per posizione.** Un
`{ramp: ...}` come figlio diretto dell'asse (Forma 1) è una **sequenza di
versioni**; lo stesso `{ramp: ...}` come manopola dentro uno stato (Forma 2) è
un **envelope** (una forma nel tempo, in una versione sola). Non si distinguono
più dalla forma del valore — si distinguono dalla **posizione**. Non c'è più la
rete "lista piatta = versioni, `[[t,v]]` = envelope": tutto il carico di
disambiguazione ricade sul discriminatore d'asse (vedi note d'implementazione).

---

## Dimostrazione su `stack_1-50smp`

Stato attuale, condensato:

```yaml
axes:                                   # (gruppo cugini)
  density:
    base: {range: 1, n: 5, drift: {step: 0.2}}      # il livello lo scrive lo spread
    range: {expr: "d * 0.6", let: {d: 25}}          # copia 1 di d
  grain.duration:
    base: {expr: "g", let: {g: 25}}                 # copia 1 di g (fallback mai usato)
    range: {n: 6, base: {expr: ".3 * g", let: {g: 3}}, range: [0, 5]}   # copia 2
spread:
  over:
    axes.density.base.base:                          # path profondo, scrive nel gruppo
      expr: "env + i/(10-i)"                         # 'env' e' uno scalare per voce
      let:
        env: {base: {expr: "d", let: {d: 25}}, range: 1.5, drift: {step: .15}}  # copia 2 di d
    axes.grain.duration.base:
      expr: "floor(g + i/(10-i))"
      let: {g: 4}                                    # copia 3 di g
versions:
  g: {ramp: {start: 4, stop: 50, step: 6}}
  d: {ramp: {start: 0, stop: 20, step: 3}}
```

Con la proposta:

```yaml
let:
  g0: 4        # grana a riposo, campioni — l'unico posto dove il numero vive
  d0: 25       # centro banda density a riposo

streams:
  cugini:
    let:
      respiro: {base: {ref: d0}, range: 1, n: 5, drift: {step: 0.2}}   # forma comune
    spread:
      n: 6
      let:
        livello: {expr: "i * 0.8"}    # offset per voce (ordinato: era il refuso 'env + i/(10-i)')
      over:
        base.pointer.start: {values: [0.12, 0.25, 0.4, 0.55, 0.93, 1.1]}
        base.pan: {expr: "(1 - 2 * (i % 2)) * (i * 27)"}
    axes:
      density:
        base:  {expr: "respiro + livello"}   # forma comune + offset: niente base.base
        range: {expr: "d0 * 0.6"}
      grain.duration:
        base: {expr: "g0"}
        range: {n: 6, base: {expr: ".3 * g0"}, range: [0, 5]}

versions:
  grana:                              # muove per nome la stessa manopola del riposo
    g0: {ramp: {start: 4, stop: 50, step: 6}}
  densita:
    d0: {ramp: {start: 0, stop: 20, step: 3}}
```

Cosa è cambiato: ogni numero vive in un posto; i path profondi spariscono
(`over` resta solo per parametri veri); `env` diventa `livello` e il ruolo "un
valore per voce" è leggibile dalla posizione; la traiettoria comune è dichiarata
(`respiro`) invece che ottenuta col seed; `versions:` muove per nome le manopole
del riposo. **Nota d'ascolto, non di sintassi:** unificare i default oggi
divergenti (25/3/4) cambia il materiale di `make stack` — se una divergenza era
una scelta d'ascolto va tenuta come formula esplicita. La migrazione del file si
fa a orecchio.

---

## Note d'implementazione (da verificare in fase di build)

- **Il discriminatore d'asse di `versions:`** è il punto delicato. Il parser
  deve capire se un'entry d'asse è una manopola co-variante (generatore/lista,
  Forma 1) o uno stato (bundle di manopole, Forma 2). Caso limite: una
  co-variante definita per banda è `{base, range, n}` — un dict — e uno stato è
  `{d0, respiro}` — anche un dict. Distinguerli è lo stesso riconoscimento-per-
  forma banda-vs-non-banda che l'engine già fa: funziona ma è fragile. Serve
  probabilmente una regola esplicita o un marcatore, non l'indovinare. È anche
  la diagnostica più importante da dare a gl-ls.
- **La guardia "ombreggiare è errore"** va scritta su tutti e tre i livelli di
  `let:` e sul confine `spread.let`↔`versions:` (C): la meccanica attuale
  risolve per ordine, il design vuole errore.
- **Iniezione al load.** Il blocco `let:` top-level si aggancia al load del
  documento (choke point comune a tutti i comandi), *prima* dei processi, con
  la stessa meccanica di `versions._inject` (**[eseguito]** che l'iniezione per
  nome funziona a questo scopo, E2/E7 del mandato). Il `let:` di gruppo si
  aggancia dopo il merge (D verifica che l'iniezione ci arriva).
- **Aritmetica inviluppo⊕scalare** solo; inviluppo⊕inviluppo (allineamento
  temporale) è fuori dal primo passo.
- **`{ref: nome}`** è un segnaposto sintattico (potrebbe essere `!ref`, `$nome`,
  o bastare `{expr: "nome"}`): con la regola anti-ombreggiamento un `d0` dentro
  un gruppo può essere solo la manopola di documento, quindi `ref` serve solo a
  dire "la mia manopola parte da quella". Forma da decidere in fase di build.

## Non verificato

- `gain_compensation` su gruppi con livelli molto diversi (serve audio vero);
- il comportamento a valle di un envelope prodotto da `ramp` *dentro uno stato*
  di `versions:` (la Forma 2 è di design, la generazione envelope-da-generatore
  esiste per gli assi ma non è stata provata in quella posizione);
- l'implementazione reale della guardia anti-ombreggiamento e del discriminatore
  d'asse (il comportamento *attuale* è misurato; le regole nuove no).

---

## Impatto su gl-ls

Segnalazione, nessuna issue aperta (come da rule del repo: prima di aprire
qualcosa su gl-ls si avvisa l'utente e si chiede conferma). Se le proposte
avanzano, gl-ls è toccato così:

**Diagnostiche nuove che servirebbero:**
- schema dei blocchi `let:` a tre livelli e di `spread.let`;
- **ombreggiamento**: un `let:` che ridichiara un nome già in scope sopra →
  errore; una manopola di `spread.let` omonima di una variabile di `versions:`
  → errore (è la guardia C portata nell'editor);
- **discriminatore d'asse di `versions:`**: distinguere Forma 1 (co-varianti) da
  Forma 2 (stati) e segnalare i casi ambigui (banda-co-variante vs bundle-stato);
- risoluzione dei nomi di manopola: "nome in expr non risolto da nessuno scope",
  "manopola non referenziata da nessuna espressione";
- `spread:` con chiave `let` oggi è "chiavi non ammesse (solo n/over)": diventa
  legittima, la diagnostica va aggiornata;
- aritmetica inviluppo⊕scalare: segnalare inviluppo⊕inviluppo (non ammesso nel
  primo passo) come errore invece di lasciarlo esplodere a runtime;
- posizione dei nodi-expr: le tre posizioni che oggi crashano con `TypeError`
  grezzo (`baseline`, elementi di `values`, `gain_compensation`) segnalate
  nell'editor.

**Se un giorno si rinomina il blocco engine `base:`** (svolta template): tutte
le regole che nominano `base.` come prefisso-path andrebbero aggiornate, più una
diagnostica di deprecazione per la chiave vecchia. Altro motivo per rimandarla.
