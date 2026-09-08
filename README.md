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

## Modalità take: non sovrascrivere l'audio già ascoltato

Di default ogni rigenerazione sovrascrive l'audio precedente. Con `TAKE`
attivo l'output va invece in `takes/<studio>/<data_ora>/`, un albero completo
per take: la versione di prima resta lì da riascoltare.

```bash
export TAKE=true                    # una volta per sessione
study 001-41-duration-pitch         # apre una take nuova e rigenera dentro
# ascolto, modifica di study.yml
study 001-41-duration-pitch         # nuova take; la precedente resta intatta

make takes STUDY=001-41-duration-pitch        # storico: data, peso, diff dello study.yml
make takes-clean STUDY=... KEEP=3             # tiene le 3 più recenti
```

Una take nuova nasce **solo se `study.yml` è cambiato** (se rilanci senza aver
toccato nulla resti nella stessa), e nasce come hardlink dell'audio di quella
prima: costa il tempo e il disco delle sole varianti effettivamente toccate
dalla modifica. Cambiare un valore dentro un asse muove poche varianti;
cambiare un parametro in `base:` le muove tutte, e la take pesa quanto uno
studio intero.

| `TAKE` | Cosa fa `study <nome>` |
|---|---|
| non impostata, `false`, `0`, `no`, `off` | come sempre: `generated/<studio>/`, sovrascrive |
| `1`, `true`, `yes` | apre una take se `study.yml` è cambiato, poi rigenera lì |
| `2026-09-08_1432` | rigenera dentro quella take, senza aprirne di nuove |

Per un singolo lancio fuori dalla modalità, senza toccare la sessione:
`TAKE=false study 001-41-duration-pitch`. Per sapere sempre dove si sta
scrivendo: `make where STUDY=...` (lo dice anche il render, in testa
all'output).

**La take la apre `study`.** Lanciando `make render STUDY=...` a mano con
`TAKE=true`, senza passare da `study` o `make take`, si rigenera **dentro la take
corrente sovrascrivendola**: la protezione sta nell'aprire la take, non nella
variabile.

Ogni take ha i **suoi** `.sv`, col nome della take nel basename
(`..._e2__grain.duration__pitch.ratio__2026-09-08_1432.sv`) e i path al suo
audio: `make sv` li rigenera dentro la take corrente (e `study` lo fa sempre).
Il nome della take nel file serve ad aprire due take insieme — Sonic Visualiser
identifica la sessione dal nome, e con due `.sv` omonimi la seconda non si apre. Non vengono ereditati dalla
take precedente — dentro un `.sv` il path dell'audio è assoluto, quindi una
sessione copiata aprirebbe in silenzio il suono di prima.

Per riascoltare una take vecchia senza rigenerare niente, i `.sv` sono lì:

```bash
sonic takes/001-41-duration-pitch/2026-09-08_1432/sv/sweep/**/*.sv
```

Cancellare una take non libera lo spazio che condivide con quelle più recenti:
il `du` della singola take sovrastima, la riga "totale su disco" di `make
takes` è quella vera.

> Dopo un aggiornamento del repo, la funzione `study` già caricata in una shell
> aperta resta quella vecchia (il precmd la ricarica solo al cambio di
> `GRANSTUDIES_ROOT`): `source .zsh_completions/_study`, o apri un terminale
> nuovo.

## Struttura

- `src/granstudies/` — il pacchetto (uno stadio per modulo).
- `studies/<id>/` — input versionati: `study.yml`, `states.yml`, `composition.yml`.
- `generated/<id>/` — output rigenerabile (git-ignorato).
- `takes/<id>/<data_ora>/` — storico delle rigenerazioni (git-ignorato, vedi sopra).
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
