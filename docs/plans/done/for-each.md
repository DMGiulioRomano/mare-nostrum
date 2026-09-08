# `for_each:` — un asse che moltiplica i file, non i gradini

Piano concordato con l'utente il 2026-09-08. Sostituisce la modalità take
(`docs/plans/done/take-mode.md`), che viene rimossa.

## Il problema

Gli `axes:` di uno studio sono assi **interni**: scorrono nel tempo dentro lo
stesso file. Su `001-41-duration-fill-factor` i due assi fanno 24 x 7 gradini da
7s = ~20 minuti per variante. Aggiungere `distribution` come terzo asse
triplicherebbe la durata di un file già lungo, e il confronto fra
`distribution: 0` e `distribution: 1` finirebbe a mezz'ora di distanza dentro
lo stesso ascolto.

Ma il confronto che serve è: **lo stesso sweep, rifatto per intero con quel
parametro diverso**. N valori, N file, ognuno percorre gli stessi due assi.

Oggi si ottiene a mano con la modalità take (cambia `study.yml`, rigenera,
confronta le due cartelle). Male: le take si nominano con la data e la chiave
cambiata, non con il valore; sono un archivio cronologico, non uno spazio
dichiarato; e per rivedere una variante bisogna riportare a mano il vecchio
valore nello `study.yml`.

## La forma della soluzione

