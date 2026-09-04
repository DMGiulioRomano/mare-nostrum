"""Processo ``stack``: N stream con lievi variazioni, sommati in un documento.

Il gemello verticale dello sweep. Dove sweep *esplode* gli stream in N file
(varianti enumerate, prodotto cartesiano), stack li *collassa* in un solo YAML
multi-stream. L'invariante: ``axes`` conosce solo Y (valori + interpolation);
il processo possiede X — sweep via plateau/transition (durata derivata), stack
via le strategy-X (``x_strategies``) normalizzate sulla durata dello stream.
``base.duration`` e' il default che ogni stream puo' sovrascrivere con la
propria ``duration:`` di entry (issue #26, #42): camminate-X ed envelope
``time_mode: normalized`` si normalizzano sulla duration *propria* dello
stream, non su quella del documento — che nessuno dichiara, perche' e'
dedotta qui come ``max(onset + duration)``.

In stack gli assi NON si combinano: niente prodotto cartesiano, niente zip.
Ogni asse di uno stream diventa un envelope indipendente sulla stessa durata,
coi suoi valori (Y), i suoi tempi (X) e la sua curva (interpolation).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from . import bounds as bounds_mod
from . import gainmap
from .study_spec import StudySpec
from .value_generators import band, band_at, expand_params, ramp
from .x_strategies import resolve_x, walk, x_owns_n
from .yaml_builder import build_multi_document, build_stream

# Le chiavi-generatore di Y ammesse in un asse, in forma *canonica* (quella con
# cui ``study_spec`` popola ``Axis.generator``): la banda ha chiave ``band``,
# non piu' ``rand``. Nello YAML la banda si riconosce invece dalla presenza di
# ``base`` (vedi ``value_generators.y_generator``).
#
# La Y viene sempre da ``axes:``, che e' Famiglia 1 (i valori di test, letti
# per indice): ``values`` qui resta ``values``, il wrapper ``linear_env:``
# della Famiglia 2 non entra in questo blocco (issue #47).
_Y_KEYS = frozenset({"values", "ramp", "band"})


def _y_generator(y_cfg: Dict[str, Any]) -> tuple[str, Any]:
    """Estrae (nome canonico, params) dell'unica chiave-generatore Y di un asse."""
    keys = [k for k in y_cfg if k in _Y_KEYS]
    if len(keys) != 1:
        opts = ", ".join(sorted(_Y_KEYS))
        raise ValueError(
            f"stack: serve esattamente una chiave-generatore Y tra {{{opts}}}, "
            f"trovate {sorted(keys) or 'nessuna'}."
        )
    return keys[0], y_cfg[keys[0]]


def axis_envelope(
    y_cfg: Dict[str, Any],
    x_cfg: Dict[str, Any] | None,
    duration: float,
    *,
    y_seed: int = 0,
    x_seed: int = 0,
    x_unit: str = "hz",
) -> List[List[float]]:
    """Assembla l'envelope ``[[t, v], ...]`` di un asse: coupling X per Y.

    Due versi, decisi dalla n-ownership (validata in entrambi):

    - **X possiede n** (camminata ``walk``, banda ``base`` nel blocco stack): i
      tempi emergono dalla frequenza; la Y deve essere una banda *senza* ``n`` e
      viene campionata ai tempi reali dei punti (``band_at``). E' la rspline.
    - **Y possiede n** (``values``/``ramp``/banda con ``n``): i valori si
      risolvono per primi e la X distribuisce ``len(values)`` tempi
      (``resolve_x``, ``linear`` per assenza dal blocco).

    ``y_seed``/``x_seed``/``x_unit`` sono i default globali gia' risolti a
    monte (catena di precedenza in ``study_spec``): il ``seed`` (e ``unit``)
    dichiarato dentro la config dell'asse vince sempre (default, non override
    brutale).
    """
    y_key, y_params = _y_generator(y_cfg)

    if x_owns_n(x_cfg):
        if y_key != "band" or "n" in y_params:
            raise ValueError(
                "stack: la camminata-X (banda 'base') possiede n — la Y deve "
                f"essere una banda senza 'n' (trovata '{y_key}'"
                + (" con 'n'" if y_key == "band" and "n" in y_params else "")
                + ")."
            )
        # Seam stack dei generatori annidati: espansione dopo l'iniezione del
        # seed effettivo, sia sulla X (banda di frequenza) sia sulla Y.
        x_params = dict(x_cfg)
        x_params.setdefault("seed", x_seed)
        x_params.setdefault("unit", x_unit)
        x_params = expand_params(x_params, seed=x_params["seed"])
        times = walk(duration=duration, **x_params)
        y_kwargs = dict(y_params)
        y_kwargs.setdefault("seed", y_seed)
        y_kwargs = expand_params(y_kwargs, seed=y_kwargs["seed"])
        values = band_at(times, **y_kwargs)
        return [[t, v] for t, v in zip(times, values)]

    if y_key == "band" and "n" not in y_params:
        raise ValueError(
            "stack: banda Y senza 'n' richiede la camminata-X (banda 'base' nel "
            "blocco 'stack:'); con X lineare dichiara 'n' nella banda Y."
        )
    if y_key == "values":
        values = list(y_params)
    elif y_key == "ramp":
        values = ramp(**expand_params(y_params, seed=y_seed))
    else:  # band con n
        y_kwargs = dict(y_params)
        y_kwargs.setdefault("seed", y_seed)
        values = band(**expand_params(y_kwargs, seed=y_kwargs["seed"]))
    times = resolve_x(x_cfg, n=len(values))
    return [[t, v] for t, v in zip(times, values)]


