"""Processo ``versions``: repliche dello stack distribuite nel tempo.

Il quarto blocco accanto ad ``axes``/``stack``/``sweep``: dichiara variabili
(vocabolario dei generatori Y: ``values`` / ``ramp`` / banda con ``n``) i cui
valori vengono iniettati negli scope ``let`` dei nodi-expr del documento. Ogni
combinazione (prodotto cartesiano lessicografico nell'ordine di dichiarazione,
prima variabile esterna/lenta) genera una *versione*: la replica completa
degli stream dello stack — envelope, camminate e seed identici — con lo
``stream_id`` suffissato con i valori della combinazione. Le versioni si
ascoltano cosi' dentro un unico documento engine, senza rimappare nessun
envelope: ogni stream conserva il proprio ``time_mode: normalized`` sulla
propria durata, e l'engine dimensiona il buffer su ``max(onset + duration)``.

Sulla timeline le versioni si posizionano con le chiavi riservate ``onset``/
``duration`` del blocco (issue #26): uno **scalare** (vale per tutte le
versioni, la forma comune) oppure una sequenza lunga N (numero di combo),
fuori dal prodotto cartesiano, mappata 1:1 sulle versioni — ``onset[k]``
assoluto, ``duration[k]`` default di versione, iniettato come
``base.duration`` del documento della combo (una duration per-stream vince).
Senza ``onset`` le versioni si concatenano sulle durate di versione: col
``duration`` scalare e' il classico ``onset = k * duration``.
Sovrapposizioni e buchi sono legittimi: il merge degli stem fa overlay-add.

Il blocco richiede ``stack:`` (le versioni sono repliche dello stack), ma e'
un processo indipendente con output proprio (``yaml/versions/versions.yml``:
``yaml/stack/stack.yml`` resta il materiale com'e' scritto, senza repliche —
e' l'istanza di partenza del percorso). ``versions.duration`` e' il passo
della concatenazione, ``base.duration`` la durata di uno stream: due cose
diverse che prima erano lo stesso numero al top del documento (issue #42).
Una variabile deve essere referenziata da almeno un'espressione del documento
(guardia anti-refuso); il default dichiarato nel ``let`` (es. ``d: 0``) tiene
lo studio valido anche senza il blocco, e viene ombreggiato dall'iniezione.
"""
from __future__ import annotations

import ast
import copy
import itertools
from typing import Any, Dict, List, Optional

from .errors import ErrCtx
from .expr import is_expr_node
from . import gainmap
from .spread import spread_pad
from .stack import build_stack_stream
from .study_spec import reject_top_level_duration, resolve_streams
from .document_let import resolve_knobs
from .sweep import _fmt
from .value_generators import (
    band,
    expand_params,
    is_generator_node,
    is_linear_env_node,
    ramp,
    stable_seed,
    y_generator,
)
from .yaml_builder import build_multi_document
from .yaml_loc import Locations

# Nomi che il sistema fornisce gia' agli scope expr (``i``/``n`` dello spread,
# le costanti): una variabile di versions con questi nomi sarebbe ambigua.
_RESERVED_NAMES = frozenset({"i", "n", "pi", "e"})

# Chiavi riservate del blocco ``versions:`` (issue #26): non sono variabili di
# scope — non entrano nel prodotto cartesiano ne' nella guardia "referenziata"
# — ma generatori della timeline: sequenze lunghe N (numero di combinazioni)
# mappate 1:1 sull'ordine lessicografico delle versioni.
_TIMELINE_KEYS = ("onset", "duration")

# ``chunk`` (opzionale): un intero, non un generatore. Se presente, il
# raggruppamento in documenti di ``generate_versions_documents`` non segue
# piu' la prima variabile dichiarata ma taglia il prodotto cartesiano piatto
# (nell'ordine lessicografico di ``version_combos``) in blocchi da ``chunk``
# combinazioni: cosi' ogni documento attraversa entrambe le variabili invece
# di fissarne una.
_CHUNK_KEY = "chunk"
_RESERVED_KEYS = _TIMELINE_KEYS + (_CHUNK_KEY,)


# Gli helper d'iniezione vivono in ``inject`` (modulo neutro condiviso con
# document_let e spread); qui restano con gli alias storici.
from .inject import expr_names as _expr_names  # noqa: E402
from .inject import inject as _inject  # noqa: E402
from .inject import referenced_names as _referenced_names  # noqa: E402


