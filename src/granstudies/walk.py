"""Generazione del percorso fra stati: random-walk seedabile o percorso autoriale.

Il random-walk attraversa il grafo di adiacenza rispettando i vincoli di
permanenza (``dwell``) di ogni stato; il dwell di ogni tappa e' campionato in
modo deterministico dal seed. Il percorso autoriale e' una sequenza esplicita di
stati (con dwell/transizioni opzionali) validata contro le definizioni.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .states import State, states_by_id


@dataclass(frozen=True)
class Step:
    """Una tappa del percorso: stato, permanenza, durata di transizione verso il prossimo."""

    state_id: str
    dwell: float
    transition: float  # secondi per migrare verso lo step successivo (0 sull'ultimo)


def _sample_dwell(state: State, rng: random.Random) -> float:
    lo, hi = state.dwell
    if hi <= lo:
        return lo
    return rng.uniform(lo, hi)


def random_walk(
    states: List[State],
    adjacency: Dict[str, List[str]],
    *,
    start: str,
    steps: int,
    seed: int,
) -> List[Step]:
    """Cammino casuale di ``steps`` tappe a partire da ``start``.

    Deterministico per dato ``seed``. Se uno stato non ha vicini, il cammino si
    ferma in anticipo (vicolo cieco). La transizione fra due tappe usa la
    ``transition_speed`` dello stato di partenza.
    """
    by_id = states_by_id(states)
    if start not in by_id:
        raise KeyError(f"Stato di partenza sconosciuto: {start}")
    rng = random.Random(seed)

    path_ids: List[str] = [start]
    for _ in range(max(0, steps - 1)):
        current = path_ids[-1]
        neighbors = adjacency.get(current, [])
        if not neighbors:
            break
        path_ids.append(rng.choice(sorted(neighbors)))

    out: List[Step] = []
    for i, sid in enumerate(path_ids):
        state = by_id[sid]
        is_last = i == len(path_ids) - 1
        out.append(
            Step(
                state_id=sid,
                dwell=_sample_dwell(state, rng),
                transition=0.0 if is_last else state.transition_speed,
            )
        )
    return out


def authored_path(states: List[State], path_spec: List[Dict[str, Any]]) -> List[Step]:
    """Costruisce gli Step da un percorso esplicito.

    Ogni elemento: ``{state: id, dwell?: float, transition?: float}``. I default
    sono il punto medio del dwell dello stato e la sua ``transition_speed``.
    """
    by_id = states_by_id(states)
    if not path_spec:
        raise ValueError("Percorso autoriale vuoto.")
    out: List[Step] = []
    for i, item in enumerate(path_spec):
        sid = item["state"]
        if sid not in by_id:
            raise KeyError(f"Stato sconosciuto nel percorso: {sid}")
        state = by_id[sid]
        lo, hi = state.dwell
        dwell = float(item.get("dwell", (lo + hi) / 2.0))
        is_last = i == len(path_spec) - 1
        transition = 0.0 if is_last else float(item.get("transition", state.transition_speed))
        out.append(Step(state_id=sid, dwell=dwell, transition=transition))
    return out
