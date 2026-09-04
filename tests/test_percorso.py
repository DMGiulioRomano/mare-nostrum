"""Test del processo ``percorso``: istanze di spread distribuite sul tempo reale.

Il blocco top-level ``percorso:`` (issue #29) orchestra lo stack lungo una
timeline — strategy enumerata (``onset:``) o camminata (``arco:`` + ``passo:``)
— e dichiara traiettorie in grammatica-Env, campionate all'onset reale di ogni
istanza e iniettate negli scope ``let`` come fa ``versions``. Nessun prodotto
cartesiano: i valori cambiano insieme, appaiati sul tempo.
"""
import pytest

from granstudies.errors import SpecError
from granstudies.percorso import (
    build_timeline,
    generate_percorso_document,
    parse_percorso,
    resolve_durations,
)


# --- documento base condiviso dai test ---------------------------------------

def _study(percorso, **over):
    data = {
        "study_id": "ptest",
        "seed": 7,
        "base": {"onset": 0, "sample": "corpus.wav"},
        "axes": {
            "density": {
                "path": "density",
                "baseline": 50,
                "n": 4,
                "base": {
                    "expr": "env + w * 10",
                    "let": {"env": [[0, 40], [1, 60]], "w": 0},
                },
                "range": 0,
            },
        },
        "stack": {},
        "streams": {"fermo": {}},
        "percorso": percorso,
    }
    data.update(over)
    return data


# --- strategy: mutua esclusione ----------------------------------------------

def test_onset_with_arco_errors():
    data = _study({"onset": {"values": [0, 10]}, "arco": 60, "w": 1})
    with pytest.raises(SpecError, match="strategy"):
        parse_percorso(data)


def test_onset_with_passo_errors():
    data = _study({"onset": {"values": [0, 10]}, "passo": 5, "w": 1})
    with pytest.raises(SpecError, match="strategy"):
        parse_percorso(data)


def test_k_alone_errors_explaining_strategies():
    data = _study({"k": 8, "w": 1})
    with pytest.raises(SpecError) as exc:
        parse_percorso(data)
    # il messaggio spiega le due strategy
    assert "onset" in str(exc.value)
    assert "arco" in str(exc.value)


def test_empty_block_errors():
    with pytest.raises(SpecError, match="percorso"):
        parse_percorso(_study({}))


def test_block_not_dict_errors():
    with pytest.raises(SpecError, match="percorso"):
        parse_percorso(_study([1, 2]))


def test_requires_stack():
    data = _study({"arco": 60, "passo": 10, "w": 1})
    del data["stack"]
    with pytest.raises(SpecError, match="stack"):
        parse_percorso(data)


def test_coexists_with_versions():
    data = _study({"arco": 60, "passo": 10, "w": 1})
    data["versions"] = {"d": {"values": [1, 2]}}
    spec = parse_percorso(data)
    assert spec.strategy == "camminata"


# --- strategy enumerata: k posseduto da onset ---------------------------------

def test_enumerata_values_own_k():
    data = _study({"onset": {"values": [0, 10, 25]}, "w": 1})
    spec = parse_percorso(data)
    assert spec.strategy == "enumerata"
    assert spec.k == 3


def test_enumerata_k_crosscheck_ok():
    data = _study({"onset": {"values": [0, 10, 25]}, "k": 3, "w": 1})
    assert parse_percorso(data).k == 3


def test_enumerata_k_crosscheck_discordant_errors():
    data = _study({"onset": {"values": [0, 10, 25]}, "k": 4, "w": 1})
    with pytest.raises(SpecError, match="discord"):
        parse_percorso(data)


def test_enumerata_ramp_with_step_owns_k():
    data = _study({"onset": {"ramp": {"start": 0, "stop": 60, "step": 20}}, "w": 1})
    assert parse_percorso(data).k == 4    # 0, 20, 40, 60


def test_enumerata_ramp_without_step_requires_k():
    data = _study({"onset": {"ramp": {"start": 0, "stop": 60}}, "w": 1})
    with pytest.raises(SpecError, match="k"):
        parse_percorso(data)


def test_enumerata_ramp_without_step_with_k_ok():
    data = _study({"onset": {"ramp": {"start": 0, "stop": 60}}, "k": 4, "w": 1})
    assert parse_percorso(data).k == 4


def test_enumerata_band_with_n_owns_k():
    data = _study({"onset": {"base": 0, "range": 60, "n": 5}, "w": 1})
    assert parse_percorso(data).k == 5


