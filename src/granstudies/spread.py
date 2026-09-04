"""Espansione delle entry-spread di ``streams:`` (macro-forma).

Una entry di ``streams:`` con la chiave riservata ``spread`` non descrive un
solo stream ma ne genera ``n``, distribuendo i valori di uno o piu' parametri
(path puntati nel documento, es. ``base.pointer.start``) secondo una strategy
del vocabolario Y (``values`` / ``ramp`` / banda ``base``). E' l'asse mancante
del sistema: Y distribuisce valori nel tempo (micro-forma), la camminata-X
distribuisce i tempi, spread distribuisce valori nella popolazione di stream
(macro-forma) — stesso vocabolario, asse diverso.

Puro pre-processing: ``resolve_streams`` chiama ``expand_spreads`` prima del
loop di deep-merge, tutto il resto della pipeline vede entry ordinarie. Lo
``study.yml`` sorgente non viene mai riscritto.

Il blocco ``spread:`` puo' anche stare al top-level del documento (sibling di
``base:``/``axes:``/``sweep:``, issue #34): e' il default che ogni entry con
la chiave ``spread`` eredita via deep-merge prima dell'espansione — lo stesso
meccanismo con cui ``sweep: {}`` riattiva il blocco ``sweep:`` globale.
L'attivazione resta esplicita: una entry senza chiave ``spread`` non espande
nulla, anche col blocco globale presente.
"""
from __future__ import annotations

import copy
from math import ceil, log10
from typing import Any, Dict, List, Tuple

from . import bounds as bounds_mod
from .errors import ErrCtx, SpecError
from .expr import eval_expr, is_corredo, is_expr_node, parse_expr_node
from .group_let import apply_group_let
from .inject import inject
from .value_generators import (
    Y_GENERATOR_KEYS,
    _threshold_at,
    band,
    expand_params,
    is_generator_node,
    ramp,
    stable_seed,
    y_generator,
)
from .yaml_loc import Locations

# Chiavi ammesse nel blocco ``spread:``.
_SPREAD_KEYS = frozenset({"n", "over", "let"})

# Chiavi ammesse in una banda-let della strategy expr: la banda di sempre,
# senza ``n`` (il conteggio e' dello spread).
_LET_BAND_KEYS = frozenset({"base", "range", "seed", "distribution", "drift"})

# Marcatori che aprono una strategy dentro ``over[path]``. Una chiave puntata
# di ``over`` che termina con uno di questi (``base.pointer.start.values``)
# viene splittata in ``{path: {marcatore: valore}}`` — la stessa espansione a
# punti che gli override di stream hanno via ``study_spec._expand_dotted_keys``.
# ponytail: i path di ``over`` puntano a ``base.*``/assi e non terminano con
# questi nomi; la collisione (un path che finisce davvero in ``base``/``seed``/
# ...) non si dà nel dominio — se servisse, si scrive la forma annidata.
_STRATEGY_MARKERS = Y_GENERATOR_KEYS | _LET_BAND_KEYS | frozenset({"expr", "let", "n"})

# Default iniettato nei generati quando l'entry non dichiara ``sweep:``: gli
# stream di uno spread vivono solo nello stack (ascolto verticale), non
# moltiplicano le varianti di sweep.
_SWEEP_OFF = {"orders": [], "orderings": []}


# Blocchi i cui figli diretti sono nomi d'asse: il primo identificatore di un
# path puntato li' sotto puo' essere dotted (asse 'grain.duration' senza
# 'path', issue #32) e il suo confine va risolto, non spezzato su ogni punto.
AXIS_NAME_BLOCKS = ("axes", "stack")


