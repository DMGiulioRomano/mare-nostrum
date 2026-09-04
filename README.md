# granulation-studies

Ciclo di studi compositivi sui parametri dell'elaborazione granulare.

Framework di **ricerca compositiva** sopra
[PythonGranularEngine](https://github.com/DMGiulioRomano/PythonGranularEngine)
(incluso come git submodule in `engine/`). Permette di esplorare metodicamente
lo spazio dei parametri del motore granulare, curare i risultati interessanti,
organizzarli in *stati* con una loro dinamica, e comporre brani come percorsi tra
quegli stati — il tutto producendo YAML che l'engine compila in audio.

## Pipeline

```
study.yml ──sweep────▶ yaml/sweep/*.yml ───────────┬─render──▶ audio + partitura
          ──stack────▶ yaml/stack/stack.yml ───────┤       │
          ──versions─▶ yaml/versions/versions__*.yml┤       │
          ──percorso─▶ yaml/percorso/percorso.yml ─┘       │
                              (ascolto + tag manuali)
                                          ▼
                                     results.yml ──┐
                                                   ▼
                                     states.yml ──matrix──▶ kinship.json
                                          │
                  composition.yml ──compose──▶ final.yml ──render──▶ brano
```

Vedi `docs/methodology.md` per il modello concettuale completo e i formati file.

## Avvio rapido

```bash
make setup                              # venv + submodule + dipendenze
# metti un file audio in samples/ (es. corpus.wav, vedi samples/README.md)
make sweep   STUDY=1-10ms
make stack   STUDY=1-10ms
make render  STUDY=1-10ms
make describe STUDY=1-10ms
# cura generated/base/results.yml (kept/tags), poi compila states.yml
make matrix  STUDY=1-10ms
make compose STUDY=1-10ms
make render-final STUDY=1-10ms
```

## Struttura

- `src/granstudies/` — il pacchetto (uno stadio per modulo).
- `studies/<id>/` — input versionati: `study.yml`, `states.yml`, `composition.yml`.
- `generated/<id>/` — output rigenerabile (git-ignorato).
- `samples/` — corpus audio (file git-ignorati, solo manifest versionato).
- `engine/` — submodule del motore (pin su commit).
- `tests/` — suite pytest (mirror di `src/`); `tests/e2e/` — end-to-end.

## Test

```bash
make tests        # suite veloce: gate obbligatorio prima di ogni commit
make e2e-tests    # end-to-end: study.yml -> CLI -> YAML -> audio
```

Le due suite sono separate. `make tests` gira su unit e golden e non tocca
disco fuori da `tmp_path`. `make e2e-tests` (marker `e2e`, cartella
`tests/e2e/`) parte da uno `study.yml` **su disco** in un repo temporaneo,
passa dalla CLI vera — `sweep`, `stack`, `versions`, `percorso`, `render` — e
dove il submodule `engine/` è inizializzato arriva al file audio, che verifica
non vuoto e non silenzioso. Senza il submodule i test che renderizzano si
skippano da soli, quelli sulla generazione restano.
