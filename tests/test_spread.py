import pytest

from granstudies import yaml_loc
from granstudies.errors import SpecError
from granstudies.group_let import apply_group_let
from granstudies.spread import expand_spreads, spread_counts
from granstudies.study_spec import resolve_streams


def _streams(**entries):
    """Dict ``streams:`` di comodo (l'ordine di inserimento e' quello YAML)."""
    return dict(entries)


# --- passthrough -------------------------------------------------------------

def test_no_spread_passthrough():
    streams = _streams(base={}, altra={"base": {"volume": -12}})
    assert expand_spreads(streams) == streams


def test_none_entry_passthrough():
    streams = {"base": None}
    assert expand_spreads(streams) == streams


# --- espansione con values ---------------------------------------------------

def _spread_entry(**extra):
    entry = {
        "spread": {
            "over": {"base.pointer.start": {"values": [0.1, 0.2, 0.3]}},
        },
    }
    entry.update(extra)
    return entry


def test_values_expansion_names_and_paths():
    out = expand_spreads(_streams(v=_spread_entry()))
    assert list(out) == ["v_1", "v_2", "v_3"]
    assert out["v_1"]["base"]["pointer"]["start"] == 0.1
    assert out["v_3"]["base"]["pointer"]["start"] == 0.3
    for entry in out.values():
        assert "spread" not in entry


def test_spread_over_dotted_axis_boundary():
    # 'over' su un asse con nome dotted ('grain.duration', senza 'path'): il
    # deep-set non deve spezzare il nome in axes.grain.duration ma fermarsi
    # al confine dell'asse dichiarato.
    streams = _streams(
        v={
            "spread": {
                "over": {"axes.grain.duration.values": {"values": [[0.001], [0.01]]}},
            },
        }
    )
    out = expand_spreads(streams, axis_names=frozenset({"grain.duration"}))
    assert out["v_1"]["axes"]["grain.duration"]["values"] == [0.001]
    assert out["v_2"]["axes"]["grain.duration"]["values"] == [0.01]


def test_spread_over_dotted_axis_end_to_end():
    # Integrazione: spread su asse dotted attraverso resolve_streams.
    data = {
        "study_id": "s",
        "base": {"sample": "x.wav"},
        "axes": {"grain.duration": {"values": [0.001, 0.01]}},
        "sweep": {"mode": "envelope", "orders": [1]},
        "streams": {
            "v": {
                "spread": {
                    "over": {
                        "axes.grain.duration.values": {"values": [[0.002], [0.02]]}
                    },
                },
            }
        },
    }
    specs = resolve_streams(data)
    by_id = {s.stream_id: s for s in specs}
    assert by_id["v_1"].axis("grain.duration").values == [0.002]
    assert by_id["v_2"].axis("grain.duration").values == [0.02]


def test_common_override_preserved_on_every_generated():
    entry = _spread_entry(base={"volume": -12})
    out = expand_spreads(_streams(v=entry))
    for name in ("v_1", "v_2", "v_3"):
        assert out[name]["base"]["volume"] == -12


def test_strategy_wins_over_common_override_on_same_path():
    entry = _spread_entry(base={"pointer": {"start": 0.9, "speed_ratio": 0.5}})
    out = expand_spreads(_streams(v=entry))
    assert out["v_2"]["base"]["pointer"]["start"] == 0.2
    # le chiavi sorelle del deep-set restano
    assert out["v_2"]["base"]["pointer"]["speed_ratio"] == 0.5


def test_generated_entries_are_independent_copies():
    out = expand_spreads(_streams(v=_spread_entry(base={"volume": -12})))
    out["v_1"]["base"]["volume"] = 0
    assert out["v_2"]["base"]["volume"] == -12
    assert out["v_1"]["sweep"] is not out["v_2"]["sweep"]


def test_order_preserved_around_spread():
    streams = _streams(a={}, v=_spread_entry(), z={})
    assert list(expand_spreads(streams)) == ["a", "v_1", "v_2", "v_3", "z"]


def test_zero_padding_follows_n_width():
    entry = {"spread": {"n": 12, "over": {"base.onset": {"values": list(range(12))}}}}
    out = expand_spreads(_streams(v=entry))
    assert list(out)[0] == "v_01"
    assert list(out)[-1] == "v_12"


def test_multiple_paths_paired_by_index():
    entry = {
        "spread": {
            "over": {
                "base.pointer.start": {"values": [0.1, 0.2]},
                "base.onset": {"values": [0, 5]},
            },
        },
    }
    out = expand_spreads(_streams(v=entry))
    assert list(out) == ["v_1", "v_2"]
    assert out["v_2"]["base"]["pointer"]["start"] == 0.2
    assert out["v_2"]["base"]["onset"] == 5


def test_values_accepts_non_numeric():
    entry = {"spread": {"over": {"base.sample": {"values": ["a.wav", "b.wav"]}}}}
    out = expand_spreads(_streams(v=entry))
    assert out["v_1"]["base"]["sample"] == "a.wav"
    assert out["v_2"]["base"]["sample"] == "b.wav"


# --- default sweep: solo stack -------------------------------------------------

def test_sweep_default_injected_empty():
    out = expand_spreads(_streams(v=_spread_entry()))
    for entry in out.values():
        assert entry["sweep"] == {"orders": [], "orderings": []}


def test_explicit_sweep_respected():
    entry = _spread_entry(sweep={"orders": [1]})
    out = expand_spreads(_streams(v=entry))
    for entry in out.values():
        assert entry["sweep"] == {"orders": [1]}


# --- risoluzione di n ----------------------------------------------------------

def test_n_explicit_must_match_values_len():
    entry = {"spread": {"n": 4, "over": {"base.onset": {"values": [1, 2, 3]}}}}
    with pytest.raises(SpecError) as exc:
        expand_spreads(_streams(v=entry))
    assert exc.value.stream == "v"


def test_two_values_with_different_len_raise():
    entry = {
        "spread": {
            "over": {
                "base.onset": {"values": [1, 2, 3]},
                "base.volume": {"values": [-6, -3]},
            },
        },
    }
    with pytest.raises(SpecError):
        expand_spreads(_streams(v=entry))


def test_n_below_one_raises():
    entry = {"spread": {"n": 0, "over": {"base.onset": {"values": []}}}}
    with pytest.raises(SpecError):
        expand_spreads(_streams(v=entry))


# --- strategy ramp ---------------------------------------------------------------

