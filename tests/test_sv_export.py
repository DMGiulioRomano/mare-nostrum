import bz2
import os
import xml.etree.ElementTree as ET

from granstudies.envelope_sweep import envelope_breakpoints
from granstudies.sv_export import _plateau_starts, _build_sv_xml, _find_envelopes, _merge_by_param


def _parse(compressed: bytes) -> ET.Element:
    xml = bz2.decompress(compressed).decode("utf-8")
    return ET.fromstring(xml)


# --- _find_envelopes -----------------------------------------------------------

def test_find_envelopes_recognizes_step():
    doc = {"grain": {"duration": {"type": "step",
                                  "points": [[0.0, 5], [0.5, 50]],
                                  "time_mode": "normalized"}}}
    assert _find_envelopes(doc) == [("grain.duration", [[0.0, 5], [0.5, 50]], "step")]


# --- _plateau_starts -----------------------------------------------------------

def test_plateau_starts_one_envelope():
    points = envelope_breakpoints([5, 50, 400], plateau=5, transition=5)
    # [[0,5],[.2,5],[.4,50],[.6,50],[.8,400],[1,400]] -> inizi: 0.0, 0.4, 0.8
    assert _plateau_starts([("density", points, "linear", 0.0, 1.0)]) == [0.0, 0.4, 0.8]


def test_plateau_starts_dedup_synchronized_envelopes():
    # Due assi mossi insieme: stessa griglia temporale -> stessi t_start, dedup.
    a = envelope_breakpoints([5, 50, 400], plateau=5, transition=5)
    b = envelope_breakpoints([0.01, 0.05, 0.2], plateau=5, transition=5)
    starts = _plateau_starts([("density", a, "linear", 0.0, 1.0), ("grain.duration", b, "linear", 0.0, 1.0)])
    assert starts == [0.0, 0.4, 0.8]


def test_plateau_starts_repeated_value_not_merged():
    # Valori consecutivi uguali (asse esterno fermo): vanno comunque contati
    # come plateau distinti -> 4 inizi, non 3.
    points = envelope_breakpoints([5, 5, 50, 400], plateau=5, transition=5)
    assert len(_plateau_starts([("density", points, "linear", 0.0, 1.0)])) == 4


def test_plateau_starts_single_value():
    points = envelope_breakpoints([42], plateau=5, transition=5)  # [[0,42],[1,42]]
    assert _plateau_starts([("density", points, "linear", 0.0, 1.0)]) == [0.0]


def test_plateau_starts_step_one_marker_per_value():
    # Geometria step: un solo punto per valore -> ogni punto e' un inizio-gradino.
    pts = envelope_breakpoints([5, 50, 400], plateau=5, transition=5, step=True)
    assert _plateau_starts([("density", pts, "step", 0.0, 1.0)]) == [0.0, 0.333333, 0.666667]


# --- plotStyle per tipo --------------------------------------------------------

def test_step_layer_uses_stepped_plot_style():
    # SV (fork): enum PlotStyle -> Stepped = 8. Il layer timevalues dell'envelope
    # step dev'essere disegnato a scalini, non a segmenti obliqui.
    pts = envelope_breakpoints([5, 50, 400], plateau=5, transition=5, step=True)
    xml = _parse(_build_sv_xml("/x.wav", 1000, 15.0, [("density", pts, "step", 0.0, 15.0)], "multi"))
    tv = [l for l in xml.findall("./data/layer") if l.get("type") == "timevalues"]
    assert len(tv) == 1
    assert tv[0].get("plotStyle") == "8"


def test_per_breakpoint_envelope_uses_per_breakpoint_plot_style():
    # SV (fork): enum PlotStyle -> PerBreakpoint = 9. Envelope con almeno un
    # punto [t, v, type] (sintassi per-punto del motore): il layer va disegnato
    # col nuovo stile misto, non con quello globale del type di envelope.
    pts = [[0.0, 5, "step"], [0.4, 50, "cubic"], [1.0, 400]]
    xml = _parse(_build_sv_xml("/x.wav", 1000, 10.0, [("density", pts, "linear", 0.0, 10.0)], "multi",
                               markers=False))
    tv = [l for l in xml.findall("./data/layer") if l.get("type") == "timevalues"]
    assert len(tv) == 1
    assert tv[0].get("plotStyle") == "9"


