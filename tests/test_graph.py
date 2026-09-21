"""La pagina del laboratorio: i parametri, le finestre, i sample."""
import json
import os

from granstudies.graph import build_html, write_graph


def _payload(html_text):
    start = html_text.index("const D = ") + len("const D = ")
    return json.loads(html_text[start:html_text.index("\n", start)].rstrip(";"))


def test_la_pagina_porta_con_se_i_parametri_del_laboratorio(tmp_path):
    """Il payload e' tutto qui: lo studio e le tacche fra cui si sceglie."""
    lab = {"base": {"volume": 12}, "params": [{"path": "grain.duration",
                                               "values": [0.001, 0.064],
                                               "kind": "num"}]}
    d = _payload(build_html("s01", lab))
    assert d["study"] == "s01"
    assert d["lab"]["params"][0]["path"] == "grain.duration"
    assert d["lab"]["base"] == {"volume": 12}


def test_write_graph_scrive_sempre_e_conta_i_parametri(tmp_path):
    """Non guarda piu' il disco: senza audio la pagina serve lo stesso."""
    out = str(tmp_path / "graph.html")
    assert write_graph("s01", out, {"base": {}, "params": [{"path": "a"}]}) == 1
    assert os.path.exists(out)
    assert write_graph("s01", out, {"base": {}, "params": []}) == 0


def test_le_finestre_sono_quelle_dell_engine_non_quelle_dello_studio():
    """Tutte le 16 del catalogo, col profilo vero: e' una scelta per stream."""
    from granstudies.__main__ import _finestre

    env = _finestre()
    assert len(env) == 16
    for nome in ("hanning", "expodec", "rexpodec", "rectangle"):
        assert nome in env
    # hanning parte e finisce a zero, rectangle e' piatta a uno: se il profilo
    # venisse da un'approssimazione scritta qui, questo non lo direbbe nessuno.
    assert env["hanning"][0] == 0.0 and env["hanning"][-1] == 0.0
    assert max(env["hanning"]) > 0.99
    assert set(env["rectangle"]) == {1.0}


def test_i_sample_sono_i_file_della_cartella(tmp_path):
    """Le tacche del `sample` non stanno nello study.yml: sono i file su disco."""
    from granstudies.graph import campioni

    (tmp_path / "sub").mkdir()
    for nome in ("b.wav", "a.flac", "note.md", "sub/c.aif"):
        (tmp_path / nome).write_bytes(b"")
    # Relativi alla cartella dei sample: e' cosi' che l'engine li risolve.
    assert campioni(str(tmp_path)) == ["a.flac", "b.wav", "sub/c.aif"]