def split_axis_key(
    dotted_key: str,
    axis_names: frozenset,
    ctx: ErrCtx | None = None,
) -> Tuple[str, List[str]]:
    """Trova il confine del nome d'asse in una chiave dotted sotto axes/stack.

    ``"grain.duration.values"`` con asse ``grain.duration`` dichiarato ->
    ``("grain.duration", ["values"])``. Precedenza: (1) match sugli assi
    dichiarati nel documento base; (2) match sul registro parametri engine
    (``bounds.known_paths``), che permette a un override di *introdurre* un
    asse dotted non ancora dichiarato; (3) fallback sintattico al primo
    segmento (comportamento storico, copre chiavi riservate come
    ``interpolation``/``seed`` e gli alias senza punto). Piu' match nello
    stesso livello di precedenza — es. assi ``grain`` e ``grain.duration``
    entrambi dichiarati — sono indecidibili: errore esplicito, mai scelta
    silenziosa.
    """
    segs = dotted_key.split(".")
    spans = range(1, len(segs) + 1)
    for candidates in (
        [j for j in spans if ".".join(segs[:j]) in axis_names],
        [j for j in spans if ".".join(segs[:j]) in bounds_mod.known_paths()],
    ):
        if len(candidates) > 1:
            names = [".".join(segs[:j]) for j in candidates]
            err_kwargs = dict(
                key=("streams",),
                hint="usa la forma annidata (axes: {<nome.asse>: {...}}) "
                "per sciogliere l'ambiguita'.",
            )
            msg = (
                f"chiave puntata '{dotted_key}' ambigua: il nome d'asse "
                f"puo' essere {' o '.join(repr(n) for n in names)}."
            )
            raise ctx.err(msg, **err_kwargs) if ctx else SpecError(msg, **err_kwargs)
        if candidates:
            j = candidates[0]
            return ".".join(segs[:j]), segs[j:]
    return segs[0], segs[1:]


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Stessa semantica del deep-merge di ``study_spec`` (copia locale: e'
    ``study_spec`` a importare questo modulo, non viceversa)."""
    result = dict(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def _deep_set(
    target: Dict[str, Any],
    dotted: str,
    value: Any,
    axis_names: frozenset = frozenset(),
    ctx: ErrCtx | None = None,
) -> None:
    """Imposta ``value`` al path puntato, creando i dict intermedi.

    Un intermedio non-dict viene rimpiazzato: la strategy vince sull'override
    comune, come l'override vince sulla base nel deep-merge delle stream.
    Sotto ``axes.``/``stack.`` il primo identificatore e' un nome d'asse
    (eventualmente dotted): il confine e' risolto da ``split_axis_key``.
    """
    keys = dotted.split(".")
    if keys[0] in AXIS_NAME_BLOCKS and len(keys) > 1:
        axis, rest = split_axis_key(".".join(keys[1:]), axis_names, ctx)
        keys = [keys[0], axis, *rest]
    node = target
    for k in keys[:-1]:
        if not isinstance(node.get(k), dict):
            node[k] = {}
        node = node[k]
    node[keys[-1]] = value


def _let_band(path: str, var: str, node: Dict[str, Any], ctx: ErrCtx) -> Dict[str, Any]:
    """Parametri-banda di una variabile random di ``let`` (strategy expr).

    Un nodo-generatore dentro ``let`` e' ammesso solo qui, e solo nella forma
    banda: un pescaggio per stream generato, che entra nello scope
    dell'espressione accanto a ``i`` e ``n``. ``values``/``ramp`` restano
    fuori: una progressione deterministica si scrive con l'aritmetica su i/n.
    """
    key = ("spread", "over", path)
    markers = sorted(Y_GENERATOR_KEYS & set(node))
    if markers != ["base"]:
        raise ctx.err(
            f"spread: expr sul path '{path}', 'let.{var}' usa {markers} — "
            "in 'let' l'unico generatore ammesso e' la banda ('base').",
            key=key,
            hint="la banda pesca un valore per stream; per una progressione "
            "deterministica usa l'aritmetica su i/n nell'espressione.",
        )
    if "n" in node:
        raise ctx.err(
            f"spread: expr sul path '{path}', 'let.{var}' dichiara 'n' — "
            "il conteggio e' dello spread, la banda-let pesca da sola un "
            "valore per stream.",
            key=key,
        )
    extra = set(node) - _LET_BAND_KEYS
    if extra:
        raise ctx.err(
            f"spread: expr sul path '{path}', 'let.{var}', chiavi non "
            f"ammesse {sorted(extra)} (solo {sorted(_LET_BAND_KEYS)}).",
            key=key,
        )
    return dict(node)


def _strategy(name: str, path: str, cfg: Any, ctx: ErrCtx) -> tuple:
    """(marcatore canonico, params) della strategy di un path di ``over``."""
    key = ("spread", "over", path)
    if not isinstance(cfg, dict):
        raise ctx.err(
            f"spread: il path '{path}' deve avere una strategy (dict), "
            f"trovato {cfg!r}.",
            key=key,
            hint="dichiara 'values', 'ramp', una banda ('base'/'range'/'seed') "
            "o un'espressione ('expr').",
        )
    if is_corredo(cfg):
        raise ctx.err(
            f"spread: il path '{path}' dichiara un corredo — un corredo non e' "
            "una strategy: si dichiara in un 'let:' e si legge per indice.",
            key=key,
            hint="per un valore per voce scritto a mano usa 'values'; per "
            "leggere un corredo, dichiaralo nel 'let:' di gruppo e usa "
            "\"{expr: 'ratio[i]'}\".",
        )
    if "expr" in cfg:
        # Quarta strategy, locale allo spread (fuori dal vocabolario Y: e'
        # l'unico posto dove esiste un indice ``i`` su cui fare aritmetica).
        markers = sorted(Y_GENERATOR_KEYS & set(cfg))
        if markers:
            raise ctx.err(
                f"spread: il path '{path}' mescola 'expr' con {markers} — "
                "esattamente una strategy per path.",
                key=key,
            )
        # Le bande-let (variabili random per-stream) si estraggono prima del
        # parse: ``parse_expr_node`` valida solo la parte statica di ``let``.
        node = cfg
        rand_let: Dict[str, Dict[str, Any]] = {}
        if isinstance(cfg.get("let"), dict):
            rand_let = {
                var: _let_band(path, var, v, ctx)
                for var, v in cfg["let"].items()
                if is_generator_node(v)
            }
            if rand_let:
                static = {k: v for k, v in cfg["let"].items() if k not in rand_let}
                node = {**cfg, "let": static}
        with ctx.wrapping(key=key):
            text, let = parse_expr_node(node)
        return "expr", (text, let, rand_let)
    with ctx.wrapping(
        key=key,
        hint="ogni path di 'over' vuole esattamente una strategy tra "
        "'values', 'ramp', banda ('base') ed 'expr'.",
    ):
        return y_generator(cfg)


def _ramp_form(path: str, params: Dict[str, Any], ctx: ErrCtx) -> str:
    """Forma del ramp di uno spread: ``full`` | ``step`` | ``stop``.

    ``{start, stop, step}`` e' il ramp pieno degli assi (possiede il
    conteggio); le forme parziali lasciano ``n`` allo spread: ``{start, step}``
    e' la progressione aritmetica (l'offset additivo), ``{start, stop}`` la
    suddivisione lineare in ``n`` punti.
    """
    key = ("spread", "over", path)
    extra = set(params) - {"start", "stop", "step"}
    if extra:
        raise ctx.err(
            f"spread: ramp sul path '{path}', chiavi non ammesse "
            f"{sorted(extra)} (solo start/stop/step).",
            key=key,
        )
    if "start" not in params:
        raise ctx.err(
            f"spread: ramp sul path '{path}' senza 'start'.",
            key=key,
        )
    has_stop, has_step = "stop" in params, "step" in params
    if has_stop and has_step:
        return "full"
    if has_step:
        return "step"
    if has_stop:
        return "stop"
    raise ctx.err(
        f"spread: ramp sul path '{path}' con solo 'start' — serve almeno "
        "'step' (progressione aritmetica) o 'stop' (suddivisione su n).",
        key=key,
    )


def _owned_count(
    name: str, path: str, marker: str, params: Any, ctx: ErrCtx
) -> int | None:
    """Conteggio posseduto dalla strategy, se lo possiede.

    ``values`` possiede la propria lunghezza; il ramp pieno la sua griglia;
    la banda solo se dichiara ``n`` proprio. Le forme parziali di ramp e la
    banda senza ``n`` lasciano il conteggio allo spread.
    """
    if marker == "values":
        return len(params)
    if marker == "ramp" and _ramp_form(path, params, ctx) == "full":
        return len(_ramp_full(name, path, params, ctx))
    if marker == "band" and "n" in params:
        return params["n"]
    return None


def _ramp_full(
    name: str, path: str, params: Dict[str, Any], ctx: ErrCtx
) -> List[float]:
    """Griglia del ramp pieno, con i nodi-generatore di ``step`` gia' espansi."""
    with ctx.wrapping(key=("spread", "over", path)):
        seed = stable_seed(f"{name}:spread:{path}")
        return ramp(**expand_params(params, seed=seed))


