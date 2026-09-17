"""La rete delle varianti discrete: nomi -> coordinate -> una pagina sola."""
import json
import os

from granstudies.graph import (DISCRETE, axes_of, build_html, collect_combos,
                               collect_nodes, parse_coords, parse_label, write_graph)


def test_parse_coords_ignora_il_prefisso_di_studio_e_stream():
    assert parse_coords("001-41_stream_o2__grain.duration=0.001__pitch.ratio=0.447") == {
        "grain.duration": 0.001, "pitch.ratio": 0.447}


def test_parse_coords_regge_underscore_nel_nome_asse_ed_esponenziali():
    assert parse_coords("o2__grain.duration=4e-05__pointer.speed_ratio=0.025") == {
        "grain.duration": 4e-05, "pointer.speed_ratio": 0.025}


def test_parse_coords_senza_coordinate_e_vuoto():
    assert parse_coords("o0__baseline") == {}


def test_parse_label_tiene_i_valori_come_stringhe():
    assert parse_label("coppia=duration-pitch__distribution=0.3") == {
        "coppia": "duration-pitch", "distribution": "0.3"}


def _fake(root, label, names, sub=""):
    d = os.path.join(root, label, DISCRETE, sub) if label else os.path.join(root, DISCRETE, sub)
    os.makedirs(d, exist_ok=True)
    for n in names:
        open(os.path.join(d, n + ".aif"), "w").close()


def test_collect_nodes_scende_nelle_sottocartelle_di_stream(tmp_path):
    root = str(tmp_path)
    _fake(root, "", ["o2__a=1__b=2"], sub="stream")
    nodes = collect_nodes(os.path.join(root, DISCRETE), root)
    assert [n["coords"] for n in nodes] == [{"a": 1.0, "b": 2.0}]
    assert nodes[0]["src"] == os.path.join(DISCRETE, "stream", "o2__a=1__b=2.aif")


def test_collect_nodes_tiene_il_mix_e_scarta_lo_stem(tmp_path):
    root = str(tmp_path)
    _fake(root, "", ["o2__a=1__b=2", "o2__a=1__b=2__stream"])
    nodes = collect_nodes(os.path.join(root, DISCRETE), root)
    assert [n["name"] for n in nodes] == ["o2__a=1__b=2"]


def test_collect_nodes_salta_i_file_senza_coordinate(tmp_path):
    root = str(tmp_path)
    _fake(root, "", ["o2__a=1__b=2", "o0__baseline"])
    assert len(collect_nodes(os.path.join(root, DISCRETE), root)) == 1


def test_axes_of_rispetta_l_ordine_dello_spec_non_quello_alfabetico():
    nodes = [{"coords": {"fill_factor": 0.5, "grain.duration": 0.1}}]
    assert axes_of(nodes) == ["fill_factor", "grain.duration"]
    assert axes_of(nodes, ["grain.duration", "fill_factor"]) == ["grain.duration", "fill_factor"]


def test_collect_combos_una_voce_per_combinazione_con_src_relativi_alla_radice(tmp_path):
    root = str(tmp_path)
    _fake(root, "coppia=ab__d=0", ["o2__a=1__b=2"])
    _fake(root, "coppia=ab__d=1", ["o2__a=1__b=2"])
    combos = collect_combos(root)
    assert [c["label"] for c in combos] == ["coppia=ab__d=0", "coppia=ab__d=1"]
    assert combos[0]["sel"] == {"coppia": "ab", "d": "0"}
    assert combos[0]["nodes"][0]["src"].startswith("coppia=ab__d=0" + os.sep)


def test_collect_combos_usa_l_ordine_assi_della_sua_combinazione(tmp_path):
    root = str(tmp_path)
    _fake(root, "coppia=ab", ["o2__fill_factor=1__grain.duration=2"])
    combos = collect_combos(root, {"coppia=ab": ["grain.duration", "fill_factor"]})
    assert combos[0]["axX"] == "grain.duration"


def test_collect_combos_ignora_le_cartelle_senza_audio_discreto(tmp_path):
    root = str(tmp_path)
    _fake(root, "resa", ["o2__a=1__b=2"])
    os.makedirs(os.path.join(root, "non-resa", "yaml"), exist_ok=True)
    assert [c["label"] for c in collect_combos(root)] == ["resa"]


def _payload(html_text):
    start = html_text.index("const D = ") + len("const D = ")
    return json.loads(html_text[start:html_text.index("\n", start)].rstrip(";"))


