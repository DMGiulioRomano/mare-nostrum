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
che serve la pagina e accetta `POST /render`. La pagina **è** il laboratorio:
si compone UN solo stream e lo si sente subito. Ogni `+ breakpoint` salva uno
snapshot di tutti i parametri a un tempo; i punti si trascinano sulla linea, e
cliccarne uno riporta i select ai suoi valori. Il documento esce in
`generated/<study>/live/<nome>.yml` e viene reso accanto in `.aif`. Un
parametro diventa una lista `[[t, v], ...]` **solo dove cambia davvero**; se
non si muove mai resta scalare.

**La griglia non c'è più.** C'era una seconda scheda che leggeva i nomi dei
file audio sotto `audio/sweep/discrete/` e ne faceva una tabella cliccabile:
è stata tolta, con tutto quello che la reggeva (`collect_combos`, `_grid`,
`_axis_orders`). `sweep render` continua a produrre quell'audio, ma non ha
più un browser: si ascolta dal disco. Git la ricorda, se servisse indietro.

### Il file di progetto

Non c'e' un formato di sessione a parte: **il progetto e' lo YAML stesso**.
E' un documento engine puro — si riapre nel laboratorio, si incolla nel brano,
si apre in PGE-ui — e sta dove vuoi tu sul disco, non per forza nello studio.

La barra file e' quella di sempre: **nuovo · apri… · salva · salva con nome…**,
col nome del file e un `•  modificato` quando ci sono modifiche non salvate.
`nuovo` e `apri` chiedono conferma se c'e' del lavoro non salvato.

Accanto ad `apri…` c'e' **`apri recente…`**, gli ultimi tre file passati da un
pannello. La lista sta sul **server** (`.recenti.json` nella cartella servita),
non nella pagina, perche' e' anche l'autorizzazione: un file gia' scelto una
volta in un pannello resta apribile al prossimo avvio, mentre un path inventato
dalla pagina no. Chi sparisce dal disco esce dalla lista.

**Il laboratorio si apre su un foglio bianco**, chiamato `nuovo stream`, con i
`DEFAULTS`. La bozza in localStorage porta l'id della sessione del server
(`POST /stato`) e torna solo se coincide: un **refresh** riprende il lavoro non
salvato, un `make serve` nuovo no — riaprendo il laboratorio si vuole un banco
pulito, non l'ultima cosa rimasta a meta'.

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

**Aperto e risalvato, e' lo stesso stream** (#3). Il laboratorio non
ricostruisce piu' lo stream dal `base:` dello studio: parte da quello del
documento aperto (`APERTO`) e ci scrive sopra **solo cio' che conosce e che e'
stato toccato**. "Toccato" e' una differenza fra due scritture dello stesso
stream: `labView()` e' lo stream come lo scriverebbe il laboratorio per intero,
`VISTA0` e' quella scrittura presa appena aperto il file, e `labDoc()` mette
sullo stream aperto le sole chiavi in cui la `labView()` di adesso differisce
da `VISTA0` (`toccati`). Il confronto scende nei blocchi (`grain`, `pointer`,
`voices.pitch`...) ma non nei valori: un inviluppo cambia o resta tutto
intero. Cosi' restano com'erano le chiavi che il laboratorio non ha
(`grain.read_direction`, che in `mare-nostrum.yml` hanno 8 stream su 10),
`onset`, e i parametri che il documento lascia al default dell'engine anche se
il laboratorio ha un campo per loro. Lo `stream_id` no: dalla #5 e' il nome del
file, e l'identita' non passa dal "toccato" (sotto). Il loop e' un gruppo
(`GRUPPO_LOOP`): se una delle sue chiavi cambia, si scrivono tutte come
`scriviLoop` le vuole. Anche la **testa** del documento si conserva (`TESTA`):
`seed`, `bpm`, la `duration` del tutto, le chiavi di PGE-ui come `ui_tracks`
restano com'erano, e del laboratorio c'e' solo la durata, che si scrive in
testa solo se `durata (s)` e' stata toccata. Un parametro che il documento non
dichiara si mostra al valore che l'engine usa al suo posto (`assente`: il
default dello schema dei parametri, che `graph` passa alla pagina con
`engine_bridge.parameter_path_defaults`), non a quello rimasto a schermo dal
documento aperto prima ne' ai `DEFAULTS` del foglio bianco — che per
`grain.duration` e `grain.envelope` sono 0.064 e gaussian contro 0.05 e
hanning: lo schermo direbbe un suono che l'ascolto non ha, e scegliere a mano
quel valore non scriverebbe niente. Dove l'engine non ha un default si ricade
su `iniziale`. Nel file non entra finche' non lo si tocca. `APERTO`, `VISTA0`
e `TESTA` stanno nella storia dell'undo e
nella bozza, accanto ai breakpoint. Il **foglio bianco** (`nuovo`, o la
pagina appena aperta) non ha uno stream aperto: nasce da `DEFAULTS` e `base:`
e il laboratorio lo scrive per intero, come prima.

