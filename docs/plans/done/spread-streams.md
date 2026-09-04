# Piano — `spread`: stream generati per regola (macro-forma)

**Repo:** `granulation-studies` (branch `claude/stream-param-composition-wn90hi`)
**Stato:** implementato in questo branch (TDD, fette 1-6). Lingua: italiano,
no emoji.

Decisioni prese dall'utente (2026-07-09):

1. le regole di variazione sono le **strategies** già esistenti del vocabolario
   Y (`values` / `ramp` / banda `base`), trattate uniformemente;
2. gli stream generati vivono **di default solo nello stack** (sweep spento);
3. una entry esplicita omonima **ritocca il generato** (patch, non collisione);
4. la chiave riservata si chiama **`spread`**.

---

## 1. Intento

Comporre la macro-forma significa dare una **regola alle relazioni tra i
parametri di più stream**: otto stream identici tranne un parametro che cresce
di 0.1, entrate sfalsate a canone, volumi estratti da una banda. Oggi l'unico
modo è scrivere a mano otto entry quasi identiche in `streams:` — rumore che
nasconde la regola invece di dichiararla.

`spread` è un **generatore di stream**: una entry di `streams:` che, invece di
descrivere un solo override, ne genera `n`, distribuendo i valori di uno o più
parametri secondo una strategy. È l'asse mancante del sistema: Y distribuisce
valori **nel tempo** (micro-forma), la camminata-X distribuisce **i tempi**,
`spread` distribuisce valori **nella popolazione di stream** (macro-forma) —
con lo stesso vocabolario (`values` / `ramp` / banda).

Vincolo di confine: **puro pre-processing del dict `streams:`**. L'espansione
avviene in `resolve_streams` prima del loop di deep-merge; tutto ciò che sta a
valle (parse, sweep, stack, render) vede entry ordinarie e non cambia. Lo
`study.yml` sorgente non viene mai riscritto: il dict espanso si materializza
come artefatto ispezionabile in `generated/<studio>/yaml/streams_expanded.yml`
(lo "yaml di aiuto").

## 2. Sintassi

```yaml
streams:
  base: {}

  ventaglio:
    base:
      pointer:
        speed_ratio: 0        # override normale: vale per tutti i generati
    spread:
      n: 8                    # opzionale se una strategy possiede il conteggio
      over:
        base.pointer.start:
          ramp: {start: 0.1, step: 0.1}     # 0.1, 0.2, ... 0.8
        base.onset:
          values: [0, 1, 2.5, 4, 6, 8, 10, 12]
        base.volume:
          base: -12           # banda piatta: n estrazioni in [-12, -12+6]
          range: 6
          seed: 42            # opzionale: default stabile per-path

  # patch: ritocca il quinto stream generato (deep-merge sopra il generato)
  ventaglio_5:
    base:
      volume: -20
```

Espansione: `ventaglio` sparisce, al suo posto compaiono `ventaglio_1` …
`ventaglio_8` (indice 1-based, zero-padded alla larghezza di `n`: con `n: 12`
si ha `ventaglio_01` … `ventaglio_12`). Ogni entry generata è:

```
deep_merge( override dell'entry senza `spread`,
            deep-set dei path di `over` al valore i-esimo,
            patch esplicita omonima se presente )
```

in quest'ordine: la strategy vince sull'override comune, la patch vince su
tutto. La patch viene **consumata** (non diventa un nono stream).

## 3. Semantica

### Strategies e n-ownership

Le strategies sono riconosciute dalla forma con `y_generator` (riuso, non
reimplementazione): esattamente un marcatore tra `values` / `ramp` / `base`.

| Strategy | Forma | Possiede `n`? | Valori |
|---|---|---|---|
| `values` | lista esplicita | sì (`len`) | così com'è, anche non numerici (es. `sample`) |
| `ramp` | `{start, stop, step}` | sì (griglia) | `ramp()` esistente |
| `ramp` | `{start, step}` | no | `start + i*step`, i = 0..n-1 |
| `ramp` | `{start, stop}` | no | interpolazione lineare su n punti |
| banda | `base` / `range` / `seed` | no | `band(n, ...)` esistente |

Risoluzione di `n`: il valore esplicito `spread.n` e ogni conteggio posseduto
dalle strategies devono **coincidere**; se `n` è omesso lo definisce l'unico
conteggio posseduto. Nessuna fonte → errore. Conteggi discordi → errore.

