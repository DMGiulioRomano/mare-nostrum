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

## `graph` — la rete delle varianti discrete

Con `sweep.mode: discrete` ogni punto della griglia è un file a sé, e il nome
porta le coordinate:

```
o2__grain.duration=0.001__pitch.ratio=0.447.aif
```

`make graph STUDY=<id>` rilegge quei nomi e scrive un `graph.html` autonomo
dentro `generated/<id>/[<combo>/]audio/sweep/discrete/`: una griglia
cliccabile dove ogni cella suona il suo file, le frecce si spostano fra celle
vicine, e i link in fondo portano alle altre combinazioni di `for_each:` già
renderizzate.

```bash
make render STUDY=001-41    # serve l'audio: graph legge i .aif, non gli YAML
make graph  STUDY=001-41
open -a Safari "$(make -s where STUDY=001-41)/audio/sweep/discrete/graph.html"
```

Aprilo con **Safari**: Chrome non legge AIFF. Nessun server e nessuna
dipendenza — i `src` sono relativi e l'HTML sta accanto all'audio.

L'export per Sonic Visualiser (`make sv`) resta sul ramo `envelope`, dove i
marker sono i plateau dello sweep; per i file discreti la navigazione è
`graph`.

## `for_each:` — n valori del parametro, n file

Gli `axes:` di uno studio scorrono **dentro** il file: su
`001-41-duration-fill-factor` i due assi fanno 24 × 7 gradini da 7s, cioè venti
minuti a variante. Un terzo asse triplicherebbe la durata, e il confronto fra
`distribution: 0` e `distribution: 1` finirebbe a mezz'ora di distanza.

`for_each:` è l'asse **esterno**: non allunga il file, ne fa uno per valore.

```yaml
for_each:
  base.distribution: {values: [0, 0.5, 1]}   # 3 render dello stesso sweep
```

```bash
study 001-41-duration-fill-factor           # genera e apre tutte le combinazioni
COMBO=distribution=1 study 001-41-...       # solo la fetta a distribution 1
make where STUDY=...                        # dove si sta scrivendo, una riga per combinazione
```

Ogni combinazione ha il suo albero completo sotto
`generated/<studio>/distribution=0.5/`, con dentro anche lo snapshot dello
`study.yml` patchato che l'ha prodotta e i suoi `.sv` (la label è nel basename:
Sonic Visualiser identifica la sessione dal nome, e con due `.sv` omonimi la
seconda non si apre — proprio il confronto per cui gli assi esterni esistono).

`COMBO` taglia una **fetta**: i vincoli sono segmenti di label separati da
`__`, in and fra loro (`COMBO=coppia=speed-pitch__distribution=0.3`), e il
match è per segmento intero (`distribution=0` non prende `distribution=0.3`).
Con più assi esterni le combinazioni sono decine e generarle tutte non ha
senso: il documento dichiara lo spazio, `COMBO` sceglie cosa materializzare
oggi.

Le chiavi sono path su tutto il documento, non solo su `base:` — quindi
funziona anche dove un asse interno non potrebbe esistere: `stack.seed` (cinque
realizzazioni della stessa camminata stocastica), `percorso.arco` (la stessa
legge distesa su tre durate), `axes.*.values` (due griglie diverse dello stesso
studio). Per gli override non scalari serve un nome:

```yaml
for_each:
  griglia:
    fitta: {axes.fill_factor.values: [0.5, 0.7, 0.85, 1, 2, 4, 8]}
    rada:  {axes.fill_factor.values: [0.5, 1, 4]}
```

Dettagli, guardie e forme in `docs/study-yml-reference.md`. Togliere un valore
dal blocco non cancella la sua cartella: resta lì con l'audio già ascoltato,
segnalata come orfana.

> Dopo un aggiornamento del repo, la funzione `study` già caricata in una shell
> aperta resta quella vecchia (il precmd la ricarica solo al cambio di
> `GRANSTUDIES_ROOT`): `source .zsh_completions/_study`, o apri un terminale
> nuovo.

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
