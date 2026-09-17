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

`make serve` chiude da solo il server di prima. Chiusa la pagina, il processo
resta: se la porta e' tenuta da un altro `granstudies serve` lo si termina
(SIGTERM, poi SIGKILL se non molla) e si riparte — e' il proprio lavoro di
prima, non quello di qualcun altro. Se la porta e' di un processo estraneo non
si tocca niente e si dice chi e' (`libera_porta` in `serve.py`, verificata in
`tests/test_serve.py`).

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
`base:`, non dalla prima tacca della lista. Il sample **si sente prima di
sceglierlo**: cambiare il menu (o premere `▶ ascolta`) lo manda nel pannello di
destra, che e' gia' il lettore completo — sonogramma, forma d'onda,
spectroscope, stereoscope, cursore, durata. Niente popup: sarebbe lo stesso
codice due volte; `↩ stream` riporta all'ultimo render dello stream — il file
c'e' ancora e i campioni sono in cache, quindi non si rende niente. Il server
serve `/samples/` dalla cartella dei sample del repo, che sta fuori da quella
servita.

**Il loop sul sample.** Quando la forma d'onda mostra un sample (`▶ ascolta`),
click e trascina disegna una regione: e' il loop del pointer, e gli estremi si
prendono per allargarlo o stringerlo; doppio click lo toglie. Il sample si
riascolta dentro il loop. Sul documento diventa `pointer.loop_unit: normalized`
+ `loop_start`/`loop_end` (frazioni del file), e `pointer.start` sparisce cosi'
il pointer parte da loop_start. Si parte sempre **senza loop** — il pointer
percorre il file intero: quello di `base:` e' una scelta dello sweep, non il
punto di partenza di un ascolto. Senza regione le chiavi di loop spariscono. Sul render dello stream non si disegna:
li' l'asse e' il tempo d'uscita, non la posizione nel sample.
Il loop suona con un `AudioBufferSourceNode` (loop nativo, preciso al
campione), non spostando `audio.currentTime`: quel seek e' asincrono e il
cursore andava fuori passo. Il campo `latenza (ms)` del trasporto ritarda il
cursore della latenza d'uscita, che Safari non dichiara: si tara a orecchio.

**Da dove parte il laboratorio.** Non da `base:` — quello e' lo stream a riposo
dello *sweep*, tarato per i render della griglia — ma da una tabella `DEFAULTS`
nella pagina: grana media (`grain.duration` 0.064), niente dispersione
(`*_range` e `distribution` a 0), niente trasposizione (`pitch.ratio` 1),
`pointer.speed_ratio` 1, `volume` 0, `grain.envelope` gaussian. Un parametro
fuori da quella tabella parte da `base:`, e se manca anche li' dalla sua prima
tacca (`iniziale()`, verificata in `tests/test_graph_js.py`).

**Undo/redo.** `cmd+Z` annulla, `cmd+shift+Z` rifa (`ctrl` fuori da macOS).
Lo stato che si annulla e' tutto il lavoro: i breakpoint, il loop, il punto
selezionato e **i valori a schermo non ancora salvati sul breakpoint** — sono
lavoro come gli altri. Si registra in `labInfo`, dove ogni modifica va a
finire, tranne durante un gesto (`GESTO`): un trascinamento e' un passo solo,
non cento. Dentro un campo di testo `cmd+Z` resta l'undo del testo. Aprire un
file o fare `nuovo` azzera la storia.

**Il tempo di un breakpoint si scrive.** La riga `tempo (0-1)` in cima ai
parametri mostra la x normalizzata del punto selezionato e la accetta digitata:
vale subito, come il trascinamento, e riordina i punti (non passa da `salva
modifica`, che riguarda i valori).

