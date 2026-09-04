"""Definizione degli *stati* compositivi (``states.yml``).

Uno stato e' un punto nello spazio parametri piu' la sua dinamica temporale:
quanto a lungo restarci (``dwell``), con che velocita' migrare
(``transition_speed``), e opzionalmente vincoli espliciti di provenienza/
destinazione (``parents``/``children``) che, se assenti, vengono derivati dalla
matrice di parentela.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import yaml


@dataclass(frozen=True)
class State:
    id: str
    params: Dict[str, float]
    dwell: Tuple[float, float]
    transition_speed: float
    parents: Optional[List[str]] = None
    children: Optional[List[str]] = None
    tags: List[str] = field(default_factory=list)
    descriptors: Dict[str, float] = field(default_factory=dict)


def _parse_dwell(raw: Any) -> Tuple[float, float]:
    if isinstance(raw, (list, tuple)):
        if len(raw) != 2:
            raise ValueError(f"dwell deve avere 2 valori [min, max], ricevuto {raw}")
        lo, hi = float(raw[0]), float(raw[1])
    else:
        lo = hi = float(raw)
    if lo > hi:
        raise ValueError(f"dwell min > max: {raw}")
    if lo < 0:
        raise ValueError(f"dwell negativo: {raw}")
    return (lo, hi)


def parse_states(data: Dict[str, Any]) -> List[State]:
    raw_states = data.get("states") or []
    if not raw_states:
        raise ValueError("Nessuno stato definito in 'states'.")
    states: List[State] = []
    seen = set()
    for s in raw_states:
        sid = s["id"]
        if sid in seen:
            raise ValueError(f"Stato duplicato: {sid}")
        seen.add(sid)
        speed = float(s.get("transition_speed", 1.0))
        if speed <= 0:
            raise ValueError(f"transition_speed deve essere > 0 (stato {sid}).")
        states.append(
            State(
                id=sid,
                params={k: float(v) for k, v in (s.get("params") or {}).items()},
                dwell=_parse_dwell(s.get("dwell", 1.0)),
                transition_speed=speed,
                parents=s.get("parents"),
                children=s.get("children"),
                tags=list(s.get("tags") or []),
                descriptors={k: float(v) for k, v in (s.get("descriptors") or {}).items()},
            )
        )
    return states


def load_states(path: str) -> List[State]:
    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return parse_states(data)


def states_by_id(states: List[State]) -> Dict[str, State]:
    return {s.id: s for s in states}