def test_enumerata_band_without_n_requires_k():
    data = _study({"onset": {"base": 0, "range": 60}, "w": 1})
    with pytest.raises(SpecError, match="k"):
        parse_percorso(data)


def test_enumerata_k_not_int_errors():
    data = _study({"onset": {"ramp": {"start": 0, "stop": 60}}, "k": 2.5, "w": 1})
    with pytest.raises(SpecError, match="inter"):
        parse_percorso(data)


# --- strategy camminata: arco + passo ------------------------------------------

def test_camminata_parses():
    data = _study({"arco": 180, "passo": {"base": [30, 8]}, "w": 1})
    spec = parse_percorso(data)
    assert spec.strategy == "camminata"
    assert spec.arco == 180
    assert spec.passo.kind == "band"
    assert spec.k is None   # emerge dalla camminata, non si dichiara


def test_camminata_passo_scalar_is_constant():
    data = _study({"arco": 60, "passo": 10, "w": 1})
    spec = parse_percorso(data)
    assert spec.passo.kind == "const"


def test_camminata_arco_without_passo_errors():
    data = _study({"arco": 60, "w": 1})
    with pytest.raises(SpecError, match="passo"):
        parse_percorso(data)


def test_camminata_passo_without_arco_errors():
    data = _study({"passo": 10, "w": 1})
    with pytest.raises(SpecError, match="arco"):
        parse_percorso(data)


def test_camminata_k_declared_errors():
    data = _study({"arco": 60, "passo": 10, "k": 6, "w": 1})
    with pytest.raises(SpecError, match="k"):
        parse_percorso(data)


def test_camminata_arco_not_scalar_errors():
    data = _study({"arco": {"base": [60, 120]}, "passo": 10, "w": 1})
    with pytest.raises(SpecError, match="arco"):
        parse_percorso(data)


def test_camminata_arco_not_positive_errors():
    data = _study({"arco": 0, "passo": 10, "w": 1})
    with pytest.raises(SpecError, match="arco"):
        parse_percorso(data)


# --- grammatica delle traiettorie ----------------------------------------------

def test_trajectory_scalar_is_constant():
    data = _study({"arco": 60, "passo": 10, "w": 0.5})
    assert parse_percorso(data).variables["w"].kind == "const"


def test_trajectory_band_grammar():
    data = _study({
        "arco": 60, "passo": 10,
        "w": {"base": [0, 1], "range": 0.1,
              "drift": {"step": 0.2}, "distribution": "gaussian", "seed": 3},
    })
    assert parse_percorso(data).variables["w"].kind == "band"


def test_trajectory_expr_node():
    data = _study({
        "arco": 60, "passo": 10,
        "w": {"expr": "env * 2", "let": {"env": [0, 0.5]}},
    })
    assert parse_percorso(data).variables["w"].kind == "expr"


def test_trajectory_values_rejected_with_hint():
    data = _study({"arco": 60, "passo": 10, "w": {"values": [0, 1]}})
    with pytest.raises(SpecError, match="indicizzat"):
        parse_percorso(data)


def test_trajectory_ramp_rejected_with_hint():
    data = _study({"arco": 60, "passo": 10, "w": {"ramp": {"start": 0, "stop": 1}}})
    with pytest.raises(SpecError, match="indicizzat"):
        parse_percorso(data)


def test_trajectory_band_with_n_rejected():
    # le traiettorie non possiedono mai il conteggio
    data = _study({"arco": 60, "passo": 10, "w": {"base": [0, 1], "n": 5}})
    with pytest.raises(SpecError, match="conteggio"):
        parse_percorso(data)


def test_trajectory_band_extra_keys_rejected():
    data = _study({"arco": 60, "passo": 10, "w": {"base": [0, 1], "foo": 3}})
    with pytest.raises(SpecError, match="foo"):
        parse_percorso(data)


def test_trajectory_unrecognized_form_errors():
    data = _study({"arco": 60, "passo": 10, "w": [0, 1]})
    with pytest.raises(SpecError, match="traiettoria"):
        parse_percorso(data)


def test_trajectory_expr_mixed_with_band_errors():
    data = _study({
        "arco": 60, "passo": 10,
        "w": {"expr": "env", "let": {"env": [0, 1]}, "base": 0},
    })
    with pytest.raises(SpecError, match="strategy|expr|base"):
        parse_percorso(data)