def test_per_breakpoint_points_emit_type_as_label():
    # Il type per-punto viaggia nella label del <point>: e' il canale che
    # TimeValueLayer::PlotPerBreakpoint legge per scegliere l'interpolazione
    # del segmento che parte dal punto. Punti senza type -> label vuota.
    pts = [[0.0, 5, "step"], [0.4, 50, "cubic"], [1.0, 400]]
    xml = _parse(_build_sv_xml("/x.wav", 1000, 10.0, [("density", pts, "linear", 0.0, 10.0)], "multi",
                               markers=False))
    ds = xml.findall("./data/dataset")
    assert len(ds) == 1
    points = ds[0].findall("point")
    assert [p.get("label") for p in points] == ["step", "cubic", ""]
    assert [p.get("value") for p in points] == ["5", "50", "400"]
    assert [p.get("frame") for p in points] == ["0", "4000", "10000"]


def test_uniform_envelope_keeps_global_plot_style():
    # Senza punti a 3 elementi il comportamento resta quello di prima:
    # plotStyle dal type dell'envelope, label vuote.
    pts = [[0.0, 5], [1.0, 400]]
    xml = _parse(_build_sv_xml("/x.wav", 1000, 10.0, [("density", pts, "cubic", 0.0, 10.0)], "multi",
                               markers=False))
    tv = [l for l in xml.findall("./data/layer") if l.get("type") == "timevalues"]
    assert tv[0].get("plotStyle") == "7"
    ds = xml.findall("./data/dataset")[0]
    assert [p.get("label") for p in ds.findall("point")] == ["", ""]


def test_stems_builder_handles_per_breakpoint_points():
    from granstudies.sv_export import _build_sv_xml_stems
    import os, tempfile

    pts = [[0.0, 5, "step"], [1.0, 50]]
    with tempfile.NamedTemporaryFile(suffix=".aif") as fh:
        stems = [("base", fh.name, 1000, 0.0, 10.0,
                  [("base/density", pts, "linear", 0.0, 10.0)])]
        xml = _parse(_build_sv_xml_stems(stems))

    tv = [l for l in xml.findall("./data/layer") if l.get("type") == "timevalues"]
    assert len(tv) == 1
    assert tv[0].get("plotStyle") == "9"
    ds = xml.findall("./data/dataset")[0]
    assert [p.get("label") for p in ds.findall("point")] == ["step", ""]


# --- marker layer nel .sv ------------------------------------------------------

def _envelopes(duration=25.0):
    pts = envelope_breakpoints([5, 50, 400], plateau=5, transition=5)
    return [("density", pts, "linear", 0.0, duration)]


def test_markers_emitted_in_data_and_every_pane():
    sr, duration = 1000, 25.0  # 3*5 + 2*5; frame = t_norm * duration * sr
    xml = _parse(_build_sv_xml("/x.wav", sr, duration, _envelopes(), "multi",
                               markers_scope="all"))

    inst_models = [m for m in xml.findall("./data/model") if m.get("dimensions") == "1"]
    assert len(inst_models) == 1

    ds_id = inst_models[0].get("dataset")
    ds = next(d for d in xml.findall("./data/dataset") if d.get("id") == ds_id)
    pts = ds.findall("point")
    assert [p.get("frame") for p in pts] == ["0", "10000", "20000"]
    assert [p.get("label") for p in pts] == ["1", "2", "3"]  # plateau 1-based

    # Il modello marker dev'essere mutato, altrimenti SV suona un click a
    # ogni instant durante il playback.
    pp = [p for p in xml.findall("./data/playparameters")
          if p.get("model") == inst_models[0].get("id")]
    assert len(pp) == 1 and pp[0].get("mute") == "true"

    data_layer = [l for l in xml.findall("./data/layer") if l.get("type") == "timeinstants"]
    assert len(data_layer) == 1
    marker_id = data_layer[0].get("id")

    # scope=all: marker in ogni pane (waveform + un pane envelope = 2 pane).
    panes = xml.findall("./display/view")
    assert len(panes) == 2
    for pane in panes:
        ids = [l.get("id") for l in pane.findall("layer") if l.get("type") == "timeinstants"]
        assert ids == [marker_id]


