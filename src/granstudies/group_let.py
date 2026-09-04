"""Manopole di gruppo: il blocco ``let:`` dentro una entry di ``streams:``.

Livello 2 del pattern a tre livelli. Nomi locali al gruppo (la traiettoria
comune condivisa dalle voci, un centro, una sagoma), risolti una volta per
gruppo e iniettati nelle espressioni di QUELLA entry — axes e blocco spread
(over/let) — prima dell'espansione dello spread, cosi' tutte le voci del
gruppo condividono il valore. Un secondo gruppo ha le proprie, indipendenti:
``respiro`` in due gruppi sono due cose diverse (non collidono, come gli
``axes:`` di gruppo).

Pre-pass su ``streams:`` prima di ``expand_spreads``: dopo, ogni gruppo e' una
entry ordinaria con i nomi gia' risolti nei ``let`` locali. Il pescaggio di
una banda (un envelope per gruppo) usa seed ``stable_seed(f"{nome}:let:
{manopola}")`` — deterministico, gruppi diversi decorrelati.
"""
from __future__ import annotations

import copy
from typing import Any, Dict

from .document_let import _guard_referenced, resolve_knobs
from .errors import ErrCtx
from .inject import inject
from .yaml_loc import Locations


def apply_group_let(
    streams: Dict[str, Any], locs: Locations | None = None
) -> Dict[str, Any]:
    """``streams:`` con le manopole di gruppo risolte e iniettate per entry.

    Senza chiave ``let:`` una entry resta invariata (opt-in). Con il blocco:
    risolve i valori, controlla che ogni manopola sia referenziata da
    un'espressione dell'entry, li inietta e rimuove il blocco.
    """
    out: Dict[str, Any] = {}
    for name, entry in streams.items():
        if not isinstance(entry, dict) or "let" not in entry:
            out[name] = entry
            continue
        ctx = ErrCtx(locs=locs, stream=name)
        block = entry["let"]
        if not isinstance(block, dict):
            raise ctx.err(
                f"let: serve un dict {{manopola: valore}} (stream '{name}').",
                key=("streams", name, "let"),
            )
        entry = copy.deepcopy(entry)
        entry.pop("let")
        if not block:
            out[name] = entry
            continue
        resolved = resolve_knobs(
            block, f"{name}:let", ctx, key_prefix=("streams", name, "let")
        )
        _guard_referenced(block, resolved, entry, ctx)
        inject(entry, resolved)
        out[name] = entry
    return out
