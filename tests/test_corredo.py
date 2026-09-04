"""Il corredo: una lista nominata, dichiarata in un ``let:`` e letta **solo per
indice** (issue #48, design in ``docs/plans/corredo-liste-indicizzabili.md``).

Il buco che colma: un valore *scelto a mano* — quattro rapporti decisi a
orecchio, non una formula — non era condivisibile fra due assi. Pescato
(banda in ``spread.let``) e calcolato (``{expr}`` con ``i``/``n``) lo erano
gia'; scelto no, perche' ``values`` in ``spread.over`` scrive su un path solo.

Il corredo aggira l'obiezione invece di combatterla: la lista vive nel ``let:``
di gruppo o di documento, dove non esiste nessun indice e quindi nessuna
pretesa sul conteggio.

Questa fetta e' la catena minima: dichiarazione, risoluzione delle manopole,
valutazione con **indice costante**, iniezione per nome, documento engine.
Niente ``i``, niente ``cycle:``, niente ``len()``.
"""
import pytest

from granstudies.document_let import apply_document_let
from granstudies.errors import SpecError
from granstudies.expr import eval_expr, is_corredo
from granstudies.group_let import apply_group_let
from granstudies.value_generators import (
    expand_env,
    is_generator_node,
    is_linear_env_node,
    parse_corredo,
)


def _doc(let, **rest):
    d = {"study_id": "t", "let": let}
    d.update(rest)
    return d


# --- il corredo non collide con la macchina esistente ------------------------

def test_riconosciuto_come_corredo():
    assert is_corredo({"list": [2, 3, 4, 7]})
    assert not is_corredo({"values": [2, 3]})
    assert not is_corredo([2, 3])


def test_non_e_un_nodo_generatore_ne_un_linear_env():
    """``list`` non e' in ``Y_GENERATOR_KEYS``: nessuna collisione."""
    node = {"list": [2, 3, 4, 7]}
    assert not is_generator_node(node)
    assert not is_linear_env_node(node)


def test_expand_env_lo_lascia_passare():
    """Non e' un envelope: ``expand_env`` non ha niente da compilare."""
    node = {"list": [2, 3]}
    assert expand_env(node, seed=0, path="base") == node


# --- dichiarazione: `let:` di documento e di gruppo --------------------------

def test_corredo_di_documento_produce_una_lista_non_un_envelope():
    out = apply_document_let(
        _doc(
            {"ratio": {"list": [2, 3, 4, 7]}},
            axes={"density": {"base": {"expr": "ratio[0]"}}},
        )
    )
    iniettato = out["axes"]["density"]["base"]["let"]["ratio"]
    assert iniettato == {"list": [2, 3, 4, 7]}
    # e NON i breakpoint che ``{values: [...]}`` avrebbe prodotto
    assert iniettato != [[0.0, 2], [1 / 3, 3], [2 / 3, 4], [1.0, 7]]


def test_corredo_di_gruppo():
    out = apply_group_let(
        {
            "cugini": {
                "let": {"ratio": {"list": [2, 3, 4, 7]}},
                "axes": {"density": {"base": {"expr": "ratio[1]"}}},
            }
        }
    )
    assert out["cugini"]["axes"]["density"]["base"]["let"]["ratio"] == {
        "list": [2, 3, 4, 7]
    }


def test_corredo_di_documento_letto_da_due_gruppi():
    out = apply_document_let(
        _doc(
            {"ratio": {"list": [2, 3, 4, 7]}},
            streams={
                "a": {"axes": {"density": {"base": {"expr": "ratio[0]"}}}},
                "b": {"axes": {"density": {"base": {"expr": "ratio[3]"}}}},
            },
        )
    )
    for g in ("a", "b"):
        assert out["streams"][g]["axes"]["density"]["base"]["let"]["ratio"] == {
            "list": [2, 3, 4, 7]
        }


# --- l'indice costante -------------------------------------------------------

@pytest.mark.parametrize("k, atteso", [(0, 2), (1, 3), (2, 4), (3, 7)])
def test_indice_costante(k, atteso):
    assert eval_expr(f"ratio[{k}]", {"ratio": {"list": [2, 3, 4, 7]}}) == atteso


def test_la_fondamentale_del_corredo_in_una_espressione():
    """``ratio[0]`` dice «la fondamentale del corredo» una volta sola: senza,
    servirebbe un ``d0: 2`` accanto alla lista, che diverge in silenzio appena
    si ritocca il primo rapporto."""
    scope = {"d": 1, "ratio": {"list": [2, 3, 4, 7]}}
    assert eval_expr("d * ratio[0] / 40", scope) == pytest.approx(0.05)


def test_indice_come_espressione_costante():
    scope = {"ratio": {"list": [2, 3, 4, 7]}}
    assert eval_expr("ratio[1 + 1]", scope) == 4
    assert eval_expr("ratio[floor(2.9)]", scope) == 4


def test_indice_intero_scritto_come_float():
    """``4 / 2`` vale 2.0, che *e'* un intero: la guardia e' sui frazionari."""
    assert eval_expr("ratio[4 / 2]", {"ratio": {"list": [2, 3, 4, 7]}}) == 4


# --- la manopola derivata che legge il corredo -------------------------------

def test_manopola_derivata_da_un_corredo():
    out = apply_document_let(
        _doc(
            {"ratio": {"list": [2, 3, 4, 7]}, "doppio": {"expr": "ratio[0] * 2"}},
            axes={"density": {"base": {"expr": "doppio"}}},
        )
    )
    assert out["axes"]["density"]["base"]["let"]["doppio"] == 4


def test_ordine_di_dichiarazione_irrilevante():
    """I corredi si risolvono nella prima passata, prima del fixpoint."""
    out = apply_document_let(
        _doc(
            {"doppio": {"expr": "ratio[0] * 2"}, "ratio": {"list": [2, 3, 4, 7]}},
            axes={"density": {"base": {"expr": "doppio"}}},
        )
    )
    assert out["axes"]["density"]["base"]["let"]["doppio"] == 4


# --- la linea di confine: una lista non e' mai un valore ---------------------

def test_il_nome_nudo_e_errore():
    with pytest.raises(ValueError, match="solo per indice"):
        eval_expr("ratio", {"ratio": {"list": [2, 3]}})