def _spread_n(raw: Any, ctx: ErrCtx) -> Any:
    """``spread.n`` normalizzato: il valore com'e', o il nodo-expr valutato.

    Il nodo-expr (percorso-v1, issue #29) rende ``n`` funzione delle variabili
    del percorso, iniettate nel suo ``let`` come in ogni espressione: il coro
    cresce o decresce di istanza in istanza. Valutato qui deve dare un intero
    >= 1; un default nel ``let`` tiene lo studio valido anche senza percorso.
    """
    if not is_expr_node(raw):
        return raw
    key = ("spread", "n")
    with ctx.wrapping(key=key):
        text, let = parse_expr_node(raw)
        out = eval_expr(text, let)
    if isinstance(out, float) and out.is_integer():
        out = int(out)
    if not isinstance(out, int) or isinstance(out, bool) or out < 1:
        raise ctx.err(
            f"spread: l'espressione di 'n' deve dare un intero >= 1 "
            f"(valutato {out!r}).",
            key=key,
            hint="arrotonda nell'espressione con floor/ceil.",
        )
    return out


# Gate di voce (``n`` come Env): campioni sul tempo normalizzato dello stream e
# floor in dB della voce spenta.
# ponytail: griglia uniforme invece delle intersezioni analitiche — con `curve`
# le intersezioni non sono in forma chiusa. 256 campioni = risoluzione 1/256
# della durata sull'istante di commutazione; se servisse esatta, si risolvono
# analiticamente i casi step/linear e si campiona solo `curve`.
_GATE_SAMPLES = 256
_GATE_FLOOR_DB = -120.0


def _is_n_env(raw: Any) -> bool:
    """``spread.n`` scritto come Env (il coro cresce/decresce NEL tempo).

    Le forme di sempre di un Env disegnato: ``[[t, n], ...]``, lo shorthand
    ``[a, b]``, o ``{type, points, curve}`` con l'interpolazione esplicita.
    Il nodo-expr (dict con ``expr``) resta il caso scalare per-istanza.
    """
    if isinstance(raw, dict):
        return "points" in raw
    return isinstance(raw, (list, tuple)) and bool(raw)


