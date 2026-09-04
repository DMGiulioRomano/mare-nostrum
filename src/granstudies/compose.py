"""Composizione: percorso fra stati -> envelope -> YAML finale dell'engine.

Ogni tappa tiene lo stato costante per il suo ``dwell``, poi migra al successivo
interpolando linearmente i parametri lungo la ``transition``. I valori nel tempo
diventano envelope a breakpoint ``[[t, v], ...]`` in ``time_mode: absolute``,
inseriti nello stream alla posizione corretta (es. ``grain.duration``).
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Tuple

from .states import State, states_by_id
from .walk import Step
from .yaml_builder import build_document, deep_set


def build_timeline(steps: List[Step]) -> List[Dict[str, float]]:
    """Converte gli Step in segmenti temporali assoluti.

    Returns: lista di ``{state_id, hold_start, hold_end, trans_end}`` dove
    ``trans_end`` e' l'istante in cui la migrazione verso lo stato successivo
    e' completata (== hold_end sull'ultima tappa).
    """
    timeline: List[Dict[str, float]] = []
    t = 0.0
    for i, step in enumerate(steps):
        hold_start = t
        hold_end = hold_start + step.dwell
        trans_end = hold_end + (step.transition if i < len(steps) - 1 else 0.0)
        timeline.append(
            {
                "state_id": step.state_id,
                "hold_start": hold_start,
                "hold_end": hold_end,
                "trans_end": trans_end,
            }
        )
        t = trans_end
    return timeline


def _dedup(points: List[List[float]]) -> List[List[float]]:
    """Rimuove breakpoint consecutivi identici (stesso t o stesso (t, v))."""
    out: List[List[float]] = []
    for p in points:
        if out and out[-1][0] == p[0]:
            out[-1] = p  # stesso istante: l'ultimo valore vince
            continue
        if out and out[-1][1] == p[1] and len(out) >= 2 and out[-2][1] == p[1]:
            out[-1] = p  # tre valori uguali di fila: collassa il mediano
            continue
        out.append(p)
    return out


def build_envelopes(
    steps: List[Step], states: List[State]
) -> Dict[str, List[List[float]]]:
    """Costruisce, per ogni path parametrico, l'envelope a breakpoint assoluti."""
    by_id = states_by_id(states)
    timeline = build_timeline(steps)

    all_paths: List[str] = []
    for s in states:
        for p in s.params:
            if p not in all_paths:
                all_paths.append(p)

    envelopes: Dict[str, List[List[float]]] = {}
    for path in all_paths:
        points: List[List[float]] = []
        for i, seg in enumerate(timeline):
            state = by_id[seg["state_id"]]
            if path not in state.params:
                continue
            value = state.params[path]
            points.append([round(seg["hold_start"], 6), value])
            points.append([round(seg["hold_end"], 6), value])
            if seg["trans_end"] > seg["hold_end"] and i < len(timeline) - 1:
                nxt = by_id[timeline[i + 1]["state_id"]]
                if path in nxt.params:
                    points.append([round(seg["trans_end"], 6), nxt.params[path]])
        envelopes[path] = _dedup(points)
    return envelopes


def total_duration(steps: List[Step]) -> float:
    timeline = build_timeline(steps)
    return timeline[-1]["trans_end"] if timeline else 0.0


def compose_document(
    steps: List[Step],
    states: List[State],
    base_stream: Mapping[str, Any],
    *,
    title: str | None = None,
    seed: int | None = None,
) -> Dict[str, Any]:
    """Produce il documento YAML finale: singolo stream con envelope per parametro."""
    duration = total_duration(steps)
    envelopes = build_envelopes(steps, states)

    base = dict(base_stream)
    base.setdefault("stream_id", "composition")
    base.setdefault("time_mode", "absolute")
    base["onset"] = 0
    base["duration"] = round(duration, 6)

    overrides: Dict[str, Any] = {}
    for path, env in envelopes.items():
        # Envelope costante (un solo valore): collassa a scalare per pulizia.
        values = {v for _, v in env}
        overrides[path] = env[0][1] if len(values) == 1 else env

    doc = build_document(base, overrides, title=title, seed=seed, duration=round(duration, 6))
    return doc
