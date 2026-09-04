# Piano — `expr`: mini-linguaggio aritmetico per Env e spread

**Repo:** `granulation-studies` (branch `feat/expr-env-arithmetic`)
**Stato:** attivo — design concordato in sessione di brainstorm (2026-07-09),
questo piano struttura solo l'implementazione TDD. Lingua: italiano, no emoji.

---

## 1. Intento

Poter scrivere un Env-sagoma normalizzato e combinarlo aritmeticamente con
scalari: `[[0,1],[0.1583,1.5]] * 50` → `[[0,50],[0.1583,75]]`. Due usi:

- **negli assi** (aritmetica statica): fattorizzare forma e livello di un Env,
  riusare la stessa sagoma a livelli diversi;
- **nello spread** (aritmetica per-stream): l'indice `i` del generato entra
  nell'espressione — `env * a * (i + 1)` produce n Env omotetici a livelli
  crescenti, la "funzione di i" che le strategy strutturate (`values`/`ramp`/
  banda) non esprimono in forma aritmetica libera.

Esempi d'uso concordati:

```yaml
# assi — forma-Threshold, scope = solo let
axes:
  density:
    base:
      expr: "env * 50"
      let:
        env: [[0, 1], [0.1583, 1.5]]

# spread — quarta strategy di over, scope = let + i + n
streams:
  v:
    spread:
      n: 4
      over:
        axes.density.base:
          expr: "env * a * (i + 1)"
          let:
            env: [[0, 1], [0.1583, 1.5]]
            a: 50
```

Vincolo di confine (come nested-generators): **l'engine non si tocca**. Il
nodo-expr si risolve interamente in granstudies alle seam esistenti; a valle
viaggiano solo forme statiche di `Threshold`.

---

## 2. Decisioni fissate (dal brainstorm — non riaprire)

| Decisione | Rationale |
|---|---|
| Parser: `ast.parse(mode="eval")` + whitelist nodi | stdlib, sicuro, ~50 righe; niente `eval` |
| Grammatica: numeri, nomi, `+ - * / **`, unario `-`, parentesi | il minimo che copre i casi d'uso; niente call/subscript/confronti |
| Env ⊙ scalare = elementwise sulle **y**, tempi intatti | è il significato musicale ("trasla/scala il livello, la forma resta") |
| Env ⊙ Env = errore esplicito | richiederebbe unione breakpoint + interpolazione; YAGNI al primo giro |
| `let:` accanto a `expr:`, chiavi = nomi in scope | esplicito, niente variabili globali implicite |
| Valori di `let`: scalari o forme **statiche** di Threshold | un nodo-generatore dentro `let` è un incrocio di meccanismi non richiesto → errore chiaro |
| `expr` NON entra in `Y_GENERATOR_KEYS` | negli assi è una forma-Threshold, non un generatore (non produce liste); nello spread è un marcatore locale a `_strategy` |
| Nello spread: `i` 0-based, `n` disponibili; `let` che li ridefinisce = errore | riservati; `i/(n-1)` dà il progresso normalizzato |
| `expr` non possiede il conteggio | una funzione di `i` ha bisogno che qualcuno dica quanti `i` — come le forme parziali di ramp |
| Errori: `ValueError` da `expr.py`, avvolti alle seam (`path` in `expand_env`, `ErrCtx` nello spread) | coerente con `value_generators`/`spread` esistenti |
| Risultati arrotondati a 9 decimali | coerenza con `ramp`/`band`/`expand_env` |

### Alternativa scartata: valutazione lazy in `_threshold_at`

Stesso argomento di nested-generators: `_threshold_at` è pura e calda,
rieseguire il parse a ogni `frac` è O(n·m) e infila scope in una funzione che
non ne ha. Il nodo-expr si compila **una volta** alla seam, come i
nodi-generatore.

---

## 3. Punti d'aggancio (impact analysis verificata sul codice)

| File | Impatto |
|---|---|
| `src/granstudies/expr.py` | **nuovo** — `eval_expr(text, scope) -> Threshold`, puro, zero import interni (solo stdlib) |
| `src/granstudies/value_generators.py` | `expand_env` riconosce il nodo-expr e lo valuta (scope = `let`); `expand_params` lo instrada a `expand_env` (oggi un dict senza marcatori Y viene attraversato come params qualunque e a valle `_threshold_at` esplode con `KeyError: 'points'`) |
| `src/granstudies/spread.py` | `_strategy` riconosce il marcatore `expr` prima di `y_generator`; `_owned_count` → `None`; `_strategy_values` → un `eval_expr` per `i` |
| `src/granstudies/study_spec.py`, `stack.py` | **zero modifiche** — consumano Threshold già passati per `expand_params` (verificato: `study_spec:466-471`, `stack:83-103`, `spread:137,212`) |
| `docs/study-yml-reference.md` | nuova forma di Env (sez. forme, ~riga 184) + strategy expr dello spread |

