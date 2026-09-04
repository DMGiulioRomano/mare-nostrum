# Piano — `distribution` (uniform/gaussian) e `drift` (random walk correlato)

**Repo:** `granulation-studies` (issue #16, branch `claude/skills-download-install-j5thmr`)
**Stato:** implementato (TDD, suite verde). Lingua: italiano, no emoji.

Costruito **sopra** i generatori annidati (`docs/plans/done/nested-generators.md`),
che risultano gia' implementati (`expand_env`/`expand_params` in
`value_generators.py`): la questione aperta della issue («sopra o in parallelo»)
si risolve da sola — sopra.

---

## 1. Intento

Oggi la banda `[base(frac), base(frac)+range(frac)]` viene pescata in modo
**indipendente e uniforme** a ogni punto (banda-Y: `band`/`band_at`) o a ogni
passo (camminata-X: `walk`). Due estensioni ortogonali, entrambe sibling di
`base`/`range` in **entrambi i registri** (`axes.<asse>` e `stack.<asse>`):

1. **`distribution: uniform | gaussian`** — *come* si pesca dentro la banda,
   indipendente dal fatto che il pescaggio sia correlato o no. Default
   `uniform` (comportamento attuale, bit-identico).
2. **`drift`** — marcatore del random walk correlato («passo dell'ubriaco»):
   il valore non e' piu' un pescaggio indipendente ma `precedente +
   passo_casuale`, per una deriva organica invece del su-e-giu' a scatti.

## 2. Semantica (decisioni della issue + scelte di design)

### `distribution`

- `uniform`: `rng.uniform(lo, hi)` — identico a oggi.
- `gaussian`: media al **centro banda** `(lo+hi)/2`, deviazione standard
  `(hi-lo)/6` (i bordi banda cadono a 3 sigma, ~0.3% di estrazioni fuori),
  **clamp** ai bordi. Banda collassata -> centro (deterministico, come oggi).
- Ogni altro valore -> errore.

### `drift`

Dict `{step: Env, seed?: int}`; `step` obbligatorio, chiavi ignote -> errore.

- **Valore iniziale**: pescaggio casuale come oggi (secondo `distribution`),
  con l'RNG della banda; da li' in poi cammina.
- **Passo**: a ogni punto/passo successivo, `s = step(frac) * (hi - lo)` —
  `step` e' **frazione della banda corrente**, si adatta se la banda respira.
  `step` e' un **Env** (stesso pattern di `ramp.step`), consultato a ogni passo
  sul dominio di `base`/`range` del registro: posizione sull'asse per la Y,
  tempo reale normalizzato per la X. `step(frac) < 0` -> errore.
- **Distribuzione del passo**: la stessa `distribution` della banda —
  `uniform` -> `U(-s, +s)`; `gaussian` -> `N(0, s)` (`s` e' la sigma).
- **Bordo banda**: **riflessione** (il valore rimbalza su `[lo, hi]`, fold
  triangolare, robusto anche a passi > 2*larghezza).
- **Banda mobile**: se il valore corrente cade fuori dalla banda al nuovo
  frac, **clamp immediato** dentro i nuovi limiti, poi si cammina.
- **Banda collassata** (larghezza 0): il valore segue `base`
  deterministicamente, come oggi.
- **Seed**: catena gerarchica del §7 di nested-generators — l'RNG del drift
  usa `drift.seed` esplicito, altrimenti `stable_seed(f"{seed_banda}:drift")`.
  RNG separato da quello della banda: il pescaggio iniziale resta stabile
  quando si fissa/cambia il seed del drift e viceversa.
- **`drift.step` annidabile**: un nodo-generatore dentro `step` si espande
  alle seam come ogni Env (path `drift.step`, seed derivato dalla catena,
  guardia di profondita' esistente `MAX_ENV_DEPTH`).

## 3. Dove vive nel codice

1. **`value_generators.py`** — il cuore:
   - `_draw(rng, lo, hi, distribution)`: il pescaggio singolo (uniform/gaussian);
   - `_reflect(v, lo, hi)`: fold triangolare nel bordo banda;
   - `_band_sampler(base, range, seed, distribution, drift, where) -> sample(frac)`:
     closure con lo stato del walk dentro — l'unico posto dove la meccanica
     drift esiste, condiviso dai tre consumatori;
   - `band` e `band_at` riscritte sopra il sampler (firme estese con
     `distribution="uniform"`, `drift=None`; ramo default bit-identico);
   - `_BAND_KEYS` += `{distribution, drift}` (viaggiano con `base` in
     `y_generator`, quindi assi, spread e nodi annidati le vedono gratis);
   - `expand_params`: ricorsione nei dict che **non** sono nodi-generatore
     (cosi' `drift.step` si espande col path accumulato; le forme statiche
     `{type, points, curve}` attraversano invariate).
2. **`x_strategies.py`** — `walk` estesa (`distribution`, `drift`), pescaggio
   della frequenza via `_band_sampler` (guardie `f <= 0` e `MAX_POINTS`
   invariate).
3. **`study_spec.py`** — `_BAND_KEYS` locale += le due chiavi (strip corretto
   negli override di stream che cambiano generatore); whitelist di
   `_stack_config` += `{distribution, drift}`.
4. **`stack.py`** / **`spread.py`** — nessun cambio: le chiavi fluiscono nei
   params della banda per costruzione.
5. **`docs/study-yml-reference.md`** — sottosezioni `distribution` e `drift`
   nella banda-Y; chiavi ammesse della camminata-X aggiornate.

## 4. Piano di test (TDD)

- `test_value_generators.py`: gaussian deterministico/in banda/centrato,
  banda collassata, distribution ignota -> errore; drift deterministico, passi
  limitati da `step*larghezza`, correlazione (escursione media dei passi <<
  pescaggio indipendente), riflessione con passo grande, clamp su banda
  mobile, `step` Env (freeze a step 0), step negativo/`drift` malformato ->
  errore, seed derivato `:drift` e seed esplicito che vince, ramo default
  bit-identico (regressione), `drift.step` annidato via `expand_params`.
- `test_x_strategies.py`: walk gaussian/drift deterministici, tempi ordinati
  in `[0, 1)`, drift che cambia i tempi rispetto al pescaggio indipendente,
  guardie invariate.
- `test_stack.py` / `test_study_spec.py`: drift/distribution nella banda-Y
  con camminata-X e nel blocco `stack:` (whitelist), sweep con banda
  gaussian+drift al parse, strip delle nuove chiavi quando uno stream cambia
  generatore.
