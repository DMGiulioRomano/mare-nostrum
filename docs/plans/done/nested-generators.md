# Piano — generatori annidati negli envelope di soglia

**Repo:** `granulation-studies` (branch `claude/nested-generators-granulation-s7cowp`)
**Stato:** proposta di design, **nessun codice scritto**. Le decisioni marcate
*(proposta)* vanno confermate; le *Questioni aperte* in fondo vanno discusse
prima di implementare. Lingua: italiano, no emoji.

Revisionato dopo la PR #12 (`feat(band)!`): modello a banda piatta senza
wrapper (`base`/`range`/`n`/`seed` diretti sull'asse), rinomine `rand` → `band`
(Y) e X-rand → camminata `walk`, blocco `stack:` piatto (niente più `cps:`),
`curve` nella forma dict degli `Env`.

---

## 1. Intento

Oggi i parametri-banda (`base`/`range` nella banda di Y, `base`/`range` della
camminata-X sotto `stack.<asse>`) accettano quattro forme statiche: scalare,
`[a, b]`, `[[t, v], ...]`, `{type, points, curve}`. La richiesta: poter
scrivere **un generatore dentro quei parametri**, ricorsivamente — una banda
dentro il `base` di una banda, un `ramp` dentro il `range` di una camminata-X,
a profondità arbitraria.

Dopo le PR #9 e #12 la banda di Y e la camminata-X condividono la stessa
semantica di banda `[base(t), base(t) + range(t)]` (`_band_at` / `_threshold_at`
nel modulo condiviso): il design qui sotto vale verbatim per entrambe, senza
casi speciali.

Vincolo di confine: **l'engine non si tocca**. I generatori annidati si
risolvono interamente in granstudies; l'engine continua a ricevere envelope
ordinari (`[[t, v], ...]` + `type`). Nessuna modifica a `yaml_builder`, ai
documenti generati, o al submodule.

## 2. Il punto d'appoggio: l'envelope di 2° ordine esiste già

`value_generators._threshold_at(spec, frac)` valuta già oggi una banda mobile:
è l'"envelope di secondo ordine" documentato in `study-yml-reference.md`. Il
tipo `Threshold` è il punto esatto dove innestare la ricorsione — non serve
inventare un livello nuovo, serve rendere ricorsivo un livello che c'è già.

Le tre seam dove un generatore viene invocato, tutte col **seed effettivo già
risolto** in mano:

| Seam | File | Cosa risolve |
|---|---|---|
| sweep / Y | `study_spec.parse_study_spec` (dispatch dopo `y_generator`) | banda con `n` al parse |
| stack / Y | `stack.axis_envelope` (entrambi i rami: `band_at` e `band`/`ramp`/`values`) | Y all'assemblaggio |
| stack / X | `stack.axis_envelope` → `x_strategies.walk` | tempi dalla frequenza |

## 3. L'idea cardine: una banda è un mini-asse

Un generatore produce `List[float]` (n valori). Un envelope è una funzione
`frac -> float`. Il ponte tra i due esiste già nel progetto: è quello che fa la
X-linear — n valori si stendono su tempi equispaziati `t_i = i/(n-1)` e
diventano breakpoint `[[t_i, v_i], ...]`.

Quindi: **un generatore annidato si compila in breakpoint**, cioè in una delle
forme che `Threshold` accetta già. Il bordo di una banda diventa un asse in
miniatura: **esattamente la grammatica piatta dell'asse** (`values`/`ramp`/
banda `base`), X implicita lineare, curva scelta con `type`/`curve` (come nella
forma `{type, points, curve}`).

Tre conseguenze che rendono il design piccolo:

1. **Le firme dei generatori non cambiano.** `band(n, base, range, seed)`
   accetta già breakpoint in `base`/`range`; idem `base`/`range` di `walk`.
   Il generatore annidato è zucchero che si desugara nella grammatica di oggi.
2. **La ricorsione vive in un punto solo**: una funzione di espansione in
   `value_generators.py`, chiamata alle tre seam prima di invocare il
   generatore. `_threshold_at`, `band`, `band_at`, `walk` restano puri e
   intoccati.