def _n_env_peak(raw: Any, ctx: ErrCtx) -> int:
    """Numero di voci da generare: il massimo di ``n(t)``, arrotondato in su.

    Le voci esistono tutte nel documento (uno stream e' statico), il gate le
    accende e spegne: il picco e' quante ne servono.
    """
    points = raw["points"] if isinstance(raw, dict) else raw
    values = [
        p[1] if isinstance(p, (list, tuple)) else p
        for p in points
    ]
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in values):
        raise ctx.err(
            f"spread: 'n' come envelope vuole valori numerici, trovato {points!r}.",
            key=("spread", "n"),
            hint="es. \"n: [[0, 1], [1, 4]]\" (da 1 a 4 voci nel tempo).",
        )
    peak = ceil(max(values))
    if peak < 1:
        raise ctx.err(
            f"spread: 'n' come envelope deve arrivare almeno a 1 voce "
            f"(picco {max(values)}).",
            key=("spread", "n"),
        )
    return peak


def _gate_envelopes(raw: Any, n: int, volume: Any, ctx: ErrCtx) -> List[Any]:
    """Envelope di ``volume`` per voce, derivato da ``n(t)``.

    ``gain(voce i) = clamp(n(t) - i, 0, 1)``: la voce e' piena quando ``n(t)``
    l'ha superata, spenta prima, e nel mezzo vale la frazione. E' la stessa
    regola che ``num_voices`` applica gia' dentro un singolo stream (fade sulla
    voce di confine), qui a livello di spread.

    La curva la decide l'interpolazione dell'Env di ``n``, come chiesto: con
    ``type: step`` la voce si accende di scatto, con la rampa (``linear``,
    eventualmente piegata da ``curve``) entra sfumando. Il gate esce sempre
    come envelope ``step``: e' la scaletta campionata di ``gain``, e cosi' il
    gradino resta netto invece di diventare una rampa tra due campioni.
    """
    if not isinstance(volume, (int, float)) or isinstance(volume, bool):
        raise ctx.err(
            f"spread: 'n' come envelope genera il gate su 'volume', ma il "
            f"volume dichiarato e' {volume!r} — le due cose si "
            "sovrascriverebbero.",
            key=("spread", "n"),
            hint="con 'n' variabile nel tempo il volume dev'essere uno scalare "
            "(il livello a voce accesa); per un profilo di volume proprio, usa "
            "'n' scalare e scrivi gli envelope in 'over.base.volume'.",
        )
    grid = [k / (_GATE_SAMPLES - 1) for k in range(_GATE_SAMPLES)]
    curve = [_threshold_at(raw, t) for t in grid]
    gates: List[Any] = []
    for i in range(n):
        points: List[List[float]] = []
        for t, value in zip(grid, curve):
            gain = min(1.0, max(0.0, value - i))
            db = (
                _GATE_FLOOR_DB
                if gain <= 0.0
                else round(volume + 20.0 * log10(gain), 6)
            )
            # Un envelope step tiene il valore fino al punto successivo: i
            # campioni che non cambiano nulla non servono.
            if points and points[-1][1] == db:
                continue
            points.append([round(t, 9), db])
        gates.append({"type": "step", "points": points})
    return gates


def _resolve_n(
    name: str, spread: Dict[str, Any], strategies: Dict[str, tuple], ctx: ErrCtx
) -> int:
    """``n`` effettivo dello spread: esplicito e conteggi posseduti coincidono."""
    counts: Dict[str, int] = {}
    if "n" in spread:
        raw = spread["n"]
        counts["spread.n"] = (
            _n_env_peak(raw, ctx) if _is_n_env(raw) else _spread_n(raw, ctx)
        )
    for path, (marker, params) in strategies.items():
        owned = _owned_count(name, path, marker, params, ctx)
        if owned is not None:
            counts[path] = owned
    if not counts:
        raise ctx.err(
            "spread: 'n' non derivabile — nessuna strategy possiede il "
            "conteggio.",
            key=("spread",),
            hint="dichiara 'n:' nel blocco spread, oppure una strategy che "
            "possiede il conteggio ('values' o 'ramp' completo).",
        )
    values = set(counts.values())
    if len(values) != 1:
        dettaglio = ", ".join(f"{k}={v}" for k, v in counts.items())
        raise ctx.err(
            f"spread: conteggi discordi ({dettaglio}) — 'n' e le strategy "
            "devono coincidere (valori appaiati per indice, niente prodotto "
            "cartesiano).",
            key=("spread",),
        )
    (n,) = values
    if not isinstance(n, int) or n < 1:
        raise ctx.err(
            f"spread: 'n' deve essere un intero >= 1 (ricevuto {n!r}).",
            key=("spread", "n"),
        )
    return n