def test_ramp_full_owns_count():
    entry = {"spread": {"over": {"base.onset": {"ramp": {"start": 0, "stop": 6, "step": 2}}}}}
    out = expand_spreads(_streams(v=entry))
    assert list(out) == ["v_1", "v_2", "v_3", "v_4"]
    assert [out[k]["base"]["onset"] for k in out] == [0, 2, 4, 6]


def test_ramp_start_step_needs_n():
    entry = {
        "spread": {
            "n": 4,
            "over": {"base.pointer.start": {"ramp": {"start": 0.1, "step": 0.1}}},
        },
    }
    out = expand_spreads(_streams(v=entry))
    assert [out[k]["base"]["pointer"]["start"] for k in out] == [0.1, 0.2, 0.3, 0.4]


def test_ramp_start_step_without_n_raises():
    entry = {"spread": {"over": {"base.onset": {"ramp": {"start": 0, "step": 1}}}}}
    with pytest.raises(SpecError):
        expand_spreads(_streams(v=entry))


def test_ramp_start_stop_is_linspace_over_n():
    entry = {
        "spread": {
            "n": 5,
            "over": {"base.volume": {"ramp": {"start": -12, "stop": 0}}},
        },
    }
    out = expand_spreads(_streams(v=entry))
    assert [out[k]["base"]["volume"] for k in out] == [-12, -9, -6, -3, 0]


def test_ramp_start_stop_with_n_1_holds_start():
    entry = {"spread": {"n": 1, "over": {"base.volume": {"ramp": {"start": -12, "stop": 0}}}}}
    out = expand_spreads(_streams(v=entry))
    assert out["v_1"]["base"]["volume"] == -12


def test_ramp_only_start_raises():
    entry = {"spread": {"n": 3, "over": {"base.onset": {"ramp": {"start": 0}}}}}
    with pytest.raises(SpecError):
        expand_spreads(_streams(v=entry))


def test_ramp_full_count_mismatch_with_explicit_n_raises():
    entry = {
        "spread": {
            "n": 3,
            "over": {"base.onset": {"ramp": {"start": 0, "stop": 6, "step": 2}}},
        },
    }
    with pytest.raises(SpecError):
        expand_spreads(_streams(v=entry))


# --- chiavi puntate in over --------------------------------------------------------

def test_over_dotted_values_equals_nested():
    dotted = {"spread": {"over": {"base.pointer.start.values": [0.1, 0.2, 0.3]}}}
    nested = {"spread": {"over": {"base.pointer.start": {"values": [0.1, 0.2, 0.3]}}}}
    assert expand_spreads(_streams(v=dotted)) == expand_spreads(_streams(v=nested))


def test_over_dotted_expr_marker():
    entry = {"spread": {"n": 3, "over": {"base.onset.expr": "10 * (i + 1)"}}}
    out = expand_spreads(_streams(v=entry))
    assert [out[k]["base"]["onset"] for k in out] == [10, 20, 30]


def test_over_dotted_leaves_dict_valued_strategy_as_full_path():
    # Valore-dict = strategy completa: la chiave resta path intero, anche se
    # termina con un marcatore (banda-base di un asse).
    entry = {
        "spread": {
            "n": 2,
            "over": {"axes.density.base": {"expr": "50 * (i + 1)", "let": {}}},
        },
    }
    out = expand_spreads(_streams(v=entry))
    assert out["v_1"]["axes"]["density"]["base"] == 50
    assert out["v_2"]["axes"]["density"]["base"] == 100


def test_over_dotted_banda_fragments_merge_on_path():
    # base + range + seed su tre righe puntate si fondono in un'unica strategy.
    from granstudies.value_generators import band

    entry = {
        "spread": {
            "n": 4,
            "over": {
                "base.volume.base": -12,
                "base.volume.range": 6,
                "base.volume.seed": 42,
            },
        },
    }
    out = expand_spreads(_streams(v=entry))
    assert [out[k]["base"]["volume"] for k in out] == band(n=4, base=-12, range=6, seed=42)


def test_over_dotted_two_markers_same_path_conflicts():
    # Due marcatori terminali puntati sullo stesso path (values + expr) si
    # fondono in un'unica strategy a due marcatori: errore a valle.
    entry = {
        "spread": {
            "over": {
                "base.onset.values": [1, 2],
                "base.onset.expr": "i",
            },
        },
    }
    with pytest.raises(SpecError):
        expand_spreads(_streams(v=entry))


def test_over_nondotted_path_unchanged():
    # Un path che NON termina con un marcatore resta chiave-path intera.
    entry = {"spread": {"over": {"base.pointer.start": {"values": [0.1, 0.2]}}}}
    out = expand_spreads(_streams(v=entry))
    assert out["v_1"]["base"]["pointer"]["start"] == 0.1


# --- strategy banda ----------------------------------------------------------------

def test_band_draws_n_values_in_band():
    entry = {
        "spread": {
            "n": 6,
            "over": {"base.volume": {"base": -12, "range": 6}},
        },
    }
    out = expand_spreads(_streams(v=entry))
    vols = [out[k]["base"]["volume"] for k in out]
    assert len(vols) == 6
    assert all(-12 <= v <= -6 for v in vols)


def test_band_with_distribution_and_drift_in_spread():
    # Le chiavi di banda dell'issue #16 viaggiano anche nella strategy di spread.
    entry = {
        "spread": {
            "n": 6,
            "over": {"base.volume": {"base": -12, "range": 6,
                                     "distribution": "gaussian",
                                     "drift": {"step": 0.2}}},
        },
    }
    a = expand_spreads(_streams(v=entry))
    b = expand_spreads(_streams(v=entry))
    vols = [a[k]["base"]["volume"] for k in a]
    assert [b[k]["base"]["volume"] for k in b] == vols
    assert len(vols) == 6
    assert all(-12 <= v <= -6 for v in vols)


def test_band_explicit_seed_matches_band_generator():
    from granstudies.value_generators import band

    entry = {
        "spread": {
            "n": 4,
            "over": {"base.volume": {"base": -12, "range": 6, "seed": 42}},
        },
    }
    out = expand_spreads(_streams(v=entry))
    assert [out[k]["base"]["volume"] for k in out] == band(n=4, base=-12, range=6, seed=42)


