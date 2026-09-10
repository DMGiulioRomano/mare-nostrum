"""La rete delle varianti discrete: nomi -> coordinate -> HTML."""
import json
import os

from granstudies.graph import axes_of, build_html, collect_nodes, parse_coords, write_graph


def test_parse_coords_ignora_il_prefisso_di_studio_e_stream():
    assert parse_coords("001-41_stream_o2__grain.duration=0.001__pitch.ratio=0.447") == {
        "grain.duration": 0.001, "pitch.ratio": 0.447}


def test_parse_coords_regge_underscore_nel_nome_asse_ed_esponenziali():
    assert parse_coords("o2__grain.duration=4e-05__pointer.speed_ratio=0.025") == {
        "grain.duration": 4e-05, "pointer.speed_ratio": 0.025}


def test_parse_coords_senza_coordinate_e_vuoto():
    assert parse_coords("o0__baseline") == {}


def _fake_audio(root, names, sub=""):
    d = os.path.join(root, sub) if sub else root
    os.makedirs(d, exist_ok=True)
    for n in names:
        open(os.path.join(d, n + ".aif"), "w").close()


def test_collect_nodes_scende_nelle_sottocartelle_di_stream(tmp_path):
    root = str(tmp_path)
    _fake_audio(root, ["o2__a=1__b=2"], sub="stream")
    nodes = collect_nodes(root)
    assert [n["coords"] for n in nodes] == [{"a": 1.0, "b": 2.0}]
    assert nodes[0]["src"] == os.path.join("stream", "o2__a=1__b=2.aif")


def test_collect_nodes_salta_i_file_senza_coordinate(tmp_path):
    _fake_audio(str(tmp_path), ["o2__a=1__b=2", "o0__baseline"])
    assert len(collect_nodes(str(tmp_path))) == 1


def test_axes_of_rispetta_l_ordine_dello_spec_non_quello_alfabetico():
    nodes = [{"coords": {"fill_factor": 0.5, "grain.duration": 0.1}}]
    assert axes_of(nodes) == ["fill_factor", "grain.duration"]
    assert axes_of(nodes, ["grain.duration", "fill_factor"]) == ["grain.duration", "fill_factor"]


def _payload(html_text):
    start = html_text.index("const D = ") + len("const D = ")
    return json.loads(html_text[start:html_text.index("\n", start)].rstrip(";"))


def test_build_html_porta_griglia_nodi_e_sorelle():
    nodes = [{"name": "n", "src": "n.aif", "coords": {"x": 1.0, "y": 2.0}},
             {"name": "m", "src": "m.aif", "coords": {"x": 3.0, "y": 2.0}}]
    d = _payload(build_html("s01", "distribution=0", nodes, ["distribution=1"], ["x", "y"]))
    assert d["axX"] == "x" and d["axY"] == "y"
    assert d["xs"] == [1.0, 3.0] and d["ys"] == [2.0]
    assert d["siblings"] == ["distribution=1"]
    assert len(d["nodes"]) == 2


def test_write_graph_senza_audio_non_scrive_niente(tmp_path):
    out = str(tmp_path / "out" / "graph.html")
    assert write_graph("s01", "", str(tmp_path), out, []) == 0
    assert not os.path.exists(out)


def test_write_graph_scrive_html_accanto_all_audio(tmp_path):
    _fake_audio(str(tmp_path), ["o2__a=1__b=2"])
    out = str(tmp_path / "graph.html")
    assert write_graph("s01", "", str(tmp_path), out, []) == 1
    assert "o2__a=1__b=2.aif" in open(out).read()
