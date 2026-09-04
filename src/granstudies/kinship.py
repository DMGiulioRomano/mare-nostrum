"""Matrice di parentela tra stati: similarity + derivazione del grafo.

La similarity combina tre contributi normalizzati in [0, 1]:
  - distanza nello spazio parametri (normalizzata sui bounds dell'engine);
  - distanza nei descrittori audio (se presenti su entrambi gli stati);
  - complemento dell'overlap dei tag manuali (Jaccard).
Pesi configurabili. Da una soglia si derivano gli archi del grafo (chi e'
abbastanza simile da poter essere genitore/figlio), salvo override manuali.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional

from . import bounds as bounds_mod
from .states import State


@dataclass(frozen=True)
class Weights:
    params: float = 0.6
    descriptors: float = 0.2
    tags: float = 0.2


def _normalized_param_distance(a: State, b: State) -> Optional[float]:
    """Distanza euclidea media sui path condivisi, normalizzata sui bounds.

    Ogni componente e' (|va-vb| / span) clampata a 1; la distanza e' la radice
    della media dei quadrati. ``None`` se non ci sono path condivisi.
    """
    shared = set(a.params) & set(b.params)
    if not shared:
        return None
    acc = 0.0
    for path in shared:
        span = bounds_mod.span(path)
        diff = abs(a.params[path] - b.params[path])
        comp = diff / span if span else (0.0 if diff == 0 else 1.0)
        comp = min(comp, 1.0)
        acc += comp * comp
    return math.sqrt(acc / len(shared))


def _normalized_descriptor_distance(a: State, b: State) -> Optional[float]:
    """Distanza sui descrittori condivisi, normalizzata per-campo dalla coppia.

    Senza un range globale dei descrittori, si normalizza ogni campo sul max dei
    due valori (scala relativa). ``None`` se non ci sono descrittori condivisi.
    """
    shared = set(a.descriptors) & set(b.descriptors)
    if not shared:
        return None
    acc = 0.0
    for key in shared:
        va, vb = a.descriptors[key], b.descriptors[key]
        denom = max(abs(va), abs(vb))
        comp = abs(va - vb) / denom if denom > 0 else 0.0
        comp = min(comp, 1.0)
        acc += comp * comp
    return math.sqrt(acc / len(shared))


def _tag_distance(a: State, b: State) -> Optional[float]:
    """1 - Jaccard sui tag. ``None`` se entrambi senza tag."""
    sa, sb = set(a.tags), set(b.tags)
    if not sa and not sb:
        return None
    union = sa | sb
    if not union:
        return None
    return 1.0 - len(sa & sb) / len(union)


def similarity(a: State, b: State, weights: Weights = Weights()) -> float:
    """Similarity in [0, 1]: 1 = identici. Pesi riscalati sui contributi attivi."""
    contribs = [
        (_normalized_param_distance(a, b), weights.params),
        (_normalized_descriptor_distance(a, b), weights.descriptors),
        (_tag_distance(a, b), weights.tags),
    ]
    active = [(d, w) for d, w in contribs if d is not None and w > 0]
    if not active:
        return 0.0
    total_w = sum(w for _, w in active)
    distance = sum(d * w for d, w in active) / total_w
    return 1.0 - distance


def kinship_matrix(states: List[State], weights: Weights = Weights()) -> Dict[str, object]:
    """Matrice simmetrica di similarity. Diagonale = 1.0."""
    ids = [s.id for s in states]
    matrix: List[List[float]] = []
    for i, a in enumerate(states):
        row: List[float] = []
        for j, b in enumerate(states):
            if i == j:
                row.append(1.0)
            elif j < i:
                row.append(matrix[j][i])
            else:
                row.append(similarity(a, b, weights))
        matrix.append(row)
    return {"ids": ids, "matrix": matrix}


def derive_edges(
    kin: Dict[str, object], threshold: float
) -> Dict[str, List[str]]:
    """Archi non orientati: per ogni stato, i vicini con similarity >= soglia."""
    ids = list(kin["ids"])  # type: ignore[index]
    matrix = kin["matrix"]  # type: ignore[index]
    edges: Dict[str, List[str]] = {sid: [] for sid in ids}
    for i, sid in enumerate(ids):
        for j, other in enumerate(ids):
            if i != j and matrix[i][j] >= threshold:  # type: ignore[index]
                edges[sid].append(other)
    return edges


def adjacency(
    states: List[State], kin: Dict[str, object], threshold: float
) -> Dict[str, List[str]]:
    """Adiacenza effettiva: override manuali (children) o archi derivati.

    Se uno stato definisce ``children`` espliciti, quelli prevalgono; altrimenti
    si usano i vicini derivati dalla matrice via soglia.
    """
    derived = derive_edges(kin, threshold)
    out: Dict[str, List[str]] = {}
    for s in states:
        if s.children is not None:
            out[s.id] = list(s.children)
        else:
            out[s.id] = derived.get(s.id, [])
    return out
