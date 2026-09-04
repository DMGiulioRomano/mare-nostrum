# Piano — expr annidati dentro let (issue #28)

**Repo:** `granulation-studies` (branch `claude/issue-28-implementation-21m3n1`)
**Stato:** completato. Lingua: italiano, no emoji.

---

## 1. Intento

Poter legare in `let` una variabile che è a sua volta un nodo-expr: sagome che
dipendono da altre espressioni si fattorizzano nel `let`, senza pre-calcolare
i breakpoint a mano fuori dal nodo.

```yaml
axes:
  density:
    n: 4
    base:
      expr: "shape * 50"
      let:
        env: [[0, 1], [0.1583, 1.5]]
        shape: {expr: "min(env, 1.2)"}   # riferisce il fratello 'env'
    range: 0
```

Il motore di valutazione (`_eval`/`_call`/`_map_y`) non cambia: il lavoro vive
nel resolver dello scope di `let`.

## 2. Decisioni fissate

| Decisione | Rationale |
|---|---|
| Risoluzione **lazy all'eval**, non al parse | un expr annidato può riferire nomi che esistono solo alla valutazione (`i`/`n` dello spread, bande-let, variabili di percorso); il parse valida solo la struttura |
| Ordine di dichiarazione irrilevante | la risoluzione on-demand alla prima referenza è un ordinamento topologico implicito — niente toposort esplicito sul dict |
| Cicli = errore esplicito con la catena (`a -> b -> a`) | stack di risoluzione condiviso alla radice dello scope; la chiave è il **binding** `(scope, nome)`, non il solo nome, così l'ombreggiatura tra livelli diversi non produce falsi cicli |
| Un expr annidato **può avere il proprio `let`** | scope **lessicale**: i nomi interni ombreggiano gli esterni, i nomi esterni restano visibili — la semantica meno sorprendente per chi scrive YAML |
| Un nome ridefinito non vede il nome che ombreggia | `a: {expr: "a + 1"}` dentro un let interno è auto-riferimento, quindi ciclo: nessuna semantica "outer reference" inventata nel v1 |
| Banda-let e expr annidato **convivono** nello stesso `let` | lo spread estrae le bande *prima* del parse (invariato); gli expr annidati restano nella parte statica e all'eval vedono anche i pescaggi e `i`/`n` |
| Guardia di profondità 8 (`_MAX_LET_DEPTH`) | stessa soglia di `MAX_ENV_DEPTH` dei generatori annidati; vale sia per l'annidamento sintattico (parse) sia per la catena di dipendenze in volo (eval) |
| Niente seed-gerarchico | `expr` è deterministico, nessun RNG da decorrelare |
| Memoizzazione per binding | ogni variabile si valuta al più una volta per scope di valutazione; il `_rebuild` finale copia, niente alias con lo scope |

## 3. Punti d'aggancio

| File | Impatto |
|---|---|
| `src/granstudies/expr.py` | `parse_expr_node` ricorsivo sui nodi annidati (guardia sintattica); `_LetScope` (risoluzione lazy, cicli, profondità, memoizzazione); `eval_expr` avvolge lo scope; `_let_error` dà il contesto `let.<nome>` agli errori annidati |
| `src/granstudies/value_generators.py` | solo commento in `expand_env` (il contratto "let statiche" è caduto) |
| `src/granstudies/spread.py` | zero modifiche: l'estrazione delle bande-let e lo scope `{**let, **draws, i, n}` funzionano invariati |
| `src/granstudies/percorso.py`, `yaml_builder.py`, `versions.py` | zero modifiche: passano da `eval_expr`, che risolve da sé |
| `docs/study-yml-reference.md` | regole di scoping nel nodo-expr; nota nella strategy `expr` dello spread |

## 4. Verifica

`tests/test_expr.py`, sezione "expr annidati dentro let": risoluzione di
fratelli, indipendenza dall'ordine, catene, Env calcolati che rientrano
nell'aritmetica e in `mix`, `let` proprio con ombreggiatura ed ereditarietà,
stesso nome a livelli diversi senza falso ciclo, cicli e auto-riferimenti,
guardie di profondità (parse ed eval), errori col nome della variabile,
divieto invariato dei nodi-generatore. Integrazione: `tests/test_spread.py`
(expr annidato che vede `i`, convivenza e referenza delle bande-let, contesto
stream negli errori) e `tests/test_value_generators.py` (`expand_env` con let
annidato, path negli errori di ciclo).