Copertura seam verificata: `base`/`range` degli assi (sweep e stack), `step`
di ramp e di drift, camminata-X — tutte passano per `expand_params`, quindi il
nodo-expr vale ovunque c'è un `Threshold` senza toccare i consumatori.

---

## 4. Unità di implementazione (TDD: test prima, per unità)

- [x] U1. **`expr.py` — il valutatore puro**

**Goal:** `eval_expr(text: str, scope: Mapping[str, Any]) -> float | list | dict`,
nessuna conoscenza di assi/spread.

**File:** crea `src/granstudies/expr.py`, `tests/test_expr.py`.

**Approccio:**
- `ast.parse(text, mode="eval")` + visitor ricorsivo; whitelist: `Expression`,
  `BinOp` (`Add`/`Sub`/`Mult`/`Div`/`Pow`), `UnaryOp` (`USub`/`UAdd`),
  `Constant` numerico (bool escluso), `Name`. Ogni altro nodo → `ValueError`
  col frammento incriminato.
- Valori: scalare, `[a, b]`, `[[t, v], ...]`, `{type, points, curve}`.
  Op binaria con un lato Env e uno scalare → elementwise sulle y (entrambi i
  lati: `env - 3` e `100 - env` funzionano; per `/` e `**` l'ordine conta e
  va rispettato). Forma dict: opera sulle y di `points`, preserva
  `type`/`curve`. Env ⊙ Env → errore "non supportato".
- Nome ignoto → errore che elenca i nomi disponibili in scope. Divisione per
  zero → errore chiaro (anche elementwise). Risultati `round(_, 9)`.

**Scenari di test:**
- Happy: `"2 + 3 * 4"` → 14 (precedenza); `"a * (i + 1)"` con scope → scalare;
  `"env * 50"` su breakpoint → y scalate, t intatti; `"env + 3"` → y traslate;
  `"env * 2"` su `[a, b]` → entrambi i capi; forma dict → y di points scalate,
  `type`/`curve` preservati; `"100 - env"` e `"env / 2"` (ordine rispettato);
  `"-env"` unario; `"i / (n - 1)"` → progresso.
- Edge: espressione senza nomi liberi e scope vuoto; scalare int vs float;
  `round` a 9 decimali.
- Errori: nome ignoto (messaggio elenca lo scope); `env1 * env2`; call
  (`"abs(x)"`), subscript, confronto, boolean → rifiutati; `"1 / 0"` e
  `"env / 0"`; sintassi rotta (`"a *"`); `True` come costante; valore di scope
  di forma non riconosciuta.

**Verifica:** `pytest tests/test_expr.py` verde; il modulo non importa nulla
da granstudies.

---

- [x] U2. **Nodo-expr alla seam `expand_env`/`expand_params`**

**Goal:** `{expr: "...", let: {...}}` riconosciuto come forma di `Threshold`
ovunque (assi base/range, step di ramp/drift, stack X-walk), compilato in
forma statica prima che chiunque lo consumi.

**Dipendenze:** U1.

**File:** modifica `src/granstudies/value_generators.py`; test in
`tests/test_value_generators.py` (file esistente).

**Approccio:**
- `is_expr_node(spec)`: dict con chiave `expr`. Validazione: chiavi ammesse
  solo `{expr, let}`; `expr` stringa; `let` dict (opzionale) con valori
  scalari o forme statiche — un nodo-generatore dentro `let` → errore
  ("solo forme statiche in let").
- In `expand_env`, prima del check `is_generator_node`: se nodo-expr →
  `eval_expr(spec["expr"], scope=let)`, poi validazione immediata del
  risultato con `_threshold_at(out, 0.0)` (pattern esistente, errore col
  `path`). `ValueError` da `eval_expr` ri-sollevato con prefisso `path`.
- In `expand_params`: il ramo `isinstance(v, dict) and not is_generator_node(v)`
  deve escludere anche i nodi-expr (instradarli a `expand_env`), altrimenti la
  ricorsione ci entra dentro come fosse un dict di parametri.
- Guardia difensiva in `_threshold_at`: un dict con `expr` che arriva fin lì è
  una seam mancata → errore esplicito invece di `KeyError: 'points'`.

**Scenari di test:**
- Happy: `expand_env` su nodo-expr con `env` breakpoint → forma statica
  attesa; nodo-expr in `base` di banda via `expand_params` (il percorso di
  `study_spec`/`stack`); nodo-expr nello `step` di drift (dict attraversato
  da `expand_params`); expr senza `let` (`"50"` → scalare).
