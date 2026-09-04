"""Modalita' ``envelope`` dello sweep: stream dinamici a plateau in cascata.

A differenza dello sweep ``discrete`` (un file statico per combinazione), la
modalita' envelope produce **un** file per combinazione di assi, in cui i
parametri attraversano tutte le permutazioni dei valori tramite breakpoint
temporali sincronizzati. Ogni combinazione occupa un *plateau* (ascolto stabile)
e si raggiunge la successiva via una *transition* lineare.

I tempi sono normalizzati in ``[0, 1]`` (``time_mode: normalized`` sullo stream);
la ``duration`` reale dello stream e' calcolata da ``plateau``/``transition``.

Vedi issue #2 (granulation-studies) per le decisioni di design.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import Any, Dict, List

from .study_spec import Axis, StudySpec


def envelope_breakpoints(
    values: List[float],
    plateau: float,
    transition: float,
    *,
    step: bool = False,
    plateau_single: bool = False,
) -> List[List[float]]:
    """Breakpoint normalizzati ``[[t, v], ...]`` per una sequenza di plateau.

    Con ``step=True`` (envelope ``type: step``) plateau e transizione collassano:
    l'engine tiene ogni valore fino al breakpoint successivo e poi salta netto,
    quindi il doppio punto per plateau e' ridondante. Si emette **un solo punto
    per valore**, equispaziato in ``[0, 1]`` (``t_i = i / N``); l'ultimo valore
    e' tenuto fino a fine stream dall'engine. La durata reale (un ``transition``
    per gradino) e' governata da ``EnvelopeVariant.duration``.

    Per ``N = len(values)`` plateau, ogni plateau occupa ``W_plateau`` e ogni
    transizione ``W_transition`` della durata totale normalizzata::

        total        = N * plateau + (N - 1) * transition
        W_plateau    = plateau / total
        W_transition = transition / total

    Il plateau ``i`` (0-indexed) va da ``t_start = i * (W_plateau + W_transition)``
    a ``t_end = t_start + W_plateau``; la transizione verso il plateau successivo
    avviene nel gap tra ``t_end`` e il ``t_start`` del prossimo (interpolazione
    lineare a carico dell'engine).

    Con ``plateau_single=True`` (asse ``step`` che *convive* con assi non-step
    nello stesso file) si tiene la stessa griglia a plateau — durata piena — ma
    si emette **un solo punto per valore** al ``t_start`` del plateau (layout C):
    i due breakpoint identici del layout plateau sono ridondanti sotto ``step``,
    perche' l'engine tiene il valore fino al punto successivo e poi salta. Il
    salto cade cosi' sull'inizio del plateau successivo, sincronizzato con gli
    assi non-step. L'ultimo valore e' tenuto fino a fine stream dall'engine.

    Caso ``N == 1``: unico plateau costante ``[[0, v], [1, v]]``.
    """
    n = len(values)
    if n == 0:
        return []
    if n == 1:
        return [[0.0, values[0]], [1.0, values[0]]]

    if step:
        return [[round(i / n, 6), v] for i, v in enumerate(values)]

    total = n * plateau + (n - 1) * transition
    w_plateau = plateau / total
    w_transition = transition / total
    step_w = w_plateau + w_transition

    points: List[List[float]] = []
    for i, v in enumerate(values):
        t_start = i * step_w
        points.append([round(t_start, 6), v])
        # plateau a larghezza zero (plateau=0): il t_end coinciderebbe col t_start,
        # un doppione inutile. Solo transizioni -> un punto per valore.
        if not plateau_single and w_plateau > 0:
            t_end = t_start + w_plateau
            points.append([round(t_end, 6), v])
    points[0][0] = 0.0
    if not plateau_single:
        # L'ultimo t_end deve cadere esattamente su 1.0 (no deriva float).
        points[-1][0] = 1.0
    return points


def cartesian_combinations(axes: List[Axis]) -> List[Dict[str, float]]:
    """Prodotto cartesiano lessicografico dei valori degli assi.

    Restituisce la lista ordinata di combinazioni ``{nome_asse: valore}``: il
    primo asse e' fisso per un blocco di ``N`` valori, poi cambia (come in un
    contatore posizionale). Per 2 assi da 3 valori -> 9 combinazioni.
    """
    value_lists = [ax.values for ax in axes]
    combos: List[Dict[str, float]] = []
    for picked in itertools.product(*value_lists):
        combos.append({ax.name: val for ax, val in zip(axes, picked)})
    return combos


@dataclass(frozen=True)
class EnvelopeVariant:
    """Una combinazione di assi mossi insieme tramite envelope sincronizzati.

    A differenza di ``Variant`` (statica, ``values: Dict[str, float]``), qui i
    valori sono una *sequenza* di combinazioni (i plateau) e gli assi mossi
    diventano envelope a breakpoint, non scalari.
    """

    name: str
    order: int
    moved: List[str]                          # nomi degli assi mossi
    combinations: List[Dict[str, float]]      # plateau in ordine lessicografico

    def overrides(self, spec: StudySpec, *, output_sr: int = 48000) -> Dict[str, Any]:
        """path YAML -> envelope (assi mossi) o scalare baseline (assi fermi).

        Gli assi mossi condividono la stessa griglia temporale (breakpoint
        sincronizzati): in ogni plateau assumono insieme i valori della
        combinazione corrente. Gli assi fermi restano scalari al baseline.

        Nessun clamp: i valori enumerabili sono gia' validati (e bloccati se
        fuori bounds) al parse.
        """
        moved_set = set(self.moved)
        all_step = self._all_step(spec)
        out: Dict[str, Any] = {}
        for ax in spec.axes:
            if ax.name in moved_set:
                seq = [combo[ax.name] for combo in self.combinations]
                # File tutto-step: layout collassato (durata ridotta). Misto:
                # griglia a plateau piena, con l'asse step a punto singolo (C).
                out[ax.path] = envelope_breakpoints(
                    seq,
                    spec.plateau,
                    spec.transition,
                    step=all_step,
                    plateau_single=(not all_step and ax.interpolation == "step"),
                )
            else:
                out[ax.path] = ax.baseline
        return out

    def _all_step(self, spec: StudySpec) -> bool:
        """True se *tutti* gli assi mossi del file sono ``step``.

        Solo in questo caso plateau/durata collassano (layout B). In presenza di
        anche un solo asse non-step la griglia a plateau resta piena.
        """
        return all(spec.axis(name).interpolation == "step" for name in self.moved)

    def envelope_types(self, spec: StudySpec) -> Dict[str, str]:
        """path YAML -> tipo di interpolazione, solo per gli assi mossi.

        Il tipo (``linear``/``cubic``/``step``) e' per-asse: nello stesso file
        assi diversi possono avere forme diverse sulla griglia condivisa.
        """
        return {spec.axis(name).path: spec.axis(name).interpolation for name in self.moved}

    def duration(self, spec: StudySpec) -> float:
        """Durata reale dello stream.

        Envelope a plateau: ``N*plateau + (N-1)*transition``. Se *tutti* gli assi
        mossi sono ``step`` plateau/transizione collassano in un unico gradino
        per valore: ``N*transition``. In caso misto la durata resta piena.
        """
        n = len(self.combinations)
        if n == 0:
            return 0.0
        if self._all_step(spec):
            return n * spec.transition
        return n * spec.plateau + (n - 1) * spec.transition


def _name(order: int, moved: List[str]) -> str:
    return f"e{order}__" + "__".join(moved)


def generate_envelope_variants(spec: StudySpec) -> List[EnvelopeVariant]:
    """Enumera gli ``EnvelopeVariant`` per gli ordini richiesti.

    Un file per ogni combinazione di ``k`` assi (``k`` = ordine), con i loro
    valori attraversati nel prodotto cartesiano lessicografico. L'ordine 0 (tutte
    le baseline) non produce envelope (nessun asse mosso).
    """
    variants: List[EnvelopeVariant] = []

    # Orderings espliciti: generano varianti indipendentemente da orders.
    explicit_keys: set = set()
    for ordering in spec.orderings:
        axes_ordered = [spec.axis(n) for n in ordering]
        moved = [ax.name for ax in axes_ordered]
        key = tuple(moved)
        explicit_keys.add(key)
        variants.append(
            EnvelopeVariant(
                name=_name(len(moved), moved),
                order=len(moved),
                moved=moved,
                combinations=cartesian_combinations(axes_ordered),
            )
        )

    for order in sorted(set(spec.orders)):
        if order <= 0:
            continue
        for combo in itertools.combinations(spec.axes, order):
            moved = [ax.name for ax in combo]
            if tuple(moved) in explicit_keys:
                continue  # ponytail: già emessa come ordering esplicito
            combinations = cartesian_combinations(list(combo))
            variants.append(
                EnvelopeVariant(
                    name=_name(order, moved),
                    order=order,
                    moved=moved,
                    combinations=combinations,
                )
            )
    return variants