def test_aritmetica_su_un_corredo_e_errore():
    with pytest.raises(ValueError, match="solo per indice"):
        eval_expr("ratio * 2", {"ratio": {"list": [2, 3]}})


def test_un_corredo_passato_a_una_funzione_e_errore():
    with pytest.raises(ValueError, match="solo per indice"):
        eval_expr("min(ratio, 2)", {"ratio": {"list": [2, 3]}})


def test_indicizzare_qualcosa_che_non_e_un_nome_e_errore():
    """La base di ``[]`` e' un nome, non un'espressione qualunque: niente
    altro nella grammatica puo' produrre una lista. (Le parentesi non contano:
    ``(ratio)[0]`` ha lo stesso AST di ``ratio[0]``.)"""
    with pytest.raises(ValueError, match="per nome"):
        eval_expr("min(1, 2)[0]", {"ratio": {"list": [2, 3]}})


def test_indice_env_e_errore():
    with pytest.raises(ValueError, match="non e' un numero"):
        eval_expr("ratio[s]", {"ratio": {"list": [2, 3]}, "s": [[0, 0], [1, 1]]})


# --- le guardie --------------------------------------------------------------

def test_corredo_vuoto_e_errore_alla_dichiarazione():
    with pytest.raises(SpecError, match="vuoto"):
        apply_document_let(
            _doc({"ratio": {"list": []}}, axes={"d": {"base": {"expr": "ratio[0]"}}})
        )


def test_il_messaggio_del_corredo_vuoto_nomina_il_corredo():
    with pytest.raises(SpecError) as exc:
        apply_document_let(
            _doc({"ratio": {"list": []}}, axes={"d": {"base": {"expr": "ratio[0]"}}})
        )
    assert "ratio" in str(exc.value)


def test_list_non_lista_e_errore():
    with pytest.raises(SpecError, match="lista"):
        apply_document_let(
            _doc({"ratio": {"list": 5}}, axes={"d": {"base": {"expr": "ratio[0]"}}})
        )


def test_elemento_non_numerico_e_errore():
    """I corredi di sagome e di valori non numerici sono rimandati (#44)."""
    with pytest.raises(SpecError, match="#44|non e' un numero"):
        apply_document_let(
            _doc(
                {"ratio": {"list": [2, [[0, 1], [1, 2]]]}},
                axes={"d": {"base": {"expr": "ratio[0]"}}},
            )
        )


def test_chiave_estranea_accanto_a_list_e_errore():
    with pytest.raises(SpecError, match="chiavi non ammesse"):
        apply_document_let(
            _doc(
                {"ratio": {"list": [2, 3], "boh": 1}},
                axes={"d": {"base": {"expr": "ratio[0]"}}},
            )
        )


def test_indice_non_intero_e_errore_con_hint():
    with pytest.raises(ValueError) as exc:
        eval_expr("ratio[0.5]", {"ratio": {"list": [2, 3]}})
    msg = str(exc.value)
    assert "//" in msg and "floor" in msg


def test_indice_fuori_range_e_errore_che_nomina_corredo_e_len():
    with pytest.raises(ValueError) as exc:
        eval_expr("ratio[9]", {"ratio": {"list": [2, 3, 4, 7]}})
    msg = str(exc.value)
    assert "ratio" in msg and "4 elementi" in msg


def test_indicizzare_un_nome_che_non_e_un_corredo_e_errore():
    with pytest.raises(ValueError, match="non e' un corredo"):
        eval_expr("d[0]", {"d": 25})


def test_indicizzare_un_envelope_e_errore():
    with pytest.raises(ValueError, match="non e' un corredo"):
        eval_expr("s[0]", {"s": [[0, 1], [1, 2]]})


def test_indicizzare_un_nome_ignoto_e_errore():
    with pytest.raises(ValueError, match="nome ignoto"):
        eval_expr("boh[0]", {"d": 1})


def test_corredo_non_referenziato_e_errore():
    """La guardia anti-refuso vale per i corredi come per ogni manopola: non
    ha richiesto modifiche, perche' ``ast.walk`` registra ``ratio`` anche da
    ``ratio[0]``."""
    with pytest.raises(SpecError, match="non e' referenziata"):
        apply_document_let(
            _doc({"ratio": {"list": [2, 3]}}, axes={"d": {"base": {"expr": "1"}}})
        )


def test_un_corredo_referenziato_solo_per_indice_e_referenziato():
    out = apply_document_let(
        _doc({"ratio": {"list": [2, 3]}}, axes={"d": {"base": {"expr": "ratio[0]"}}})
    )
    assert out["axes"]["d"]["base"]["let"]["ratio"] == {"list": [2, 3]}


def test_corredo_che_ombreggia_una_manopola_di_documento_e_errore():
    with pytest.raises(SpecError, match="ombreggiare"):
        apply_document_let(
            _doc(
                {"ratio": {"list": [2, 3]}},
                streams={
                    "a": {
                        "let": {"ratio": {"list": [5, 6]}},
                        "axes": {"d": {"base": {"expr": "ratio[0]"}}},
                    }
                },
            )
        )


# --- parse_corredo, direttamente ---------------------------------------------

def test_parse_corredo_normalizza_in_lista():
    assert parse_corredo({"list": (2, 3)}, "ratio") == {"list": [2, 3]}


def test_parse_corredo_rifiuta_i_booleani():
    with pytest.raises(ValueError, match="non e' un numero"):
        parse_corredo({"list": [True, 2]}, "ratio")


# --- end-to-end: dal file al documento engine --------------------------------

def _fixture(nome):
    import os

    import yaml

    from granstudies.document_let import apply_document_let
    from granstudies.study_spec import resolve_streams

    path = os.path.join(os.path.dirname(__file__), "fixtures", nome)
    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    data = apply_document_let(data)
    return data, resolve_streams(data, data["study_id"])


def test_end_to_end_indice_costante():
    """Il corredo attraversa tutti gli strati e arriva ai valori d'asse."""
    _, specs = _fixture("corredo_indice_costante.yml")
    spec = specs[0]
    # base = d * ratio[0] * 10 = 1 * 2 * 10 = 20, range 0 -> banda collassata
    assert spec.axis("density").values == pytest.approx([20.0] * 4)
    # base = d * ratio[3] / 1000 = 7 / 1000
    assert spec.axis("grain_duration").values == pytest.approx([0.007] * 4)


