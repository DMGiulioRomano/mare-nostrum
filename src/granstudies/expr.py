"""Valutatore di espressioni aritmetiche su scalari ed Env (nodo-expr).

Il nodo-expr ``{expr: "...", let: {...}}`` e' una forma di ``Threshold``:
un'espressione aritmetica i cui nomi si risolvono in uno scope di scalari e
forme *statiche* di Env (``[a, b]``, ``[[t, v], ...]``, ``{type, points,
curve}``). Un'operazione tra un Env e uno scalare agisce elementwise sulle y
(i tempi restano intatti); tra due Env e' un errore esplicito — richiederebbe
unione dei breakpoint. L'unica porta Env⊙Env e' la primitiva ``mix(A, B, w)``
(issue #29): il morphing pesato tra due forme, con semantica esplicita di
ricampionamento sull'unione dei tempi (vedi ``_mix``).

Grammatica (whitelist AST, ``mode="eval"``): numeri, nomi, ``+ - * / // % **``,
unario ``-``, parentesi, l'indicizzazione di un corredo ``nome[expr]``, le
chiamate alle funzioni primitive di ``_FUNCTIONS``
(``abs``/``floor``/``ceil``/``sqrt``/``exp``/``log``/``sin``/``cos``/``tan``/
``atan``/``min``/``max``/``mix``/``len``) e le costanti ``pi``/``e`` (ombreggiabili
dallo scope). Una chiamata con un argomento-Env agisce elementwise sulle y
(es. ``min(env, 10)`` e' un clamp); due Env nella stessa chiamata sono un
errore, come per gli operatori — tranne ``mix``, che di due (o tre) Env vive.
Niente confronti o keyword: il parser rifiuta ogni altro costrutto col
frammento incriminato.

Il **corredo** (``{list: [...]}`` in un ``let:``) e' un tipo a parte: una lista
nominata, letta solo per indice. La linea di confine e' dichiarata e stretta —
*una lista non e' mai un valore*: puo' comparire solo come ``nome[expr]`` o
``len(nome)``, non si passa ad altre funzioni, non ci si fa aritmetica, non si restituisce. Cosi' il
tipo di ogni **espressione** resta ``scalare | Env`` e i corredi sono un
namespace di dichiarazione separato.

I valori di ``let`` sono scalari, forme statiche di Env, oppure altri
nodi-expr (issue #28): un nodo annidato si risolve *lazy* alla prima
referenza, contro lo scope che lo contiene — i fratelli dello stesso ``let``
piu' i nomi esterni (``i``/``n``, bande-let, variabili di percorso). L'ordine
di dichiarazione non conta (la risoluzione on-demand e' un ordinamento
topologico implicito); un ``let`` proprio del nodo annidato apre uno scope
figlio lessicale (i nomi interni ombreggiano gli esterni); i cicli sono un
errore esplicito, con guardia di profondita' ``_MAX_LET_DEPTH`` sia
sull'annidamento sintattico (parse) sia sulla catena di dipendenze (eval).

Modulo puro, solo stdlib: chi lo chiama decide lo scope (``expand_env`` passa
il solo ``let``; la strategy di spread aggiunge ``i``, ``n`` e i pescaggi
delle bande-let, estratte a monte del parse) e avvolge i ``ValueError`` col
proprio contesto (path, stream, riga).
"""
from __future__ import annotations

import ast
import math
import operator
from typing import Any, Dict, Mapping, Tuple

_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

# Costanti note alle espressioni; un nome uguale nello scope (``let``) le
# ombreggia.
_CONSTANTS = {"pi": math.pi, "e": math.e}

