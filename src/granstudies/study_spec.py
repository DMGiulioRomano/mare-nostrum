"""Parsing e validazione di ``study.yml`` (la definizione di uno studio).

Uno studio fissa uno stream *base* e un insieme di *assi* (i parametri sotto
osservazione). Ogni asse ha un path YAML, un valore di baseline e una lista di
valori di test. Lo sweep combinatorio (vedi ``sweep.py``) muove gli assi a
ordini crescenti (1 alla volta, a coppie, ...).
"""
from __future__ import annotations

import itertools
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple

import yaml

from . import bounds as bounds_mod
from . import gainmap
from . import yaml_loc
from .errors import ErrCtx, SpecError
from .group_let import apply_group_let
from .spread import AXIS_NAME_BLOCKS, expand_spreads, split_axis_key
from .value_generators import (
    Y_GENERATOR_KEYS,
    band,
    expand_params,
    ramp,
    stable_seed,
    y_generator,
)
from .x_strategies import X_UNITS, x_owns_n

# Chiavi che marcano il generatore Y di un asse (values | ramp | base): la
# presenza di ``base`` marca la banda piatta. Mutuamente esclusive.
_GENERATOR_KEYS = Y_GENERATOR_KEYS
# Chiavi della banda piatta che accompagnano ``base`` (viaggiano con essa,
# vanno rimosse insieme quando uno stream cambia generatore su quell'asse).
_BAND_KEYS = frozenset({"base", "range", "n", "seed", "distribution", "drift"})

# Campi obbligatori per marcatore-generatore (chiave canonica di ``y_generator``).
# Un merge/override parziale puo' lasciare un generatore incompleto (es.
# ``ramp: {step: 1}`` senza ``start``/``stop``): senza guardia esploderebbe con
# un ``TypeError`` grezzo da ``ramp(**params)``. ``values`` (lista) e ``band``
# (``base`` garantito dal marcatore, ``n`` gia' validato) non hanno campi
# scoperti — la tabella e' estendibile a futuri generatori.
_REQUIRED_GEN_FIELDS = {"ramp": ("start", "stop", "step")}


@dataclass(frozen=True)
class Axis:
    """Un parametro sotto studio."""

    name: str
    path: str
    baseline: float
    values: List[float]
    interpolation: str = "linear"   # linear | cubic | step
    # Config grezza del generatore Y ({chiave: params}): serve al processo
    # stack, che risolve i valori al momento dell'assemblaggio (coupling con la
    # strategy-X, seed risolti per precedenza).
    generator: Dict[str, Any] = field(default_factory=dict)

    def defers_n(self) -> bool:
        """True se la Y non possiede ``n`` (banda senza ``n``): i valori emergono
        dalla camminata-X in stack, non si enumerano al parse."""
        params = self.generator.get("band")
        return isinstance(params, dict) and "n" not in params


# Chiavi riservate sotto ``axes:`` che non descrivono un asse ma vocabolario Y
# condiviso: ``interpolation`` (curva di Y, default di studio) e ``seed``
# (seed-Y globale, default per ogni banda di Y senza seed proprio). Il timing
# (plateau/transition) e' proprieta' del processo sweep e vive sotto ``sweep:``.
_AXES_RESERVED_KEYS = ("interpolation", "seed")

# Nome dei valori attesi per ogni ``grain.duration_unit``, per i messaggi
# d'errore sui bounds. Unita' assente o ``seconds`` -> secondi.
_UNIT_LABELS = {"samples": "campioni", "milliseconds": "ms"}

# Vocabolario di ``interpolation`` (curva di Y fra i valori di test): ``step``
# (tenuta), ``linear`` (rampa), ``cubic`` (curva). Un valore fuori da qui e' un
# refuso: va fermato al parse, non passato muto a valle (issue #37). Pubblico
# perche' e' la definizione del vocabolario per tutto il repo: ``sv_export``
# ricava i suoi tipi disegnabili da ``_PLOT_STYLE_BY_TYPE`` e un test verifica
# che i due insiemi coincidano.
VALID_INTERPOLATION = ("linear", "cubic", "step")