def _strategy_values(
    name: str, path: str, marker: str, params: Any, n: int, ctx: ErrCtx
) -> List[Any]:
    """Gli ``n`` valori della strategy, uno per stream generato.

    Il seed di default (banda senza ``seed``, nodi-generatore negli Env) e'
    ``stable_seed(f"{nome}:spread:{path}")``: deterministico tra run, e path
    diversi della stessa spread si decorrelano da soli.
    """
    if marker == "values":
        return list(params)
    key = ("spread", "over", path)
    if marker == "expr":
        text, let, rand_let = params
        reserved = sorted({"i", "n"} & (set(let) | set(rand_let)))
        if reserved:
            raise ctx.err(
                f"spread: expr sul path '{path}', 'let' ridefinisce i nomi "
                f"riservati {reserved} ('i' e 'n' li fornisce lo spread).",
                key=key,
            )
        # Bande-let: ``n`` pescaggi per variabile, uno per stream generato;
        # seed di default derivato per-variabile (come per-path nella banda).
        draws: Dict[str, List[Any]] = {}
        for var, band_params in rand_let.items():
            band_params = dict(band_params)
            band_params.setdefault(
                "seed", stable_seed(f"{name}:spread:{path}:let:{var}")
            )
            with ctx.wrapping(key=key):
                draws[var] = band(
                    n=n, **expand_params(band_params, seed=band_params["seed"])
                )
        out: List[Any] = []
        for i in range(n):
            scope = {
                **let,
                **{var: values[i] for var, values in draws.items()},
                "i": i,
                "n": n,
            }
            try:
                out.append(eval_expr(text, scope))
            except SpecError:
                raise
            except ValueError as exc:
                # Il contesto che manca al valutatore: *quale voce* ha rotto.
                # Serve soprattutto all'indicizzazione di un corredo, dove il
                # fuori range dipende da ``i`` e non dal testo (issue #49).
                raise ctx.err(
                    f"spread: {path}, voce {i + 1} di {n}: {exc}", key=key
                ) from exc
        return out
    if marker == "ramp":
        form = _ramp_form(path, params, ctx)
        if form == "full":
            return _ramp_full(name, path, params, ctx)
        start = params["start"]
        if form == "step":
            step = params["step"]
            if not isinstance(step, (int, float)):
                raise ctx.err(
                    f"spread: ramp sul path '{path}', senza 'stop' il passo "
                    f"deve essere scalare (ricevuto {step!r}).",
                    key=key,
                    hint="per un passo-Env dichiara anche 'stop' (ramp pieno).",
                )
            return [round(start + step * i, 9) for i in range(n)]
        stop = params["stop"]  # form == "stop": suddivisione lineare su n
        if n == 1:
            return [round(start, 9)]
        return [round(start + (stop - start) * i / (n - 1), 9) for i in range(n)]
    # banda: n dello spread, seed esplicito o derivato per-path.
    band_params = {k: v for k, v in params.items() if k != "n"}
    band_params.setdefault("seed", stable_seed(f"{name}:spread:{path}"))
    with ctx.wrapping(key=key):
        return band(n=n, **expand_params(band_params, seed=band_params["seed"]))


def _expand_over_dotted(over: Dict[str, Any]) -> Dict[str, Any]:
    """Espande le chiavi puntate di ``over``.

    Una chiave che termina con un marcatore di strategy diventa
    ``{path: {marcatore: valore}}`` (``base.pointer.start.values: [...]`` ->
    ``base.pointer.start: {values: [...]}``); i frammenti che condividono il
    path si fondono, cosi' una banda si scrive su piu' righe (``.base``,
    ``.range``, ``.seed``). Le chiavi che non terminano con un marcatore sono
    path interi e restano invariate. Simmetrico a
    ``study_spec._expand_dotted_keys`` per gli override di stream.
    """
    out: Dict[str, Any] = {}
    for key, val in over.items():
        head, _, last = key.rpartition(".") if isinstance(key, str) else ("", "", "")
        # Un valore-dict e' gia' una strategy completa: la chiave resta path
        # intero (cosi' ``axes.density.base: {expr: ...}`` non si spezza sul
        # ``base`` finale). Si splitta solo il valore terminale, dove il
        # marcatore vive nella chiave (``...start.values: [..]``).
        if head and last in _STRATEGY_MARKERS and not isinstance(val, dict):
            slot = out.setdefault(head, {})
            if isinstance(slot, dict):
                slot[last] = val
                continue
        # path intero: fonde con eventuali frammenti gia' accumulati sul path.
        if isinstance(out.get(key), dict) and isinstance(val, dict):
            out[key] = {**out[key], **val}
        else:
            out[key] = val
    return out


