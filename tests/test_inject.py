"""Analisi dei nomi di un'espressione (``inject.expr_names``).

Il nome di una funzione primitiva non e' una manopola referenziata: e' un
termine della grammatica, come ``+`` o ``**``. Confonderlo con una manopola
rompe il fixpoint di ``resolve_knobs``, che usa proprio questo insieme come
cancello (issue #45).
"""
import pytest

from granstudies.expr import _FUNCTIONS
from granstudies.inject import expr_names, referenced_names


def test_nomi_semplici():
    assert expr_names("a + b * 2") == frozenset({"a", "b"})


def test_il_nome_della_funzione_non_e_una_manopola():
    assert expr_names("min(a, 10)") == frozenset({"a"})


@pytest.mark.parametrize("fn", sorted(_FUNCTIONS))
def test_nessuna_primitiva_compare_fra_i_nomi(fn):
    """Vale per tutte le primitive, non solo per quella che ha rivelato il bug."""
    arity = _FUNCTIONS[fn][1]
    args = ", ".join(["x"] * arity)
    assert expr_names(f"{fn}({args})") == frozenset({"x"})


def test_chiamate_annidate():
    assert expr_names("max(min(a, b), floor(c))") == frozenset({"a", "b", "c"})


def test_argomento_omonimo_di_una_primitiva_resta_visibile():
    """Una manopola *usata come argomento* si registra anche se si chiama come
    una primitiva: e' solo il bersaglio della chiamata a essere escluso."""
    assert expr_names("min(abs, 2)") == frozenset({"abs"})


def test_referenced_names_attraversa_i_nodi_expr():
    doc = {"axes": {"d": {"base": {"expr": "floor(g0 / 2)"}}}}
    assert referenced_names(doc) == {"g0"}