def test_end_to_end_il_documento_engine_porta_i_valori_del_corredo():
    """Il corredo si consuma al load: nel documento engine restano solo i
    numeri che ha prodotto, nessuna traccia della dichiarazione."""
    from granstudies.envelope_sweep import generate_envelope_variants
    from granstudies.render import _envelope_document

    _, specs = _fixture("corredo_indice_costante.yml")
    spec = specs[0]
    variants = generate_envelope_variants(spec)
    assert variants, "lo sweep deve produrre almeno una variante"
    doc = _envelope_document(spec, variants[0])
    testo = repr(doc)
    assert "list" not in testo and "expr" not in testo
    stream = doc["streams"][0]
    # gli assi sono mossi da envelope: ogni breakpoint porta il valore che il
    # corredo ha prodotto (range 0 -> banda collassata, quattro plateau uguali)
    assert {y for _, y in stream["density"]["points"]} == {20.0}
    assert {y for _, y in stream["grain"]["duration"]["points"]} == {0.007}


# =============================================================================
# Fetta 2/7 (issue #49): l'indicizzazione per voce
# =============================================================================

def _spread(streams):
    from granstudies.spread import expand_spreads

    return expand_spreads(apply_group_let(streams))


def _accordo(let, spread_let, n=4, **extra):
    over = extra.pop("over", {"base.pan": {"expr": "i"}})
    return {
        "accordo": {
            "let": let,
            "spread": {"n": n, "let": spread_let, "over": over},
            "axes": {"density": {"base": {"expr": "r"}}},
            **extra,
        }
    }


def _r(out):
    """Il valore di ``r`` in ogni voce generata, in ordine."""
    return [v["axes"]["density"]["base"]["let"]["r"] for v in out.values()]


# --- ratio[i] ----------------------------------------------------------------

def test_indice_per_voce_in_spread_let():
    out = _spread(
        _accordo({"ratio": {"list": [2, 3, 4, 7]}}, {"r": {"expr": "ratio[i]"}})
    )
    assert _r(out) == [2, 3, 4, 7]


def test_indice_per_voce_in_una_strategy_expr_di_over():
    out = _spread(
        _accordo(
            {"ratio": {"list": [2, 3, 4, 7]}},
            {"r": {"expr": "i"}},
            over={"base.pointer.start": {"expr": "ratio[i] / 10"}},
        )
    )
    starts = [v["base"]["pointer"]["start"] for v in out.values()]
    assert starts == pytest.approx([0.2, 0.3, 0.4, 0.7])


def test_corredo_di_documento_letto_da_due_gruppi_ognuno_col_proprio_i():
    from granstudies.spread import expand_spreads

    doc = apply_document_let(
        _doc(
            {"ratio": {"list": [2, 3, 4, 7]}},
            streams={
                "a": {
                    "spread": {"n": 2, "let": {"r": {"expr": "ratio[i]"}},
                               "over": {"base.pan": {"expr": "i"}}},
                    "axes": {"density": {"base": {"expr": "r"}}},
                },
                "b": {
                    "spread": {"n": 3, "let": {"r": {"expr": "ratio[i + 1]"}},
                               "over": {"base.pan": {"expr": "i"}}},
                    "axes": {"density": {"base": {"expr": "r"}}},
                },
            },
        )
    )
    out = expand_spreads(doc["streams"])
    assert _r({k: v for k, v in out.items() if k.startswith("a_")}) == [2, 3]
    assert _r({k: v for k, v in out.items() if k.startswith("b_")}) == [3, 4, 7]


# --- indici negativi ---------------------------------------------------------

@pytest.mark.parametrize("k, atteso", [(-1, 7), (-2, 4), (-3, 3), (-4, 2)])
def test_indice_negativo(k, atteso):
    assert eval_expr(f"ratio[{k}]", {"ratio": {"list": [2, 3, 4, 7]}}) == atteso


def test_indice_negativo_inverte_il_senso_di_lettura():
    out = _spread(
        _accordo({"ratio": {"list": [2, 3, 4, 7]}}, {"r": {"expr": "ratio[-1 - i]"}})
    )
    assert _r(out) == [7, 4, 3, 2]


def test_negativo_oltre_la_lunghezza_e_errore():
    with pytest.raises(ValueError, match="fuori dal corredo"):
        eval_expr("ratio[-5]", {"ratio": {"list": [2, 3, 4, 7]}})


def test_il_messaggio_di_fuori_range_elenca_entrambi_i_versi():
    with pytest.raises(ValueError) as exc:
        eval_expr("ratio[-5]", {"ratio": {"list": [2, 3, 4, 7]}})
    msg = str(exc.value)
    assert "0..3" in msg and "-1..-4" in msg


# --- fuori range dentro lo spread --------------------------------------------

def test_n_maggiore_di_len_su_corredo_finito_e_errore():
    with pytest.raises(SpecError) as exc:
        _spread(_accordo({"ratio": {"list": [2, 3]}}, {"r": {"expr": "ratio[i]"}}, n=4))
    msg = str(exc.value)
    assert "voce 3 di 4" in msg      # la voce
    assert "ratio" in msg            # il nome del corredo
    assert "2 elementi" in msg       # la lunghezza


def test_n_minore_di_len_non_e_errore():
    """Un corredo sotto-consumato e' legittimo: si sta ascoltando un
    sottoinsieme dell'accordo. Il warning arriva nella fetta 6/7."""
    out = _spread(
        _accordo({"ratio": {"list": [2, 3, 4, 7]}}, {"r": {"expr": "ratio[i]"}}, n=2)
    )
    assert _r(out) == [2, 3]


def test_n_uguale_a_len_e_il_caso_pieno():
    out = _spread(
        _accordo({"ratio": {"list": [2, 3, 4, 7]}}, {"r": {"expr": "ratio[i]"}}, n=4)
    )
    assert _r(out) == [2, 3, 4, 7]


# --- il corredo non si dichiara nello spread ---------------------------------

