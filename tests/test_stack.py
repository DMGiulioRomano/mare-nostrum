import pytest

from granstudies.stack import axis_envelope


# --- caso X linear (default: assenza dal blocco): n dalla Y ----------------------

def test_values_with_default_x_linear():
    env = axis_envelope({"values": [1, 2, 3]}, None, duration=30.0)
    assert env == [[0.0, 1], [0.5, 2], [1.0, 3]]


def test_ramp_with_x_linear():
    env = axis_envelope(
        {"ramp": {"start": 0.001, "stop": 0.002, "step": 0.0005}},
        None,
        duration=30.0,
    )
    assert [t for t, _ in env] == [0.0, 0.5, 1.0]
    assert [v for _, v in env] == [0.001, 0.0015, 0.002]


def test_band_with_n_and_x_linear():
    env = axis_envelope(
        {"band": {"n": 4, "base": 0, "range": 10, "seed": 1}}, None, duration=30.0
    )
    assert len(env) == 4
    assert [t for t, _ in env] == [0.0, pytest.approx(1 / 3), pytest.approx(2 / 3), 1.0]


def test_single_value_is_single_point():
    env = axis_envelope({"values": [42]}, None, duration=30.0)
    assert env == [[0.0, 42]]


# --- caso X-walk (rspline): la X possiede n, la Y segue --------------------------

def test_rspline_end_to_end_counts_match_and_deterministic():
    y = {"band": {"base": 0, "range": 10}}
    x = {"base": 5, "range": 0}
    a = axis_envelope(y, x, duration=10.0, y_seed=1, x_seed=2)
    b = axis_envelope(y, x, duration=10.0, y_seed=1, x_seed=2)
    assert a == b
    assert len(a) == 50                       # n emerge: 5 Hz x 10 s
    times = [t for t, _ in a]
    assert times == sorted(times)
    assert all(0 <= v <= 10 for _, v in a)


def test_rspline_y_sampled_at_real_times():
    # Banda Y collassata e mobile: il valore DEVE essere l'interpolazione al
    # tempo reale del punto (coupling), non all'indice.
    bp = [[0, 0], [1, 10]]
    y = {"band": {"base": bp}}
    x = {"base": 5, "range": 0}
    env = axis_envelope(y, x, duration=10.0)
    for t, v in env:
        assert v == pytest.approx(10 * t, abs=1e-6)


def test_seed_in_axis_config_wins_over_global():
    y = {"band": {"base": 0, "range": 10, "seed": 7}}
    x = {"base": 5, "range": 1, "seed": 9}
    a = axis_envelope(y, x, duration=10.0, y_seed=1, x_seed=1)
    b = axis_envelope(y, x, duration=10.0, y_seed=2, x_seed=2)
    assert a == b                             # i seed per-asse vincono sui globali


def test_global_seeds_apply_when_axis_has_none():
    y = {"band": {"base": 0, "range": 10}}
    x = {"base": 5, "range": 1}
    a = axis_envelope(y, x, duration=10.0, y_seed=1, x_seed=1)
    b = axis_envelope(y, x, duration=10.0, y_seed=2, x_seed=2)
    assert a != b


# --- validazione n-ownership (nei due sensi) -------------------------------------

def test_x_walk_with_y_values_raises():
    with pytest.raises(ValueError):
        axis_envelope({"values": [1, 2]}, {"base": 5}, duration=10.0)


def test_x_walk_with_y_band_with_n_raises():
    with pytest.raises(ValueError):
        axis_envelope(
            {"band": {"n": 5, "base": 0, "range": 1}},
            {"base": 5},
            duration=10.0,
        )


def test_x_linear_with_y_band_without_n_raises():
    with pytest.raises(ValueError):
        axis_envelope({"band": {"base": 0, "range": 1}}, None, duration=10.0)


# --- generate_stack_document: N stream collassati in un documento ----------------

def _study_data():
    return {
        "study_id": "s",
        "title": "Studio stack",
        "seed": 1988,
        "base": {"sample": "x.wav", "volume": -6, "duration": 30},
        "axes": {
            "density": {
                "path": "density",
                "baseline": 20,
                "values": [5, 50, 400],
                "interpolation": "cubic",
            },
            "grain_duration": {
                "path": "grain.duration",
                "values": [0.01],           # un solo valore -> resta scalare
            },
        },
        "stack": {"seed": 42},
        "streams": {
            "voce_a": {"base": {"pointer": {"start": 0.1}}},
            "voce_b": {"base": {"pointer": {"start": 0.4}}},
        },
    }


