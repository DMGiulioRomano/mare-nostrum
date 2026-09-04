"""Loader YAML con posizioni: tabella {key-path -> riga} e lookup override-first."""
import yaml

from granstudies.yaml_loc import loads


TEXT = """\
study_id: s
duration: 10
axes:
  density:
    path: density
    baseline: 20
    base: 4
    range: 8
stack: {}
streams:
  lineare:
    axes:
      density:
        n: 6
  camminata:
    stack:
      density:
        base: [2, 5]
"""


def test_loads_same_data_as_safe_load():
    data, _ = loads(TEXT)
    assert data == yaml.safe_load(TEXT)


def test_key_lines_nested():
    _, locs = loads(TEXT)
    assert locs.lookup(("study_id",)) == 1
    assert locs.lookup(("axes",)) == 3
    assert locs.lookup(("axes", "density")) == 4
    assert locs.lookup(("axes", "density", "base")) == 7
    assert locs.lookup(("streams", "camminata", "stack", "density", "base")) == 18


def test_sequence_items():
    text = "values:\n  - 1\n  - 2\n"
    _, locs = loads(text)
    assert locs.lookup(("values", 0)) == 2
    assert locs.lookup(("values", 1)) == 3


def test_lookup_unknown_path_is_none():
    _, locs = loads(TEXT)
    assert locs.lookup(("axes", "density", "n")) is None


def test_lookup_stream_override_first():
    _, locs = loads(TEXT)
    # La stream 'lineare' definisce n: vince l'override.
    assert locs.lookup(("axes", "density", "n"), stream="lineare") == 14
    # Chiave solo nel base: si ricade sul base.
    assert locs.lookup(("axes", "density", "base"), stream="lineare") == 7
    # Override di un'altra stream: per 'camminata' n non esiste da nessuna parte.
    assert locs.lookup(("axes", "density", "n"), stream="camminata") is None


def test_source_travels():
    _, locs = loads(TEXT, source="studies/s/study.yml")
    assert locs.source == "studies/s/study.yml"
