# Piano — banda-let: variabili random per-stream nella strategy `expr`

**Repo:** `granulation-studies` (branch `claude/study-yml-granulation-vars-d510k0`)
**Stato:** completato. Lingua: italiano, no emoji.

---

## 1. Intento

Nella strategy `expr` dello spread, poter dichiarare in `let` una variabile
**random**: un pescaggio per stream generato, che entra nello scope
dell'espressione accanto a `i` e `n`. Il caso d'uso: combinare aritmetica
deterministica (funzione di `i`) e dispersione stocastica nella stessa
espressione, senza dover scegliere tra la strategy banda (solo random, niente
aritmetica) e la strategy expr (solo aritmetica, niente random).

```yaml
streams:
  coro:
    spread:
      n: 8
      over:
        base.volume:
          expr: "v - 2 * i"            # pescaggio + gradino
          let:
            v: {base: -12, range: 6}   # banda-let: un random per stream
```

Lo spread è l'unico posto sensato: solo lì esiste una popolazione di stream
con un indice per-stream su cui "lanciare" il random. Negli assi e nei
parametri statici il divieto di nodi-generatore in `let` resta intatto.

---

## 2. Decisioni fissate

| Decisione | Rationale |
|---|---|
| Solo la forma **banda** (`{base, range?, seed?, distribution?, drift?}`) | è il vocabolario random esistente; `values`/`ramp` in `let` sono progressioni deterministiche già esprimibili con l'aritmetica su `i`/`n` → errore con hint |
| `n` dentro la banda-let = errore | il conteggio è dello spread; la banda-let pesca esattamente un valore per stream |
| `frac = i/(n-1)` sulla popolazione | stessa semantica delle altre strategy di spread: un `base`-Env fa scorrere la banda lungo i generati |
| Seed di default `stable_seed("<entry>:spread:<path>:let:<var>")` | deterministico tra run (ciclo rigenera-e-confronta); variabili e path diversi si decorrelano da soli; un `seed` esplicito congela la sequenza |
| Estrazione **prima** di `parse_expr_node` | `expr.py` resta puro (niente random, niente import da `value_generators` — eviterebbe pure un import circolare); il parse vede solo la parte statica di `let` |
| `distribution`/`drift` valgono anche qui | la banda-let è la banda di sempre: `expand_params` espande gli eventuali nodi annidati, `band()` fa il resto |
| Nomi riservati `i`/`n` vietati anche come bande-let | stesso errore della parte statica, controllo sull'unione dei due insiemi |

## 3. Punti d'aggancio

| File | Impatto |
|---|---|
| `src/granstudies/spread.py` | `_let_band` (validazione forma), split in `_strategy` (bande-let fuori dal parse), pescaggi in `_strategy_values` (un `band(n=...)` per variabile, valori nello scope per indice) |
| `src/granstudies/expr.py` | solo docstring: il contratto "niente generatori in `let`" resta, con l'eccezione documentata a monte |
| `src/granstudies/value_generators.py` | zero modifiche (riuso di `band`/`expand_params`/`stable_seed`/`is_generator_node`) |
| `docs/study-yml-reference.md` | banda-let nella sezione della strategy `expr`, eccezione nel nodo-expr, derivazione seed |
| `studies/study_expr_test/study.yml` | uso 4: esempio vivo della banda-let |

## 4. Verifica

`tests/test_spread.py`, sezione "banda-let": pescaggi in banda e non costanti,
determinismo tra run, seed esplicito ≡ `band()`, aritmetica con `let` statico,
scala di un Env-sagoma, decorrelazione tra variabili, banda collassata che
segue un `base`-Env, `distribution`/`drift`, errori (`n` nella banda-let,
`values`/`ramp` in `let`, chiave ignota, nome riservato). Suite intera verde.
