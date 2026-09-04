# CLAUDE.md — granulation-studies

**Lingua:** rispondi sempre in italiano.

## Stato reale del progetto (leggi prima di toccare qualunque cosa)

L'utente ha curato a mano **solo**: il submodule `engine/`, il proprio
`study.yml`, lo `sweep` e l'`sv export`. È fermo a livello **render**: il suo
ciclo di lavoro attuale è `study.yml → audio → ascolto → modifica study.yml →
rigenera`. Niente oltre.

Tutto il resto — `states.yml`, `composition.yml`, `methodology.md`, e i moduli
`states.py` / `kinship.py` / `walk.py` / `compose.py` / `descriptors.py` /
`curation.py` / `bounds.py` — è stato **generato da un comando Claude e NON è
ancora stato studiato, validato né usato** dall'utente. Trattalo come
scaffolding non vagliato, non come design consolidato: lo schema di `states.yml`
e la semantica della kinship/walk vanno discussi e decisi con l'utente, non dati
per buoni. Conferma di questo: in `make/studies.mk` il target `all-study` è
`sweep render #describe matrix compose render-final` — le fasi describe/matrix/
compose/render-final sono **commentate**, quindi fuori dalla pipeline viva.

Non proporre di "continuare" su quei moduli come se fossero scelte dell'utente.

## Struttura di `studies/`

Il repository **è** lo studio (study01). In futuro diventerà un template da
clonare e rendere agnostico per un nuovo parametro. Le cartelle sotto `studies/`
sono le **scale/varianti** dello stesso studio, più i brani; il diario di
ascolto è unico per tutto lo studio, in `studies/ascolto/`. `STUDY` è il nome
della cartella-scala.

| Cartella | Cos'è | `STUDY=` |
|----------|-------|----------|
| `1-10ms` | scala di riferimento, curata a mano (density + grain.duration 1-10 ms) | `1-10ms` |
| `1-50smp` | grani corti, grain.duration in `samples` (1-50 campioni) | `1-50smp` |
| `10-50ms` | grani corti, grain.duration 10-50 ms | `10-50ms` |
| `50-300ms` | grani medio-lunghi, grain.duration 50-300 ms (step 5 ms) | `50-300ms` |
| `300-1000ms` | grani lunghi, grain.duration 300-1000 ms (step 25 ms) | `300-1000ms` |
| `stack` | stream non-cartesiani (ascolto verticale) | `stack` |
| `stack_1-50smp` | stack: 7 punti di lettura insieme, grain.duration 1-50 campioni; `versions` su density e grana | `stack_1-50smp` |
| `stack_1-10ms` | come `stack_1-50smp`, scala 1-10 ms (`duration_unit: milliseconds`) | `stack_1-10ms` |
| `stack_10-50ms` | come `stack_1-50smp`, scala 10-50 ms (ms) | `stack_10-50ms` |
| `stack_50-300ms` | come `stack_1-50smp`, scala 50-300 ms (ms) | `stack_50-300ms` |
| `stack_100-300ms` | come `stack_1-50smp` ma grana lunga: grain.duration 100-300 ms (secondi, niente `duration_unit`) | `stack_100-300ms` |
| `stack_300-1000ms` | come `stack_1-50smp`, scala 300-1000 ms (ms) | `stack_300-1000ms` |
| `brano01` | brano musicale (ex `study_stack_test_5`) | `brano01` |
| `brano01_v2` | versione a 10 min di brano01 (ex `study_stack_test_5_10min`) | `brano01_v2` |
| `ascolto` | diario di ascolto dello studio — non è uno `STUDY` | — |

**Naming.** Il nome della cartella è il **range di grain.duration** e basta
(`1-10ms`, `1-50smp`): il prefisso `grain_` era ridondante — è sempre
grain.duration. Le varianti di **stack** (più stream ascoltati insieme)
prendono il prefisso `stack_` seguito dallo stesso range: `stack_1-50smp`.
La cartella `stack` senza suffisso resta quella storica delle curve non
cartesiane, non legata a un range.

## Diario di ascolto

Il diario è unico per lo studio e vive in `studies/ascolto/`:

```
studies/ascolto/
├── YYYY-MM-DD.md   ← log della giornata, diario di bordo in prosa
├── index.md        ← sintesi cronologica, aggiornata su richiesta
└── riepilogo.md    ← tabella consolidata regioni/transizioni, aggiornata su richiesta
```

Un solo file per giorno: `YYYY-MM-DD.md`. Se in una giornata ci sono più
sessioni di ascolto, non si creano file separati né suffissi — si aggiungono
come sezioni `## Sessione N — <tema> (scala: 1-10ms, sample: ...)` dentro lo
stesso file, in ordine cronologico. La **scala** (il nome della cartella, es. `1-10ms`/`1-50smp`/`stack_1-50smp`)
e il `sample` stanno nell'heading di sessione, non nel frontmatter.

Il log è **prosa libera**. Nel descrivere un oggetto in ascolto, il filo
ricorrente è: **cosa** si ascolta → **range dove il percetto resta uguale**
(plateau) → **range dove cambia** (transizione) → **plateau successivo**. Così
scrivendo si mappano da sé regioni e transizioni.

### Creare il log di oggi

Quando l'utente dice "crea il log di oggi" o simile:

1. Recupera l'hash con `git rev-parse --short HEAD`
2. Crea `studies/ascolto/YYYY-MM-DD.md` con frontmatter minimo:

```yaml
---
data: YYYY-MM-DD
studio: study01
study_yml_commit: {hash}
---
```

3. Corpo vuoto — lo scrive l'utente in prosa, in sezioni `## Sessione N — <tema>
   (sample: ...)` se la giornata ha più sessioni.

### Rispondere a "dove eravamo"

Quando l'utente chiede "dove eravamo" o simile: leggi `promemoria.md`
(sezione "Da fare"), gli ultimi 2-3 log in `studies/ascolto/` e l'ultimo
commit. Riporta cosa è stato fatto di recente, cosa è rimasto aperto
(sessioni di log vuote o a una riga) e le voci non fatte del promemoria.

### Aggiornare index e riepilogo

Quando l'utente lo chiede, leggi tutti i log `YYYY-MM-DD.md` e rigenera:
- `index.md` — cronologia + temi emergenti;
- `riepilogo.md` — tabella `sample | tipo | density | grain.dur | percetto`, dove
  `tipo` è `plateau` (range dove resta uguale) o `transizione` (bracket `a→b`
  sull'asse mosso).
