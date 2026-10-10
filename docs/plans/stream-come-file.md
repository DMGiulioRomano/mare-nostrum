# Lo stream come file: laboratorio e PGE-ui sullo stesso brano

Piano concordato con l'utente il 2026-09-28.

## Il problema

Due modi di lavorare sullo stesso brano che oggi non si parlano:

- **PGE-ui**, controllo macro: la timeline dove gli stream si sentono insieme,
  ma anche una DAW in cui ogni stream si modifica nel dettaglio;
- **il laboratorio** (`make serve`), controllo micro: un solo stream, un solo
  file YAML.

Si vuole che uno stream del brano **sia** un file YAML, apribile nel
laboratorio, e che il documento di PGE-ui lo importi. Il motore deve
continuare a leggere e rendere il brano da solo (`pge master.yml`).

## La forma della soluzione

```yaml
# master (il documento di PGE-ui)
seed: 42
streams:
  - file: streams/risacca.yml   # un documento del laboratorio
    onset: 12.5
    mute: true
  - stream_id: stream2          # gli stream scritti nel master restano validi
    ...
```

Regole:

1. Il file importato e' un documento del laboratorio cosi' com'e': un solo
   stream, si apre e si rende anche da solo.
2. Il path e' relativo alla cartella del master. Un file-stream non importa
   altri file (niente catene, niente cicli).
3. **Ogni chiave ha una sola casa.** Il master tiene solo il piazzamento:
   `onset`, `mute`, `solo`, `stream_id` (default: il nome del file). Tutto il
   resto, `duration` compresa, sta nel file-stream. `duration`, `bpm` e
   `seed` top-level del file importato si ignorano.
4. PGE-ui modifica anche gli stream importati (macro e micro): una modifica a
   una chiave del file-stream si scrive nel file-stream, non nel master.
5. **Duplicare** uno stream importato in PGE-ui crea un file nuovo e
   indipendente.
6. **Split** di uno stream importato: la prima meta' resta nel suo file
   (accorciata), la seconda diventa un file nuovo, `<nome>-2.yml`.
7. **Due editor, un file.** Ognuno ricorda com'era il file quando l'ha letto;
   prima di scrivere, se su disco e' cambiato: senza modifiche proprie
   rilegge, con modifiche proprie chiede (ricarica / sovrascrivi).

Identita' del suono: l'RNG del motore e' `(seed, stream_id, componente)`,
quindi lo stesso stream suona uguale nei due posti solo con stesso seed e
stesso id. Il laboratorio scrive `stream_id` = nome del file e un `seed`.

## Passi

1. **Il laboratorio conserva il documento che apre** (fatto: #3, #4, #9).
   `labDoc()` oggi ricostruisce lo stream dal `base:` dello studio piu' i
   parametri che conosce, e `carica()` legge solo quelli: aperto e risalvato,
   uno stream del brano perde `grain.read_direction` (8 stream su 10), legge
   `NaN` dagli inviluppi `{type, points}` e riceve chiavi del `base:` che non
   aveva. Si parte dallo stream aperto e si sovrascrive solo cio' che il
   laboratorio conosce. Criterio: ogni stream di `mare-nostrum.yml`, aperto e
   risalvato senza toccare niente, da' al motore lo stesso stream.
2. **`file:` nel motore** (PythonGranularEngine): risolto in `load_yaml`,
   prima di tutto il resto; cache, fingerprint, solo/mute invariati. Errori
   che nominano master e file importato. Poi bump del submodule (fatto:
   PythonGranularEngine#291, #7; la fixture e' in
   `tests/fixtures/stream_come_file/`).
3. **Laboratorio:** `stream_id` = nome del file, `seed` nel documento
   (fatto: #5), guardia sul file cambiato su disco (regola 7; fatto: #6).
4. **PGE-ui:** import risolti in lettura, file-stream riscritti in
   salvataggio e prima del render, stessa guardia, duplica e split (regole
   5-6) (fatto: DMGiulioRomano/PGE-ui#183-#187). La guardia copriva solo il
   master: la regola 7 sui file degli stream — firmati alla lettura, guardati
   in salvataggio e render anche quando non si riscrivono, riletti da soli
   senza riaprire il brano — e' venuta con la review del piano. Round-trip
   inverso: un file del laboratorio (finestra che cambia nel tempo,
   progressione) torna intatto da PGE-ui (fatto: DMGiulioRomano/PGE-ui#188).
   Il brano: fatto (#8). Il master e' uno solo, quello versionato, spostato in
   `configs/mare-nostrum.yml`, dove lo apre PGE-ui, con `seed: 1441`; ognuno
   dei dieci stream e' in `configs/streams/<id>.yml`, col nome del file
   uguale allo `stream_id` di prima (vedi CLAUDE.md, «Il brano»).
5. **PGE-ls** deve conoscere la chiave `file:` (DMGiulioRomano/PGE-ls#65).

## Cosa resta

- **La cache per stream non vede il seed**, ne' quella del motore ne' i
  pallini di PGE-ui: dopo un cambio di seed del master gli stem in cache
  restano la realizzazione di prima, annunciati come buoni. Fino a che il
  fingerprint non lo porta, il rimedio e' a mano (CLAUDE.md, «Il brano»).
- **Cancellare o rinominare** uno stream importato in PGE-ui lascia il file
  com'era: un file che nessuno nomina, o un id che non e' piu' il nome del
  file. `tests/test_brano.py` lo dice, il rimedio e' a mano (CLAUDE.md).