def test_corredo_in_spread_let_e_errore_con_hint_al_let_di_gruppo():
    with pytest.raises(SpecError) as exc:
        _spread(
            {
                "a": {
                    "spread": {"n": 2, "let": {"ratio": {"list": [2, 3]}},
                               "over": {"base.pan": {"expr": "i"}}},
                    "axes": {"density": {"base": {"expr": "ratio[0]"}}},
                }
            }
        )
    msg = str(exc.value)
    assert "let:" in msg and "gruppo" in msg


def test_corredo_come_strategy_di_over_e_errore():
    with pytest.raises(SpecError, match="non e' una strategy"):
        _spread(
            {
                "a": {
                    "spread": {"n": 2, "over": {"base.pan": {"list": [2, 3]}}},
                    "axes": {"density": {"base": 5}},
                }
            }
        )


def test_i_e_n_restano_non_ridichiarabili():
    with pytest.raises(SpecError, match="riservati"):
        _spread(
            _accordo(
                {"ratio": {"list": [2, 3, 4, 7]}},
                {"r": {"expr": "ratio[i]", "let": {"i": 2}}},
            )
        )


def test_end_to_end_accordo_quattro_voci_coi_periodi_attesi():
    """Quattro voci, periodi 2s / 3s / 4s / 7s: la polimetria in rapporti
    scelti, con la fondamentale letta da un secondo asse."""
    _, specs = _fixture("corredo_accordo.yml")
    assert len(specs) == 4
    assert [s.axis("density").values[0] for s in specs] == pytest.approx(
        [2.0, 3.0, 4.0, 7.0]
    )
    # grain.duration legge ratio[0] in tutte le voci: la fondamentale e' una
    # sola, dichiarata una volta
    for s in specs:
        assert s.axis("grain_duration").values[0] == pytest.approx(0.05)
    # ogni voce legge un punto diverso del sample
    assert [s.stream_id for s in specs] == [f"accordo_{k}" for k in range(1, 5)]


# =============================================================================
# Fetta 4/7 (issue #51): la primitiva len()
# =============================================================================

def test_len_di_un_corredo():
    assert eval_expr("len(ratio)", {"ratio": {"list": [2, 3, 4, 7]}}) == 4


def test_len_in_uno_scope_di_asse():
    out = apply_document_let(
        _doc(
            {"ratio": {"list": [2, 3, 4, 7]}},
            axes={"density": {"base": {"expr": "len(ratio) * 10"}}},
        )
    )
    from granstudies.expr import eval_expr as _e

    nodo = out["axes"]["density"]["base"]
    assert _e(nodo["expr"], nodo["let"]) == 40


def test_len_dentro_una_manopola_derivata_di_let():
    """Richiede il fix di #45: senza, il nome della primitiva restava nel
    cancello del fixpoint di ``resolve_knobs`` e la manopola non risolveva
    mai, con un errore di «dipendenze cicliche» inesistenti."""
    out = apply_document_let(
        _doc(
            {"ratio": {"list": [2, 3, 4, 7]}, "quante": {"expr": "len(ratio)"}},
            axes={"density": {"base": {"expr": "quante"}}},
        )
    )
    assert out["axes"]["density"]["base"]["let"]["quante"] == 4


def test_len_di_un_envelope_e_errore():
    with pytest.raises(ValueError, match="vuole un corredo"):
        eval_expr("len(s)", {"s": [[0, 1], [1, 2]]})


def test_il_messaggio_spiega_perche_len_di_un_envelope_non_esiste():
    with pytest.raises(ValueError) as exc:
        eval_expr("len(s)", {"s": [[0, 1], [1, 2]]})
    assert "rappresentazione" in str(exc.value)


def test_len_di_uno_scalare_e_errore():
    with pytest.raises(ValueError, match="vuole un corredo"):
        eval_expr("len(d)", {"d": 25})


def test_len_di_un_nome_inesistente_e_errore():
    with pytest.raises(ValueError, match="nome ignoto"):
        eval_expr("len(boh)", {"d": 1})


def test_len_di_una_espressione_e_errore():
    with pytest.raises(ValueError, match="per nome"):
        eval_expr("len(2 + 2)", {"ratio": {"list": [2, 3]}})


@pytest.mark.parametrize("text", ["len()", "len(ratio, 2)"])
def test_len_vuole_esattamente_un_argomento(text):
    with pytest.raises(ValueError, match="1 argomento"):
        eval_expr(text, {"ratio": {"list": [2, 3]}})


# --- spread.n legato al corredo ----------------------------------------------

def test_spread_n_da_len_produce_la_popolazione_del_corredo():
    """La direzione ammessa: il corredo puo' *dare* n, non prenderlo. Non e'
    circolare, perche' il corredo si risolve al load, prima dell'espansione."""
    out = _spread(
        _accordo(
            {"ratio": {"list": [2, 3, 4, 7]}},
            {"r": {"expr": "ratio[i]"}},
            n={"expr": "len(ratio)"},
            over={"base.pointer.start": {"ramp": {"start": 0.1, "step": 0.2}}},
        )
    )
    assert len(out) == 4
    assert _r(out) == [2, 3, 4, 7]


def test_spread_n_da_len_segue_un_corredo_piu_corto():
    out = _spread(
        _accordo(
            {"ratio": {"list": [2, 3, 4]}},
            {"r": {"expr": "ratio[i]"}},
            n={"expr": "len(ratio)"},
            over={"base.pointer.start": {"ramp": {"start": 0.1, "step": 0.2}}},
        )
    )
    assert _r(out) == [2, 3, 4]


# --- l'accordo replicato per ottave ------------------------------------------

def test_accordo_replicato_per_ottave():
    """L'idioma del design doc: `%` e `//` erano entrati per trasformare `i` in
    coordinate di griglia; qui danno tre ottave dello stesso accordo."""
    streams = {
        "accordo": {
            "let": {"d": 1, "ratio": {"list": [2, 3, 4, 7]}},
            "spread": {
                "n": 12,
                "let": {
                    "r": {"expr": "ratio[i % len(ratio)]"},
                    "ott": {"expr": "2 ** (i // len(ratio))"},
                },
                "over": {"base.pointer.start": {"ramp": {"start": 0.05,
                                                         "step": 0.075}}},
            },
            "axes": {"density": {"base": {"expr": "d * r / ott"}}},
        }
    }
    out = _spread(streams)
    periodi = [
        v["axes"]["density"]["base"]["let"]["r"]
        / v["axes"]["density"]["base"]["let"]["ott"]
        for v in out.values()
    ]
    assert periodi == pytest.approx(
        [2, 3, 4, 7, 1, 1.5, 2, 3.5, 0.5, 0.75, 1, 1.75]
    )