@dataclass(frozen=True)
class StudySpec:
    study_id: str
    title: str | None
    seed: int | None
    # Durata dello stream (s), risolta per catena ``duration:`` di entry >
    # ``base.duration`` (issue #42). Non e' la durata del documento: quella e'
    # sempre dedotta, ``max(onset + duration)`` sugli stream costruiti.
    duration: float | None
    # Onset dello stream sulla timeline (s). ``None`` = non dichiarato: lo
    # distingue da un esplicito ``onset: 0`` cosi' il processo stack non
    # schiaccia un eventuale ``base.onset`` ereditato. E' una chiave solo
    # per-stream: al top-level del documento e' rifiutata (``resolve_streams``).
    onset: float | None
    samples_dir: str | None
    base: Dict[str, Any]
    axes: List[Axis]
    orders: List[int]
    orderings: List[List[str]] = field(default_factory=list)
    mode: str = "discrete"          # discrete | envelope | both
    plateau: float = 5.0            # secondi per plateau (ascolto stabile)
    transition: float = 5.0         # secondi per transizione tra plateau
    interpolation: str = "linear"   # linear | cubic | step
    stream_id: str | None = None    # sotto-cartella per versionare gli output
    # Processo stack: config X per-asse (None = blocco ``stack:`` assente), i
    # due seed globali (seed-Y in axes, seed-X in stack) e l'unita' globale
    # della camminata (``stack.unit``), override-abili per-stream via il
    # deep-merge di ``resolve_streams``.
    stack: Dict[str, Any] | None = None
    stack_seed: int | None = None
    stack_unit: str | None = None
    axes_seed: int | None = None
    # Blocco ``gain_compensation:`` top-level ({alpha, max_shift}), None =
    # assente. Lo consuma ``gainmap.compensate`` sui documenti multi-stream.
    gain_compensation: Dict[str, float] | None = None

    def axis(self, name: str) -> Axis:
        for ax in self.axes:
            if ax.name == name:
                return ax
        raise KeyError(name)

    def _seed_key(self) -> str:
        return self.stream_id or self.study_id

    def resolved_y_seed(self) -> int:
        """Seed-Y di default per questo stream (il per-asse vince comunque).

        Precedenza: ``axes.seed`` globale, altrimenti auto-derivazione stabile
        dall'id dello stream — gli stream impilati si decorrelano di default.
        Il salt ``:y`` separa il dominio da quello X: senza, Y e X con lo stesso
        seed auto-derivato pescherebbero la stessa sequenza uniforme.
        """
        if self.axes_seed is not None:
            return self.axes_seed
        return stable_seed(f"{self._seed_key()}:y")

    def resolved_x_seed(self) -> int:
        """Seed-X di default per questo stream (il per-asse vince comunque)."""
        if self.stack_seed is not None:
            return self.stack_seed
        return stable_seed(f"{self._seed_key()}:x")

    def resolved_x_unit(self) -> str:
        """Unita' della camminata-X per questo stream (il per-asse vince comunque).

        Stessa catena del seed: ``stack.<asse>.unit`` > ``stack.unit`` globale
        (per-stream via deep-merge) > default ``hz`` (retrocompatibile).
        """
        return self.stack_unit or "hz"


def _validate(spec: StudySpec, ctx: ErrCtx, *, orders_explicit: bool = False) -> None:
    if not spec.axes:
        raise ctx.err(
            "Lo studio deve definire almeno un asse in 'axes'.", key=("axes",)
        )
    n = len(spec.axes)
    for order in spec.orders:
        if order < 0 or order > n:
            raise ctx.err(
                f"order {order} fuori range: con {n} assi gli ordini validi "
                f"sono 0..{n}.",
                key=("sweep", "orders"),
            )
    axis_names = {ax.name for ax in spec.axes}
    for ordering in spec.orderings:
        unknown = set(ordering) - axis_names
        if unknown:
            raise ctx.err(
                f"orderings: assi sconosciuti {sorted(unknown)}",
                key=("sweep", "orderings"),
                hint=f"gli assi dichiarati sono {sorted(axis_names)}.",
            )
        dupes = [n for n in ordering if ordering.count(n) > 1]
        if dupes:
            raise ctx.err(
                f"orderings: assi duplicati {sorted(set(dupes))}",
                key=("sweep", "orderings"),
            )
        if len(ordering) < 2:
            raise ctx.err(
                f"orderings: la voce {ordering} ha meno di 2 assi; un ordering "
                "e' una sequenza lento->veloce e richiede almeno 2 assi.",
                key=("sweep", "orderings"),
                hint="per muovere un solo asse usa 'orders: [1]'.",
            )

    # Ridondanza di ``orders`` scritto esplicito rispetto a ``orderings``:
    # se ci sono orderings e nessuna combinazione automatica degli ordini
    # richiesti aggiunge una variante nuova (tutte gia' coperte, per sequenza
    # esatta, dagli orderings), allora ``orders`` non fa nulla -> errore. Copre
    # sia ``orders: []`` sia un ``orders: [k]`` interamente deduplicato. La
    # forma di default (orders assente) non passa di qui.
    if orders_explicit and spec.orderings:
        decl = [ax.name for ax in spec.axes]
        ordering_seqs = {tuple(o) for o in spec.orderings}
        auto_seqs = {
            combo
            for order in spec.orders
            if order > 0
            for combo in itertools.combinations(decl, order)
        }
        if not (auto_seqs - ordering_seqs):
            raise ctx.err(
                "sweep.orders e' ridondante: con 'orderings' popolato non "
                "aggiunge nessuna combinazione automatica nuova.",
                key=("sweep", "orders"),
                hint="rimuovi 'orders' (gli orderings bastano) oppure indica "
                "ordini che generino combinazioni non gia' negli orderings.",
            )
    seen = set()
    for ax in spec.axes:
        if ax.name in seen:
            raise ctx.err(f"Asse duplicato: {ax.name}", key=("axes", ax.name))
        seen.add(ax.name)
        if not ax.values and not ax.defers_n():
            raise ctx.err(
                f"Asse '{ax.name}' senza valori di test.",
                key=("axes", ax.name),
                axis=ax.name,
                hint="dichiara 'values', 'ramp' o una banda ('base'/'range'/'n').",
            )
        # Non-numero fuori sede: ``baseline`` e gli elementi di ``values`` sono
        # slot *strutturali* (il baseline di riposo, i valori che si enumerano),
        # non ambienti Env dove un ``expr:`` avrebbe senso. Qualunque non-numero
        # qui — nodo-expr, stringa, lista — esploderebbe poco sotto nel confronto
        # bounds con un ``TypeError`` grezzo, senza path (issue #37).
        for slot, v in (
            [("baseline", ax.baseline)] + [("values", x) for x in ax.values]
        ):
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                cosa = "un nodo-expr" if isinstance(v, dict) else "un non-numero"
                raise ctx.err(
                    f"Asse '{ax.name}': '{slot}' contiene {cosa} ({v!r}), "
                    "non ammesso qui.",
                    key=("axes", ax.name, slot),
                    axis=ax.name,
                    hint=f"'{slot}' vuole un numero: e' uno slot strutturale "
                    "(conta/enumera i valori), non un ambiente 'expr:'/'let:'.",
                )
        # Sforo bloccante: i bounds engine sono un safety clamp, un valore
        # fuori range va fermato al parse invece di essere silenziosamente
        # clampato in render. Il confronto lo fa ``bounds.violation`` (unico
        # punto): qui si passa solo l'unita' dichiarata dallo stream, perche' i
        # bounds sono in secondi ma i valori dell'asse ``grain.duration``
        # possono essere in campioni o millisecondi (stream.py:415).
        grain_unit = (
            spec.base.get("grain", {}).get("duration_unit")
            if ax.path == "grain.duration"
            else None
        )
        if grain_unit == "seconds":
            grain_unit = None
        for v in list(ax.values) + [ax.baseline]:
            b = bounds_mod.violation(ax.path, v, unit=grain_unit)
            if b is not None:
                unit = _UNIT_LABELS.get(grain_unit, "s")
                raise ctx.err(
                    f"Asse '{ax.name}' valore {v} {unit} fuori bounds {b} "
                    f"(s) per il path '{ax.path}'.",
                    key=("axes", ax.name),
                    axis=ax.name,
                    hint=f"i valori (e il baseline), convertiti in secondi, "
                    f"devono stare in {b}.",
                )


