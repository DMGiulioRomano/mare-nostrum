"""Generazione combinatoria delle varianti: OAT -> fattoriale completo.

Per ogni ordine k richiesto si prendono tutte le combinazioni di k assi e, per
ciascuna, il prodotto cartesiano dei loro valori di test; gli assi non
selezionati restano alla baseline. Ogni variante e' *completamente* specificata
(tutti gli assi hanno un valore), cosi' le varianti sono direttamente
confrontabili. L'ordine 0 (tutte le baseline) e' la variante di riferimento.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import Any, Dict, List

from .study_spec import StudySpec
from .yaml_builder import build_document


def _fmt(value: Any) -> str:
    """Formatta un valore per il nome file: niente zeri di coda inutili."""
    if isinstance(value, float):
        if value == int(value):
            return str(int(value))
        return repr(value).rstrip("0").rstrip(".")
    return str(value)


@dataclass(frozen=True)
class Variant:
    name: str
    order: int
    moved: List[str]              # nomi degli assi mossi rispetto alla baseline
    values: Dict[str, float]      # nome asse -> valore (tutti gli assi)

    def overrides(self, spec: StudySpec, *, output_sr: int = 48000) -> Dict[str, float]:
        """path YAML -> valore per ogni asse.

        Nessun clamp: i valori enumerabili sono gia' validati (e bloccati se
        fuori bounds) al parse — il clamp per correttezza avviene una volta
        sola, li'. ``output_sr`` resta nella firma per simmetria coi consumer.
        """
        return {ax.path: self.values[ax.name] for ax in spec.axes}

    def to_document(self, spec: StudySpec, *, output_sr: int = 48000) -> Dict[str, Any]:
        base = dict(spec.base)
        base.setdefault("stream_id", "stream")  # l'engine lo richiede
        return build_document(
            base,
            self.overrides(spec, output_sr=output_sr),
            title=f"{spec.study_id} :: {self.name}",
            seed=spec.seed,
            duration=spec.duration,
        )


def _name(order: int, moved_values: Dict[str, float]) -> str:
    if not moved_values:
        return "o0__baseline"
    parts = [f"{ax}={_fmt(v)}" for ax, v in sorted(moved_values.items())]
    return f"o{order}__" + "__".join(parts)


def generate_discrete_variants(spec: StudySpec) -> List[Variant]:
    """Enumera le varianti *discrete* per gli ordini richiesti, deduplicando.

    In ``mode: envelope`` la pipeline discrete non produce nulla (le varianti
    dinamiche sono generate da ``envelope_sweep.generate_envelope_variants``);
    ``discrete`` e ``both`` generano il set statico completo.
    """
    if spec.mode == "envelope":
        return []
    baseline = {ax.name: ax.baseline for ax in spec.axes}
    seen_vectors: set = set()
    variants: List[Variant] = []

    for order in sorted(set(spec.orders)):
        if order == 0:
            vec = tuple(sorted(baseline.items()))
            if vec not in seen_vectors:
                seen_vectors.add(vec)
                variants.append(Variant("o0__baseline", 0, [], dict(baseline)))
            continue

        for combo in itertools.combinations(spec.axes, order):
            value_lists = [ax.values for ax in combo]
            for picked in itertools.product(*value_lists):
                values = dict(baseline)
                moved_values: Dict[str, float] = {}
                for ax, val in zip(combo, picked):
                    values[ax.name] = val
                    moved_values[ax.name] = val
                vec = tuple(sorted(values.items()))
                if vec in seen_vectors:
                    continue
                seen_vectors.add(vec)
                variants.append(
                    Variant(
                        name=_name(order, moved_values),
                        order=order,
                        moved=[ax.name for ax in combo],
                        values=values,
                    )
                )
    return variants


# Alias di backward-compat: i consumatori storici importano ``generate_variants``.
generate_variants = generate_discrete_variants