# --- la lista resta non passabile a ogni altra funzione ----------------------

@pytest.mark.parametrize(
    "text", ["min(ratio, 2)", "max(ratio, 2)", "abs(ratio)", "floor(ratio)",
             "mix(ratio, 1, 0.5)"]
)
def test_nessuna_altra_funzione_accetta_un_corredo(text):
    with pytest.raises(ValueError, match="solo per indice"):
        eval_expr(text, {"ratio": {"list": [2, 3]}})


# =============================================================================
# Fetta 5/7 (issue #52): generatori dentro list:
# =============================================================================

def _corredo_risolto(node, nome="ratio"):
    """Il corredo come lo vede un'espressione, passando per il ``let:``."""
    out = apply_document_let(
        _doc({nome: node}, axes={"d": {"base": {"expr": f"{nome}[0]"}}})
    )
    return out["axes"]["d"]["base"]["let"][nome]["list"]


def test_corredo_da_ramp_pieno():
    assert _corredo_risolto({"list": {"ramp": {"start": 1, "stop": 8, "step": 1}}}) == [
        1, 2, 3, 4, 5, 6, 7, 8
    ]


def test_corredo_da_values_equivale_alla_lista_letterale():
    assert _corredo_risolto({"list": {"values": [2, 3, 4, 7]}}) == _corredo_risolto(
        {"list": [2, 3, 4, 7]}
    )


def test_corredo_pescato():
    from granstudies.value_generators import band

    got = _corredo_risolto({"list": {"n": 5, "base": 2, "range": 6, "seed": 1988}})
    assert got == band(5, 2, 6, seed=1988)
    assert all(2 <= v <= 8 for v in got)


def test_corredo_pescato_deterministico_fra_run():
    node = {"list": {"n": 12, "base": 2, "range": 6, "seed": 1988}}
    assert _corredo_risolto(node) == _corredo_risolto(node)


def test_corredo_pescato_senza_seed_deriva_dalla_catena_gerarchica():
    """Stessa derivazione delle altre manopole generate: il prefisso del blocco
    piu' il nome della manopola."""
    from granstudies.value_generators import band, stable_seed

    got = _corredo_risolto({"list": {"n": 4, "base": 2, "range": 6}})
    assert got == band(4, 2, 6, seed=stable_seed("t:let:ratio"))


def test_corredo_pescato_di_gruppo_deriva_dal_nome_del_gruppo():
    from granstudies.value_generators import band, stable_seed

    out = apply_group_let(
        {
            "cugini": {
                "let": {"ratio": {"list": {"n": 4, "base": 2, "range": 6}}},
                "axes": {"density": {"base": {"expr": "ratio[0]"}}},
            }
        }
    )
    got = out["cugini"]["axes"]["density"]["base"]["let"]["ratio"]["list"]
    assert got == band(4, 2, 6, seed=stable_seed("cugini:let:ratio"))


def test_l_insieme_pescato_esiste_come_oggetto():
    """Il caso che oggi non esisteva: la banda di ``spread.let`` pesca per
    voce e l'insieme non e' un oggetto — non se ne puo' nominare la
    fondamentale. Pescato una volta e indicizzato, `ratio[i] / ratio[0]`
    diventa scrivibile."""
    out = _spread(
        _accordo(
            {"ratio": {"list": {"n": 4, "base": 2, "range": 6, "seed": 1988}}},
            {"r": {"expr": "ratio[i] / ratio[0]"}},
        )
    )
    rapporti = _r(out)
    assert rapporti[0] == 1.0                     # la prima estratta e' l'unita'
    assert len({round(x, 9) for x in rapporti}) == 4


def test_len_di_un_corredo_generato():
    out = apply_document_let(
        _doc(
            {"ratio": {"list": {"ramp": {"start": 1, "stop": 8, "step": 1}}}},
            axes={"d": {"base": {"expr": "len(ratio)"}}},
        )
    )
    nodo = out["axes"]["d"]["base"]
    assert eval_expr(nodo["expr"], nodo["let"]) == 8


# --- le forme senza conteggio proprio sono errore ----------------------------

@pytest.mark.parametrize(
    "gen, atteso",
    [
        ({"ramp": {"start": 1, "step": 1}}, "stop"),
        ({"ramp": {"start": 1, "stop": 8}}, "step"),
        ({"base": 2, "range": 6}, "n"),
    ],
)
def test_generatore_senza_conteggio_proprio_e_errore(gen, atteso):
    with pytest.raises(SpecError) as exc:
        apply_document_let(
            _doc({"ratio": {"list": gen}}, axes={"d": {"base": {"expr": "ratio[0]"}}})
        )
    msg = str(exc.value)
    assert atteso in msg
    assert "possiede la propria lunghezza" in msg


def test_il_messaggio_della_banda_rimanda_a_spread_let():
    with pytest.raises(SpecError) as exc:
        apply_document_let(
            _doc(
                {"ratio": {"list": {"base": 2, "range": 6}}},
                axes={"d": {"base": {"expr": "ratio[0]"}}},
            )
        )
    assert "spread.let" in str(exc.value)


def test_linear_env_dentro_list_e_errore():
    """I due wrapper marcano ruoli opposti: uno si legge per tempo, l'altro
    per indice. Annidarli e' una contraddizione."""
    with pytest.raises(SpecError, match="per indice"):
        apply_document_let(
            _doc(
                {"ratio": {"list": {"linear_env": [2, 3]}}},
                axes={"d": {"base": {"expr": "ratio[0]"}}},
            )
        )


def test_generatore_senza_marcatore_dentro_list_e_errore():
    with pytest.raises(SpecError, match="chiave-generatore"):
        apply_document_let(
            _doc(
                {"ratio": {"list": {"boh": 1}}},
                axes={"d": {"base": {"expr": "ratio[0]"}}},
            )
        )