def parse_versions(
    data: Dict[str, Any], locs: Locations | None = None
) -> Dict[str, List[Any]]:
    """Valida il blocco ``versions:`` e risolve i valori di ogni variabile.

    Ritorna ``{nome: [valori]}`` nell'ordine di dichiarazione. Ogni variabile
    e' un generatore Y (``values``/``ramp``/banda **con** ``n``: qui non c'e'
    coupling con una X, il conteggio va dichiarato). Una banda senza ``seed``
    deriva ``stable_seed("<study>:versions:<nome>")``: deterministico tra run,
    variabili diverse decorrelate da sole. Le chiavi riservate ``onset``/
    ``duration`` non sono variabili: le legge ``parse_version_timeline``.
    """
    ctx = ErrCtx(locs=locs)
    raw = data.get("versions")
    if not isinstance(raw, dict) or not raw:
        raise ctx.err(
            "versions: serve un dict non vuoto {variabile: generatore}.",
            key=("versions",),
            hint="es. 'versions: {d: {values: [1, 2, 3]}}'.",
        )
    raw = {k: v for k, v in raw.items() if k not in _RESERVED_KEYS}
    if not raw:
        raise ctx.err(
            "versions: servono variabili oltre alle chiavi riservate "
            "'onset'/'duration'/'chunk' (sono loro a decidere quante "
            "versioni esistono).",
            key=("versions",),
            hint="dichiara almeno una variabile, es. 'd: {values: [1, 2, 3]}'.",
        )
    sid = data.get("study_id") or "study"
    referenced = _referenced_names(
        {k: v for k, v in data.items() if k != "versions"}
    )
    out: Dict[str, List[Any]] = {}
    for name, cfg in raw.items():
        key = ("versions", name)
        if name in _RESERVED_NAMES:
            raise ctx.err(
                f"versions: '{name}' e' un nome riservato degli scope expr "
                f"({', '.join(sorted(_RESERVED_NAMES))}).",
                key=key,
                hint="scegli un altro nome per la variabile.",
            )
        if not isinstance(cfg, dict):
            raise ctx.err(
                f"versions: la variabile '{name}' deve avere un generatore "
                f"(dict), trovato {cfg!r}.",
                key=key,
                hint="dichiara 'values', 'ramp' o una banda ('base'/'range'/'n').",
            )
        seed = stable_seed(f"{sid}:versions:{name}")
        values = _sequence_values(name, cfg, seed, ctx, key)
        if name not in referenced:
            raise ctx.err(
                f"versions: la variabile '{name}' non e' referenziata da "
                "nessuna espressione del documento.",
                key=key,
                hint=f"usala in un nodo-expr (es. \"expr: 'env + {name}'\") "
                "oppure toglila dal blocco.",
            )
        out[name] = values
    return out


def _sequence_values(
    name: str, cfg: Any, seed: int, ctx: ErrCtx, key: tuple
) -> List[Any]:
    """Sequenza di scalari di una manopola-versione (asse a singola manopola o
    manopola co-variante di Forma 1).

    ``values`` / lista nuda -> la lista; ``ramp`` -> la rampa; banda -> ``n``
    pescaggi (``n`` obbligatorio: qui non c'e' camminata-X a possedere il
    conteggio). Seed di default per decorrelare manopole diverse.
    """
    if isinstance(cfg, list):
        values: List[Any] = list(cfg)
    else:
        if not isinstance(cfg, dict):
            raise ctx.err(
                f"versions: '{name}' deve avere un generatore (dict) o una "
                f"lista, trovato {cfg!r}.",
                key=key,
                hint="dichiara 'values', 'ramp' o una banda ('base'/'range'/'n').",
            )
        with ctx.wrapping(key=key):
            gen_key, params = y_generator(cfg)
        with ctx.wrapping(key=key):
            if gen_key == "values":
                values = list(params)
            elif gen_key == "ramp":
                values = ramp(**expand_params(params, seed=seed))
            else:  # band
                if "n" not in params:
                    raise ctx.err(
                        f"versions: la banda di '{name}' richiede 'n' (qui non "
                        "c'e' una camminata-X a possedere il conteggio).",
                        key=key,
                    )
                band_params = dict(params)
                band_params.setdefault("seed", seed)
                values = band(
                    **expand_params(band_params, seed=band_params["seed"])
                )
    if not values:
        raise ctx.err(
            f"versions: '{name}' non genera nessun valore.", key=key
        )
    return values


