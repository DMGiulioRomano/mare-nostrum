"""Diagnostica non fatale: il corredo sotto-consumato (issue #53).

Un corredo sotto-consumato e' legittimo — si sta ascoltando un sottoinsieme
dell'accordo — ma e' anche il sintomo piu' comune di un refuso. Quindi
warning, non errore.

Il vincolo che conta non e' il messaggio: e' che il controllo sia una
**funzione pura** ``(documento, Locations) -> diagnostici``, con stderr e il
language server come due consumatori. Se nascesse come ``print`` dentro la
CLI, ``gl-ls`` dovrebbe riscriverlo e le due diagnostiche divergerebbero.
"""
import pytest

from granstudies.diagnostics import (
    CORREDO_SOTTO_CONSUMATO,
    Diagnostic,
    WarnCtx,
    check_corredi,
    check_corredi_combos,
    dedup,
)


def _doc(let=None, streams=None, **rest):
    d = {"study_id": "t"}
    if let is not None:
        d["let"] = let
    if streams is not None:
        d["streams"] = streams
    d.update(rest)
    return d


def _gruppo(let, n, expr="ratio[i]", **spread_extra):
    return {
        "cugini": {
            "let": let,
            "spread": {
                "n": n,
                "let": {"r": {"expr": expr}},
                "over": {"base.pan": {"expr": "i"}},
                **spread_extra,
            },
            "axes": {"density": {"base": {"expr": "r"}}},
        }
    }


# --- il canale ---------------------------------------------------------------

def test_warnctx_raccoglie_invece_di_alzare():
    ctx = WarnCtx()
    ctx.warn("qualcosa", code="x", key=("let", "a"), hint="rimedio")
    assert len(ctx.items) == 1
    assert isinstance(ctx.items[0], Diagnostic)


def test_il_layout_e_quello_degli_errori():
    """Un rilievo e un errore devono leggersi allo stesso modo."""
    ctx = WarnCtx()
    ctx.stream = "cugini"
    ctx.warn("qualcosa", code="x", key=("let", "a"), hint="rimedio")
    blocco = ctx.items[0].format_block()
    assert "posizione:" in blocco
    assert "contesto:   stream 'cugini'" in blocco
    assert "problema:" in blocco
    assert "rimedio:" in blocco


def test_dedup_tiene_l_ordine_di_prima_apparizione():
    a = Diagnostic("uno", code="x")
    b = Diagnostic("due", code="x")
    assert dedup([a, b, a, b, a]) == [a, b]


# --- il controllo, come funzione pura ----------------------------------------

def test_n_minore_di_len_produce_un_rilievo():
    got = check_corredi(_doc(streams=_gruppo({"ratio": {"list": [2, 3, 4, 7]}}, 2)))
    assert len(got) == 1
    assert got[0].code == CORREDO_SOTTO_CONSUMATO


def test_il_rilievo_riporta_gruppo_corredo_len_e_n():
    got = check_corredi(_doc(streams=_gruppo({"ratio": {"list": [2, 3, 4, 7]}}, 2)))
    msg = got[0].msg
    assert "cugini" in msg and "ratio" in msg and "4 elementi" in msg and "2 voci" in msg


def test_il_rilievo_riporta_la_riga():
    from granstudies.yaml_loc import loads

    testo = (
        "study_id: t\n"
        "streams:\n"
        "  cugini:\n"
        "    let:\n"
        "      ratio: {list: [2, 3, 4, 7]}\n"
        "    spread:\n"
        "      n: 2\n"
        "      let: {r: {expr: 'ratio[i]'}}\n"
        "      over: {base.pan: {expr: 'i'}}\n"
        "    axes: {density: {base: {expr: 'r'}}}\n"
    )
    data, locs = loads(testo, source="study.yml")
    got = check_corredi(data, locs)
    assert got and got[0].line == 5