def test_bordi_annidati_dentro_una_banda_di_corredo():
    """``base``/``range`` della banda restano Env: un ``linear_env`` dentro si
    espande come sempre."""
    got = _corredo_risolto(
        {"list": {"n": 4, "base": {"linear_env": [0, 30]}, "range": 0, "seed": 1}}
    )
    assert got == pytest.approx([0.0, 10.0, 20.0, 30.0])


# =============================================================================
# Fetta 3/7 (issue #50): cycle — accordo o pattern
# =============================================================================

def _politica(elems, cycle=None):
    node = {"list": elems}
    if cycle is not None:
        node["cycle"] = cycle
    out = apply_document_let(
        _doc({"ratio": node}, axes={"d": {"base": {"expr": "ratio[0]"}}})
    )
    return out["axes"]["d"]["base"]["let"]["ratio"]


def test_senza_cycle_il_corredo_e_un_accordo():
    assert _politica([2, 3, 4, 7]) == {"list": [2, 3, 4, 7]}


def test_cycle_true_lo_rende_un_pattern():
    assert _politica([2, 3, 4, 7], True) == {"list": [2, 3, 4, 7], "cycle": True}


def test_cycle_false_e_esplicitamente_un_accordo():
    assert _politica([2, 3, 4, 7], False) == {"list": [2, 3, 4, 7]}


# --- l'avvolgimento ----------------------------------------------------------

@pytest.mark.parametrize("k, atteso", [(4, 2), (5, 3), (9, 3), (12, 2)])
def test_l_indice_si_avvolge(k, atteso):
    c = _politica([2, 3, 4, 7], True)
    assert eval_expr(f"ratio[{k}]", {"ratio": c}) == atteso


def test_la_regola_vale_identica_per_indici_costanti_e_calcolati():
    """Se dipendesse dall'essere l'indice costante o calcolato, tornerebbe a
    dipendere dall'uso — che e' cio' che il design ha scartato tre volte."""
    c = _politica([2, 3, 4, 7], True)
    costante = eval_expr("ratio[9]", {"ratio": c})
    calcolato = eval_expr("ratio[i]", {"ratio": c, "i": 9})
    assert costante == calcolato == 3


@pytest.mark.parametrize("k, atteso", [(-1, 7), (-4, 2), (-5, 7), (-6, 4)])
def test_i_negativi_cadono_fuori_gratis_dal_modulo(k, atteso):
    c = _politica([2, 3, 4, 7], True)
    assert eval_expr(f"ratio[{k}]", {"ratio": c}) == atteso


def test_su_un_accordo_lo_stesso_indice_e_errore():
    c = _politica([2, 3, 4, 7])
    with pytest.raises(ValueError, match="accordo"):
        eval_expr("ratio[9]", {"ratio": c})


def test_il_messaggio_dell_accordo_indica_cycle():
    c = _politica([2, 3, 4, 7])
    with pytest.raises(ValueError) as exc:
        eval_expr("ratio[9]", {"ratio": c})
    assert "cycle: true" in str(exc.value)


# --- le guardie --------------------------------------------------------------

def test_corredo_vuoto_ciclico_resta_errore():
    """Sarebbe anche un modulo per zero."""
    with pytest.raises(SpecError, match="vuoto"):
        apply_document_let(
            _doc(
                {"ratio": {"list": [], "cycle": True}},
                axes={"d": {"base": {"expr": "ratio[0]"}}},
            )
        )


def test_cycle_senza_list_e_errore():
    with pytest.raises(SpecError, match="senza 'list'"):
        apply_document_let(
            _doc({"ratio": {"cycle": True}}, axes={"d": {"base": {"expr": "ratio"}}})
        )


def test_cycle_non_booleano_e_errore():
    with pytest.raises(SpecError, match="true o false"):
        apply_document_let(
            _doc(
                {"ratio": {"list": [2, 3], "cycle": "si"}},
                axes={"d": {"base": {"expr": "ratio[0]"}}},
            )
        )


def test_cycle_si_combina_con_un_corredo_generato():
    """Nessun caso speciale: `cycle` e' la politica, il generatore produce gli
    elementi (criterio rimandato qui dalla fetta 5/7)."""
    c = _politica({"ramp": {"start": 1, "stop": 3, "step": 1}}, True)
    assert c == {"list": [1, 2, 3], "cycle": True}
    assert eval_expr("ratio[4]", {"ratio": c}) == 2


def test_cycle_si_combina_con_un_corredo_pescato():
    from granstudies.value_generators import band

    c = _politica({"n": 3, "base": 2, "range": 6, "seed": 1988}, True)
    assert c["list"] == band(3, 2, 6, seed=1988)
    assert eval_expr("ratio[3]", {"ratio": c}) == c["list"][0]


# --- i due casi d'ascolto ----------------------------------------------------

def test_ispessimento_tre_voci_per_rapporto():
    """Tre voci per rapporto, ognuna che legge un punto diverso del buffer:
    stesso periodo, contenuto e fase diversi. L'accordo si ispessisce senza
    cambiare le altezze."""
    out = _spread(
        _accordo(
            {"ratio": {"list": [2, 3, 4, 7], "cycle": True}},
            {"r": {"expr": "ratio[i]"}},
            n=12,
            over={"base.pointer.start": {"ramp": {"start": 0.05, "step": 0.075}}},
        )
    )
    assert _r(out) == [2, 3, 4, 7, 2, 3, 4, 7, 2, 3, 4, 7]
    starts = [v["base"]["pointer"]["start"] for v in out.values()]
    assert len(set(starts)) == 12          # ogni voce legge un punto diverso