def build_stack_stream(
    spec: StudySpec, *, output_sr: Optional[int] = 48000
) -> Dict[str, Any]:
    """Costruisce il dict engine di *uno* stream del processo stack.

    Per ogni asse l'envelope si assembla con ``axis_envelope`` (X della
    strategy per-stream, seed per precedenza) e i valori si clampano ai bounds
    engine — i valori *espliciti* fuori bounds falliscono gia' al parse, qui
    si proteggono quelli che emergono (Y-rand). ``output_sr`` attiva il floor
    dinamico di ``grain.duration`` (1 campione invece del fallback statico di
    1ms, issue #17): deve combaciare col sample rate usato in render.

    Regola scalare (stream statici legittimi): sequenza di un solo punto ->
    valore secco via ``deep_set``, non envelope costante.
    """
    if spec.duration is None:
        raise ValueError(
            f"stack [{spec.stream_id or spec.study_id}]: nessuna 'duration' "
            "risolta (ne' propria dello stream ne' ereditata da 'base.duration')."
        )
    base = dict(spec.base)
    base["stream_id"] = spec.stream_id or "stream"
    base["time_mode"] = "normalized"
    # Scrittura *incondizionata*, al contrario della riga gemella per l'onset
    # qui sotto: ``spec.duration`` e' gia' la catena ``duration:`` di entry >
    # ``base.duration`` risolta al parse (#42), quindi una eventuale
    # ``base.duration`` presente in ``spec.base`` e' o lo stesso valore o
    # quello che l'override di entry ha appena scavalcato. Renderla
    # condizionale perderebbe l'override.
    base["duration"] = spec.duration
    # L'onset per-stream (issue #26) vince su un eventuale ``base.onset``
    # ereditato; non dichiarato (None) lo lascia intatto.
    if spec.onset is not None:
        base["onset"] = spec.onset
    grain_unit = base.get("grain", {}).get("duration_unit")
    overrides: Dict[str, Any] = {}
    types: Dict[str, str] = {}
    for ax in spec.axes:
        env = axis_envelope(
            ax.generator,
            (spec.stack or {}).get(ax.name),
            spec.duration,
            y_seed=spec.resolved_y_seed(),
            x_seed=spec.resolved_x_seed(),
            x_unit=spec.resolved_x_unit(),
        )
        unit = grain_unit if ax.path == "grain.duration" else None
        env = [
            [t, bounds_mod.clamp(
                ax.path, v, output_sr=output_sr, unit=unit
            )]
            for t, v in env
        ]
        if len(env) == 1:
            overrides[ax.path] = env[0][1]
        else:
            overrides[ax.path] = env
            types[ax.path] = ax.interpolation
    return build_stream(
        base,
        overrides,
        envelope_time_mode="normalized",
        envelope_types=types,
    )


def generate_stack_document(
    specs: List[StudySpec],
    *,
    output_sr: Optional[int] = 48000,
    samples_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """Collassa gli stream di uno studio in un documento engine multi-stream.

    Un elemento di ``streams:`` per ogni spec (una per stream, da
    ``resolve_streams``), costruito da ``build_stack_stream``.

    Col blocco ``gain_compensation:`` e un ``samples_dir`` risolto, gli stream
    ricevono qui l'offset di ``volume`` che pareggia il mascheramento fra punti
    di lettura diversi dello stesso buffer (v. ``gainmap``).
    """
    if not specs:
        raise ValueError("generate_stack_document: serve almeno uno spec.")
    built = [build_stack_stream(spec, output_sr=output_sr) for spec in specs]
    first = specs[0]
    if first.gain_compensation and samples_dir:
        gainmap.compensate(
            built,
            samples_dir=samples_dir,
            output_sr=output_sr or 48000,
            **first.gain_compensation,
        )
    return build_multi_document(
        built,
        title=f"{first.study_id} :: stack",
        seed=first.seed,
        # La durata documento copre anche gli stream spostati in avanti
        # (onset per-stream o base.onset): sv_export la usa per l'end frame.
        duration=max(
            float(s.get("onset", 0) or 0) + s["duration"] for s in built
        ),
    )