Un blocco top-level `for_each:`, con la **grammatica di `versions:`** (assi
ortogonali, prodotto cartesiano lessicografico nell'ordine di dichiarazione),
ma il prodotto si materializza in **file separati** invece che nel tempo.

Ogni combinazione è una **patch sullo `study.yml`**: chiavi = path puntati su
tutto il documento, non solo su `base:`. Il documento patchato è quello che
tutti i processi leggono, quindi `for_each` vale per sweep, stack, versions e
percorso senza toccarne nessuno.

```yaml
for_each:
  distribution: {values: [0, 0.5, 1]}      # asse a manopola singola: base.distribution
  griglia:                                  # stati nominati, per override non scalari
    fitta: {axes.fill_factor.values: [0.5, 0.7, 0.85, 1, 2, 4, 8]}
    rada:  {axes.fill_factor.values: [0.5, 1, 4]}
```

→ 3 x 2 = 6 render in `generated/<study>/<combo>/`, con `<combo>` =
`distribution=0.5__griglia=rada`.

### Perché serve anche fuori dallo sweep

Ci sono chiavi che **non possono** essere assi interni, per costruzione:

- **stack** — le camminate-X sono stocastiche (`seed`, `range`, `drift`).
  Ascoltare cinque realizzazioni dello stesso impasto è cinque file, mai uno:
  `for_each: {seed: {values: [1, 2, 3, 4, 5]}}`.
- **percorso** — idem per `seed`/`drift`, più `arco:` e `passo:`: la timeline
  *è* il file, quindi «la stessa legge distesa su 90, 180, 360 secondi» esiste
  solo come asse esterno.
- **versions** — valvola di sfogo del cartesiano interno: `grana x densita` = 16
  versioni concatenate, una terza variabile porta a 48 e il file diventa
  inascoltabile. La si sposta fuori e si ottengono N file da 16.

Il criterio, che è anche la riga di doc del blocco:

> Interno se il confronto sta nella **giustapposizione** (lo senti cambiare
> mentre suona). Esterno se sta nel **riascolto** (devi risentire la stessa cosa
> da capo), o se la chiave definisce il file stesso — `seed`, `sample`, `arco`,
> la durata.

### Naming delle cartelle

- Valore **scalare corto** (numero, bool, stringa breve senza separatori) →
  `chiave=valore`, sanificato come già fa `_sv_name` (`[^A-Za-z0-9._-]` → `_`).
- Qualunque altra cosa (lista, dict, breakpoint, banda) → l'asse **deve** essere
  a stati nominati: il nome lo dà l'utente. Un generatore non scalare in un asse
  a manopola singola è errore di parse, con hint («dagli un nome: `for_each:
  {griglia: {rada: {...}}}`»). Niente indici anonimi `d0/ d1/`: un nome di
  cartella che non dice cosa contiene è il difetto delle take.
- `for_each` assente = una combinazione vuota = `generated/<study>/` piatto,
  identico a oggi. È il caso degenere, non un ramo speciale.

### Combinazioni orfane

Togliere un valore da `for_each` lascia la sua cartella con dentro l'audio
vecchio. Stesso trattamento delle varianti orfane dello sweep
(`_warn_orphans`, `src/granstudies/__main__.py:225`): **avviso, nessuna
cancellazione**. Una combinazione orfana è spesso proprio quella che si vuole
tenere — il «prima» da riascoltare — e cancellarla d'ufficio rifarebbe il
difetto delle take. Per buttarla c'è `rm -rf`, non serve un target.

## L'interfaccia

```zsh
study 001-41-duration-fill-factor              # rigenera TUTTE le combinazioni
COMBO=distribution=1 study 001-41-...          # solo quella (e apre solo i suoi .sv)
make where STUDY=...                           # stampa le root, una per riga
```

`COMBO` è un filtro di sessione, non un interruttore di modalità: senza, si fa
tutto. Prende il nome esatto della cartella-combinazione. Serve a due cose che
sono la stessa: non rirenderizzare sei varianti da venti minuti per sentirne
una, e non aprire sei sessioni di Sonic Visualiser insieme.

Il render resta incrementale per mtime dentro ogni combinazione, quindi
rigenerare tutto dopo una modifica che tocca una sola combo costa poco. Niente
hardlink fra combinazioni: sono documenti diversi per costruzione, e il caso
«due combo con lo stesso audio» non esiste (se esiste, l'asse è inutile).

## Cosa si tocca

| File | Modifica |
|---|---|
| `src/granstudies/for_each.py` (nuovo) | Parse del blocco, prodotto cartesiano, label della combinazione, deep-merge della patch sul documento. Funzione pura: nessun I/O, così gl-ls può consumarla. |
| `src/granstudies/__main__.py` | Due choke point e un loop. `gen_dir()` appende il segmento-combo; `_load_data`/`_load_specs` applicano la patch. Il loop sta in `_dispatch`: ogni comando gira N volte con il contesto-combo impostato, e i `cmd_*` non si toccano. Via `take_label()`, `cmd_take_slug`, `study_diff_slug`. |
| `make/takes.mk` | Cancellato (`take`, `takes`, `takes-clean`). `where` si sposta in `make/studies.mk`. |
| `.zsh_completions/_study` | Via la chiamata a `make take`; `root` diventa la lista delle root, filtrata da `COMBO`; completion di `COMBO` dalle cartelle esistenti. |
| `.gitignore` | `/takes/` **resta**: la cartella e' ancora sul disco con i suoi gigabyte, e toglierla dall'ignore riempirebbe `git status` di audio. Il commento dice che la modalita' non esiste piu'. |
| `docs/study-yml-reference.md` | Sezione `for_each:` accanto a `versions:`; via il paragrafo take dal layout di `generated/`. |
| `README.md`, `CLAUDE.md` | Via la sezione «Modalità take», dentro la sezione `for_each`. |
| `tests/` | Prodotto cartesiano e ordine lessicografico; label con valori scalari e stati nominati; errore sul non-scalare anonimo; patch che tocca `axes.*` e non solo `base.*`; `gen_dir` con e senza combo; avviso orfane. Via i test take di `test_render.py`. |

In `render.py` e `sv_export.py` sparisce anche lo sgancio dell'hardlink prima
della scrittura: serviva solo perche' una take nasceva come `cp -al` della
precedente. Le combinazioni non condividono inode — sono documenti diversi per
costruzione — quindi la guardia era diventata codice morto.

`takes/` non viene migrato: è fuori da git, e le take esistenti restano sul
disco finché l'utente non le cancella. Chi vuole conservarne una la riscrive
come stato di `for_each`.

## Impatto su gl-ls

Il blocco è sintassi nuova osservabile nello `study.yml`: chiave top-level
`for_each:`, path puntati come chiavi (forma che nessun altro blocco usa),
regola «non-scalare → stato nominato obbligatorio», e la guardia anti-refuso
sui path che non esistono nel documento. Prima del merge va aperta una issue su
`DMGiulioRomano/gl-ls` (regola `.claude/rules/gl-ls-impact.md`), chiedendo
conferma all'utente.

## Scartato

- **`scope: file` come flag sull'asse** (`axes: {distribution: {values: [...],
  scope: file}}`): diff minimo, ma un asse che non scorre nel tempo non è un
  asse — andrebbe escluso dagli `orderings`, ignorerebbe `interpolation`, e ogni
  regola sugli assi acquisterebbe un'eccezione.
- **`for_each` dentro `sweep:`**: vero che è lo sweep a essere moltiplicato, ma
  lo legherebbe a un processo solo — stack, versions e percorso ne hanno
  bisogno quanto lui.
- **Tenere `TAKE` accanto a `for_each`**: due meccanismi per la stessa cosa
  significa non fidarsi di nessuno dei due. Il gesto rapido («ho cambiato, non
  voglio perdere il prima») diventa esplicito: si nomina uno stato.
- **Cancellazione automatica delle combinazioni orfane**: vedi sopra.