def _expand_spread_dotted(spread: Dict[str, Any]) -> Dict[str, Any]:
    """Espande le chiavi puntate ``over.<path>`` al primo livello di ``spread:``.

    Simmetrico a ``_expand_over_dotted``, un livello sopra: ``{"over.base.
    pointer.start.values": [...]}`` -> ``{"over": {"base.pointer.start.
    values": [...]}}``, cosi' la notazione a punti disponibile dentro ``over``
    (issue: chiavi non ammesse su ``over.*`` scritto flat) vale anche per la
    chiave ``over`` stessa. Frammenti multipli (``over.a``, ``over.b``) e una
    forma ``over: {...}`` gia' annidata si fondono nello stesso dict.
    """
    out: Dict[str, Any] = {}
    for k, v in spread.items():
        if isinstance(k, str) and k.startswith("over.") and len(k) > len("over."):
            rest = k[len("over."):]
            slot = out.setdefault("over", {})
            if isinstance(slot, dict):
                if isinstance(slot.get(rest), dict) and isinstance(v, dict):
                    slot[rest] = {**slot[rest], **v}
                else:
                    slot[rest] = v
                continue
        if k == "over" and isinstance(v, dict) and isinstance(out.get("over"), dict):
            out["over"] = {**out["over"], **v}
            continue
        out[k] = v
    return out


def _validate_spread(name: str, spread: Any, ctx: ErrCtx) -> Dict[str, Any]:
    if not isinstance(spread, dict):
        raise ctx.err(
            f"spread: serve un dict con 'over' (e opzionalmente 'n'), "
            f"trovato {spread!r}.",
            key=("spread",),
        )
    spread = _expand_spread_dotted(spread)
    extra = set(spread) - _SPREAD_KEYS
    if extra:
        raise ctx.err(
            f"spread: chiavi non ammesse {sorted(extra)} (solo n/over/let).",
            key=("spread",),
            hint="le strategy vivono sotto 'over: {path: strategy}'; le "
            "manopole di voce sotto 'let: {nome: strategy}'.",
        )
    over = spread.get("over")
    if not isinstance(over, dict) or not over:
        raise ctx.err(
            "spread: 'over' obbligatorio e non vuoto ({path: strategy}).",
            key=("spread",),
            hint="es. \"over: {base.pointer.start: {ramp: {start: 0.1, "
            "step: 0.1}}}\".",
        )
    return _expand_over_dotted(over)


def _let_values(
    name: str, spread: Dict[str, Any], n: int, ctx: ErrCtx
) -> Dict[str, List[Any]]:
    """Valori per voce delle manopole di ``spread.let`` (``{nome: [n valori]}``).

    Stesso vocabolario delle strategy di ``over``, ma solo le due forme che
    NON possiedono il conteggio (n resta di ``over``/``spread.n``): ``expr``
    con ``i``/``n`` (deterministico) e la banda (un pescaggio per voce).
    ``values``/``ramp`` sono rifiutati: un conteggio proprio qui sarebbe
    ridondante con ``over``.
    """
    block = spread.get("let")
    if block is None:
        return {}
    if not isinstance(block, dict):
        raise ctx.err(
            f"spread: 'let' serve un dict {{nome: strategy}}, trovato {block!r}.",
            key=("spread", "let"),
            hint="es. \"let: {livello: {expr: 'i * 0.8'}}\".",
        )
    out: Dict[str, List[Any]] = {}
    for var, cfg in block.items():
        if is_corredo(cfg):
            raise ctx.err(
                f"spread: 'let.{var}' dichiara un corredo — a livello di voce "
                "'i' e' gia' fissato, quindi una lista qui non avrebbe nessun "
                "indice da cui essere letta.",
                key=("spread", "let", var),
                hint="dichiara il corredo nel 'let:' di gruppo (o di "
                "documento) e leggilo da qui con "
                f"\"{var}: {{expr: 'ratio[i]'}}\".",
            )
        label = f"let:{var}"
        marker, params = _strategy(name, label, cfg, ctx)
        if marker in ("values", "ramp"):
            raise ctx.err(
                f"spread: 'let.{var}' usa '{marker}' — in 'let' valgono solo "
                "'expr' (deterministico per voce) o la banda (un pescaggio per "
                "voce); il conteggio e' di 'over'/'n'.",
                key=("spread", "let", var),
            )
        out[var] = _strategy_values(name, label, marker, params, n, ctx)
    return out


