"""Bounds dei parametri per clamping e normalizzazione delle distanze.

Tutti i bounds vengono dall'engine — single source of truth, niente tabelle
copiate: il registry ``parameter_definitions.GRANULAR_PARAMETERS`` per i
parametri registrati (mappa path->chiave derivata da ``ALL_SCHEMAS``),
``PitchUnit.value_bounds`` per i path ``pitch.<unita'>``, che unit-driven non
sono nel registry.

Le chiavi sono i path YAML *dotted* (es. ``grain.duration``), come usati nello
``study.yml`` e nelle definizioni di stato.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Dict, Optional, Tuple

# Path noti al registry dell'engine ma assenti da ``ALL_SCHEMAS`` (non hanno
# una voce di schema YAML): unica tabella rimasta a mano. Tutto il resto viene
# da ``engine_bridge.parameter_schema_paths``.
_EXTRA_PATHS: Dict[str, str] = {
    "pointer.deviation": "pointer_deviation",
    "num_voices": "num_voices",
    "scatter": "scatter",
}

_PITCH_PREFIX = "pitch."


@lru_cache(maxsize=1)
def _path_map() -> Dict[str, str]:
    """path YAML dotted -> chiave nel registry, derivata dagli schema engine."""
    from .engine_bridge import parameter_bounds, parameter_schema_paths

    registry = parameter_bounds()
    # ``pointer.start`` sta negli schema ma non nel registry: nessun bound da
    # confrontare, quindi resta fuori dai path noti.
    return {
        **{p: k for p, k in parameter_schema_paths().items() if k in registry},
        **_EXTRA_PATHS,
    }


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
    """Tutti i path dotted noti: registry engine + le unita' di ``pitch.*``."""
    from .engine_bridge import pitch_units

    return frozenset(_path_map()) | frozenset(
        _PITCH_PREFIX + u for u in pitch_units()
    )


# Path il cui dominio non e' un intervallo ma un elenco di nomi: i bounds non
# li descrivono (``grain.envelope`` non ha min/max), il catalogo dell'engine
# si'. Stessa regola dei bounds: nessuna tabella copiata qui, solo il ponte.
_CATEGORICAL: Dict[str, str] = {
    "grain.envelope": "window_names",
}


def categorical_domain(path: str) -> Optional[frozenset]:
    """I nomi ammessi per un path categoriale, o ``None`` se il path non lo e'.

    Un asse su un path categoriale enumera stringhe (``[hanning, expodec, ...]``)
    invece di numeri: e' il dominio che lo dice, non il tipo dei valori scritti.
    """
    fn = _CATEGORICAL.get(path)
    if fn is None:
        return None
    from . import engine_bridge

    return getattr(engine_bridge, fn)()


def bounds_for(
    path: str,
    output_sr: Optional[int] = None,
) -> Optional[Tuple[Optional[float], Optional[float]]]:
    """(min, max) per un path, o ``None`` se sconosciuto.

    I bounds vengono dall'engine: il registry dei parametri per i path di
    ``ALL_SCHEMAS``, ``PitchUnit.value_bounds`` per i path ``pitch.<unita'>``
    (l'ultimo segmento e' il nome dell'unita', come nel blocco ``pitch:`` dello
    YAML).

    ``max`` puo' essere ``None`` (bound dinamico nell'engine): i ``loop_*``
    dipendono dalla durata del sample, che qui non si conosce, quindi di quelli
    si valida solo il minimo.

    ``output_sr`` di default e' quello di render dell'engine, cosi' il minimo di
    ``grain.duration`` e' sempre il pavimento dinamico (1 campione) e mai il
    fallback statico di 1 ms: ometterlo non deve cambiare il verdetto (issue #17).
    """
    if path.startswith(_PITCH_PREFIX):
        from .engine_bridge import pitch_bounds

        try:
            pb = pitch_bounds(path[len(_PITCH_PREFIX):])
        except Exception:
            return None
        return (pb.min_val, pb.max_val)
    key = _path_map().get(path)
    if key is None:
        return None
    from .engine_bridge import parameter_bounds

    sr = output_sr or default_output_sr()
    pb = parameter_bounds(output_sr=sr)[key]
    return (pb.min_val, pb.max_val)


def default_output_sr() -> int:
    """Sample rate di render di default dell'engine (single source)."""
    from .engine_bridge import default_output_sr as _sr

    return _sr()


def _bounds_in_unit(
    path: str,
    *,
    unit: Optional[str] = None,
    output_sr: Optional[int] = None,
) -> Optional[Tuple[Optional[float], Optional[float]]]:
    """Bounds del path riportati nell'unita' del valore da confrontare.

    ``unit`` ha senso solo per ``grain.duration`` (l'unico parametro con
    un'unita' dichiarabile nello YAML, ``stream.py:415``): sugli altri path
    viene ignorato.
    """
    sr = output_sr or default_output_sr()
    b = bounds_for(path, output_sr=sr)
    if b is None:
        return None
    lo, hi = b
    factor = grain_duration_factor(
        unit if path == "grain.duration" else None, sr
    )
    if factor != 1.0:
        lo = None if lo is None else lo / factor
        hi = None if hi is None else hi / factor
    return lo, hi


def violation(
    path: str,
    value: float,
    *,
    unit: Optional[str] = None,
    output_sr: Optional[int] = None,
) -> Optional[Tuple[Optional[float], Optional[float]]]:
    """I bounds *in secondi* se ``value`` li sfora, altrimenti ``None``.

    Unico punto in cui si decide se un valore e' ammesso: il confronto avviene
    nell'unita' di ``value`` (vedi ``_bounds_in_unit``), il ritorno e' in
    secondi perche' e' il dominio in cui i bounds sono dichiarati e in cui ha
    senso mostrarli in un errore.
    """
    b = _bounds_in_unit(path, unit=unit, output_sr=output_sr)
    if b is None:
        return None
    lo, hi = b
    if (lo is not None and value < lo) or (hi is not None and value > hi):
        return bounds_for(path, output_sr=output_sr)
    return None


def clamp(
    path: str,
    value: float,
    *,
    output_sr: Optional[int] = None,
    unit: Optional[str] = None,
) -> float:
    """Riporta ``value`` entro i bounds del path (no-op se path sconosciuto).

    ``unit``: unita' in cui e' espresso ``value``, quando il path e'
    ``grain.duration`` e lo stream dichiara un ``grain.duration_unit``
    (stream.py:415). Il ritorno resta nell'unita' di partenza.
    """
    b = _bounds_in_unit(path, unit=unit, output_sr=output_sr)
    if b is None:
        return value
    lo, hi = b
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