L'**anteprima** sotto i breakpoint legge il documento (`labDoc`), non i
breakpoint: un inviluppo non toccato vi compare com'e' scritto.

**Si salva col piazzamento, si ascolta senza.** `onset`, `mute` e `solo` di uno
stream aperto dal brano restano nel file — sono dello stream. Ma il render del
laboratorio e' l'ascolto dello stream da solo: `labPost` manda anche un
documento `ascolto` con `onset: 0` e senza `mute`/`solo` (`perAscolto`), e il
server rende quello (scritto in `logs/<nome>.ascolto.yml`) accanto allo YAML
salvato. Senza, uno stream con onset 43 s partirebbe dopo 43 s di silenzio e
uno con `mute` non suonerebbe affatto.

**L'identita' dello stream: il nome del file e il seed** (#5). L'RNG
dell'engine e' `(seed, rng_group o stream_id, componente)`
(`shared/seeding.py`), quindi lo stesso stream suona uguale in due posti solo
con lo stesso seed e lo stesso id. Nessuno dei due e' una manopola del
laboratorio: non si scelgono, si leggono.

- **`stream_id` = il nome del file**, senza estensione (`idDa`), che e' anche
  il modo in cui il master nomina uno stream importato (il piano, regola 3).
  Un foglio mai salvato non ha un nome di file: vale il campo `nome`, che e'
  poi quello che il pannello di salvataggio propone. **`salva con nome` cambia
  il nome, quindi l'id, quindi la realizzazione**: e' accettato, e la riga di
  stato lo dice (`notaIdentita`) — a orecchio non si capirebbe da dove viene.
- **`seed`**: si conserva quello del documento aperto; se il documento non ne
  ha, vale il `seed:` dello `study.yml` servito, che `lab_data` passa alla
  pagina. Se nemmeno lo studio ne ha uno il laboratorio **non lo inventa** —
  un numero scelto qui non e' il seed di nessuno — e lo dice nella riga di
  stato e nel chip. `seed: 0` e' un seed come gli altri (l'engine deriva su
  sha256), quindi il controllo e' su null/undefined.
- **Il seed si mostra e non si cambia**, in un testo accanto al nome del file
  e non in un campo: cambiarlo qui romperebbe l'identita' col brano, dove il
  master usa il proprio seed e ignora quello del file importato (regola 3).

Da qui viene che **due render dello stesso documento danno lo stesso audio**, e
che le curve realizzate e il piano dei grani sono la realizzazione che ha
suonato anche con una strategia stocastica (vedi "Gli inviluppi realizzati").

Il corollario e' su `FILE`, il file su cui si lavora: e' quello scelto in un
pannello, non quello che il server scrive. Un `rendi e ascolta` su un foglio
mai salvato scrive in `live/` col nome ripulito (`_SAFE` in `serve.py`), e
adottarlo faceva due cose sbagliate — `salva` provava a riscrivere un percorso
che nessun pannello aveva autorizzato, e l'id cambiava fra il primo render e il
secondo, cioe' lo stesso documento dava due audio. Dopo un salvataggio invece
il campo `nome` segue il file, come fa `carica` aprendo.

