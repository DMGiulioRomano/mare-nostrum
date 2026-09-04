import numpy as np

from granstudies import descriptors


def test_silence():
    sr = 8000
    sig = np.zeros(sr)
    d = descriptors.describe_array(sig, sr)
    assert d["rms"] == 0.0
    assert d["peak"] == 0.0
    assert d["zero_crossing_rate"] == 0.0
    assert d["spectral_centroid"] == 0.0
    assert d["active_ratio"] == 0.0
    assert d["duration_sec"] == 1.0


def test_sine_centroid_near_frequency():
    sr = 8000
    f = 440.0
    t = np.arange(sr) / sr
    sig = 0.5 * np.sin(2 * np.pi * f * t)
    d = descriptors.describe_array(sig, sr)
    assert abs(d["spectral_centroid"] - f) < 30.0     # centroide vicino a 440 Hz
    assert abs(d["rms"] - 0.5 / np.sqrt(2)) < 0.01
    assert d["active_ratio"] > 0.95                    # sempre attivo


def test_noise_centroid_higher_than_sine():
    sr = 8000
    rng = np.random.default_rng(0)
    noise = rng.standard_normal(sr)
    t = np.arange(sr) / sr
    sine = np.sin(2 * np.pi * 200 * t)
    assert (
        descriptors.spectral_centroid(noise, sr)
        > descriptors.spectral_centroid(sine, sr)
    )


def test_crest_factor_sine():
    sr = 8000
    t = np.arange(sr) / sr
    sig = np.sin(2 * np.pi * 100 * t)
    # crest factor di una sinusoide ~ sqrt(2)
    assert abs(descriptors.crest_factor(sig) - np.sqrt(2)) < 0.05