def test_band_default_seed_deterministic_and_decorrelated_per_path():
    entry = {
        "spread": {
            "n": 5,
            "over": {
                "base.volume": {"base": -12, "range": 6},
                "base.pointer.start": {"base": 0.1, "range": 0.5},
            },
        },
    }
    out_a = expand_spreads(_streams(v=entry))
    out_b = expand_spreads(_streams(v=entry))
    vols = [out_a[k]["base"]["volume"] for k in out_a]
    starts = [out_a[k]["base"]["pointer"]["start"] for k in out_a]
    # deterministico tra run
    assert vols == [out_b[k]["base"]["volume"] for k in out_b]
    # path diversi si decorrelano da soli (frazioni della banda diverse)
    frac_v = [(v + 12) / 6 for v in vols]
    frac_s = [(s - 0.1) / 0.5 for s in starts]
    assert frac_v != frac_s


def test_band_with_inner_n_owns_count():
    entry = {"spread": {"over": {"base.volume": {"base": -12, "range": 6, "n": 3}}}}
    out = expand_spreads(_streams(v=entry))
    assert list(out) == ["v_1", "v_2", "v_3"]


def test_band_without_n_anywhere_raises():
    entry = {"spread": {"over": {"base.volume": {"base": -12, "range": 6}}}}
    with pytest.raises(SpecError):
        expand_spreads(_streams(v=entry))


def test_ramp_full_paired_with_band():
    entry = {
        "spread": {
            "over": {
                "base.onset": {"ramp": {"start": 0, "stop": 4, "step": 2}},
                "base.volume": {"base": -12, "range": 6},
            },
        },
    }
    out = expand_spreads(_streams(v=entry))
    assert list(out) == ["v_1", "v_2", "v_3"]
    assert all("volume" in out[k]["base"] for k in out)


# --- patch: l'esplicito ritocca il generato ---------------------------------------

def test_patch_merges_on_top_and_is_consumed():
    streams = _streams(v=_spread_entry(), v_2={"base": {"volume": -20}})
    out = expand_spreads(streams)
    assert list(out) == ["v_1", "v_2", "v_3"]     # la patch non e' un quarto stream
    assert out["v_2"]["base"]["volume"] == -20
    assert out["v_2"]["base"]["pointer"]["start"] == 0.2   # strategy preservata
    assert "volume" not in out["v_1"]["base"]


def test_patch_wins_on_strategy_path():
    streams = _streams(v=_spread_entry(), v_2={"base": {"pointer": {"start": 0.99}}})
    out = expand_spreads(streams)
    assert out["v_2"]["base"]["pointer"]["start"] == 0.99
    assert out["v_1"]["base"]["pointer"]["start"] == 0.1


def test_patch_defined_before_spread_applies():
    streams = _streams(v_2={"base": {"volume": -20}}, v=_spread_entry())
    out = expand_spreads(streams)
    assert list(out) == ["v_1", "v_2", "v_3"]
    assert out["v_2"]["base"]["volume"] == -20


def test_patch_none_entry_is_noop():
    streams = _streams(v=_spread_entry(), v_2=None)
    out = expand_spreads(streams)
    assert list(out) == ["v_1", "v_2", "v_3"]
    assert out["v_2"]["base"]["pointer"]["start"] == 0.2


def test_patch_can_reactivate_sweep():
    streams = _streams(v=_spread_entry(), v_2={"sweep": {"orders": [1]}})
    out = expand_spreads(streams)
    assert out["v_2"]["sweep"]["orders"] == [1]
    assert out["v_1"]["sweep"] == {"orders": [], "orderings": []}


def test_patch_with_spread_raises():
    streams = _streams(
        v={"spread": {"n": 2, "over": {"base.onset": {"values": [0, 1]}}}},
        v_2={"spread": {"n": 2, "over": {"base.onset": {"values": [5, 6]}}}},
    )
    with pytest.raises(SpecError) as exc:
        expand_spreads(streams)
    assert "v_2" in str(exc.value)


# --- errori di schema ------------------------------------------------------------

def test_spread_without_over_raises():
    with pytest.raises(SpecError):
        expand_spreads(_streams(v={"spread": {"n": 3}}))


def test_spread_with_empty_over_raises():
    with pytest.raises(SpecError):
        expand_spreads(_streams(v={"spread": {"n": 3, "over": {}}}))


def test_spread_unknown_keys_raise():
    entry = {"spread": {"count": 3, "over": {"base.onset": {"values": [1]}}}}
    with pytest.raises(SpecError) as exc:
        expand_spreads(_streams(v=entry))
    assert "count" in str(exc.value)


def test_spread_not_a_dict_raises():
    with pytest.raises(SpecError):
        expand_spreads(_streams(v={"spread": 8}))


def test_over_entry_without_strategy_raises():
    entry = {"spread": {"n": 2, "over": {"base.onset": {}}}}
    with pytest.raises(SpecError):
        expand_spreads(_streams(v=entry))


def test_over_entry_with_two_strategies_raises():
    entry = {
        "spread": {
            "over": {"base.onset": {"values": [1, 2], "ramp": {"start": 0, "step": 1}}},
        },
    }
    with pytest.raises(SpecError):
        expand_spreads(_streams(v=entry))


# --- integrazione con resolve_streams ---------------------------------------------

def _doc():
    return {
        "study_id": "s",
        "base": {"onset": 0, "sample": "c.wav", "duration": 30},
        "axes": {"a": {"path": "density", "baseline": 20, "values": [5, 50]}},
        "streams": {
            "base": {},
            "v": {
                "spread": {
                    "n": 3,
                    "over": {"base.onset": {"ramp": {"start": 0, "step": 2}}},
                },
            },
        },
    }


def test_resolve_streams_expands_spread():
    specs = resolve_streams(_doc())
    assert [s.stream_id for s in specs] == ["base", "v_1", "v_2", "v_3"]
    onsets = [s.base["onset"] for s in specs[1:]]
    assert onsets == [0, 2, 4]


def test_resolve_streams_spread_has_sweep_off_by_default():
    specs = resolve_streams(_doc())
    by_id = {s.stream_id: s for s in specs}
    assert by_id["v_1"].orders == []
    assert by_id["v_1"].orderings == []
    # lo stream non-spread conserva il default (tutti gli ordini)
    assert by_id["base"].orders == [1]


def test_resolve_streams_applies_patch():
    doc = _doc()
    doc["streams"]["v_2"] = {"base": {"volume": -20}}
    specs = resolve_streams(doc)
    by_id = {s.stream_id: s for s in specs}
    assert len(specs) == 4
    assert by_id["v_2"].base["volume"] == -20
    assert by_id["v_2"].base["onset"] == 2


def test_generated_streams_have_decorrelated_seeds():
    specs = resolve_streams(_doc())
    by_id = {s.stream_id: s for s in specs}
    assert by_id["v_1"].resolved_y_seed() != by_id["v_2"].resolved_y_seed()


