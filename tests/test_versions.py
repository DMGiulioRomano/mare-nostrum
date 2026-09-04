"""Test del processo ``versions``: repliche dello stack concatenate per onset.

Il blocco top-level ``versions:`` dichiara variabili (vocabolario dei
generatori Y) che vengono iniettate negli scope ``let`` dei nodi-expr del
documento; ogni combinazione (prodotto cartesiano, ordine di dichiarazione)
replica gli stream dello stack con onset scalato di ``k * duration``.
"""
import copy

import pytest

from granstudies.errors import SpecError
from granstudies.versions import (
    generate_versions_document,
    generate_versions_documents,
    inject_combo,
    parse_version_axes,
    parse_versions,
    version_combos,
)


# --- documento base condiviso dai test --------------------------------------

def _study(versions):
    # Ex 'duration: 20' top-level (#26): faceva sia da durata di stream sia da
    # passo delle versioni. Post-#42 le due cose sono separate — durata di
    # stream in 'base.duration', passo in 'versions.duration' — e questo helper
    # le riproduce entrambe, cosi' i test che non dichiarano una timeline
    # propria concatenano come prima. Con 'onset' o 'duration' gia' nel blocco
    # (una timeline esplicita) il passo di default non si aggiunge.
    versions = dict(versions)
    if "onset" not in versions and "duration" not in versions:
        versions["duration"] = 20
    return {
        "study_id": "vtest",
        "seed": 7,
        "base": {"onset": 0, "sample": "corpus.wav", "duration": 20},
        "axes": {
            "density": {
                "path": "density",
                "baseline": 50,
                "n": 4,
                "base": {
                    "expr": "env + d",
                    "let": {"env": [[0, 40], [1, 60]], "d": 0},
                },
                "range": 0,
            },
        },
        "stack": {},
        "streams": {
            "fermo": {
                "axes": {"density": {"base": {"expr": "env"}}},
            },
            "mobile": {},
        },
        "versions": versions,
    }


# --- parse e validazione -----------------------------------------------------

def test_parse_values_generator():
    data = _study({"d": {"values": [1, 2, 3]}})
    out = parse_versions(data)
    assert out == {"d": [1, 2, 3]}


def test_parse_ramp_generator():
    data = _study({"d": {"ramp": {"start": 1, "stop": 3, "step": 1}}})
    assert parse_versions(data) == {"d": [1, 2, 3]}


def test_parse_band_generator_deterministic():
    data = _study({"d": {"n": 3, "base": 0, "range": 10, "seed": 1}})
    a = parse_versions(data)
    b = parse_versions(data)
    assert a == b
    assert len(a["d"]) == 3
    assert all(0 <= v <= 10 for v in a["d"])


def test_parse_band_without_n_errors():
    data = _study({"d": {"base": 0, "range": 10}})
    with pytest.raises(SpecError, match="'n'"):
        parse_versions(data)


def test_empty_block_errors():
    data = _study({})
    with pytest.raises(SpecError, match="versions"):
        parse_versions(data)


def test_reserved_names_error():
    for name in ("i", "n", "pi", "e"):
        data = _study({name: {"values": [1]}})
        # la variabile riservata non e' referenziata, ma l'errore giusto e'
        # quello sul nome, non sul riferimento mancante.
        with pytest.raises(SpecError, match="riservat"):
            parse_versions(data)


def test_unreferenced_var_errors():
    data = _study({"zeta": {"values": [1, 2]}})
    with pytest.raises(SpecError, match="zeta"):
        parse_versions(data)


def test_versions_requires_stack_block():
    data = _study({"d": {"values": [1]}})
    del data["stack"]
    with pytest.raises(SpecError, match="stack"):
        generate_versions_document(data, "vtest", output_sr=None)


def test_versions_requires_step_to_concatenate():
    # Senza 'versions.onset' ne' 'versions.duration' non c'e' un passo con cui
    # posizionare le versioni: errore (post-#42 il 'duration:' top-level, che
    # in #26 faceva anche da passo, non esiste piu').
    data = _study({"d": {"values": [1]}})
    del data["versions"]["duration"]          # tolgo il passo di default
    with pytest.raises(SpecError, match="duration"):
        generate_versions_document(data, "vtest", output_sr=None)


# --- prodotto cartesiano -----------------------------------------------------