def _plan_entry(
    name: str,
    entry: Dict[str, Any],
    locs: Locations | None,
    pad: int | None = None,
    base_volume: Any = None,
) -> tuple[List[str], Dict[str, List[Any]], Dict[str, List[Any]], List[str]]:
    """(nomi generati, valori per path, nomi-fantasma) di una entry-spread.

    I nomi sono 1-based, zero-padded alla larghezza di ``n`` — o di ``pad``
    quando il chiamante lo fornisce (il percorso passa il massimo ``n`` lungo
    le istanze: la stessa voce logica ha lo stesso nome ovunque esista, e il
    post-merge per nome-base la cuce nel tempo). I nomi-fantasma sono le voci
    tra ``n`` e ``pad`` che *in questa istanza* non esistono: servono a
    consumare le loro patch senza farne stream ordinari. Una collisione tra
    generati di spread diverse e' strutturalmente impossibile (l'indice e'
    solo cifre, i nomi delle entry sono chiavi uniche del dict): l'unico
    incontro possibile e' con una entry esplicita, cioe' la patch.
    """
    ctx = ErrCtx(locs=locs, stream=name)
    over = _validate_spread(name, entry["spread"], ctx)
    strategies = {path: _strategy(name, path, cfg, ctx) for path, cfg in over.items()}
    n = _resolve_n(name, entry["spread"], strategies, ctx)
    per_path = {
        path: _strategy_values(name, path, marker, params, n, ctx)
        for path, (marker, params) in strategies.items()
    }
    # ``n`` come Env: le voci ci sono tutte, il gate le accende nel tempo.
    raw_n = entry["spread"].get("n")
    if _is_n_env(raw_n):
        if "base.volume" in per_path:
            raise ctx.err(
                "spread: 'n' come envelope e 'over.base.volume' scrivono "
                "entrambi il volume delle voci.",
                key=("spread", "n"),
                hint="tieni uno dei due: il gate di 'n' o gli envelope scritti "
                "a mano in 'over'.",
            )
        volume = (entry.get("base") or {}).get("volume", base_volume)
        per_path["base.volume"] = _gate_envelopes(
            raw_n, n, 0.0 if volume is None else volume, ctx
        )
    # Manopole di voce: valori per voce iniettati per nome (non su un path).
    per_let = _let_values(name, entry["spread"], n, ctx)
    top = max(n, pad or 0)
    width = len(str(top))
    names = [f"{name}_{i + 1:0{width}d}" for i in range(n)]
    ghosts = [f"{name}_{i + 1:0{width}d}" for i in range(n, top)]
    return names, per_path, per_let, ghosts


def _is_spread(entry: Any) -> bool:
    return isinstance(entry, dict) and "spread" in entry


def _with_global_spread(
    streams: Dict[str, Any],
    global_spread: Any,
    locs: Locations | None = None,
) -> Dict[str, Any]:
    """Fonde il blocco globale ``spread:`` nelle entry che dichiarano la chiave.

    Stesso meccanismo di ``sweep:``: il globale e' il default, ``spread: {}``
    (o ``spread:`` nullo) per-stream lo eredita intero, un blocco parziale lo
    ritocca via deep-merge (le liste rimpiazzano). Una entry SENZA la chiave
    resta un singolo stream: l'attivazione e' esplicita, il globale da solo
    non espande nulla. La validazione resta post-merge, per-entry
    (``_validate_spread``): il globale da solo puo' essere parziale (es. solo
    ``n``) e completarsi negli stream. Un valore-spread non-dict nella entry
    passa invariato: l'errore di schema resta quello di sempre, col contesto
    dello stream.
    """
    if global_spread is None:
        return streams
    if not isinstance(global_spread, dict):
        raise ErrCtx(locs=locs).err(
            f"spread: il blocco globale deve essere un dict con 'over' "
            f"(e opzionalmente 'n'), trovato {global_spread!r}.",
            key=("spread",),
            hint="il blocco globale e' il default che le entry con 'spread:' "
            "ereditano via deep-merge, come per 'sweep:'.",
        )
    if not global_spread:
        return streams
    out: Dict[str, Any] = {}
    for name, entry in streams.items():
        if _is_spread(entry):
            local = entry["spread"] if entry["spread"] is not None else {}
            if isinstance(local, dict):
                entry = {**entry, "spread": _deep_merge(global_spread, local)}
        out[name] = entry
    return out