def _timeline_sequence(
    name: str, cfg: Any, n: int, sid: str, ctx: ErrCtx
) -> List[float]:
    """Risolve una chiave riservata (``onset``/``duration``) in N valori.

    Uno **scalare** e' la forma corta: lo stesso valore per tutte le versioni.
    Su ``duration`` e' il caso comune — versioni tutte lunghe uguale, passo
    costante — e va scritto come si legge, ``versions: {duration: 50}``
    (issue #42). Su ``onset`` lo scalare e' legittimo ma dice un'altra cosa:
    tutte le versioni allo *stesso* istante, cioe' sovrapposte (il merge fa
    overlay-add). Per scaglionarle serve una sequenza.

    Altrimenti il vocabolario e' quello delle variabili
    (``values``/``ramp``/banda), ma il conteggio lo possiede il prodotto
    cartesiano: ``values`` deve avere esattamente N elementi; la banda deduce
    ``n = N`` (unico punto del progetto dove n e' deducibile) e un ``n``
    esplicito diverso e' errore; ``ramp`` senza ``step`` distribuisce N valori
    equispaziati start -> stop, con ``step`` la griglia generata deve contare
    esattamente N. Una banda senza ``seed`` deriva
    ``stable_seed("<study>:versions:<nome>")``.
    """
    key = ("versions", name)
    if isinstance(cfg, (int, float)) and not isinstance(cfg, bool):
        values: List[Any] = [cfg] * n
        return _check_timeline_values(name, values, n, ctx, key)
    if not isinstance(cfg, dict):
        raise ctx.err(
            f"versions: '{name}' deve avere un generatore (dict) o uno "
            f"scalare, trovato {cfg!r}.",
            key=key,
            hint="uno scalare vale per tutte le versioni (es. 'duration: 50'); "
            "altrimenti dichiara 'values', 'ramp' o una banda ('base'/'range').",
        )
    with ctx.wrapping(key=key):
        gen_key, params = y_generator(cfg)
    seed = stable_seed(f"{sid}:versions:{name}")
    with ctx.wrapping(key=key):
        if gen_key == "values":
            values: List[Any] = list(params)
        elif gen_key == "ramp":
            if "step" in params:
                values = ramp(**expand_params(params, seed=seed))
            else:
                if "start" not in params or "stop" not in params:
                    raise ctx.err(
                        f"versions: '{name}', la rampa richiede 'start' e "
                        "'stop'.",
                        key=key,
                    )
                start, stop = params["start"], params["stop"]
                values = [
                    start + (stop - start) * k / (n - 1) for k in range(n)
                ] if n > 1 else [start]
        else:  # band
            band_params = dict(params)
            if band_params.setdefault("n", n) != n:
                raise ctx.err(
                    f"versions: '{name}', 'n' e' {band_params['n']} ma le "
                    f"versioni sono {n} — il conteggio lo possiede il "
                    "prodotto cartesiano delle variabili.",
                    key=key,
                    hint="ometti 'n': per le chiavi riservate e' dedotto.",
                )
            band_params.setdefault("seed", seed)
            values = band(
                **expand_params(band_params, seed=band_params["seed"])
            )
    return _check_timeline_values(name, values, n, ctx, key)


def _check_timeline_values(
    name: str, values: List[Any], n: int, ctx: ErrCtx, key: tuple
) -> List[float]:
    """Valida la sequenza di una chiave riservata: lunghezza, tipo, segno.

    Condivisa dalle due forme (scalare broadcastato e generatore): quello che
    la timeline accetta non dipende da come e' stata scritta.
    """
    if len(values) != n:
        raise ctx.err(
            f"versions: '{name}' genera {len(values)} valori ma le versioni "
            f"sono {n} (la sequenza si mappa 1:1 sulle combinazioni).",
            key=key,
        )
    for v in values:
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            raise ctx.err(
                f"versions: '{name}', valore non numerico {v!r}.", key=key
            )
        if name == "onset" and v < 0:
            raise ctx.err(
                f"versions: onset deve essere >= 0 (generato {v}).", key=key
            )
        if name == "duration" and v <= 0:
            raise ctx.err(
                f"versions: duration deve essere > 0 (generato {v}).", key=key
            )
    return [float(v) for v in values]