def test_combos_single_var():
    assert version_combos({"d": [1, 2, 3]}) == [{"d": 1}, {"d": 2}, {"d": 3}]


def test_combos_two_vars_lexicographic_declaration_order():
    combos = version_combos({"f": [50, 100], "d": [1, 2]})
    assert combos == [
        {"f": 50, "d": 1},
        {"f": 50, "d": 2},
        {"f": 100, "d": 1},
        {"f": 100, "d": 2},
    ]


# --- iniezione nello scope let ------------------------------------------------

def test_inject_shadows_let_default():
    data = _study({"d": {"values": [1, 2]}})
    out = inject_combo(data, {"d": 2})
    node = out["axes"]["density"]["base"]
    assert node["let"]["d"] == 2
    assert node["expr"] == "env + d"       # l'espressione non si tocca


def test_inject_only_where_referenced():
    data = _study({"d": {"values": [1]}})
    # lo stream 'fermo' ha un expr che NON nomina d: il suo let (ereditato
    # via deep-merge) non deve ricevere l'iniezione.
    out = inject_combo(data, {"d": 1})
    fermo = out["streams"]["fermo"]["axes"]["density"]["base"]
    assert "let" not in fermo or "d" not in (fermo.get("let") or {})


def test_inject_reaches_nested_expr_let():
    # expr annidato in let (issue #28): il nodo annidato che nomina la
    # variabile riceve l'iniezione nel *proprio* let, ombreggiando il default
    data = _study({"d": {"values": [1, 2]}})
    data["axes"]["density"]["base"] = {
        "expr": "g * 2",
        "let": {"g": {"expr": "d + 1", "let": {"d": 0}}},
    }
    out = inject_combo(data, {"d": 10})
    node = out["axes"]["density"]["base"]
    assert node["let"]["g"]["let"]["d"] == 10
    from granstudies.expr import eval_expr

    assert eval_expr(node["expr"], node["let"]) == 22


def test_inject_does_not_mutate_input():
    data = _study({"d": {"values": [1]}})
    snapshot = copy.deepcopy(data)
    inject_combo(data, {"d": 1})
    assert data == snapshot


# --- documento generato --------------------------------------------------------

def _doc(versions):
    return generate_versions_document(_study(versions), "vtest", output_sr=None)


def test_document_replicates_streams_per_combo():
    doc = _doc({"d": {"values": [1, 2, 3]}})
    ids = [s["stream_id"] for s in doc["streams"]]
    assert len(ids) == 6                    # 3 versioni x 2 stream
    assert ids[0] == "fermo__d=1"
    assert ids[1] == "mobile__d=1"
    assert ids[-1] == "mobile__d=3"


def test_document_onsets_shifted_by_version():
    doc = _doc({"d": {"values": [1, 2]}})
    onsets = [s["onset"] for s in doc["streams"]]
    assert onsets == [0, 0, 20, 20]
    durations = {s["duration"] for s in doc["streams"]}
    assert durations == {20}
    assert doc["duration"] == 40            # copre l'ultima versione


def test_document_injected_values_reach_envelopes():
    doc = _doc({"d": {"values": [1, 2]}})
    by_id = {s["stream_id"]: s for s in doc["streams"]}

    def ys(sid):
        return [v for _, v in by_id[sid]["density"]["points"]]

    # fermo campiona env (40 -> 60); mobile = env + d, identico a meno
    # dell'offset (stessi seed -> stessa sequenza in ogni versione).
    base = ys("fermo__d=1")
    assert ys("fermo__d=2") == base
    assert ys("mobile__d=1") == [pytest.approx(v + 1) for v in base]
    assert ys("mobile__d=2") == [pytest.approx(v + 2) for v in base]


def test_document_two_vars_stream_labels():
    data = _study({"f": {"values": [50, 100]}, "d": {"values": [1]}})
    data["axes"]["density"]["base"]["expr"] = "env * f / 50 + d"
    data["axes"]["density"]["base"]["let"]["f"] = 50
    doc = generate_versions_document(data, "vtest", output_sr=None)
    ids = [s["stream_id"] for s in doc["streams"]]
    assert ids[0] == "fermo__f=50__d=1"
    assert ids[-1] == "mobile__f=100__d=1"


