"""Regola cardine delle manopole: ombreggiare un nome e' errore.

Un ``let:`` non puo' ridichiarare un nome gia' in scope in un livello
superiore della propria linea:
  - documento e' antenato di ogni gruppo e di ogni spread.let;
  - il gruppo e' antenato del proprio spread.let.
Due gruppi diversi (o due spread.let di gruppi diversi) sono fratelli: lo
stesso nome NON collide. La regola cancella la decisione di precedenza:
niente ordine da ricordare, un valore diverso vuole un nome diverso.
"""
import pytest

from granstudies.document_let import apply_document_let
from granstudies.errors import SpecError


def _doc(*, let=None, streams=None):
    d = {"study_id": "t", "axes": {"density": {"baseline": 10}}}
    if let is not None:
        d["let"] = let
    if streams is not None:
        d["streams"] = streams
    return d


# --- collisioni verticali = errore -------------------------------------------

def test_gruppo_ombreggia_documento():
    doc = _doc(
        let={"d0": 25},
        streams={"cugini": {"let": {"d0": 90},
                            "axes": {"density": {"base": {"expr": "d0"}}}}},
    )
    with pytest.raises(SpecError, match="d0"):
        apply_document_let(doc)


def test_spread_let_ombreggia_documento():
    doc = _doc(
        let={"g0": 4},
        streams={"cugini": {
            "spread": {"n": 2, "let": {"g0": {"expr": "i"}},
                       "over": {"base.pan": {"expr": "i"}}},
            "axes": {"grain.duration": {"base": {"expr": "g0"}}}}},
    )
    with pytest.raises(SpecError, match="g0"):
        apply_document_let(doc)


def test_spread_let_ombreggia_gruppo():
    doc = _doc(
        streams={"cugini": {
            "let": {"respiro": 5},
            "spread": {"n": 2, "let": {"respiro": {"expr": "i"}},
                       "over": {"base.pan": {"expr": "i"}}},
            "axes": {"density": {"base": {"expr": "respiro"}}}}},
    )
    with pytest.raises(SpecError, match="respiro"):
        apply_document_let(doc)


# --- fratelli = ok -----------------------------------------------------------

def test_due_gruppi_stesso_nome_ok():
    doc = _doc(
        streams={
            "a": {"let": {"respiro": 10},
                  "axes": {"density": {"base": {"expr": "respiro"}}}},
            "b": {"let": {"respiro": 99},
                  "axes": {"density": {"base": {"expr": "respiro"}}}},
        },
    )
    # non deve sollevare: i due 'respiro' sono fratelli
    apply_document_let(doc)


def test_due_spread_let_stesso_nome_ok():
    doc = _doc(
        streams={
            "a": {"spread": {"n": 2, "let": {"x": {"expr": "i"}},
                             "over": {"base.pan": {"expr": "i"}}},
                  "axes": {"density": {"base": {"expr": "x"}}}},
            "b": {"spread": {"n": 2, "let": {"x": {"expr": "i*2"}},
                             "over": {"base.pan": {"expr": "i"}}},
                  "axes": {"density": {"base": {"expr": "x"}}}},
        },
    )
    apply_document_let(doc)


def test_gruppo_e_voce_nomi_diversi_ok():
    doc = _doc(
        let={"d0": 25},
        streams={"cugini": {
            "let": {"respiro": {"base": {"expr": "d0"}, "range": 1, "n": 3}},
            "spread": {"n": 2, "let": {"livello": {"expr": "i"}},
                       "over": {"base.pan": {"expr": "i"}}},
            "axes": {"density": {"base": {"expr": "respiro + livello"}}}}},
    )
    apply_document_let(doc)