def test_markers_scope_waveform():
    # Default: marker solo nel pane waveform (primo), non nei pane envelope.
    xml = _parse(_build_sv_xml("/x.wav", 1000, 25.0, _envelopes(), "multi"))
    data_layer = [l for l in xml.findall("./data/layer") if l.get("type") == "timeinstants"]
    assert len(data_layer) == 1
    marker_id = data_layer[0].get("id")

    panes = xml.findall("./display/view")
    assert len(panes) == 2
    waveform_ids = [l.get("id") for l in panes[0].findall("layer") if l.get("type") == "timeinstants"]
    envelope_ids = [l.get("id") for l in panes[1].findall("layer") if l.get("type") == "timeinstants"]
    assert waveform_ids == [marker_id]
    assert envelope_ids == []


def test_spectrogram_in_waveform_pane():
    xml = _parse(_build_sv_xml("/x.wav", 1000, 25.0, _envelopes(), "multi"))
    # Layer spectrogram definito in data
    spec_layers = [l for l in xml.findall("./data/layer") if l.get("type") == "spectrogram"]
    assert len(spec_layers) == 1
    sl = spec_layers[0]
    assert sl.get("windowSize") == "8192"
    assert sl.get("windowHopLevel") == "3"
    assert sl.get("colourScheme") == "2"
    assert sl.get("frequencyScale") == "0"
    assert sl.get("channel") == "-1"

    # Presente nel pane waveform (primo pane)
    waveform_pane = xml.findall("./display/view")[0]
    pane_spec = [l for l in waveform_pane.findall("layer") if l.get("type") == "spectrogram"]
    assert len(pane_spec) == 1


def test_markers_disabled():
    xml = _parse(_build_sv_xml("/x.wav", 1000, 25.0, _envelopes(), "multi", markers=False))
    assert [l for l in xml.findall("./data/layer") if l.get("type") == "timeinstants"] == []
    for pane in xml.findall("./display/view"):
        assert pane.findall("layer[@type='timeinstants']") == []


# --- stack: envelope multi-stream ---------------------------------------------

def test_stack_envelopes_prefixes_stream_id_and_skips_scalars():
    from granstudies.sv_export import _stack_envelopes
    doc = {"streams": [
        {"stream_id": "base",
         "density": {"type": "step", "points": [[0.0, 5], [1.0, 50]]},
         "grain": {"duration": 0.004}},          # scalare -> nessun envelope
        {"stream_id": "voce_b",
         "density": {"type": "cubic", "points": [[0.0, 10], [1.0, 20]]}},
        {"stream_id": "drone",
         "density": 8, "grain": {"duration": 0.05}},  # tutto scalare -> niente
    ]}
    envs = _stack_envelopes(doc)
    paths = [p for p, _pts, _t, _onset, _dur in envs]
    assert paths == ["base/density", "voce_b/density"]


def test_stack_envelopes_draws_static_axes_as_two_point_line():
    """Con i path degli assi, un asse scalare diventa una retta a due punti.

    Due punti e non uno: SV disegna un segmento fra breakpoint, con un punto
    solo il layer resterebbe vuoto.
    """
    from granstudies.sv_export import _stack_envelopes
    doc = {"streams": [
        {"stream_id": "base",
         "density": {"type": "step", "points": [[0.0, 5], [1.0, 50]]},
         "grain": {"duration": 0.004}},          # asse statico
        {"stream_id": "drone",
         "density": 8, "grain": {"duration": 0.05}, "volume": -6},  # non-asse
    ]}
    envs = _stack_envelopes(doc, ["density", "grain.duration"])
    by_path = {p: pts for p, pts, _t, _o, _d in envs}
    assert by_path["base/grain.duration"] == [[0.0, 0.004], [1.0, 0.004]]
    assert by_path["drone/density"] == [[0.0, 8], [1.0, 8]]
    assert by_path["base/density"] == [[0.0, 5], [1.0, 50]]   # mobile: intatto
    assert "drone/volume" not in by_path                       # non e' un asse


def test_multi_groups_envelopes_by_stream_prefix():
    # Path con prefisso stream/ (export stack): gli assi di uno stream finiscono
    # nello stesso pane; stream diversi in pane diversi.
    envs = [
        ("a/density", [[0.0, 5], [1.0, 50]], "step", 0.0, 10.0),
        ("a/grain.duration", [[0.0, 0.001], [1.0, 0.01]], "linear", 0.0, 10.0),
        ("b/density", [[0.0, 10], [1.0, 20]], "cubic", 0.0, 10.0),
    ]
    xml = _parse(_build_sv_xml("/x.wav", 1000, 10.0, envs, "multi", markers=False))
    panes = xml.findall("./display/view")
    env_panes = panes[1:]  # il primo e' waveform
    names = [[l.get("name") for l in p.findall("layer[@type='timevalues']")] for p in env_panes]
    assert names == [["a/density", "a/grain.duration"], ["b/density"]]


