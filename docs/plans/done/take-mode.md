# Modalità take: non sovrascrivere l'audio a ogni rigenerazione

Piano concordato con l'utente il 2026-09-08.

## Il problema

Il ciclo di lavoro è `study.yml → audio → ascolto → modifica study.yml →
rigenera`. La rigenerazione **sovrascrive** l'audio precedente: non si può
confrontare a orecchio la versione di prima con quella di adesso, e non resta
traccia di cosa era stato provato.

## La forma della soluzione

Un albero completo e autonomo per take, sotto `takes/`:

```
takes/001-41-duration-pitch/
├── 2026-09-08_1432/
│   ├── yaml/ audio/ sv/ cache/ score/    ← identico a generated/<study>/
│   └── study.yml                         ← lo stato che ha prodotto quell'audio
├── 2026-09-08_1710/
└── latest -> 2026-09-08_1710
```

Il costo apparente (4.8 GB a take su `001-41-duration-fill-factor`, più un full
re-render) si azzera con gli **hardlink**: una take nuova nasce come `cp -al`
di `audio/` della precedente — istantanea, zero disco — e il render, che è incrementale per
mtime, salta le varianti immutate lasciandole hardlink condivisi e riscrive solo
quelle toccate dalla modifica. `du` riporta 4.8 GB per take, ma il disco cresce
solo di ciò che è cambiato davvero. **[eseguito]** `cp -al` funziona su APFS.

Hardlink **solo su `audio/`** — è lì che stanno i gigabyte, ed è l'unica cosa
che scrive l'engine. Tutto il resto (`yaml/`, `cache/`, `sv/`, lo snapshot
`study.yml`) è testo e viene copiato davvero: quei file li riscrivono
scritture che troncano l'inode in place, e condividerli corromperebbe la take
precedente. Emerso durante l'implementazione, non era nel piano iniziale.

`takes/` sta alla radice, **fuori da `generated/`**: `make clean` fa `rm -rf
generated` e cancellerebbe l'archivio.

## L'interfaccia

Un interruttore di sessione, non un cambio permanente. Senza `TAKE` tutto si
comporta come oggi, in `generated/<study>/`.

```zsh
home
export TAKE=1                    # una volta per sessione
study 001-41-duration-pitch      # → takes/001-41-duration-pitch/2026-09-08_1432/
# ascolto, modifica di study.yml
study 001-41-duration-pitch      # → takes/001-41-duration-pitch/2026-09-08_1710/
                                 #   la take delle 14:32 resta intatta
```

Valori di `TAKE`: `1`/`true`/`yes` → la take corrente (`latest`); una label
esplicita (`TAKE=2026-09-08_1432`) → quella take, per tornarci e rigenerare lì
dentro.

**Chi apre una take nuova.** Lo fa `study` da sé, ma **solo se `study.yml` è
cambiato** rispetto allo snapshot della take corrente. Rilanciando senza aver
toccato nulla si resta dentro la stessa take: niente proliferazione di cartelle
gemelle. È il gesto dell'utente («ho cambiato un parametro, riascolto») a
segnare il confine fra una take e l'altra.

Il timestamp non può essere calcolato al volo dentro i comandi: `make sweep` e
`make render` sono processi distinti e darebbero due cartelle diverse. La take
si apre con un comando esplicito (`make take`), tutto il resto risolve `latest`.

### Storico

```zsh
make takes STUDY=001-41-duration-pitch
#  2026-09-08_1432   1.2G   (prima take)
#  2026-09-08_1710   340M   pitch.ratio.values: [1.0, 2.0] → [1.0, 1.5, 2.0]
#  2026-09-08_1955   340M   grain.duration.band: [1, 10] → [1, 20]   ← latest

make takes-clean STUDY=... KEEP=3
```

La colonna di destra è il `diff` fra gli snapshot di `study.yml` di take
consecutive: è lì che si legge cosa è cambiato, non nel nome del file.

Lo snapshot viene riscritto **a ogni render**, non alla creazione della take:
così è sempre lo stato che ha davvero prodotto quell'audio, qualunque sia
l'ordine in cui si modifica e si rigenera.

## Cosa si tocca

| File | Modifica |
|---|---|
| `src/granstudies/__main__.py:38` | `gen_dir()` legge `TAKE` e punta a `takes/<study>/<label>/`. È l'unico choke point: `yaml/`, `audio/`, `sv/`, `cache/`, `score/` seguono da soli. Più l'avviso in log quando la modalità è attiva e lo snapshot di `study.yml` in `cmd_render`. |
| `src/granstudies/render.py:437` | Guardia: prima di rirenderizzare, se il file target ha `st_nlink > 1` viene unlinkato. Senza, l'engine tronca l'inode condiviso e **corrompe la take precedente**. Vale per il mix e per gli stem. |
| `make/takes.mk` (nuovo) | `take`, `takes`, `takes-clean`, `where`. |
| `.zsh_completions/_study` | Risolve la root da `make where STUDY=...` invece del `generated/<s>` fisso, e apre una take nuova quando `study.yml` è cambiato. |
| `.gitignore` | `/takes/` |
| `tests/test_render.py` | `gen_dir` con `TAKE` punta alla take; un render dentro una take non altera il file hardlinkato della precedente. |

`make where` stampa la cartella di output corrente ed è l'unica fonte di verità
condivisa fra shell e Python: la logica di risoluzione di `TAKE` non viene
duplicata in zsh.

L'engine non si tocca: la sua cache per-stream lascia in pace i file `clean`
(`stream_cache_manager.py:210`), quindi gli hardlink degli stem invariati
sopravvivono; quelli `dirty` passano dalla guardia di unlink.

## Scartato

- **Archiviare solo i file sovrascritti** invece dell'albero completo: costa meno
  disco ma una take non è più consultabile da sola, e la semantica si inverte
  (l'etichetta scritta prima del render descriverebbe il materiale *vecchio*).
- **Il parametro cambiato nel nome del file audio**: fragile con più assi, e il
  `diff` degli snapshot lo dice meglio.
- **Diff semantico dello YAML**: `diff` basta.
- **Take per `make brano`**: fuori dal dominio `studies/`, si aggiunge dopo se
  serve.
