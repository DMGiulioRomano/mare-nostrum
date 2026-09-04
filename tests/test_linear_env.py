"""I due ruoli di ``values:``, separati: ``values`` indicizzato, ``linear_env``
letto per tempo (issue #47).

La stessa lista significa due cose diverse a seconda del ruolo. Nella
**Famiglia 1** la posizione *k* e' l'elemento *k* di una serie discreta (i
valori di test di un asse, un valore per voce in ``spread.over``, una sequenza
di versioni). Nella **Famiglia 2** i valori diventano i breakpoint di un
envelope su tempi equispaziati, e il valore in mezzo esce
dall'interpolazione.

In quasi tutti i contesti la posizione disambigua da sola; in un ``let:`` no —
i due ruoli sono plausibili allo stesso livello di annidamento, con la stessa
forma. Da qui il wrapper: ``values:`` resta il marcatore della Famiglia 1,
``linear_env:`` marca la Famiglia 2 e accetta dentro di se' l'intero
vocabolario dei generatori.
"""
import pytest

from granstudies.document_let import apply_document_let
from granstudies.errors import SpecError
from granstudies.group_let import apply_group_let
from granstudies.value_generators import (
    band,
    expand_env,
    expand_params,
    is_generator_node,
    is_linear_env_node,
    resolve,
    stable_seed,
)


def _doc(let, **rest):
    d = {"study_id": "t", "let": let}
    d.update(rest)
    return d


# --- il wrapper riconosciuto -------------------------------------------------

def test_is_linear_env_node():
    assert is_linear_env_node({"linear_env": [1, 2]})
    assert is_linear_env_node({"linear_env": {"ramp": {"start": 1, "stop": 2}}})
    assert not is_linear_env_node({"values": [1, 2]})
    assert not is_linear_env_node([1, 2])
    assert not is_linear_env_node(3.0)


def test_il_wrapper_non_e_un_nodo_generatore():
    """``is_generator_node`` torna a significare una cosa sola: riconosce un
    generatore. Il ruolo lo dichiara il wrapper, non la forma delle chiavi."""
    assert not is_generator_node({"linear_env": [1, 2]})


# --- le tre forme dentro il wrapper ------------------------------------------

def test_lista_letterale():
    assert expand_env({"linear_env": [1, 2, 3]}, seed=0, path="base") == [
        [0.0, 1], [0.5, 2], [1.0, 3],
    ]


def test_values_esplicito_equivale_alla_lista():
    diretta = expand_env({"linear_env": [1, 2, 3]}, seed=0, path="base")
    avvolta = expand_env({"linear_env": {"values": [1, 2, 3]}}, seed=0, path="base")
    assert diretta == avvolta


def test_ramp_dentro_il_wrapper():
    got = expand_env(
        {"linear_env": {"ramp": {"start": 1, "stop": 3, "step": 1}}},
        seed=0, path="base",
    )
    assert got == [[0.0, 1], [0.5, 2], [1.0, 3]]


def test_banda_dentro_il_wrapper():
    got = expand_env(
        {"linear_env": {"n": 3, "base": 0, "range": 10, "seed": 5}},
        seed=0, path="base",
    )
    want = band(3, 0, 10, seed=5)
    assert got == [[0.0, want[0]], [0.5, want[1]], [1.0, want[2]]]


def test_banda_dentro_il_wrapper_deriva_il_seed_dal_padre():
    got = expand_env(
        {"linear_env": {"n": 3, "base": 0, "range": 10}}, seed=99, path="base"
    )
    assert [v for _, v in got] == band(3, 0, 10, seed=stable_seed("99:base"))


# --- type/curve: accanto al wrapper, non dentro ------------------------------

def test_type_accanto_al_wrapper():
    got = expand_env({"linear_env": [1, 2], "type": "step"}, seed=0, path="base")
    assert got == {"type": "step", "points": [[0.0, 1], [1.0, 2]]}


def test_curve_accanto_al_wrapper():
    got = expand_env({"linear_env": [0, 10], "curve": 2}, seed=0, path="base")
    assert got == {"type": "linear", "points": [[0.0, 0], [1.0, 10]], "curve": 2}


def test_type_dentro_il_wrapper_e_errore():
    """Sarebbero due posti per la stessa chiave, e una lista letterale non
    avrebbe dove ospitarla: il posto e' uno solo."""
    with pytest.raises(ValueError, match="accanto al wrapper"):
        expand_env(
            {"linear_env": {"values": [1, 2], "type": "step"}}, seed=0, path="base"
        )


def test_chiave_estranea_accanto_al_wrapper_e_errore():
    with pytest.raises(ValueError, match="chiavi non ammesse"):
        expand_env({"linear_env": [1, 2], "n": 3}, seed=0, path="base")


def test_wrapper_annidato_in_se_stesso_e_errore():
    with pytest.raises(ValueError, match="annidato"):
        expand_env({"linear_env": {"linear_env": [1, 2]}}, seed=0, path="base")


def test_contenuto_scalare_e_errore():
    with pytest.raises(ValueError, match="lista o un generatore"):
        expand_env({"linear_env": 5}, seed=0, path="base")


# --- migrazione: Famiglia 1 in posizione di Famiglia 2 -----------------------

@pytest.mark.parametrize(
    "nodo",
    [
        {"values": [1, 2, 3]},
        {"ramp": {"start": 1, "stop": 3, "step": 1}},
        {"n": 3, "base": 0, "range": 10},
    ],
)
def test_generatore_nudo_in_posizione_di_famiglia_2_e_errore(nodo):
    with pytest.raises(ValueError, match="linear_env"):
        expand_env(nodo, seed=0, path="base")