def _resolve_baseline(
    name: str,
    cfg: Dict[str, Any],
    defaults: Dict[str, Any] | None,
    ctx: ErrCtx,
    grain_unit: str | None = None,
):
    """Risolve il ``baseline`` di un asse: esplicito o dal default engine.

    Single source of truth: se ``baseline`` e' omesso, lo si legge dal default
    dello schema engine via ``path``. I path ``pitch.*`` (unit-driven, nessun
    default) e i parametri con ``default=None`` (es. ``density``) richiedono un
    baseline esplicito.

    ``grain_unit`` e' la ``grain.duration_unit`` dichiarata in ``base``: come
    nell'engine (stream.py, dove la ``grain.duration`` diventa obbligatoria con
    un'unita' non-secondi), un default in secondi non e' un valore in campioni
    ne' in millisecondi, quindi il baseline va scritto a mano.
    """
    if "baseline" in cfg:
        return cfg["baseline"]
    path = cfg.get("path", name)
    if path == "grain.duration" and grain_unit not in (None, "seconds"):
        raise ctx.err(
            f"Asse '{name}': con 'grain.duration_unit: {grain_unit}' il "
            f"'baseline' e' obbligatorio.",
            key=("axes", name),
            axis=name,
            hint=f"il default engine ({path}) e' in secondi e non verrebbe "
            f"convertito: scrivi 'baseline:' in {_UNIT_LABELS[grain_unit]}.",
        )
    if path == "pitch" or path.startswith("pitch."):
        raise ctx.err(
            f"Asse '{name}': path '{path}' e' unit-driven (pitch), "
            f"'baseline' e' obbligatorio.",
            key=("axes", name),
            axis=name,
            hint=f"aggiungi 'baseline:' all'asse '{name}'.",
        )
    if defaults is None:
        from .engine_bridge import parameter_defaults

        defaults = parameter_defaults()
    if path not in defaults or defaults[path] is None:
        raise ctx.err(
            f"Asse '{name}': nessun default engine per il path '{path}', "
            f"'baseline' e' obbligatorio.",
            key=("axes", name),
            axis=name,
            hint=f"aggiungi 'baseline:' all'asse '{name}'.",
        )
    return defaults[path]


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    result = dict(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def _expand_dotted_keys(
    override: Dict[str, Any],
    axis_names: frozenset = frozenset(),
    ctx: ErrCtx | None = None,
    literal_children: bool = False,
) -> Dict[str, Any]:
    """Espande le chiavi puntate di un override di stream in dict annidati.

    ``{"axes.density.base.expr": X}`` -> ``{"axes": {"density": {"base":
    {"expr": X}}}}``. La stessa notazione a punti che ``spread.over`` gia'
    accetta (via ``_deep_set``) vale cosi' anche negli override scritti a mano
    in ``streams:``: senza questa espansione la chiave puntata finiva come
    chiave *letterale* top-level, ignorata dal merge e dal parse — l'override
    era un no-op silenzioso (era la causa di ``fermo == mobile`` in
    ``study_versions_test``, issue #29).

    Sotto ``axes:``/``stack:`` il primo identificatore e' un *nome d'asse*,
    che puo' essere a sua volta dotted (asse ``grain.duration`` senza
    ``path``, issue #32): il suo confine e' risolto da ``split_axis_key``
    (assi dichiarati -> registro engine -> fallback sintattico), sia nella
    forma tutta-puntata (``axes.grain.duration.values``) sia nelle chiavi
    figlie dirette del blocco (``axes: {grain.duration.values: ...}``);
    dentro la config dell'asse l'espansione riprende sintattica.

    Rami che si sovrappongono — una chiave puntata e una forma annidata sullo
    stesso path, o due chiavi puntate con prefisso comune — si **fondono** via
    ``_deep_merge`` nell'ordine di dichiarazione (l'ultima vince sui conflitti
    di foglia). Ricorsivo: una forma annidata puo' contenere a sua volta chiavi
    puntate. Le chiavi senza punto restano invariate.
    """

    def nest(parts: List[str], leaf: Any) -> Any:
        for p in reversed(parts):
            leaf = {p: leaf}
        return leaf

    out: Dict[str, Any] = {}
    for k, v in override.items():
        if isinstance(v, dict):
            v = _expand_dotted_keys(
                v,
                axis_names,
                ctx,
                literal_children=(
                    not literal_children and k in AXIS_NAME_BLOCKS
                ),
            )
        if isinstance(k, str) and "." in k:
            if literal_children:
                # Figlio diretto di axes/stack: la testa e' un nome d'asse.
                axis, rest = split_axis_key(k, axis_names, ctx)
                contribution = {axis: nest(rest, v)}
            else:
                parts = k.split(".")
                if parts[0] in AXIS_NAME_BLOCKS and len(parts) > 1:
                    # Forma tutta-puntata: dopo il blocco viene il nome d'asse.
                    axis, rest = split_axis_key(".".join(parts[1:]), axis_names, ctx)
                    contribution = {parts[0]: {axis: nest(rest, v)}}
                else:
                    contribution = {parts[0]: nest(parts[1:], v)}
        else:
            contribution = {k: v}
        out = _deep_merge(out, contribution)
    return out


def _check_generator_complete(
    name: str, gen_key: str, gen_params: Any, ctx: ErrCtx
) -> None:
    """Alza ``SpecError`` se al generatore mancano campi obbligatori.

    Guardia contro i generatori incompleti che un override/merge parziale puo'
    lasciare (``ramp: {step}`` eredita ``start``/``stop`` solo se la base era a
    sua volta un ramp; se la base era ``values`` restano solo i campi scritti).
    Tabella-driven (``_REQUIRED_GEN_FIELDS``): estendibile senza toccare questa
    funzione.
    """
    required = _REQUIRED_GEN_FIELDS.get(gen_key, ())
    if not isinstance(gen_params, dict):
        return
    missing = [k for k in required if k not in gen_params]
    if missing:
        raise ctx.err(
            f"Asse '{name}': {gen_key} incompleto, manca {missing} "
            f"(servono {list(required)}).",
            key=("axes", name),
            axis=name,
            hint=f"dichiara {', '.join(required)} su axes.{name}.{gen_key}; "
            "un override parziale eredita gli altri campi solo se la base ha "
            f"gia' un {gen_key}.",
        )


def _replace_generators(merged: Dict[str, Any], override: Dict[str, Any]) -> None:
    """Se un override sceglie un generatore per un asse, rimpiazza quello ereditato.

    Il deep-merge conserva le chiavi della base: un asse con ``values`` di base a
    cui lo stream aggiunge ``ramp`` finirebbe con entrambe (collisione). Coerente
    con la semantica "le liste rimpiazzano": il marcatore-generatore dell'override
    vince, si tolgono gli altri ereditati su quello stesso asse. Passare a
    ``values``/``ramp`` toglie anche le chiavi della banda (``base``/``range``/
    ``n``/``seed``); passare a ``base`` toglie ``values``/``ramp``.

    Lato ``stack`` (camminata-X): un override che porta ``base`` diventa/aggiorna
    la camminata via deep-merge; per riportare un asse a ``linear`` lo stream
    annulla l'entry (``stack: {asse: null}``), gestito in ``_stack_config``.
    """
    ov_axes = override.get("axes") or {}
    merged_axes = merged.get("axes") or {}
    for name, ov in ov_axes.items():
        if not isinstance(ov, dict):
            continue
        chosen = _GENERATOR_KEYS & ov.keys()
        ax = merged_axes.get(name)
        if len(chosen) != 1 or not isinstance(ax, dict):
            continue
        (marker,) = chosen
        for k in _GENERATOR_KEYS - chosen:      # via gli altri marcatori
            ax.pop(k, None)
        if marker in ("values", "ramp"):        # via le chiavi della banda
            for k in _BAND_KEYS:
                ax.pop(k, None)


def reject_top_level_duration(
    data: Dict[str, Any], locs: yaml_loc.Locations | None = None
) -> None:
    """Rifiuta ``duration:`` al top del documento ORIGINALE (issue #42, D3).

    Si chiamava "durata del documento" e non lo e' mai stata — quella e'
    sempre dedotta, ``max(onset + duration)``. La durata di uno *stream* si
    dichiara accanto allo stream. Dopo il merge la ``duration:`` di una entry
    diventa top-level del documento merged, e ``parse_study_spec`` la legge
    senza obiettare: il divieto vale solo sul documento originale.

    Vive fuori da ``resolve_streams`` perche' i rami ``versions:`` e
    ``percorso:`` non le passano mai il documento originale — ci arrivano i
    documenti per-combo, dove la ``base.duration`` iniettata ha gia'
    sostituito il top-level. Senza questa chiamata all'ingresso dei due rami,
    uno studio non migrato verrebbe accettato in silenzio proprio dove il
    divieto serve.
    """
    if "duration" in data:
        raise ErrCtx(locs=locs).err(
            "'duration' non e' una chiave top-level dello studio: la durata "
            "del documento e' dedotta, non dichiarata.",
            key=("duration",),
            hint="per la durata di uno stream usa 'base.duration' (dentro "
            "'base:', default per tutti gli stream) o 'duration:' nella entry; "
            "per il passo delle versioni usa 'versions.duration'.",
        )


def resolve_streams(
    data: Dict[str, Any],
    study_id: str | None = None,
    locs: yaml_loc.Locations | None = None,
    *,
    spread_pad: Dict[str, int] | None = None,
) -> List["StudySpec"]:
    """Ritorna una lista di StudySpec, uno per stream.

    Se ``streams:`` è assente, ritorna un singolo spec senza stream_id.
    Le entry-spread vengono espanse in entry ordinarie prima del merge
    (``spread.expand_spreads``), col blocco ``spread:`` top-level del
    documento come default ereditabile per-entry (issue #34, lo stesso
    meccanismo di ``sweep:``): da qui in poi ogni stream, generato o
    scritto a mano, e' un override come gli altri. Con ``locs`` gli errori
    di parse portano file e riga; la rete di sicurezza sotto etichetta con
    lo stream anche i ``ValueError`` nudi non ancora migrati a ``SpecError``.
    ``spread_pad`` (percorso-v1) stabilizza il padding dei nomi generati sul
    massimo ``n`` lungo le istanze — vedi ``expand_spreads``.
    """
    sid = study_id or data.get("study_id") or "study"
    streams = data.get("streams")
    # ``onset`` e' solo per-stream: qui, sul documento ORIGINALE (prima del
    # merge), la chiave top-level viene rifiutata. Dopo il merge l'onset di
    # uno stream *diventa* top-level del documento merged, ed e' per questo
    # che ``parse_study_spec`` la legge senza obiettare.
    if "onset" in data:
        raise ErrCtx(locs=locs).err(
            "'onset' non e' una chiave top-level dello studio: si dichiara "
            "per-stream (dentro 'streams:').",
            key=("onset",),
            hint="un onset globale che sposta tutti gli stream insieme e' "
            "ambiguo; ogni stream si posiziona col proprio 'onset'.",
        )
    # ``duration`` top-level: vietata come ``onset`` (issue #42, D3). Il
    # controllo vive in ``reject_top_level_duration`` perche' lo condividono i
    # rami versions/percorso, che qui passano gia' i documenti per-combo.
    reject_top_level_duration(data, locs)
    if not streams:
        return [parse_study_spec(data, sid, locs=locs)]
    # Nomi d'asse del documento base: risolvono il confine dei nomi dotted
    # nelle chiavi puntate degli override e nei path di spread.over (vedi
    # ``split_axis_key``).
    axis_names = frozenset(
        k
        for k, v in (data.get("axes") or {}).items()
        if k not in _AXES_RESERVED_KEYS and isinstance(v, dict)
    )
    # Manopole di gruppo (`let:` per entry): risolte e iniettate PRIMA
    # dell'espansione, cosi' tutte le voci del gruppo condividono il valore.
    streams = apply_group_let(streams, locs)
    streams = expand_spreads(
        streams,
        locs,
        pad_n=spread_pad,
        axis_names=axis_names,
        global_spread=data.get("spread"),
        base_volume=(data.get("base") or {}).get("volume"),
    )
    result = []
    for stream_id, override in streams.items():
        # Le chiavi puntate scritte a mano nell'override (``axes.density.base.expr``)
        # si espandono in dict annidati prima del merge, come in ``spread.over``.
        override = _expand_dotted_keys(
            override or {}, axis_names, ErrCtx(locs=locs, stream=stream_id)
        )
        merged = _deep_merge(data, override)
        _replace_generators(merged, override)
        merged.pop("streams", None)
        merged.setdefault("sweep", {})["stream_id"] = stream_id
        try:
            result.append(parse_study_spec(merged, sid, locs=locs))
        except SpecError:
            raise
        except ValueError as e:
            raise SpecError(
                str(e),
                stream=stream_id,
                source=locs.source if locs else None,
            ) from e
    return result


def _stack_config(
    data: Dict[str, Any], ctx: ErrCtx
) -> tuple[Dict[str, Any] | None, int | None, str | None]:
    """Estrae dal documento il blocco ``stack:``: (config per-asse, seed-X
    globale, unit globale della camminata).

    Schema piatto: ``seed`` e ``unit`` sono le chiavi riservate; ogni altra
    chiave e' un nome d'asse -> camminata-X (banda ``base``/``range``/``seed``,
    piu' ``unit``/``distribution``/``drift`` come nella banda di Y). La
    *presenza* dell'asse marca la camminata; l'assenza dal blocco = ``linear``.
    Una entry annullata (``asse: null``, utile per riportare a linear in uno
    stream) viene scartata. Blocco assente -> (None, None, None); ``curve`` va
    dentro l'Env di ``base``/``range``, non come chiave dell'entry.
    """
    if "stack" not in data:
        return None, None, None
    raw = dict(data.get("stack") or {})
    seed = raw.pop("seed", None)
    unit = raw.pop("unit", None)
    if unit is not None and unit not in X_UNITS:
        opts = " | ".join(sorted(X_UNITS))
        raise ctx.err(
            f"stack: unit '{unit}' non ammessa ({opts}).",
            key=("stack", "unit"),
            hint="'hz' = frequenza di generazione, 's' = periodo in secondi "
            "tra breakpoint, 'bpm' = battiti al minuto.",
        )
    raw = {name: xcfg for name, xcfg in raw.items() if xcfg is not None}
    for name, xcfg in raw.items():
        if isinstance(xcfg, dict) and ("rand" in xcfg or "cps" in xcfg):
            raise ctx.err(
                f"stack: asse '{name}', i wrapper 'rand:'/'cps:' non esistono "
                "piu': dichiara la camminata piatta (base/range/seed diretti).",
                key=("stack", name),
                axis=name,
                hint="es. 'rand: {cps: {base, range}}' -> 'base: ...', 'range: ...'.",
            )
        if not isinstance(xcfg, dict) or "base" not in xcfg:
            raise ctx.err(
                f"stack: asse '{name}' deve avere una camminata con 'base' "
                f"(banda nell'unita' di 'unit': hz, default | s | bpm), "
                f"trovato {xcfg!r}.",
                key=("stack", name),
                axis=name,
                hint="un asse assente dal blocco 'stack:' resta 'linear' (n dalla Y).",
            )
        extra = set(xcfg) - {"base", "range", "seed", "unit", "distribution", "drift"}
        if extra:
            raise ctx.err(
                f"stack: asse '{name}', chiavi non ammesse {sorted(extra)} "
                "(solo base/range/seed/unit/distribution/drift).",
                key=("stack", name),
                axis=name,
                hint="'curve' va dentro l'Env di base/range, non come chiave dell'entry.",
            )
        if "unit" in xcfg and xcfg["unit"] not in X_UNITS:
            opts = " | ".join(sorted(X_UNITS))
            raise ctx.err(
                f"stack: asse '{name}', unit '{xcfg['unit']}' non ammessa ({opts}).",
                key=("stack", name),
                axis=name,
                hint="'hz' = frequenza di generazione, 's' = periodo in secondi "
                "tra breakpoint, 'bpm' = battiti al minuto.",
            )
    return raw, seed, unit


def _check_interpolation(
    value: Any, ctx: ErrCtx, key: Tuple[Any, ...], axis: str | None = None
) -> None:
    """Ferma al parse un ``interpolation`` fuori vocabolario (issue #37)."""
    if value not in VALID_INTERPOLATION:
        raise ctx.err(
            f"interpolation '{value}' sconosciuta.",
            key=key,
            axis=axis,
            hint=f"i valori validi sono {list(VALID_INTERPOLATION)}.",
        )


def parse_study_spec(
    data: Dict[str, Any],
    study_id: str | None = None,
    locs: yaml_loc.Locations | None = None,
) -> StudySpec:
    """Costruisce uno ``StudySpec`` da un dict gia' caricato.

    ``locs`` (opzionale) sono le posizioni delle chiavi nel file d'origine
    (``yaml_loc``): con esse gli errori portano file e riga. Il documento puo'
    essere il merge di una stream: lo ``stream_id`` in ``sweep:`` guida sia
    l'etichetta degli errori sia il lookup override-first delle righe.
    """
    axes_raw = data.get("axes") or {}
    # Risolve i default engine una sola volta, solo se serve (lazy).
    _defaults_cache: Dict[str, Any] | None = None
    needs_defaults = any(
        k not in _AXES_RESERVED_KEYS and isinstance(v, dict) and "baseline" not in v
        for k, v in axes_raw.items()
    )
    if needs_defaults:
        from .engine_bridge import parameter_defaults

        _defaults_cache = parameter_defaults()
    # Unita' di ``grain.duration`` dichiarata in ``base``: governa sia il
    # baseline (che non puo' venire dal default engine, in secondi) sia il
    # confronto coi bounds in ``_validate``.
    _grain_unit = ((data.get("base") or {}).get("grain") or {}).get("duration_unit")

    sweep_cfg = data.get("sweep") or {}
    ctx = ErrCtx(locs=locs, stream=sweep_cfg.get("stream_id") or None)
    if "combine" in sweep_cfg:
        raise ctx.err(
            "sweep.combine non esiste piu': lo sweep fa solo il prodotto "
            "cartesiano.",
            key=("sweep", "combine"),
            hint="l'accoppiamento degli assi (ex parallel) vive nel processo "
            "stack — stessa strategy-X e stesso n.",
        )
    # Durata dello stream: si dichiara accanto allo stream (issue #42). La
    # catena e' ``duration:`` di entry > ``base.duration``, risolta qui sul
    # documento *merged* — dopo il merge la ``duration:`` di una entry e'
    # diventata chiave top-level, esattamente come succede a ``onset``. Il
    # ``duration:`` scritto a mano al top di uno studio e' l'ultima rete, in
    # via di rimozione: la durata del documento non si dichiara, si deduce.
    base_duration = (data.get("base") or {}).get("duration")
    for value, label, key in (
        (base_duration, "'base.duration'", ("base", "duration")),
        (data.get("duration"), "'duration'", ("duration",)),
    ):
        if value is not None and (
            not isinstance(value, (int, float)) or isinstance(value, bool)
            or value <= 0
        ):
            raise ctx.err(
                f"{label} deve essere un numero > 0 (ricevuto {value!r}).",
                key=key,
            )
    top_duration = data.get("duration")
    duration = top_duration if top_duration is not None else base_duration
    onset = data.get("onset")
    if onset is not None and (
        not isinstance(onset, (int, float)) or isinstance(onset, bool)
        or onset < 0
    ):
        raise ctx.err(
            f"'onset' deve essere un numero >= 0 (ricevuto {onset!r}).",
            key=("onset",),
        )
    stack_axes, stack_seed, stack_unit = _stack_config(data, ctx)
    axes_seed = axes_raw.get("seed")
    sid = study_id or data.get("study_id") or "study"
    seed_key = sweep_cfg.get("stream_id") or sid
    # Default per le bande di Y senza seed proprio (precedenza: per-asse >
    # axes.seed globale > auto-derivazione per-stream).
    default_y_seed = axes_seed if axes_seed is not None else stable_seed(f"{seed_key}:y")

    study_interpolation = axes_raw.get("interpolation", "linear")
    if "interpolation" in axes_raw:
        _check_interpolation(
            study_interpolation, ctx, key=("axes", "interpolation")
        )
    axes: List[Axis] = []
    for name, cfg in axes_raw.items():
        if name in _AXES_RESERVED_KEYS:
            continue
        if not isinstance(cfg, dict):
            hint = (
                "'plateau'/'transition' vivono in 'sweep:', non in 'axes:'."
                if name in ("plateau", "transition")
                else "un asse e' un dict con 'path' e un generatore Y."
            )
            raise ctx.err(
                f"Asse '{name}': config non valida ({cfg!r}), serve un dict.",
                key=("axes", name),
                axis=name,
                hint=hint,
            )
        # 'path' esplicito resta un alias; se omesso, la chiave dell'asse
        # (anche in dot-notation, es. 'grain.duration') e' il path engine.
        path = cfg.get("path", name)
        if "interpolation" in cfg:
            _check_interpolation(
                cfg["interpolation"], ctx,
                key=("axes", name, "interpolation"), axis=name,
            )
        # Generatore Y riconosciuto dalla forma (values | ramp | base): chiave
        # canonica values|ramp|band, con i parametri della banda raccolti piatti.
        with ctx.wrapping(key=("axes", name), axis=name):
            gen_key, gen_params = y_generator(cfg)
        _check_generator_complete(name, gen_key, gen_params, ctx)
        x_cfg = (stack_axes or {}).get(name)
        defers = gen_key == "band" and "n" not in gen_params
        if defers:
            # n-ownership, verso X: solo la camminata-X 'base' puo' possedere n.
            if not x_owns_n(x_cfg):
                raise ctx.err(
                    f"Asse '{name}': banda senza 'n' richiede la camminata-X "
                    "'base' nel blocco 'stack:' (e' la X a possedere n).",
                    key=("axes", name),
                    axis=name,
                    hint=f"dichiara 'n' nella banda (axes.{name}.n) oppure la "
                    f"camminata sotto 'stack: {{{name}: {{base: ...}}}}'.",
                )
            values: List[float] = []
        else:
            # n-ownership, verso Y: con la camminata-X la Y non puo' contare i valori.
            if x_owns_n(x_cfg):
                raise ctx.err(
                    f"Asse '{name}': la camminata-X 'base' possiede n, ma il "
                    f"generatore Y '{gen_key}' enumera i valori.",
                    key=("stack", name),
                    axis=name,
                    hint=f"usa la banda senza 'n' su axes.{name}, oppure togli "
                    f"la camminata-X (stack.{name}).",
                )
            # Seam sweep/Y dei generatori annidati: i nodi dentro gli Env
            # (base/range della banda, step del ramp) si compilano in
            # breakpoint qui, col seed effettivo gia' risolto.
            with ctx.wrapping(key=("axes", name), axis=name):
                if gen_key == "values":
                    values = list(gen_params)
                elif gen_key == "ramp":
                    params = expand_params(gen_params, seed=default_y_seed)
                    values = ramp(**params)
                else:  # band con n: la Y possiede il conteggio
                    params = dict(gen_params)
                    params.setdefault("seed", default_y_seed)
                    values = band(**expand_params(params, seed=params["seed"]))
        axes.append(
            Axis(
                name=name,
                path=path,
                baseline=_resolve_baseline(
                    name, cfg, _defaults_cache, ctx, _grain_unit
                ),
                values=values,
                interpolation=cfg.get("interpolation", study_interpolation),
                generator={gen_key: gen_params},
            )
        )
    if stack_axes:
        axis_names = {ax.name for ax in axes}
        unknown = set(stack_axes) - axis_names
        if unknown:
            raise ctx.err(
                f"stack: assi sconosciuti {sorted(unknown)}.",
                key=("stack",),
                hint=f"gli assi dichiarati in 'axes:' sono {sorted(axis_names)}.",
            )
    # Il documento qui puo' essere il merge di uno stream: ``duration`` e'
    # assente solo se lo stream non ne risolve nessuna, ne' propria ne'
    # ereditata da ``base.duration`` (che e' un default, non un vincolo).
    if stack_axes is not None and duration is None:
        raise ctx.err(
            "stack: lo stream non risolve nessuna 'duration' (ne' propria "
            "ne' ereditata da 'base.duration').",
            key=("stack",),
            hint="dichiara 'base: {duration: <secondi>}' (default per tutti "
            "gli stream) oppure 'duration:' nella entry dello stream.",
        )
    orderings = [list(o) for o in sweep_cfg.get("orderings", [])]
    # Default di ``orders`` condizionato dalla presenza di ``orderings``: se
    # l'utente ha gia' scelto combinazioni esplicite, non aggiungiamo tutte le
    # automatiche a sua insaputa (assetto chirurgico). Senza orderings resta il
    # default storico [1..n] (copertura completa). ``orders`` scritto esplicito
    # vince sempre. Vedi tabella in _validate per la ridondanza.
    if "orders" in sweep_cfg:
        orders = list(sweep_cfg["orders"])
    elif orderings:
        orders = []
    else:
        orders = list(range(1, len(axes) + 1))
    orders_explicit = "orders" in sweep_cfg
    # Riavvolge i ValueError nudi di ``parse_config`` in SpecError col path del
    # blocco, cosi' un ``alpha`` fuori sede o una chiave sconosciuta portano la
    # posizione come ogni altro errore di parse (issue #37).
    with ctx.wrapping(key=("gain_compensation",)):
        gain_compensation = gainmap.parse_config(data)
    spec = StudySpec(
        study_id=sid,
        title=data.get("title"),
        seed=data.get("seed"),
        duration=duration,
        onset=onset,
        samples_dir=data.get("samples_dir"),
        base=dict(data.get("base") or {}),
        axes=axes,
        orders=orders,
        orderings=orderings,
        mode=sweep_cfg.get("mode", "discrete"),
        plateau=float(sweep_cfg.get("plateau", 5.0)),
        transition=float(sweep_cfg.get("transition", 5.0)),
        interpolation=axes_raw.get("interpolation", "linear"),
        stream_id=sweep_cfg.get("stream_id") or None,
        stack=stack_axes,
        stack_seed=stack_seed,
        stack_unit=stack_unit,
        axes_seed=axes_seed,
        gain_compensation=gain_compensation,
    )
    _validate(spec, ctx, orders_explicit=orders_explicit)
    return spec


def load_study_spec(path: str) -> StudySpec:
    """Carica e valida ``study.yml`` da disco (con posizioni per gli errori)."""
    data, locs = yaml_loc.load(path)
    study_id = data.get("study_id") or os.path.basename(os.path.dirname(os.path.abspath(path)))
    return parse_study_spec(data, study_id=study_id, locs=locs)