def test_stream_own_onset_preserved_inside_version():
    data = _study({"d": {"values": [1, 2]}})
    data["streams"]["mobile"] = {"base": {"onset": 2}}
    doc = generate_versions_document(data, "vtest", output_sr=None)
    by_id = {s["stream_id"]: s for s in doc["streams"]}
    assert by_id["mobile__d=1"]["onset"] == 2
    assert by_id["mobile__d=2"]["onset"] == 22


# --- chiavi riservate onset/duration del blocco versions (issue #26) -----------

def test_reserved_keys_are_not_variables():
    data = _study({
        "d": {"values": [1, 2]},
        "onset": {"values": [0, 30]},
        "duration": {"values": [10, 10]},
    })
    # niente errore "non referenziata": onset/duration non sono variabili di
    # scope, e non compaiono tra i valori risolti.
    assert parse_versions(data) == {"d": [1, 2]}


def test_only_reserved_keys_errors():
    data = _study({"onset": {"values": [0, 30]}})
    with pytest.raises(SpecError, match="variabil"):
        parse_versions(data)


def test_onset_values_wrong_length_errors():
    data = _study({"d": {"values": [1, 2, 3]}, "onset": {"values": [0, 10]}})
    with pytest.raises(SpecError, match="onset"):
        generate_versions_document(data, "vtest", output_sr=None)


def test_onset_band_with_explicit_n_mismatch_errors():
    data = _study({
        "d": {"values": [1, 2, 3]},
        "onset": {"base": 0, "range": 10, "n": 2},
    })
    with pytest.raises(SpecError, match="n"):
        generate_versions_document(data, "vtest", output_sr=None)


def test_onset_negative_errors():
    data = _study({"d": {"values": [1, 2]}, "onset": {"values": [-1, 5]}})
    with pytest.raises(SpecError, match="onset"):
        generate_versions_document(data, "vtest", output_sr=None)


def test_reserved_duration_non_positive_errors():
    data = _study({"d": {"values": [1, 2]}, "duration": {"values": [0, 10]}})
    with pytest.raises(SpecError, match="duration"):
        generate_versions_document(data, "vtest", output_sr=None)


def test_onset_key_positions_versions_absolutely():
    data = _study({"d": {"values": [1, 2]}, "onset": {"values": [3, 7]}})
    doc = generate_versions_document(data, "vtest", output_sr=None)
    onsets = [s["onset"] for s in doc["streams"]]
    assert onsets == [3, 3, 7, 7]             # sovrapposte: legittimo
    assert doc["duration"] == 27              # max(onset + duration) = 7 + 20


def test_onset_ramp_without_step_spreads_over_versions():
    data = _study({"d": {"values": [1, 2, 3]}, "onset": {"ramp": {"start": 0, "stop": 100}}})
    doc = generate_versions_document(data, "vtest", output_sr=None)
    onsets = sorted({s["onset"] for s in doc["streams"]})
    assert onsets == [0, 50, 100]             # linspace: n = numero versioni


def test_onset_ramp_with_step_wrong_count_errors():
    data = _study({"d": {"values": [1, 2, 3]}, "onset": {"ramp": {"start": 0, "stop": 10, "step": 10}}})
    with pytest.raises(SpecError, match="onset"):
        generate_versions_document(data, "vtest", output_sr=None)


def test_onset_band_deterministic_with_derived_seed():
    data = _study({"d": {"values": [1, 2, 3]}, "onset": {"base": 0, "range": 50}})
    a = generate_versions_document(data, "vtest", output_sr=None)
    b = generate_versions_document(data, "vtest", output_sr=None)
    assert [s["onset"] for s in a["streams"]] == [s["onset"] for s in b["streams"]]
    assert all(0 <= s["onset"] <= 50 for s in a["streams"])


def test_stream_onset_relative_to_version_onset():
    data = _study({"d": {"values": [1, 2]}, "onset": {"values": [3, 7]}})
    data["streams"]["mobile"] = {"onset": 2}  # onset per-stream (issue #26)
    doc = generate_versions_document(data, "vtest", output_sr=None)
    by_id = {s["stream_id"]: s for s in doc["streams"]}
    assert by_id["mobile__d=1"]["onset"] == 5     # 3 + 2
    assert by_id["mobile__d=2"]["onset"] == 9     # 7 + 2