def test_spread_error_carries_line_and_stream():
    text = """\
study_id: s
base:
  onset: 0
axes:
  a: {path: density, baseline: 20, values: [5, 50]}
streams:
  v:
    spread:
      n: 3
      over:
        base.onset: {values: [1, 2]}
"""
    data, locs = yaml_loc.loads(text, source="study.yml")
    with pytest.raises(SpecError) as exc:
        resolve_streams(data, "s", locs=locs)
    assert exc.value.stream == "v"
    assert exc.value.source == "study.yml"
    assert exc.value.line == 8  # riga di streams.v.spread


# --- CLI: artefatto streams_expanded.yml (lo "yaml di aiuto") ----------------------

def _cli_study(tmp_path, monkeypatch, doc):
    import os

    import yaml as _yaml

    from granstudies import __main__ as cli

    sdir = tmp_path / "studies" / doc["study_id"]
    sdir.mkdir(parents=True)
    (sdir / "study.yml").write_text(_yaml.safe_dump(doc, sort_keys=False))
    monkeypatch.setattr(
        cli, "study_dir",
        lambda study: os.path.join(str(tmp_path), "studies", study),
    )
    monkeypatch.setattr(
        cli, "gen_dir",
        lambda study: os.path.join(str(tmp_path), "generated", study),
    )
    return cli, doc["study_id"], tmp_path / "generated" / doc["study_id"]


def _stack_doc():
    doc = _doc()
    doc["stack"] = {}
    doc["streams"]["v"]["spread"]["over"]["base.onset"] = {
        "ramp": {"start": 0, "step": 2},
    }
    return doc


def test_cmd_stack_writes_expanded_streams(tmp_path, monkeypatch):
    import yaml as _yaml

    cli, study, gdir = _cli_study(tmp_path, monkeypatch, _stack_doc())
    assert cli.cmd_stack(study) == 0
    artifact = gdir / "yaml" / "streams_expanded.yml"
    assert artifact.exists()
    expanded = _yaml.safe_load(artifact.read_text())
    assert list(expanded) == ["base", "v_1", "v_2", "v_3"]
    assert expanded["v_2"]["base"]["onset"] == 2
    assert all("spread" not in (e or {}) for e in expanded.values())


def test_cmd_stack_without_spread_writes_no_artifact(tmp_path, monkeypatch):
    doc = _stack_doc()
    doc["streams"] = {"base": {}}
    cli, study, gdir = _cli_study(tmp_path, monkeypatch, doc)
    assert cli.cmd_stack(study) == 0
    assert not (gdir / "yaml" / "streams_expanded.yml").exists()


def test_cmd_sweep_writes_expanded_streams(tmp_path, monkeypatch):
    doc = _stack_doc()
    doc["sweep"] = {"mode": "discrete"}
    doc["base"]["duration"] = 5
    cli, study, gdir = _cli_study(tmp_path, monkeypatch, doc)
    assert cli.cmd_sweep(study) == 0
    assert (gdir / "yaml" / "streams_expanded.yml").exists()


# --- strategy expr: aritmetica per-stream su i/n -----------------------------------

def _expr_entry(n=4):
    return {
        "spread": {
            "n": n,
            "over": {
                "axes.density.base": {
                    "expr": "env * a * (i + 1)",
                    "let": {"env": [[0, 1], [0.1583, 1.5]], "a": 50},
                },
            },
        },
    }


def test_expr_generates_scaled_envs():
    out = expand_spreads(_streams(v=_expr_entry()))
    assert list(out) == ["v_1", "v_2", "v_3", "v_4"]
    bases = [out[k]["axes"]["density"]["base"] for k in out]
    assert bases[0] == [[0, 50], [0.1583, 75]]
    assert bases[1] == [[0, 100], [0.1583, 150]]
    assert bases[3] == [[0, 200], [0.1583, 300]]


def test_expr_scalar_values():
    entry = {"spread": {"n": 3, "over": {"base.onset": {"expr": "10 * (i + 1)"}}}}
    out = expand_spreads(_streams(v=entry))
    assert [out[k]["base"]["onset"] for k in out] == [10, 20, 30]


def test_expr_i_and_n_in_scope():
    entry = {"spread": {"n": 5, "over": {"base.volume": {"expr": "-12 * i / (n - 1)"}}}}
    out = expand_spreads(_streams(v=entry))
    assert [out[k]["base"]["volume"] for k in out] == [0, -3, -6, -9, -12]


def test_expr_paired_with_sibling_that_owns_count():
    entry = {
        "spread": {
            "over": {
                "base.onset": {"values": [0, 5, 10]},
                "base.volume": {"expr": "-6 * i"},
            },
        },
    }
    out = expand_spreads(_streams(v=entry))
    assert list(out) == ["v_1", "v_2", "v_3"]
    assert [out[k]["base"]["volume"] for k in out] == [0, -6, -12]


def test_expr_n_1():
    entry = {"spread": {"n": 1, "over": {"base.onset": {"expr": "i"}}}}
    out = expand_spreads(_streams(v=entry))
    assert out["v_1"]["base"]["onset"] == 0


def test_expr_patch_still_applies():
    streams = _streams(v=_expr_entry(), v_2={"base": {"volume": -20}})
    out = expand_spreads(streams)
    assert list(out) == ["v_1", "v_2", "v_3", "v_4"]
    assert out["v_2"]["base"]["volume"] == -20
    assert out["v_2"]["axes"]["density"]["base"] == [[0, 100], [0.1583, 150]]


def test_expr_alone_without_n_raises():
    entry = {"spread": {"over": {"base.onset": {"expr": "i * 2"}}}}
    with pytest.raises(SpecError, match="derivabile"):
        expand_spreads(_streams(v=entry))


def test_expr_let_redefining_i_raises():
    entry = {
        "spread": {
            "n": 2,
            "over": {"base.onset": {"expr": "i * 2", "let": {"i": 3}}},
        },
    }
    with pytest.raises(SpecError, match="riservat"):
        expand_spreads(_streams(v=entry))


def test_expr_plus_values_marker_raises():
    entry = {
        "spread": {
            "over": {"base.onset": {"expr": "i", "values": [1, 2]}},
        },
    }
    with pytest.raises(SpecError):
        expand_spreads(_streams(v=entry))


