# Allineare `bounds.py` all'engine

## Context

Uno `study.yml` con `grain.duration: 0.0001` (secondi) veniva rifiutato al parse
con "fuori bounds (0.001, 10.0)" pur essendo renderizzabile dall'engine. Causa:
in `study_spec.py` il floor dinamico si attivava solo se lo stream dichiarava
una `grain.duration_unit` non-secondi. Gia' corretto su `main` (`011d431`), ma
era il sintomo di un problema strutturale: **`bounds.py` mantiene a mano tre
tabelle che l'engine gia' pubblica**, e i chiamanti ricostruiscono il confronto
ognuno a modo suo.

Divergenze concrete oggi:

1. `output_sr` e' un parametro opzionale che, se omesso, **cambia
   silenziosamente il risultato** (floor 1 ms invece di 4 campioni). E' l'errore
   appena successo, ed e' invitato dalla firma.
2. `_MANUAL_BOUNDS` hardcoda `pitch.semitones`/`pitch.cents`, che l'engine
   calcola da solo (`pitch_unit.py:105` `EdoUnit.value_bounds`). **`pitch.ratio`
   manca**: l'asse `pitch.ratio` di `grana-001-41` (study.yml:54) oggi non e'
   validato affatto, mentre l'engine dichiara `(0.001, 8.0)`
   (`pitch_unit.py:140` `RatioUnit.value_bounds`). Le unita' `{edo: N}` non sono
   coperte in nessun modo.
3. `_PATH_TO_ENGINE_KEY` e' una lista scritta a mano di 10 path: mancano
   `pointer.start`, `loop_start`, `loop_end`, `loop_dur`, `grain.reverse`,
   `grain.read_direction`, `grain.envelope`. Un asse su quei path passa il parse
   senza nessun controllo. L'engine espone la mappa in
   `pge.parameters.parameter_schema.ALL_SCHEMAS` (sezione + `yaml_path` ->
   `param_key`).
4. Il confronto vive in tre posti diversi: `study_spec._validate` (converte a
   mano in secondi), `stack.py:165` (`clamp`, con `output_sr` sempre passato),
   `gainmap.py:145` (solo il factor). Solo il primo dei tre sbagliava, perche'
   e' l'unico che riscriveva la logica.

Esito voluto: **una sola funzione dice se un valore e' ammesso**, e i bounds
vengono dall'engine invece che da tabelle copiate.

## Interventi

### 1. `output_sr` di default in `bounds.py`

`bounds_for(path, output_sr=None)` -> se `output_sr` e' `None` usa
`default_output_sr()`. Chi vuole un sample rate diverso lo passa; nessuno puo'
piu' perdere il floor dinamico per omissione. Stesso trattamento in `clamp()`.

File: `src/granstudies/bounds.py` (`bounds_for`, `clamp`).

### 2. Bounds di `pitch.*` dall'engine

Nuova funzione in `engine_bridge.py`:

```python
def pitch_bounds(unit: str) -> ParameterBounds:   # 'semitones'|'cents'|'ratio'|'edo:N'
    from pge.parameters.pitch_unit import make_pitch_unit
    return make_pitch_unit(unit).value_bounds()
```

`bounds_for` riconosce il prefisso `pitch.` e usa l'ultimo segmento come nome
dell'unita' (e' gia' la convenzione dello `study.yml`: `pitch.ratio` significa
blocco `pitch` con unita' `ratio`). `_MANUAL_BOUNDS` sparisce. Unita'
sconosciuta -> `None` (nessun bound), come oggi per i path non mappati.

File: `src/granstudies/engine_bridge.py`, `src/granstudies/bounds.py`.

### 3. `_PATH_TO_ENGINE_KEY` derivata da `ALL_SCHEMAS`

Costruire la mappa a import-time da `ALL_SCHEMAS`: per la sezione `stream` e
`density` il path dotted e' gia' `spec.yaml_path` (`grain.duration`, `density`);
per `pointer` e' `f"pointer.{spec.yaml_path}"`. Scartare i path segnaposto
(`_dummy_fixed_zero_`, `_internal_calc_`). Resta una tabella manuale ridotta
solo per cio' che non e' in nessuno schema ma e' nel registry:
`pointer.deviation`, `num_voices`, `scatter`.

Conseguenza voluta: `pointer.start`, `loop_*`, `grain.reverse` ecc. diventano
path noti. Attenzione a `known_paths()`, che alimenta anche
`spread.split_axis_key` (`spread.py:95`): una chiave `pointer.start.values` si
splittera' su `pointer.start` invece che su `pointer` — e' il comportamento
corretto, ma va verificato con `tests/test_spread.py`.

Nota: i bounds di `loop_*` dipendono da `sample_dur_sec` nell'engine; non
passandolo il `max` resta `None` e si valida solo il minimo. Accettabile,
documentarlo nel docstring.

File: `src/granstudies/bounds.py`.

### 4. Un solo punto di confronto

Aggiungere in `bounds.py`:

```python
def violation(path, value, *, unit=None, output_sr=None) -> Optional[tuple]:
    """(lo, hi) in secondi se `value` e' fuori bounds, altrimenti None."""
```

`clamp` e la nuova `violation` condividono la stessa conversione
`grain_duration_factor`. `study_spec._validate` (righe ~250-283) si riduce a
chiamare `violation` e formattare l'errore: sparisce la conversione a mano e la
scelta locale di `output_sr`.

File: `src/granstudies/bounds.py`, `src/granstudies/study_spec.py`.

## Verifica

- `.venv/bin/python -m pytest -q` — tutta la suite verde (attenzione a
  `test_spread.py` e `test_bounds.py`, i piu' esposti).
- Nuovi test in `tests/test_bounds.py`:
  - `bounds_for("pitch.ratio") == (0.001, 8.0)` e coincide con
    `RatioUnit().value_bounds()`;
  - `bounds_for("pitch.semitones")` uguale a prima (-36, 36), ma ora derivato;
  - `bounds_for("pointer.start")` non e' piu' `None`;
  - `bounds_for("grain.duration")` senza `output_sr` da' il floor a 4 campioni,
    non 0.001.
- Nuovo test in `tests/test_study_spec.py`: un asse `pitch.ratio` con
  `values: [20]` fallisce al parse con "fuori bounds" (oggi passa).
- Regressione reale: `.venv/bin/python -m granstudies sweep grana-001-41` deve
  ancora partire (asse `pitch.ratio` 0.2-1.0, `grain.duration` da 0.0001).

## Fuori scope (deciso)

- Messaggio d'errore piu' diagnostico (bounds nell'unita' dell'asse, sample rate
  usato).
- Issue di impatto su `gl-ls` (regola `.claude/rules/gl-ls-impact.md`): i path
  validabili cambiano, andra' aperta prima di chiudere il lavoro.
- Discussione su `MIN_GRAIN_SAMPLES = 4` come vincolo di repo.
