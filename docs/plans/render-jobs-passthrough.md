# Il render dello studio girava a un core solo

Branch `perf/engine-jobs-passthrough`. Nessun cambio di sintassi `study.yml`,
nessun cambio nell'audio prodotto: solo tempo di render.

## Il sintomo

`make render STUDY=grana-001-41 FORCE=1` impiegava circa 6 minuti su una
macchina a 12 core, con 11 core fermi.

## La causa

Non è il volume di audio in sé — che è grande e voluto. Lo sweep di
`grana-001-41` ha un solo `ordering`, `[grain.duration, pitch.ratio]`, con 24
valori per il primo asse e 7 per il secondo: 168 gradini da 20s, cioè **3360
secondi (56 minuti) di audio in un unico file continuo**. È il modo giusto di
ascoltare uno studio a un asse — un solo file da percorrere — ma è anche il
motivo per cui il parallelismo *tra varianti* non serve a niente: di varianti
ce n'è una.

Il sistema ha due livelli di parallelismo e non se ne attivava nessuno.

**Livello 1, tra varianti.** `render_variants` (`src/granstudies/render.py`) ha
un `ProcessPoolExecutor` che dà una variante a ogni worker. Con una variante
sola il pool è degenere: un worker, un core.

**Livello 2, dentro una variante.** L'engine ha già il chunk-parallel
dell'overlap-add dei grani (`engine/src/pge/rendering/numpy_parallel.py`,
attivato da `NumpyAudioRenderer._overlap_add` quando `jobs > 1` e i grani
superano `DEFAULT_MIN_PARALLEL_GRAINS = 1024`). Ma `engine_bridge.render`
chiamava `pge.api.render(...)` **senza mai passare `jobs`**, e il default
dell'API è `jobs=1`. Quel path non veniva mai preso da `granstudies`: era
codice funzionante e mai raggiunto. Il target `brano` invece `--jobs` lo passa
da sempre (`make/render.mk`), ed è per questo che il brano non aveva lo stesso
problema.

## La soluzione

`--jobs` diventa il **budget totale di processi**, non più "quante varianti in
parallelo". `_split_jobs(budget, n_pending)` lo ripartisce tra i due livelli:

```python
workers     = max(1, min(budget, n_pending))
engine_jobs = max(1, budget // workers)
```

| caso | workers | engine_jobs |
|------|---------|-------------|
| una variante lunga (grana-001-41) | 1 | budget |
| varianti ≥ budget | budget | 1 (come prima) |
| `--jobs 1` | 1 | 1 (sequenziale puro) |

`workers * engine_jobs` non supera mai il budget, quindi quando i due pool si
annidano non c'è oversubscription. Il default resta `min(8, cpu)`: un buffer
stereo float64 da 56 minuti pesa ~2.6 GB e il chunk path ne fa transitare circa
un altro. `JOBS=12` per usare tutto.

## Cosa è stato toccato

- `src/granstudies/engine_bridge.py` — `render(..., jobs=1)` inoltrato a
  `api.render(jobs=...)`.
- `src/granstudies/render.py` — `_split_jobs`, e `_render_one` che passa `jobs`
  a entrambe le pass (mix e stems).
- `src/granstudies/__main__.py`, `Makefile` — help di `--jobs`/`JOBS`.

Il submodule `engine/` **non è stato toccato**: l'API `jobs` esisteva già.

## Test

- `tests/test_render.py::test_split_jobs_*` — la ripartizione, incluso
  l'invariante che il prodotto non superi mai il budget.
- `tests/test_render.py::test_render_passes_engine_jobs_to_bridge` — regressione
  diretta sul bug: il budget arriva davvero al bridge.
- `tests/test_engine_bridge.py::test_render_jobs_activates_parallel_path_without_changing_audio`
  — integrazione reale sull'engine con un documento abbastanza denso da
  superare la soglia dei 1024 grani (verificato: 1913 grani, path parallelo
  effettivamente preso), audio identico tra `jobs=1` e `jobs=4`.

## Quel che resta sul tavolo

Con `--stem` attivo di default ogni variante passa **due volte** dall'engine:
una per il mix, una per gli stem. `grana-001-41` ha un solo stream con
`onset: 0`, quindi lo stem è lo stesso audio del mix — un 2× quasi puro.
Eliminarlo intreccia la semantica di `sv export` (vuole sia il pane mix sia
quello stem) e il manifest di cache che governa lo skip incrementale: merita un
branch suo. Nel frattempo la via senza codice esiste già:
`make render STUDY=... STEM=false`.