# --- nomi riservati e guardia anti-refuso ---------------------------------------

@pytest.mark.parametrize("name", ["i", "n", "pi", "e"])
def test_reserved_scope_names_rejected(name):
    data = _study({"arco": 60, "passo": 10, name: 0.5, "w": 1})
    with pytest.raises(SpecError, match="riservat"):
        parse_percorso(data)


def test_unreferenced_variable_errors():
    data = _study({"arco": 60, "passo": 10, "w": 1, "zz": 3})
    with pytest.raises(SpecError, match="referenziata"):
        parse_percorso(data)


def test_variable_referenced_in_spread_patch_counts():
    data = _study({"arco": 60, "passo": 10, "w": 1, "g": 2})
    data["streams"] = {
        "coro": {"spread": {"n": 3, "over": {
            "base.volume": {"expr": "g * (i + 1)", "let": {"g": 1}},
        }}},
        "fermo": {},
    }
    spec = parse_percorso(data)
    assert set(spec.variables) == {"w", "g"}


# --- duration: traiettoria con unit --------------------------------------------

def test_duration_scalar_default_unit_factor():
    data = _study({"arco": 60, "passo": 10, "duration": 1.3, "w": 1})
    spec = parse_percorso(data)
    assert spec.duration.kind == "const"
    assert spec.duration_unit == "factor"


def test_duration_band_with_unit_s():
    data = _study({"arco": 60, "passo": 10,
                   "duration": {"base": [30, 8], "unit": "s"}, "w": 1})
    spec = parse_percorso(data)
    assert spec.duration.kind == "band"
    assert spec.duration_unit == "s"


def test_duration_expr_with_unit():
    data = _study({"arco": 60, "passo": 10,
                   "duration": {"expr": "1 + 1", "unit": "s"}, "w": 1})
    spec = parse_percorso(data)
    assert spec.duration.kind == "expr"
    assert spec.duration_unit == "s"


def test_duration_unknown_unit_errors():
    data = _study({"arco": 60, "passo": 10,
                   "duration": {"base": 1, "unit": "ms"}, "w": 1})
    with pytest.raises(SpecError, match="unit"):
        parse_percorso(data)


def test_duration_absent_is_legato():
    data = _study({"arco": 60, "passo": 10, "w": 1})
    spec = parse_percorso(data)
    assert spec.duration is None
    assert spec.duration_unit == "factor"


def test_percorso_without_variables_is_valid():
    # la timeline possiede tutto: la pura ripetizione dello stack e' legittima
    data = _study({"arco": 60, "passo": 10})
    spec = parse_percorso(data)
    assert spec.variables == {}


# --- timeline: strategy enumerata ----------------------------------------------

def _timeline(percorso, **over):
    data = _study(percorso, **over)
    spec = parse_percorso(data)
    return build_timeline(spec, data.get("study_id") or "study")


def test_enumerata_values_absolute_onsets():
    tl = _timeline({"onset": {"values": [0, 10, 25]}, "w": 1})
    assert tl.onsets == [0.0, 10.0, 25.0]
    assert tl.span == 25.0


def test_enumerata_ramp_step_grid():
    tl = _timeline({"onset": {"ramp": {"start": 0, "stop": 60, "step": 20}}, "w": 1})
    assert tl.onsets == [0.0, 20.0, 40.0, 60.0]


def test_enumerata_ramp_start_stop_equispaced_on_k():
    tl = _timeline({"onset": {"ramp": {"start": 0, "stop": 60}}, "k": 4, "w": 1})
    assert tl.onsets == [0.0, 20.0, 40.0, 60.0]


def test_enumerata_band_deterministic():
    p = {"onset": {"base": 0, "range": 60, "n": 4}, "w": 1}
    a, b = _timeline(p), _timeline(p)
    assert a.onsets == b.onsets
    assert len(a.onsets) == 4
    assert all(0 <= t <= 60 for t in a.onsets)


def test_enumerata_negative_onset_errors():
    with pytest.raises(SpecError, match="onset"):
        _timeline({"onset": {"values": [0, -5]}, "w": 1})


def test_enumerata_intervals_last_repeats():
    tl = _timeline({"onset": {"values": [0, 10, 25]}, "w": 1})
    # intervallo verso la prossima; l'ultima istanza usa l'ultimo intervallo noto
    assert tl.intervals == [10.0, 15.0, 15.0]