def parse_version_timeline(
    data: Dict[str, Any], n: int, locs: Locations | None = None
) -> tuple[List[float] | None, List[float] | None]:
    """Risolve le chiavi riservate ``onset``/``duration`` di ``versions:``.

    Ritorna ``(onsets, durations)``, ognuno una lista lunga ``n`` o ``None``
    se la chiave e' assente. ``onset[k]`` e' la posizione **assoluta** della
    versione k sulla timeline (non monotono legittimo: sovrapposizioni e
    buchi emergono dai valori); ``duration[k]`` fa da default di ``duration:``
    per gli stream della versione k.
    """
    ctx = ErrCtx(locs=locs)
    raw = data.get("versions") or {}
    sid = data.get("study_id") or "study"
    out = {}
    for name in _TIMELINE_KEYS:
        cfg = raw.get(name)
        out[name] = (
            None if cfg is None else _timeline_sequence(name, cfg, n, sid, ctx)
        )
    return out["onset"], out["duration"]


def version_combos(
    vars: Dict[str, List[Any]], *, interleaved: bool = False
) -> List[Dict[str, Any]]:
    """Prodotto cartesiano delle variabili.

    Di default lessicografico: l'ordine di dichiarazione conta, la prima
    variabile e' esterna (lenta), l'ultima interna (veloce) — come gli
    ``orderings`` dello sweep. Con ``interleaved=True`` (attivato da
    ``versions.chunk``, v. ``_build_versions``) nessuna variabile resta
    ferma per un intero giro delle altre: le combinazioni sono ordinate per
    somma degli indici crescente (traversata diagonale della griglia), cosi'
    un ``chunk`` attraversa sempre entrambi gli assi invece di scorrere solo
    quella interna a variabile esterna fissa.
    """
    names = list(vars)
    if not interleaved:
        return [
            dict(zip(names, picked))
            for picked in itertools.product(*(vars[n] for n in names))
        ]
    ranges = [range(len(vars[n])) for n in names]
    idx_combos = sorted(itertools.product(*ranges), key=lambda idxs: (sum(idxs), idxs))
    return [
        dict(zip(names, (vars[n][i] for n, i in zip(names, idxs))))
        for idxs in idx_combos
    ]


AxisState = tuple  # (label: str, knobs: Dict[str, value])


def parse_version_axes(
    data: Dict[str, Any], locs: Locations | None = None
) -> Dict[str, List[AxisState]]:
    """Il blocco ``versions:`` come assi ortogonali.

    Ritorna ``{asse: [(label, {manopola: valore}), ...]}`` nell'ordine di
    dichiarazione. Un asse e' o un fascio di manopole parallele (Forma 1:
    ogni manopola una sequenza scalare, lunghezza = la piu' lunga, le corte
    tengono l'ultimo) o un insieme di stati nominati (Forma 2: ogni stato un
    bundle di manopole, i cui valori possono essere envelope). Un asse a
    generatore singolo (``d: {values: ...}``) e' la forma piatta storica: una
    manopola omonima dell'asse. Il prodotto cartesiano corre FRA gli assi
    (``axis_combos``). Le chiavi riservate ``onset``/``duration``/``chunk``
    non sono assi.
    """
    ctx = ErrCtx(locs=locs)
    raw = data.get("versions")
    if not isinstance(raw, dict) or not raw:
        raise ctx.err(
            "versions: serve un dict non vuoto {asse: ...}.",
            key=("versions",),
            hint="es. 'versions: {d: {values: [1, 2, 3]}}'.",
        )
    raw = {k: v for k, v in raw.items() if k not in _RESERVED_KEYS}
    if not raw:
        raise ctx.err(
            "versions: servono assi oltre alle chiavi riservate "
            "'onset'/'duration'/'chunk'.",
            key=("versions",),
            hint="dichiara almeno un asse, es. 'd: {values: [1, 2, 3]}'.",
        )
    sid = data.get("study_id") or "study"
    referenced = _referenced_names(
        {k: v for k, v in data.items() if k != "versions"}
    )
    out: Dict[str, List[AxisState]] = {}
    knobs_all: set = set()
    for axis, cfg in raw.items():
        states = _parse_axis(axis, cfg, sid, ctx)
        out[axis] = states
        for _, knobs in states:
            knobs_all |= set(knobs)
    for knob in sorted(knobs_all):
        if knob in _RESERVED_NAMES:
            raise ctx.err(
                f"versions: la manopola '{knob}' e' un nome riservato degli "
                f"scope expr ({', '.join(sorted(_RESERVED_NAMES))}).",
                key=("versions",),
                hint="scegli un altro nome.",
            )
        if knob not in referenced:
            raise ctx.err(
                f"versions: la manopola '{knob}' non e' referenziata da "
                "nessuna espressione del documento.",
                key=("versions",),
                hint=f"usala in un nodo-expr (es. \"expr: '{knob}'\") oppure "
                "toglila dal blocco.",
            )
    return out


