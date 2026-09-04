# Percorso v1 — orchestrazione temporale dello stack (issue #29)

Attuazione del design consolidato nei commenti della issue #29 (memo di
brainstorming + memo di grilling). Il blocco `percorso:` è il quarto processo
del sistema: distribuisce istanze di spread sul tempo reale, con lo stesso
vocabolario degli altri assi. Nessun linguaggio nuovo; l'engine PGE non è
toccato (riceve il documento multi-stream finale, come per `versions`).

Questo plan fissa il perimetro del v1. La semantica fine è nel memo sulla
issue; qui vivono le fasi, i file toccati e i test.

## Obiettivo

- Blocco `percorso:` con due strategy di timeline mutuamente esclusive:
  enumerata (`onset:`) e camminata (`arco:` + `passo:`).
- `duration` d'istanza come traiettoria, `unit: factor` (default) | `s`,
  default legato.
- Traiettorie in grammatica-Env (come la `base` degli axes), campionate
  all'onset reale, iniettate nei `let` come fa `versions`.
- Primitiva `mix(A, B, w)` nella whitelist di `expr.py` — unica porta
  Env⊙Env, qualunque combinazione di forme, `w` anche Env.
- `spread.n` come nodo-expr; padding nomi stabile sul massimo `n`.
- Separazione dei processi (breaking): `make stack` torna puro, `versions`
  trasloca in `yaml/versions/`, nasce `yaml/percorso/`.

## Fase 0 — separazione dei processi (breaking, indipendente dal resto)

Test (`tests/test_cli_load.py` o nuovo `tests/test_cli_processes.py`):

- sottocomando `versions` dedicato: richiede il blocco `versions:`, scrive in
  `yaml/versions/versions.yml`;
- `stack` con blocco `versions:` presente produce lo stack puro (ignora il
  blocco) in `yaml/stack/stack.yml` — è l'ascolto dell'istanza di partenza;
- il render generico discende anche `yaml/versions/` (e poi `yaml/percorso/`).

Implementazione: sottocomando in `__main__.py`, target `versions` in
`make/studies.mk`. Nessun cambiamento a `versions.py` (cambia solo chi lo
chiama e dove scrive).

## Fase 1 — `mix()` in `expr.py`

Test (`tests/test_expr.py`):

- lerp scalare `mix(3, 8, 0.5) == 5.5`; broadcast scalare↔Env (lo scalare
  diventa Env costante);
- lineare↔lineare: breakpoint sull'unione dei tempi, risultato esatto in
  ogni punto (fast-path);
- step↔step: risultato `type: step` sull'unione, esatto;
- forme miste o `curve != 1` o `w`-Env con forme mobili: campionamento
  adattivo — suddivisione ricorsiva al punto medio finché lo scarto calcolato
  scende sotto tolleranza (proporzionale all'escursione); il test verifica il
  bound, non i punti esatti;
- `w` fuori [0, 1]: estrapolazione, nessun clamp;
- annidamento `mix(mix(A, B, w), C, v)`; firma rigida (3 argomenti
  posizionali, keyword rifiutate);
- il risultato entra nell'aritmetica esistente (Env⊙scalare ok, Env⊙Env
  resta vietato fuori da `mix`).

Rifinitura rimandata all'implementazione (con test d'ascolto): la
discontinuità pesata (step dentro morphing continuo), rappresentabile coi
type per-punto `[t, v, type]` che l'engine già accetta.

## Fase 2 — parsing del blocco `percorso` (nuovo modulo `percorso.py`)

Test (nuovo `tests/test_percorso.py`):

- strategy esclusive: `onset:` insieme ad `arco:`/`passo:` è errore; `k:` da
  solo è errore (messaggio che spiega le due strategy);
- strategy enumerata: `k` posseduto da `onset` (`values` → lunghezza, `ramp`
  con `step` → griglia); `k:` esplicito come cross-check (discordanza =
  errore stile `_resolve_n`); `ramp {start, stop}` senza `step` richiede `k:`;