def test_isoritmo_due_corredi_coprimi():
    """Color e talea: due corredi ciclici di lunghezze coprime scorrono uno
    contro l'altro, e il pattern combinato ha periodo lcm(4, 3) = 12. Cade
    fuori da due `cycle: true`, senza sintassi dedicata.

    (Il design doc dice «la coppia non si ripete prima della voce 12»: con
    `durate: [1, 1, 2]`, che ha un duplicato, singole coppie *si* ripetono —
    e' la **sequenza** ad avere periodo 12, non ogni coppia a essere unica.)
    """
    streams = {
        "isoritmo": {
            "let": {
                "d": 1,
                "ratio": {"list": [2, 3, 4, 7], "cycle": True},
                "durate": {"list": [1, 1, 2], "cycle": True},
            },
            "spread": {
                "n": 12,
                "let": {"r": {"expr": "ratio[i]"}, "dur": {"expr": "durate[i]"}},
                # `durate[i]` di nuovo, non `dur`: le manopole di `spread.let`
                # sono iniettate negli stream generati, non nelle strategy di
                # `over` che corrono in parallelo a loro.
                "over": {"duration": {"expr": "durate[i] * 8"}},
            },
            "axes": {"density": {"base": {"expr": "d * r"}}},
        }
    }
    out = _spread(streams)
    rapporti = [v["axes"]["density"]["base"]["let"]["r"] for v in out.values()]
    durate = [v["duration"] for v in out.values()]
    # i due corredi scorrono uno contro l'altro: 4 e 3 sono coprimi
    assert rapporti == [2, 3, 4, 7] * 3
    assert durate == [8, 8, 16] * 4
    coppie = list(zip(rapporti, durate))
    assert coppie[0] == (2, 8)
    # il periodo minimo della sequenza di coppie e' 12, non uno dei divisori
    assert all(
        coppie[:12 - p] != coppie[p:]
        for p in (1, 2, 3, 4, 6)
    )


def test_end_to_end_ispessimento():
    _, specs = _fixture("corredo_ispessimento.yml")
    assert len(specs) == 12
    periodi = [s.axis("density").values[0] for s in specs]
    assert periodi == pytest.approx([2, 3, 4, 7] * 3)


def test_end_to_end_isoritmo():
    _, specs = _fixture("corredo_isoritmo.yml")
    assert len(specs) == 12
    assert [s.axis("density").values[0] for s in specs] == pytest.approx(
        [2, 3, 4, 7] * 3
    )
    assert [s.duration for s in specs] == pytest.approx([8, 8, 16] * 4)


# =============================================================================
# Fetta 7/7 (issue #54): corredi sotto versions: e percorso:
# =============================================================================

def _versioni(data):
    """Le voci generate per ogni combinazione di ``versions:``."""
    from granstudies.spread import expand_spreads
    from granstudies.versions import axis_combos, inject_combo, parse_version_axes

    axes = parse_version_axes(data)
    doc = apply_document_let(data)
    out = {}
    for label, combo in axis_combos(axes):
        d = inject_combo(doc, combo)
        out[label] = expand_spreads(apply_group_let(d["streams"]))
    return out


def _due_intonazioni(n, **extra):
    return {
        "study_id": "t",
        "let": {"ratio": {"list": [2, 3, 4, 7]}, **extra.pop("let", {})},
        "versions": {
            "intonazione": {
                "giusta": {"ratio": {"list": [2, 3, 4, 7]}},
                "stretta": {"ratio": {"list": [2, 3, 4]}},
            }
        },
        "streams": {
            "cugini": {
                "spread": {
                    "n": n,
                    "let": {"r": {"expr": "ratio[i]"}},
                    "over": {"base.pan": {"expr": "i"}},
                },
                "axes": {"density": {"base": {"expr": "r"}}},
            }
        },
        **extra,
    }


def test_uno_stato_puo_sostituire_un_corredo():
    """Due insiemi di rapporti a confronto all'ascolto: due intonazioni."""
    got = _versioni(_due_intonazioni({"expr": "len(ratio)"}))
    assert _r(got["intonazione=giusta"]) == [2, 3, 4, 7]
    assert _r(got["intonazione=stretta"]) == [2, 3, 4]


def test_la_popolazione_segue_il_corredo_della_versione():
    got = _versioni(_due_intonazioni({"expr": "len(ratio)"}))
    assert len(got["intonazione=giusta"]) == 4
    assert len(got["intonazione=stretta"]) == 3


def test_il_pad_dei_nomi_e_stabile_fra_versioni():
    """Il pad si fissa sul massimo dell'intero prodotto cartesiano (#39): la
    stessa voce logica ha lo stesso nome ovunque esista."""
    from granstudies.versions import generate_versions_document

    data = _due_intonazioni({"expr": "len(ratio)"})
    data["versions"]["duration"] = 10        # il passo della concatenazione
    data.update(
        {
            "base": {"sample": "corpus.wav", "duration": 10, "onset": 0},
            "axes": {"density": {"path": "density", "baseline": 20, "n": 2,
                                 "base": 20, "range": 0}},
            "stack": {},
        }
    )
    data["streams"]["cugini"]["axes"] = {
        "density": {"base": {"expr": "r"}, "range": 0}
    }
    doc = generate_versions_document(data, "t", output_sr=None)
    ids = [s["stream_id"] for s in doc["streams"]]
    giusta = sorted(i.split("__")[0] for i in ids if "giusta" in i)
    stretta = sorted(i.split("__")[0] for i in ids if "stretta" in i)
    assert giusta == ["cugini_1", "cugini_2", "cugini_3", "cugini_4"]
    assert stretta == ["cugini_1", "cugini_2", "cugini_3"]


# --- il tipo lo fissa la dichiarazione ---------------------------------------

def test_uno_stato_che_sostituisce_un_corredo_con_altro_e_errore():
    data = _due_intonazioni(2)
    data["versions"]["intonazione"]["stretta"] = {"ratio": 5}
    with pytest.raises(SpecError, match="mai il suo tipo"):
        apply_document_let(data)


def test_uno_stato_che_cambia_la_politica_cycle_e_errore():
    data = _due_intonazioni(2)
    data["versions"]["intonazione"]["stretta"] = {
        "ratio": {"list": [2, 3, 4], "cycle": True}
    }
    with pytest.raises(SpecError, match="politica di 'cycle'"):
        apply_document_let(data)


def test_il_messaggio_spiega_perche_la_politica_non_si_muove():
    data = _due_intonazioni(2)
    data["versions"]["intonazione"]["stretta"] = {
        "ratio": {"list": [2, 3, 4], "cycle": True}
    }
    with pytest.raises(SpecError) as exc:
        apply_document_let(data)
    assert "da una versione all'altra" in str(exc.value)


def test_un_pattern_puo_essere_sostituito_da_un_altro_pattern():
    data = _due_intonazioni(2)
    data["let"]["ratio"]["cycle"] = True
    for stato in data["versions"]["intonazione"].values():
        stato["ratio"]["cycle"] = True
    assert apply_document_let(data)


