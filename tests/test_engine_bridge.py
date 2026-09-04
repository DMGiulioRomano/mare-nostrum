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


def test_parameter_bounds_static_registry():
    """Senza output_sr: bounds statici del registry (comportamento storico)."""
    pb = engine_bridge.parameter_bounds()
    assert pb["grain_duration"].min_val == 0.001
    assert pb["density"].max_val == 4000.0


def test_parameter_bounds_dynamic_output_sr():
    """Con output_sr: min di grain_duration = 1 campione (1/output_sr),
    come calcolato dall'engine per ogni render reale (issue #17)."""
    pb = engine_bridge.parameter_bounds(output_sr=48000)
    assert pb["grain_duration"].min_val == 1.0 / 48000
    # gli altri parametri restano statici
    assert pb["density"].max_val == 4000.0
