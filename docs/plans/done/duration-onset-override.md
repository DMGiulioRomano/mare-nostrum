# Duration/onset override per-stream con ereditarietà (issue #26)

Attuazione del design consolidato nel commento della issue #26. La parte a
valle (engine, `sv_export`, merge stem in `render.py`) legge già `onset` e
`duration` per-stream: tutto il lavoro è a monte, `study.yml → StudySpec →
stack/versions`.

## Obiettivo

- `duration:` top-level diventa un default, non un vincolo: ogni stream può
  dichiarare la propria `duration` (catena stream > versione > top-level).
- `onset:` diventa dichiarabile per-stream (default 0, solo per-stream: come
  chiave top-level del documento è rifiutata con errore chiaro).
- Il blocco `versions:` guadagna due chiavi riservate generate, `onset` e
  `duration`, che posizionano le versioni sulla timeline senza entrare nel
  prodotto cartesiano.

## Fase 1 — per-stream (`study_spec.py`)

Test (`tests/test_study_spec.py`):

- uno stream con `duration:` propria la vede come `spec.duration`; uno senza
  eredita il top-level (consolidamento del comportamento da deep-merge);
- uno stream con `onset:` propria la vede come `spec.onset`; assente → `None`;
- `onset:` top-level nel documento originale è rifiutata da `resolve_streams`
  (sia nel ramo con `streams:` sia in quello senza);
- validazioni: `duration <= 0` errore, `onset < 0` errore, tipi non numerici
  errore;
- il vincolo "stack richiede duration" non scatta se ogni stream risolve una
  duration (propria o ereditata); scatta, con messaggio aggiornato, per lo
  stream che non ne risolve nessuna.

Implementazione:

- `StudySpec.onset: float | None = None` (None distingue "assente" da un
  esplicito `onset: 0`, così `build_stack_stream` non schiaccia un eventuale
  `base.onset` ereditato);
- `parse_study_spec` legge `data.get("onset")` e valida `>= 0`; valida anche
  `duration > 0` quando presente. Nota di design: dopo il merge l'onset dello
  stream *diventa* chiave top-level del documento merged, quindi qui si legge
  normalmente — il rifiuto del top-level vive in `resolve_streams` sul
  documento **originale**, prima del merge;
- messaggio di `study_spec.py:491` riformulato: la condizione (documento
  merged senza `duration`) è già per-stream, cambia solo il testo (duration
  propria o ereditata, non "top-level obbligatoria").

## Fase 2 — stack (`stack.py`)

Test (`tests/test_stack.py`):

- `build_stack_stream` scrive `onset` nello stream engine quando
  `spec.onset` è dichiarato, e vince su un `base.onset` ereditato;
  con `spec.onset is None` il `base.onset` resta intatto;
- `generate_stack_document`: durata documento = `max(onset + duration)`
  sugli stream costruiti (oggi `max(duration)`, che sfora con uno stream
  spostato in avanti; `sv_export` la usa per l'end frame);
- stack senza `duration:` top-level ma con duration per-stream su ogni
  stream: documento generato senza errori.

Implementazione: `build_stack_stream` scrive `base["onset"] = spec.onset`
se non `None`; `generate_stack_document` legge onset/duration dagli stream
costruiti. Messaggio dell'errore duration-mancante allineato alla fase 1.

## Fase 3 — versions (`versions.py`)

`onset`/`duration` come chiavi riservate del blocco `versions:`; non entrano
nel prodotto cartesiano, generano una sequenza lunga N (numero combo) mappata
1:1 sull'ordine lessicografico delle versioni.

Test (`tests/test_versions.py`):

- `parse_versions` non tratta `onset`/`duration` come variabili (pop prima
  del ciclo; esenti dalla guardia "referenziata" e dal check nomi riservati);
  blocco con sole chiavi riservate e nessuna variabile → errore;
- sequenze riservate: `values` con lunghezza ≠ N → errore; `ramp` senza
  `step` → N valori equispaziati `start → stop`; `ramp` con `step` che genera
  ≠ N valori → errore; banda senza `n` → `n = N` (unico punto del progetto
  dove n è deducibile); banda con `n ≠ N` → errore; banda senza seed →
  `stable_seed("<study>:versions:onset")` / `"...:duration"`, deterministico;
- validazioni: onset generati `>= 0`, duration generate `> 0`;
- `onset[k]` = posizione assoluta della versione k (non monotono legittimo);
  onset per-stream relativo alla versione: `onset_finale = onset_versione +
  onset_stream`;
- `duration[k]` iniettata come `duration:` del documento della combo k prima
  di `resolve_streams` (default per gli stream della versione; una duration
  per-stream vince);
- chiavi riservate assenti → comportamento attuale (`onset = k * duration`);
  con `duration` riservata e `onset` assente le versioni si concatenano sulle
  durate generate (cumsum, generalizzazione della retrocompatibilità);
- durata documento = `max(onset_finale + duration_stream)` su tutti gli
  stream costruiti (nel caso classico coincide con `N * duration`);
- vincolo `duration:` top-level rilassato: serve solo quando non c'è né
  `versions.onset` (per posizionare) né `versions.duration` (per le durate);
  ogni stream che non risolve una duration erra comunque al parse (fase 1).

## Fase 4 — pulizia e documentazione

- `render.py`: il commento del merge stem ("le versioni non si sovrappongono
  mai") descrive l'assunzione vecchia, non un vincolo — aggiornarlo
  (l'overlay-add gestisce già la sovrapposizione);
- docstring: `versions.py` (modulo e `generate_versions_document`),
  `stack.py` ("durata condivisa" ora è un default; camminate-X ed envelope
  `time_mode: normalized` si normalizzano sulla duration propria dello
  stream — comportamento voluto, da dichiarare);
- `docs/study-yml-reference.md`: `duration:` top-level come default,
  `onset`/`duration` per-stream, chiavi riservate del blocco `versions:`.

## Impatto cross-repo

Nessuno: cambia solo la superficie di `study.yml` (granulation-studies). Il
documento engine prodotto usa chiavi che PGE supporta già. Niente issue su
PGE-ls/PGE-ui, niente bump del submodule nel paper CIM.