# Funzioni primitive: nome -> (fn, arieta' minima, arieta' massima o None).
# Il criterio e' il set generatore: da queste si costruiscono le altre
# (tan = sin/cos e' comodita'; asin/acos derivano da atan e sqrt; le basi di
# log da log(x, b); il clamp da min/max annidate).
_FUNCTIONS = {
    "abs": (abs, 1, 1),
    "floor": (math.floor, 1, 1),
    "ceil": (math.ceil, 1, 1),
    "sqrt": (math.sqrt, 1, 1),
    "exp": (math.exp, 1, 1),
    "log": (math.log, 1, 2),
    "sin": (math.sin, 1, 1),
    "cos": (math.cos, 1, 1),
    "tan": (math.tan, 1, 1),
    "atan": (math.atan, 1, 1),
    "min": (min, 2, None),
    "max": (max, 2, None),
    # ``mix`` ha un ramo dedicato in ``_call`` (accetta Env multipli: e'
    # l'unica porta Env⊙Env); qui vive per la whitelist e il check di arieta'.
    "mix": (None, 3, 3),
    # ``len`` ha un ramo dedicato in ``_call``, e per la ragione opposta:
    # accetta **solo** un corredo, che nessun'altra primitiva puo' toccare.
    "len": (None, 1, 1),
}

# Chiavi ammesse nel nodo-expr.
_NODE_KEYS = frozenset({"expr", "let"})

# Il corredo: una lista nominata, dichiarata in un ``let:`` e letta **solo per
# indice**. Vive come dict ``{list: [...]}`` anche dopo la risoluzione — una
# lista non e' un valore, quindi non c'e' niente in cui trasformarla, e la
# forma-dict resta serializzabile nei documenti intermedi.
CORREDO_KEY = "list"

# La politica del corredo. Non e' un flag di comodo: sono due oggetti
# compositivi diversi. Un **accordo** e' un insieme fisso di rapporti — se ne
# chiedi il quinto, la domanda e' sbagliata. Un **pattern** e' periodico per
# natura — il quinto elemento *e'* il primo, come in un ciclo ritmico.
CYCLE_KEY = "cycle"


def is_corredo(v: Any) -> bool:
    """True se ``v`` e' un corredo (dict con chiave ``list``)."""
    return isinstance(v, dict) and CORREDO_KEY in v


def is_cyclic(v: Dict[str, Any]) -> bool:
    """True se il corredo e' un pattern (si avvolge) invece che un accordo."""
    return bool(v.get(CYCLE_KEY))


def corredo_values(v: Dict[str, Any]) -> list:
    """Gli elementi di un corredo gia' risolto."""
    return v[CORREDO_KEY]

# Guardia di profondita' degli expr annidati in ``let`` (issue #28): vale sia
# per l'annidamento sintattico (let dentro let, al parse) sia per la catena di
# dipendenze in risoluzione (all'eval). Stessa soglia di MAX_ENV_DEPTH dei
# generatori annidati: oltre 3 livelli le config sono gia' illeggibili, 8 e'
# puro margine anti-degenerazione.
_MAX_LET_DEPTH = 8


def is_expr_node(spec: Any) -> bool:
    """True se ``spec`` e' un nodo-expr (dict con chiave ``expr``)."""
    return isinstance(spec, dict) and "expr" in spec


def parse_expr_node(
    spec: Dict[str, Any], *, _depth: int = 0
) -> Tuple[str, Dict[str, Any]]:
    """``(testo, let)`` del nodo-expr, validati.

    ``let`` e' opzionale; i suoi valori sono scalari, forme statiche di Env,
    oppure altri nodi-expr (validati qui ricorsivamente, risolti all'eval) —
    un nodo-generatore dentro ``let`` resta un incrocio di meccanismi non
    ammesso (la validazione lo rifiuta come forma non riconosciuta). L'unica
    eccezione vive nella strategy expr dello spread: le bande-let (variabili
    random per-stream) vengono estratte *prima* di chiamare questo parse, che
    vede solo la parte statica di ``let``.
    """
    if _depth > _MAX_LET_DEPTH:
        raise ValueError(
            f"nodo-expr: profondita' di annidamento in 'let' oltre "
            f"{_MAX_LET_DEPTH} — config degenere (alias YAML ricorsivo?)."
        )
    extra = set(spec) - _NODE_KEYS
    if extra:
        raise ValueError(
            f"nodo-expr: chiavi non ammesse {sorted(extra)} (solo expr/let)."
        )
    text = spec["expr"]
    if not isinstance(text, str):
        raise ValueError(
            f"nodo-expr: 'expr' deve essere una stringa (ricevuto {text!r})."
        )
    let = spec.get("let") or {}
    if not isinstance(let, dict):
        raise ValueError(f"nodo-expr: 'let' deve essere un dict (ricevuto {let!r}).")
    for name, value in let.items():
        if is_expr_node(value):
            try:
                parse_expr_node(value, _depth=_depth + 1)
            except ValueError as exc:
                raise _let_error(name, exc) from None
        else:
            _checked(name, value)
    return text, dict(let)