Accoppiamento: con più path in `over` i valori si appaiano **per indice**
(niente prodotto cartesiano — stessa filosofia dello stack): lo stream i-esimo
prende il valore i-esimo di ogni strategy.

Seed della banda: esplicito se dichiarato, altrimenti
`stable_seed(f"{nome_entry}:spread:{path}")` — deterministico tra run, e path
diversi della stessa spread si decorrelano da soli. (Gli stream generati hanno
poi ciascuno il proprio `stream_id`, quindi i seed Y/X per-stream si
auto-decorrelano già col meccanismo esistente.)

### Default: solo stack

Se l'override dell'entry spread **non** dichiara `sweep:`, ogni entry generata
riceve `sweep: {orders: [], orderings: []}`: gli stream generati entrano nel
documento stack (ascolto verticale, il senso di uno spread) ma non moltiplicano
le varianti di sweep. Un `sweep:` esplicito nell'entry riattiva lo sweep e
viene ereditato tale e quale da tutti i generati.

### Patch e collisioni

- Entry esplicita con nome uguale a un generato → deep-merge **sopra** il
  generato, entry consumata. "Genera 8, poi ritocca a mano il quinto."
- Una patch che contiene a sua volta `spread` → errore (ambigua).
- Due spread che generano lo stesso nome: **strutturalmente impossibile**
  (emerso in implementazione) — l'indice è solo cifre e i nomi delle entry
  sono chiavi uniche del dict, quindi `a_i == b_j` implica `a == b`. L'unico
  incontro possibile è con una entry esplicita, cioè la patch.
- L'ordine del dict espanso preserva l'ordine del documento: i generati
  compaiono al posto dell'entry spread.

### Errori

`SpecError` con `stream=<nome entry>` e `key=("spread", ...)`: il lookup
override-first di `yaml_loc` risolve la riga dentro `streams.<nome>.spread`.
Casi: `over` assente o vuoto; `n < 1`; chiavi diverse da `n`/`over` nel blocco;
strategy assente o doppia (riavvolge il `ValueError` di `y_generator`);
conteggi discordi; `n` non derivabile; patch con `spread`; nomi generati in
collisione.

## 4. Architettura

- **Nuovo modulo `src/granstudies/spread.py`**: `expand_spreads(streams, locs)
  -> dict` — funzione pura, dict in ingresso, dict espanso in uscita.
  Nessun I/O, nessuna dipendenza da `study_spec` (per evitare cicli:
  `study_spec` importa `spread`, non viceversa).
- **`study_spec.resolve_streams`**: una riga in testa,
  `streams = expand_spreads(streams, locs)`. Nient'altro cambia.
- **`__main__`**: `cmd_sweep` e `cmd_stack` materializzano
  `generated/<studio>/yaml/streams_expanded.yml` (via `render._dump`,
  scrittura incrementale) quando lo studio contiene almeno una spread.
- **Docs**: sezione nuova in `docs/study-yml-reference.md` dopo il blocco
  `stack:`.

## 5. Fette TDD (rosso → verde, commit a suite verde)

1. **Core `expand_spreads`**: entry senza spread passano invariate; espansione
   con `values` (naming, padding, deep-set dei path, override comune
   preservato, iniezione `sweep` vuoto, `sweep` esplicito rispettato);
   risoluzione di `n`; errori di schema.
2. **Strategies `ramp` e banda**: le tre forme di ramp, banda con seed
   esplicito e derivato (determinismo), appaiamento per indice, conteggi
   discordi.
3. **Patch**: l'esplicito ritocca il generato e viene consumato; patch con
   spread → errore; collisione tra nomi generati → errore.
4. **Integrazione `resolve_streams`**: spec per-stream con `stream_id`
   generato, `orders`/`orderings` vuoti di default, parametro distribuito
   visibile in `spec.base`, patch applicata, righe d'errore da `yaml_loc`.
5. **CLI**: artefatto `streams_expanded.yml` scritto da `sweep`/`stack`.
6. **Docs**: reference aggiornata, piano spostato in `done/`.

## 6. Fuori scope (esplicito)

- Strategy moltiplicativa (`factor`, rapporti/detune) ed espressioni con
  indice: si aggiungono al vocabolario quando servono, la forma-strategy le
  accoglie senza cambiare schema.
- Spread annidati (spread dentro spread) e spread su path di `stack.*`:
  il deep-set generico non li vieta strutturalmente, ma non sono validati
  né testati — l'MVP valida path qualsiasi come stringhe puntate e basta.
- L'engine non si tocca: tutto vive in granstudies.
