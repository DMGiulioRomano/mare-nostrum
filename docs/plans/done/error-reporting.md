# Piano — error reporting con posizioni YAML e contesto di stream

**Repo:** `granulation-studies` (branch `claude/earloamo-v2jtbu`)
**Stato:** approvato, in implementazione TDD (test rossi → verdi, un commit per step).

## Il problema

Un errore di validazione di `study.yml` esce oggi come traceback Python nudo:

```
ValueError: Asse 'density': banda senza 'n' richiede la camminata-X 'base'
nel blocco 'stack:' (e' la X a possedere n); con X lineare dichiara 'n'.
```

Mancano le due coordinate che servono per correggere: **quale stream** stava
venendo validata e **a quale riga** di `study.yml` vive la chiave incriminata.
In piu' c'e' un bug che ha innescato il caso concreto: `cmd_render` (e
`describe`/`compose`/`render-final`) usano `_load_spec`, che valida il
**documento grezzo senza risolvere le stream**. Nei documenti in stile
stack-test il base e' incompleto per costruzione (la `n` vive negli override
di stream), quindi `render` fallisce anche quando ogni stream e' valida —
e l'errore, non riguardando nessuna stream, non puo' nominarne una.

## Design

Quattro pezzi, implementati in quest'ordine (ciascuno utile da solo):

### 1. Fix CLI: `_load_spec` passa da `resolve_streams`

`_load_spec` smette di validare il documento grezzo: risolve le stream come
gia' fanno `sweep`/`stack` e ritorna il primo spec (i campi che i comandi
consumano — `samples_dir`, `base`, `seed` — sono top-level, identici su ogni
stream). Effetto: il documento base incompleto smette di essere un falso
positivo, e ogni errore nasce gia' dentro il contesto di una stream.

### 2. Loader YAML con posizioni — `yaml_loc.py`

`yaml.safe_load` scarta i mark. Un `SafeLoader` esteso (nessuna dipendenza
nuova) registra durante il parse una tabella laterale
`{key-path → (riga, colonna)}`, con i path come tuple di chiavi/indici:
`("axes", "density", "base") → riga 44`.

`Locations.lookup(path, stream=None)`: con `stream` prova prima il path
dentro l'override (`("streams", sid) + path`), poi il base. Cosi' la
provenienza attraverso il deep-merge non richiede di mergiare la tabella:
la precedenza override-first rispecchia `_deep_merge` per costruzione
(il merge conserva le chiavi base e fa vincere l'override; `_replace_generators`
al piu' *toglie* chiavi, che quindi non vengono piu' cercate).

### 3. `SpecError` strutturato — `errors.py`

`SpecError(ValueError)` con campi: `msg`, `key` (path della chiave), `axis`,
`stream`, `hint`, `location` (riga), `source` (path del file). Modulo nuovo
per evitare cicli di import (`study_spec` importa `value_generators` e
`x_strategies`).

In `study_spec.py`:
- i `raise ValueError` diventano `SpecError` con `key`/`axis`/`hint`;
- `parse_study_spec` accetta `locs`/`source`/`stream` opzionali e risolve
  la `location` al momento del raise;
- i `ValueError` profondi (da `band`/`ramp` in `value_generators`, dalle
  guardie di `x_strategies`) vengono riavvolti in `SpecError` con il
  contesto dell'asse corrente, senza toccare quei moduli;
- `resolve_streams` etichetta con lo `stream_id` ogni errore nato dentro
  il parse di quella stream.

Retrocompatibilita': `SpecError` **e'** un `ValueError`, i test esistenti
con `pytest.raises(ValueError)` restano verdi.

### 4. Handler in `main()`

`main()` avvolge il dispatch: `SpecError` → blocco formattato su stderr,
exit code 2; `yaml.YAMLError` (che i mark li ha gia') → messaggio con
posizione. Traceback completo solo con `GRANSTUDIES_DEBUG=1`. Formato:

```
[granstudies] errore in studies/study_stack_test_5/study.yml

  posizione:  study.yml:41  (axes.density)
  contesto:   stream 'camminata_annidata'
  problema:   banda senza 'n' richiede la camminata-X 'base' nel
              blocco 'stack:' (e' la X a possedere n)
  rimedio:    dichiara 'n' nella banda oppure la camminata sotto
              'stack: {density: {base: ...}}'
```

`contesto: documento base (nessuna stream)` quando l'errore non nasce da
una stream.

## Non-obiettivi

- Nessun cambiamento alla semantica di parsing/merge/validazione: cambia
  solo *come* gli errori vengono riportati.
- Niente ruamel.yaml o altre dipendenze.
- I moduli scaffolding (`states.py`, `kinship.py`, ...) restano fuori:
  il sistema copre la pipeline viva (`study.yml` → sweep/stack/render).

## Test (TDD, un ciclo rosso→verde per step)

1. `tests/test_cli_load.py`: study in stile stack-test (base senza `n`,
   stream che la aggiungono) → `_load_spec` non solleva; su study
   single-stream ritorna lo spec di sempre.
2. `tests/test_yaml_loc.py`: posizioni di chiavi annidate, liste, override
   di stream; `lookup` override-first.
3. `tests/test_spec_errors.py`: ogni categoria di errore porta `key`,
   `axis`, `stream`, riga giusta e `hint`; errori profondi riavvolti;
   `pytest.raises(ValueError)` continua a funzionare.
4. `tests/test_cli_errors.py`: exit code 2, blocco su stderr senza
   traceback, `GRANSTUDIES_DEBUG=1` rilancia.
