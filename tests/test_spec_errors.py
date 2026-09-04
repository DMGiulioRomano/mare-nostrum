"""SpecError: gli errori di study.yml portano stream, asse, chiave e riga."""
import pytest

from granstudies.errors import SpecError
from granstudies.study_spec import parse_study_spec, resolve_streams
from granstudies.yaml_loc import loads


BASE_TEXT = """\
study_id: s
base:
  onset: 0
  duration: 10
axes:
  density:
    path: density
    baseline: 20
    base: 4
    range: 8
stack: {}
"""


def test_spec_error_is_value_error():
    assert issubclass(SpecError, ValueError)


def test_band_without_n_no_stream():
    data, locs = loads(BASE_TEXT, source="study.yml")
    with pytest.raises(SpecError) as exc:
        parse_study_spec(data, "s", locs=locs)
    e = exc.value
    assert e.axis == "density"
    assert e.key == ("axes", "density")
    assert e.stream is None
    assert e.line == 6          # riga di axes.density
    assert e.source == "study.yml"
    assert e.hint                # rimedio presente
    assert "banda senza 'n'" in e.msg


def test_error_in_stream_carries_stream_and_base_line():
    text = BASE_TEXT + """\
streams:
  rotta: {}
"""
    data, locs = loads(text, source="study.yml")
    with pytest.raises(SpecError) as exc:
        resolve_streams(data, "s", locs=locs)
    e = exc.value
    assert e.stream == "rotta"
    assert e.axis == "density"
    assert e.line == 6          # la chiave vive nel base, non nell'override


def test_error_in_override_points_at_override_line():
    text = BASE_TEXT + """\
streams:
  conflitto:
    axes:
      density: {n: 6}
    stack:
      density: {base: 2}
"""
    data, locs = loads(text, source="study.yml")
    with pytest.raises(SpecError) as exc:
        resolve_streams(data, "s", locs=locs)
    e = exc.value
    assert e.stream == "conflitto"
    assert e.key == ("stack", "density")
    assert e.line == 17         # streams.conflitto.stack.density
    assert "possiede n" in e.msg


def test_deep_value_error_wrapped_with_axis_context():
    text = """\
study_id: s
base: {onset: 0}
axes:
  a:
    path: density
    baseline: 20
    ramp: {start: 5, stop: 50, step: 0}
"""
    data, locs = loads(text, source="study.yml")
    with pytest.raises(SpecError) as exc:
        parse_study_spec(data, "s", locs=locs)
    e = exc.value
    assert e.axis == "a"
    assert e.key == ("axes", "a")
    assert e.line == 4
    assert "step" in e.msg


def test_missing_path_derives_from_axis_key():
    data, locs = loads("study_id: s\nbase: {}\naxes:\n  a: {baseline: 20, values: [1]}\n")
    spec = parse_study_spec(data, "s", locs=locs)
    assert spec.axis("a").path == "a"


def test_parse_without_locs_still_works():
    data, _ = loads(BASE_TEXT)
    with pytest.raises(SpecError) as exc:
        parse_study_spec(data, "s")
    e = exc.value
    assert e.line is None
    assert e.axis == "density"


def test_str_keeps_message_for_match():
    """Retrocompatibilita': str(e) contiene il messaggio originale."""
    data, locs = loads(BASE_TEXT, source="study.yml")
    with pytest.raises(ValueError, match="banda senza 'n'"):
        parse_study_spec(data, "s", locs=locs)


RAMP_INCOMPLETE_TEXT = """\
study_id: s
base:
  onset: 0
  duration: 10
axes:
  density:
    path: density
    baseline: 20
    ramp: {step: 1}
sweep:
  orders: [1]
"""


