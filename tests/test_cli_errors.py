"""Handler CLI: niente traceback, blocco leggibile su stderr, exit code 2."""
import os

import pytest
import yaml

from granstudies import __main__ as cli
from granstudies.errors import SpecError


BROKEN = """\
study_id: s_err
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
streams:
  rotta: {}
"""


def _write_study(tmp_path, monkeypatch, text, study="s_err"):
    sdir = tmp_path / "studies" / study
    sdir.mkdir(parents=True)
    (sdir / "study.yml").write_text(text)
    monkeypatch.setattr(cli, "study_dir", lambda s: os.path.join(str(tmp_path), "studies", s))
    monkeypatch.delenv("GRANSTUDIES_DEBUG", raising=False)
    return study


def test_spec_error_formatted_no_traceback(tmp_path, monkeypatch, capsys):
    study = _write_study(tmp_path, monkeypatch, BROKEN)
    rc = cli.main(["render", study])
    assert rc == 2
    err = capsys.readouterr().err
    assert "Traceback" not in err
    assert "posizione:" in err
    assert "study.yml:6" in err          # axes.density
    assert "axes.density" in err
    assert "stream 'rotta'" in err
    assert "problema:" in err
    assert "rimedio:" in err


def test_debug_env_reraises(tmp_path, monkeypatch):
    study = _write_study(tmp_path, monkeypatch, BROKEN)
    monkeypatch.setenv("GRANSTUDIES_DEBUG", "1")
    with pytest.raises(SpecError):
        cli.main(["render", study])


def test_yaml_syntax_error_formatted(tmp_path, monkeypatch, capsys):
    study = _write_study(tmp_path, monkeypatch, "axes:\n  a: [unclosed\n")
    rc = cli.main(["render", study])
    assert rc == 2
    err = capsys.readouterr().err
    assert "Traceback" not in err
    assert "YAML" in err


def test_yaml_error_debug_reraises(tmp_path, monkeypatch):
    study = _write_study(tmp_path, monkeypatch, "axes:\n  a: [unclosed\n")
    monkeypatch.setenv("GRANSTUDIES_DEBUG", "1")
    with pytest.raises(yaml.YAMLError):
        cli.main(["render", study])