def _parse_axis(axis: str, cfg: Any, sid: str, ctx: ErrCtx) -> List[AxisState]:
    key = ("versions", axis)
    _reject_linear_env(axis, None, cfg, ctx, key)
    # Asse a singola manopola (forma piatta storica): generatore o lista nuda.
    if is_generator_node(cfg) or isinstance(cfg, list):
        seed = stable_seed(f"{sid}:versions:{axis}")
        values = _sequence_values(axis, cfg, seed, ctx, key)
        return [(_fmt(v), {axis: v}) for v in values]
    if not isinstance(cfg, dict) or not cfg:
        raise ctx.err(
            f"versions: l'asse '{axis}' deve essere un generatore, una lista, "
            "o un dict di manopole co-varianti / stati nominati.",
            key=key,
        )
    # Discriminatore Forma 1 (co-varianti) vs Forma 2 (stati): ogni entry e'
    # una sequenza (generatore/lista) o un bundle (dict non-generatore).
    kinds = {}
    for name, v in cfg.items():
        _reject_linear_env(axis, name, v, ctx, ("versions", axis, name))
        if isinstance(v, dict) and not is_generator_node(v):
            kinds[name] = "bundle"
        elif is_generator_node(v) or isinstance(v, list):
            kinds[name] = "seq"
        else:
            raise ctx.err(
                f"versions: l'asse '{axis}', entry '{name}': uno scalare nudo "
                "e' ambiguo — una manopola co-variante vuole una sequenza "
                "('values'/'ramp'/banda/lista), uno stato un bundle di manopole.",
                key=("versions", axis, name),
            )
    kset = set(kinds.values())
    if kset == {"seq"}:
        return _forma1(axis, cfg, sid, ctx)
    if kset == {"bundle"}:
        return _forma2(axis, cfg, sid, ctx)
    raise ctx.err(
        f"versions: l'asse '{axis}' mescola manopole co-varianti (Forma 1) e "
        "stati nominati (Forma 2) — un asse e' o l'uno o l'altro.",
        key=key,
        hint="separa le due cose in due assi distinti.",
    )


def _reject_linear_env(
    axis: str, entry: str | None, cfg: Any, ctx: ErrCtx, key: tuple
) -> None:
    """``linear_env:`` come *entry* di un asse e' Famiglia 2 dove serve la 1.

    Senza questa guardia il wrapper cadrebbe nel ramo bundle del
    discriminatore e ``linear_env`` diventerebbe il nome di una manopola: un
    errore piu' avanti, e fuorviante. Dentro un bundle di Forma 2 il wrapper
    e' invece la forma giusta — la' il valore e' un envelope (issue #47).
    """
    if not is_linear_env_node(cfg):
        return
    dove = f"l'asse '{axis}', entry '{entry}'" if entry else f"l'asse '{axis}'"
    raise ctx.err(
        f"versions: {dove} usa 'linear_env:', che marca una forma nel tempo — "
        "qui serve una sequenza di versioni, letta per indice.",
        key=key,
        hint="dichiara 'values', 'ramp' o una banda direttamente; "
        "'linear_env:' vale dentro un bundle di Forma 2, dove il valore di "
        "una manopola e' un envelope.",
    )


def _forma1(axis: str, cfg: Dict[str, Any], sid: str, ctx: ErrCtx) -> List[AxisState]:
    """Manopole parallele: ognuna una sequenza, lunghezza = la piu' lunga, le
    corte tengono l'ultimo valore."""
    seqs: Dict[str, List[Any]] = {}
    for knob, v in cfg.items():
        seed = stable_seed(f"{sid}:versions:{axis}:{knob}")
        seqs[knob] = _sequence_values(
            knob, v, seed, ctx, ("versions", axis, knob)
        )
    length = max(len(s) for s in seqs.values())
    return [
        (
            str(i + 1),
            {knob: seq[min(i, len(seq) - 1)] for knob, seq in seqs.items()},
        )
        for i in range(length)
    ]