def test_duration_key_is_version_default_stream_wins():
    data = _study({"d": {"values": [1, 2]}, "duration": {"values": [5, 8]}})
    data["streams"]["fermo"] = {
        "duration": 4,                        # la duration propria vince
        "axes": {"density": {"base": {"expr": "env"}}},
    }
    doc = generate_versions_document(data, "vtest", output_sr=None)
    by_id = {s["stream_id"]: s for s in doc["streams"]}
    assert by_id["fermo__d=1"]["duration"] == 4
    assert by_id["fermo__d=2"]["duration"] == 4
    assert by_id["mobile__d=1"]["duration"] == 5   # default di versione
    assert by_id["mobile__d=2"]["duration"] == 8


def test_duration_key_without_onset_concatenates_on_generated_durations():
    data = _study({"d": {"values": [1, 2, 3]}, "duration": {"values": [5, 8, 2]}})
    doc = generate_versions_document(data, "vtest", output_sr=None)
    onsets = sorted({s["onset"] for s in doc["streams"]})
    assert onsets == [0, 5, 13]               # cumsum delle durate generate
    assert doc["duration"] == 15              # 13 + 2


def test_reserved_duration_generator_concatenates():
    data = _study({"d": {"values": [1, 2]}, "duration": {"values": [5, 8]}})
    doc = generate_versions_document(data, "vtest", output_sr=None)
    onsets = [s["onset"] for s in doc["streams"]]
    assert onsets == [0, 0, 5, 5]
    assert doc["duration"] == 13


def test_onset_key_with_per_stream_durations():
    data = _study({"d": {"values": [1, 2]}, "onset": {"values": [0, 30]}})
    data["streams"]["fermo"] = {
        "duration": 10,
        "axes": {"density": {"base": {"expr": "env"}}},
    }
    data["streams"]["mobile"] = {"duration": 6}
    doc = generate_versions_document(data, "vtest", output_sr=None)
    assert doc["duration"] == 40              # 30 + 10


# --- split per variabile esterna -----------------------------------------------

def _study_dg(versions):
    """Fixture a due variabili: ``g`` deve essere referenziata da un'expr,
    altrimenti scatta la guardia anti-refuso di ``parse_versions``."""
    data = _study(versions)
    data["axes"]["density"]["range"] = {"expr": "g", "let": {"g": 0}}
    return data


def test_split_one_document_per_outer_value():
    """La prima variabile e' il confine di file: N_d documenti, ognuno con le
    sole combo di quel d, ribasato a zero."""
    data = _study_dg({"d": {"values": [1, 2]}, "g": {"values": [4, 5, 6]}})
    docs = generate_versions_documents(data, "vtest", output_sr=None)
    assert [label for label, _ in docs] == ["d=1", "d=2"]
    for label, doc in docs:
        ids = [s["stream_id"] for s in doc["streams"]]
        assert len(ids) == 6                  # 3 valori di g x 2 stream
        assert all(label in i for i in ids)
        assert min(s["onset"] for s in doc["streams"]) == 0
        assert doc["duration"] == 60          # 3 versioni x 20 s


def test_split_preserves_relative_layout_with_explicit_onset():
    """Con onset espliciti la ribasatura toglie solo l'offset del gruppo: i
    buchi e le distanze interne restano quelli scritti."""
    data = _study_dg({
        "d": {"values": [1, 2]},
        "g": {"values": [4, 5]},
        "onset": {"values": [0, 25, 100, 140]},
    })
    docs = generate_versions_documents(data, "vtest", output_sr=None)
    assert [sorted({s["onset"] for s in doc["streams"]}) for _, doc in docs] == [
        [0, 25], [0, 40],
    ]


# --- spread.n mosso da una variabile di versions (issue #39) ----------------------
# Le due cose si incontravano gia' da sole (``spread.n`` accetta un nodo-expr,
# ``versions`` inietta nell'intero documento prima di ``resolve_streams``), ma
# il padding dei nomi era calcolato per versione: a cavallo di una decade la
# stessa voce logica cambiava nome, e una patch per nome si applicava solo dove
# le cifre coincidevano.

def _coro_study(versions, patches=None, n=None):
    """Studio con una entry-spread il cui ``n`` e' guidato da ``k``.

    ``k`` e' nominata solo dentro ``spread.n``: la guardia anti-refuso di
    ``parse_version_axes`` conta anche quel nodo-expr.
    """
    data = _study(versions)
    data["streams"] = {
        "cugini": {
            "spread": {
                "n": n if n is not None else {"expr": "k", "let": {"k": 3}},
                "over": {"base.volume": {"expr": "0 - i"}},
            },
        },
    }
    data["streams"].update(patches or {})
    return data