3. **Niente arriva all'engine.** I breakpoint annidati servono solo a
   disegnare la banda mentre si estraggono i valori esterni; nello YAML engine
   finisce, come oggi, soltanto l'envelope dell'asse.

### Alternativa scartata: valutazione lazy in `_threshold_at`

Insegnare a `_threshold_at` a riconoscere un nodo-generatore e risolverlo al
volo significherebbe rieseguire il generatore a ogni `frac` (O(n·m) invece di
O(n+m)) e infilare il contesto seed dentro una funzione oggi pura e calda.
Scartata: si **compila una volta**, si valuta n volte.

### Alternativa scartata: espansione al parse per tutto

Espandere tutto in `study_spec` (macro-expansion a monte) è pulito ma rompe
l'invariante dello stack: la banda Y senza `n` e la X si risolvono
all'assemblaggio, col seed per precedenza per-stream. L'espansione sta dove
sta già l'iniezione del seed: al momento dell'invocazione, per ciascuna seam.
(Per lo sweep quel momento coincide col parse — nessuna differenza pratica.)

## 4. Grammatica

```
Env ::= scalare                            # banda a livello costante
      | [a, b]                             # rampa lineare a -> b
      | [[t, v], ...]                      # breakpoint, interpolazione linear
      | {type: linear|step, points: [[t, v], ...], curve?: k}
      | {type?: linear|step, curve?: k, NODO}   # NUOVO: bordo generato

NODO ::= values: [v, ...]                  # stesi su t_i = i/(n-1)
       | ramp: {start, stop, step: Env}    # step mobile: accelerando/ritardando (§4.1)
       | base: Env (+ range?: Env, n, seed?)   # banda annidata, piatta come sull'asse
```

Il nodo parla **la stessa grammatica piatta dell'asse** (PR #12): niente
wrapper `rand:`, la banda annidata si marca con la presenza di `base` esattamente
come l'asse. Il predicato di riconoscimento è lo stesso di `y_generator`: dict
con **esattamente una** chiave-marcatore tra `Y_GENERATOR_KEYS`
(`{values, ramp, base}`), più le opzionali `type`/`curve` (e `n`/`range`/`seed`
quando il marcatore è `base`). Nessuna collisione con le forme esistenti:
`type`/`points`/`curve` non sono marcatori; le liste restano liste.

L'espansione è guidata da `Y_GENERATOR_KEYS` e dalla canonicalizzazione di
`y_generator` — il predicato di nodo e il walk generico sui parametri non
conoscono le singole strategie — quindi ogni generatore futuro aggiunto a quel
vocabolario diventa annidabile gratis, e ogni suo parametro di tipo `Env`
accetta a sua volta generatori.

