"""Processo ``percorso``: istanze di spread distribuite sul tempo reale.

Il quarto asse del sistema (issue #29), gemello compositivo di ``versions``:
dove ``versions`` genera il prodotto cartesiano delle combinazioni (analisi,
una variabile si muove e le altre stanno ferme), ``percorso`` dispone K
*istanze* dello stack su una timeline e fa cambiare i valori **insieme**,
appaiati sul tempo — nessun prodotto cartesiano. Sta a ``versions`` come
``stack`` sta a ``sweep``.

La timeline ha due strategy mutuamente esclusive:

- **enumerata** (``onset:``): gli onset li dichiari tu, sull'indice, col
  vocabolario di sequenza (``values`` / ``ramp`` / banda). Il conteggio ``k``
  lo possiede ``onset`` (lunghezza di ``values``, griglia del ramp con
  ``step``, ``n`` della banda); ``k:`` esplicito e' ammesso come cross-check
  e obbligatorio solo quando ``onset`` non possiede un conteggio.
- **camminata** (``arco:`` + ``passo:``): ``arco`` e' l'estensione totale,
  ``passo`` la legge dell'intervallo — ``t_next = t + passo(t)``, campionato
  all'onset corrente, finche' ``t < arco``. ``k`` emerge, non si dichiara.
  La camminata-X trasposta sull'asse delle istanze.

Le altre chiavi del blocco sono **traiettorie**: la legge con cui una
variabile cambia lungo il tempo reale del percorso. Si scrivono come la
``base`` di un axis — banda (``base`` + ``range``/``drift``/``distribution``/
``seed``) o nodo-expr; uno scalare nudo e' la costante. MAI ``values``/
``ramp``: sono generatori di sequenze, appartengono ai contesti indicizzati.
Il tempo dei breakpoint e' normalizzato 0 -> 1 sull'estensione del percorso
(l'``arco`` in camminata, l'ultimo onset in enumerata). I valori campionati
all'onset reale di ogni istanza vengono iniettati negli scope ``let`` dei
nodi-expr che li nominano, come fa ``versions``.

``duration`` e' una traiettoria riservata con ``unit: factor`` (default) |
``s``: col factor ``duration_k = factor(t_k) * intervallo verso la prossima
istanza`` (1 = legato, > 1 sovrapposizione, < 1 buchi); assente = legato.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .errors import ErrCtx
from .expr import eval_expr, parse_expr_node
from .value_generators import (
    Y_GENERATOR_KEYS,
    _band_sampler,
    _threshold_at,
    band,
    expand_params,
    ramp,
    stable_seed,
)
from .versions import _referenced_names
from .yaml_loc import Locations

# Nomi che il sistema fornisce gia' agli scope expr (``i``/``n`` dello spread,
# le costanti): una traiettoria con questi nomi sarebbe ambigua.
_RESERVED_NAMES = frozenset({"i", "n", "pi", "e"})

# Chiavi riservate del blocco ``percorso:``: la timeline (le due strategy) e
# la duration d'istanza. Non sono variabili di scope.
_TIMELINE_KEYS = frozenset({"k", "onset", "arco", "passo", "duration"})

# Chiavi ammesse in una traiettoria-banda: la banda di sempre, senza ``n``
# (le traiettorie non possiedono mai il conteggio: sono leggi sul tempo).
_BAND_KEYS = frozenset({"base", "range", "seed", "distribution", "drift"})

# Unit ammesse per la traiettoria ``duration``.
_DURATION_UNITS = ("factor", "s")


@dataclass
class Trajectory:
    """Una traiettoria del percorso, validata ma non ancora campionata.

    ``kind``: ``const`` (params = lo scalare) | ``band`` (params = dict della
    banda) | ``expr`` (params = ``(testo, let)``).
    """

    kind: str
    params: Any


@dataclass
class PercorsoSpec:
    """Il blocco ``percorso:`` validato.

    ``k`` e' il conteggio effettivo nella strategy enumerata (posseduto da
    ``onset``, cross-check con ``k:`` esplicito); ``None`` in camminata, dove
    il conteggio emerge da ``arco``/``passo`` alla costruzione della timeline.
    """

    strategy: str                                  # "enumerata" | "camminata"
    k: Optional[int] = None
    onset: Optional[Dict[str, Any]] = None         # cfg del generatore (enumerata)
    arco: Optional[float] = None                   # estensione totale (camminata)
    passo: Optional[Trajectory] = None             # legge dell'intervallo (camminata)
    duration: Optional[Trajectory] = None          # None = legato
    duration_unit: str = "factor"
    variables: Dict[str, Trajectory] = field(default_factory=dict)


def _is_scalar(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _trajectory(name: str, cfg: Any, ctx: ErrCtx) -> Trajectory:
    """Valida e classifica una traiettoria (grammatica-Env).

    Scalare nudo = costante; dict con ``base`` = banda; dict con ``expr`` =
    nodo-expr. ``values``/``ramp`` sono errore con l'hint sui contesti
    indicizzati: una traiettoria e' una legge sul tempo, non una sequenza.
    """
    key = ("percorso", name)
    if _is_scalar(cfg):
        return Trajectory("const", cfg)
    if not isinstance(cfg, dict):
        raise ctx.err(
            f"percorso: '{name}' non e' una traiettoria — serve uno scalare "
            f"(costante), una banda ('base') o un nodo-expr (trovato {cfg!r}).",
            key=key,
            hint="una traiettoria si scrive come la 'base' di un axis: es. "
            "'{base: [0, 1], range: .1}' oppure '{expr: \"...\", let: {...}}'.",
        )
    if "values" in cfg or "ramp" in cfg:
        marker = "values" if "values" in cfg else "ramp"
        raise ctx.err(
            f"percorso: '{name}' usa '{marker}' — le traiettorie non si "
            "scrivono con generatori di sequenze.",
            key=key,
            hint="'values'/'ramp' appartengono ai contesti indicizzati "
            "('onset' enumerato, 'spread', 'versions', gli assi), dove la "
            "posizione k e' l'elemento k; una traiettoria e' una legge sul "
            "tempo: banda ('base') o nodo-expr. Per una forma disegnata "
            "scrivila come Env dentro 'base' (es. 'base: {linear_env: "
            "[0, 1, 0]}').",
        )
    if "expr" in cfg:
        markers = sorted(Y_GENERATOR_KEYS & set(cfg))
        if markers:
            raise ctx.err(
                f"percorso: '{name}' mescola 'expr' con {markers} — "
                "esattamente una forma per traiettoria.",
                key=key,
            )
        with ctx.wrapping(key=key):
            text, let = parse_expr_node(cfg)
        return Trajectory("expr", (text, let))
    if "base" in cfg:
        if "n" in cfg:
            raise ctx.err(
                f"percorso: '{name}' dichiara 'n' — le traiettorie non "
                "possiedono mai il conteggio: sono leggi sul tempo, le "
                "campioni in 3 o 300 istanze e sono le stesse.",
                key=key,
                hint="il conteggio lo possiede la timeline ('onset' o "
                "'arco'/'passo').",
            )
        extra = set(cfg) - _BAND_KEYS
        if extra:
            raise ctx.err(
                f"percorso: '{name}', chiavi non ammesse {sorted(extra)} "
                f"(solo {sorted(_BAND_KEYS)}).",
                key=key,
            )
        return Trajectory("band", dict(cfg))
    raise ctx.err(
        f"percorso: '{name}' non e' una traiettoria riconoscibile "
        f"(chiavi {sorted(cfg)}).",
        key=key,
        hint="scalare nudo = costante; banda = 'base' con "
        "'range'/'drift'/'distribution'/'seed' opzionali; nodo-expr = "
        "'{expr, let}'.",
    )


def _duration_trajectory(
    cfg: Any, ctx: ErrCtx
) -> Tuple[Optional[Trajectory], str]:
    """``(traiettoria, unit)`` della chiave riservata ``duration``.

    ``unit`` viaggia accanto alla forma (``{base: ..., unit: s}``) e si
    stacca prima del parse della traiettoria; ``factor`` e' il default —
    il duty un asse piu' in alto.
    """
    if cfg is None:
        return None, "factor"
    unit = "factor"
    if isinstance(cfg, dict) and "unit" in cfg:
        unit = cfg["unit"]
        if unit not in _DURATION_UNITS:
            raise ctx.err(
                f"percorso: duration, unit '{unit}' non ammessa "
                f"({' | '.join(_DURATION_UNITS)}).",
                key=("percorso", "duration"),
                hint="'factor' moltiplica l'intervallo verso la prossima "
                "istanza (1 = legato); 's' e' assoluta in secondi.",
            )
        cfg = {k: v for k, v in cfg.items() if k != "unit"}
    return _trajectory("duration", cfg, ctx), unit


def _onset_seed(sid: str) -> int:
    """Seed derivato del generatore di ``onset`` (banda senza ``seed``,
    nodi-generatore annidati): unico per parse e timeline, cosi' il conteggio
    e la generazione non possono divergere."""
    return stable_seed(f"{sid}:percorso:onset")


def _owned_k(onset: Dict[str, Any], sid: str, ctx: ErrCtx) -> Optional[int]:
    """Il conteggio posseduto dal generatore di ``onset``, se lo possiede.

    ``values`` possiede la propria lunghezza; ``ramp`` con ``step`` la sua
    griglia; la banda solo con ``n`` proprio. ``ramp {start, stop}`` senza
    ``step`` e la banda senza ``n`` lasciano il conteggio a ``k:``.
    """
    key = ("percorso", "onset")
    if not isinstance(onset, dict):
        raise ctx.err(
            f"percorso: 'onset' deve avere un generatore (dict), trovato "
            f"{onset!r}.",
            key=key,
            hint="dichiara 'values', 'ramp' o una banda ('base'/'range').",
        )
    if "values" in onset:
        return len(onset["values"])
    if "ramp" in onset:
        params = onset["ramp"]
        if not isinstance(params, dict) or "start" not in params or "stop" not in params:
            raise ctx.err(
                "percorso: onset, la rampa richiede 'start' e 'stop'.",
                key=key,
            )
        if "step" not in params:
            return None
        with ctx.wrapping(key=key):
            return len(
                ramp(**expand_params(dict(params), seed=_onset_seed(sid)))
            )
    if "base" in onset:
        n = onset.get("n")
        if n is None:
            return None
        return n
    raise ctx.err(
        "percorso: 'onset' senza generatore riconoscibile "
        f"(chiavi {sorted(onset) if isinstance(onset, dict) else onset!r}).",
        key=key,
        hint="dichiara 'values' (tempi assoluti), 'ramp' o una banda "
        "('base'/'range').",
    )


def _resolve_k(raw: Dict[str, Any], sid: str, ctx: ErrCtx) -> int:
    """``k`` effettivo della strategy enumerata: esplicito e posseduto coincidono."""
    counts: Dict[str, Any] = {}
    if "k" in raw:
        counts["k"] = raw["k"]
    owned = _owned_k(raw["onset"], sid, ctx)
    if owned is not None:
        counts["onset"] = owned
    if not counts:
        raise ctx.err(
            "percorso: 'k' non derivabile — 'onset' non possiede il "
            "conteggio.",
            key=("percorso",),
            hint="dichiara 'k:' accanto a 'onset', oppure un generatore che "
            "possiede il conteggio ('values', 'ramp' con 'step', banda con "
            "'n').",
        )
    values = set(counts.values())
    if len(values) != 1:
        dettaglio = ", ".join(f"{k}={v}" for k, v in counts.items())
        raise ctx.err(
            f"percorso: conteggi discordi ({dettaglio}) — 'k' e 'onset' "
            "devono coincidere (il conteggio lo possiede 'onset', 'k:' e' "
            "un cross-check).",
            key=("percorso", "k"),
        )
    (k,) = values
    if not isinstance(k, int) or isinstance(k, bool) or k < 1:
        raise ctx.err(
            f"percorso: 'k' deve essere un intero >= 1 (ricevuto {k!r}).",
            key=("percorso", "k"),
        )
    return k


def parse_percorso(
    data: Dict[str, Any], locs: Locations | None = None
) -> PercorsoSpec:
    """Valida il blocco ``percorso:`` e classifica timeline e traiettorie.

    Richiede ``stack:`` (le istanze sono la popolazione dello stack disposta
    nel tempo); ``versions:`` puo' coesistere nel documento — sono processi
    indipendenti, li esercita il target. Ogni variabile deve essere
    referenziata da almeno un'espressione del documento (guardia anti-refuso,
    come ``versions``).
    """
    ctx = ErrCtx(locs=locs)
    sid = data.get("study_id") or "study"
    raw = data.get("percorso")
    if not isinstance(raw, dict) or not raw:
        raise ctx.err(
            "percorso: serve un dict non vuoto con una strategy di timeline "
            "e le traiettorie.",
            key=("percorso",),
            hint="es. 'percorso: {arco: 180, passo: 22.5, w: {base: [0, 1]}}'.",
        )
    if "stack" not in data:
        raise ctx.err(
            "percorso: richiede il blocco 'stack:' (le istanze sono la "
            "popolazione dello stack disposta nel tempo).",
            key=("percorso",),
            hint="aggiungi 'stack: {}' (anche vuoto) al documento.",
        )
    has_onset = "onset" in raw
    has_walk = "arco" in raw or "passo" in raw
    if has_onset and has_walk:
        raise ctx.err(
            "percorso: 'onset' insieme ad 'arco'/'passo' — le due strategy "
            "di timeline sono mutuamente esclusive.",
            key=("percorso",),
            hint="strategy enumerata: 'onset:' (piu' 'k:' quando serve); "
            "strategy camminata: 'arco:' + 'passo:'. Scegline una.",
        )
    if not has_onset and not has_walk:
        raise ctx.err(
            "percorso: manca la strategy di timeline — 'k:' da solo non "
            "esiste (le traiettorie non possiedono il conteggio).",
            key=("percorso",),
            hint="strategy enumerata: 'onset:' dichiara i tempi sull'indice "
            "('values'/'ramp'/banda); strategy camminata: 'arco:' + 'passo:' "
            "(l'equispaziato e' un passo costante: 'arco: 180, passo: 22.5').",
        )

    if has_onset:
        spec = PercorsoSpec(
            strategy="enumerata",
            k=_resolve_k(raw, sid, ctx),
            onset=dict(raw["onset"]) if isinstance(raw["onset"], dict) else raw["onset"],
        )
    else:
        if "k" in raw:
            raise ctx.err(
                "percorso: 'k' non si dichiara nella strategy camminata — "
                "il conteggio emerge da 'arco' e 'passo'.",
                key=("percorso", "k"),
                hint="togli 'k:'; per un conteggio dichiarato usa la "
                "strategy enumerata ('onset:').",
            )
        if "arco" not in raw:
            raise ctx.err(
                "percorso: 'passo' senza 'arco' — la camminata li richiede "
                "insieme.",
                key=("percorso",),
                hint="'arco' e' l'estensione totale del percorso in secondi.",
            )
        if "passo" not in raw:
            raise ctx.err(
                "percorso: 'arco' senza 'passo' — la camminata li richiede "
                "insieme.",
                key=("percorso",),
                hint="'passo' e' la legge dell'intervallo tra un'istanza e "
                "la prossima (scalare, banda o nodo-expr).",
            )
        arco = raw["arco"]
        if not _is_scalar(arco) or arco <= 0:
            raise ctx.err(
                f"percorso: 'arco' deve essere uno scalare > 0 (ricevuto "
                f"{arco!r}) — e' l'estensione totale, non una traiettoria.",
                key=("percorso", "arco"),
            )
        spec = PercorsoSpec(
            strategy="camminata",
            arco=float(arco),
            passo=_trajectory("passo", raw["passo"], ctx),
        )

    spec.duration, spec.duration_unit = _duration_trajectory(
        raw.get("duration"), ctx
    )

    referenced = _referenced_names(
        {k: v for k, v in data.items() if k != "percorso"}
    )
    for name, cfg in raw.items():
        if name in _TIMELINE_KEYS:
            continue
        if name in _RESERVED_NAMES:
            raise ctx.err(
                f"percorso: '{name}' e' un nome riservato degli scope expr "
                f"({', '.join(sorted(_RESERVED_NAMES))}).",
                key=("percorso", name),
                hint="scegli un altro nome per la traiettoria.",
            )
        traj = _trajectory(name, cfg, ctx)
        if name not in referenced:
            raise ctx.err(
                f"percorso: la traiettoria '{name}' non e' referenziata da "
                "nessuna espressione del documento.",
                key=("percorso", name),
                hint=f"usala in un nodo-expr (es. \"expr: 'env + {name}'\") "
                "oppure toglila dal blocco.",
            )
        spec.variables[name] = traj
    return spec


# --- campionamento delle traiettorie e timeline --------------------------------

# Tetto anti-runaway della camminata: un passo che collassa verso lo zero
# genererebbe una timeline enorme. Stessa filosofia di MAX_RAMP_POINTS nei
# generatori (errore di configurazione, non caso d'uso).
MAX_ISTANZE = 10_000


@dataclass
class Timeline:
    """La timeline risolta: dove le istanze vivono sul tempo reale.

    ``intervals[k]`` e' l'intervallo di riferimento dell'istanza k (verso la
    prossima): in camminata e' ``passo(t_k)`` per ogni k (l'ultima usa il
    passo che avrebbe seguito, gia' calcolato dal loop); in enumerata e' la
    differenza tra onset consecutivi, con l'ultima che ripete l'ultimo
    intervallo noto. ``span`` e' l'estensione su cui i tempi delle traiettorie
    si normalizzano 0 -> 1: l'``arco`` in camminata (l'ultima istanza cade
    *prima* di 1 — campionamento onesto, come i grani campionano un envelope),
    l'ultimo onset in enumerata (l'ultima cade esattamente a 1).
    """

    onsets: List[float]
    intervals: List[float]
    span: float

    def fracs(self) -> List[float]:
        """La posizione normalizzata 0 -> 1 di ogni istanza."""
        if self.span <= 0:
            return [0.0 for _ in self.onsets]
        return [t / self.span for t in self.onsets]


def make_sampler(name: str, traj: Trajectory, sid: str, ctx: ErrCtx):
    """``sample(frac) -> valore`` di una traiettoria.

    Costante -> il valore; banda -> il pescaggio di ``_band_sampler`` (con
    ``drift`` lo stato del walk vive nella closure: campionare le istanze in
    ordine cronologico produce la deriva correlata); nodo-expr -> valutato una
    volta, il risultato (scalare o Env statico) campionato con la semantica
    di sempre. Una banda senza ``seed`` deriva
    ``stable_seed("<study>:percorso:<nome>")``: deterministico tra run,
    traiettorie diverse decorrelate da sole.
    """
    key = ("percorso", name)
    if traj.kind == "const":
        value = float(traj.params)
        return lambda frac: value
    if traj.kind == "expr":
        text, let = traj.params
        with ctx.wrapping(key=key):
            out = eval_expr(text, let)
        if isinstance(out, (int, float)):
            return lambda frac: float(out)

        def sample_expr(frac: float) -> float:
            with ctx.wrapping(key=key):
                return float(_threshold_at(out, frac))

        return sample_expr
    # banda: parametri espansi alla seam (nodi-generatore annidati compresi)
    params = dict(traj.params)
    seed = params.pop("seed", stable_seed(f"{sid}:percorso:{name}"))
    with ctx.wrapping(key=key):
        params = expand_params(params, seed=seed)
        inner = _band_sampler(
            params["base"],
            params.get("range", 0.0),
            seed,
            params.get("distribution", "uniform"),
            params.get("drift"),
            f"percorso.{name}",
        )

    def sample_band(frac: float) -> float:
        with ctx.wrapping(key=key):
            return inner(frac)

    return sample_band


def _enumerated_onsets(spec: PercorsoSpec, sid: str, ctx: ErrCtx) -> List[float]:
    """Gli onset assoluti della strategy enumerata, risolti sull'indice.

    Stessa semantica di ``_timeline_sequence`` di ``versions``: ``values`` =
    tempi assoluti uno per istanza; ``ramp`` con ``step`` = griglia (conta
    ``k`` da sola); ``ramp {start, stop}`` = ``k`` valori equispaziati;
    banda = ``k`` pescaggi (seed derivato se assente).
    """
    key = ("percorso", "onset")
    onset, k = spec.onset, spec.k
    seed = _onset_seed(sid)
    with ctx.wrapping(key=key):
        if "values" in onset:
            values: List[Any] = list(onset["values"])
        elif "ramp" in onset:
            params = dict(onset["ramp"])
            if "step" in params:
                values = ramp(**expand_params(params, seed=seed))
            else:
                start, stop = params["start"], params["stop"]
                values = (
                    [start + (stop - start) * i / (k - 1) for i in range(k)]
                    if k > 1 else [start]
                )
        else:  # banda (il parse ha gia' validato la forma)
            params = {kk: v for kk, v in onset.items() if kk != "n"}
            params.setdefault("seed", seed)
            values = band(
                n=k, **expand_params(params, seed=params["seed"])
            )
    for v in values:
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            raise ctx.err(
                f"percorso: onset, valore non numerico {v!r}.", key=key
            )
        if v < 0:
            raise ctx.err(
                f"percorso: onset deve essere >= 0 (generato {v}).", key=key
            )
    return [round(float(v), 9) for v in values]


def build_timeline(
    spec: PercorsoSpec, sid: str, locs: Locations | None = None
) -> Timeline:
    """Risolve la timeline delle istanze (fase 1 dell'ordine a due fasi).

    La circolarita' si rompe qui: gli onset nascono sull'indice (enumerata) o
    dall'accumulo del passo (camminata); tutto il resto — ``duration`` e le
    traiettorie ordinarie — si campiona poi sull'onset reale. In camminata
    ``t_next = t + passo(t)`` finche' ``t < arco``: ``k`` emerge, e un passo
    non positivo al campionamento e' errore (loop infinito).
    """
    ctx = ErrCtx(locs=locs)
    if spec.strategy == "enumerata":
        onsets = _enumerated_onsets(spec, sid, ctx)
        span = onsets[-1]
        if len(onsets) > 1:
            diffs = [
                round(b - a, 9) for a, b in zip(onsets, onsets[1:])
            ]
            intervals = diffs + [diffs[-1]]
        else:
            # Nessun intervallo di riferimento: legato/factor erroreranno
            # in resolve_durations (serve unit: s).
            intervals = [0.0]
        return Timeline(onsets=onsets, intervals=intervals, span=span)

    # camminata
    sample = make_sampler("passo", spec.passo, sid, ctx)
    arco = spec.arco
    onsets: List[float] = []
    intervals: List[float] = []
    t = 0.0
    while t < arco:
        frac = t / arco
        step = sample(frac)
        if not isinstance(step, (int, float)) or step <= 0:
            raise ctx.err(
                f"percorso: passo non positivo ({step}) all'onset {t} — "
                "la camminata non avanzerebbe.",
                key=("percorso", "passo"),
                hint="la traiettoria di 'passo' deve restare > 0 su tutto "
                "l'arco.",
            )
        onsets.append(round(t, 9))
        intervals.append(round(float(step), 9))
        t += step
        if len(onsets) > MAX_ISTANZE:
            raise ctx.err(
                f"percorso: oltre {MAX_ISTANZE} istanze — il passo e' "
                "troppo piccolo per l'arco.",
                key=("percorso", "passo"),
            )
    return Timeline(onsets=onsets, intervals=intervals, span=float(arco))


def resolve_durations(
    spec: PercorsoSpec,
    timeline: Timeline,
    sid: str,
    locs: Locations | None = None,
) -> List[float]:
    """La durata di ogni istanza, campionata al suo onset reale.

    Identica nelle due strategy: solo il modo in cui gli onset vengono al
    mondo le distingue. Assente = legato (factor 1). Con ``unit: factor``
    (default) ``duration_k = factor(t_k) * intervals[k]`` — 1 = legato, > 1
    sovrapposizione (crossfade), < 1 buchi: il duty un asse piu' in alto, e
    la proporzione tiene dentro un accelerando. Con ``unit: s`` la durata e'
    assoluta. Enumerata con ``k = 1`` e factor e' errore: nessun intervallo
    di riferimento.
    """
    ctx = ErrCtx(locs=locs)
    key = ("percorso", "duration")
    if spec.duration is None:
        factors = None  # legato: factor 1 senza campionare nulla
        unit = "factor"
    else:
        sample = make_sampler("duration", spec.duration, sid, ctx)
        factors = [sample(frac) for frac in timeline.fracs()]
        unit = spec.duration_unit
    if unit == "factor" and spec.strategy == "enumerata" and len(timeline.onsets) == 1:
        raise ctx.err(
            "percorso: con una sola istanza enumerata non c'e' un intervallo "
            "di riferimento per il factor (e il legato e' un factor 1).",
            key=key,
            hint="dichiara una durata assoluta: 'duration: {base: <s>, "
            "unit: s}'.",
        )
    if factors is None:
        durations = list(timeline.intervals)
    elif unit == "factor":
        durations = [
            round(f * dt, 9) for f, dt in zip(factors, timeline.intervals)
        ]
    else:
        durations = [round(float(f), 9) for f in factors]
    for k, d in enumerate(durations):
        if d <= 0:
            raise ctx.err(
                f"percorso: duration dell'istanza {k + 1} non positiva "
                f"({d}).",
                key=key,
                hint="con onset non monotoni il legato/factor produce "
                "intervalli negativi: dichiara 'unit: s' o riordina gli "
                "onset.",
            )
    return durations


# --- generazione del documento ---------------------------------------------------

def generate_percorso_document(
    data: Dict[str, Any],
    study_id: str | None = None,
    locs: Locations | None = None,
    *,
    output_sr: Optional[int] = 48000,
    samples_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """Il documento engine multi-stream con le istanze del percorso.

    Ordine a due fasi: prima la timeline (onset e durate d'istanza), poi per
    ogni istanza le traiettorie campionate al suo onset reale — in ordine
    cronologico, cosi' una banda con ``drift`` deriva davvero di istanza in
    istanza — e iniettate negli scope ``let`` dei nodi-expr che le nominano
    (``inject_combo``, il meccanismo di ``versions``). Poi il parse di
    sempre: ``resolve_streams`` + ``build_stack_stream``, con le strategy di
    spread che si **rivalutano a ogni istanza** coi valori iniettati — e'
    l'evoluzione-di-spread del design. Il seed resta invariato se non
    toccato: la stessa camminata/pescaggio ritorna, trasformata dalle
    variabili (il gesto che ritorna); il reseed e' un override come un altro.

    Col blocco ``gain_compensation:`` e un ``samples_dir`` risolto, gli stream
    ricevono qui l'offset di ``volume`` che pareggia il mascheramento fra punti
    di lettura diversi dello stesso buffer (v. ``gainmap``), come stack e
    versions. La regola resta quella condivisa: riferimento **locale** (la media
    degli stream contemporanei, calcolata per istanza sulla sovrapposizione
    ``[onset, onset+duration)``), traslazione in sottrazione **unica** per
    documento, ``max_shift`` di default a 24 dB. Le tre estensioni specifiche
    del percorso che la issue #36 solleva — riferimento globale opzionale, peso
    per frazione di sovrapposizione sugli stack sfalsati a catena, default di
    ``max_shift`` piu' stretto sugli archi lunghi — sono scelte musicali
    lasciate all'utente e non sono implementate qui.

    La ``duration`` d'istanza entra come ``base.duration`` del documento della
    singola istanza prima del parse (issue #42): fa da default, una duration
    per-stream vince. Lo ``stream_id`` e' suffissato ``__k=NN`` (1-based, zero-padded
    sulla larghezza del K finale: l'ordine alfabetico in SV e' quello
    cronologico); l'onset per-stream resta relativo alla propria istanza
    (``onset_finale = onset_istanza + onset_stream``). Il padding dei nomi di
    spread e' stabilizzato sulla larghezza del massimo ``n`` lungo il
    percorso (``spread_counts`` -> ``spread_pad``): la stessa voce logica ha
    lo stesso nome ovunque esista, e il post-merge per nome-base la cuce nel
    tempo. Durata documento = ``max(onset + duration)``.
    """
    from . import gainmap
    from .stack import build_stack_stream
    from .spread import spread_pad
    from .study_spec import reject_top_level_duration, resolve_streams
    from .versions import inject_combo
    from .yaml_builder import build_multi_document

    sid = study_id or data.get("study_id") or "study"
    ctx = ErrCtx(locs=locs)
    # Divieto di ``duration:`` top-level (#42, D3) sul documento originale:
    # ``resolve_streams`` piu' sotto vede solo i documenti per-istanza, dove
    # la duration d'istanza e' gia' in ``base.duration``.
    reject_top_level_duration(data, locs)
    spec = parse_percorso(data, locs=locs)
    timeline = build_timeline(spec, sid, locs=locs)
    durations = resolve_durations(spec, timeline, sid, locs=locs)
    samplers = {
        name: make_sampler(name, traj, sid, ctx)
        for name, traj in spec.variables.items()
    }
    combos = [
        {name: round(sample(frac), 9) for name, sample in samplers.items()}
        for frac in timeline.fracs()
    ]
    base_data = {k: v for k, v in data.items() if k != "percorso"}

    # Prima passata: documenti iniettati e massimo n per entry-spread (il
    # padding stabile richiede il conteggio di TUTTE le istanze prima di
    # nominare la prima voce).
    docs: List[Dict[str, Any]] = []
    for k, combo in enumerate(combos):
        data_k = inject_combo(base_data, combo)
        # La duration d'istanza entra come ``base.duration`` del documento
        # dell'istanza (issue #42), gemella dell'iniezione di ``versions``:
        # e' il default degli stream dell'istanza, e li' vivono i default.
        # ``base:`` dichiarato vuoto e' None, non {}.
        data_k["base"] = {**(data_k.get("base") or {}), "duration": durations[k]}
        docs.append(data_k)
    pad_n = spread_pad(docs, locs)

    width = len(str(len(docs)))
    built: List[Dict[str, Any]] = []
    for k, data_k in enumerate(docs):
        label = f"k={k + 1:0{width}d}"
        for s_spec in resolve_streams(data_k, sid, locs=locs, spread_pad=pad_n):
            s = build_stack_stream(s_spec, output_sr=output_sr)
            s["stream_id"] = f"{s['stream_id']}__{label}"
            s["onset"] = (s.get("onset") or 0) + timeline.onsets[k]
            built.append(s)
    # Compensazione prima di collassare in documento: il riferimento e' locale
    # (per istanza, sulla sovrapposizione temporale) e la traslazione in
    # sottrazione e' unica per l'intero percorso, cosi' i rapporti di livello
    # fra istanze restano confrontabili all'ascolto (v. issue #36).
    gain = gainmap.parse_config(data)
    if gain and samples_dir:
        gainmap.compensate(
            built,
            samples_dir=samples_dir,
            output_sr=output_sr or 48000,
            **gain,
        )
    return build_multi_document(
        built,
        title=f"{sid} :: stack :: percorso",
        seed=data.get("seed"),
        duration=max(s["onset"] + s["duration"] for s in built),
    )