def _coro_ids(data):
    doc = generate_versions_document(data, "vtest", output_sr=None)
    return [s["stream_id"] for s in doc["streams"]]


def test_spread_n_varies_per_version():
    ids = _coro_ids(_coro_study({"k": {"values": [2, 4]}}))
    assert ids == [
        "cugini_1__k=2", "cugini_2__k=2",
        "cugini_1__k=4", "cugini_2__k=4", "cugini_3__k=4", "cugini_4__k=4",
    ]


def test_variable_referenced_only_in_spread_n_passes_guard():
    # nessun'altra espressione nomina k: la guardia deve comunque vederla
    assert parse_version_axes(_coro_study({"k": {"values": [2, 4]}}))["k"]


def test_name_width_stable_across_a_decade():
    # k=9 -> 9 voci, k=11 -> 11: senza pad condiviso sarebbero cugini_1 e
    # cugini_01, cioe' due nomi per la stessa voce logica
    ids = _coro_ids(_coro_study({"k": {"values": [9, 11]}}))
    assert ids[:2] == ["cugini_01__k=9", "cugini_02__k=9"]
    assert len([i for i in ids if i.endswith("__k=9")]) == 9
    assert ids[-1] == "cugini_11__k=11"
    assert {len(i.split("__")[0]) for i in ids} == {len("cugini_01")}


def test_patch_applies_in_every_version_where_the_voice_exists():
    data = _coro_study(
        {"k": {"values": [9, 11]}},
        patches={"cugini_03": {"base": {"volume": -90}}},
    )
    doc = generate_versions_document(data, "vtest", output_sr=None)
    by_id = {s["stream_id"]: s for s in doc["streams"]}
    assert by_id["cugini_03__k=9"]["volume"] == -90
    assert by_id["cugini_03__k=11"]["volume"] == -90
    # e resta una patch, non uno stream in piu': 9 + 11 voci in tutto
    assert len(doc["streams"]) == 20


def test_patch_of_a_voice_absent_from_a_version_is_consumed_silently():
    # cugini_11 esiste solo nella versione k=11: nella k=2 e' una voce-fantasma
    data = _coro_study(
        {"k": {"values": [2, 11]}},
        patches={"cugini_11": {"base": {"volume": -90}}},
    )
    doc = generate_versions_document(data, "vtest", output_sr=None)
    by_id = {s["stream_id"]: s for s in doc["streams"]}
    assert "cugini_11__k=2" not in by_id
    assert by_id["cugini_11__k=11"]["volume"] == -90
    assert len([i for i in by_id if i.endswith("__k=2")]) == 2


def test_constant_n_keeps_historic_narrow_names():
    # senza variabilita' il pad non allarga niente: retro-compatibile
    data = _coro_study({"k": {"values": [1, 2]}}, n=3)
    # con n costante k non e' piu' nominata dallo spread: le serve un altro
    # riferimento, o scatta la guardia anti-refuso
    data["axes"]["density"]["range"] = {"expr": "k", "let": {"k": 0}}
    ids = _coro_ids(data)
    assert ids[:3] == ["cugini_1__k=1", "cugini_2__k=1", "cugini_3__k=1"]


def test_pad_is_shared_across_split_documents():
    # il massimo e' sul prodotto intero, non per gruppo: i file di
    # generate_versions_documents restano confrontabili fra loro
    data = _coro_study({"k": {"values": [2, 11]}})
    docs = generate_versions_documents(data, "vtest", output_sr=None)
    assert [label for label, _ in docs] == ["k=2", "k=11"]
    first = [s["stream_id"] for s in docs[0][1]["streams"]]
    assert first == ["cugini_01__k=2", "cugini_02__k=2"]


# --- versions.duration: scalare e default di versione (issue #42) ---------------

def test_reserved_duration_accepts_scalar_broadcast_on_n():
    # Il caso di gran lunga piu' comune — tutte le versioni lunghe uguale —
    # era l'unico che non si poteva scrivere: pretendeva un generatore.
    data = _study({"d": {"values": [1, 2, 3]}, "duration": 5})
    doc = generate_versions_document(data, "vtest", output_sr=None)
    onsets = sorted({s["onset"] for s in doc["streams"]})
    assert onsets == [0, 5, 10]               # passo 5, broadcastato su N
    assert {s["duration"] for s in doc["streams"]} == {5}
    assert doc["duration"] == 15