Le due forme dict si generalizzano a vicenda: `{type, points, curve}` e
`{type, curve, <nodo>}` sono lo stesso involucro — `points` dà i breakpoint
letterali, il nodo li genera. `curve` viene gratis: il nodo si compila in
`{type, points, curve}` e la piega `u^k` (PR #12) si applica ai segmenti
generati come a quelli scritti a mano.

Regole:

- **`n` obbligatorio nella banda annidata.** La n-ownership è una faccenda del
  coupling X/Y degli assi; dentro un envelope non c'è coupling: il nodo deve
  poter produrre da solo la sua lista finita. Banda senza `n` in un `Env` è
  errore di parse. (`ramp` e `values` la posseggono per costruzione.)
- **X implicita lineare.** I valori del nodo si stendono equispaziati. Dare al
  mini-asse una sua strategy-X (tempi non equispaziati dentro la banda) è
  l'estensione naturale v2 — la forma a dict ha spazio per una chiave in più —
  ma resta fuori da questa iterazione.
- **Ricorsione ovunque c'è un `Env`**: quindi in `base`/`range` della banda
  annidata stessa — profondità arbitraria. Guardia di profondità esplicita
  (proposta: 8) nella filosofia di `MAX_POINTS`: meglio un errore chiaro che
  una config degenere (gli alias YAML ricorsivi esistono).

### 4.1 `ramp` con `step: Env` — accelerando e ritardando

Verificato sul codice: il `ramp` di oggi è **solo aritmetico**
(`ramp(start, stop, step)`, `step` scalare costante `> 0`). Accelerando e
ritardando non esistono ancora; questa estensione li introduce promuovendo
`step` da scalare a `Env` — la stessa mossa di `base`/`range`, quindi anche
`step` accetta le quattro forme statiche *e i generatori annidati*.

Semantica: `step` è una funzione del **progresso in valore**,
`frac = |v − start| / |stop − start|` (non dell'indice: il conteggio dei passi
non è noto a priori). Si itera `v += sign · step(frac(v))` finché si raggiunge
`stop`; `n` **emerge** dall'integrazione, come i tempi della camminata-X.

```yaml
ramp: {start: 5, stop: 100, step: 5}          # oggi: passo costante
ramp: {start: 5, stop: 100, step: [10, 1]}    # accelerando: i passi si stringono
ramp: {start: 5, stop: 100, step: [1, 10]}    # ritardando: i passi si allargano
ramp:
  start: 5
  stop: 100
  step:
    n: 4                                      # rampa a passo stocastico (ricorsione)
    base: 1
    range: 6
```

Guardie: `step(frac) <= 0` in qualunque punto → errore (passo nullo = loop
infinito, come la frequenza non positiva della camminata-X); tetto punti alla
`MAX_POINTS`. `ramp` resta deterministico e continua a possedere `n`; il caso
scalare resta identico al comportamento attuale (retrocompatibile, conteggio
anti-drift incluso).

Nota di disambiguazione, importante per non confondersi con lo stack: questo è
l'accelerando **dei valori** (la griglia di Y si infittisce). L'accelerando
**nel tempo** (breakpoint che si addensano sulla timeline) è dominio della
strategy-X — e in forma deterministica **esiste già**: camminata a banda
collassata (§4.2). Per la piega *dentro un segmento* c'è invece già `curve`
(PR #12), che agisce sulla rampa tra due breakpoint, non sulla griglia.

### 4.2 Censimento: cosa è promuovibile a `Env`, registro per registro

X e Y non si trattano allo stesso modo: cambiano sia il **dominio** su cui un
`Env` viene consultato, sia **quali parametri** ha senso promuovere.

**Il criterio.** Un parametro è promuovibile a `Env` se e solo se la strategia
lo consulta **ripetutamente lungo la generazione** — a ogni punto (Y) o a ogni
passo della camminata (X). I parametri consumati una volta sola — estremi,
cardinalità, seed, durata — restano scalari: un `Env` valutato in un punto solo
è uno scalare travestito. Il criterio vale anche per le strategie future: chi
entra nel vocabolario dichiara Env i parametri che legge per-punto, e quelli
soli.

**Il dominio, la vera differenza X/Y:**

- **Y** consulta i suoi `Env` alla **posizione del punto sull'asse `[0,1]`
  dello stream**: `i/(n-1)` quando `n` è della Y (sweep, X-linear), il tempo
  reale normalizzato dei breakpoint quando `n` è della X (`band_at`, rspline).
  Un generatore annidato in un `Env` di Y si stende su quell'asse. Eccezione
  interna: lo `step` di `ramp` vive sul **progresso in valore** (§4.1), perché
  lì l'indice non è noto a priori.
- **X** consulta i suoi `Env` sul **tempo reale normalizzato** durante la
  camminata (`t/duration`). Un generatore annidato nel `base`/`range` di
  `stack.<asse>` si stende sulla timeline vera dello stack.

La meccanica di espansione è identica (nodo → breakpoint su `[0,1]`); a
cambiare è **cosa quel `[0,1]` misura**. La reference lo dice già per `curve`
(«la piega è la stessa, il dominio no»): per l'annidamento vale la stessa nota.

| Registro | Strategia | Parametro | `Env`? | Dominio |
|---|---|---|---|---|
| Y | `values` | gli elementi | no — è la foglia esplicita per definizione | — |
| Y | `ramp` | `start`, `stop` | no — estremi, consumati una volta | — |
| Y | `ramp` | `step` | **sì — nuovo (§4.1)** | progresso in valore |
| Y | banda (`band`) | `n` | no — cardinalità | — |
| Y | banda (`band`) | `base`, `range` | già `Env` oggi | posizione del punto |
| Y | banda (`band`) | `seed` | no — identità dell'estrazione | — |
| X | `linear` | `n` (dalla Y) | no — cardinalità | — |
| X | camminata (`walk`) | `base`, `range` | già `Env` oggi | tempo reale normalizzato |
| X | camminata (`walk`) | `duration`, `seed` | no | — |

Quindi: i punti d'innesto dell'annidamento sono `base`/`range` (banda Y),
`base`/`range` di `stack.<asse>` (camminata-X) e il nuovo `step` (Y-ramp).
Tutto il resto resta scalare per natura, non per pigrizia. (`curve` non è un
parametro di generatore: vive dentro la forma dict di un `Env`, e l'annidamento
la eredita per costruzione.)

**Le bande collassate, verificate sul codice.** Nella camminata `range` è
opzionale con default `0.0` (`x_strategies.walk`): `stack: {asse: {base: [2, 8]}}`
senza `range` è già oggi un **accelerando deterministico nel tempo** — la banda
collassa e la frequenza segue `base` (il seed non influisce sui tempi). Il
gemello Y esiste dal PR #9: banda con `range` omesso insegue `base`
deterministicamente su `n` punti. Le due bande collassate sono gli *inseguitori
di curva* dei due registri; con l'annidamento, anche le curve inseguite possono
essere generate. Una strategy-X `ramp` dedicata sarebbe quindi ridondante
(stessa cosa, parametrizzata a passo invece che a frequenza).

## 5. Esempi

Banda Y con bordi generati (sweep o stack, identico) — il nodo annidato è
piatto come l'asse che lo contiene:

```yaml
axes:
  density:
    path: density
    n: 40
    base:
      n: 6                       # il pavimento della banda: random walk a 6 punti
      base: 2
      range: 6
    range:
      type: step                 # la larghezza: salti netti tra 4 e 14
      n: 6
      base: 4
      range: 10
```

Camminata-X dello stack con frequenza di generazione essa stessa stocastica —
il caso citato nella richiesta, con un terzo livello:

```yaml
stack:
  density:
    base:
      n: 8                       # la base salta tra 2 e 6 Hz
      base: 2
      range: 4
    range:
      n: 5
      base: 0.5
      range:
        ramp: {start: 1, stop: 4, step: 1}   # terzo livello
```

## 6. Semantica: cosa aggiunge (e cosa no)

Musicalmente l'annidamento è **controllo della varianza a più scale
temporali**: la banda esterna dà la fluttuazione punto-per-punto, la banda
annidata dà la deriva a media scala, un livello ancora sotto disegna la
macro-forma. La scomposizione `base`/`range` (PR #9, resa piatta dalla #12)
rende le due leve ortogonali anche qui: annidare in `base` muove il **centro**
della tessitura (la banda trasla come un corpo solo, larghezza intatta),
annidare in `range` ne fa **respirare la varianza** (il centro sta fermo, la
dispersione si apre e si chiude). È l'idea rspline-di-rspline; col vocabolario
del progetto: un `range` con `type: step` costruisce **plateau di banda** — si
fa sedere lo stream in una regione stocastica, poi si salta a un'altra.

Casi degeneri, da documentare per onestà:

- `ramp` annidato **a passo costante** con interpolazione linear ≡
  `[start, stop]`: non aggiunge nulla (e la sola piega del segmento è già
  `curve: k` sulla forma statica, senza annidare niente). Aggiunge con
  `type: step` (banda a scalini) o con `step: Env` (§4.1): l'accelerando curva
  la *griglia* della rampa, e annidato in un bordo dà una banda che deriva con
  morfologia non lineare.
- `values` annidato ≡ `[[t, v], ...]` con tempi equispaziati: solo comodità.
- la banda che si muove a larghezza costante non richiede trucchi: `base`
  annidato + `range` scalare. Con il vecchio vocabolario `min`/`max` sarebbe
  servito correlare due generatori con lo stesso seed; la scomposizione
  `base`/`range` lo dà per costruzione, e l'annidamento la eredita.

## 7. Seed: derivazione gerarchica

Requisiti: deterministico tra run e macchine (ciclo rigenera-e-confronta),
decorrelato tra `base` e `range` e tra profondità, esplicito che vince ovunque.
Stessa filosofia della catena esistente (il più specifico vince; auto-derivazione
CRC32 con salt).

*(proposta)* Ogni banda annidata senza `seed` proprio deriva:

```
seed_figlio = stable_seed(f"{seed_effettivo_del_padre}:{path_locale}")
```

dove `path_locale` è `base` o `range` (il parametro in cui il nodo è innestato,
più `step` per il ramp §4.1) e si concatena scendendo: `base.range`, ... Vale
identico nei due registri — per la Y il padre è il seed della banda d'asse, per
la X quello della camminata (già decorrelati a monte dai salt `:y`/`:x` della
catena esistente). Proprietà:

- cambiare il seed esterno **riseeda l'intero sottoalbero**: l'oggetto si
  rigenera coerente;
- fissare un seed a un nodo **congela solo quel sottoalbero**;
- `base` e `range` si decorrelano da soli (path diversi);
- il padre ha sempre un seed effettivo definito, perché l'espansione avviene
  alla seam dove la catena per-asse → globale → auto per-stream è già risolta.

`ramp` e `values` non consumano seed: la derivazione attraversa i nodi
deterministici senza consumare nulla (il path però li include, così una banda
sotto un `ramp` resta stabile se si riordina il resto).

## 8. Dove vive nel codice

Tutto in granstudies, tre file toccati più i test:

1. **`value_generators.py`** — il cuore, ~3 funzioni nuove:
   - `is_generator_node(spec) -> bool`: il predicato del §4 (riuso di
     `Y_GENERATOR_KEYS` e della logica di `y_generator`);
   - `expand_env(spec, *, seed, path, depth) -> Threshold`: compila un nodo in
     breakpoint (o `{type, points, curve}` se il nodo ha `type`/`curve`),
     ricorsivo;
   - `expand_params(params, *, seed, path) -> dict`: cammina i parametri di un
     generatore e espande ogni valore che è un nodo (walk generico sui dict,
     così il `base`/`range` della camminata si trova senza schema per-strategia);
   - `ramp` riscritto per `step: Env` (§4.1): iterazione a passo mobile con
     guardie, ramo scalare identico all'attuale.
2. **`study_spec.py`** — seam sweep/Y: `expand_params` sui `gen_params` in
   `parse_study_spec`, subito dopo il `setdefault("seed", default_y_seed)`,
   prima di invocare `band`.
3. **`stack.py`** — seam stack: `expand_params` su `y_kwargs` (entrambi i rami)
   e su `x_params` dopo i rispettivi `setdefault("seed", ...)`. Da rilassare la
   whitelist di `_stack_config` (oggi `{base, range, seed}` con valori qualsiasi:
   i nodi annidati sono *valori* di `base`/`range`, quindi dovrebbe già passare —
   verificare con un test).
4. **`x_strategies.py`** — invariato: `walk` riceve `base`/`range` già espansi.
5. **`docs/study-yml-reference.md`** — la tabella delle forme di `Env` (sezione
   «`base` — banda, seeded») guadagna la riga del nodo generato, con gli esempi
   del §5 e il trucco dei bordi correlati; la nota sul dominio ricalca quella
   già scritta per `curve`.

Nota di doppia risoluzione: per un asse sweep con banda Y, il parse espande e
risolve i valori, ma `Axis.generator` conserva la config grezza per lo stack,
che ri-espande all'assemblaggio. Stesso seed → stessi breakpoint: le due
espansioni non possono divergere.

Nota sul merge di stream: la forma-nodo è un dict, quindi negli override di
`streams:` si **fonde** ricorsivamente come ogni dict (stessa regola già
documentata per `curve`: ridefinire una chiave non azzera le sorelle). Per
rimpiazzare in blocco un bordo generato si usa una forma lista, che rimpiazza.
Da documentare accanto alla nota su `curve` e override.

### Walk generico vs schema esplicito

Un'alternativa più rigida: dichiarare per ogni generatore quali parametri sono
di tipo `Env` (`ENVELOPE_PARAMS = {"band": {"base", "range"}, ...}`) ed espandere
solo quelli. Più contratto, più boilerplate, e ogni generatore futuro deve
registrarsi due volte. Col predicato stretto del §4 il walk generico non ha
falsi positivi sul vocabolario attuale — l'unica forma dict legittima di un
`Env`, `{type, points, curve}`, non contiene marcatori. *(proposta: walk
generico; se un giorno un generatore avrà un parametro dict che può confondersi,
si passa allo schema.)*

## 9. Validazione ed errori

- **path negli errori**: l'espansione porta con sé il path di config
  (`axes.density.base.base`) e ne decora i `ValueError`; il runtime
  `range negativo a frac=...` di `_band_at` resta l'ultima rete.
- banda annidata senza `n` → errore al parse (§4).
- due chiavi-marcatore in un nodo → errore standard (riuso del messaggio di
  `y_generator`).
- profondità oltre la guardia → errore esplicito.
- `curve` con `type: step` dentro un nodo → stesso errore della forma statica
  (il nodo si compila in `{type, points, curve}` e la validazione esistente di
  `_threshold_at` fa il resto).
- i valori estratti dalla banda esterna restano clampati ai bounds engine dove
  già avviene (stack); i breakpoint *interni* non si clampano: sono soglie, non
  valori di parametro.

## 10. Piano di test (TDD, `tests/test_value_generators.py` + `test_stack.py`)

- unit espansione: `values`/`ramp`/banda annidati → breakpoint attesi; nodo
  con `type: step`; nodo con `curve`; profondità 3; passthrough delle forme
  statiche esistenti (inclusa `{type, points, curve}`).
- seed: stessa config → stessi breakpoint tra due run; `base`/`range`
  decorrelati di default; seed esplicito nel nodo vince; cambiare il seed
  esterno cambia il sottoalbero; banda a larghezza costante con `base` annidato
  e `range` scalare.
- ramp accelerando: `step: [a, b]` produce passi monotoni attesi; ramo scalare
  invariato bit-a-bit (regressione anti-drift); `step` che tocca 0 → errore;
  tetto punti; generatore annidato dentro `step`.
- bande collassate (idiomi §4.2): camminata senza `range` → tempi deterministici
  che seguono `base`; banda Y senza `range` → insegue `base`; entrambe con
  un generatore annidato nella curva inseguita.
- errori: banda annidata senza `n`; due chiavi-marcatore; profondità oltre
  guardia; `range` negativo con path nel messaggio; `curve` + `type: step` nel
  nodo.
- integrazione stack: study di prova con nested nel `base` della camminata →
  `stack.yml` identico tra due generazioni; le combinazioni di n-ownership
  esistenti non cambiano output (regressione con i 4 study `study_stack_test_*`);
  whitelist di `_stack_config` con nodo annidato in `base`/`range`.
- integrazione streams: override parziale di un bordo generato (merge dict) e
  rimpiazzo con forma lista.
- una volta implementato: `study_stack_test_5` come studio-documentazione dei
  generatori annidati, nello stile dei quattro esistenti.

## 11. Questioni aperte — decise con l'utente (2026-07-08)

1. **Strategy-X per il mini-asse**: rinviata a v2. La grammatica ha spazio; la
   X-`ramp` dedicata resta ridondante (camminata a banda collassata, §4.2).
2. **Chiave di curva nel nodo**: **`type`**, valori **`linear|step`** soltanto.
   Niente `cubic` nelle bande — conferma della scelta già presa in `07adb9e`
   («cubic non implementato: marginale su banda campionata a caso»); la piega
   non lineare del segmento è coperta da `curve: k`.
3. **`values` annidato**: **sì**, per simmetria col vocabolario dell'asse.
4. **Guardia di profondità**: **8**.
5. **Sintassi della banda annidata**: **piatta**, coerente col modello della
   PR #12 (`base: {n, base, range}`, nessun marcatore dedicato). Il «quarto
   `base`» va aggiunto alla nota di disambiguazione della reference.