def _forma2(axis: str, cfg: Dict[str, Any], sid: str, ctx: ErrCtx) -> List[AxisState]:
    """Stati nominati: ogni stato un bundle di manopole (valori anche envelope,
    risolti come le manopole di gruppo). Bundle parziale: le manopole non
    nominate restano al riposo di ``let:``."""
    states: List[AxisState] = []
    for state, bundle in cfg.items():
        if not isinstance(bundle, dict) or not bundle:
            raise ctx.err(
                f"versions: l'asse '{axis}', stato '{state}' deve essere un "
                "bundle non vuoto {manopola: valore}.",
                key=("versions", axis, state),
            )
        resolved = resolve_knobs(
            bundle,
            f"{sid}:versions:{axis}:{state}",
            ctx,
            key_prefix=("versions", axis, state),
        )
        states.append((str(state), resolved))
    return states


def axis_combos(
    axes: Dict[str, List[AxisState]], *, interleaved: bool = False
) -> List[AxisState]:
    """Prodotto cartesiano FRA gli assi: ``[(label, {manopola: valore}), ...]``.

    Riusa ``version_combos`` (lessicografico o diagonale) sugli stati; ogni
    combinazione fonde i bundle dei suoi assi e concatena le etichette
    (``grana=1__densita=rada``). Su collisione di manopola fra due assi vince
    l'ultimo dichiarato (assi ortogonali: non dovrebbero condividere manopole).
    """
    picks = version_combos(axes, interleaved=interleaved)
    out: List[AxisState] = []
    for pick in picks:
        parts, merged = [], {}
        for ax, (label, knobs) in pick.items():
            parts.append(f"{ax}={label}")
            merged.update(knobs)
        out.append(("__".join(parts), merged))
    return out


def inject_combo(data: Dict[str, Any], combo: Dict[str, Any]) -> Dict[str, Any]:
    """Copia del documento con i valori della combinazione iniettati nei ``let``.

    L'iniezione tocca solo i nodi-expr la cui espressione *nomina* la
    variabile: un ``let`` che non la referenzia resta intatto (nessun nome
    fantasma negli scope altrui). Il valore iniettato ombreggia il default
    dichiarato nel ``let`` — e' il punto del meccanismo.
    """
    out = copy.deepcopy(data)
    _inject(out, combo)
    return out


