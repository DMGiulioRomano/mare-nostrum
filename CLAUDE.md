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
| `001-41-duration-pitch` | grain.duration x pitch.ratio su `001-41_5-5_5_norm.flac`, il sample più ricorrente del brano; base presa da `stream2` di `mare-nostrum.yml` | `001-41-duration-pitch` |
| `001-41-duration-fill-factor` | grain.duration x fill_factor sullo stesso sample; pitch.ratio fissato a 1.0 | `001-41-duration-fill-factor` |
| `ascolto` | diario di ascolto dello studio — non è uno `STUDY` | — |

Le cartelle-scala (`1-10ms`, `1-50smp`, `10-50ms`, `50-300ms`, `300-1000ms`,
`stack*`) e i brani (`brano01`, `brano01_v2`) sono stati rimossi: il lavoro è
ora concentrato su `001-41-duration-pitch` e `001-41-duration-fill-factor`.
Restano citati nei log di `studies/ascolto/` come riferimento storico.

**Naming.** Il nome della cartella è il **range di grain.duration** e basta
(`1-10ms`, `1-50smp`): il prefisso `grain_` era ridondante — è sempre
grain.duration. Le varianti di **stack** (più stream ascoltati insieme)
prendono il prefisso `stack_` seguito dallo stesso range: `stack_1-50smp`.
La cartella `stack` senza suffisso resta quella storica delle curve non
cartesiane, non legata a un range.

## Assi esterni (`for_each:`)

Il blocco `for_each:` nello `study.yml` dichiara assi le cui combinazioni sono
patch sul documento: ognuna produce un render intero in
`generated/<scala>/<label>/`, con dentro anche lo snapshot dello `study.yml`
patchato. Serve quando il confronto sta nel **riascolto** e non nella
giustapposizione — `distribution` a 0 / 0.5 / 1 sullo stesso sweep, cinque
`stack.seed` diversi — o quando la chiave definisce il file stesso.
`COMBO=<label>` restringe generazione e apertura a una sola combinazione.
La modalità take non esiste più: vedi `docs/plans/done/for-each.md`.

## Il laboratorio (`make serve`)

`make serve STUDY=<scala>` non e' piu' `http.server`: e' `granstudies serve`,
che serve la pagina e accetta `POST /render`. La pagina ha due schede.

- **griglia** — quello che c'era: si sceglie fra audio gia' renderizzati.
- **laboratorio** — si compone UN solo stream e lo si sente subito. Ogni
  `+ breakpoint` salva uno snapshot di tutti i parametri a un tempo; i punti
  si trascinano sulla linea, e cliccarne uno riporta i select ai suoi valori.
  Il documento esce in `generated/<study>/live/<nome>.yml` e viene reso
  accanto in `.aif`. Un parametro diventa una lista `[[t, v], ...]` **solo
  dove cambia davvero**; se non si muove mai resta scalare.

### Il file di progetto

Non c'e' un formato di sessione a parte: **il progetto e' lo YAML stesso**.
E' un documento engine puro — si riapre nel laboratorio, si incolla nel brano,
si apre in PGE-ui — e sta dove vuoi tu sul disco, non per forza nello studio.

La barra file e' quella di sempre: **nuovo · apri… · salva · salva con nome…**,
col nome del file e un `•  modificato` quando ci sono modifiche non salvate.
`nuovo` e `apri` chiedono conferma se c'e' del lavoro non salvato.

I pannelli Apri/Salva sono **quelli nativi di macOS**: li apre il server con
`osascript` (`POST /pick`), perche' la pagina da sola non sa dove sta un file
sul disco — Safari non ha le File System Access API, e un `<input type=file>`
darebbe il contenuto ma non il percorso su cui risalvare. Solo i percorsi
usciti da un pannello di quella sessione si possono leggere e scrivere: il
dialogo **e'** l'autorizzazione dell'utente. L'audio nasce accanto allo YAML,
stesso nome: due file che si spostano insieme.

