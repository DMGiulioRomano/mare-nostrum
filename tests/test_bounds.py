import pytest

from granstudies import bounds


def test_bounds_from_engine_registry():
    # density: [0.01, 4000] dal registry dell'engine
    lo, hi = bounds.bounds_for("density")
    assert lo == 0.01 and hi == 4000.0


def test_bounds_nested_path():
    lo, hi = bounds.bounds_for("grain.duration")
    assert lo == 0.001 and hi == 10.0


def test_bounds_manual_pitch():
    assert bounds.bounds_for("pitch.semitones") == (-36.0, 36.0)


def test_bounds_unknown_path():
    assert bounds.bounds_for("non.esiste") is None


def test_clamp_within_and_outside():
    assert bounds.clamp("density", 50) == 50
    assert bounds.clamp("density", -5) == 0.01
    assert bounds.clamp("density", 99999) == 4000.0
    # path sconosciuto: no-op
    assert bounds.clamp("non.esiste", 12345) == 12345


def test_bounds_grain_duration_dynamic_output_sr():
    # con output_sr il minimo e' il floor dello studio: 4 campioni (bounds.py)
    lo, hi = bounds.bounds_for("grain.duration", output_sr=48000)
    assert lo == bounds.MIN_GRAIN_SAMPLES / 48000
    assert hi == 10.0


def test_bounds_output_sr_ignored_for_other_paths():
    # output_sr non tocca i parametri senza bound dinamico
    assert bounds.bounds_for("density", output_sr=48000) == (0.01, 4000.0)
    assert bounds.bounds_for("pitch.semitones", output_sr=48000) == (-36.0, 36.0)


def test_grain_duration_factor_per_unita():
    assert bounds.grain_duration_factor(None) == 1.0
    assert bounds.grain_duration_factor("seconds") == 1.0
    assert bounds.grain_duration_factor("milliseconds") == 0.001
    assert bounds.grain_duration_factor("samples", 48000) == 1 / 48000


def test_grain_duration_factor_samples_pretende_output_sr():
    # 'samples' e' l'unica unita' che dipende dal sample rate
    with pytest.raises(ValueError, match="output_sr"):
        bounds.grain_duration_factor("samples")
    assert bounds.grain_duration_factor("milliseconds") == 0.001


def test_grain_duration_factor_unita_sconosciuta():
    with pytest.raises(ValueError, match="sconosciuta"):
        bounds.grain_duration_factor("frames")


def test_clamp_grain_duration_in_millisecondi():
    # bounds in secondi [4/48000, 10] -> in ms [1/12, 10000]
    lo_ms = bounds.MIN_GRAIN_SAMPLES / 48000 * 1000
    assert bounds.clamp(
        "grain.duration", 50, output_sr=48000, unit="milliseconds"
    ) == 50
    assert bounds.clamp(
        "grain.duration", 0.0001, output_sr=48000, unit="milliseconds"
    ) == pytest.approx(lo_ms)
    assert bounds.clamp(
        "grain.duration", 99999, output_sr=48000, unit="milliseconds"
    ) == pytest.approx(10_000.0)


def test_clamp_grain_duration_in_campioni():
    assert bounds.clamp(
        "grain.duration", 50, output_sr=48000, unit="samples"
    ) == 50
    assert bounds.clamp(
        "grain.duration", 1, output_sr=48000, unit="samples"
    ) == pytest.approx(bounds.MIN_GRAIN_SAMPLES)


def test_span():
    assert bounds.span("distribution") == 1.0
    assert bounds.span("pitch.semitones") == 72.0
    assert bounds.span("non.esiste") is None


def test_volume_ceiling_patched():
    # il tetto engine (+12 dB) e' alzato a runtime da engine_bridge
    from granstudies.engine_bridge import VOLUME_MAX_DB
    from pge.parameters.parameter_definitions import get_parameter_definition

    assert bounds.bounds_for("volume") == (-120.0, VOLUME_MAX_DB)
    # il patch vale anche per il parser dell'engine, non solo per bounds.py
    assert get_parameter_definition("volume").max_val == VOLUME_MAX_DB
    assert bounds.clamp("volume", 999) == VOLUME_MAX_DB