def test_one_layer_per_param_across_versions():
    # Piu' stream della stessa voce nello stesso pane: un layer per parametro
    # (density, grain.duration), non uno per stream. Interpolazioni diverse tra
    # le versioni -> il type finisce nella label e il layer passa a PlotPerBreakpoint.
    envs = [
        ("v__d=1/density", [[0.0, 5], [1.0, 10]], "linear", 0.0, 10.0),
        ("v__d=1/grain.duration", [[0.0, 0.001], [1.0, 0.002]], "linear", 0.0, 10.0),
        ("v__d=2/density", [[0.0, 20], [1.0, 40]], "step", 10.0, 10.0),
        ("v__d=2/grain.duration", [[0.0, 0.003], [1.0, 0.004]], "linear", 10.0, 10.0),
    ]
    xml = _parse(_build_sv_xml("/x.wav", 1000, 20.0, envs, "multi", markers=False))
    tv = [l for l in xml.findall("./data/layer") if l.get("type") == "timevalues"]
    assert [l.get("name") for l in tv] == ["v/density", "v/grain.duration"]
    env_panes = xml.findall("./display/view")[1:]
    assert len(env_panes) == 1

    sparse = {m.get("dataset"): m.get("name") for m in xml.findall("./data/model")
              if m.get("type") == "sparse"}
    frames = {sparse[ds.get("id")]: [int(p.get("frame")) for p in ds.findall("point")]
              for ds in xml.findall("./data/dataset")}
    assert frames["v/density"] == [0, 10000, 10000, 20000]
    # density: linear + step mescolati -> label per punto, plotStyle 9
    density_layer = [l for l in tv if l.get("name") == "v/density"][0]
    assert density_layer.get("plotStyle") == "9"
    # grain.duration: type unico -> resta il plotStyle del layer, label vuote
    grain_layer = [l for l in tv if l.get("name") == "v/grain.duration"][0]
    assert grain_layer.get("plotStyle") == "3"


def test_stack_envelopes_carry_stream_onset_and_duration():
    # study_versions_test: 3 versioni concatenate, ognuna con la propria
    # durata (20s) e onset (0/20/40) diversi dalla durata totale dello
    # stack (60s). I punti normalizzati [0,1] di ogni stream vanno riportati
    # sull'asse assoluto come onset + t_norm*duration_stream, non contro la
    # durata totale del documento (bug: prima schiacciava/spostava tutto).
    from granstudies.sv_export import _stack_envelopes
    doc = {
        "duration": 60,
        "streams": [
            {"stream_id": "fermo__d=1", "onset": 0, "duration": 20,
             "density": {"type": "linear", "points": [[0.0, 1], [1.0, 2]]}},
            {"stream_id": "fermo__d=2", "onset": 20, "duration": 20,
             "density": {"type": "linear", "points": [[0.0, 1], [1.0, 2]]}},
        ],
    }
    envs = _stack_envelopes(doc)
    assert [(onset, dur) for _p, _pts, _t, onset, dur in envs] == [(0.0, 20.0), (20.0, 20.0)]

    xml = _parse(_build_sv_xml("/x.wav", 1000, 60.0, envs, "multi", markers=False))
    datasets = xml.findall("./data/dataset")
    # le due versioni della stessa voce si fondono in un layer density unico
    assert len(datasets) == 1
    frames = [p.get("frame") for p in datasets[0].findall("point")]
    # t_norm=1.0: primo stream -> (0 + 1*20)*1000 = 20000; secondo -> (20 + 1*20)*1000 = 40000
    assert frames == ["0", "20000", "20000", "40000"]


def test_multi_without_prefix_is_one_pane_per_envelope():
    # Path sweep (senza '/'): comportamento invariato, un pane per envelope.
    envs = [("density", [[0.0, 5]], "step", 0.0, 10.0), ("grain.duration", [[0.0, 0.001]], "linear", 0.0, 10.0)]
    xml = _parse(_build_sv_xml("/x.wav", 1000, 10.0, envs, "multi", markers=False))
    env_panes = xml.findall("./display/view")[1:]
    assert len(env_panes) == 2


