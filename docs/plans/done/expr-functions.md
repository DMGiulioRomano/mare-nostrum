# Piano — funzioni primitive e operatori interi nel mini-linguaggio `expr`

**Repo:** `granulation-studies` (branch `claude/study-yml-granulation-vars-d510k0`)
**Stato:** completato. Lingua: italiano, no emoji.

---

## 1. Intento

Estendere la grammatica di `expr` oltre l'aritmetica di base: resto e
quoziente intero (`%`, `//`) e le chiamate a un set di **funzioni primitive**
da cui costruire le altre. Casi d'uso concreti:

```yaml
# griglia dall'indice dello spread: colonna = i % 3, riga = i // 3
base.onset:
  expr: "4 * (i % 3) + 2 * (i // 3)"

# clamp di un pescaggio: mai sotto -14
base.volume:
  expr: "max(v - 2 * i, -14)"
  let:
    v: {base: -3, range: 3}

# quantizzazione e curve
grain.duration:
  expr: "0.002 * floor(env * 5)"
```

## 2. Decisioni fissate

| Decisione | Rationale |
|---|---|
| Operatori nuovi: `%` (semantica Python, segno del divisore) e `//` | con `i` trasformano l'indice in coordinate di griglia; `divmod` a mano |
| Whitelist funzioni: `abs floor ceil sqrt exp log sin cos tan atan min max` | set generatore: `tan` è comodità, `asin`/`acos` derivano da `atan`+`sqrt`, le basi di `log` da `log(x, b)`, il clamp da `min`/`max` |
| Costanti `pi` / `e`, ombreggiabili dallo scope (`let` vince) | servono per trig e curve exp; lo shadowing esplicito non sorprende |
| Chiamata con un argomento-Env → elementwise sulle y, due Env → errore | stessa regola degli operatori binari, nessuna nuova semantica |
| Arietà validata per funzione (`log` 1-2, `min`/`max` >= 2, il resto 1) | errore chiaro al parse-time invece del TypeError di Python |
| Fuori dominio (`sqrt(-1)`, `log(0)`, overflow) → `ValueError` col frammento | i `ValueError` risalgono le seam esistenti (path, stream, riga) |
| Risultato complesso (potenza frazionaria di negativo) → errore esplicito | prima era un `TypeError` grezzo in `_rebuild` (bug pre-esistente) |
| Niente keyword, subscript, confronti, starred | superficie minima, il fallback della whitelist li rifiuta già |

## 3. Punti d'aggancio

| File | Impatto |
|---|---|
| `src/granstudies/expr.py` | `_BINOPS` + `Mod`/`FloorDiv`; tabelle `_CONSTANTS` e `_FUNCTIONS`; `_call` (arietà, elementwise, dominio); guardia complessi in `_rebuild` |
| tutto il resto | zero modifiche: ogni consumatore passa da `eval_expr`, la novità vale ovunque il nodo-expr già valeva (assi, parametri statici, strategy expr dello spread, bande-let) |
| `docs/study-yml-reference.md` | grammatica e tabella funzioni nella sezione del nodo-expr |
| `studies/study_expr_test/study.yml` | uso 5: griglia da `%`/`//` e clamp con `max` |

## 4. Verifica

`tests/test_expr.py`: operatori (`%`, `//`, modulo per zero, elementwise su
Env), funzioni (arrotondamenti, `sqrt`/`exp`/`log`, trig e costanti,
shadowing, `min`/`max`, chiamate annidate, Env mappato sulle y, clamp,
forma dict preservata) ed errori (funzione ignota con elenco, arietà,
keyword, dominio, due Env, starred, risultato complesso).
`tests/test_spread.py`: griglia 3x2 da `%`/`//` e clamp su banda-let.
Suite intera verde.
