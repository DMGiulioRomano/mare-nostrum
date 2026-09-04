"""Descrittori audio elementari calcolati in NumPy (zero dipendenze esterne).

Servono a quantificare le varianti per la curation e la matrice di parentela.
Tutti i descrittori sono deterministici e definiti su un array mono.
"""
from __future__ import annotations

from typing import Dict

import numpy as np


def _to_mono(samples: np.ndarray) -> np.ndarray:
    if samples.ndim > 1:
        samples = np.mean(samples, axis=1)
    return samples.astype(np.float64, copy=False)


def rms(samples: np.ndarray) -> float:
    if samples.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(samples))))


def peak(samples: np.ndarray) -> float:
    if samples.size == 0:
        return 0.0
    return float(np.max(np.abs(samples)))


def zero_crossing_rate(samples: np.ndarray) -> float:
    """Frazione di campioni adiacenti con cambio di segno (in [0, 1])."""
    if samples.size < 2:
        return 0.0
    signs = np.signbit(samples)
    return float(np.mean(signs[1:] != signs[:-1]))


def spectral_centroid(samples: np.ndarray, sr: int) -> float:
    """Centroide spettrale (Hz), media pesata delle frequenze sul modulo FFT."""
    if samples.size == 0:
        return 0.0
    spectrum = np.abs(np.fft.rfft(samples))
    freqs = np.fft.rfftfreq(samples.size, d=1.0 / sr)
    total = float(np.sum(spectrum))
    if total <= 0.0:
        return 0.0
    return float(np.sum(freqs * spectrum) / total)


def crest_factor(samples: np.ndarray) -> float:
    """Peak/RMS: alto per texture impulsive/sparse, basso per texture dense."""
    r = rms(samples)
    if r <= 0.0:
        return 0.0
    return peak(samples) / r


def active_ratio(samples: np.ndarray, sr: int, frame_ms: float = 20.0) -> float:
    """Frazione di frame con energia sopra una soglia relativa al picco.

    Proxy di densita' percepita: 1.0 = sempre attivo, ~0 = grani molto radi.
    """
    if samples.size == 0:
        return 0.0
    frame = max(1, int(sr * frame_ms / 1000.0))
    n_frames = samples.size // frame
    if n_frames == 0:
        return 1.0 if rms(samples) > 0 else 0.0
    trimmed = samples[: n_frames * frame].reshape(n_frames, frame)
    energies = np.sqrt(np.mean(np.square(trimmed), axis=1))
    peak_energy = float(np.max(energies))
    if peak_energy <= 0.0:
        return 0.0
    threshold = 0.1 * peak_energy
    return float(np.mean(energies >= threshold))


def describe_array(samples: np.ndarray, sr: int) -> Dict[str, float]:
    """Tutti i descrittori per un array mono."""
    mono = _to_mono(samples)
    return {
        "duration_sec": float(mono.size / sr) if sr else 0.0,
        "rms": rms(mono),
        "peak": peak(mono),
        "crest_factor": crest_factor(mono),
        "zero_crossing_rate": zero_crossing_rate(mono),
        "spectral_centroid": spectral_centroid(mono, sr),
        "active_ratio": active_ratio(mono, sr),
    }


def describe_file(audio_path: str) -> Dict[str, float]:
    """Carica un file audio e ne calcola i descrittori."""
    import soundfile as sf

    samples, sr = sf.read(audio_path)
    return describe_array(np.asarray(samples), sr)