def _specs(data=None):
    from granstudies.study_spec import resolve_streams

    return resolve_streams(data or _study_data())


def test_document_collapses_all_streams():
    from granstudies.stack import generate_stack_document

    doc = generate_stack_document(_specs())
    assert len(doc["streams"]) == 2
    assert doc["duration"] == 30
    assert doc["seed"] == 1988
    ids = [s["stream_id"] for s in doc["streams"]]
    assert ids == ["voce_a", "voce_b"]


def test_document_axes_become_independent_envelopes():
    from granstudies.stack import generate_stack_document

    doc = generate_stack_document(_specs())
    s = doc["streams"][0]
    assert s["density"] == {
        "type": "cubic",
        "points": [[0.0, 5], [0.5, 50], [1.0, 400]],
        "time_mode": "normalized",
    }
    assert s["time_mode"] == "normalized"
    assert s["duration"] == 30


def test_document_single_value_axis_stays_scalar():
    from granstudies.stack import generate_stack_document

    doc = generate_stack_document(_specs())
    assert doc["streams"][0]["grain"]["duration"] == 0.01


def test_document_deterministic_with_rspline_axis():
    from granstudies.stack import generate_stack_document

    data = _study_data()
    data["axes"]["density"] = {
        "path": "density",
        "baseline": 20,
        "base": 5,
        "range": 45,
        "interpolation": "cubic",
    }
    data["stack"]["density"] = {"base": 3, "range": 1}
    a = generate_stack_document(_specs(data))
    b = generate_stack_document(_specs(data))
    assert a == b
    # Senza seed globali, l'auto-derivazione per-stream decorrela le voci:
    # stessi assi, envelope diversi tra voce_a e voce_b.
    del data["stack"]["seed"]
    c = generate_stack_document(_specs(data))
    pts_a = c["streams"][0]["density"]["points"]
    pts_b = c["streams"][1]["density"]["points"]
    assert pts_a != pts_b


def test_document_emerging_values_clamped_to_engine_bounds():
    # I valori espliciti fuori bounds falliscono gia' al parse; quelli che
    # EMERGONO (banda Y deferita, sotto il minimo engine) vanno clampati.
    from granstudies.stack import generate_stack_document

    data = _study_data()
    data["axes"]["grain_duration"] = {
        "path": "grain.duration",
        "base": 0.00001,
        "range": 0.00001,  # sotto sia il floor statico (1ms) sia 4 campioni @48k
    }
    data["stack"]["grain_duration"] = {"base": 2, "range": 0}

    # Senza output_sr esplicito: default 48000, floor dinamico a 4 campioni.
    doc = generate_stack_document(_specs(data))
    pts = doc["streams"][0]["grain"]["duration"]["points"]
    assert all(v == 4 / 48000 for _, v in pts)

    # output_sr=None ripristina il fallback statico di 1ms (issue #17).
    doc_static = generate_stack_document(_specs(data), output_sr=None)
    pts_static = doc_static["streams"][0]["grain"]["duration"]["points"]
    assert all(v == 0.001 for _, v in pts_static)


def test_document_clamp_rispetta_duration_unit_milliseconds():
    """Con ``duration_unit: milliseconds`` i valori dell'asse sono in ms: i
    bounds engine (secondi) vanno riportati in ms prima di clampare, altrimenti
    una grana di 50 ms verrebbe schiacciata al tetto di 10."""
    from granstudies.stack import generate_stack_document

    data = _study_data()
    data["base"]["grain"] = {"duration_unit": "milliseconds"}
    data["axes"]["grain_duration"] = {
        "path": "grain.duration",
        "baseline": 50,
        "base": 50,
        "range": 0,
    }
    data["stack"]["grain_duration"] = {"base": 2, "range": 0}

    doc = generate_stack_document(_specs(data))
    dur = doc["streams"][0]["grain"]["duration"]
    pts = dur["points"] if isinstance(dur, dict) else [[0, dur]]
    assert all(v == 50 for _, v in pts)