@pytest.mark.parametrize("n", [4, 5, 12])
def test_nessun_rilievo_quando_n_uguale_o_maggiore_di_len(n):
    """``n > len`` e' errore su corredo finito e silenzio su ciclico: in
    nessuno dei due casi e' materia di questo warning."""
    assert check_corredi(_doc(streams=_gruppo({"ratio": {"list": [2, 3, 4, 7]}}, n))) == []


def test_solo_il_corredo_sotto_consumato_fra_due():
    """Per corredo, non per gruppo."""
    streams = {
        "cugini": {
            "let": {"ratio": {"list": [2, 3, 4, 7]}, "durate": {"list": [1, 1]}},
            "spread": {
                "n": 2,
                "let": {"r": {"expr": "ratio[i]"}, "x": {"expr": "durate[i]"}},
                "over": {"base.pan": {"expr": "i"}},
            },
            "axes": {"density": {"base": {"expr": "r"}}},
        }
    }
    got = check_corredi(_doc(streams=streams))
    assert len(got) == 1
    assert "ratio" in got[0].msg and "durate" not in got[0].msg


def test_un_corredo_letto_solo_con_indice_costante_non_e_sotto_consumato():
    """`ratio[0]` e' la fondamentale: non ne usa nemmeno uno oltre il primo, ed
    e' esattamente cio' che si voleva. «Gli elementi da indice n non sono
    usati» sarebbe falso."""
    streams = _gruppo({"ratio": {"list": [2, 3, 4, 7]}}, 2, expr="ratio[0] * i")
    assert check_corredi(_doc(streams=streams)) == []


def test_corredo_di_documento_sotto_consumato_da_un_gruppo():
    got = check_corredi(
        _doc(
            let={"ratio": {"list": [2, 3, 4, 7]}},
            streams=_gruppo({}, 2),
        )
    )
    assert len(got) == 1
    assert got[0].key == ("let", "ratio")


def test_nessun_rilievo_senza_spread():
    doc = _doc(
        let={"ratio": {"list": [2, 3, 4, 7]}},
        streams={"a": {"axes": {"density": {"base": {"expr": "ratio[0]"}}}}},
    )
    assert check_corredi(doc) == []


def test_un_corredo_malformato_non_produce_warning():
    """E' gia' un errore del load, con posizione e rimedio: un warning che lo
    duplica e' rumore."""
    assert check_corredi(_doc(streams=_gruppo({"ratio": {"list": []}}, 2))) == []


# --- il limite statico/dinamico ----------------------------------------------

def test_n_da_len_non_produce_mai_un_rilievo():
    """La forma con cui la popolazione segue il corredo: `n == len` per
    costruzione."""
    streams = _gruppo({"ratio": {"list": [2, 3, 4, 7]}}, {"expr": "len(ratio)"})
    assert check_corredi(_doc(streams=streams)) == []


def test_n_non_decidibile_staticamente_e_saltato():
    """`n` mosso da una variabile che il riposo non conosce: il rilievo puo'
    nascere solo alla generazione."""
    streams = _gruppo({"ratio": {"list": [2, 3, 4, 7]}}, {"expr": "k"})
    assert check_corredi(_doc(streams=streams)) == []


def test_n_da_una_manopola_scalare_e_decidibile():
    doc = _doc(
        let={"k": 2, "ratio": {"list": [2, 3, 4, 7]}},
        streams=_gruppo({}, {"expr": "k"}),
    )
    assert len(check_corredi(doc)) == 1


# --- versions: una volta per combinazione, deduplicato -----------------------

def test_con_versions_i_rilievi_sono_deduplicati():
    """Tre combinazioni che producono lo stesso rilievo ne danno uno: senza
    deduplica il rumore vanificherebbe il segnale."""
    doc = _doc(
        let={"k": 2, "g": 1, "ratio": {"list": [2, 3, 4, 7]}},
        versions={"g": {"values": [1, 2, 3]}},
        streams={
            "cugini": {
                "spread": {
                    "n": {"expr": "k"},
                    "let": {"r": {"expr": "ratio[i] * g"}},
                    "over": {"base.pan": {"expr": "i"}},
                },
                "axes": {"density": {"base": {"expr": "r"}}},
            }
        },
    )
    got = check_corredi_combos(doc)
    assert len(got) == 1


