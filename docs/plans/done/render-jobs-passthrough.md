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

## Quanto rende, misurato

A/B sulla sola variante vera (3360s di audio, `STEM=false`, 12 core):

| | wall | CPU medio |
|---|---|---|
| `JOBS=1` (identico al pre-modifica) | 3m47 | 99% |
| `JOBS=12` | 2m36 | 180% |

**1.45×.** Meno di quanto la disponibilità di 12 core farebbe sperare, e vale la
pena sapere perché: per Amdahl solo ~34% del tempo sta nell'overlap-add, che è
l'unica parte che questo cambiamento parallelizza. Il resto è irriducibile qui —
la generazione dei grani vive nel processo padre (consuma il `random` seminato,
e parallelizzarla romperebbe la riproducibilità), più `dc_block`, clip,
scrittura di ~1.2 GB e il travaso dei buffer di chunk dai worker al padre via
pickle, che su un buffer da 2.6 GB non è gratis.

Il collo di bottiglia successivo non è quindi il numero di core: è il rapporto
tra grani generati e audio scritto.

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

**La variante orfana.** `generated/.../yaml/sweep/envelope/` contiene ancora
`e2__pitch.ratio__grain.duration.yml`, residuo di un `ordering` precedente:
`make sweep` lo segnala ("varianti orfane, rimuovile a mano") ma non lo cancella,
e `make render FORCE=1` lo ri-renderizza lo stesso. Sono 2400s di audio, circa
il 40% del lavoro di un render forzato, prodotti per niente. Cancellare quel
file (e il suo audio) rende più della modifica di questo branch.

**La doppia pass.**
Con `--stem` attivo di default ogni variante passa **due volte** dall'engine:
una per il mix, una per gli stem. `grana-001-41` ha un solo stream con
`onset: 0`, quindi lo stem è lo stesso audio del mix — un 2× quasi puro.
Eliminarlo intreccia la semantica di `sv export` (vuole sia il pane mix sia
quello stem) e il manifest di cache che governa lo skip incrementale: merita un
branch suo. Nel frattempo la via senza codice esiste già:
`make render STUDY=... STEM=false`.
