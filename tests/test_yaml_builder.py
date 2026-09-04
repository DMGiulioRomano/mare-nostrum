import pytest
from granstudies.yaml_builder import deep_set, deep_get, build_stream, build_document


def test_deep_set_creates_nested():
    d = {}
    deep_set(d, "grain.duration", 0.2)
    assert d == {"grain": {"duration": 0.2}}


def test_deep_set_overwrites_non_dict():
    d = {"grain": 5}
    deep_set(d, "grain.duration", 0.2)
    assert d == {"grain": {"duration": 0.2}}


def test_deep_set_top_level():
    d = {}
    deep_set(d, "density", 50)
    assert d == {"density": 50}


def test_deep_get():
    d = {"grain": {"duration": 0.2}}
    assert deep_get(d, "grain.duration") == 0.2
    assert deep_get(d, "grain.missing", "x") == "x"
    assert deep_get(d, "nope", None) is None


def test_build_stream_does_not_mutate_base():
    base = {"density": 20, "grain": {"duration": 0.05}}
    out = build_stream(base, {"grain.duration": 0.2})
    assert out["grain"]["duration"] == 0.2
    assert base["grain"]["duration"] == 0.05  # base intatto


def test_build_document_includes_optional_keys_only_when_given():
    base = {"density": 20}
    doc = build_document(base, {}, title="t", seed=1, duration=6)
    assert doc["title"] == "t" and doc["seed"] == 1 and doc["duration"] == 6
    assert doc["streams"][0]["density"] == 20

    minimal = build_document(base, {})
    assert "title" not in minimal and "seed" not in minimal
    assert minimal["streams"][0] == {"density": 20}


# --- envelope wrapping (gated) -------------------------------------------------

def test_build_stream_wraps_list_override_when_envelope_mode():
    out = build_stream(
        {"density": 20},
        {"density": [[0, 5], [1, 5]]},
        envelope_time_mode="normalized",
    )
    assert out["density"] == {
        "type": "linear",
        "points": [[0, 5], [1, 5]],
        "time_mode": "normalized",
    }


def test_build_stream_per_path_envelope_types():
    out = build_stream(
        {"density": 20, "grain": {"duration": 0.05}},
        {"density": [[0, 5], [1, 5]], "grain.duration": [[0, 0.01], [1, 0.2]]},
        envelope_time_mode="normalized",
        envelope_types={"density": "step", "grain.duration": "cubic"},
    )
    assert out["density"]["type"] == "step"
    assert out["grain"]["duration"]["type"] == "cubic"


def test_build_stream_envelope_types_fallback_to_scalar():
    # path non presente nella mappa -> ricade sul default envelope_type
    out = build_stream(
        {"density": 20},
        {"density": [[0, 5], [1, 5]]},
        envelope_time_mode="normalized",
        envelope_types={},
    )
    assert out["density"]["type"] == "linear"


def test_build_stream_list_override_raw_by_default():
    # backward compat (compose): senza envelope_time_mode la lista resta grezza
    out = build_stream({"density": 20}, {"density": [[0, 5], [1, 5]]})
    assert out["density"] == [[0, 5], [1, 5]]


def test_build_stream_scalar_override_never_wrapped():
    out = build_stream({"density": 20}, {"density": 50}, envelope_time_mode="normalized")
    assert out["density"] == 50


def test_build_document_wraps_list_override():
    doc = build_document(
        {"density": 20},
        {"density": [[0, 5], [0.5, 5], [1, 50]]},
        envelope_time_mode="normalized",
        duration=25,
    )
    stream = doc["streams"][0]
    assert stream["density"] == {
        "type": "linear",
        "points": [[0, 5], [0.5, 5], [1, 50]],
        "time_mode": "normalized",
    }
    assert doc["duration"] == 25


# --- documento multi-stream (processo stack) -------------------------------------

def test_build_multi_document_two_streams():
    from granstudies.yaml_builder import build_multi_document

    s1 = build_stream({"density": 20}, {})
    s2 = build_stream({"density": 20}, {"density": 50})
    doc = build_multi_document([s1, s2], title="t", seed=1, duration=30)
    assert doc["title"] == "t" and doc["seed"] == 1 and doc["duration"] == 30
    assert len(doc["streams"]) == 2
    assert doc["streams"][0]["density"] == 20
    assert doc["streams"][1]["density"] == 50


def test_build_multi_document_mixed_scalar_and_envelope():
    from granstudies.yaml_builder import build_multi_document

    s1 = build_stream(
        {"volume": -6},
        {"density": [[0, 5], [1, 50]], "grain.duration": 0.05},
        envelope_time_mode="normalized",
        envelope_types={"density": "cubic"},
    )
    s2 = build_stream({"volume": -6}, {})   # stream statico: legittimo (drone)
    doc = build_multi_document([s1, s2], duration=30)
    assert doc["streams"][0]["density"]["type"] == "cubic"
    assert doc["streams"][0]["grain"]["duration"] == 0.05
    assert doc["streams"][1] == {"volume": -6}
    assert "title" not in doc and "seed" not in doc


def test_build_multi_document_rejects_empty():
    import pytest
    from granstudies.yaml_builder import build_multi_document

    with pytest.raises(ValueError):
        build_multi_document([])


# --- nodi-expr nei parametri statici: valutati alla costruzione del documento ----

def test_build_stream_resolves_expr_node_scalar():
    base = {"volume": {"expr": "v - 1", "let": {"v": -19}}}
    assert build_stream(base, {})["volume"] == -20


def test_build_stream_resolves_expr_node_nested_env():
    # l'engine accetta envelope scritti direttamente nei parametri stream:
    # un nodo-expr qui produce lo stesso Env che si scriverebbe a mano.
    base = {"grain": {"duration": {"expr": "env / 10",
                                   "let": {"env": [[0, 0.02], [1, 0.1]]}}}}
    assert build_stream(base, {})["grain"]["duration"] == [[0, 0.002], [1, 0.01]]


def test_build_stream_resolves_expr_node_in_override():
    assert build_stream({"volume": -6}, {"onset": {"expr": "2 * 3"}})["onset"] == 6


def test_build_stream_expr_error_carries_path():
    base = {"grain": {"duration": {"expr": "boh"}}}
    with pytest.raises(ValueError, match=r"grain\.duration"):
        build_stream(base, {})


def test_build_stream_static_params_untouched():
    base = {"volume": -6, "pointer": {"start": 0.3}, "sample": "c.wav"}
    assert build_stream(base, {}) == base