# --- timeline: strategy camminata ------------------------------------------------

def test_camminata_constant_passo_equispaced():
    tl = _timeline({"arco": 60, "passo": 10, "w": 1})
    assert tl.onsets == [0.0, 10.0, 20.0, 30.0, 40.0, 50.0]
    assert tl.intervals == [10.0] * 6
    assert tl.span == 60.0


def test_camminata_accumulates_passo_at_current_onset():
    # passo in rampa (banda collassata): accelerando deterministico
    tl = _timeline({"arco": 60, "passo": {"base": [10, 20]}, "w": 1})
    assert tl.onsets[0] == 0.0
    assert all(t < 60 for t in tl.onsets)
    for i, dt in enumerate(tl.intervals[:-1]):
        assert tl.onsets[i + 1] == pytest.approx(tl.onsets[i] + dt)
    # il passo cresce lungo l'arco: intervalli strettamente crescenti
    assert all(a < b for a, b in zip(tl.intervals, tl.intervals[1:]))


def test_camminata_passo_expr_constant():
    tl = _timeline({"arco": 30, "passo": {"expr": "5 + 5"}, "w": 1})
    assert tl.onsets == [0.0, 10.0, 20.0]


def test_camminata_passo_not_positive_errors():
    with pytest.raises(SpecError, match="passo"):
        _timeline({"arco": 60, "passo": 0, "w": 1})


def test_camminata_single_instance():
    tl = _timeline({"arco": 10, "passo": 25, "w": 1})
    assert tl.onsets == [0.0]
    assert tl.intervals == [25.0]


# --- duration: traiettoria, factor | s, legato di default -------------------------

def _durations(percorso, **over):
    data = _study(percorso, **over)
    spec = parse_percorso(data)
    sid = data.get("study_id") or "study"
    tl = build_timeline(spec, sid)
    return resolve_durations(spec, tl, sid)


def test_legato_default_enumerata():
    d = _durations({"onset": {"values": [0, 10, 25]}, "w": 1})
    assert d == [10.0, 15.0, 15.0]


def test_legato_default_camminata_last_uses_passo():
    # l'ultima istanza puo' sforare l'arco con la propria durata
    d = _durations({"arco": 60, "passo": 25, "w": 1})
    assert d == [25.0, 25.0, 25.0]   # onsets 0, 25, 50; 50 + 25 > 60


def test_factor_scales_interval():
    d = _durations({"onset": {"values": [0, 10, 25]}, "duration": 1.5, "w": 1})
    assert d == [15.0, 22.5, 22.5]


def test_factor_below_one_leaves_gaps():
    d = _durations({"arco": 40, "passo": 20, "duration": 0.5, "w": 1})
    assert d == [10.0, 10.0]


def test_unit_s_absolute():
    d = _durations({"arco": 40, "passo": 20,
                    "duration": {"base": 12, "unit": "s"}, "w": 1})
    assert d == [12.0, 12.0]


def test_duration_sampled_at_real_onset_camminata_norm_on_arco():
    # normalizzazione 0->1 sull'arco: onsets 0 e 30 su arco 60 -> frac 0 e 0.5
    d = _durations({"arco": 60, "passo": 30,
                    "duration": {"base": [[0, 10], [1, 20]], "unit": "s"}, "w": 1})
    assert d == [10.0, 15.0]


def test_duration_sampled_at_real_onset_enumerata_norm_on_last_onset():
    # normalizzazione sull'ultimo onset: 0, 10, 20 -> frac 0, 0.5, 1
    d = _durations({"onset": {"values": [0, 10, 20]},
                    "duration": {"base": [[0, 10], [1, 20]], "unit": "s"}, "w": 1})
    assert d == [10.0, 15.0, 20.0]


def test_enumerata_single_instance_factor_errors():
    with pytest.raises(SpecError, match="unit"):
        _durations({"onset": {"values": [0]}, "duration": 1.3, "w": 1})


def test_enumerata_single_instance_legato_errors():
    # il legato e' factor 1: senza intervallo di riferimento serve unit: s
    with pytest.raises(SpecError, match="unit"):
        _durations({"onset": {"values": [0]}, "w": 1})


def test_enumerata_single_instance_unit_s_ok():
    d = _durations({"onset": {"values": [0]},
                    "duration": {"base": 12, "unit": "s"}, "w": 1})
    assert d == [12.0]