- Edge: forme statiche e nodi-generatore passano invariati (nessuna
  regressione: la suite esistente resta verde).
- Errori: chiave extra nel nodo (`{expr, let, seed}`); `expr` non stringa;
  nodo-generatore dentro `let`; errore di `eval_expr` arriva col `path` nel
  messaggio; dict-expr passato crudo a `_threshold_at`.
- Integrazione: uno `study.yml` minimo con `axes.density.base` nodo-expr
  risolve end-to-end via `resolve_streams` (stile `tests/test_spread.py`).

**Verifica:** suite intera verde; l'esempio degli assi (sez. 1) produce l'Env
atteso.

---

- [x] U3. **Marcatore `expr` come quarta strategy di `spread.over`**

**Goal:** nello spread l'espressione è funzione di `i` (e `n`): un valore —
scalare o Env intero — per stream generato.

**Dipendenze:** U1 (U2 non è prerequisito tecnico ma va prima per coerenza
di messaggi d'errore).

**File:** modifica `src/granstudies/spread.py`; test in
`tests/test_spread.py` (file esistente, sezione nuova).

**Approccio:**
- `_strategy`: se `"expr" in cfg` → marcatore `("expr", cfg)` senza passare
  da `y_generator`; mutua esclusione con `values`/`ramp`/`base` (due marcatori
  → errore, riuso del messaggio "esattamente una strategy"). Stessa
  validazione chiavi/`let` di U2 (condivisa, non duplicata).
- `_owned_count`: `expr` → `None` (il conteggio viene da `spread.n` o da una
  strategy sorella; senza → l'errore esistente di `_resolve_n`).
- `_strategy_values`, marcatore `expr`:
  `[eval_expr(text, {**let, "i": i, "n": n}) for i in range(n)]`,
  avvolto in `ctx.wrapping(key=("spread", "over", path))`. `let` che
  dichiara `i` o `n` → errore. Il risultato va in `_deep_set` così com'è
  (scalare o Env intero).

**Scenari di test:**
- Happy: l'esempio concordato (`env * a * (i+1)`, n=4) → 4 stream con Env
  `[[0,50],[0.1583,75]]`, `[[0,100],[0.1583,150]]`, ...; expr scalare
  (`"10 * (i + 1)"`) → deep-set di scalari; `i`/`n` in scope
  (`"i / (n - 1)"`); expr appaiata per indice con una strategy sorella che
  possiede il conteggio (es. `values`).
- Edge: patch su un generato di spread-expr (il meccanismo patch esistente
  non cambia); `n: 1`.
- Errori: expr da sola senza `n` (→ "n non derivabile"); `let: {i: 3}`;
  `expr` + `values` nello stesso path; errore di valutazione porta
  stream/riga (`SpecError` con `locs`, stile `test_spread_error_carries_line_and_stream`).
- Integrazione: `resolve_streams` su doc con spread-expr → spec con gli Env
  attesi negli assi dei generati.

**Verifica:** suite intera verde; l'esempio dello spread (sez. 1) genera i
4 Env attesi.

---

- [x] U4. **Documentazione**

**Goal:** `docs/study-yml-reference.md` documenta la nuova forma di Env
(sezione forme, con l'insidia YAML "espressioni sempre quotate") e la strategy
`expr` dello spread (`i`/`n` riservati, non possiede il conteggio, Env ⊙ Env
non supportato).

**Dipendenze:** U2, U3.

**Test:** nessuno — solo documentazione.

---

## 5. Questioni rinviate all'implementazione

- Nome esatto di `is_expr_node` / firma della validazione condivisa tra
  `value_generators` e `spread` (si decide vedendo dove cade più naturale,
  probabilmente in `expr.py` per evitare import circolari — `spread` importa
  già da `value_generators`, non viceversa).
- Se l'overflow di `**` (OverflowError) meriti un messaggio dedicato o basti
  lasciarlo salire: si decide col test alla mano.

## 6. Impatto di sistema

- **Invarianti intoccati:** `Y_GENERATOR_KEYS`, firme di `band`/`ramp`/
  `_threshold_at`/`walk`, engine e YAML generati, semantica di sweep/stack.
- **Propagazione errori:** `ValueError` puro in `expr.py` → prefisso `path`
  in `expand_env` → `SpecError` con stream/file/riga alle seam che hanno
  `ErrCtx` (spread, study_spec).
- **Copertura integrazione:** i due esempi della sez. 1 come test end-to-end
  (U2 e U3), non solo unit.