def eval_expr(text: str, scope: Mapping[str, Any]) -> Any:
    """Valuta ``text`` nello ``scope``: scalare o Env (elementwise sulle y).

    I valori di scope che sono nodi-expr si risolvono alla prima referenza
    (vedi ``_LetScope``). Il risultato e' sempre una struttura nuova (niente
    alias con lo scope), con i float arrotondati a 9 decimali come nel resto
    del modulo dei generatori.
    """
    if not isinstance(scope, _LetScope):
        scope = _LetScope(scope)
    return _rebuild(_eval_text(text, scope))


def _eval_text(text: str, scope: "_LetScope") -> Any:
    """Il valore grezzo di ``text`` (senza rebuild: usato anche dai nodi annidati)."""
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"expr: sintassi non valida in {text!r}: {exc.msg}.") from exc
    try:
        return _eval(tree.body, scope)
    except ZeroDivisionError:
        raise ValueError(f"expr: divisione o modulo per zero in {text!r}.") from None


def _let_error(name: str, exc: ValueError) -> ValueError:
    """L'errore di un nodo annidato, col nome della variabile di ``let``."""
    msg = str(exc)
    for prefix in ("expr: ", "nodo-expr: "):
        if msg.startswith(prefix):
            msg = msg[len(prefix):]
            break
    return ValueError(f"expr: let.{name}: {msg}")


class _LetScope:
    """Scope con risoluzione lazy dei nodi-expr legati in ``let`` (issue #28).

    Un valore di scope che e' a sua volta un nodo-expr si valuta alla prima
    referenza, contro lo scope che lo contiene: i fratelli dello stesso
    ``let`` piu' la catena esterna — cosi' l'ordine di dichiarazione non
    conta (la risoluzione on-demand e' un ordinamento topologico implicito)
    e i nomi dinamici iniettati dai chiamanti (``i``/``n``, bande-let,
    variabili di percorso) restano visibili. Un ``let`` proprio del nodo
    annidato apre uno scope figlio, lessicale: i nomi interni ombreggiano
    gli esterni. Lo stack di risoluzione, condiviso lungo la catena, rileva
    i cicli — la chiave e' il binding ``(scope, nome)``, non il solo nome,
    cosi' l'ombreggiatura tra livelli diversi non produce falsi cicli — e
    fa da guardia di profondita' sulla catena di dipendenze. I risultati
    sono memoizzati per binding.
    """

    def __init__(
        self, bindings: Mapping[str, Any], parent: "_LetScope | None" = None
    ):
        self._bindings = bindings
        self._parent = parent
        self._cache: Dict[str, Any] = {}
        self._stack: list = parent._stack if parent is not None else []

    def __contains__(self, name: object) -> bool:
        return name in self._bindings or (
            self._parent is not None and name in self._parent
        )

    def __iter__(self):
        # L'unione dei nomi visibili, per gli elenchi nei messaggi d'errore.
        yield from self._bindings
        if self._parent is not None:
            for name in self._parent:
                if name not in self._bindings:
                    yield name

    def __getitem__(self, name: str) -> Any:
        if name not in self._bindings:
            if self._parent is None:
                raise KeyError(name)
            return self._parent[name]
        if name in self._cache:
            return self._cache[name]
        value = self._bindings[name]
        if is_expr_node(value):
            value = self._resolve(name, value)
        self._cache[name] = value
        return value

    def _resolve(self, name: str, node: Dict[str, Any]) -> Any:
        key = (id(self), name)
        if key in self._stack:
            chain = [n for _, n in self._stack[self._stack.index(key):]]
            chain.append(name)
            raise ValueError(f"expr: ciclo nel let ({' -> '.join(chain)}).")
        if len(self._stack) >= _MAX_LET_DEPTH:
            chain = " -> ".join([n for _, n in self._stack] + [name])
            raise ValueError(
                f"expr: profondita' della catena di let oltre {_MAX_LET_DEPTH} "
                f"({chain}) — config degenere."
            )
        self._stack.append(key)
        try:
            text, let = parse_expr_node(node)
            return _eval_text(text, _LetScope(let, parent=self))
        except ValueError as exc:
            raise _let_error(name, exc) from None
        finally:
            self._stack.pop()