# --- per-stem: padding dell'onset come silenzio iniziale -----------------------

def _write_aif(path, seconds, sr=1000, value=0.5):
    import numpy as np
    import soundfile as sf
    data = np.full(round(seconds * sr), value, dtype="float64")
    sf.write(path, data, sr, format="AIFF")


def test_padded_stem_prepends_onset_silence(tmp_path):
    import numpy as np
    import soundfile as sf
    from granstudies.sv_export import _padded_stem

    src = str(tmp_path / "stack__mobile.aif")
    _write_aif(src, seconds=2.0, sr=1000)
    out = _padded_stem(src, onset=1.5, padded_dir=str(tmp_path / "padded"))

    data, sr = sf.read(out)
    assert sr == 1000
    assert len(data) == 3500                      # 1.5s silenzio + 2s contenuto
    assert np.all(data[:1500] == 0)               # silenzio iniziale
    assert np.allclose(data[1500:], 0.5, atol=1e-3)


def test_padded_stem_incremental(tmp_path):
    import os
    from granstudies.sv_export import _padded_stem

    src = str(tmp_path / "stack__mobile.aif")
    _write_aif(src, seconds=1.0)
    out = _padded_stem(src, onset=0.5, padded_dir=str(tmp_path / "padded"))
    first = os.path.getmtime(out)
    out2 = _padded_stem(src, onset=0.5, padded_dir=str(tmp_path / "padded"))
    assert out2 == out
    assert os.path.getmtime(out) == first         # originale invariato -> skip
    # originale piu' nuovo -> rigenera
    os.utime(src, (first + 10, first + 10))
    _padded_stem(src, onset=0.5, padded_dir=str(tmp_path / "padded"))
    assert os.path.getmtime(out) > first


def test_stems_sv_uses_process_prefix_not_hardcoded_stack(tmp_path):
    """Issue #29: gli stem di 'percorso'/'versions' hanno il prefisso del
    processo, non il letterale 'stack__' — altrimenti l'export SV per-stem non
    li trova (bug segnalato sulla PR #30)."""
    import yaml
    from granstudies.sv_export import stack_stems_to_sv

    audio_dir = tmp_path / "audio"
    audio_dir.mkdir()
    # Voce logica 'coro' moltiplicata da percorso: il post-merge produce il
    # file accorpato 'percorso__coro.aif' (non 'stack__coro.aif').
    _write_aif(str(audio_dir / "percorso__coro.aif"), seconds=2.0, sr=1000)

    doc = {"duration": 4, "streams": [
        {"stream_id": "coro__d=1", "onset": 0, "duration": 2,
         "density": {"type": "linear", "points": [[0.0, 10], [1.0, 20]],
                     "time_mode": "normalized"}},
        {"stream_id": "coro__d=2", "onset": 2, "duration": 2,
         "density": {"type": "linear", "points": [[0.0, 30], [1.0, 40]],
                     "time_mode": "normalized"}},
    ]}
    yml = tmp_path / "percorso.yml"
    yml.write_text(yaml.safe_dump(doc))

    # Col default (process='stack') non troverebbe lo stem -> None.
    assert stack_stems_to_sv(str(yml), str(audio_dir), str(tmp_path / "no.sv")) is None
    # Col processo giusto lo trova e scrive.
    out = stack_stems_to_sv(str(yml), str(audio_dir), str(tmp_path / "s.sv"),
                            process="percorso")
    assert out is not None
    xml = _parse((tmp_path / "s.sv").read_bytes())
    files = [m.get("file") for m in xml.findall("./data/model")
             if m.get("type") == "wavefile"]
    assert any(f.endswith("percorso__coro.aif") for f in files)


