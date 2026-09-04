"""Manopole di gruppo: il blocco ``let:`` dentro una entry di ``streams:``.

Livello 2 del pattern a tre livelli. Nomi locali al gruppo (es. ``respiro``,
la traiettoria comune condivisa dalle voci), risolti una volta per gruppo e
iniettati nelle espressioni di QUELLA entry — axes, e anche il blocco spread
(over/let) se li nominano. Un secondo gruppo ha le proprie, indipendenti.

Valori: scalari, envelope disegnati, derivati, e bande (un pescaggio per
gruppo, compilato in envelope una volta).
"""
import pytest

from granstudies.errors import SpecError
from granstudies.group_let import apply_group_let


def _stream(let, **rest):
    e = {"let": let}
    e.update(rest)
    return e


# --- iniezione nel gruppo ----------------------------------------------------

def test_scalare_di_gruppo_iniettato_negli_axes():
    streams = {
        "cugini": _stream(
            {"centro": 40},
            axes={"density": {"base": {"expr": "centro"}}},
        )
    }
    out = apply_group_let(streams)
    assert "let" not in out["cugini"]
    assert out["cugini"]["axes"]["density"]["base"]["let"]["centro"] == 40


def test_envelope_disegnato_di_gruppo():
    streams = {
        "cugini": _stream(
            {"respiro": [[0, 5], [1, 6]]},
            axes={"density": {"base": {"expr": "respiro + 1"}}},
        )
    }
    out = apply_group_let(streams)
    assert out["cugini"]["axes"]["density"]["base"]["let"]["respiro"] == [[0, 5], [1, 6]]


def test_banda_di_gruppo_pescata_una_volta_come_envelope():
    """Una banda in let: di gruppo si compila in envelope (breakpoint), un
    pescaggio per gruppo — la traiettoria comune 'pescata'."""
    streams = {
        "cugini": _stream(
            {"respiro": {"linear_env": {"base": 50, "range": 5, "n": 6}}},
            axes={"density": {"base": {"expr": "respiro"}}},
        )
    }
    out = apply_group_let(streams)
    env = out["cugini"]["axes"]["density"]["base"]["let"]["respiro"]
    assert isinstance(env, list) and len(env) == 6           # 6 breakpoint
    assert all(isinstance(p, list) and len(p) == 2 for p in env)
    assert all(45 <= v <= 55 for _, v in env)                # dentro la banda


def test_gruppo_inietta_anche_nel_blocco_spread():
    """La manopola di gruppo raggiunge le espressioni del blocco spread."""
    streams = {
        "cugini": _stream(
            {"centro": 30},
            spread={"n": 2, "let": {"liv": {"expr": "centro + i"}},
                    "over": {"base.pan": {"expr": "i"}}},
            axes={"density": {"base": {"expr": "liv"}}},
        )
    }
    out = apply_group_let(streams)
    band = out["cugini"]["spread"]["let"]["liv"]
    assert band["let"]["centro"] == 30


def test_due_gruppi_indipendenti_stesso_nome():
    """respiro in due gruppi = due cose diverse, non collidono."""
    streams = {
        "a": _stream({"respiro": 10}, axes={"density": {"base": {"expr": "respiro"}}}),
        "b": _stream({"respiro": 99}, axes={"density": {"base": {"expr": "respiro"}}}),
    }
    out = apply_group_let(streams)
    assert out["a"]["axes"]["density"]["base"]["let"]["respiro"] == 10
    assert out["b"]["axes"]["density"]["base"]["let"]["respiro"] == 99


# --- guardie -----------------------------------------------------------------

def test_manopola_di_gruppo_derivata_che_chiama_una_primitiva():
    """Issue #45: ``resolve_knobs`` e' condiviso, il bug si vede anche qui."""
    streams = {
        "cugini": _stream(
            {"centro": 40, "clamp": {"expr": "min(centro, 30)"}},
            axes={"density": {"base": {"expr": "clamp"}}},
        )
    }
    out = apply_group_let(streams)
    assert out["cugini"]["axes"]["density"]["base"]["let"]["clamp"] == 30


def test_manopola_di_gruppo_non_referenziata_e_errore():
    streams = {
        "cugini": _stream(
            {"respiro": 5}, axes={"density": {"base": {"expr": "altro"}}}
        )
    }
    with pytest.raises(SpecError, match="non e' referenziata"):
        apply_group_let(streams)


def test_stream_senza_let_invariato():
    streams = {"cugini": {"axes": {"density": {"base": 5}}}}
    assert apply_group_let(streams) == streams