def test_expr_eval_error_carries_stream_and_line():
    text = """\
study_id: s
base:
  onset: 0
axes:
  a: {path: density, baseline: 20, values: [5, 50]}
streams:
  v:
    spread:
      n: 2
      over:
        base.onset: {expr: "boh * 2"}
"""
    data, locs = yaml_loc.loads(text, source="study.yml")
    with pytest.raises(SpecError) as exc:
        resolve_streams(data, "s", locs=locs)
    assert exc.value.stream == "v"
    assert exc.value.source == "study.yml"
    assert "boh" in str(exc.value)


def test_expr_functions_and_modulo_in_spread():
    # griglia 3x2 dagli operatori interi: colonna = i % 3, riga = i // 3
    entry = {
        "spread": {
            "n": 6,
            "over": {"base.onset": {"expr": "4 * (i % 3) + 10 * (i // 3)"}},
        },
    }
    out = expand_spreads(_streams(v=entry))
    assert [out[k]["base"]["onset"] for k in out] == [0, 4, 8, 10, 14, 18]


def test_expr_clamp_with_min_on_band_let():
    # clamp di un pescaggio: volume mai sotto -10
    entry = {
        "spread": {
            "n": 8,
            "over": {
                "base.volume": {
                    "expr": "max(v - 2 * i, 0 - 10)",
                    "let": {"v": {"base": -3, "range": 3}},
                },
            },
        },
    }
    out = expand_spreads(_streams(v=entry))
    vols = [out[k]["base"]["volume"] for k in out]
    assert all(v >= -10 for v in vols)
    assert vols[-1] == -10  # a i=7 il pescaggio meno 14 sta sempre sotto il clamp


# --- strategy expr: banda-let (un pescaggio per stream generato) -------------------

def _rand_let_entry(n=6, **band_spec):
    spec = {"base": -12, "range": 6}
    spec.update(band_spec)
    return {
        "spread": {
            "n": n,
            "over": {"base.volume": {"expr": "v", "let": {"v": spec}}},
        },
    }


def test_expr_let_band_draws_one_value_per_stream():
    out = expand_spreads(_streams(v=_rand_let_entry()))
    vols = [out[k]["base"]["volume"] for k in out]
    assert len(vols) == 6
    assert all(-12 <= x <= -6 for x in vols)
    assert len(set(vols)) > 1  # pescaggi, non una costante


def test_expr_let_band_deterministic_between_runs():
    a = expand_spreads(_streams(v=_rand_let_entry()))
    b = expand_spreads(_streams(v=_rand_let_entry()))
    assert [a[k]["base"]["volume"] for k in a] == [b[k]["base"]["volume"] for k in b]


def test_expr_let_band_explicit_seed_matches_band_generator():
    from granstudies.value_generators import band

    out = expand_spreads(_streams(v=_rand_let_entry(n=4, seed=42)))
    assert [out[k]["base"]["volume"] for k in out] == band(
        n=4, base=-12, range=6, seed=42
    )


def test_expr_let_band_enters_arithmetic_with_static_let():
    from granstudies.value_generators import band

    entry = {
        "spread": {
            "n": 4,
            "over": {
                "base.volume": {
                    "expr": "a + v * 2",
                    "let": {"a": -6, "v": {"base": 0, "range": 1, "seed": 7}},
                },
            },
        },
    }
    out = expand_spreads(_streams(v=entry))
    draws = band(n=4, base=0, range=1, seed=7)
    assert [out[k]["base"]["volume"] for k in out] == [
        round(-6 + d * 2, 9) for d in draws
    ]


def test_expr_let_band_scales_env_per_stream():
    from granstudies.value_generators import band

    entry = {
        "spread": {
            "n": 3,
            "over": {
                "axes.density.base": {
                    "expr": "env * v",
                    "let": {
                        "env": [[0, 1], [1, 2]],
                        "v": {"base": 10, "range": 5, "seed": 1},
                    },
                },
            },
        },
    }
    out = expand_spreads(_streams(v=entry))
    draws = band(n=3, base=10, range=5, seed=1)
    bases = [out[k]["axes"]["density"]["base"] for k in out]
    assert bases == [[[0, d], [1, round(2 * d, 9)]] for d in draws]


def test_expr_let_band_vars_decorrelate_by_default():
    entry = {
        "spread": {
            "n": 5,
            "over": {
                "base.volume": {
                    "expr": "a - b",
                    "let": {"a": {"base": 0, "range": 1}, "b": {"base": 0, "range": 1}},
                },
            },
        },
    }
    out = expand_spreads(_streams(v=entry))
    diffs = [out[k]["base"]["volume"] for k in out]
    assert any(d != 0 for d in diffs)


def test_expr_let_band_env_base_slides_over_population():
    # range omesso -> banda collassata: i pescaggi seguono l'Env di base
    # deterministicamente, frac = i/(n-1) sulla popolazione.
    entry = {
        "spread": {
            "n": 5,
            "over": {"base.onset": {"expr": "v", "let": {"v": {"base": [0, 10]}}}},
        },
    }
    out = expand_spreads(_streams(v=entry))
    assert [out[k]["base"]["onset"] for k in out] == [0, 2.5, 5, 7.5, 10]


def test_expr_let_band_distribution_and_drift():
    a = expand_spreads(
        _streams(v=_rand_let_entry(distribution="gaussian", drift={"step": 0.2}))
    )
    b = expand_spreads(
        _streams(v=_rand_let_entry(distribution="gaussian", drift={"step": 0.2}))
    )
    vols = [a[k]["base"]["volume"] for k in a]
    assert [b[k]["base"]["volume"] for k in b] == vols
    assert all(-12 <= x <= -6 for x in vols)


def test_expr_let_band_with_n_raises():
    entry = {
        "spread": {
            "n": 3,
            "over": {
                "base.onset": {"expr": "v", "let": {"v": {"base": 0, "range": 1, "n": 3}}},
            },
        },
    }
    with pytest.raises(SpecError, match="conteggio"):
        expand_spreads(_streams(v=entry))


def test_expr_let_values_node_raises():
    entry = {
        "spread": {
            "n": 2,
            "over": {"base.onset": {"expr": "v", "let": {"v": {"values": [1, 2]}}}},
        },
    }
    with pytest.raises(SpecError, match="banda"):
        expand_spreads(_streams(v=entry))


def test_expr_let_ramp_node_raises():
    entry = {
        "spread": {
            "n": 2,
            "over": {
                "base.onset": {"expr": "v", "let": {"v": {"ramp": {"start": 0, "step": 1}}}},
            },
        },
    }
    with pytest.raises(SpecError, match="banda"):
        expand_spreads(_streams(v=entry))