def test_camminata_single_instance_legato_ok():
    # in camminata l'intervallo di riferimento esiste sempre: passo(t_K)
    d = _durations({"arco": 10, "passo": 25, "w": 1})
    assert d == [25.0]


def test_duration_not_positive_errors():
    with pytest.raises(SpecError, match="duration"):
        _durations({"arco": 40, "passo": 20,
                    "duration": {"base": 0, "unit": "s"}, "w": 1})


def test_legato_non_monotone_onsets_errors():
    with pytest.raises(SpecError, match="duration"):
        _durations({"onset": {"values": [0, 20, 10]}, "w": 1})


# --- documento generato (integrazione, stile test_versions) ----------------------

def _pdoc(percorso, **over):
    data = _study(percorso, **over)
    return generate_percorso_document(data, "ptest", output_sr=None)


def _by_id(doc):
    return {s["stream_id"]: s for s in doc["streams"]}


def _ys(doc, sid):
    return [v for _, v in _by_id(doc)[sid]["density"]["points"]]


def test_document_instances_and_naming():
    doc = _pdoc({"onset": {"values": [0, 10, 25]}, "w": 1})
    ids = [s["stream_id"] for s in doc["streams"]]
    assert ids == ["fermo__k=1", "fermo__k=2", "fermo__k=3"]


def test_document_k_padded_on_final_width():
    doc = _pdoc({"arco": 100, "passo": 10, "w": 1})
    ids = [s["stream_id"] for s in doc["streams"]]
    assert len(ids) == 10
    assert ids[0] == "fermo__k=01"
    assert ids[-1] == "fermo__k=10"


def test_document_onset_is_instance_plus_stream():
    data = _study({"onset": {"values": [0, 10]}, "w": 1})
    data["streams"]["mobile"] = {"base": {"onset": 2}}
    doc = generate_percorso_document(data, "ptest", output_sr=None)
    by_id = _by_id(doc)
    assert by_id["fermo__k=1"]["onset"] == 0
    assert by_id["mobile__k=1"]["onset"] == 2
    assert by_id["fermo__k=2"]["onset"] == 10
    assert by_id["mobile__k=2"]["onset"] == 12


def test_document_duration_instance_default_stream_wins():
    data = _study({"onset": {"values": [0, 10]},
                   "duration": {"base": 8, "unit": "s"}, "w": 1})
    data["streams"]["mobile"] = {"duration": 5}
    doc = generate_percorso_document(data, "ptest", output_sr=None)
    by_id = _by_id(doc)
    assert by_id["fermo__k=1"]["duration"] == 8
    assert by_id["mobile__k=1"]["duration"] == 5
    # durata documento = max(onset + duration)
    assert doc["duration"] == 18


def test_document_injected_values_reach_envelopes():
    # w sale 0 -> 1 sul percorso: l'istanza 2 (frac 1) suona env + 10
    doc = _pdoc({"onset": {"values": [0, 10]},
                 "w": {"base": [[0, 0], [1, 1]]}})
    base = _ys(doc, "fermo__k=1")
    assert _ys(doc, "fermo__k=2") == [pytest.approx(v + 10) for v in base]


def test_document_seed_unchanged_across_instances():
    # il gesto che ritorna: con variabili costanti ogni istanza ripete la
    # stessa camminata/pescaggio (seed invariato se non toccato)
    data = _study({"onset": {"values": [0, 10, 20]}, "w": 1})
    data["axes"]["density"]["range"] = 5
    doc = generate_percorso_document(data, "ptest", output_sr=None)
    a = _ys(doc, "fermo__k=1")
    assert _ys(doc, "fermo__k=2") == a
    assert _ys(doc, "fermo__k=3") == a


def _coro_study(percorso, patches=None):
    data = _study(percorso)
    data["streams"] = {
        "coro": {"spread": {
            "n": {"expr": "floor(2 + 8 * w)", "let": {"w": 0}},
            "over": {"base.volume": {"expr": "0 - i"}},
        }},
    }
    data["streams"].update(patches or {})
    return data


