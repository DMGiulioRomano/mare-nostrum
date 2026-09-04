"""Bounds dei parametri per clamping e normalizzazione delle distanze.

I bounds dei parametri registrati derivano dall'engine
(``parameter_definitions.GRANULAR_PARAMETERS``) — single source of truth, niente
duplicazione. I parametri unit-driven (pitch) non sono nel registry e sono
aggiunti qui a mano, come documentato in ``parameter_definitions.py``.

Le chiavi sono i path YAML *dotted* (es. ``grain.duration``), come usati nello
``study.yml`` e nelle definizioni di stato.
"""
from __future__ import annotations

from typing import Dict, Optional, Tuple

# path YAML dotted -> chiave nel registry dell'engine
_PATH_TO_ENGINE_KEY: Dict[str, str] = {
    "density": "density",
    "distribution": "distribution",
    "fill_factor": "fill_factor",
    "grain.duration": "grain_duration",
    "pan": "pan",
    "volume": "volume",
    "pointer.speed_ratio": "pointer_speed_ratio",
    "pointer.deviation": "pointer_deviation",
    "scatter": "scatter",
    "num_voices": "num_voices",
}

# path non presenti nel registry (bounds unit-driven o derivati): valori manuali
# coerenti coi commenti in parameter_definitions.py (EDO ±3 ottave).
_MANUAL_BOUNDS: Dict[str, Tuple[float, float]] = {
    "pitch.semitones": (-36.0, 36.0),
    "pitch.cents": (-3600.0, 3600.0),
}

# Minimo di grain.duration in campioni imposto da questo studio (l'engine
# scende a 1 campione). Vedi ``bounds_for``.
MIN_GRAIN_SAMPLES = 4

# Unita' ammesse per ``grain.duration``/``grain.duration_range``, come
# l'engine (``pge.core.stream.GRAIN_DURATION_UNITS``). I bounds del registry
# sono in secondi: qui vive la conversione verso quel dominio.
GRAIN_DURATION_UNITS = ("seconds", "samples", "milliseconds")

_MS_PER_SECOND = 1000.0


def grain_duration_factor(
    unit: Optional[str],
    output_sr: Optional[int] = None,
) -> float:
    """Fattore che porta un valore di ``grain.duration`` in secondi.

    ``seconds`` (o unita' assente) -> 1.0; ``milliseconds`` -> 1e-3;
    ``samples`` -> ``1/output_sr``, l'unica unita' che dipende dal sample rate
    e quindi l'unica che pretende ``output_sr``.
    """
    if unit is None or unit == "seconds":
        return 1.0
    if unit == "milliseconds":
        return 1.0 / _MS_PER_SECOND
    if unit == "samples":
        if output_sr is None:
            raise ValueError("l'unita' 'samples' richiede output_sr")
        return 1.0 / output_sr
    raise ValueError(
        f"unita' di grain.duration sconosciuta: {unit!r} "
        f"(ammesse: {list(GRAIN_DURATION_UNITS)})"
    )


def known_paths() -> frozenset:
    """Tutti i path dotted noti (registry engine + manuali), senza import engine."""
    return frozenset(_PATH_TO_ENGINE_KEY) | frozenset(_MANUAL_BOUNDS)


def bounds_for(
    path: str,
    output_sr: Optional[int] = None,
) -> Optional[Tuple[Optional[float], Optional[float]]]:
    """(min, max) per un path, o ``None`` se sconosciuto.

    ``max`` puo' essere ``None`` (bound dinamico nell'engine, es. loop_*).
    ``output_sr``, se fornito, attiva i bound dinamici dell'engine: il minimo
    di ``grain.duration`` diventa 1 campione (``1/output_sr``) invece del
    fallback statico di 1ms (issue #17).
    """
    if path in _MANUAL_BOUNDS:
        return _MANUAL_BOUNDS[path]
    key = _PATH_TO_ENGINE_KEY.get(path)
    if key is None:
        return None
    from .engine_bridge import parameter_bounds

    pb = parameter_bounds(output_sr=output_sr)[key]
    lo = pb.min_val
    if path == "grain.duration" and output_sr:
        # Floor dello studio: l'engine ammette 1 campione, ma sotto i 4 campioni
        # il grano non ha inviluppo udibile. Vincolo di questo repo, non engine.
        lo = max(lo, MIN_GRAIN_SAMPLES / output_sr)
    return (lo, pb.max_val)


def default_output_sr() -> int:
    """Sample rate di render di default dell'engine (single source)."""
    from .engine_bridge import default_output_sr as _sr

    return _sr()


def clamp(
    path: str,
    value: float,
    *,
    output_sr: Optional[int] = None,
    unit: Optional[str] = None,
) -> float:
    """Riporta ``value`` entro i bounds del path (no-op se path sconosciuto).

    ``output_sr``, se fornito, attiva il floor dinamico di ``grain.duration``
    (vedi ``bounds_for``) invece del fallback statico di 1ms.

    ``unit``: unita' in cui e' espresso ``value``, quando il path e'
    ``grain.duration`` e lo stream dichiara un ``grain.duration_unit``
    (stream.py:415). I bounds del registry sono in secondi, quindi vengono
    riportati nell'unita' di ``value`` prima del confronto; il ritorno resta
    nell'unita' di partenza.
    """
    b = bounds_for(path, output_sr=output_sr)
    if b is None:
        return value
    lo, hi = b
    factor = grain_duration_factor(unit, output_sr)
    if factor != 1.0:
        lo = None if lo is None else lo / factor
        hi = None if hi is None else hi / factor
    if lo is not None and value < lo:
        return lo
    if hi is not None and value > hi:
        return hi
    return value


def span(path: str) -> Optional[float]:
    """Ampiezza (max-min) di un path, per normalizzare le distanze.

    Ritorna ``None`` se i bounds non sono entrambi finiti.
    """
    b = bounds_for(path)
    if b is None:
        return None
    lo, hi = b
    if lo is None or hi is None:
        return None
    width = float(hi) - float(lo)
    return width if width > 0 else None