def test_stems_sv_uses_padded_audio_and_offsets_envelopes(tmp_path):
    import yaml
    from granstudies.sv_export import stack_stems_to_sv

    audio_dir = tmp_path / "audio"
    audio_dir.mkdir()
    _write_aif(str(audio_dir / "stack__fermo.aif"), seconds=2.0, sr=1000)
    _write_aif(str(audio_dir / "stack__mobile.aif"), seconds=2.0, sr=1000)

    doc = {"duration": 4, "streams": [
        {"stream_id": "fermo", "onset": 0, "duration": 2,
         "density": {"type": "linear", "points": [[0.0, 10], [1.0, 20]],
                     "time_mode": "normalized"}},
        {"stream_id": "mobile", "onset": 2, "duration": 2,
         "density": {"type": "linear", "points": [[0.0, 10], [1.0, 20]],
                     "time_mode": "normalized"}},
    ]}
    stack_yml = tmp_path / "stack.yml"
    stack_yml.write_text(yaml.safe_dump(doc))
    out = stack_stems_to_sv(str(stack_yml), str(audio_dir), str(tmp_path / "s.sv"))
    assert out is not None

    xml = _parse((tmp_path / "s.sv").read_bytes())
    models = {m.get("id"): m for m in xml.findall("./data/model")
              if m.get("type") == "wavefile"}
    files = [m.get("file") for m in models.values()]
    # onset 0 -> stem originale; onset 2 -> copia paddata in padded/
    assert any(f.endswith("audio/stack__fermo.aif") or f.endswith("stack__fermo.aif")
               and "padded" not in f for f in files)
    assert any("padded" in f and f.endswith("stack__mobile.aif") for f in files)

    # envelope di mobile offsettati di onset: 2s..4s a 1000 Hz -> 2000..4000
    sparse = {m.get("dataset"): m.get("name") for m in xml.findall("./data/model")
              if m.get("type") == "sparse"}
    for ds in xml.findall("./data/dataset"):
        name = sparse.get(ds.get("id"), "")
        frames = [int(p.get("frame")) for p in ds.findall("point")]
        if name.startswith("mobile/"):
            assert frames == [2000, 4000]
        elif name.startswith("fermo/"):
            assert frames == [0, 2000]


# --- issue #24: gruppi di versioni accorpati per nome-base ----------------------

def test_stack_stems_to_sv_merged_versions_one_pane_per_base(tmp_path):
    # Documento versions: 2 voci logiche x 2 combinazioni. Il render ha gia'
    # prodotto i file accorpati stack__{base}.aif: un pane per voce logica,
    # non uno per combinazione, con gli envelope di ogni versione offsettati
    # al proprio onset. Nessun padding: il file accorpato e' ancorato a 0.
    import yaml
    from granstudies.sv_export import stack_stems_to_sv

    audio_dir = tmp_path / "audio"
    audio_dir.mkdir()
    _write_aif(str(audio_dir / "stack__fermo.aif"), seconds=4.0, sr=1000)
    _write_aif(str(audio_dir / "stack__mobile.aif"), seconds=4.0, sr=1000)

    env = {"type": "linear", "points": [[0.0, 10], [1.0, 20]],
           "time_mode": "normalized"}
    doc = {"duration": 4, "streams": [
        {"stream_id": "fermo__d=1", "onset": 0, "duration": 2, "density": dict(env)},
        {"stream_id": "fermo__d=2", "onset": 2, "duration": 2, "density": dict(env)},
        {"stream_id": "mobile__d=1", "onset": 0, "duration": 2, "density": dict(env)},
        {"stream_id": "mobile__d=2", "onset": 2, "duration": 2, "density": dict(env)},
    ]}
    stack_yml = tmp_path / "stack.yml"
    stack_yml.write_text(yaml.safe_dump(doc))
    out = stack_stems_to_sv(str(stack_yml), str(audio_dir), str(tmp_path / "s.sv"))
    assert out is not None

    xml = _parse((tmp_path / "s.sv").read_bytes())
    wave_models = [m for m in xml.findall("./data/model") if m.get("type") == "wavefile"]
    files = sorted(os.path.basename(m.get("file")) for m in wave_models)
    assert files == ["stack__fermo.aif", "stack__mobile.aif"]
    assert all("padded" not in m.get("file") for m in wave_models)
    # 2 pane (uno per voce logica), non 4
    assert len(xml.findall("./display/view")) == 2

    # envelope per versione, offsettati sull'asse assoluto dello stack
    sparse = {m.get("dataset"): m.get("name") for m in xml.findall("./data/model")
              if m.get("type") == "sparse"}
    frames_by_name = {}
    for ds in xml.findall("./data/dataset"):
        name = sparse.get(ds.get("id"), "")
        frames_by_name[name] = [int(p.get("frame")) for p in ds.findall("point")]
    # un solo layer density per voce: le due versioni, consecutive nel tempo,
    # sono una polilinea sola invece di due layer sovrapposti
    assert frames_by_name["fermo/density"] == [0, 2000, 2000, 4000]
    assert frames_by_name["mobile/density"] == [0, 2000, 2000, 4000]