def _build_versions(
    data: Dict[str, Any],
    study_id: str | None = None,
    locs: Locations | None = None,
    *,
    output_sr: Optional[int] = 48000,
    samples_dir: Optional[str] = None,
) -> tuple[str, List[tuple[str, Dict[str, Any]]]]:
    """Gli stream di tutte le versioni, ognuno con l'etichetta del suo gruppo.

    Cuore condiviso da ``generate_versions_document`` (un documento solo) e
    ``generate_versions_documents`` (uno per gruppo).

    Per ogni combinazione: iniezione nello scope, risoluzione degli stream
    (``resolve_streams``, il parse di sempre), costruzione via
    ``build_stack_stream`` — identica allo stack — poi ``stream_id``
    suffissato con l'etichetta della combinazione (``fermo__d=1``) e onset
    spostato sulla posizione della versione.

    Le chiavi riservate ``onset``/``duration`` del blocco (issue #26)
    posizionano le versioni: ``onset[k]`` e' assoluto (l'onset per-stream
    resta relativo alla propria versione: ``onset_finale = onset_versione +
    onset_stream``); ``duration[k]`` viene iniettata come ``base.duration``
    del documento della combo k *prima* di ``resolve_streams`` (issue #42),
    quindi fa da default e una duration per-stream vince comunque. Chiavi
    assenti -> concatenazione: ``onset_versione[k]`` e' la somma delle durate
    delle versioni precedenti (con ``versions.duration`` scalare, il classico
    ``k * duration``). La durata documento e' ``max(onset + duration)`` sugli
    stream costruiti: versioni sovrapposte o bucate sono legittime.

    Una variabile del blocco puo' muovere ``spread.n`` (nodo-expr), e allora
    il numero di voci di una entry-spread cambia da una versione all'altra: il
    padding dei nomi generati e' stabilizzato sulla larghezza del massimo
    ``n`` di TUTTO il prodotto cartesiano (``spread_pad``, issue #39), come il
    percorso fa lungo le istanze. E' la stessa evoluzione-di-spread, a gradini
    di versione invece che sul tempo reale.
    """
    sid = study_id or data.get("study_id") or "study"
    ctx = ErrCtx(locs=locs)
    # Il divieto di ``duration:`` top-level (#42, D3) va applicato QUI, sul
    # documento originale: ``resolve_streams`` piu' sotto vede solo i
    # documenti per-combo, dove la duration di versione e' gia' in
    # ``base.duration``. Senza, uno studio non migrato passerebbe in silenzio.
    reject_top_level_duration(data, locs)
    if "stack" not in data:
        raise ctx.err(
            "versions: richiede il blocco 'stack:' (le versioni sono "
            "repliche dello stack).",
            key=("versions",),
            hint="aggiungi 'stack: {}' (anche vuoto) al documento.",
        )
    raw_versions = data.get("versions") or {}
    chunk = raw_versions.get(_CHUNK_KEY)
    if chunk is not None and (
        not isinstance(chunk, int) or isinstance(chunk, bool) or chunk < 1
    ):
        raise ctx.err(
            f"versions: 'chunk' deve essere un intero >= 1, trovato {chunk!r}.",
            key=("versions", "chunk"),
        )
    axes = parse_version_axes(data, locs=locs)
    combos = axis_combos(axes, interleaved=chunk is not None)
    onsets, durations = parse_version_timeline(data, len(combos), locs=locs)
    if onsets is None:
        # Concatenazione: serve 'versions.duration' come passo. Il 'duration:'
        # top-level, che in #26 faceva anche da passo, non esiste piu' (#42):
        # la sua meta' "passo" e' ora 'versions.duration', la sua meta' "durata
        # di stream" e' 'base.duration' — e base.duration NON vale come passo.
        if durations is None:
            raise ctx.err(
                "versions: senza 'versions.onset' serve 'versions.duration' "
                "come passo per concatenare le versioni.",
                key=("versions",),
                hint="aggiungi 'duration: <secondi>' dentro il blocco "
                "'versions:' (il passo della concatenazione) oppure "
                "'versions.onset' per posizionare le versioni a mano. La "
                "'base.duration' non vale: e' la durata di uno stream, non "
                "il passo delle versioni.",
            )
        per_version = durations
        onsets = []
        acc = 0.0
        for d in per_version:
            onsets.append(acc)
            acc += d
    base_data = {k: v for k, v in data.items() if k != "versions"}

    # Prima passata: i documenti iniettati, e il massimo ``n`` per entry-spread
    # sull'intero prodotto cartesiano. Il padding stabile dei nomi generati
    # richiede il conteggio di TUTTE le versioni prima di nominare la prima
    # voce (issue #39): con ``spread.n`` mosso da una variabile del blocco il
    # numero di voci cambia a gradini di versione, e senza pad condiviso la
    # stessa voce logica cambierebbe nome a cavallo di una decade. Il massimo
    # e' sul prodotto intero, non per gruppo: i documenti di
    # ``generate_versions_documents`` restano confrontabili fra loro, e una
    # patch per nome vale in ogni file.
    docs: List[Dict[str, Any]] = []
    for k, (_label, combo) in enumerate(combos):
        data_k = inject_combo(base_data, combo)
        if durations is not None:
            # La duration di versione entra come ``base.duration`` del
            # documento della combo (issue #42): e' il default degli stream
            # della versione, quindi va scritta dove i default degli stream
            # vivono. Una ``duration:`` di entry la scavalca come sempre.
            # ``base:`` dichiarato vuoto e' None, non {}: la forma con ``or``
            # evita il TypeError e tiene il resto dei default.
            data_k["base"] = {**(data_k.get("base") or {}), "duration": durations[k]}
        docs.append(data_k)
    pad_n = spread_pad(docs, locs)

    if chunk is not None:
        n_groups = -(-len(combos) // chunk)  # ceil
        pad = len(str(n_groups - 1))
    built: List[tuple[str, Dict[str, Any]]] = []
    for k, (label, _combo) in enumerate(combos):
        # Gruppo di default: il primo asse (esterno/lento) — la prima parte
        # dell'etichetta (``grana=1__densita=rada`` -> ``grana=1``).
        group = (
            f"chunk={k // chunk:0{pad}d}"
            if chunk is not None
            else label.split("__", 1)[0]
        )
        for spec in resolve_streams(docs[k], sid, locs=locs, spread_pad=pad_n):
            s = build_stack_stream(spec, output_sr=output_sr)
            s["stream_id"] = f"{s['stream_id']}__{label}"
            s["onset"] = (s.get("onset") or 0) + onsets[k]
            built.append((group, s))
    # La compensazione sta qui, *prima* del raggruppamento in documenti: il
    # riferimento e' comunque per-versione (le versioni concatenate non si
    # sovrappongono, quindi ognuna si normalizza da se'), ma la traslazione in
    # sottrazione e' unica per l'intero prodotto cartesiano. Compensando dopo
    # lo split, ogni file riceverebbe uno shift diverso e i gruppi non
    # sarebbero piu' confrontabili fra loro all'ascolto.
    gain = gainmap.parse_config(data)
    if gain and samples_dir:
        gainmap.compensate(
            [s for _, s in built],
            samples_dir=samples_dir,
            output_sr=output_sr or 48000,
            **gain,
        )
    return sid, built


def _versions_document(
    data: Dict[str, Any], sid: str, streams: List[Dict[str, Any]], title: str
) -> Dict[str, Any]:
    return build_multi_document(
        streams,
        title=title,
        seed=data.get("seed"),
        duration=max(s["onset"] + s["duration"] for s in streams),
    )


def generate_versions_document(
    data: Dict[str, Any],
    study_id: str | None = None,
    locs: Locations | None = None,
    *,
    output_sr: Optional[int] = 48000,
    samples_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """Tutte le versioni in un solo documento (timeline completa).

    E' la vista non spezzata: la produzione passa da
    ``generate_versions_documents``.
    """
    sid, built = _build_versions(
        data, study_id, locs, output_sr=output_sr, samples_dir=samples_dir
    )
    return _versions_document(
        data, sid, [s for _, s in built], f"{sid} :: stack :: versions"
    )


def generate_versions_documents(
    data: Dict[str, Any],
    study_id: str | None = None,
    locs: Locations | None = None,
    *,
    output_sr: Optional[int] = 48000,
    samples_dir: Optional[str] = None,
) -> List[tuple[str, Dict[str, Any]]]:
    """Un documento per gruppo (default: per valore della **variabile esterna**).

    Il prodotto cartesiano di ``versions:`` cresce in fretta e un documento
    unico diventa un audio da decine di minuti, ingestibile da aprire e da
    ascoltare. Senza ``versions.chunk`` il raggruppamento usa la prima
    variabile dichiarata (esterna/lenta, v. ``version_combos``) come confine
    naturale di file: con ``d`` x ``g`` escono N_d documenti, ciascuno con
    le sole combo di quel ``d`` — utile ma fissa una variabile per documento.

    Con ``versions.chunk: N`` il raggruppamento ignora le variabili e taglia
    il prodotto cartesiano piatto (ordine lessicografico di ``version_combos``)
    in blocchi da N combinazioni consecutive: ogni documento attraversa cosi'
    entrambe le variabili, invece di sentirne muovere una sola per file.

    Ogni documento e' **ribasato a zero** (si sottrae l'onset minimo del
    gruppo), cosi' apre da solo senza silenzio iniziale; le posizioni
    relative dentro il gruppo — comprese quelle dettate da ``versions.onset``
    esplicito, sovrapposizioni e buchi inclusi — restano intatte.

    Ritorna coppie ``(etichetta, documento)`` con etichetta ``"d=3"``,
    nell'ordine delle versioni.
    """
    sid, built = _build_versions(
        data, study_id, locs, output_sr=output_sr, samples_dir=samples_dir
    )
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for group, s in built:
        groups.setdefault(group, []).append(s)
    out = []
    for group, streams in groups.items():
        off = min(s["onset"] for s in streams)
        for s in streams:
            s["onset"] -= off
        out.append(
            (group, _versions_document(
                data, sid, streams, f"{sid} :: stack :: versions :: {group}"
            ))
        )
    return out