def test_document_spread_n_expr_per_instance_with_stable_padding():
    # w: 0 -> 0.5 -> 1 => n: 2, 6, 10; padding sulla larghezza del massimo n
    data = _coro_study({"onset": {"values": [0, 10, 20]},
                        "w": {"base": [[0, 0], [1, 1]]}})
    doc = generate_percorso_document(data, "ptest", output_sr=None)
    ids = [s["stream_id"] for s in doc["streams"]]
    k1 = [i for i in ids if i.endswith("__k=1")]
    k3 = [i for i in ids if i.endswith("__k=3")]
    assert k1 == ["coro_01__k=1", "coro_02__k=1"]
    assert len(k3) == 10
    assert k3[-1] == "coro_10__k=3"


def test_document_spread_patch_applies_where_voice_exists():
    # la patch di coro_09 tocca solo le istanze dove la voce esiste; puo'
    # contenere expr con variabili del percorso (l'eccezione evolve)
    data = _coro_study(
        {"onset": {"values": [0, 10, 20]}, "w": {"base": [[0, 0], [1, 1]]}},
        patches={
            "coro_02": {"base": {"volume": {"expr": "0 - 20 * w", "let": {"w": 0}}}},
            "coro_09": {"base": {"volume": -90}},
        },
    )
    doc = generate_percorso_document(data, "ptest", output_sr=None)
    by_id = _by_id(doc)
    # coro_09 esiste solo nell'istanza 3 (n=10): niente stream orfani prima
    assert "coro_09__k=1" not in by_id
    assert "coro_09__k=2" not in by_id
    assert by_id["coro_09__k=3"]["volume"] == -90
    # la patch-expr di coro_02 evolve con w
    assert by_id["coro_02__k=1"]["volume"] == 0
    assert by_id["coro_02__k=3"]["volume"] == -20


def test_document_spread_n_expr_below_one_errors():
    data = _coro_study({"onset": {"values": [0, 10]},
                        "w": {"base": [[0, -0.2], [1, 0]]}})
    with pytest.raises(SpecError, match="inter"):
        generate_percorso_document(data, "ptest", output_sr=None)


def test_document_title_and_seed():
    doc = _pdoc({"onset": {"values": [0, 10]}, "w": 1})
    assert doc["title"] == "ptest :: stack :: percorso"
    assert doc["seed"] == 7


# --- gain_compensation sul percorso (issue #36) ----------------------------------
# Come stack e versions: col blocco e un samples_dir risolto, ogni istanza del
# percorso riceve l'offset di volume che pareggia il mascheramento fra punti di
# lettura diversi dello stesso buffer. Senza samples_dir non tocca niente.

SR = 48000


def _gain_study(gain=None):
    """Percorso a due stream (forte/debole) che leggono punti diversi del buffer,
    tre istanze enumerate che si sovrappongono nel tempo."""
    data = {
        "study_id": "ptest",
        # Niente 'duration:' top-level (#42): la durata la da' l'istanza
        # ('percorso.duration'), che viaggia come base.duration del documento.
        "base": {
            "sample": "t.wav",
            "volume": 0.0,
            "time_mode": "normalized",
            "grain": {"envelope": "hanning", "duration_unit": "samples"},
            "pointer": {"loop_unit": "absolute", "speed_ratio": 0},
        },
        "axes": {
            "density": {"baseline": 10, "base": 10},
            "grain.duration": {"baseline": 50, "base": 50},
        },
        "stack": {"density": {"base": 1}, "grain.duration": {"base": 1}},
        "streams": {
            "forte": {"base": {"pointer": {"start": 0.1}}},
            "debole": {"base": {"pointer": {"start": 0.6}}},
        },
        "percorso": {
            "onset": {"values": [0, 3, 6]},
            "duration": {"base": 10, "unit": "s"},
        },
    }
    if gain is not None:
        data["gain_compensation"] = gain
    return data


