"""Manopole di voce: la chiave ``let`` dentro il blocco ``spread:``.

Ogni voce riceve i propri valori iniettati per nome, con lo stesso vocabolario
delle strategy di ``over`` (``expr`` con ``i``/``n`` deterministico, banda =
un pescaggio per voce). Il gruppo legge i nomi dove il valore vive, invece di
farseli scrivere da fuori su path profondi. ``over`` resta per le destinazioni
uniche e i valori non numerici.
"""
import pytest

from granstudies.errors import SpecError
from granstudies.spread import expand_spreads

AXIS = frozenset({"density"})


def _entry(n, *, let=None, over=None, axes=None):
    spread = {"n": n}
    if let is not None:
        spread["let"] = let
    spread["over"] = over or {"base.pan": {"expr": "i * 10"}}
    entry = {"spread": spread}
    if axes is not None:
        entry["axes"] = axes
    return entry


def _let_of(stream, axis="density", node="base"):
    return stream["axes"][axis][node]["let"]


# --- (a) deterministico per voce: expr con i --------------------------------

def test_manopola_di_voce_deterministica():
    streams = {
        "cugini": _entry(
            3,
            let={"livello": {"expr": "i * 0.8"}},
            axes={"density": {"base": {"expr": "livello"}}},
        )
    }
    out = expand_spreads(streams, axis_names=AXIS)
    assert list(out) == ["cugini_1", "cugini_2", "cugini_3"]
    got = [_let_of(out[n])["livello"] for n in out]
    assert got == pytest.approx([0.0, 0.8, 1.6])


def test_over_ed_expr_vivono_insieme():
    """La manopola di voce nell'axes + una scrittura su path in over."""
    streams = {
        "cugini": _entry(
            2,
            let={"g": {"expr": "4 + i"}},
            over={"base.pointer.start": {"values": [0.1, 0.9]}},
            axes={"grain.duration": {"base": {"expr": "g"}}},
        )
    }
    out = expand_spreads(streams, axis_names=AXIS)
    assert [s["base"]["pointer"]["start"] for s in out.values()] == [0.1, 0.9]
    g = [out[n]["axes"]["grain.duration"]["base"]["let"]["g"] for n in out]
    assert g == [4, 5]


# --- (b) pescato per voce: banda --------------------------------------------

def test_manopola_di_voce_pescata_banda():
    """Una banda in spread.let pesca un valore per voce (non dipende da i):
    valori diversi fra voci, dentro la banda, deterministici via seed."""
    streams = {
        "cugini": _entry(
            4,
            let={"pesca": {"base": 100, "range": 10}},
            axes={"density": {"base": {"expr": "pesca"}}},
        )
    }
    out = expand_spreads(streams, axis_names=AXIS)
    vals = [_let_of(out[n])["pesca"] for n in out]
    assert len(set(vals)) == 4                       # decorrelati fra voci
    assert all(90 <= v <= 110 for v in vals)          # dentro la banda
    # deterministico: stessa espansione, stessi pescaggi
    out2 = expand_spreads(streams, axis_names=AXIS)
    assert [_let_of(out2[n])["pesca"] for n in out2] == vals


def test_pescaggio_condiviso_fra_due_parametri():
    """Il caso che over non copre: UN pescaggio per voce, letto da due assi."""
    streams = {
        "cugini": _entry(
            3,
            let={"env": {"base": 50, "range": 5}},
            axes={
                "density": {"base": {"expr": "env"}},
                "grain.duration": {"base": {"expr": "env * 0.1"}},
            },
        )
    }
    out = expand_spreads(streams, axis_names=AXIS)
    for n in out:
        d = out[n]["axes"]["density"]["base"]["let"]["env"]
        g = out[n]["axes"]["grain.duration"]["base"]["let"]["env"]
        assert d == g                                 # stesso valore, per riferimento


# --- indipendenza fra gruppi -------------------------------------------------

def test_due_gruppi_manopole_di_voce_indipendenti():
    streams = {
        "a": _entry(2, let={"x": {"expr": "i"}},
                    axes={"density": {"base": {"expr": "x + 10"}}}),
        "b": _entry(2, let={"x": {"expr": "i * 5"}},
                    axes={"density": {"base": {"expr": "x + 90"}}}),
    }
    out = expand_spreads(streams, axis_names=AXIS)
    assert [_let_of(out[n])["x"] for n in ("a_1", "a_2")] == [0, 1]
    assert [_let_of(out[n])["x"] for n in ("b_1", "b_2")] == [0, 5]


# --- guardie -----------------------------------------------------------------

def test_let_deve_essere_dict():
    streams = {"cugini": _entry(2, let=[1, 2],
                                axes={"density": {"base": {"expr": "x"}}})}
    with pytest.raises(SpecError, match="let"):
        expand_spreads(streams, axis_names=AXIS)


def test_spread_ancora_rifiuta_chiavi_ignote():
    """let e' ammessa ora, ma una chiave inventata resta errore."""
    streams = {"cugini": {"spread": {"n": 2, "over": {"base.pan": {"expr": "i"}},
                                     "boh": 1}}}
    with pytest.raises(SpecError, match="non ammesse|boh"):
        expand_spreads(streams, axis_names=AXIS)