def test_ramp_incomplete_is_spec_error_not_typeerror():
    # ramp senza start/stop: prima usciva un TypeError grezzo da ramp(**params).
    data, locs = loads(RAMP_INCOMPLETE_TEXT, source="study.yml")
    with pytest.raises(SpecError) as exc:
        parse_study_spec(data, "s", locs=locs)
    e = exc.value
    assert e.axis == "density"
    assert e.key == ("axes", "density")
    assert e.line == 6          # riga di axes.density
    assert e.source == "study.yml"
    assert e.hint               # rimedio presente
    assert "ramp" in e.msg
    assert "start" in e.msg and "stop" in e.msg


# --- issue #37: nodo-expr fuori sede / interpolation non validata ----------------
# Slot strutturali (baseline, values, gain_compensation.alpha) e un valore
# inventato di interpolation devono uscire come SpecError col path, non come
# TypeError grezzo o (per interpolation) senza alcun errore.

def _base_axis(**over):
    ax = {"path": "density", "baseline": 10, "values": [1, 2, 3]}
    ax.update(over)
    return {
        "study_id": "s",
        "base": {"sample": "x.wav"},
        "axes": {"density": ax},
        "sweep": {"orders": [1]},
    }


def test_baseline_expr_node_is_spec_error_not_typeerror():
    data = _base_axis(baseline={"expr": "10"}, values=None)
    del data["axes"]["density"]["values"]
    data["axes"]["density"].update({"base": 5, "range": 1, "n": 3})
    with pytest.raises(SpecError) as exc:
        parse_study_spec(data, "s")
    e = exc.value
    assert e.axis == "density"
    assert e.key == ("axes", "density", "baseline")
    assert "nodo-expr" in e.msg
    assert e.hint


def test_values_element_expr_node_is_spec_error_not_typeerror():
    data = _base_axis(values=[1, {"expr": "2"}, 3])
    with pytest.raises(SpecError) as exc:
        parse_study_spec(data, "s")
    e = exc.value
    assert e.axis == "density"
    assert e.key == ("axes", "density", "values")
    assert "nodo-expr" in e.msg


@pytest.mark.parametrize("bad", ["dieci", [1], None, True])
def test_baseline_non_numero_is_spec_error_not_typeerror(bad):
    # Il nodo-expr non e' l'unico non-numero che finiva nel confronto bounds:
    # stringa, lista, null e bool esplodevano allo stesso modo, senza path.
    data = _base_axis(baseline=bad)
    with pytest.raises(SpecError) as exc:
        parse_study_spec(data, "s")
    assert exc.value.key == ("axes", "density", "baseline")


@pytest.mark.parametrize("bad", ["due", [2], None, True])
def test_values_element_non_numero_is_spec_error_not_typeerror(bad):
    data = _base_axis(values=[1, bad, 3])
    with pytest.raises(SpecError) as exc:
        parse_study_spec(data, "s")
    assert exc.value.key == ("axes", "density", "values")


def test_gain_compensation_alpha_expr_node_is_spec_error_not_typeerror():
    data = _base_axis()
    data["gain_compensation"] = {"alpha": {"expr": "0.7"}, "max_shift": 12}
    with pytest.raises(SpecError) as exc:
        parse_study_spec(data, "s")
    e = exc.value
    assert e.key == ("gain_compensation",)
    assert "alpha" in e.msg


def test_interpolation_unknown_value_rejected_on_axis():
    data = _base_axis(interpolation="banana")
    with pytest.raises(SpecError) as exc:
        parse_study_spec(data, "s")
    e = exc.value
    assert e.axis == "density"
    assert e.key == ("axes", "density", "interpolation")
    assert "banana" in e.msg
    assert "linear" in e.hint and "step" in e.hint


def test_interpolation_unknown_value_rejected_at_study_level():
    data = _base_axis()
    data["axes"]["interpolation"] = "banana"
    with pytest.raises(SpecError) as exc:
        parse_study_spec(data, "s")
    e = exc.value
    assert e.key == ("axes", "interpolation")
    assert "banana" in e.msg


def test_interpolation_step_is_accepted():
    # 'step' e' nel vocabolario unico (linear | cubic | step): non deve fallire.
    spec = parse_study_spec(_base_axis(interpolation="step"), "s")
    assert spec.axis("density").interpolation == "step"
