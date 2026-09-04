"""Manopole di documento: il blocco top-level ``let:``.

Un dizionario ``{nome: valore}`` di manopole a riposo, risolte al load e
iniettate per nome in ogni nodo-expr che le referenzia — stessa meccanica di
``versions._inject``, un livello sopra. ``let:`` dichiara il riposo;
``versions:``/``percorso:`` iniettano *dopo* e lo ombreggiano (il movimento
vince sul riposo).

Increment 1: valori scalari, envelope disegnati (liste) e nodi-expr derivati
che referenziano altre manopole. Le manopole pescate (banda) sono dopo.
"""
import pytest

from granstudies.document_let import apply_document_let
from granstudies.errors import SpecError
from granstudies.versions import inject_combo


def _doc(let, **rest):
    d = {"study_id": "t", "let": let}
    d.update(rest)
    return d


# --- iniezione per nome ------------------------------------------------------

def test_scalare_iniettato_in_ogni_expr_che_lo_nomina():
    out = apply_document_let(
        _doc(
            {"g0": 4},
            axes={"grain.duration": {"base": {"expr": "g0"}}},
            streams={"s": {"axes": {"density": {"base": {"expr": "g0 * 10"}}}}},
        )
    )
    # il blocco let: sparisce dopo l'iniezione
    assert "let" not in out
    # entrambe le expr ricevono la manopola nel proprio let
    assert out["axes"]["grain.duration"]["base"]["let"]["g0"] == 4
    assert out["streams"]["s"]["axes"]["density"]["base"]["let"]["g0"] == 4


def test_manopola_ombreggia_il_default_locale():
    """Un let locale che dichiara lo stesso nome: la manopola vince (come
    versions ombreggia il default)."""
    out = apply_document_let(
        _doc(
            {"g0": 4},
            axes={"grain.duration": {"base": {"expr": "g0", "let": {"g0": 999}}}},
        )
    )
    assert out["axes"]["grain.duration"]["base"]["let"]["g0"] == 4


def test_envelope_disegnato_come_manopola():
    """Una lista e' un envelope statico: passa nello scope tale e quale, e
    l'aritmetica Env+scalare la combina (gia' in eval_expr)."""
    out = apply_document_let(
        _doc(
            {"respiro": [[0, 5], [1, 6]]},
            axes={"density": {"base": {"expr": "respiro + 2"}}},
        )
    )
    assert out["axes"]["density"]["base"]["let"]["respiro"] == [[0, 5], [1, 6]]


def test_manopola_derivata():
    """Un nodo-expr che referenzia un'altra manopola si risolve al load."""
    out = apply_document_let(
        _doc(
            {"g0": 4, "dur0": {"expr": "g0 / 1000"}},
            axes={"grain.duration": {"base": {"expr": "dur0"}}},
        )
    )
    assert out["axes"]["grain.duration"]["base"]["let"]["dur0"] == pytest.approx(0.004)


# --- guardie -----------------------------------------------------------------

def test_manopola_non_referenziata_e_errore():
    with pytest.raises(SpecError, match="non e' referenziata"):
        apply_document_let(
            _doc({"g0": 4}, axes={"density": {"base": {"expr": "d0"}}})
        )


def test_manopola_derivata_referenziata_solo_da_altra_manopola():
    """g0 usata solo da dur0 (che e' usata nel resto): g0 e' referenziata."""
    out = apply_document_let(
        _doc(
            {"g0": 4, "dur0": {"expr": "g0 / 1000"}},
            axes={"grain.duration": {"base": {"expr": "dur0"}}},
        )
    )
    assert out["axes"]["grain.duration"]["base"]["let"]["dur0"] == pytest.approx(0.004)


def test_manopola_derivata_che_chiama_una_primitiva():
    """Issue #45: il nome della funzione non e' una manopola mancante."""
    out = apply_document_let(
        _doc(
            {"a": 5, "b": {"expr": "min(a, 10)"}},
            axes={"density": {"base": {"expr": "b"}}},
        )
    )
    assert out["axes"]["density"]["base"]["let"]["b"] == 5


@pytest.mark.parametrize(
    "text, atteso",
    [
        ("abs(-a)", 5),
        ("floor(a / 2)", 2),
        ("ceil(a / 2)", 3),
        ("sqrt(a * 5)", 5),
        ("exp(a * 0)", 1),
        ("log(a / a)", 0),
        ("sin(a * 0)", 0),
        ("cos(a * 0)", 1),
        ("tan(a * 0)", 0),
        ("atan(a * 0)", 0),
        ("min(a, 10)", 5),
        ("max(a, 10)", 10),
        ("mix(a, a, 0.5)", 5),
    ],
)
def test_ogni_primitiva_dentro_una_manopola_derivata(text, atteso):
    """Regressione per ciascuna primitiva (issue #45)."""
    out = apply_document_let(
        _doc({"a": 5, "b": {"expr": text}}, axes={"density": {"base": {"expr": "b"}}})
    )
    assert out["axes"]["density"]["base"]["let"]["b"] == pytest.approx(atteso)


def test_dipendenza_ciclica_e_errore():
    with pytest.raises(SpecError, match="cicl|irrisolvibil"):
        apply_document_let(
            _doc(
                {"a": {"expr": "b"}, "b": {"expr": "a"}},
                axes={"density": {"base": {"expr": "a + b"}}},
            )
        )


# --- opt-in / no-op ----------------------------------------------------------

def test_nessun_blocco_let_e_no_op():
    doc = {"study_id": "t", "axes": {"density": {"base": 5}}}
    assert apply_document_let(doc) == doc


def test_blocco_let_vuoto_e_no_op():
    out = apply_document_let(_doc({}, axes={"density": {"base": 5}}))
    assert "let" not in out
    assert out["axes"]["density"]["base"] == 5


# --- ombreggiatura riposo -> movimento (versions vince) ----------------------

def test_versions_ombreggia_la_manopola():
    """Dopo il riposo (let: g0=4), l'iniezione di versions (g0=50) vince:
    e' l'ordine load -> versions della pipeline."""
    out = apply_document_let(
        _doc({"g0": 4}, axes={"grain.duration": {"base": {"expr": "g0"}}})
    )
    moved = inject_combo(out, {"g0": 50})
    assert moved["axes"]["grain.duration"]["base"]["let"]["g0"] == 50