def test_expr_let_band_unknown_key_raises():
    entry = {
        "spread": {
            "n": 2,
            "over": {"base.onset": {"expr": "v", "let": {"v": {"base": 0, "foo": 1}}}},
        },
    }
    with pytest.raises(SpecError, match="foo"):
        expand_spreads(_streams(v=entry))


def test_expr_let_band_on_reserved_name_raises():
    entry = {
        "spread": {
            "n": 2,
            "over": {"base.onset": {"expr": "i * 2", "let": {"i": {"base": 0, "range": 1}}}},
        },
    }
    with pytest.raises(SpecError, match="riservat"):
        expand_spreads(_streams(v=entry))


def test_expr_resolve_streams_end_to_end():
    doc = _doc()
    # asse a banda: base scalare di default, rimpiazzata per-stream dall'expr
    doc["axes"]["a"] = {"path": "density", "baseline": 20,
                        "base": 5, "range": 0, "n": 2}
    doc["streams"]["v"] = {
        "spread": {
            "n": 2,
            "over": {
                "axes.a.base": {
                    "expr": "env * a * (i + 1)",
                    "let": {"env": [[0, 1], [0.1583, 1.5]], "a": 50},
                },
            },
        },
    }
    specs = resolve_streams(doc)
    by_id = {s.stream_id: s for s in specs}
    (axis,) = by_id["v_2"].axes
    # banda collassata (range 0) sull'Env valutato: frac 0 -> 100, frac 1 -> 150
    assert axis.values == [100.0, 150.0]


# --- strategy expr: expr annidati dentro let (issue #28) ---------------------------

def test_expr_nested_let_sees_spread_index():
    entry = {
        "spread": {
            "n": 3,
            "over": {
                "base.onset": {"expr": "g * 2", "let": {"g": {"expr": "i + 1"}}},
            },
        },
    }
    out = expand_spreads(_streams(v=entry))
    assert [out[k]["base"]["onset"] for k in out] == [2, 4, 6]


def test_expr_nested_let_coexists_with_band_let():
    from granstudies.value_generators import band

    entry = {
        "spread": {
            "n": 3,
            "over": {
                "base.volume": {
                    "expr": "v + g",
                    "let": {
                        "v": {"base": 0, "range": 1, "seed": 7},
                        "g": {"expr": "i * 10"},
                    },
                },
            },
        },
    }
    out = expand_spreads(_streams(v=entry))
    draws = band(n=3, base=0, range=1, seed=7)
    assert [out[k]["base"]["volume"] for k in out] == [
        round(d + i * 10, 9) for i, d in enumerate(draws)
    ]


def test_expr_nested_let_references_band_let_var():
    from granstudies.value_generators import band

    entry = {
        "spread": {
            "n": 3,
            "over": {
                "base.volume": {
                    "expr": "g",
                    "let": {
                        "v": {"base": 0, "range": 1, "seed": 7},
                        "g": {"expr": "v * 2"},
                    },
                },
            },
        },
    }
    out = expand_spreads(_streams(v=entry))
    draws = band(n=3, base=0, range=1, seed=7)
    assert [out[k]["base"]["volume"] for k in out] == [round(d * 2, 9) for d in draws]


def test_expr_nested_let_cycle_carries_stream_context():
    entry = {
        "spread": {
            "n": 2,
            "over": {
                "base.onset": {
                    "expr": "a",
                    "let": {"a": {"expr": "b"}, "b": {"expr": "a"}},
                },
            },
        },
    }
    with pytest.raises(SpecError) as exc:
        expand_spreads(_streams(v=entry))
    assert "ciclo" in str(exc.value)


# --- n come nodo-expr (percorso-v1, fase 4) --------------------------------------

def test_n_expr_node_evaluated():
    entry = {
        "spread": {
            "n": {"expr": "1 + 2"},
            "over": {"base.volume": {"expr": "0 - i", "let": {}}},
        },
    }
    out = expand_spreads(_streams(v=entry))
    assert list(out) == ["v_1", "v_2", "v_3"]


def test_n_expr_with_let_default():
    # il default nel let tiene lo studio valido senza percorso; l'iniezione
    # lo ombreggia (floor(2 + 8 * w) con w=0 -> 2)
    entry = {
        "spread": {
            "n": {"expr": "floor(2 + 8 * w)", "let": {"w": 0}},
            "over": {"base.volume": {"expr": "0 - i"}},
        },
    }
    out = expand_spreads(_streams(v=entry))
    assert list(out) == ["v_1", "v_2"]


def test_n_expr_non_integral_errors():
    entry = {
        "spread": {
            "n": {"expr": "2.5"},
            "over": {"base.volume": {"expr": "0 - i"}},
        },
    }
    with pytest.raises(SpecError, match="inter"):
        expand_spreads(_streams(v=entry))


def test_n_expr_below_one_errors():
    entry = {
        "spread": {
            "n": {"expr": "0"},
            "over": {"base.volume": {"expr": "0 - i"}},
        },
    }
    with pytest.raises(SpecError, match="inter"):
        expand_spreads(_streams(v=entry))


def test_n_expr_discordant_with_values_errors():
    entry = {
        "spread": {
            "n": {"expr": "4"},
            "over": {"base.volume": {"values": [-1, -2, -3]}},
        },
    }
    with pytest.raises(SpecError, match="discord"):
        expand_spreads(_streams(v=entry))


# --- padding stabile con n dinamico (percorso-v1, fase 4) --------------------------

def test_pad_n_stabilizes_name_width():
    entry = {
        "spread": {
            "n": 3,
            "over": {"base.volume": {"expr": "0 - i"}},
        },
    }
    out = expand_spreads(_streams(coro=entry), pad_n={"coro": 12})
    # larghezza del massimo n del percorso: la stessa voce logica ha lo
    # stesso nome ovunque esista
    assert list(out) == ["coro_01", "coro_02", "coro_03"]


def test_pad_n_patch_within_range_applies():
    entry = {
        "spread": {
            "n": 3,
            "over": {"base.volume": {"expr": "0 - i"}},
        },
    }
    streams = _streams(coro=entry, coro_02={"base": {"volume": -90}})
    out = expand_spreads(streams, pad_n={"coro": 12})
    assert out["coro_02"]["base"]["volume"] == -90


def test_pad_n_patch_out_of_range_consumed_silently():
    # la voce coro_09 non esiste in questa istanza (n=3, pad su 12): la patch
    # non deve diventare uno stream ordinario
    entry = {
        "spread": {
            "n": 3,
            "over": {"base.volume": {"expr": "0 - i"}},
        },
    }
    streams = _streams(coro=entry, coro_09={"base": {"volume": -90}})
    out = expand_spreads(streams, pad_n={"coro": 12})
    assert "coro_09" not in out
    assert list(out) == ["coro_01", "coro_02", "coro_03"]