def test_con_versions_combinazioni_diverse_danno_rilievi_diversi():
    """Due `n` diversi sono due fatti diversi: la deduplica non li fonde."""
    doc = _doc(
        let={"k": 2, "ratio": {"list": [2, 3, 4, 7]}},
        versions={"k": {"values": [2, 3]}},
        streams=_gruppo({}, {"expr": "k"}),
    )
    got = check_corredi_combos(doc)
    assert len(got) == 2
    assert {"2 voci", "3 voci"} == {
        "2 voci" if "2 voci" in d.msg else "3 voci" for d in got
    }


def test_con_versions_una_combinazione_sana_non_zittisce_l_altra():
    doc = _doc(
        let={"k": 2, "ratio": {"list": [2, 3, 4, 7]}},
        versions={"k": {"values": [2, 4]}},
        streams=_gruppo({}, {"expr": "k"}),
    )
    got = check_corredi_combos(doc)
    assert len(got) == 1 and "2 voci" in got[0].msg


def test_senza_versions_equivale_al_controllo_semplice():
    doc = _doc(streams=_gruppo({"ratio": {"list": [2, 3, 4, 7]}}, 2))
    assert check_corredi_combos(doc) == check_corredi(doc)


def test_un_blocco_versions_rotto_non_fa_esplodere_il_controllo():
    doc = _doc(
        let={"ratio": {"list": [2, 3, 4, 7]}},
        versions={"x": {"a": {"values": [1, 2]}, "s": {"d0": 5}}},  # misto
        streams=_gruppo({}, 2),
    )
    assert len(check_corredi_combos(doc)) == 1


# --- quali elementi sono davvero non usati ------------------------------------
#
# La frase «gli elementi da indice n non sono usati» vale solo se l'indice e'
# ``ratio[i]``. Con un indice qualunque il corredo si legge altrove, e dire
# «da indice n» e' falso — con ``ratio[i + 2]`` e' esattamente rovesciato.

def _msg(let, n, expr):
    ds = check_corredi(_doc(streams=_gruppo(let, n, expr=expr)))
    assert len(ds) == 1, f"atteso un rilievo, trovati {len(ds)}"
    return ds[0].msg


CORREDO = {"ratio": {"list": [2, 3, 4, 7]}}


def test_indice_identita_nomina_gli_indici_di_coda():
    """``ratio[i]`` con n=2 legge 0 e 1: restano 2 e 3."""
    assert "2, 3" in _msg(CORREDO, 2, "ratio[i]")


def test_indice_traslato_nomina_gli_indici_di_testa():
    """``ratio[i + 2]`` con n=2 legge 2 e 3: restano 0 e 1, non «da indice 2»."""
    msg = _msg(CORREDO, 2, "ratio[i + 2]")
    assert "0, 1" in msg
    assert "da indice 2" not in msg


def test_indice_a_passo_due_nomina_gli_indici_dispari():
    """``ratio[i * 2]`` con n=2 legge 0 e 2: restano 1 e 3."""
    assert "1, 3" in _msg(CORREDO, 2, "ratio[i * 2]")


def test_indice_invertito_nomina_gli_indici_di_testa():
    """``ratio[-1 - i]`` con n=2 legge 3 e 2: restano 0 e 1."""
    assert "0, 1" in _msg(CORREDO, 2, "ratio[-1 - i]")


def test_il_rimedio_len_solo_quando_consumerebbe_davvero():
    """``n: len(ratio)`` e' il rimedio giusto solo per l'indice identita': con
    ``ratio[i + 2]`` alzare n manderebbe l'indice fuori range."""
    ds = check_corredi(_doc(streams=_gruppo(CORREDO, 2, expr="ratio[i]")))
    assert "len(ratio)" in (ds[0].hint or "")
    ds = check_corredi(_doc(streams=_gruppo(CORREDO, 2, expr="ratio[i + 2]")))
    assert "len(ratio)" not in (ds[0].hint or "")