def expand_spreads(
    streams: Dict[str, Any],
    locs: Locations | None = None,
    pad_n: Dict[str, int] | None = None,
    axis_names: frozenset = frozenset(),
    global_spread: Dict[str, Any] | None = None,
    base_volume: Any = None,
) -> Dict[str, Any]:
    """Espande le entry-spread di ``streams:`` in entry ordinarie.

    Le entry senza ``spread`` passano invariate; l'ordine del documento e'
    preservato (i generati compaiono al posto della loro entry). Una entry
    esplicita omonima di un generato e' una *patch*: deep-merge sopra il
    generato e viene consumata ("genera n, poi ritocca a mano il quinto"),
    ovunque compaia nel documento. Con ``locs`` gli errori portano file e
    riga (lookup override-first dentro ``streams.<nome>``).

    ``pad_n`` (percorso-v1, issue #29) stabilizza il padding dei nomi con
    ``n`` dinamico: ``{entry: massimo n lungo il percorso}``. La patch di una
    voce che in questa istanza non esiste (indice oltre ``n`` ma dentro il
    massimo) viene consumata in silenzio: la voce e' speciale *in tutte le
    istanze in cui esiste*, e qui non esiste. Senza ``pad_n`` il
    comportamento storico e' invariato.

    ``axis_names`` (nomi d'asse del documento base) risolve il confine dei
    nomi dotted nei path di ``over`` sotto ``axes.``/``stack.`` (issue #32).

    ``global_spread`` (il blocco ``spread:`` top-level del documento, issue
    #34) e' il default che ogni entry con la chiave ``spread`` eredita via
    deep-merge prima dell'espansione: ``spread: {}`` lo riattiva intero, un
    blocco parziale lo ritocca, una entry senza chiave non espande nulla.
    Senza blocco globale il comportamento storico e' invariato.

    ``base_volume`` e' il ``base.volume`` del documento: serve come livello
    "voce accesa" quando ``n`` e' un Env e il gate viene generato (la entry
    puo' comunque dichiarare il proprio).
    """
    streams = _with_global_spread(streams, global_spread, locs)
    plans = {
        name: _plan_entry(
            name, entry, locs, (pad_n or {}).get(name), base_volume
        )
        for name, entry in streams.items()
        if _is_spread(entry)
    }
    # Le patch si individuano prima di costruire: una entry-patch che e' a sua
    # volta una spread e' ambigua (generatore o ritocco?) -> errore.
    consumed: set = set()
    for name, (names, _, _, ghosts) in plans.items():
        for gname in names:
            if gname not in streams:
                continue
            if _is_spread(streams[gname]):
                raise ErrCtx(locs=locs, stream=name).err(
                    f"spread: '{gname}' e' generato da '{name}' ma e' a sua "
                    "volta una entry-spread — patch ambigua.",
                    key=("spread",),
                    hint=f"rinomina una delle due entry, oppure togli 'spread' "
                    f"da '{gname}' per farne un ritocco del generato.",
                )
            consumed.add(gname)
        for gname in ghosts:
            if gname in streams and not _is_spread(streams[gname]):
                consumed.add(gname)

    expanded: Dict[str, Any] = {}
    for name, entry in streams.items():
        if name in consumed:
            continue
        if name not in plans:
            expanded[name] = entry
            continue
        names, per_path, per_let, _ghosts = plans[name]
        proto = {k: v for k, v in entry.items() if k != "spread"}
        for i, gname in enumerate(names):
            override = copy.deepcopy(proto)
            for path, values in per_path.items():
                _deep_set(
                    override,
                    path,
                    values[i],
                    axis_names,
                    ErrCtx(locs=locs, stream=name),
                )
            # Manopole di voce: iniettate per nome negli scope let dei nodi-expr
            # del generato (non scritte su un path, come fa over).
            if per_let:
                inject(override, {var: vals[i] for var, vals in per_let.items()})
            if "sweep" not in override:
                override["sweep"] = copy.deepcopy(_SWEEP_OFF)
            if gname in consumed:
                override = _deep_merge(override, copy.deepcopy(streams[gname] or {}))
            expanded[gname] = override
    return expanded


def spread_counts(
    streams: Dict[str, Any],
    locs: Locations | None = None,
    global_spread: Dict[str, Any] | None = None,
) -> Dict[str, int]:
    """``n`` effettivo di ogni entry-spread di ``streams:``.

    Serve al percorso per il padding stabile: valutato sul documento di ogni
    istanza (dopo l'iniezione), il massimo per entry diventa il ``pad_n`` di
    ``expand_spreads``. Stessa risoluzione di ``_plan_entry``, senza generare
    i valori; ``global_spread`` e' lo stesso default per-entry di
    ``expand_spreads`` (il conteggio va risolto sul blocco gia' ereditato).
    """
    streams = _with_global_spread(streams, global_spread, locs)
    out: Dict[str, int] = {}
    for name, entry in streams.items():
        if not _is_spread(entry):
            continue
        ctx = ErrCtx(locs=locs, stream=name)
        over = _validate_spread(name, entry["spread"], ctx)
        strategies = {
            path: _strategy(name, path, cfg, ctx) for path, cfg in over.items()
        }
        out[name] = _resolve_n(name, entry["spread"], strategies, ctx)
    return out


def spread_pad(
    docs: List[Dict[str, Any]], locs: Locations | None = None
) -> Dict[str, int]:
    """``{entry: massimo n}`` per il padding stabile dei nomi generati.

    Con ``n`` dinamico il conteggio di una entry-spread cambia da un documento
    all'altro — di istanza in istanza lungo il percorso, a gradini di versione
    sotto ``versions:`` — e la larghezza dello zero-padding va fissata sul
    massimo PRIMA di nominare la prima voce: altrimenti la stessa voce logica
    cambia nome (``coro_9`` / ``coro_09``) e una patch per nome si applica solo
    dove le cifre coincidono, restando altrove una entry ordinaria non
    consumata — in silenzio.

    Riceve i documenti gia' iniettati (uno per istanza/versione) e applica a
    ognuno la stessa pre-pass di ``resolve_streams``: le manopole di gruppo
    (``let:`` per entry, che possono alimentare ``spread.n``) e il blocco
    ``spread:`` top-level come default per-entry. Il risultato e' il ``pad_n``
    di ``expand_spreads``, passato come ``spread_pad=`` a ``resolve_streams``.
    """
    out: Dict[str, int] = {}
    for data in docs:
        streams = apply_group_let(data.get("streams") or {}, locs)
        counts = spread_counts(streams, locs, global_spread=data.get("spread"))
        for entry, n in counts.items():
            out[entry] = max(out.get(entry, 0), n)
    return out