**Dove si scrive, la tastiera è di chi scrive.** Con il focus in un campo
(o in un menu) gli scorciatoi della pagina si fanno da parte: frecce per
muovere il cursore, shift+frecce per selezionare, barra spaziatrice per lo
spazio, backspace per una cifra, `cmd+Z` per l'undo del testo. Fuori dai campi
tornano a valere trasporto (spazio), navigazione della griglia (frecce), undo
e `delete`. La guardia è una sola, `inCampo()`, chiamata da tutti i gestori:
mancava a quello della griglia, che si prendeva frecce e spazio su tutta la
pagina.

**Selezione multipla.** Trascinando sul **vuoto** della linea dei breakpoint
si disegna una banda, come su una scrivania, e i punti che ci cadono dentro
(estremi compresi) restano selezionati — anello attorno, e il conto nella riga
di stato. Un click a vuoto la scioglie. Sul punto no: lì il trascinamento è
già il suo, lo sposta nel tempo.

`delete` (o `backspace`) toglie: i selezionati se c'è una banda, altrimenti il
punto corrente — cioè quello che `togli` ha sempre fatto. Dentro un campo di
testo resta la cancellazione del testo. La selezione non entra nell'undo
(selezionare non modifica il documento) e si azzera su undo, `nuovo` e `apri`,
dove i breakpoint che tornano sono altri oggetti. Verificata in
`tests/test_graph_js.py`.

**Generare breakpoint a mucchio.** Il blocco `genera breakpoint` (chiuso
finché non serve, sotto i bottoni) prende un tratto dell'asse — `da`, `a`,
`quanti` — e ci mette n punti disposti in uno di tre modi.

- `regolare` + **`ratio`**: la ragione con cui ogni passo sta al precedente.
  A **1** i passi sono uguali (equidistanti); **>1** crescono e i punti si
  addensano in principio; **<1** calano e si addensano alla fine. La
  geometrica non è un modo a parte, è il valore `ratio = (b/a)^(1/(n-1))` —
  quello per cui resta costante il rapporto fra un *valore* e il successivo.
  Gli estremi ci cadono sempre sopra per costruzione, e lo zero non è più un
  caso vietato.
- `random (uniforme)` — pescati, tutti i valori ugualmente probabili.
- `random (gaussiana)` — pescati, centro dell'intervallo come media e tre
  sigma sugli estremi, code tagliate sulla maschera.

Il campo `ratio` si spegne sui due modi che pescano: lì non vuol dire niente.
I tempi si ordinano prima che i valori vengano assegnati, così una rampa segue
il tempo anche con tempi casuali.

Con `+ parametro` si aggiunge una **regola**: parametro, `min`, `max` (la
maschera, prefillata con le tacche dello `study.yml`), lo stesso menu dei
quattro modi, e un `passo` facoltativo che quantizza a multipli — il passo
comanda, quindi con un `max` che non è multiplo l'ultimo punto resta sotto.
Un parametro senza regola prende il valore che ha a schermo, come `+ breakpoint`.
I punti generati si aggiungono a quelli che ci sono (non li sostituiscono) e
sono **un passo solo di undo**. La matematica è tutta in `riempi()`, verificata
in `tests/test_graph_js.py`.

**I numerici si scelgono E si scrivono.** Ogni parametro numerico
(`grain.duration`, `grain.duration_range`, `fill_factor`, `pitch.ratio`,
`pitch.range`, `pointer.speed_ratio`, `pointer.offset_range`, `distribution`,
`volume`) ha due controlli sulla stessa riga: il **campo** che tiene il valore
e, accanto, il **menu `▾` delle tacche** dello `study.yml`. Sceglierne una la
scrive nel campo e il menu torna al suo `▾`: il valore buono e' uno solo,
quello scritto. Nel campo si puo' digitare anche un valore che fra le tacche
non c'e'; la virgola vale il punto, e un campo vuoto o illeggibile tiene il
valore del breakpoint invece di scrivere NaN (`tests/test_graph_js.py`).
I limiti di `bounds_for` non bloccano il campo, restano come tooltip.
**Il volume** resta l'unico senza menu (`free: true`): non ha tacche, e' un
aggiustamento continuo. I categoriali (sample, finestre) restano menu chiusi.

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
