"""versions: assi ortogonali, Forma 1 (co-varianti) e Forma 2 (stati).

Un asse di ``versions:`` e' o un fascio di manopole parallele (Forma 1: ogni
manopola una sequenza scalare, lunghezza = la piu' lunga, le corte tengono
l'ultimo) o un insieme di stati nominati (Forma 2: ogni stato un bundle di
manopole, i cui valori possono essere envelope). Il prodotto cartesiano corre
FRA gli assi. Il vecchio dizionario piatto (una manopola per chiave) resta un
asse a singola manopola: retro-compatibile.
"""
import pytest

from granstudies.document_let import apply_document_let
from granstudies.errors import SpecError
from granstudies.study_spec import resolve_streams
from granstudies.versions import (
    axis_combos,
    generate_versions_document,
    parse_version_axes,
)


def _states(axes, axis):
    """Coppie (label, knobs) di un asse, senza il dettaglio interno."""
    return axes[axis]


# --- retro-compat: asse a singola manopola (forma piatta storica) -----------

def test_singola_manopola_retrocompat():
    data = {"study_id": "t", "versions": {"d": {"values": [1, 2, 3]}},
            "axes": {"density": {"base": {"expr": "d"}}}}
    axes = parse_version_axes(data)
    assert [lbl for lbl, _ in axes["d"]] == ["1", "2", "3"]
    assert [kn for _, kn in axes["d"]] == [{"d": 1}, {"d": 2}, {"d": 3}]


# --- Forma 1: manopole parallele co-varianti --------------------------------

def test_forma1_covarianti_hold_last():
    data = {"study_id": "t",
            "versions": {"grana": {"g0": {"values": [4, 10, 20, 40]},
                                   "apr": {"values": [0, 2, 5]}}},
            "axes": {"density": {"base": {"expr": "g0 + apr"}}}}
    axes = parse_version_axes(data)
    knobs = [kn for _, kn in axes["grana"]]
    # lunghezza = max(4, 3) = 4 ; apr tiene l'ultimo (5) alla 4a
    assert knobs == [
        {"g0": 4, "apr": 0},
        {"g0": 10, "apr": 2},
        {"g0": 20, "apr": 5},
        {"g0": 40, "apr": 5},
    ]


# --- Forma 2: stati nominati, envelope, bundle parziale ---------------------

def test_forma2_stati_nominati():
    data = {"study_id": "t",
            "versions": {"densita": {
                "estrema": {"d0": 500, "respiro": [[0, 0], [1, 34]]},
                "minima": {"d0": 2}}},
            "axes": {"density": {"base": {"expr": "d0 + respiro"}}}}
    axes = parse_version_axes(data)
    labels = [lbl for lbl, _ in axes["densita"]]
    assert labels == ["estrema", "minima"]
    estrema = axes["densita"][0][1]
    assert estrema["d0"] == 500
    assert estrema["respiro"] == [[0, 0], [1, 34]]      # envelope disegnato intatto
    minima = axes["densita"][1][1]
    assert minima == {"d0": 2}                           # bundle parziale


def test_forma2_envelope_da_generatore():
    """Dentro uno stato, un ramp e' un ENVELOPE (non una sequenza di versioni)."""
    data = {"study_id": "t",
            "versions": {"col": {"caldo": {"respiro": {"linear_env": {
                "ramp": {"start": 20, "stop": 60, "step": 10}}}}}},
            "axes": {"density": {"base": {"expr": "respiro"}}}}
    axes = parse_version_axes(data)
    env = axes["col"][0][1]["respiro"]
    assert isinstance(env, list) and all(len(p) == 2 for p in env)   # breakpoint


# --- discriminatore: forme miste = errore -----------------------------------

def test_asse_misto_seq_e_bundle_e_errore():
    data = {"study_id": "t",
            "versions": {"x": {"a": {"values": [1, 2]},          # sequenza
                               "s": {"d0": 5}}},                  # bundle
            "axes": {"density": {"base": {"expr": "a + d0"}}}}
    with pytest.raises(SpecError, match="mescola|Forma|misto"):
        parse_version_axes(data)


# --- prodotto cartesiano fra assi -------------------------------------------

def test_axis_combos_prodotto_fra_assi():
    data = {"study_id": "t",
            "versions": {"grana": {"g0": {"values": [4, 40]}},
                         "densita": {"rada": {"d0": 5}, "fitta": {"d0": 50}}},
            "axes": {"density": {"base": {"expr": "g0 + d0"}}}}
    axes = parse_version_axes(data)
    combos = axis_combos(axes)
    labels = [lbl for lbl, _ in combos]
    assert labels == ["grana=1__densita=rada", "grana=1__densita=fitta",
                      "grana=2__densita=rada", "grana=2__densita=fitta"]
    # ogni combo fonde i knob dei due assi
    assert combos[0][1] == {"g0": 4, "d0": 5}
    assert combos[3][1] == {"g0": 40, "d0": 50}


# --- end-to-end: Forma 2 con envelope raggiunge il documento -----------------

def test_end_to_end_forma2_envelope():
    data = {"study_id": "t",
            "base": {"sample": "x.wav", "onset": 0, "time_mode": "normalized",
                     "duration": 10},
            "axes": {"density": {"baseline": 10}},
            "stack": {"density": {"base": 2}},
            "streams": {"s": {"axes": {"density": {"base": {"expr": "d0"}, "range": 0}}}},
            "versions": {"duration": 10,
                         "livello": {"basso": {"d0": 30}, "alto": {"d0": 300}}}}
    out = generate_versions_document(apply_document_let(data), samples_dir=None)
    ids = sorted(s["stream_id"] for s in out["streams"])
    assert ids == ["s__livello=basso", "s__livello=alto"] or \
           ids == sorted(["s__livello=basso", "s__livello=alto"])
    def dens(sid):
        s = next(s for s in out["streams"] if s["stream_id"] == sid)
        return sum(v for _, v in s["density"]["points"]) / len(s["density"]["points"])
    assert 25 <= dens("s__livello=basso") <= 35
    assert 280 <= dens("s__livello=alto") <= 320