@pytest.fixture
def buffer_dir(tmp_path):
    import numpy as np
    import soundfile as sf

    x = np.concatenate([np.full(SR // 2, 0.8), np.full(SR // 2, 0.08)])
    sf.write(str(tmp_path / "t.wav"), x, SR)
    return str(tmp_path)


def test_document_gain_compensation_pairs_each_instance(buffer_dir):
    doc = generate_percorso_document(
        _gain_study({"alpha": 1.0}), "ptest", output_sr=SR, samples_dir=buffer_dir
    )
    vols = [s["volume"] for s in doc["streams"]]
    # forte/debole di ogni istanza si pareggiano (20 dB), un solo massimo a 0
    # su tutto il percorso (traslazione in sottrazione unica).
    assert max(vols) == 0.0
    assert max(vols) - min(vols) == pytest.approx(20.0, abs=0.5)
    by_id = _by_id(doc)
    for k in (1, 2, 3):
        forte = by_id[f"forte__k={k}"]["volume"]
        debole = by_id[f"debole__k={k}"]["volume"]
        assert debole - forte == pytest.approx(20.0, abs=0.5)


def test_document_gain_compensation_noop_without_samples_dir(buffer_dir):
    # Senza samples_dir il sample non e' raggiungibile: documento com'era, in
    # silenzio (non e' un errore), i volumi restano tutti alla base.
    doc = generate_percorso_document(
        _gain_study({"alpha": 1.0}), "ptest", output_sr=SR, samples_dir=None
    )
    assert {s["volume"] for s in doc["streams"]} == {0.0}


def test_document_without_gain_block_untouched(buffer_dir):
    # Non-regressione: senza blocco gain_compensation i volumi non cambiano
    # anche se il samples_dir e' risolto.
    doc = generate_percorso_document(
        _gain_study(), "ptest", output_sr=SR, samples_dir=buffer_dir
    )
    assert {s["volume"] for s in doc["streams"]} == {0.0}


# --- la duration d'istanza passa per base.duration (issue #42) --------------------

def test_instance_duration_is_stream_default():
    # La durata d'istanza (qui legato: l'intervallo fra un onset e il
    # successivo) fa da default per gli stream dell'istanza.
    doc = _pdoc({"onset": {"values": [0, 10, 25]}, "w": 1})
    by_id = _by_id(doc)
    assert by_id["fermo__k=1"]["duration"] == 10
    assert by_id["fermo__k=2"]["duration"] == 15


def test_instance_duration_loses_to_per_stream_duration():
    data = _study({"onset": {"values": [0, 10, 25]}, "w": 1})
    data["streams"]["fermo"] = {"duration": 3}
    doc = generate_percorso_document(data, "ptest", output_sr=None)
    assert {s["duration"] for s in doc["streams"]} == {3}


def test_instance_duration_never_travels_as_top_level_key(monkeypatch):
    # La duration d'istanza e' un canale INTERNO fra percorso e parse. Passava
    # per la 'duration:' top-level del documento, che la fase 5 di #42 vieta:
    # da qui in poi viaggia dove i default degli stream vivono, base.duration.
    from granstudies import study_spec

    visti = []
    originale = study_spec.resolve_streams

    def spia(data, *args, **kwargs):
        visti.append(data)
        return originale(data, *args, **kwargs)

    monkeypatch.setattr(study_spec, "resolve_streams", spia)
    _pdoc({"onset": {"values": [0, 10, 25]}, "w": 1})
    assert visti, "il percorso non ha risolto nessuno stream"
    assert all("duration" not in d for d in visti)
    assert [d["base"]["duration"] for d in visti] == [10, 15, 15]


def test_instance_duration_wins_over_document_base_duration():
    # base.duration e' il default del documento, la duration d'istanza e' piu'
    # specifica: la ombreggia (come fa la duration di versione).
    data = _study({"onset": {"values": [0, 10, 25]}, "w": 1})
    data["base"]["duration"] = 99
    doc = generate_percorso_document(data, "ptest", output_sr=None)
    by_id = _by_id(doc)
    assert by_id["fermo__k=1"]["duration"] == 10
    assert doc["duration"] == 40                  # 25 + 15, non 25 + 99


# --- divieto del duration: top-level anche nel ramo percorso (issue #42, D3) ---

def test_top_level_duration_rejected_in_percorso():
    # Come per versions: resolve_streams vede solo i documenti per-istanza, e
    # il pop del top-level lo rendeva invisibile invece che vietato.
    data = _study({"onset": {"values": [0, 10, 25]}, "w": 1})
    data["duration"] = 999
    with pytest.raises(SpecError, match=r"base\.duration"):
        generate_percorso_document(data, "ptest", output_sr=None)


def test_empty_base_block_takes_the_instance_duration():
    # 'base:' dichiarato vuoto e' None, non {}: l'iniezione della duration
    # d'istanza non deve inciamparci.
    data = _study({"onset": {"values": [0, 10, 25]}, "w": 1})
    data["base"] = None
    data["streams"]["fermo"] = {"base": {"onset": 0, "sample": "corpus.wav"}}
    doc = generate_percorso_document(data, "ptest", output_sr=None)
    assert {s["duration"] for s in doc["streams"]} == {10, 15}