def test_without_pad_n_out_of_range_entry_stays_ordinary():
    # comportamento storico invariato fuori dal percorso
    entry = {
        "spread": {
            "n": 3,
            "over": {"base.volume": {"expr": "0 - i"}},
        },
    }
    streams = _streams(v=entry, v_9={"base": {"volume": -90}})
    out = expand_spreads(streams)
    assert "v_9" in out


# --- blocco globale spread:, eredita' per-stream (issue #34) -----------------------

_GLOBAL = {"over": {"base.pointer.start.values": [0.1, 0.25, 0.4]}}


def test_global_empty_dict_inherits_whole_block():
    out = expand_spreads(_streams(z={"spread": {}}), global_spread=_GLOBAL)
    assert list(out) == ["z_1", "z_2", "z_3"]
    assert [out[k]["base"]["pointer"]["start"] for k in out] == [0.1, 0.25, 0.4]


def test_global_null_spread_value_inherits_like_empty_dict():
    # ``spread:`` senza valore (None in YAML) equivale a ``spread: {}``,
    # come gia' per ``sweep:``.
    out = expand_spreads(_streams(z={"spread": None}), global_spread=_GLOBAL)
    assert list(out) == ["z_1", "z_2", "z_3"]


def test_global_partial_override_replaces_leaf():
    # deep merge come per sweep: la chiave dello stream rimpiazza la foglia
    # globale (le liste rimpiazzano)
    entry = {"spread": {"over": {"base.pointer.start.values": [0.9, 1.0]}}}
    out = expand_spreads(_streams(z=entry), global_spread=_GLOBAL)
    assert list(out) == ["z_1", "z_2"]
    assert [out[k]["base"]["pointer"]["start"] for k in out] == [0.9, 1.0]


def test_global_partial_override_merges_sibling_paths():
    # un path nuovo nello stream si aggiunge a quello globale (deep merge di over)
    entry = {"spread": {"over": {"base.volume.values": [-6, -3, 0]}}}
    out = expand_spreads(_streams(z=entry), global_spread=_GLOBAL)
    assert [out[k]["base"]["pointer"]["start"] for k in out] == [0.1, 0.25, 0.4]
    assert [out[k]["base"]["volume"] for k in out] == [-6, -3, 0]


def test_global_may_be_partial_and_completed_per_stream():
    # il globale porta solo n; la strategy vive nello stream (la validazione
    # e' post-merge, per-entry)
    entry = {"spread": {"over": {"base.onset": {"ramp": {"start": 0, "step": 2}}}}}
    out = expand_spreads(_streams(z=entry), global_spread={"n": 3})
    assert [out[k]["base"]["onset"] for k in out] == [0, 2, 4]


def test_stream_n_completes_global_band():
    g = {"over": {"base.volume": {"base": -12, "range": 6}}}
    out = expand_spreads(_streams(z={"spread": {"n": 3}}), global_spread=g)
    assert list(out) == ["z_1", "z_2", "z_3"]
    assert all(-12 <= out[k]["base"]["volume"] <= -6 for k in out)


def test_global_present_stream_without_key_not_expanded():
    # attivazione esplicita, come sweep: senza chiave 'spread' niente cugini
    out = expand_spreads(
        _streams(z={"sweep": {}}, w={"base": {"volume": -6}}), global_spread=_GLOBAL
    )
    assert list(out) == ["z", "w"]
    assert "spread" not in out["z"]


def test_global_patch_still_applies():
    streams = _streams(z={"spread": {}}, z_2={"base": {"volume": -20}})
    out = expand_spreads(streams, global_spread=_GLOBAL)
    assert list(out) == ["z_1", "z_2", "z_3"]
    assert out["z_2"]["base"]["volume"] == -20
    assert out["z_2"]["base"]["pointer"]["start"] == 0.25


def test_no_global_empty_spread_still_raises():
    # senza blocco globale ``spread: {}`` resta l'errore di sempre
    with pytest.raises(SpecError, match="over"):
        expand_spreads(_streams(z={"spread": {}}))


def test_global_not_a_dict_raises():
    with pytest.raises(SpecError, match="globale"):
        expand_spreads(_streams(z={"spread": {}}), global_spread=[0.1, 0.25])


def test_global_with_non_dict_entry_spread_keeps_schema_error():
    # il valore-spread non-dict della entry non viene fuso: l'errore di
    # schema resta quello storico, col contesto dello stream
    with pytest.raises(SpecError) as exc:
        expand_spreads(_streams(z={"spread": 8}), global_spread=_GLOBAL)
    assert exc.value.stream == "z"


def test_global_inherited_error_carries_stream():
    # blocco ereditato invalido (n senza over): l'errore appartiene alla entry
    with pytest.raises(SpecError) as exc:
        expand_spreads(_streams(z={"spread": {}}), global_spread={"n": 3})
    assert exc.value.stream == "z"


def test_spread_counts_with_global():
    counts = spread_counts(
        _streams(z={"spread": {}}, solo={}), global_spread=_GLOBAL
    )
    assert counts == {"z": 3}


def _global_doc():
    return {
        "study_id": "s",
        "base": {"onset": 0, "sample": "c.wav", "duration": 30},
        "axes": {"a": {"path": "density", "baseline": 20, "values": [5, 50]}},
        "spread": {"over": {"base.pointer.start.values": [0.1, 0.25, 0.4]}},
        "streams": {
            "solo": {},
            "z": {"sweep": {}, "spread": {}},
        },
    }


def test_resolve_streams_inherits_global_spread():
    specs = resolve_streams(_global_doc())
    assert [s.stream_id for s in specs] == ["solo", "z_1", "z_2", "z_3"]
    by_id = {s.stream_id: s for s in specs}
    assert by_id["z_2"].base["pointer"]["start"] == 0.25
    # lo stream senza chiave spread resta singolo, senza espansione
    assert "pointer" not in by_id["solo"].base


def test_resolve_streams_global_spread_partial_override():
    doc = _global_doc()
    doc["streams"]["z"] = {"spread": {"over": {"base.pointer.start.values": [0.9]}}}
    specs = resolve_streams(doc)
    assert [s.stream_id for s in specs] == ["solo", "z_1"]
    assert specs[1].base["pointer"]["start"] == 0.9