def test_document_clamp_millisecondi_sotto_il_floor():
    """Sotto il minimo (4 campioni @48k = 1/12 ms) il clamp resta in ms."""
    from granstudies.stack import generate_stack_document

    data = _study_data()
    data["base"]["grain"] = {"duration_unit": "milliseconds"}
    data["axes"]["grain_duration"] = {
        "path": "grain.duration",
        "baseline": 50,
        "base": 0.00001,
        "range": 0.00001,
    }
    data["stack"]["grain_duration"] = {"base": 2, "range": 0}

    doc = generate_stack_document(_specs(data))
    dur = doc["streams"][0]["grain"]["duration"]
    pts = dur["points"] if isinstance(dur, dict) else [[0, dur]]
    assert all(v == pytest.approx(4 / 48000 * 1000) for _, v in pts)


def test_baseline_obbligatorio_con_duration_unit_dichiarata():
    """Il default engine di ``grain.duration`` e' in secondi: con un'unita'
    dichiarata non e' un valore in quell'unita', quindi il baseline va scritto.
    Stessa regola dell'engine sulla ``grain.duration`` esplicita."""
    from granstudies.errors import SpecError

    data = _study_data()
    data["base"]["grain"] = {"duration_unit": "milliseconds"}
    data["axes"]["grain_duration"] = {"path": "grain.duration", "values": [50]}

    with pytest.raises(SpecError, match="'baseline' e' obbligatorio"):
        _specs(data)


# --- unit della camminata-X alle seam dello stack ---------------------------------

def test_axis_entry_unit_seconds_walks_in_period_space():
    y = {"band": {"base": 0, "range": 10}}
    x = {"base": 2, "range": 0, "unit": "s"}
    env = axis_envelope(y, x, duration=10.0, y_seed=1, x_seed=2)
    assert [t for t, _ in env] == [0.0, 0.2, 0.4, 0.6, 0.8]


def test_global_x_unit_applies_when_entry_has_none():
    y = {"band": {"base": 0, "range": 10}}
    x = {"base": 2, "range": 0}
    env = axis_envelope(y, x, duration=10.0, x_unit="s")
    assert [t for t, _ in env] == [0.0, 0.2, 0.4, 0.6, 0.8]


def test_unit_in_axis_entry_wins_over_global():
    y = {"band": {"base": 0, "range": 10}}
    x = {"base": 2, "range": 0, "unit": "hz"}
    env = axis_envelope(y, x, duration=10.0, x_unit="s")
    assert len(env) == 20           # 2 Hz x 10 s, non un punto ogni 2 s


def test_document_stack_unit_seconds_end_to_end():
    from granstudies.stack import generate_stack_document

    data = _study_data()
    data["axes"]["density"] = {
        "path": "density", "baseline": 20, "base": 5, "range": 45,
    }
    data["stack"]["unit"] = "s"
    data["stack"]["density"] = {"base": 3, "range": 0}
    doc = generate_stack_document(_specs(data))
    pts = doc["streams"][0]["density"]["points"]
    # duration 30, un punto ogni 3 s: t reali 0..27 -> normalizzati 0.0..0.9.
    assert [t for t, _ in pts] == [pytest.approx(i / 10) for i in range(10)]


# --- generatori annidati (plan nested-generators) ---------------------------------

def test_nested_base_in_y_band_follows_generated_floor():
    # range 0: la banda collassa e insegue il pavimento generato [0 -> 10].
    y = {"band": {"n": 4, "base": {"linear_env": [0, 10]}, "range": 0}}
    env = axis_envelope(y, None, duration=10.0)
    assert [v for _, v in env] == [
        pytest.approx(0.0), pytest.approx(10 / 3),
        pytest.approx(20 / 3), pytest.approx(10.0),
    ]


def test_nested_base_with_type_step_makes_plateaus():
    y = {"band": {"n": 4, "base": {"type": "step", "linear_env": [0, 10]},
                  "range": 0}}
    env = axis_envelope(y, None, duration=10.0)
    assert [v for _, v in env] == [0.0, 0.0, 0.0, 10.0]