def test_reserved_duration_scalar_non_positive_errors():
    data = _study({"d": {"values": [1, 2]}, "duration": 0})
    with pytest.raises(SpecError, match="deve essere > 0"):
        generate_versions_document(data, "vtest", output_sr=None)


def test_reserved_duration_scalar_non_numeric_errors():
    data = _study({"d": {"values": [1, 2]}, "duration": "cinque"})
    with pytest.raises(SpecError, match="scalare"):
        generate_versions_document(data, "vtest", output_sr=None)


def test_reserved_onset_accepts_scalar_broadcast_on_n():
    # Simmetria: onset e duration sono la stessa chiave riservata, con la
    # stessa forma. Uno scalare su onset e' un valore assoluto ripetuto —
    # tutte le versioni sovrapposte, legittimo (il merge fa overlay-add).
    data = _study({"d": {"values": [1, 2]}, "onset": 3})
    doc = generate_versions_document(data, "vtest", output_sr=None)
    assert {s["onset"] for s in doc["streams"]} == {3}


def test_scalar_duration_is_version_default_and_stream_wins():
    # D2: versions.duration resta doppia — passo E default degli stream della
    # versione. Il default passa ora per base.duration, quindi una duration
    # di entry lo scavalca come qualsiasi altro default di documento.
    data = _study({"d": {"values": [1, 2]}, "duration": 5})
    data["streams"]["fermo"] = {
        "duration": 4,
        "axes": {"density": {"base": {"expr": "env"}}},
    }
    doc = generate_versions_document(data, "vtest", output_sr=None)
    by_id = {s["stream_id"]: s for s in doc["streams"]}
    assert by_id["fermo__d=1"]["duration"] == 4    # la propria vince
    assert by_id["mobile__d=1"]["duration"] == 5   # eredita la versione
    assert by_id["mobile__d=2"]["onset"] == 5      # il passo resta il suo


def test_version_duration_survives_a_document_with_base_duration():
    # base.duration del documento e' il default degli stream; la duration di
    # versione e' piu' specifica e la ombreggia (stesso posto, valore nuovo).
    data = _study({"d": {"values": [1, 2]}, "duration": 5})
    data["base"]["duration"] = 30
    doc = generate_versions_document(data, "vtest", output_sr=None)
    assert {s["duration"] for s in doc["streams"]} == {5}


# --- divieto del duration: top-level anche nel ramo versions (issue #42, D3) ----

def test_top_level_duration_rejected_with_versions_duration():
    # Il ramo versions non passa mai il documento originale a resolve_streams:
    # ci arrivano i documenti per-combo, dove base.duration e' gia' iniettata.
    # Senza il divieto all'ingresso, un top-level residuo passava in silenzio.
    data = _study({"d": {"values": [1, 2]}, "duration": 5})
    data["duration"] = 999
    with pytest.raises(SpecError, match=r"base\.duration"):
        generate_versions_document(data, "vtest", output_sr=None)


def test_top_level_duration_rejected_without_versions_duration():
    # Stesso YAML sbagliato, stesso esito: prima l'errore dipendeva dalla
    # presenza di 'versions.duration' (con, silenzio; senza, errore).
    data = _study({"d": {"values": [1, 2]}, "onset": {"values": [0, 30]}})
    data["duration"] = 999
    with pytest.raises(SpecError, match=r"base\.duration"):
        generate_versions_document(data, "vtest", output_sr=None)


def test_top_level_duration_rejected_in_versions_documents_too():
    data = _study({"d": {"values": [1, 2]}, "duration": 5})
    data["duration"] = 999
    with pytest.raises(SpecError, match="top-level"):
        generate_versions_documents(data, "vtest", output_sr=None)


def test_empty_base_block_takes_the_version_duration():
    # 'base:' dichiarato vuoto e' None, non {}: l'iniezione della duration di
    # versione non deve inciamparci (TypeError invece di un documento).
    data = _study({"d": {"values": [1, 2]}, "duration": 5})
    data["base"] = None
    data["streams"]["fermo"]["base"] = {"sample": "corpus.wav"}
    data["streams"]["mobile"]["base"] = {"sample": "corpus.wav"}
    doc = generate_versions_document(data, "vtest", output_sr=None)
    assert {s["duration"] for s in doc["streams"]} == {5}