def test_il_messaggio_di_migrazione_nomina_il_marcatore_e_il_path():
    with pytest.raises(ValueError) as exc:
        expand_env({"values": [1, 2]}, seed=0, path="range.step")
    msg = str(exc.value)
    assert "range.step" in msg and "values" in msg and "linear_env" in msg


# --- migrazione: Famiglia 2 in posizione di Famiglia 1 -----------------------

def test_linear_env_su_un_asse_e_errore():
    with pytest.raises(ValueError, match="per indice"):
        resolve({"path": "x", "linear_env": [1, 2, 3]})


def test_il_messaggio_inverso_indica_values():
    with pytest.raises(ValueError) as exc:
        resolve({"path": "x", "linear_env": [1, 2, 3]})
    assert "values" in str(exc.value)


# --- i tre contesti di Famiglia 2 --------------------------------------------

def test_famiglia_2_in_un_bordo_di_env():
    """``base``/``range`` di una banda: il bordo e' un Env."""
    out = expand_params(
        {"n": 4, "base": {"linear_env": [0, 10]}, "range": 0.5, "seed": 3}, seed=3
    )
    assert out["base"] == [[0.0, 0], [1.0, 10]]


def test_famiglia_2_in_un_bordo_di_env_col_generatore_nudo_e_errore():
    with pytest.raises(ValueError, match="linear_env"):
        expand_params({"n": 4, "base": {"values": [0, 10]}, "seed": 3}, seed=3)


def test_famiglia_2_nel_let_di_documento():
    out = apply_document_let(
        _doc(
            {"respiro": {"linear_env": [5, 6, 7]}},
            axes={"density": {"base": {"expr": "respiro"}}},
        )
    )
    assert out["axes"]["density"]["base"]["let"]["respiro"] == [
        [0.0, 5], [0.5, 6], [1.0, 7],
    ]


def test_famiglia_2_nel_let_di_documento_col_generatore_nudo_e_errore():
    with pytest.raises(SpecError, match="linear_env"):
        apply_document_let(
            _doc(
                {"respiro": {"values": [5, 6, 7]}},
                axes={"density": {"base": {"expr": "respiro"}}},
            )
        )


def test_l_errore_nel_let_nomina_la_manopola():
    with pytest.raises(SpecError) as exc:
        apply_document_let(
            _doc(
                {"respiro": {"values": [5, 6]}},
                axes={"density": {"base": {"expr": "respiro"}}},
            )
        )
    assert "respiro" in str(exc.value)


def test_famiglia_2_nel_let_di_gruppo():
    out = apply_group_let(
        {
            "cugini": {
                "let": {"respiro": {"linear_env": {"ramp": {"start": 1, "stop": 3,
                                                            "step": 1}}}},
                "axes": {"density": {"base": {"expr": "respiro"}}},
            }
        }
    )
    assert out["cugini"]["axes"]["density"]["base"]["let"]["respiro"] == [
        [0.0, 1], [0.5, 2], [1.0, 3],
    ]


def test_famiglia_2_nel_let_di_gruppo_col_generatore_nudo_e_errore():
    with pytest.raises(SpecError, match="linear_env"):
        apply_group_let(
            {
                "cugini": {
                    "let": {"respiro": {"values": [1, 2]}},
                    "axes": {"density": {"base": {"expr": "respiro"}}},
                }
            }
        )


def test_famiglia_2_in_un_bundle_di_forma_2():
    """Gli stati di ``versions:`` Forma 2 passano da ``resolve_knobs``: stesso
    ruolo, stessa regola."""
    from granstudies.versions import parse_version_axes

    axes = parse_version_axes(
        {
            "study_id": "t",
            "versions": {"densita": {"rada": {"d": {"linear_env": [1, 2]}}}},
            "axes": {"density": {"base": {"expr": "d"}}},
        }
    )
    assert axes["densita"][0][1]["d"] == [[0.0, 1], [1.0, 2]]


def test_famiglia_2_in_un_bundle_col_generatore_nudo_e_errore():
    from granstudies.versions import parse_version_axes

    with pytest.raises(SpecError, match="linear_env"):
        parse_version_axes(
            {
                "study_id": "t",
                "versions": {"densita": {"rada": {"d": {"values": [1, 2]}}}},
                "axes": {"density": {"base": {"expr": "d"}}},
            }
        )


# --- quello che NON cambia ---------------------------------------------------

def test_le_forme_statiche_di_env_restano_nude():
    """Una lista di breakpoint non e' un generatore: nessun wrapper da mettere."""
    for spec in (3.0, [1, 5], [[0, 1], [1, 5]],
                 {"type": "step", "points": [[0, 1], [1, 5]]}):
        assert expand_env(spec, seed=0, path="base") == spec


def test_values_su_un_asse_resta_values():
    assert resolve({"path": "x", "values": [1, 2, 3]}) == [1, 2, 3]


# --- il wrapper come entry di un asse di versions ----------------------------

def test_linear_env_come_asse_piatto_di_versions_e_errore():
    """Cadrebbe nel ramo bundle del discriminatore e 'linear_env' diventerebbe
    il nome di una manopola: un errore piu' avanti, e fuorviante."""
    from granstudies.versions import parse_version_axes

    with pytest.raises(SpecError, match="linear_env"):
        parse_version_axes(
            {
                "study_id": "t",
                "versions": {"d": {"linear_env": [1, 2]}},
                "axes": {"density": {"base": {"expr": "d"}}},
            }
        )


def test_linear_env_come_entry_di_un_asse_di_versions_e_errore():
    from granstudies.versions import parse_version_axes

    with pytest.raises(SpecError, match="linear_env"):
        parse_version_axes(
            {
                "study_id": "t",
                "versions": {"col": {"a": {"linear_env": [1, 2]}}},
                "axes": {"density": {"base": {"expr": "a"}}},
            }
        )