def test_un_corredo_di_gruppo_mosso_da_versions():
    data = {
        "study_id": "t",
        "versions": {"i18e": {"g": {"ratio": {"list": [2, 3]}}}},
        "streams": {
            "cugini": {
                "let": {"ratio": {"list": [2, 3, 4, 7]}},
                "spread": {"n": 2, "let": {"r": {"expr": "ratio[i]"}},
                           "over": {"base.pan": {"expr": "i"}}},
                "axes": {"density": {"base": {"expr": "r"}}},
            }
        },
    }
    assert apply_document_let(data)
    data["versions"]["i18e"]["g"]["ratio"] = 5
    with pytest.raises(SpecError, match="mai il suo tipo"):
        apply_document_let(data)


def test_una_traiettoria_di_percorso_non_puo_sostituire_un_corredo():
    data = _due_intonazioni(2)
    del data["versions"]
    data["percorso"] = {"k": 3, "arco": 10, "passo": 2, "ratio": 5}
    with pytest.raises(SpecError, match="legge sul tempo"):
        apply_document_let(data)


# --- la guardia anti-refuso ---------------------------------------------------

def test_la_guardia_di_versions_riconosce_l_uso_per_indicizzazione():
    """`ratio[i]` registra `ratio` fra i nomi referenziati: la guardia non ha
    richiesto modifiche."""
    from granstudies.versions import parse_version_axes

    data = _due_intonazioni({"expr": "len(ratio)"})
    assert parse_version_axes(data)          # nessun «non e' referenziata»


def test_uno_stato_che_muove_un_corredo_mai_indicizzato_e_errore():
    data = _due_intonazioni(2)
    data["streams"]["cugini"]["spread"]["let"] = {"r": {"expr": "i"}}
    data["streams"]["cugini"]["axes"] = {"density": {"base": {"expr": "r"}}}
    from granstudies.versions import parse_version_axes

    with pytest.raises(SpecError, match="non e' referenziata"):
        parse_version_axes(data)


# --- make stack ignora versions ------------------------------------------------

def test_stack_usa_il_corredo_del_let_non_quello_di_versions():
    """`versions:` resta analisi: `make stack` non lo vede, e legge il corredo
    dichiarato in `let:` — l'istanza di partenza."""
    data = _due_intonazioni({"expr": "len(ratio)"})
    out = expand_spreads_from(apply_document_let(data))
    assert _r(out) == [2, 3, 4, 7]           # il riposo, non 'stretta'


def expand_spreads_from(doc):
    from granstudies.spread import expand_spreads

    return expand_spreads(apply_group_let(doc["streams"]))


# =============================================================================
# Il `let` locale di un nodo-expr: letterale sì, generato no
# =============================================================================

def _nodo(ratio):
    return {"expr": "ratio[1] * 10", "let": {"ratio": ratio}}


def test_corredo_letterale_nel_let_locale_e_ammesso():
    """E' un valore statico come `[[0, 1], [1, 2]]`, che quel `let` accetta
    gia': vietarlo sarebbe arbitrario."""
    assert eval_expr("ratio[1] * 10", {"ratio": {"list": [2, 3, 4]}}) == 30


def test_corredo_letterale_nel_let_locale_attraversa_il_load():
    doc = apply_document_let(
        {"study_id": "t", "axes": {"density": {"base": _nodo({"list": [2, 3, 4]})}}}
    )
    assert doc["axes"]["density"]["base"]["let"]["ratio"] == {"list": [2, 3, 4]}


def test_corredo_generato_nel_let_locale_e_errore_al_load():
    """Il `let` locale entra nello scope com'e' scritto — `resolve_knobs` lo
    fonde grezzo — quindi il generatore non verrebbe mai eseguito e non
    avrebbe un seed da cui pescare."""
    gen = {"list": {"ramp": {"start": 1, "stop": 8, "step": 1}}}
    with pytest.raises(SpecError, match="senza espansione e senza seed"):
        apply_document_let(
            {"study_id": "t", "axes": {"density": {"base": _nodo(gen)}}}
        )


def test_il_messaggio_distingue_il_letterale_dal_generato():
    gen = {"list": {"n": 3, "base": 2, "range": 6}}
    with pytest.raises(SpecError) as exc:
        apply_document_let(
            {"study_id": "t", "axes": {"density": {"base": _nodo(gen)}}}
        )
    msg = str(exc.value)
    assert "letterale" in msg and "let:' di documento o di gruppo" in msg


def test_la_guardia_trova_il_nodo_ovunque_sia_nel_documento():
    gen = {"list": {"ramp": {"start": 1, "stop": 8, "step": 1}}}
    with pytest.raises(SpecError, match="senza seed"):
        apply_document_let(
            {
                "study_id": "t",
                "streams": {
                    "cugini": {
                        "spread": {
                            "n": 2,
                            "let": {"r": _nodo(gen)},
                            "over": {"base.pan": {"expr": "i"}},
                        },
                        "axes": {"density": {"base": {"expr": "r"}}},
                    }
                },
            }
        )


def test_un_corredo_di_documento_generato_resta_ammesso():
    """La guardia colpisce il `let` *locale* di un nodo-expr, non il blocco
    `let:` che lo risolve al load."""
    doc = apply_document_let(
        {
            "study_id": "t",
            "let": {"ratio": {"list": {"ramp": {"start": 1, "stop": 8, "step": 1}}}},
            "axes": {"density": {"base": {"expr": "ratio[0]"}}},
        }
    )
    assert doc["axes"]["density"]["base"]["let"]["ratio"]["list"] == [
        1, 2, 3, 4, 5, 6, 7, 8
    ]


def test_la_guardia_e_idempotente_dopo_l_iniezione():
    """`_write_expanded_streams` richiama `apply_document_let`: l'iniezione
    mette in scope corredi gia' *risolti*, cioe' letterali, quindi la seconda
    passata non produce falsi positivi."""
    d = {
        "study_id": "t",
        "let": {"ratio": {"list": {"ramp": {"start": 1, "stop": 8, "step": 1}}}},
        "axes": {"density": {"base": {"expr": "ratio[0]"}}},
    }
    uno = apply_document_let(d)
    assert apply_document_let(uno) == uno