def test_build_html_espone_i_selettori_degli_assi_esterni():
    combos = [
        {"label": "c=x__d=0", "sel": {"c": "x", "d": "0"}, "axX": "a", "axY": "b",
         "xs": [1.0], "ys": [2.0], "nodes": [{"name": "n", "src": "n.aif", "coords": {"a": 1.0, "b": 2.0}}]},
        {"label": "c=y__d=0", "sel": {"c": "y", "d": "0"}, "axX": "a", "axY": "b",
         "xs": [1.0], "ys": [2.0], "nodes": [{"name": "m", "src": "m.aif", "coords": {"a": 1.0, "b": 2.0}}]},
    ]
    d = _payload(build_html("s01", combos))
    assert d["keys"] == ["c", "d"]
    assert d["values"] == {"c": ["x", "y"], "d": ["0"]}
    assert len(d["combos"]) == 2


def test_i_valori_dei_selettori_sono_ordinati_per_numero_dove_possibile():
    combos = [{"label": f"d={v}", "sel": {"d": v}, "axX": "a", "axY": "", "xs": [1.0],
               "ys": [0], "nodes": [{"name": v, "src": v, "coords": {"a": 1.0}}]}
              for v in ("0.3", "0", "1")]
    assert _payload(build_html("s01", combos))["values"]["d"] == ["0", "0.3", "1"]


def test_write_graph_senza_audio_non_scrive_niente(tmp_path):
    out = str(tmp_path / "graph.html")
    assert write_graph("s01", str(tmp_path), out) == (0, 0)
    assert not os.path.exists(out)


def test_write_graph_una_pagina_sola_per_tutte_le_combinazioni(tmp_path):
    root = str(tmp_path)
    _fake(root, "d=0", ["o2__a=1__b=2"])
    _fake(root, "d=1", ["o2__a=1__b=2", "o2__a=3__b=2"])
    out = os.path.join(root, "graph.html")
    assert write_graph("s01", root, out) == (2, 3)
    assert os.path.exists(out)


def test_asse_con_piu_valori_va_in_verticale():
    """La griglia e' piu' alta che larga: 24 grain.duration su una riga
    sborderebbero, in colonna scorrono."""
    from granstudies.graph import _grid
    nodes = [{"coords": {"grain.duration": d, "pitch.ratio": p}}
             for d in (0.001, 0.002, 0.004) for p in (0.2, 1.0)]
    g = _grid(nodes, ["grain.duration", "pitch.ratio"])
    assert g["axY"] == "grain.duration" and len(g["ys"]) == 3
    assert g["axX"] == "pitch.ratio" and len(g["xs"]) == 2


def test_a_pari_lunghezza_resta_l_ordine_dichiarato():
    from granstudies.graph import _grid
    nodes = [{"coords": {"a": x, "b": y}} for x in (1, 2) for y in (3, 4)]
    assert _grid(nodes, ["a", "b"])["axX"] == "a"


def test_un_asse_solo_non_scambia_nulla():
    from granstudies.graph import _grid
    g = _grid([{"coords": {"a": 1}}, {"coords": {"a": 2}}], ["a"])
    assert (g["axX"], g["axY"]) == ("a", "")
    assert g["xs"] == [1, 2] and g["ys"] == [0]


def test_nessun_asse_griglia_degenere():
    from granstudies.graph import _grid
    g = _grid([{"coords": {}}], [])
    assert (g["axX"], g["axY"]) == ("", "")
    assert g["xs"] == [] and g["ys"] == [0]


def test_y_gia_piu_lungo_resta_dov_e():
    from granstudies.graph import _grid
    nodes = [{"coords": {"a": x, "b": y}}
             for x in (1, 2) for y in (3, 4, 5)]
    g = _grid(nodes, ["a", "b"])
    assert g["axX"] == "a" and g["xs"] == [1, 2]
    assert g["axY"] == "b" and g["ys"] == [3, 4, 5]


def test_asse_categoriale_resta_una_coordinata(tmp_path):
    """grain.envelope non e' un numero: prima cadeva e la griglia collassava."""
    root = str(tmp_path)
    _fake(root, "", ["o2__grain.duration=0.001__grain.envelope=hanning",
                     "o2__grain.duration=0.001__grain.envelope=sinc",
                     "o2__grain.duration=0.002__grain.envelope=hanning",
                     "o2__grain.duration=0.002__grain.envelope=sinc"])
    combo = collect_combos(root)[0]
    assert len(combo["nodes"]) == 4
    assert sorted([combo["axX"], combo["axY"]]) == ["grain.duration", "grain.envelope"]
    assert combo["ys"] == ["hanning", "sinc"] or combo["xs"] == ["hanning", "sinc"]


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