def test_no_global_brano01_v2_shape_unchanged():
    # Retrocompatibilita': la sagoma di brano01_v2 — spread per-stream con
    # expr/let e patch omonime, NESSUN blocco globale — resta identica.
    streams = _streams(
        fermo={},
        dens_1={"base": {"pan": -50}},
        dens={
            "spread": {
                "n": 4,
                "over": {
                    "axes.density.base": {
                        "expr": "env + v * (i + 1)",
                        "let": {"env": [[0, 0], [0.1583, 0.5]], "v": 50},
                    },
                    "base.pan": {"expr": "i * a", "let": {"a": -20}},
                },
            },
        },
    )
    out = expand_spreads(streams)
    assert list(out) == ["fermo", "dens_1", "dens_2", "dens_3", "dens_4"]
    assert "spread" not in out["fermo"] and "axes" not in out["fermo"]
    assert out["dens_1"]["base"]["pan"] == -50      # patch vince sulla strategy
    assert out["dens_2"]["base"]["pan"] == -20
    assert out["dens_3"]["axes"]["density"]["base"] == [[0, 150], [0.1583, 150.5]]


def test_cmd_stack_expanded_artifact_with_global_spread(tmp_path, monkeypatch):
    # lo "yaml di aiuto" eredita il blocco globale come resolve_streams
    import yaml as _yaml

    doc = _doc()
    doc["stack"] = {}
    doc["spread"] = doc["streams"]["v"].pop("spread")
    doc["streams"]["v"] = {"spread": {}}
    cli, study, gdir = _cli_study(tmp_path, monkeypatch, doc)
    assert cli.cmd_stack(study) == 0
    artifact = gdir / "yaml" / "streams_expanded.yml"
    assert artifact.exists()
    expanded = _yaml.safe_load(artifact.read_text())
    assert list(expanded) == ["base", "v_1", "v_2", "v_3"]
    assert expanded["v_2"]["base"]["onset"] == 2
    assert all("spread" not in (e or {}) for e in expanded.values())


# --- n come envelope: il coro cresce/decresce nel tempo ---------------------


def _n_env_doc(n_spec):
    return {
        "base": {"sample": "s.wav", "time_mode": "normalized", "volume": 24},
        "axes": {"density": {"baseline": 10}},
        "streams": {
            "cugini": {
                "spread": {
                    "n": n_spec,
                    "over": {"base.pointer.start": {"ramp": {"start": 0.1, "step": 0.1}}},
                }
            }
        },
    }


def _gates(n_spec):
    from granstudies.spread import expand_spreads

    doc = _n_env_doc(n_spec)
    out = expand_spreads(doc["streams"], base_volume=doc["base"]["volume"])
    return {name: e["base"]["volume"] for name, e in out.items()}


def test_n_envelope_genera_il_picco_di_voci():
    gates = _gates([[0, 1], [1, 4]])
    assert list(gates) == ["cugini_1", "cugini_2", "cugini_3", "cugini_4"]


def test_n_envelope_step_accende_di_scatto():
    # La voce 2 e' spenta finche' n(t) non la supera, poi va piena: due soli
    # livelli, nessuna rampa.
    gate = _gates({"type": "step", "points": [[0, 1], [0.5, 2]]})["cugini_2"]
    assert gate["type"] == "step"
    assert [v for _, v in gate["points"]] == [-120.0, 24.0]
    assert gate["points"][1][0] == pytest.approx(0.5, abs=0.01)


def test_n_envelope_rampa_fa_entrare_sfumando():
    gate = _gates([[0, 1], [1, 2]])["cugini_2"]
    livelli = [v for _, v in gate["points"]]
    assert livelli[0] == -120.0 and livelli[-1] == 24.0
    # sfumatura, non gradino: molti livelli intermedi, monotoni crescenti
    assert len(livelli) > 10
    assert livelli[1:] == sorted(livelli[1:])


def test_n_envelope_con_volume_envelope_e_errore():
    from granstudies.spread import expand_spreads

    doc = _n_env_doc([[0, 1], [1, 2]])
    with pytest.raises(SpecError, match="sovrascriverebbero"):
        expand_spreads(doc["streams"], base_volume=[[0, 0], [1, 24]])


def test_n_envelope_confligge_con_over_base_volume():
    from granstudies.spread import expand_spreads

    doc = _n_env_doc([[0, 1], [1, 2]])
    doc["streams"]["cugini"]["spread"]["over"]["base.volume"] = {"values": [0, 24]}
    with pytest.raises(SpecError, match="entrambi il volume"):
        expand_spreads(doc["streams"], base_volume=24)


# --- spread_pad: il massimo n per entry su piu' documenti (issue #39) --------------
# Il padding stabile serve a ogni processo che ripete lo stesso documento con
# ``spread.n`` mosso da una variabile: il percorso sulle istanze, versions sulle
# versioni. ``spread_pad`` e' il gemello di ``spread_counts`` sul *documento*:
# applica la stessa pre-pass di ``resolve_streams`` prima di contare.

def _pad_doc(n, **extra):
    entry = {"spread": {"n": n, "over": {"base.volume": {"expr": "0 - i"}}}}
    entry.update(extra)
    return {"streams": {"coro": entry}}


def test_spread_pad_takes_max_across_documents():
    from granstudies.spread import spread_pad

    docs = [_pad_doc(2), _pad_doc(11), _pad_doc(7)]
    assert spread_pad(docs) == {"coro": 11}


def test_spread_pad_ignores_non_spread_entries():
    from granstudies.spread import spread_pad

    docs = [{"streams": {"solo": {"base": {"volume": -6}}}}]
    assert spread_pad(docs) == {}


def test_spread_pad_reads_global_spread_block():
    from granstudies.spread import spread_pad

    # il conteggio va risolto sul blocco gia' ereditato dal globale
    docs = [{"spread": _GLOBAL, "streams": {"z": {"spread": {}}}}]
    assert spread_pad(docs) == {"z": 3}


def test_spread_pad_applies_group_let_before_counting():
    from granstudies.spread import spread_pad

    # ``spread.n`` alimentato da una manopola di gruppo: senza la pre-pass di
    # ``apply_group_let`` il conteggio leggerebbe il default del let locale
    # (1) invece del valore di gruppo (5), e il pad uscirebbe troppo stretto.
    doc = _pad_doc({"expr": "q", "let": {"q": 1}}, let={"q": 5})
    assert spread_pad([doc]) == {"coro": 5}
    # ed e' davvero il conteggio che expand_spreads produce
    assert len(expand_spreads(apply_group_let(doc["streams"]))) == 5
