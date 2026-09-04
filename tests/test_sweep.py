from granstudies.study_spec import parse_study_spec
from granstudies.sweep import generate_variants, generate_discrete_variants


def _mode_spec(mode):
    return parse_study_spec(
        {
            "study_id": "s",
            "base": {"density": 20, "volume": -6},
            "axes": {
                "a": {"path": "density", "baseline": 20, "values": [5, 50]},
                "b": {"path": "volume", "baseline": -6, "values": [-12, -3]},
            },
            "sweep": {"orders": [0, 1, 2], "mode": mode},
        }
    )


def test_discrete_mode_generates_variants():
    assert len(generate_discrete_variants(_mode_spec("discrete"))) == 9


def test_envelope_mode_returns_empty_discrete():
    # in mode envelope la pipeline discrete non produce nulla
    assert generate_discrete_variants(_mode_spec("envelope")) == []


def test_both_mode_generates_discrete_variants():
    assert len(generate_discrete_variants(_mode_spec("both"))) == 9


def test_generate_variants_is_alias():
    assert generate_variants is generate_discrete_variants


def _clean_spec(orders):
    # baseline NON tra i valori -> conteggi deterministici (nessun collasso)
    return parse_study_spec(
        {
            "study_id": "s",
            "base": {"density": 20, "volume": -6},
            "axes": {
                "a": {"path": "density", "baseline": 20, "values": [5, 50]},
                "b": {"path": "volume", "baseline": -6, "values": [-12, -3]},
            },
            "sweep": {"orders": orders},
        }
    )


def test_counts_per_order():
    variants = generate_variants(_clean_spec([0, 1, 2]))
    by_order = {}
    for v in variants:
        by_order.setdefault(v.order, []).append(v)
    assert len(by_order[0]) == 1          # baseline
    assert len(by_order[1]) == 4          # 2 assi * 2 valori
    assert len(by_order[2]) == 4          # 1 coppia * 2*2
    assert len(variants) == 9


def test_naming():
    variants = generate_variants(_clean_spec([0, 1]))
    names = {v.name for v in variants}
    assert "o0__baseline" in names
    assert "o1__a=50" in names
    assert "o1__b=-12" in names


def test_order2_name_is_sorted():
    variants = generate_variants(_clean_spec([2]))
    assert all(v.name.startswith("o2__a=") for v in variants)  # 'a' prima di 'b'


def test_baseline_collapse_dedup():
    # 'b' ha baseline 0.5 INCLUSO nei valori: la variante o1 che mette b=0.5
    # coincide con la baseline e viene deduplicata.
    spec = parse_study_spec(
        {
            "study_id": "s",
            "base": {"density": 20, "distribution": 0.5},
            "axes": {
                "a": {"path": "density", "baseline": 20, "values": [5, 50]},
                "b": {"path": "distribution", "baseline": 0.5, "values": [0.0, 0.5, 1.0]},
            },
            "sweep": {"orders": [0, 1]},
        }
    )
    variants = generate_variants(spec)
    names = [v.name for v in variants]
    # b=0.5 NON deve comparire come variante separata (== baseline)
    assert "o1__b=0.5" not in names
    assert "o0__baseline" in names


def test_overrides_are_clamped():
    spec = parse_study_spec(
        {
            "study_id": "s",
            "base": {"density": 20},
            "axes": {"a": {"path": "density", "baseline": 20, "values": [5, 50]}},
            "sweep": {"orders": [1]},
        }
    )
    v = generate_variants(spec)[0]
    ov = v.overrides(spec)
    assert ov["density"] in (5, 50)


def test_to_document_has_stream_id():
    spec = parse_study_spec(
        {
            "study_id": "s",
            "base": {"density": 20},
            "axes": {"a": {"path": "density", "baseline": 20, "values": [5, 50]}},
            "sweep": {"orders": [1]},
        }
    )
    doc = generate_variants(spec)[0].to_document(spec)
    assert doc["streams"][0]["stream_id"]  # l'engine lo richiede
