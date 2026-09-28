"""Smoke test d'integrazione: rendering reale attraverso il submodule engine.

Richiede il submodule ``engine/`` inizializzato. Genera un sample sintetico,
renderizza un YAML minimale e verifica che esca audio non vuoto + partitura PDF.
"""
import os

import numpy as np
import soundfile as sf
import yaml
import pytest

from granstudies import engine_bridge


pytestmark = pytest.mark.skipif(
    not os.path.isdir(engine_bridge.ENGINE_SRC),
    reason="submodule engine non inizializzato",
)


def _minimal_doc(sample_name):
    return {
        "streams": [
            {
                "stream_id": "s",
                "onset": 0,
                "duration": 1,
                "sample": sample_name,
                "time_mode": "absolute",
                "density": 30,
                "distribution": 0.5,
                "grain": {"duration": 0.05, "envelope": "hanning"},
                "pitch": {"semitones": 0},
                "pointer": {"start": 0, "speed_ratio": 1},
                "pan": 0,
                "volume": -6,
            }
        ]
    }


@pytest.fixture
def studio(tmp_path):
    samples = tmp_path / "samples"
    samples.mkdir()
    sr = 44100
    t = np.arange(sr) / sr
    sf.write(str(samples / "test.wav"), 0.5 * np.sin(2 * np.pi * 220 * t), sr)

    yaml_path = tmp_path / "mini.yml"
    with open(yaml_path, "w", encoding="utf-8") as fh:
        yaml.safe_dump(_minimal_doc("test.wav"), fh)
    return tmp_path, samples, yaml_path


def test_render_produces_nonempty_audio(studio):
    tmp_path, samples, yaml_path = studio
    out = tmp_path / "out.aif"
    generated = engine_bridge.render(
        str(yaml_path), str(out), samples_dir=str(samples)
    )
    assert generated
    audio_path = generated[0]
    assert os.path.exists(audio_path)
    data, sr = sf.read(audio_path)
    assert data.size > 0
    assert float(np.max(np.abs(data))) > 0.0   # non silenzio


def test_score_pdf_is_created(studio):
    tmp_path, samples, yaml_path = studio
    pdf = tmp_path / "out.pdf"
    engine_bridge.score_pdf(str(yaml_path), str(pdf), samples_dir=str(samples))
    assert pdf.exists() and pdf.stat().st_size > 0


def test_render_jobs_activates_parallel_path_without_changing_audio(tmp_path):
    """`jobs` arriva fino all'engine e non cambia il suono.

    Il chunk-parallel dell'engine scatta solo sopra 1024 grani
    (DEFAULT_MIN_PARALLEL_GRAINS), quindi qui il documento e' denso apposta:
    con density 1000 su 2s si superano i 2000 grani e il path parallelo viene
    davvero esercitato. L'engine garantisce identita' entro 1 LSB a 24 bit
    (cambia solo l'ordine delle somme float64).
    """
    samples = tmp_path / "samples"
    samples.mkdir()
    sr = 44100
    t = np.arange(sr) / sr
    sf.write(str(samples / "test.wav"), 0.5 * np.sin(2 * np.pi * 220 * t), sr)

    doc = _minimal_doc("test.wav")
    # Senza seed esplicito l'engine ne estrae uno di sessione diverso a ogni
    # run: i due render non sarebbero confrontabili.
    doc["seed"] = 4242
    doc["streams"][0]["duration"] = 2
    doc["streams"][0]["density"] = 1000
    yaml_path = tmp_path / "denso.yml"
    with open(yaml_path, "w", encoding="utf-8") as fh:
        yaml.safe_dump(doc, fh)

    seq = engine_bridge.render(
        str(yaml_path), str(tmp_path / "seq.aif"),
        samples_dir=str(samples), jobs=1,
    )[0]
    par = engine_bridge.render(
        str(yaml_path), str(tmp_path / "par.aif"),
        samples_dir=str(samples), jobs=4,
    )[0]

    a, _ = sf.read(seq, always_2d=True)
    b, _ = sf.read(par, always_2d=True)
    assert a.shape == b.shape
    assert float(np.max(np.abs(a))) > 0.0
    assert float(np.max(np.abs(a - b))) <= 2.0 ** -23   # 1 LSB a 24 bit