def _is_scalar(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _is_pairs(v: Any) -> bool:
    """True se ``v`` e' una lista di breakpoint ``[[t, y], ...]`` numerici."""
    return (
        isinstance(v, (list, tuple))
        and len(v) > 0
        and all(
            isinstance(p, (list, tuple)) and len(p) == 2
            and _is_scalar(p[0]) and _is_scalar(p[1])
            for p in v
        )
    )


def _checked(name: str, v: Any) -> Any:
    """Il valore di scope ``name``, se ha una forma ammessa.

    Ammette anche i corredi: sono binding legittimi (l'iniezione per nome li
    mette negli scope ``let`` come ogni altra manopola). E' ``_eval`` sul nome
    nudo a rifiutarli — un corredo si legge solo per indice.
    """
    if _is_scalar(v):
        return v
    if is_corredo(v):
        return _checked_corredo(name, v)
    if _is_pairs(v):
        return v
    if (
        isinstance(v, (list, tuple)) and len(v) == 2
        and _is_scalar(v[0]) and _is_scalar(v[1])
    ):
        return v
    if isinstance(v, dict) and _is_pairs(v.get("points")):
        return v
    raise ValueError(
        f"expr: '{name}' ha una forma non riconosciuta ({v!r}) — in scope "
        "solo scalari, forme statiche di Env o corredi (niente "
        "nodi-generatore)."
    )


def _checked_corredo(name: str, v: Dict[str, Any]) -> Dict[str, Any]:
    """Un corredo in scope, se e' gia' risolto e ben formato.

    La validazione alla *dichiarazione* vive in ``value_generators``, dove ci
    sono le coordinate dello YAML; qui si controlla solo cio' che serve a non
    valutare su una struttura rotta — un corredo puo' arrivare in scope anche
    scritto a mano nel ``let`` di un nodo-expr.
    """
    elems = v[CORREDO_KEY]
    if isinstance(elems, dict):
        raise ValueError(
            f"expr: il corredo '{name}' non e' stato generato — un corredo con "
            "un generatore dentro 'list' si dichiara in un 'let:' di documento "
            "o di gruppo, che lo risolve al load; qui arriva gia' fatto."
        )
    if not isinstance(elems, list) or not elems:
        raise ValueError(
            f"expr: il corredo '{name}' e' vuoto o malformato ({v!r}) — "
            "'list' vuole una lista non vuota."
        )
    if not all(_is_scalar(x) for x in elems):
        raise ValueError(
            f"expr: il corredo '{name}' contiene elementi non scalari — "
            "i corredi di sagome sono fuori dalla v1 (issue #44)."
        )
    if CYCLE_KEY in v and not isinstance(v[CYCLE_KEY], bool):
        raise ValueError(
            f"expr: il corredo '{name}': '{CYCLE_KEY}' vuole true o false "
            f"(ricevuto {v[CYCLE_KEY]!r})."
        )
    return v


def _map_y(env: Any, fn) -> Any:
    """L'Env con ``fn`` applicata a ogni y, tempi e forma intatti."""
    if isinstance(env, dict):
        return {**env, "points": [[t, fn(y)] for t, y in env["points"]]}
    if _is_pairs(env):
        return [[t, fn(y)] for t, y in env]
    a, b = env  # shorthand [a, b]
    return [fn(a), fn(b)]


def _eval(node: ast.AST, scope: Mapping[str, Any]) -> Any:
    if isinstance(node, ast.Constant):
        if not _is_scalar(node.value):
            raise ValueError(f"expr: costante non numerica {node.value!r}.")
        return node.value
    if isinstance(node, ast.Name):
        if node.id in scope:
            v = _checked(node.id, scope[node.id])
            if is_corredo(v):
                # La linea di confine della grammatica: una lista non e' mai un
                # valore. Puo' comparire solo come ``nome[expr]``.
                raise ValueError(
                    f"expr: '{node.id}' e' un corredo — si legge solo per "
                    f"indice ('{node.id}[0]'), non come valore: non si passa "
                    "a una funzione, non ci si fa aritmetica."
                )
            return v
        if node.id in _CONSTANTS:
            return _CONSTANTS[node.id]
        names = ", ".join(sorted(set(scope) | set(_CONSTANTS))) or "nessuno"
        raise ValueError(
            f"expr: nome ignoto '{node.id}' (disponibili: {names})."
        )
    if isinstance(node, ast.Subscript):
        return _subscript(node, scope)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        v = _eval(node.operand, scope)
        if isinstance(node.op, ast.UAdd):
            return v
        return _map_y(v, operator.neg) if not _is_scalar(v) else -v
    if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
        op = _BINOPS[type(node.op)]
        left = _eval(node.left, scope)
        right = _eval(node.right, scope)
        left_env, right_env = not _is_scalar(left), not _is_scalar(right)
        if left_env and right_env:
            raise ValueError(
                "expr: operazione tra due Env non supportata "
                "(solo Env con scalare)."
            )
        if left_env:
            return _map_y(left, lambda y: op(y, right))
        if right_env:
            return _map_y(right, lambda y: op(left, y))
        return op(left, right)
    if isinstance(node, ast.Call):
        return _call(node, scope)
    raise ValueError(
        f"expr: costrutto non ammesso {ast.unparse(node)!r} "
        "(solo numeri, nomi, + - * / // % **, funzioni primitive, parentesi)."
    )


def _len(node: ast.Call, scope: Mapping[str, Any]) -> int:
    """``len(nome)``: la lunghezza di un corredo. Solo di un corredo.

    ``len`` di un envelope dev'essere errore, non «quanti breakpoint ha»:
    quello e' un dettaglio di rappresentazione — ``expand_env`` puo' produrne
    un numero diverso a parita' di intenzione — e farlo trapelare renderebbe
    le espressioni dipendenti dall'implementazione.
    """
    if node.keywords:
        raise ValueError(
            "expr: 'len' non accetta argomenti keyword (solo posizionali)."
        )
    if len(node.args) != 1:
        raise ValueError(
            f"expr: 'len' vuole 1 argomento (ricevuti {len(node.args)})."
        )
    arg = node.args[0]
    if not isinstance(arg, ast.Name):
        raise ValueError(
            f"expr: 'len' accetta solo un corredo per nome, non "
            f"{ast.unparse(arg)!r}."
        )
    name = arg.id
    if name not in scope:
        names = ", ".join(sorted(set(scope) | set(_CONSTANTS))) or "nessuno"
        raise ValueError(f"expr: nome ignoto '{name}' (disponibili: {names}).")
    v = _checked(name, scope[name])
    if not is_corredo(v):
        raise ValueError(
            f"expr: 'len' vuole un corredo, ma '{name}' e' "
            f"{'un envelope' if not _is_scalar(v) else 'uno scalare'} "
            f"({v!r}) — la lunghezza di un envelope e' un dettaglio di "
            "rappresentazione, non un fatto del linguaggio."
        )
    return len(corredo_values(v))


def _subscript(node: ast.Subscript, scope: Mapping[str, Any]) -> Any:
    """``nome[expr]``: l'elemento di un corredo.

    La base e' un **nome**, non un'espressione qualunque: una lista non e' mai
    un valore, quindi non c'e' niente altro che possa produrne una. L'indice
    invece e' un'espressione libera, purche' valuti a un intero — un indice
    frazionario e' errore, la quantizzazione si scrive con ``//`` o ``floor``.
    """
    if not isinstance(node.value, ast.Name):
        raise ValueError(
            f"expr: si indicizza solo un corredo per nome, non "
            f"{ast.unparse(node.value)!r} — una lista non e' mai un valore."
        )
    name = node.value.id
    if name not in scope:
        names = ", ".join(sorted(set(scope) | set(_CONSTANTS))) or "nessuno"
        raise ValueError(f"expr: nome ignoto '{name}' (disponibili: {names}).")
    corredo = _checked(name, scope[name])
    if not is_corredo(corredo):
        raise ValueError(
            f"expr: '{name}' non e' un corredo, non si puo' indicizzare "
            f"({corredo!r}) — l'indicizzazione legge le liste dichiarate con "
            "'list:' in un 'let:'."
        )
    return _element(name, corredo, _eval(node.slice, scope))


def _element(name: str, corredo: Dict[str, Any], idx: Any) -> Any:
    """L'elemento di ``corredo`` all'indice ``idx``, validato."""
    if not _is_scalar(idx):
        raise ValueError(
            f"expr: l'indice di '{name}' non e' un numero ({idx!r}) — un Env "
            "non indicizza."
        )
    if isinstance(idx, float):
        if not idx.is_integer():
            raise ValueError(
                f"expr: l'indice di '{name}' non e' intero ({idx}) — fra due "
                "elementi non c'e' niente. Quantizza con '//' o 'floor()'."
            )
        idx = int(idx)
    elems = corredo_values(corredo)
    size = len(elems)
    if is_cyclic(corredo):
        # Un pattern e' periodico per natura: il quinto elemento *e'* il primo.
        # Il modulo di Python porta con se' i negativi gratis (``-1 % 4 == 3``),
        # quindi il senso di lettura invertito resta coerente.
        return elems[idx % size]
    # Indici negativi: ``ratio[-1]`` e' l'ultimo. Servono a invertire il senso
    # di lettura del corredo.
    pos = idx + size if idx < 0 else idx
    if not 0 <= pos < size:
        raise ValueError(
            f"expr: indice {idx} fuori dal corredo '{name}', che ha {size} "
            f"elementi (indici 0..{size - 1} dall'inizio, -1..-{size} dalla "
            f"fine) — e' un accordo, un insieme fisso. Per un pattern che si "
            f"ripete dichiara '{CYCLE_KEY}: true' accanto a 'list'."
        )
    return elems[pos]


def _call(node: ast.Call, scope: Mapping[str, Any]) -> Any:
    """Una chiamata a funzione primitiva, elementwise se un argomento e' Env."""
    if not isinstance(node.func, ast.Name) or node.func.id not in _FUNCTIONS:
        got = ast.unparse(node.func)
        names = ", ".join(sorted(_FUNCTIONS))
        raise ValueError(f"expr: funzione ignota '{got}' (disponibili: {names}).")
    name = node.func.id
    if node.keywords:
        raise ValueError(
            f"expr: '{name}' non accetta argomenti keyword (solo posizionali)."
        )
    fn, lo, hi = _FUNCTIONS[name]
    if name == "len":
        # Prima della valutazione degli argomenti: ``_eval`` su un nome-corredo
        # e' errore (una lista non e' un valore), e ``len`` e' l'unica funzione
        # che di un corredo vive.
        return _len(node, scope)
    args = [_eval(a, scope) for a in node.args]
    count = len(args)
    if count < lo or (hi is not None and count > hi):
        span = str(lo) if hi == lo else (f"{lo}-{hi}" if hi else f"almeno {lo}")
        raise ValueError(
            f"expr: '{name}' vuole {span} argomenti (ricevuti {count})."
        )
    if name == "mix":
        return _mix(*args)

    def apply(*xs):
        try:
            return fn(*xs)
        except (ValueError, OverflowError):
            frag = ", ".join(repr(x) for x in xs)
            raise ValueError(f"expr: {name}({frag}) fuori dominio.") from None

    env_pos = [k for k, a in enumerate(args) if not _is_scalar(a)]
    if not env_pos:
        return apply(*args)
    if len(env_pos) > 1:
        raise ValueError(
            "expr: operazione tra due Env non supportata (solo Env con scalare)."
        )
    (k,) = env_pos

    def on_y(y):
        xs = list(args)
        xs[k] = y
        return apply(*xs)

    return _map_y(args[k], on_y)


# --- mix(A, B, w): il morphing tra due forme (issue #29) ----------------------
#
# L'unica porta Env⊙Env del DSL: ricampiona A e B sull'unione dei tempi e
# interpola le y col peso ``w`` (che puo' essere a sua volta un Env). Fast-path
# esatti dove il risultato e' rappresentabile senza perdita (linear/linear con
# w scalare; step/step; w-Env su forme scalari); altrove campionamento
# adattivo con suddivisione ricorsiva al punto medio. Niente clamp su ``w``
# (l'estrapolazione e' legittima; il clamp si scrive con min/max).

# Tolleranza del campionamento adattivo, frazione dell'escursione del
# risultato: sotto e' inudibile e i breakpoint restano pochi e leggibili.
_MIX_REL_TOL = 1e-3

# Guardia anti-degenerazione della suddivisione ricorsiva: 2**12 punti per
# segmento bastano a qualunque forma sensata (errore di configurazione, non
# caso d'uso — stessa filosofia di MAX_RAMP_POINTS nei generatori).
_MIX_MAX_DEPTH = 12


def _mix_form(v: Any) -> Tuple[str, Any, float]:
    """``(kind, data, curve)`` di un argomento di mix.

    ``kind``: ``scalar`` (data = valore) | ``linear`` | ``step`` (data =
    breakpoint ordinati per tempo). Le forme sono quelle statiche di Env gia'
    ammesse in scope; ``type`` fuori da linear/step non e' campionabile qui
    (le forme future dell'engine entreranno con la loro semantica, non con
    una inventata).
    """
    if _is_scalar(v):
        return "scalar", v, 1.0
    if isinstance(v, dict):
        kind = v.get("type", "linear")
        curve = v.get("curve", 1.0)
        pts = sorted(v["points"], key=lambda p: p[0])
        if kind == "step":
            if curve != 1.0:
                raise ValueError(
                    "expr: mix, 'curve' non ha effetto con 'type: step' "
                    "(nessuna rampa da piegare)."
                )
            return "step", pts, 1.0
        if kind != "linear":
            raise ValueError(
                f"expr: mix, type '{kind}' non campionabile (linear | step)."
            )
        if curve <= 0:
            raise ValueError(
                f"expr: mix, curve deve essere > 0 (ricevuto {curve})."
            )
        return "linear", pts, curve
    if _is_pairs(v):
        return "linear", sorted(([t, y] for t, y in v), key=lambda p: p[0]), 1.0
    a, b = v  # shorthand [a, b] == [[0, a], [1, b]]
    return "linear", [[0.0, a], [1.0, b]], 1.0


def _form_at(form: Tuple[str, Any, float], t: float) -> float:
    """La forma campionata al tempo ``t``, con hold fuori dai bordi.

    Stessa semantica di ``_interp_breakpoints`` in ``value_generators``
    (linear con piega ``u**curve``, step hold-sinistro): logica duplicata
    perche' e' ``value_generators`` a importare questo modulo, non viceversa
    (come il deep-merge locale di ``spread``).
    """
    kind, data, curve = form
    if kind == "scalar":
        return data
    pts = data
    if t <= pts[0][0]:
        return pts[0][1]
    if t >= pts[-1][0]:
        return pts[-1][1]
    for (t0, v0), (t1, v1) in zip(pts, pts[1:]):
        if t0 <= t <= t1:
            if kind == "step" or t1 == t0:
                return v0
            u = (t - t0) / (t1 - t0)
            if curve != 1.0:
                u = u ** curve
            return v0 + (v1 - v0) * u
    return pts[-1][1]  # irraggiungibile: t e' tra primo e ultimo tempo


def _mix(a: Any, b: Any, w: Any) -> Any:
    """``A*(1-w) + B*w``: morphing pesato tra due forme.

    Tre scalari -> lerp scalare. Con Env in gioco le forme devono abitare lo
    stesso mondo: tutte step (il risultato e' step sull'unione dei tempi,
    esatto) o tutte continue (linear/curve). Nel continuo il risultato e'
    esatto sull'unione dei tempi quando resta piecewise-linear (``curve == 1``
    ovunque e nessun prodotto Env×Env: ``w`` scalare, oppure ``w``-Env su A e
    B scalari); altrimenti campionamento adattivo (``_mix_adaptive``). Step
    dentro morphing continuo = discontinuita' pesata, fuori dal v1: errore
    esplicito, nessuna semantica inventata.
    """
    forms = [_mix_form(x) for x in (a, b, w)]
    kinds = {kind for kind, _, _ in forms if kind != "scalar"}
    if not kinds:
        return a + (b - a) * w
    if "step" in kinds and "linear" in kinds:
        raise ValueError(
            "expr: mix tra una forma step e una continua non e' supportato "
            "(discontinuita' pesata, fuori dal v1) — dichiara le forme "
            "entrambe step o entrambe continue."
        )

    def value(t: float) -> float:
        va = _form_at(forms[0], t)
        vb = _form_at(forms[1], t)
        vw = _form_at(forms[2], t)
        return va + (vb - va) * vw

    times = sorted({
        t for kind, data, _ in forms if kind != "scalar" for t, _ in data
    })
    if kinds == {"step"}:
        return {"type": "step", "points": [[t, value(t)] for t in times]}
    exact = all(
        curve == 1.0 for kind, _, curve in forms if kind == "linear"
    ) and (
        forms[2][0] == "scalar"
        or (forms[0][0] == "scalar" and forms[1][0] == "scalar")
    )
    if exact or len(times) < 2:
        return [[t, value(t)] for t in times]
    return _mix_adaptive(value, times)


def _mix_adaptive(value, times: list) -> list:
    """Breakpoint lineari adattivi di ``value`` sui segmenti di ``times``.

    Suddivisione ricorsiva al punto medio finche' lo scarto della corda,
    misurato al punto medio, scende sotto tolleranza (il caso peggiore per
    segmento e' una parabola — i prodotti di forme lineari — e li' lo scarto
    massimo cade esattamente al punto medio). Tolleranza proporzionale
    all'escursione stimata campionando tempi e punti medi di partenza. La
    tabella di campionamento e' locale e temporanea: l'output resta un Env
    simbolico a pochi breakpoint, leggibile nei pannelli envelope.
    """
    samples = [(t, value(t)) for t in times]
    mids = [
        ((t0 + t1) / 2, value((t0 + t1) / 2))
        for (t0, _), (t1, _) in zip(samples, samples[1:])
    ]
    ys = [y for _, y in samples] + [y for _, y in mids]
    span = max(ys) - min(ys)
    tol = max(span * _MIX_REL_TOL, 1e-9)
    out = [samples[0]]

    def refine(t0, y0, t1, y1, depth):
        tm = (t0 + t1) / 2
        ym = value(tm)
        if abs(ym - (y0 + y1) / 2) <= tol or depth >= _MIX_MAX_DEPTH:
            out.append((t1, y1))
            return
        refine(t0, y0, tm, ym, depth + 1)
        refine(tm, ym, t1, y1, depth + 1)

    for (t0, y0), (t1, y1) in zip(samples, samples[1:]):
        refine(t0, y0, t1, y1, 0)
    return [[t, y] for t, y in out]


def _rebuild(v: Any) -> Any:
    """Copia del risultato con i float arrotondati a 9 decimali."""
    if isinstance(v, complex):
        raise ValueError(
            "expr: risultato complesso (potenza frazionaria di un negativo?) "
            "— le espressioni producono solo reali."
        )
    if isinstance(v, float):
        return round(v, 9)
    if isinstance(v, int):
        return v
    if isinstance(v, dict):
        return {**v, "points": [[_rebuild(t), _rebuild(y)] for t, y in v["points"]]}
    return [_rebuild(x) for x in v]