def test_nested_in_x_walk_base_deterministic():
    y = {"band": {"base": 0, "range": 10}}
    x = {"base": {"linear_env": [5, 5]}, "range": 0}
    a = axis_envelope(y, x, duration=10.0, y_seed=1, x_seed=2)
    b = axis_envelope(y, x, duration=10.0, y_seed=1, x_seed=2)
    assert a == b
    assert len(a) == 50  # frequenza costante 5 Hz x 10 s


def test_nested_third_level_in_x_walk():
    y = {"band": {"base": 0, "range": 10}}
    x = {
        "base": {"linear_env": {"n": 8, "base": 2, "range": 4}},
        "range": {"linear_env": {
            "n": 5, "base": 0.5,
            "range": {"linear_env": {"ramp": {"start": 1, "stop": 4, "step": 1}}},
        }},
    }
    a = axis_envelope(y, x, duration=10.0, y_seed=1, x_seed=2)
    b = axis_envelope(y, x, duration=10.0, y_seed=1, x_seed=2)
    assert a == b
    times = [t for t, _ in a]
    assert times == sorted(times)


def test_nested_y_ramp_with_env_step_in_stack():
    y = {"ramp": {"start": 0, "stop": 10, "step": {"type": "step", "points": [[0, 2], [0.5, 1]]}}}
    env = axis_envelope(y, None, duration=10.0)
    assert [v for _, v in env] == [0, 2, 4, 6, 7, 8, 9, 10]


# --- distribution e drift alle seam dello stack (issue #16) ------------------------

def test_drift_in_y_band_with_x_walk_deterministic_in_band():
    # rspline con Y in deriva: la banda [0, 10] contiene tutti i valori e la
    # sequenza e' riproducibile.
    y = {"band": {"base": 0, "range": 10, "drift": {"step": 0.1}}}
    x = {"base": 5, "range": 0}
    a = axis_envelope(y, x, duration=10.0, y_seed=1, x_seed=2)
    b = axis_envelope(y, x, duration=10.0, y_seed=1, x_seed=2)
    assert a == b
    assert all(0 <= v <= 10 for _, v in a)
    ind = axis_envelope({"band": {"base": 0, "range": 10}}, x,
                        duration=10.0, y_seed=1, x_seed=2)
    assert a != ind


def test_drift_in_x_walk_changes_times_deterministically():
    y = {"band": {"base": 0, "range": 10}}
    x = {"base": 3, "range": 4, "drift": {"step": 0.1}}
    a = axis_envelope(y, x, duration=10.0, y_seed=1, x_seed=2)
    b = axis_envelope(y, x, duration=10.0, y_seed=1, x_seed=2)
    assert a == b
    times = [t for t, _ in a]
    assert times == sorted(times)
    ind = axis_envelope(y, {"base": 3, "range": 4}, duration=10.0,
                        y_seed=1, x_seed=2)
    assert times != [t for t, _ in ind]


def test_gaussian_in_y_band_with_n_and_x_linear():
    y = {"band": {"n": 12, "base": 0, "range": 10, "distribution": "gaussian"}}
    env = axis_envelope(y, None, duration=10.0, y_seed=3)
    assert len(env) == 12
    assert all(0 <= v <= 10 for _, v in env)
    assert env != axis_envelope({"band": {"n": 12, "base": 0, "range": 10}},
                                None, duration=10.0, y_seed=3)


def test_drift_step_nested_node_at_stack_seam():
    # drift.step come nodo-generatore: l'espansione alla seam lo compila.
    y = {"band": {"base": 0, "range": 10,
                  "drift": {"step": {"linear_env": {"n": 3, "base": 0.01,
                                                    "range": 0.1}}}}}
    x = {"base": 5, "range": 0}
    a = axis_envelope(y, x, duration=10.0, y_seed=1, x_seed=2)
    b = axis_envelope(y, x, duration=10.0, y_seed=1, x_seed=2)
    assert a == b
    assert all(0 <= v <= 10 for _, v in a)


# --- duration/onset per-stream (issue #26) ----------------------------------------

def test_stream_onset_written_into_engine_stream():
    from granstudies.stack import generate_stack_document

    data = _study_data()
    data["streams"]["voce_b"]["onset"] = 5
    doc = generate_stack_document(_specs(data))
    by_id = {s["stream_id"]: s for s in doc["streams"]}
    assert by_id["voce_b"]["onset"] == 5
    assert "onset" not in by_id["voce_a"]     # non dichiarato: nessuna chiave