def test_parameter_bounds_static_registry():
    """Senza output_sr: bounds statici del registry (comportamento storico)."""
    pb = engine_bridge.parameter_bounds()
    assert pb["grain_duration"].min_val == 0.001
    assert pb["density"].max_val is None  # tetto tolto nell'engine (#272)


def test_parameter_bounds_dynamic_output_sr():
    """Con output_sr: min di grain_duration = 1 campione (1/output_sr),
    come calcolato dall'engine per ogni render reale (issue #17)."""
    pb = engine_bridge.parameter_bounds(output_sr=48000)
    assert pb["grain_duration"].min_val == 1.0 / 48000
    # gli altri parametri restano statici
    assert pb["density"].min_val == 0.01


def _env(punti):
    engine_bridge._ensure_engine_on_path()
    from pge.envelopes.envelope import Envelope

    return Envelope(punti)


def test_la_spezzata_tiene_il_gradino_esatto():
    """Un `step` campionato fitto resterebbe una rampa ripidissima.

    Il salto e' due punti allo stesso tempo, come il `steps-post` della
    partitura; il segmento lineare che segue resta campionato.
    """
    sp = engine_bridge._spezzata(_env([[0, 1, "step"], [5, 4], [10, 1]]), 10.0, 20)
    assert sp[0] == (0.0, 1.0)
    assert sp[1] == (5.0, 1.0) and sp[2] == (5.0, 4.0)   # l'angolo, poi il salto
    assert sp[-1] == (10.0, 1.0)
    # La rampa dopo il gradino e' campionata, non due punti soli.
    assert len([p for p in sp if 5 < p[0] <= 10]) > 5


def test_la_spezzata_campiona_la_cubica_e_copre_lo_stream():
    """Una cubica non e' una retta fra i suoi breakpoint, e va guardata in mezzo.

    E fuori dai breakpoint la curva tiene il primo e l'ultimo valore, come fa
    `evaluate`: la spezzata arriva comunque a fine stream.
    """
    cub = engine_bridge._spezzata(_env([[0, 0, "cubic"], [4, 1]]), 8.0, 40)
    lin = engine_bridge._spezzata(_env([[0, 0], [4, 1]]), 8.0, 40)
    # A meta' segmento la S ci passa lo stesso (e' simmetrica): il confronto
    # va fatto a un quarto, dove la cubica e' ancora seduta sulla partenza.
    a = lambda sp, t0: [v for t, v in sp if abs(t - t0) < 1e-9][0]
    assert a(cub, 1.0) < a(lin, 1.0) / 1.5
    assert abs(a(cub, 2.0) - a(lin, 2.0)) < 1e-9
    assert cub[-1][0] == 8.0 and cub[-1][1] == 1.0   # tiene fino in fondo


def test_i_grani_escono_disegnabili(studio):
    """Le colonne parallele sono la geometria della partitura, indice compreso.

    Il grano sta dentro il suo tempo (x .. x+w) e dentro il sample sull'asse
    di lettura; l'indice di palette e' un indice vero, non un colore da
    interpretare.
    """
    _tmp, samples, yaml_path = studio
    grani = engine_bridge.stream_analysis(
        str(yaml_path), str(samples))["grani"]
    assert grani["n"] == grani["tot"] > 0     # pochi grani: nessuna decimazione
    assert grani["passo"] == 1
    n = grani["n"]
    assert all(len(grani[c]) == n for c in ("x", "w", "y", "h", "k"))
    assert max(grani["x"]) + max(grani["w"]) <= 1.5   # stream di 1 s
    assert all(0 <= y <= grani["sample_dur"] for y in grani["y"])
    # pitch 0 semitoni: lettura in avanti, altezza = durata del grano.
    assert all(h > 0 for h in grani["h"])
    assert all(0 <= k < len(grani["palette"]) for k in grani["k"])


def test_i_grani_si_decimano_sopra_il_tetto(studio):
    """Sopra il tetto si manda un grano ogni N, e si dice quanti erano."""
    _tmp, samples, yaml_path = studio
    from granstudies import engine_bridge as eb

    grani = eb._grani(
        eb.load_generator(str(yaml_path), samples_dir=str(samples)).streams[0],
        massimo=5)
    assert grani["n"] <= 5 and grani["tot"] > 5
    assert grani["passo"] == -(-grani["tot"] // 5)