I breakpoint non si salvano a parte perche' **non sono un'informazione in
piu'**: sono i tempi che compaiono negli inviluppi. Riaprendo si prende
l'unione di quei tempi, e ogni parametro vale li' quanto vale il suo
inviluppo — **interpolato**, non il punto a sinistra, altrimenti risalvando
una rampa ripartirebbe piu' tardi e il file suonerebbe diverso da quello
aperto. Round-trip verificato. Un preset che non cambiava nulla rispetto al
precedente non torna: non cambiava il suono.

Il lavoro non salvato sopravvive a un refresh (localStorage, per studio): e'
una rete di sicurezza, non un salvataggio. La verita' e' il file.

Divisione dei ruoli con PGE-ui: la GUI e' la timeline, dove gli stream si
sentono insieme; il laboratorio e' il banco del singolo stream. I valori fra
cui si sceglie sono le tacche gia' dichiarate nello `study.yml` (assi interni
e `for_each: base.*`).

**Interpolazione.** Tre livelli, dal piu' largo al piu' stretto:

1. `interpolazione (tutti)` — scrive su **tutti i breakpoint**, subito: e' la
   decisione che azzera le eccezioni fatte finora;
2. `interpolazione (questo bp)` — muove i menu del breakpoint corrente (si
   conferma con `salva modifica`, come i valori);
3. il menu a destra di **ogni parametro**, per l'eccezione singola.

I tipi sono `linear` | `cubic` | `step`, i tre che l'engine conosce. La
scelta e' **per breakpoint**: il tipo sta sul punto e governa il
segmento che PARTE da li', quindi l'ultimo punto non ne ha uno. `linear` e'
il default e non viene scritto nello YAML; gli altri diventano il terzo
elemento del punto, `[[0, 0.001, cubic], [1, 0.016]]`.

**I breakpoint sul suono.** Dopo un render del laboratorio i punti compaiono
anche sopra sonogramma e forma d'onda, in giallo e numerati (il cursore di
riproduzione resta rosso), e si muovono mentre trascini. Spariscono appena
suona un file della griglia: li' indicherebbero punti a caso.

**`grain.envelope` si automatizza come gli altri**, ma per un'altra strada:
l'engine non interpola fra due finestre, le **sceglie grano per grano**. Una
lista di breakpoint li' sopra la rifiuta ("Window non trovata"); quello che
conosce e' `{states, curve}` (`MultiStateWindowStrategy`), dove `states` mappa
un valore in [0,1] su un nome di finestra e `curve` e' il cammino nel tempo
dentro quello spazio.

La galleria delle finestre e' percio' scesa fra i parametri automatizzabili, col
suo menu di interpolazione come tutti gli altri, e li' i tre tipi vogliono dire
una cosa sola ma udibile:

- `step` — **cambio netto**: fino a quel tempo tutti i grani hanno la finestra
  vecchia, da li' in poi tutti la nuova;
- `linear` / `cubic` — **morphing**: nella transizione i grani si mescolano, la
  proporzione segue la curva (a meta' strada e' 50/50).

Gli stati sono le finestre nell'ordine in cui compaiono, non l'insieme: una
finestra che torna (hanning -> bartlett -> hanning) ne apre uno nuovo, perche'
l'engine pretende valori di stato crescenti. Se la finestra non cambia mai
resta la stringa scalare di prima. Il round-trip e' verificato
(`tests/test_graph_js.py`).

Gli altri categoriali restano fissi per lo stream. Tutti i parametri numerici
reggono gli inviluppi — verificati uno per uno.

**Il sample** e' un fisso come gli altri, ma le sue tacche non stanno nello
`study.yml`: sono i file audio della cartella `samples_dir` dello studio, letti
da `graph` (`campioni()`) e messi in un menu. I fissi partono dal valore di
`base:`, non dalla prima tacca della lista.

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