def test_stack_stems_to_sv_merged_group_missing_file_aborts(tmp_path):
    import yaml
    from granstudies.sv_export import stack_stems_to_sv

    audio_dir = tmp_path / "audio"
    audio_dir.mkdir()
    # esistono solo gli stem per combinazione, non il file accorpato
    _write_aif(str(audio_dir / "stack__fermo__d=1.aif"), seconds=2.0, sr=1000)
    _write_aif(str(audio_dir / "stack__fermo__d=2.aif"), seconds=2.0, sr=1000)
    doc = {"duration": 4, "streams": [
        {"stream_id": "fermo__d=1", "onset": 0, "duration": 2},
        {"stream_id": "fermo__d=2", "onset": 2, "duration": 2},
    ]}
    stack_yml = tmp_path / "stack.yml"
    stack_yml.write_text(yaml.safe_dump(doc))
    assert stack_stems_to_sv(str(stack_yml), str(audio_dir), str(tmp_path / "s.sv")) is None
    assert not os.path.exists(tmp_path / "s.sv")


def test_stack_stems_to_sv_singleton_suffixed_stream_keeps_raw_stem(tmp_path):
    # Un solo stream per nome-base, anche se suffissato: nessun file accorpato
    # da attendersi, si consuma lo stem grezzo come prima (con padding onset).
    import yaml
    from granstudies.sv_export import stack_stems_to_sv

    audio_dir = tmp_path / "audio"
    audio_dir.mkdir()
    _write_aif(str(audio_dir / "stack__fermo__d=1.aif"), seconds=2.0, sr=1000)
    doc = {"duration": 4, "streams": [
        {"stream_id": "fermo__d=1", "onset": 2, "duration": 2},
    ]}
    stack_yml = tmp_path / "stack.yml"
    stack_yml.write_text(yaml.safe_dump(doc))
    out = stack_stems_to_sv(str(stack_yml), str(audio_dir), str(tmp_path / "s.sv"))
    assert out is not None
    xml = _parse((tmp_path / "s.sv").read_bytes())
    files = [m.get("file") for m in xml.findall("./data/model")
             if m.get("type") == "wavefile"]
    assert len(files) == 1
    assert "padded" in files[0] and files[0].endswith("stack__fermo__d=1.aif")


def test_vocabolario_interpolation_allineato_col_parser():
    """Il vocabolario che il parse accetta e i tipi che il .sv sa disegnare sono
    lo stesso insieme. Erano due liste letterali scritte a mano in due moduli:
    questo test e' cio' che tiene ferma la coincidenza, senza far dipendere
    l'export dal parser."""
    from granstudies.study_spec import VALID_INTERPOLATION
    from granstudies.sv_export import _ENVELOPE_TYPES, _PLOT_STYLE_BY_TYPE

    assert set(VALID_INTERPOLATION) == _ENVELOPE_TYPES
    assert set(VALID_INTERPOLATION) == set(_PLOT_STYLE_BY_TYPE)


def test_gap_between_versions_closes_param_to_zero():
    # Due segmenti della stessa voce separati da un buco (in mezzo suona un
    # altro gruppo): il parametro va a zero nel buco invece di essere
    # interpolato dritto. Segmenti contigui restano una polilinea unica.
    envs = [
        ("v__a/density", [[0.0, 5], [1.0, 10]], "linear", 0.0, 10.0),
        ("v__b/density", [[0.0, 20], [1.0, 40]], "linear", 30.0, 10.0),
    ]
    merged = _merge_by_param(envs, group="v")
    assert merged[0][1] == [[0.0, 5], [10.0, 10], [10.0, 0], [30.0, 0],
                            [30.0, 20], [40.0, 40]]

    contiguo = [
        ("v__a/density", [[0.0, 5], [1.0, 10]], "linear", 0.0, 10.0),
        ("v__b/density", [[0.0, 20], [1.0, 40]], "linear", 10.0, 10.0),
    ]
    assert _merge_by_param(contiguo, group="v")[0][1] == [
        [0.0, 5], [10.0, 10], [10.0, 20], [20.0, 40]]