def test_stream_onset_wins_over_inherited_base_onset():
    from granstudies.stack import generate_stack_document

    data = _study_data()
    data["base"]["onset"] = 2                 # ereditato da tutti gli stream
    data["streams"]["voce_b"]["onset"] = 5    # l'onset per-stream vince
    doc = generate_stack_document(_specs(data))
    by_id = {s["stream_id"]: s for s in doc["streams"]}
    assert by_id["voce_a"]["onset"] == 2      # base.onset resta intatto
    assert by_id["voce_b"]["onset"] == 5


def test_stream_duration_written_into_engine_stream():
    from granstudies.stack import generate_stack_document

    data = _study_data()
    data["streams"]["voce_b"]["duration"] = 12
    doc = generate_stack_document(_specs(data))
    by_id = {s["stream_id"]: s for s in doc["streams"]}
    assert by_id["voce_a"]["duration"] == 30  # eredita il default
    assert by_id["voce_b"]["duration"] == 12  # override locale


def test_document_duration_covers_shifted_stream():
    from granstudies.stack import generate_stack_document

    data = _study_data()
    data["streams"]["voce_b"]["onset"] = 10   # 10 + 30 > 30: il documento copre
    doc = generate_stack_document(_specs(data))
    assert doc["duration"] == 40


def test_document_duration_covers_base_onset_too():
    from granstudies.stack import generate_stack_document

    data = _study_data()
    data["streams"]["voce_b"]["base"] = {"onset": 4}
    doc = generate_stack_document(_specs(data))
    assert doc["duration"] == 34


def test_document_without_base_duration():
    from granstudies.stack import generate_stack_document

    data = _study_data()
    del data["base"]["duration"]
    data["streams"]["voce_a"]["duration"] = 10
    data["streams"]["voce_b"] = {"duration": 25, "onset": 10}
    doc = generate_stack_document(_specs(data))
    by_id = {s["stream_id"]: s for s in doc["streams"]}
    assert by_id["voce_a"]["duration"] == 10
    assert doc["duration"] == 35              # max(onset + duration)


# --- base.duration nel ramo streams (issue #42) -----------------------------------

def _base_duration_data():
    # _study_data la dichiara gia' in base (post-migrazione): alias esplicito.
    return _study_data()


def test_base_duration_survives_stream_construction():
    # Il sintomo 2 di #42: prima la base.duration era sovrascritta senza
    # guardare, quindi una 'base: {duration: N}' non faceva nulla e non
    # avvisava. Ora e' la fonte, e arriva nello stream engine.
    from granstudies.stack import generate_stack_document

    doc = generate_stack_document(_specs(_base_duration_data()))
    assert [s["duration"] for s in doc["streams"]] == [30, 30]


def test_entry_base_duration_is_read_per_stream():
    from granstudies.stack import generate_stack_document

    data = _base_duration_data()
    data["streams"]["voce_b"]["base"] = {"duration": 12}
    doc = generate_stack_document(_specs(data))
    by_id = {s["stream_id"]: s for s in doc["streams"]}
    assert by_id["voce_a"]["duration"] == 30
    assert by_id["voce_b"]["duration"] == 12


def test_entry_duration_wins_over_entry_base_duration():
    # La catena entry > base va risolta PRIMA di scrivere lo stream: rendere
    # condizionale la scrittura di stack.py (non riscrivere se base ne ha
    # gia' una) perderebbe proprio questo override.
    from granstudies.stack import generate_stack_document

    data = _base_duration_data()
    data["streams"]["voce_b"] = {"duration": 12, "base": {"duration": 99}}
    doc = generate_stack_document(_specs(data))
    by_id = {s["stream_id"]: s for s in doc["streams"]}
    assert by_id["voce_b"]["duration"] == 12


def test_document_duration_unchanged_with_base_duration():
    from granstudies.stack import generate_stack_document

    data = _base_duration_data()
    data["streams"]["voce_b"]["onset"] = 10
    doc = generate_stack_document(_specs(data))
    assert doc["duration"] == 40              # max(onset + duration), invariato
