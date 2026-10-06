"""Forma compatta a cicli (``[pattern, end_time, n_reps, ...]``) come manopola.

La sintassi dei loop dell'engine dentro un ``let:``: si espande in breakpoint
alla risoluzione delle manopole, quindi a valle e' un Env statico come ogni
altro (``mix``, aritmetica, iniezione nelle expr) e nessun altro modulo la
vede. Il ventaglio asimmetrico e' il caso d'uso: un pattern con vertice al 25%
ripetuto N volte, che ``values:`` non sa scrivere (tempi equispaziati).
"""
import pytest

from granstudies.document_let import apply_document_let
from granstudies.errors import SpecError
from granstudies.expr import eval_expr
from granstudies.value_generators import expand_env, is_compact_env


def _doc(let, **rest):
    d = {"study_id": "t", "let": let}
    d.update(rest)
    return d


# --- riconoscimento -----------------------------------------------------------

def test_non_collide_con_le_forme_statiche_di_env():
    assert not is_compact_env([[0, 0], [1, 1]])      # breakpoint
    assert not is_compact_env([0, 1])                 # shorthand [a, b]
    assert not is_compact_env(4)
    assert is_compact_env([[[0, 0], [25, 1]], 1, 4])


# --- espansione ---------------------------------------------------------------

def test_ventaglio_asimmetrico_ripetuto():
    """Vertice al 25% del ciclo, 4 cicli: i tempi NON sono equispaziati (e' la
    ragione per cui 'values:' non basta)."""
    env = expand_env([[[0, 0], [25, 1]], 1, 4], seed=0, path="s")
    assert len(env) == 8
    assert env[0] == [0.0, 0]
    # primo ciclo: 0 a t=0, vertice a t=0.0625 (25% di un quarto di durata)
    assert env[1] == pytest.approx([0.0625, 1], abs=1e-6)
    # ogni ciclo riparte, l'ultimo comincia a 3/4
    assert env[6][0] == pytest.approx(0.75, abs=1e-5)
    assert all(0.0 <= t <= 1.0 for t, _ in env)


def test_manopola_compatta_iniettata_come_env():
    out = apply_document_let(
        _doc(
            {"s": [[[0, 0], [25, 1]], 1, 2]},
            axes={"density": {"base": {"expr": "mix(10, 20, s)"}}},
        )
    )
    s = out["axes"]["density"]["base"]["let"]["s"]
    assert isinstance(s, list) and all(len(p) == 2 for p in s)
    # e' un Env come gli altri: mix lo consuma senza saperne la provenienza
    mixed = eval_expr("mix(10, 20, s)", {"s": s})
    assert [y for _, y in mixed] == [10, 20, 10, 20]


# --- vincoli propri dello studio ----------------------------------------------

def test_end_time_in_secondi_e_errore():
    """Dentro un let l'Env vive sul tempo normalizzato: end_time diverso da 1
    darebbe breakpoint fuori bordo, appiattiti in hold senza un errore."""
    with pytest.raises(SpecError, match="end_time deve essere 1"):
        apply_document_let(
            _doc(
                {"s": [[[0, 0], [25, 1]], 50, 4]},
                axes={"density": {"base": {"expr": "mix(10, 20, s)"}}},
            )
        )


def test_punto_pattern_a_tre_elementi_e_errore():
    with pytest.raises(SpecError, match="devono essere coppie"):
        apply_document_let(
            _doc(
                {"s": [[[0, 0], [25, 1, "step"]], 1, 4]},
                axes={"density": {"base": {"expr": "mix(10, 20, s)"}}},
            )
        )


# --- i guard di forma del motore (PGE #211) -----------------------------------
# La forma compatta si espande con l'`EnvelopeBuilder` del motore, e dal bump
# che porta PythonGranularEngine#287 (#7) il builder rifiuta i corpi che prima
# espandeva in silenzio: x del pattern fuori da [0, 100] o all'indietro, y che
# non e' un numero. Il suo errore nomina una sotto-posizione
# (`envelope.compact.pattern`) e mette il perche' nell'hint: senza l'hint il
# messaggio dice "valore invalido: 150" e basta. E una distribuzione temporale
# sbagliata, che prima elencava quelle disponibili, le elencava solo li'.

def _perche_del_motore(compatto):
    from granstudies import engine_bridge
    engine_bridge._ensure_engine_on_path()
    from pge.envelopes.envelope_builder import EnvelopeBuilder
    with pytest.raises(ValueError) as info:
        EnvelopeBuilder.parse(list(compatto))
    return info.value.hint


@pytest.mark.parametrize("compatto", [
    [[[0, 0], [150, 1]], 1, 2],                           # x oltre 100
    [[[50, 0], [10, 1]], 1, 2],                           # x all'indietro
    [[[0, True], [100, 1]], 1, 2],                        # y che non e' un numero
    [[[0, 0], [100, 1]], 1, 2, "linear", {"type": "boh"}],  # distribuzione ignota
])
def test_il_rifiuto_del_motore_arriva_col_suo_perche(compatto):
    perche = _perche_del_motore(compatto)
    assert perche
    with pytest.raises(SpecError) as info:
        apply_document_let(
            _doc(
                {"s": compatto},
                axes={"density": {"base": {"expr": "mix(10, 20, s)"}}},
            )
        )
    assert "forma compatta" in str(info.value)
    assert perche in str(info.value)