- strategy camminata: `arco:` + `passo:` obbligatori insieme; `passo`
  scalare nudo ammesso;
- traiettorie: grammatica-Env (banda `base`/`range`/`drift`/`distribution`/
  `seed`, nodo-expr, scalare nudo = costante); `values`/`ramp` in una
  traiettoria = errore con hint sui contesti indicizzati;
- nomi riservati (`k`, `onset`, `arco`, `passo`, `duration`, più `i`/`n`/
  `pi`/`e`) rifiutati come nomi di traiettoria; guardia anti-refuso
  (traiettoria non referenziata da nessuna espressione = errore);
- `percorso:` richiede `stack:` (come `versions`); `percorso:` e `versions:`
  possono coesistere nel documento (processi indipendenti, li esercita il
  target).

## Fase 3 — timeline

Test (`tests/test_percorso.py`):

- enumerata: onset assoluti dal generatore su indice (riuso della semantica
  di `_timeline_sequence`);
- camminata: accumulo `t += passo(t)` con `passo` campionato all'onset
  corrente, generazione finché `t < arco`; ultima istanza può sforare;
  `passo <= 0` al campionamento = errore;
- `duration` traiettoria campionata all'onset dell'istanza, identica nelle
  due strategy; assente → legato (`onset_{k+1} − onset_k`; ultima:
  `passo(t_K)` in camminata, ultimo intervallo in enumerata);
- `unit: factor` (default): `duration_k = factor(t_k) × intervallo`; 1 =
  legato, >1 sovrapposizione, <1 buchi; `unit: s` assoluta;
- bordi: enumerata con `k = 1` e `unit: factor` = errore (serve `unit: s`);
- normalizzazione del tempo delle traiettorie: 0→1 su `arco` (camminata) o
  sull'ultimo onset (enumerata).

## Fase 4 — generazione del documento

Test (`tests/test_percorso.py`, integrazione stile `test_versions`):

- per ogni istanza: campionamento delle traiettorie al suo onset, iniezione
  nei `let` dei nodi-expr che le nominano (riuso di `inject_combo`),
  `resolve_streams` + `build_stack_stream` (le strategy di spread si
  rivalutano per istanza, come già con `versions`);
- `spread.n` come nodo-expr: valutato per istanza, deve dare intero >= 1;
- padding dei nomi di spread stabilizzato sulla larghezza del massimo `n`
  lungo il percorso (la stessa voce logica ha lo stesso nome ovunque esista);
- `stream_id` suffissato `nome__k=NN` (1-based, zero-padded sulla larghezza
  del K finale); onset finale = onset istanza + onset per-stream; la
  `duration` d'istanza fa da default del documento della singola istanza
  (una duration per-stream vince);
- la patch di spread (`ventaglio_5:`) si applica a ogni istanza in cui la
  voce esiste, e può contenere expr con variabili del percorso;
- seed invariato se non toccato: stessa camminata/pescaggio a ogni istanza,
  trasformata dalle variabili; il reseed è un override come un altro;
- durata documento = `max(onset + duration)`; output in
  `yaml/percorso/percorso.yml`, target `make percorso`.

## Fuori perimetro (parcheggiato, vedi memo issue #29)

- Patch di singola istanza (eccezione orizzontale): prima serve una
  convenzione per indirizzare le istanze, da scoprire con l'uso.
- `versions` di percorsi (confrontare K percorsi): la forma naturale è
  versions fuori, percorso dentro.
- `w` step dentro morphing continuo (discontinuità pesata): rifinitura
  d'implementazione con test d'ascolto.
- La rete (temperatura, similarità) e il controllo su grandezze derivate.

## Impatto cross-repo

A implementazione avvenuta, issue su `gl-ls`: nuovo blocco `percorso` (chiavi
riservate, due strategy, diagnostiche), `mix()` nella whitelist, `spread.n`
non più solo int, grammatica delle traiettorie. L'engine PGE non è toccato.
