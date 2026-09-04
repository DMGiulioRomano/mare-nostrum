# Promemoria — cose rimaste da fare

Cose che vengono in mente durante le sessioni ma non si fanno subito. Quando
una voce è fatta, si sposta in fondo sotto `## Fatto` con la data, non si
cancella.

## Da fare

- [ ] Riascoltare le 4 zone d'ombra compartimentate (stream `zona_ombra_d01_10`,
  `zona_ombra_d10_20`, `zona_ombra_d25_50`, `zona_ombra_d55_80` — study.yml:66-105)
  con i 7 cugini pointer.start (indice→secondi: 1=0.1 2=0.25 3=0.4 4=0.55 5=0.8
  6=0.915 7=1.1), sostituiscono la mappa precedente in `riepilogo.md`. In
  particolare per `zona_ombra_d55_80` verificare l'estensione grain.dur fino a
  0.008 (prima non coperta, segnalata come "da verificare" nel vecchio riepilogo).
- [ ] `zona_ombra_d55_80`: la ramp density ora arriva a **80**
  (`study.yml:101`, valori 55 e 80). Ho sentito finora solo fino a density 60;
  density 80 è ancora da sentire.
- [ ] Ascolto differenza di density tra due stream in stack (versions),
  ripetuto a diverse densità di base: 20–30 Hz, 30–50 Hz, 50–100 Hz,
  100–1000 Hz. (Il range 30–50 Hz con differenze 0.01/0.1/1 è già stato
  fatto — vedi ascolto/2026-07-14.md, sessione 3. Manca: affinare la soglia
  di transizione tra 0.1 e 1 nel range già fatto, e ripetere lo stesso
  protocollo negli altri range.)
- [ ] Ascolto sweep con il parametro `distribution`: riprendere ad usarlo e
  sentire come si comporta il movimento della distribution a diverse
  densità che si muovono nel tempo (density come sweep, non fissa).
- [ ] Indagare `distribution` su tutte le altre scale di grain.duration, non
  solo `10-50ms` (dove il 2026-07-18 sono emersi lo sdoppiamento in due
  voci a bassa density, l'effetto "radio che perde il segnale" tra roughness
  e banda audio, e la differenza step/cubic — vedi ascolto/2026-07-18.md,
  sessioni 3-5): ripetere lo stesso protocollo su `1-10ms`,
  `1-50smp`, `50-300ms`, `300-1000ms` e `stack`, per capire quali effetti sono
  specifici del range 10-50ms e quali sono generali a `distribution`.
- [ ] Chiarire Sessione 1 del 2026-07-14: "3 Hz (terzi)" — capire se
  intendevo terzi di tono o Hz di differenza.
- [ ] Fare tutti gli ascolti dei grani della scala **1-50smp** e delle scale **50-300ms** / **300-1000ms**.
- [ ] Scrivere la scala **meso** (ancora da fare) e poi farne gli ascolti.

## Fatto

- [x] 2026-07-21 — Funzione `study` (`.zsh_completions/_study`): passare uno
  `STREAM` a uno studio senza blocco `sweep:` (es. `study stack_1-50smp
  cugini`) faceva saltare in silenzio l'intero ramo `stack`/`versions` in
  `cmd_sv`, con `[sv] 0 sessioni totali` invece dei `.sv` attesi — `STREAM`
  filtra solo dentro `sweep/envelope/<stream>*`, non ha senso su documenti
  multi-stream. Ora la funzione avvisa e si ferma se lo `study.yml` non ha
  `sweep:` e viene passato uno `stream`.
- [x] 2026-07-21 — Prefisso `grain_` tolto da tutte le cartelle scala
  (`grain_1-10ms`→`1-10ms`, ecc.): era ridondante, è sempre grain.duration.
  Le varianti stack prendono il prefisso `stack_` + range: nuova
  `stack_1-50smp` (7 punti di lettura insieme, `versions` su density e grana).
  La cartella `stack` senza suffisso resta quella delle curve non cartesiane.
- [x] 2026-07-21 — Il `.sv` di stack/versions disegna anche gli assi **statici**
  come retta a due breakpoint: prima un asse fermo (numero nudo, nessun
  envelope) spariva dai pane.
- [x] 2026-07-18 — Cartelle scala rinominate in base al range di grain.duration:
  `base`→`1-10ms`, `short`→`1-50smp`, `long`→`50-1000ms`
  (`stack` invariata). Stream `zona_ombra_d05`→`zona_ombra_d01_10` (era già
  density 1-10, il nome non rifletteva il range) e `zona_ombra_d55_60`→
  `zona_ombra_d55_80` in tutti e tre gli study.yml.
- [x] 2026-07-18 — Diario di ascolto spostato in `studies/ascolto/` (unico per lo
  studio) e struttura `studies/` appiattita: le scale sono cartelle dirette
  (`base`, `short`, `long`, `stack`) invece che `study01_*`. Il repo è lo studio;
  in futuro diventerà un template. `STUDY=base` sostituisce
  `STUDY=study01_grain_density`.
