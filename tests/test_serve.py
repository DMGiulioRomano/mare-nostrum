"""Il render on demand: documento JSON -> YAML leggibile -> engine."""
import json
import subprocess

from granstudies import serve as S


def _ok(*a, **k):
    return subprocess.CompletedProcess(a, 0, "", "")


DOC = {"duration": 4, "streams": [{"stream_id": "lab",
                                   "grain": {"duration": [[0, 0.001], [1, 0.02]]}}]}


def test_scrive_yaml_e_audio_accanto(tmp_path, monkeypatch):
    monkeypatch.setattr(S.subprocess, "run", _ok)
    out = S.render_doc(DOC, "prova bp", str(tmp_path), str(tmp_path))
    assert out == {"ok": True, "src": "live/prova_bp.aif", "yaml": "live/prova_bp.yml"}
    # I breakpoint su una riga sola: e' la forma in cui questi documenti si
    # leggono, e in block style sarebbero sei righe di trattini.
    assert "duration: [[0, 0.001], [1, 0.02]]" in (tmp_path / "live" / "prova_bp.yml").read_text()


def test_errore_dell_engine_torna_alla_pagina(tmp_path, monkeypatch):
    monkeypatch.setattr(S.subprocess, "run",
                        lambda *a, **k: subprocess.CompletedProcess(a, 1, "", "boom"))
    out = S.render_doc(DOC, "x", str(tmp_path), str(tmp_path))
    assert out["ok"] is False and "boom" in out["error"]


def test_nome_senza_scappatoie_di_percorso(tmp_path, monkeypatch):
    monkeypatch.setattr(S.subprocess, "run", _ok)
    out = S.render_doc(DOC, "../../etc/passwd", str(tmp_path), str(tmp_path))
    assert out["src"] == "live/.._.._etc_passwd.aif"
    assert (tmp_path / "live").exists() and list((tmp_path / "live").glob("*.yml"))


def test_salva_senza_rendere(tmp_path, monkeypatch):
    """Salvare e' immediato, rendere no: si tiene il lavoro senza aspettare."""
    chiamato = []
    monkeypatch.setattr(S.subprocess, "run", lambda *a, **k: chiamato.append(a) or _ok())
    out = S.render_doc(DOC, "bozza", str(tmp_path), str(tmp_path), render=False)
    assert out == {"ok": True, "src": None, "yaml": "live/bozza.yml"}
    assert not chiamato                      # l'engine non e' stato toccato
    assert (tmp_path / "live" / "bozza.yml").exists()


def test_elenco_dei_progetti_salvati(tmp_path, monkeypatch):
    """La pagina riapre da qui: YAML tradotto in JSON dal server."""
    monkeypatch.setattr(S.subprocess, "run", _ok)
    S.render_doc(DOC, "uno", str(tmp_path), str(tmp_path), render=False)
    S.render_doc({"duration": 3, "streams": []}, "due", str(tmp_path), str(tmp_path), render=False)
    (tmp_path / "live" / "rotto.yml").write_text("[: non yaml")
    el = S.elenco(str(tmp_path))
    assert sorted(el) == ["due", "uno"]      # il file rotto si salta, non esplode
    assert el["uno"]["streams"][0]["grain"]["duration"] == [[0, 0.001], [1, 0.02]]