**Due editor, un file** (#6, regola 7 del piano). Lo stesso
`streams/risacca.yml` puo' stare aperto nel laboratorio e in PGE-ui. Il
laboratorio ricorda com'era il file quando l'ha letto (`FIRMA`, l'hash che
torna da `/open`) e la manda a ogni scrittura; il server confronta e, se su
disco non e' piu' quella, non scrive e risponde `cambiato`.

- **La firma e' l'hash del contenuto, non l'mtime** (`serve.py`: `firma`,
  `firma_di`, `cambiato_su_disco`). Un mtime dice che qualcuno ha scritto, non
  che il file sia diverso, e le due risposte portano a cose opposte: rileggere,
  oppure lasciar passare la riscrittura di un file identico. Si firmano i
  **byte**, non il documento caricato — la domanda e' "il file su disco e'
  quello che ho letto", e due editor scrivono lo stesso documento con
  formattazioni diverse. L'algoritmo sta nel prefisso (`sha256:`) perche' la
  stessa firma la calcola PGE-ui (DMGiulioRomano/PGE-ui#185): il giorno che una
  delle due convenzioni cambia si deve vedere che non e' il file a essere
  cambiato.
- **Senza modifiche proprie non c'e' niente da decidere**: si rilegge e si
  riprova, e il render prosegue sulla versione su disco — quella che l'altro
  editor ha appena scritto e' quella che si vuole sentire. La riga di stato lo
  dice (`RILETTO`), perche' il documento a schermo non e' piu' quello di prima
  e sarebbe l'unica modifica che il laboratorio fa da solo senza che si veda.
  Si riprova **una volta sola**: se il file cambia ancora fra la rilettura e
  la scrittura lo si dice, invece di rincorrerlo.
- **Con modifiche proprie decide l'utente**, e sono due bottoni accanto al nome
  del file — non un `confirm`, che ha due risposte, mentre qui le scelte sono
  tre: `ricarica`, `sovrascrivi`, e non scrivere niente, che non deve costare
  un click ne' finire sotto il tasto Annulla accanto a una che perde lavoro.
  La scrittura resta ferma finche' non si risponde, e ogni scrittura nuova
  sostituisce la domanda in attesa (la via d'uscita piu' ovvia e' salvare le
  proprie da un'altra parte). `ricarica` e' un `apri` dello stesso file:
  `carica` azzera la storia, o un undo riporterebbe indietro una versione che
  su disco non c'e' piu' e la scrittura dopo la riscriverebbe.
- **La firma e' di `FILE` e vale solo per lui.** Un `salva con nome` scrive un
  file che il laboratorio non ha letto — li' non si manda niente, e della
  sovrascrittura ha chiesto il pannello nativo. Due casi non sono un file
  cambiato: nessuna firma letta, e un file **che non c'e' piu'** (non ci sta
  il lavoro di nessuno, e rifiutare lascerebbe la domanda senza via d'uscita —
  "ricarica" non puo' rileggere un file cancellato). La guardia non vale per
  il `live/<nome>.yml` di un foglio mai salvato: e' la cartella di lavoro del
  server, che nessuno rilegge.
- **La firma di cio' che si e' appena scritto torna dalla risposta** e prende
  il posto di quella letta: senza, il salvataggio dopo manderebbe la firma di
  prima e si rifiuterebbe da se'. Sta anche nella bozza, o un refresh
  disarmerebbe la guardia proprio sul file su cui si stava lavorando. Nella
  storia dell'undo no, come `FILE`: non e' lavoro, e' un fatto sul disco.

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

**Gli inviluppi `{type, points}`** (#4). L'interpolazione globale di un
inviluppo si scrive `{type: cubic, points: [...]}`: la scrive PGE-ui da solo,
appena l'interpolazione globale di una curva di soli breakpoint non e'
lineare, e nel brano la portano `grain.duration` (stream6, stream8),
`fill_factor` (stream4) e `voices.pitch.pitch_range` (stream10, `step`).
Il laboratorio li legge (`curva`): `type` e' il tipo di ogni segmento che non
ne dichiara uno sul punto, e il menu di interpolazione di ogni breakpoint lo
mostra. **I valori si leggono come li legge l'engine**, non in linea:
`valoreA` e' `Envelope.evaluate` rifatto passo per passo — un segmento solo
se nessun punto dichiara un tipo, uno per coppia altrimenti, e la cubica e'
la PCHIP di Fritsch-Carlson con le tangenti calcolate su **tutti** i punti
(`tangenti`, `hermite`). Conta perche' riaprendo ogni inviluppo prende un
punto anche dove il breakpoint e' di un altro parametro: li' il valore a
schermo e' quello che l'engine suona. Sul tempo di un punto vale il punto,
senza l'arrotondamento della formula (`0.009`, non `0.009000000000000001`).
La stessa lettura la usano `segui il render` e il lucchetto (`bpFra`), sulla
curva dei breakpoint.

Non toccato, un `{type, points}` resta com'era (#3). **Toccato, resta un
`{type: T, points}` finche' i suoi segmenti sono tutti T** (`forma`); con i
tipi mescolati diventa la lista del laboratorio, col tipo sui punti da cui
parte un segmento non lineare. Per l'engine le due forme sono lo stesso
inviluppo, bit per bit, integrale compreso: le tangenti della cubica le
calcola sempre su tutti i punti, che il tipo sia globale o scritto su ogni
punto. Non e' un'ipotesi: lo prova
`test_type_points_e_tipo_su_ogni_punto_sono_lo_stesso_inviluppo` sui quattro
inviluppi del brano. La terza forma — il dict col tipo globale e le eccezioni
sul punto — l'engine la legge uguale, ma il laboratorio non la scrive: PGE-ui
non la rilegge intatta (`wrapEnv`, appena un punto ha un tipo suo, scrive la
lista piatta e il `type` globale si perde, quindi la cubica degli altri
segmenti diventerebbe una retta alla prima modifica fatta li'). Le due forme
che il laboratorio scrive PGE-ui le riapre e le riscrive uguali. Il prezzo di un inviluppo toccato e' quello di sempre del
laboratorio: prende un punto a ogni breakpoint dove il suo valore cambia,
anche a quelli di altri parametri, e una cubica con un punto in piu' ha
tangenti diverse — fra due punti la curva puo' muoversi di poco, mentre su
ogni breakpoint l'engine vale quanto il laboratorio mostra.

Il criterio del passo 1 del piano (`docs/plans/stream-come-file.md`) e' un
test: ognuno dei 10 stream di `mare-nostrum.yml`, aperto e risalvato senza
toccare niente, da' all'engine lo stesso fingerprint
(`test_criterio_del_piano_ogni_stream_del_brano_risalvato_e_lo_stesso`). I test
del documento girano sulla pagina intera, non a frammenti: `tests/lab_dom.js`
e' un DOM finto in node (un `<select>` con un valore che non ha vale `""`,
come nel browser), e `graph.lab_completo` da' loro lo stesso corredo che
`make serve` da' alla pagina.

**I breakpoint sul suono.** Dopo un render del laboratorio i punti compaiono
anche sopra sonogramma e forma d'onda, in giallo e numerati (il cursore di
riproduzione resta rosso), e si muovono mentre trascini. Spariscono appena si
ascolta un sample: lì indicherebbero punti a caso.

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

**Start e loop del pointer.** Fra i fissi ci sono `pointer.start`,
`pointer.loop` (`off`/`on`) e `pointer.loop_unit` (`normalized`/`seconds`);
fra i parametri sui breakpoint `pointer.loop_start` e `pointer.loop_end`, che
compaiono solo col loop acceso. Cosa si automatizza lo dice l'engine
(`pointer_controller.py`, `POINTER_PARAMETER_SCHEMA`): loop_start/loop_end
reggono inviluppi (loop mobile), `start` e' scalare e un envelope lo rifiuta,
`loop_unit` e' la meta-chiave che legge tutti e tre. `pointer.loop` non e'
dell'engine: e' la presenza delle chiavi, e spento le toglie (`scriviLoop`).
`start` a 0 non si scrive: col loop il pointer parte cosi' da loop_start.
Si parte sempre **senza loop** — quello di `base:` e' una scelta dello
sweep, non il punto di partenza di un ascolto. Riaprendo (`leggiLoop`), un
documento senza `loop_unit` si legge in secondi come fa l'engine, e un
`loop_dur` scalare diventa `loop_end`.

**La regione sul sample e' quella coppia di campi.** Quando la forma d'onda
mostra un sample (`▶ ascolta`), click e trascina disegna il loop e lo scrive
in loop_start/loop_end (accendendo `pointer.loop`); gli estremi si prendono
per allargarlo o stringerlo; doppio click lo spegne. Scrivere i campi sposta
la regione. Un loop fermo si sposta su tutti i breakpoint, uno che si muove
gia' cambia solo sul punto corrente. In `seconds` la regione si vede solo
ascoltando il sample, perche' serve la sua durata. Sul render dello stream
non si disegna: li' l'asse e' il tempo d'uscita, non la posizione nel sample.
Il loop suona con un `AudioBufferSourceNode` (loop nativo, preciso al
campione), non spostando `audio.currentTime`: quel seek e' asincrono e il
cursore andava fuori passo. Il campo `latenza (ms)` del trasporto ritarda il
cursore della latenza d'uscita, che Safari non dichiara: si tara a orecchio.

**Da dove parte il laboratorio.** Non da `base:` — quello e' lo stream a riposo
dello *sweep*, tarato per i render dello sweep — ma da una tabella `DEFAULTS`
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

**I tempi sul documento seguono il suo `time_mode`.** Nella pagina i tempi
dei breakpoint sono frazioni dello stream, ma l'engine li legge cosi' solo con
`time_mode: normalized`; senza, sono secondi. Decide lo stream: quello
aperto (#3), o il `base:` dello studio sul foglio bianco. Con `normalized` i
tempi escono frazioni, altrimenti `labView` li scrive in secondi
(`scalaTempi`, `inSecondi`), e riaprendo `carica` legge da una copia dello
stream coi tempi in frazioni (`tempiFrazione`) — lo stream aperto (`APERTO`)
resta com'e' scritto, e un inviluppo non toccato esce nei suoi secondi di
prima. Cosi' gli inviluppi che lo stream ha gia' restano nella loro
convenzione: forzare `time_mode: normalized` sarebbe stato piu' semplice, ma
li avrebbe riletti in frazioni. Vale per tutto cio' che sta sui breakpoint:
numerici, voci, loop, la `curve` di `grain.envelope`, la progressione, e i
punti di un `{type, points}` (#4). Prima la pagina contava sul
`time_mode: normalized` del `base:`, che oggi tutti gli studi dichiarano: su
uno studio senza, una rampa di 30 s si schiacciava nel primo secondo, e il
render non diceva niente (#9). Riportato da
DMGiulioRomano/granulation-studies@93f201c, verificato in
`tests/test_graph_js.py` (foglio bianco) e in `tests/test_lab_documento.py`
(uno stream aperto in secondi, col suo `{type: cubic}`). Un `time_unit`
dentro un `{type, points}`, che per l'engine prevale sul `time_mode` dello
stream, non e' gestito: si conserva se non lo si tocca.

**Il tempo di un breakpoint si scrive.** La riga `tempo (0-1)` in cima ai
parametri mostra la x normalizzata del punto selezionato e la accetta digitata:
vale subito, come il trascinamento, e riordina i punti (non passa da `salva
modifica`, che riguarda i valori).

**Dove si scrive, la tastiera è di chi scrive.** Con il focus in un campo
(o in un menu) gli scorciatoi della pagina si fanno da parte: frecce per
muovere il cursore, shift+frecce per selezionare, barra spaziatrice per lo
spazio, backspace per una cifra, `cmd+Z` per l'undo del testo. Fuori dai campi
tornano a valere trasporto (spazio), undo e `delete`. La guardia è una sola,
`inCampo()`, chiamata da tutti i gestori.

**Il lucchetto della durata.** Le x dei breakpoint sono normalizzate, quindi
cambiare `durata (s)` cambia il significato di ognuna: lo stesso 0.5 è 15 s in
uno stream di 30 e 5 s in uno di 10. Il bottone sulla riga della durata sceglie
cosa deve succedere.

- **aperto** (default) — i punti restano dove sono e si stirano con lo stream.
  È quello che il laboratorio ha sempre fatto.
- **chiuso** — i punti tengono il loro tempo **in secondi** e si ridispongono:
  `t' = t * durVecchia / durNuova`. È il `freezeEnvOnResize` di PGE-ui
  (`rescaleStreamEnvelopes` in `src/lib/envelope-utils.js`), stessa formula.

Accorciando, i punti che finiscono oltre la nuova fine escono, ma lasciano il
punto in cui l'inviluppo **tagliava** il bordo, interpolato (`bpFra`) — se no
la coda resterebbe piatta sull'ultimo valore rimasto; è la stessa cura del
`truncateEnvArray` di PGE-ui. Il valore del punto di chiusura e' quello della
curva dei breakpoint letta come l'engine (`valoreA`): un `step` sul punto di
partenza tiene il suo valore, una `cubic` resta la cubica. Quanti ne sono
usciti lo dice la riga di stato.

La durata entra nella storia dell'undo: riportare indietro i breakpoint senza
di lei lascerebbe i tempi in secondi diversi da quelli ripristinati. Verificato
in `tests/test_graph_js.py`.

**Seguire il render.** Sotto il lucchetto c'e' `segui il render`: acceso,
mentre suona i parametri smettono di mostrare il breakpoint selezionato e
mostrano **dove sono adesso** — gli inviluppi letti al tempo del cursore, con
la stessa interpolazione dei breakpoint (`bpFra`, via `bpA`: la curva dei
breakpoint letta come l'engine, cubica compresa), l'estremo fuori
dagli estremi. E' una lettura: non tocca i breakpoint, non entra nell'undo, e
spegnendolo si torna al punto selezionato (`mostraBp`). Vale solo sul render
dello stream, non sull'ascolto di un sample. Verificato in
`tests/test_graph_js.py`.

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

Dopo la generazione il punto corrente è l'ultimo generato e **i valori a
schermo lo seguono** (`mostraBp`), come quando si clicca un punto: se restassero
quelli di prima, `cambiati()` li segnerebbe come "non salvati" su un breakpoint
che nessuno ha toccato. Vale anche dopo `togli`, che sposta il corrente su un
altro punto.

Il campo `ratio` si spegne sui due modi che pescano: lì non vuol dire niente.
I tempi si ordinano prima che i valori vengano assegnati, così una rampa segue
il tempo anche con tempi casuali.

Con `+ parametro` si aggiunge una **regola**: parametro, `min`, `max` (la
maschera, prefillata con le tacche dello `study.yml`), lo stesso menu dei
quattro modi, e un `passo` facoltativo che quantizza a multipli — il passo
comanda, quindi con un `max` che non è multiplo l'ultimo punto resta sotto.
Nelle regole c'e' un quarto modo, **`tacche dello study.yml`**: niente passo
da indovinare, i valori sono le tacche di quel parametro, una per breakpoint
nell'ordine della lista, a partire dalla prima che non sta sotto `min`.
Dove si arriva lo dice `quanti`, non un `max`: finite le tacche, i punti che
avanzano tengono l'ultima. Il `passo` li' e' un salto sull'indice della
lista (2 = una tacca si' e una no; vuoto = 1). `max` e `ratio` si spengono, e sui
parametri senza tacche (volume, pan) il modo non c'e'. Verificato in
`tests/test_graph_js.py` (`tacche()`).
Un parametro senza regola prende il valore che ha a schermo, come `+ breakpoint`.
I punti generati si aggiungono a quelli che ci sono (non li sostituiscono) e
sono **un passo solo di undo**. La matematica è tutta in `riempi()`, verificata
in `tests/test_graph_js.py`.

**I numerici si scelgono E si scrivono.** Ogni parametro numerico
(`grain.duration`, `grain.duration_range`, `fill_factor`, `pitch.ratio`,
`pitch.range`, `pointer.speed_ratio`, `pointer.offset_range`, `distribution`,
`volume`, `pan`, `pan_range`) ha due controlli sulla stessa riga: il **campo** che tiene il valore
e, accanto, il **menu `▾` delle tacche** dello `study.yml`. Sceglierne una la
scrive nel campo e il menu torna al suo `▾`: il valore buono e' uno solo,
quello scritto. Nel campo si puo' digitare anche un valore che fra le tacche
non c'e'; la virgola vale il punto, e un campo vuoto o illeggibile tiene il
valore del breakpoint invece di scrivere NaN (`tests/test_graph_js.py`).
I limiti di `bounds_for` non bloccano il campo, restano come tooltip.
**Volume, pan e pan_range** sono i tre senza menu (`free: true`): non hanno
tacche, sono aggiustamenti continui. I categoriali (sample, finestre) restano
menu chiusi.

## Le voci nel laboratorio

Il blocco `voices:` dell'engine sta sotto i parametri, un `<details>` chiuso
per asse: `voci` (num_voices, scatter) e poi pitch, onset_offset, pointer, pan.
Ogni asse ha il suo menu `strategy`, dove `off` non e' una strategia
dell'engine ma **l'assenza del blocco**, ed e' il valore di partenza. Sulla
linguetta compare la strategia accesa, cosi' si vede cosa e' in gioco senza
aprire. Le righe che la strategia scelta non usa spariscono: `base` sotto una
`linear` non e' una manopola morbida, e' la manopola di un'altra strategia.

Strategie e parametri sono quelli di PGE-ui (`src/components/VoicesSection.jsx`)
— pitch `step | range | chord | chord_progression | stochastic | spectral`,
onset `linear | geometric | stochastic`, pointer `linear | stochastic`, pan
`range | stochastic | step`. **Cosa si automatizza lo decide l'engine, non
l'estetica:** `_parse_strategy_kwarg` (`core/stream.py`) fa diventare envelope
qualunque kwarg envelope-like, quindi `step`, `pitch_range`, `max_offset`,
`base`, `pointer_range`, `spread`, piu' `num_voices` e `scatter`, stanno sui
breakpoint come tutti gli altri numerici, col loro menu di interpolazione.
`strategy`, `unit`, `chord`, `voice_leading`, `max_partial` e il flag
`normalized` sono struttura, e restano fissi per lo stream.

L'eccezione e' **`chord_progression`**, dove l'accordo E' una funzione del
tempo: si sceglie per breakpoint come `grain.envelope`, e sul documento diventa
`progression: [[t, accordo], ...]`. Un accordo ripetuto non apre un passo
nuovo — dura finche' non cambia — e il **rivolto** e' il terzo elemento del
passo, scritto solo quando non e' lo stato fondamentale e limitato alle note
che quell'accordo ha. Con `chord` invece il rivolto e' uno scalare: vale
quello del primo breakpoint. Il tipo di interpolazione del punto diventa
l'`interp` della progressione (`linear`/`cubic` glissando, `step` a blocchi).

Sul documento ci va solo quello che l'engine legge davvero (`vociDoc`): gli
assi spenti spariscono, di ogni blocco restano le chiavi della sua strategia,
`unit: edo` diventa `{edo: N}` col numero del campo accanto, `normalized`
diventa il booleano, e un `voices:` con una voce sola e nessuna strategia non
si scrive affatto. Il round-trip e' verificato (`tests/test_graph_js.py`).

## Gli inviluppi realizzati (sotto lo spectroscope)

Dopo un render del laboratorio, sotto lo spectroscope compaiono **le curve che
lo stream ha davvero percorso**, come la corsia di uno stream nella partitura
(`ScoreVisualizer._draw_envelopes`). Non sono gli inviluppi che hai scritto:
vengono dalla IR, cioe' dallo stream caricato dall'engine, quindi dentro ci
sono anche le **curve derivate** — `effective_density`, il quoziente
fill_factor/grain_duration che il motore calcola a ogni onset e non conserva —
e gli **offset per-voce** (`voice_pitch_offset__v1`, ...), che non stanno nel
documento perche' sono il risultato della strategia, non la strategia.

Le due funzioni sono quelle della partitura, non una riscrittura:
`envelope_extractor.get_stream_envelopes` dice quali curve ha lo stream,
`envelope_display` quanto sono alte. Ogni curva scala sulla **propria**
escursione (nessun range fisso: e' l'auto-zoom della partitura), il pan sul
giro. La legenda sotto dice il colore, il nome e l'escursione vera
(`10.0ms … 200ms`), che e' l'unica cosa che una curva normalizzata non puo'
mostrare da se'.

Il conto lo fa il server dopo il render (`engine_bridge.stream_analysis`,
chiamato da `_analisi` in `serve.py`) ricaricando lo YAML appena scritto, e
le curve tornano nella risposta di `POST /render` gia' campionate e
normalizzate: la pagina tira una linea e basta. Le **costanti restano fuori**
(`show_static=False`), come nella partitura: qui si guarda cio' che si muove.

**Gradini esatti, e i breakpoint.** La curva non arriva come una griglia di
campioni ma come la spezzata gia' fatta (`pts`), perche' un segmento `step`
campionato fitto resterebbe una rampa ripidissima — due pixel di pendenza
invece di una verticale. La regola e' quella della partitura
(`drawstyle='steps-post'`) ma applicata **per segmento**, perche' l'engine
tiene l'interpolazione sul segmento (`Envelope.segments`): un `step` da' due
punti, l'angolo, e il salto lo chiude il primo punto del segmento dopo; una
`linear` o una `cubic` restano campionate fitte, tante quanto la loro quota
dei 600 punti, cosi' la S di una cubica corta non diventa una spezzata.
Tutto in `_spezzata` (`engine_bridge.py`), verificata in
`tests/test_engine_bridge.py`. Arrivano anche i **breakpoint** (`bp`), che la
pagina segna con un quadratino: sulle curve che l'engine campiona da se'
(`effective_density`, gli offset per-voce) sono fitti, ed e' giusto che si
veda che sono campionate e non scritte.

Il pannello e' l'asse del tempo del file, quindi si clicca per cercare come
sonogramma e forma d'onda, e il cursore corre anche li'. Sparisce appena si
ascolta un sample: li' non sarebbero le curve di niente.
Le curve occupano la frazione di larghezza che lo stream occupa nel file
(la coda dell'ultimo grano puo' allungarlo), verificata in
`tests/test_graph_js.py`.

Sono la realizzazione **che ha suonato**, non un'altra estrazione, anche con
una strategia stocastica: il documento porta un `seed` e lo `stream_id` del
file (#5) e l'analisi ricarica quello stesso YAML, quindi l'RNG
`(seed, stream_id, componente)` ripesca le stesse sequenze. L'unico caso in cui
non torna e' un documento senza seed su uno studio senza seed, dove il
laboratorio non ne inventa uno: li' lo dice la riga di stato, e il chip accanto
al nome del file legge `senza seed`.

**L'altezza dei pannelli di analisi** e' quella dell'attributo `height` del
canvas e basta: `width:100%` da solo la lascerebbe al rapporto fra gli
attributi della bitmap (`height:auto` su un elemento rimpiazzato), e con la
bitmap ancora larga 300 — nessun audio caricato — una colonna larga stirava il
sonogramma per mezzo schermo. La riga che la fissa sta nel JS, non nel CSS,
cosi' i numeri restano scritti una volta sola (nell'HTML).

## I grani (sotto gli inviluppi)

Sotto le curve, l'altro pannello della partitura: il **piano dei grani**
(`ScoreVisualizer._draw_grains_full`). x e' il tempo d'uscita, y la posizione
di lettura nel sample — l'asse su cui la partitura mette la forma d'onda del
file — l'altezza di un grano e' la porzione di buffer che percorre davvero
(`read_span`, durata per |pitch_ratio|, verso il basso se legge all'indietro),
il colore la sua altezza sulla stessa colormap divergente auto-zoomata, e
l'opacita' il volume. Tutto da `grain_visuals`, che e' dove quella mappa vive:
qui non si riscrive.

Il conto lo fa il server dopo il render, nello **stesso caricamento** delle
curve (`engine_bridge.stream_analysis`, che ha preso il posto di
`stream_envelopes`): materializzare gli stream e' la parte cara, e chiederlo
due volte raddoppierebbe l'attesa di ogni ascolto.

Sono decine di migliaia di grani, e per questo:

- non arrivano come oggetti ma come **colonne parallele** di numeri (`x`, `w`,
  `y`, `h`) piu' un indice `k`; il colore non viaggia per grano, e' una
  `palette` di 128 tinte (32 tacche di pitch x 4 di volume) mandata una volta;
- sopra `GRANI_MAX` (40000) si **decima** — uno ogni N, e la legenda dice
  quanti erano: un canvas largo mille pixel non ha dove mettere il
  centomillesimo grano;
- il grano e' una **colonna**, non la freccia ne' la silhouette della finestra:
  a questa scala e' largo un paio di pixel, e la partitura stessa ripiega sulla
  freccia sotto i tre (`window_shape_min_px`). La freccia tornerebbe utile solo
  con uno zoom sull'asse dei tempi, che il pannello non ha;
- si disegna **un `Path2D` per tinta**, non per grano: `fillStyle` cambia 128
  volte invece di 40000, ed e' li' che sta il costo di un canvas 2D.

A sinistra, in verticale, c'e' la **forma d'onda del sample**: senza, il piano
dice dove il pointer legge ma non cosa c'e' li'. E' la corsia `ax_wave` della
partitura (`_draw_waveform_full`) — stesso asse y dei grani, x l'ampiezza —
disegnata su un canvas suo accanto a quello dei grani, cosi' il cursore e il
seek restano in percentuale sulla sola larghezza del piano. I campioni sono
quelli veri, presi da `/samples/` e tenuti nella stessa cache degli ascolti:
sentire il sample dopo averlo visto non ridecodifica niente. Il nome del file
viaggia nel payload (`sample`), l'audio no.

**Dove si legge adesso.** Sulla forma d'onda corre una riga orizzontale,
perpendicolare al cursore rosso del tempo e dello stesso colore: e' lo stesso
istante letto sull'altro asse. Non e' un dato in piu' — sono i grani vivi in
quell'istante. Un grano percorre il suo tratto di buffer mentre dura, quindi
al tempo t legge `y + h * (t - onset) / durata`, non il pointer d'attacco;
fra i grani vivi c'e' un'escursione (offset_range, voci, dispersione del
pointer) e quella diventa la **banda**, con la riga sul centro — cento righe
separate sarebbero cento righe attaccate. Niente grani vivi, niente banda.
Il conto sta in `letturaA`, verificato in `tests/test_graph_js.py`; la
scansione e' lineare su tutti i grani a ogni frame, che su quarantamila
valori tipizzati non si sente.

Come il pannello degli inviluppi: compare solo dopo un render del laboratorio,
si clicca per cercare, il cursore ci corre sopra, e sparisce appena si ascolta
un sample. Tutti e due si ridisegnano alla fine di `analyse`, non appena chi
rende li ha chiesti: stanno sull'asse dei tempi del file, e quella durata la
sa solo l'analisi — che e' asincrona. Disegnati prima, restavano vuoti finche'
un click su un breakpoint non li ridisegnava.

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
