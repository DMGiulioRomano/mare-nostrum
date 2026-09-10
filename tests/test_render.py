import os

import yaml

from granstudies.study_spec import parse_study_spec
from granstudies import render as render_mod
from granstudies.render import render_variants, write_variants


def _spec(mode):
    return parse_study_spec(
        {
            "study_id": "s",
            "base": {
                "sample": "x.wav",
                "duration": 6,
                "time_mode": "normalized",
                "grain": {"envelope": "hanning"},
            },
            "axes": {
                "density": {"path": "density", "baseline": 20, "values": [5, 50, 400]},
                "grain_duration": {
                    "path": "grain.duration",
                    "baseline": 0.05,
                    "values": [0.01, 0.05, 0.2],
                },
            },
            "sweep": {"mode": mode, "orders": [1, 2], "plateau": 5, "transition": 5},
        }
    )


def _load(path):
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _find(written, suffix):
    return next(p for p in written if p.endswith(suffix))


def test_write_discrete_goes_into_discrete_subdir(tmp_path):
    written = write_variants(_spec("discrete"), str(tmp_path))
    assert written
    assert all((os.sep + "discrete" + os.sep) in p for p in written)
    assert not os.path.isdir(tmp_path / "envelope")


def test_discrete_file_uses_base_duration(tmp_path):
    written = write_variants(_spec("discrete"), str(tmp_path))
    doc = _load(written[0])
    # base.duration finisce nello stream (file discrete statici)
    assert doc["streams"][0]["duration"] == 6


def test_write_envelope_goes_into_envelope_subdir(tmp_path):
    written = write_variants(_spec("envelope"), str(tmp_path))
    assert written
    assert all((os.sep + "envelope" + os.sep) in p for p in written)
    assert not os.path.isdir(tmp_path / "discrete")


def test_envelope_file_structure(tmp_path):
    written = write_variants(_spec("envelope"), str(tmp_path))
    doc = _load(_find(written, "e1__density.yml"))
    stream = doc["streams"][0]
    assert stream["time_mode"] == "normalized"
    # density e' l'asse mosso -> envelope wrappato
    assert stream["density"]["type"] == "linear"
    assert stream["density"]["time_mode"] == "normalized"
    assert isinstance(stream["density"]["points"], list)
    # grain.duration fermo al baseline (scalare)
    assert stream["grain"]["duration"] == 0.05
    # la base.duration statica e' sostituita dalla durata calcolata, sia a
    # livello stream (richiesta dall'engine, scala i tempi normalizzati) sia doc
    # N=3 -> 3*5 + 2*5 = 25
    assert stream["duration"] == 25
    assert doc["duration"] == 25


def test_envelope_o2_has_two_synchronized_envelopes(tmp_path):
    written = write_variants(_spec("envelope"), str(tmp_path))
    doc = _load(_find(written, "e2__density__grain_duration.yml"))
    stream = doc["streams"][0]
    assert stream["density"]["type"] == "linear"
    assert stream["grain"]["duration"]["type"] == "linear"
    # stessa griglia temporale (sincronizzati)
    assert (
        [t for t, _ in stream["density"]["points"]]
        == [t for t, _ in stream["grain"]["duration"]["points"]]
    )
    # N=9 -> 9*5 + 8*5 = 85
    assert doc["duration"] == 85


def _spec_mixed():
    return parse_study_spec(
        {
            "study_id": "s",
            "base": {"sample": "x.wav", "duration": 6, "time_mode": "normalized"},
            "axes": {
                "density": {"path": "density", "baseline": 20, "values": [5, 50, 400], "interpolation": "step"},
                "grain_duration": {"path": "grain.duration", "baseline": 0.05, "values": [0.01, 0.05, 0.2], "interpolation": "cubic"},
            },
            "sweep": {"mode": "envelope", "orders": [2], "plateau": 5, "transition": 5},
        }
    )


def test_envelope_o2_mixed_per_axis_types(tmp_path):
    written = write_variants(_spec_mixed(), str(tmp_path))
    doc = _load(_find(written, "e2__density__grain_duration.yml"))
    stream = doc["streams"][0]
    # type per-asse nel documento renderizzato
    assert stream["density"]["type"] == "step"
    assert stream["grain"]["duration"]["type"] == "cubic"
    # density (step) a punto singolo, grain (cubic) doppio-punto; sincronizzati
    assert len(stream["density"]["points"]) == 9
    assert len(stream["grain"]["duration"]["points"]) == 18
    assert doc["duration"] == 85


def test_both_mode_writes_both_sets(tmp_path):
    written = write_variants(_spec("both"), str(tmp_path))
    assert os.path.isdir(tmp_path / "discrete")
    assert os.path.isdir(tmp_path / "envelope")
    assert any((os.sep + "discrete" + os.sep) in p for p in written)
    assert any((os.sep + "envelope" + os.sep) in p for p in written)


# --- render incrementale ---------------------------------------------------

def test_dump_preserves_mtime_when_unchanged(tmp_path):
    written = write_variants(_spec("envelope"), str(tmp_path))
    past = 1_000_000_000
    for p in written:
        os.utime(p, (past, past))
    rewritten = write_variants(_spec("envelope"), str(tmp_path))
    assert sorted(rewritten) == sorted(written)
    assert all(os.path.getmtime(p) == past for p in written)


def _fake_engine_render(calls):
    def fake(yaml_path, output_path, samples_dir, output_sr=48000,
             per_stream=False, use_cache=False, cache_dir=None, jobs=1):
        calls.append(yaml_path)
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, "w") as fh:
            fh.write("x")
        return [output_path]

    return fake


def test_render_variants_skips_up_to_date(tmp_path, monkeypatch):
    variant_dir = str(tmp_path / "variants")
    n = len(write_variants(_spec("envelope"), variant_dir))
    calls = []
    monkeypatch.setattr(render_mod.engine_bridge, "render", _fake_engine_render(calls))
    kwargs = dict(
        variant_dir=variant_dir,
        audio_dir=str(tmp_path / "audio"),
        score_dir=None,
        samples_dir="unused",
        jobs=1,
    )
    first = render_variants(**kwargs)
    assert len(calls) == n
    assert not any(e["skipped"] for e in first)
    # secondo giro: tutto aggiornato, nessun render
    second = render_variants(**kwargs)
    assert len(calls) == n
    assert all(e["skipped"] for e in second)
    # force: rirenderizza tutto
    third = render_variants(**kwargs, force=True)
    assert len(calls) == 2 * n
    assert not any(e["skipped"] for e in third)


def test_render_variants_rerenders_only_changed(tmp_path, monkeypatch):
    variant_dir = str(tmp_path / "variants")
    written = write_variants(_spec("envelope"), variant_dir)
    calls = []
    monkeypatch.setattr(render_mod.engine_bridge, "render", _fake_engine_render(calls))
    kwargs = dict(
        variant_dir=variant_dir,
        audio_dir=str(tmp_path / "audio"),
        score_dir=None,
        samples_dir="unused",
        jobs=1,
    )
    render_variants(**kwargs)
    calls.clear()
    # tocco un solo YAML -> si rirenderizza solo quello
    changed = written[0]
    now = os.path.getmtime(changed) + 10
    os.utime(changed, (now, now))
    manifest = render_variants(**kwargs)
    assert calls == [changed]
    assert sum(1 for e in manifest if not e["skipped"]) == 1


# --- confronto golden: documento YAML completo letto da disco -------------------

def _golden_spec(orders):
    # spec minimale e deterministica per confronti byte-equivalenti
    return parse_study_spec(
        {
            "study_id": "golden",
            "seed": 1988,
            "base": {
                "sample": "corpus.wav",
                "onset": 0,
                "duration": 6,
                "time_mode": "normalized",
            },
            "axes": {
                "density": {"path": "density", "baseline": 20, "values": [5, 50, 400]},
                "grain_duration": {
                    "path": "grain.duration",
                    "baseline": 0.05,
                    "values": [0.01, 0.05, 0.2],
                },
            },
            "sweep": {"mode": "envelope", "orders": orders, "plateau": 5, "transition": 5},
        }
    )


def test_golden_e1_density_full_document(tmp_path):
    # Confronta l'INTERO documento scritto (round-trip su disco) con l'atteso.
    # I breakpoint replicano l'esempio della issue: densita'=[5,50,400], 25s.
    written = write_variants(_golden_spec([1]), str(tmp_path))
    doc = _load(_find(written, "e1__density.yml"))
    assert doc == {
        "title": "golden :: e1__density",
        "seed": 1988,
        "duration": 25.0,
        "streams": [
            {
                "sample": "corpus.wav",
                "onset": 0,
                "time_mode": "normalized",
                "stream_id": "stream",
                "duration": 25.0,
                "density": {
                    "type": "linear",
                    "points": [
                        [0.0, 5],
                        [0.2, 5],
                        [0.4, 50],
                        [0.6, 50],
                        [0.8, 400],
                        [1.0, 400],
                    ],
                    "time_mode": "normalized",
                },
                "grain": {"duration": 0.05},
            }
        ],
    }


def test_golden_e2_synchronized_points_exact(tmp_path):
    # I due assi mossi devono avere ESATTAMENTE gli stessi tempi e i valori
    # del prodotto cartesiano lessicografico, su 9 plateau (85s).
    written = write_variants(_golden_spec([2]), str(tmp_path))
    doc = _load(_find(written, "e2__density__grain_duration.yml"))
    stream = doc["streams"][0]
    assert doc["duration"] == 85.0
    assert stream["duration"] == 85.0

    # tempi attesi: 9 plateau, W_plateau = W_transition = 5/85
    w = 5 / 85
    expected_times = []
    for i in range(9):
        t_start = i * (w + w)
        expected_times.append(round(t_start, 6))
        expected_times.append(round(t_start + w, 6))
    expected_times[0] = 0.0
    expected_times[-1] = 1.0

    dens_times = [t for t, _ in stream["density"]["points"]]
    grain_times = [t for t, _ in stream["grain"]["duration"]["points"]]
    assert dens_times == expected_times
    assert grain_times == expected_times

    # valori per plateau (uno ogni 2 breakpoint) = prodotto lessicografico
    dens_vals = [v for _, v in stream["density"]["points"]][0::2]
    grain_vals = [v for _, v in stream["grain"]["duration"]["points"]][0::2]
    assert dens_vals == [5, 5, 5, 50, 50, 50, 400, 400, 400]
    assert grain_vals == [0.01, 0.05, 0.2, 0.01, 0.05, 0.2, 0.01, 0.05, 0.2]


# --- processo stack: scrittura documento + render ---------------------------------

def _stack_specs():
    from granstudies.study_spec import resolve_streams

    return resolve_streams(
        {
            "study_id": "s",
            "seed": 1,
            "base": {"sample": "x.wav", "duration": 30},
            "axes": {
                "density": {"path": "density", "baseline": 20, "values": [5, 50, 400]},
            },
            "stack": {},
            "streams": {"voce_a": {}, "voce_b": {}},
        }
    )


def test_write_stack_single_document(tmp_path):
    from granstudies.render import write_stack

    written = write_stack(_stack_specs(), str(tmp_path))
    assert written == [str(tmp_path / "stack" / "stack.yml")]
    doc = _load(written[0])
    assert len(doc["streams"]) == 2


def test_render_picks_up_stack_document(tmp_path, monkeypatch):
    from granstudies.render import write_stack

    yaml_dir = str(tmp_path / "yaml")
    write_stack(_stack_specs(), yaml_dir)
    calls = []
    monkeypatch.setattr(render_mod.engine_bridge, "render", _fake_engine_render(calls))
    manifest = render_variants(
        variant_dir=yaml_dir,
        audio_dir=str(tmp_path / "audio"),
        score_dir=None,
        samples_dir="unused",
        jobs=1,
    )
    assert len(manifest) == 1
    # niente prefisso di stream: stack/stack.yml -> audio/stack/stack.aif
    assert manifest[0]["audio"] == str(tmp_path / "audio" / "stack" / "stack.aif")
    assert os.path.exists(manifest[0]["audio"])


# --- issue #24: post-merge degli stem di versions per nome-base -------------------

def _write_stem(path, seconds, sr=1000, value=0.5):
    import numpy as np
    import soundfile as sf

    data = np.full((round(seconds * sr), 2), value, dtype="float64")
    sf.write(str(path), data, sr, format="AIFF")


def _versions_doc(tmp_path):
    """Documento stack in stile versions: 2 voci logiche x 2 combinazioni."""
    doc = {
        "duration": 4,
        "streams": [
            {"stream_id": "fermo__d=1", "onset": 0, "duration": 2},
            {"stream_id": "fermo__d=2", "onset": 2, "duration": 2},
            {"stream_id": "mobile__d=1", "onset": 0, "duration": 2},
            {"stream_id": "mobile__d=2", "onset": 2, "duration": 2},
        ],
    }
    yaml_path = tmp_path / "stack.yml"
    yaml_path.write_text(yaml.safe_dump(doc))
    return str(yaml_path)


def test_merge_stems_by_base_overlay_adds_at_onset(tmp_path):
    import numpy as np
    import soundfile as sf
    from granstudies.render import merge_stems_by_base

    yaml_path = _versions_doc(tmp_path)
    audio_dir = tmp_path / "audio"
    audio_dir.mkdir()
    # Gli stem dell'engine hanno onset RELATIVO (partono dal proprio onset,
    # lunghi quanto la durata dello stream): il merge li posiziona all'onset.
    stems = []
    for sid, value in [("fermo__d=1", 0.25), ("fermo__d=2", 0.5),
                       ("mobile__d=1", 0.1), ("mobile__d=2", 0.2)]:
        p = audio_dir / f"stack__{sid}.aif"
        _write_stem(p, seconds=2.0, value=value)
        stems.append(str(p))

    merged = merge_stems_by_base(yaml_path, str(audio_dir / "stack.aif"), stems)
    assert sorted(os.path.basename(p) for p in merged) == [
        "stack__fermo.aif", "stack__mobile.aif",
    ]
    data, sr = sf.read(str(audio_dir / "stack__fermo.aif"), always_2d=True)
    assert sr == 1000
    assert len(data) == 4000                       # max(onset + len) = 4s
    assert np.allclose(data[:2000], 0.25, atol=1e-3)
    assert np.allclose(data[2000:], 0.5, atol=1e-3)
    data, _sr = sf.read(str(audio_dir / "stack__mobile.aif"), always_2d=True)
    assert np.allclose(data[:2000], 0.1, atol=1e-3)
    assert np.allclose(data[2000:], 0.2, atol=1e-3)


def test_merge_stems_by_base_skips_streams_without_suffix(tmp_path):
    from granstudies.render import merge_stems_by_base

    doc = {"duration": 2, "streams": [
        {"stream_id": "voce_a", "onset": 0, "duration": 2},
        {"stream_id": "voce_b", "onset": 0, "duration": 2},
    ]}
    yaml_path = tmp_path / "stack.yml"
    yaml_path.write_text(yaml.safe_dump(doc))
    audio_dir = tmp_path / "audio"
    audio_dir.mkdir()
    stems = []
    for sid in ("voce_a", "voce_b"):
        p = audio_dir / f"stack__{sid}.aif"
        _write_stem(p, seconds=2.0)
        stems.append(str(p))
    merged = merge_stems_by_base(str(yaml_path), str(audio_dir / "stack.aif"), stems)
    assert merged == []
    assert sorted(os.listdir(audio_dir)) == [
        "stack__voce_a.aif", "stack__voce_b.aif",
    ]


def test_merge_stems_by_base_singleton_group_not_merged(tmp_path):
    # Un solo stem per nome-base (anche se suffissato): niente file accorpato,
    # stack_stems_to_sv continuera' a consumare lo stem grezzo.
    from granstudies.render import merge_stems_by_base

    doc = {"duration": 2, "streams": [
        {"stream_id": "fermo__d=1", "onset": 0, "duration": 2},
    ]}
    yaml_path = tmp_path / "stack.yml"
    yaml_path.write_text(yaml.safe_dump(doc))
    audio_dir = tmp_path / "audio"
    audio_dir.mkdir()
    p = audio_dir / "stack__fermo__d=1.aif"
    _write_stem(p, seconds=2.0)
    merged = merge_stems_by_base(str(yaml_path), str(audio_dir / "stack.aif"), [str(p)])
    assert merged == []
    assert not os.path.exists(audio_dir / "stack__fermo.aif")


def test_merge_stems_by_base_incremental(tmp_path):
    from granstudies.render import merge_stems_by_base

    yaml_path = _versions_doc(tmp_path)
    audio_dir = tmp_path / "audio"
    audio_dir.mkdir()
    stems = []
    for sid in ("fermo__d=1", "fermo__d=2", "mobile__d=1", "mobile__d=2"):
        p = audio_dir / f"stack__{sid}.aif"
        _write_stem(p, seconds=2.0)
        stems.append(str(p))
    mix = str(audio_dir / "stack.aif")
    merged = merge_stems_by_base(yaml_path, mix, stems)
    first = {p: os.path.getmtime(p) for p in merged}
    # niente stem cambiato -> nessuna riscrittura
    merged2 = merge_stems_by_base(yaml_path, mix, stems)
    assert sorted(merged2) == sorted(merged)
    assert all(os.path.getmtime(p) == first[p] for p in merged)
    # uno stem di fermo piu' nuovo -> si rigenera solo stack__fermo.aif
    later = max(first.values()) + 10
    os.utime(stems[0], (later, later))
    merge_stems_by_base(yaml_path, mix, stems)
    fermo = str(audio_dir / "stack__fermo.aif")
    mobile = str(audio_dir / "stack__mobile.aif")
    assert os.path.getmtime(fermo) > first[fermo]
    assert os.path.getmtime(mobile) == first[mobile]


def test_merge_stems_by_base_regenerates_when_document_changes(tmp_path):
    # Gruppo che si riduce (5 -> 3 combinazioni in study.yml): gli stem correnti
    # sono piu' vecchi del file accorpato, ma il documento e' stato riscritto.
    # La composizione del gruppo deriva SOLO dal documento, quindi il check
    # incrementale deve includere anche l'mtime dello YAML — altrimenti il file
    # accorpato resterebbe con l'audio delle combinazioni rimosse.
    import soundfile as sf
    from granstudies.render import merge_stems_by_base

    audio_dir = tmp_path / "audio"
    audio_dir.mkdir()
    stems = []
    for k in (1, 2, 3):
        p = audio_dir / f"stack__fermo__d={k}.aif"
        _write_stem(p, seconds=2.0)
        stems.append(str(p))

    def _write_doc(n):
        doc = {"duration": 2 * n, "streams": [
            {"stream_id": f"fermo__d={k}", "onset": 2 * (k - 1), "duration": 2}
            for k in range(1, n + 1)
        ]}
        (tmp_path / "stack.yml").write_text(yaml.safe_dump(doc))

    yaml_path = str(tmp_path / "stack.yml")
    mix = str(audio_dir / "stack.aif")
    _write_doc(3)
    merged = merge_stems_by_base(yaml_path, mix, stems)
    data, _sr = sf.read(merged[0], always_2d=True)
    assert len(data) == 6000

    # il documento si riduce a 2 combinazioni; gli stem restanti non cambiano
    _write_doc(2)
    later = os.path.getmtime(merged[0]) + 10
    os.utime(yaml_path, (later, later))
    merged = merge_stems_by_base(yaml_path, mix, stems[:2])
    data, _sr = sf.read(merged[0], always_2d=True)
    assert len(data) == 4000


def test_merge_stems_by_base_unknown_stream_id_raises(tmp_path):
    # Uno stem suffissato il cui stream_id non esiste nel documento e' un
    # disallineamento tra naming dell'engine e YAML: default silenzioso a
    # onset 0 sommerebbe audio che non devono coesistere. Errore esplicito.
    import pytest
    from granstudies.render import merge_stems_by_base

    doc = {"duration": 4, "streams": [
        {"stream_id": "fermo__d=1", "onset": 0, "duration": 2},
        {"stream_id": "fermo__d=2", "onset": 2, "duration": 2},
    ]}
    yaml_path = tmp_path / "stack.yml"
    yaml_path.write_text(yaml.safe_dump(doc))
    audio_dir = tmp_path / "audio"
    audio_dir.mkdir()
    stems = []
    for sid in ("fermo__d=1", "fermo__d=9"):   # d=9 non esiste nel documento
        p = audio_dir / f"stack__{sid}.aif"
        _write_stem(p, seconds=2.0)
        stems.append(str(p))
    with pytest.raises(ValueError, match="fermo__d=9"):
        merge_stems_by_base(str(yaml_path), str(audio_dir / "stack.aif"), stems)


def test_render_variants_per_stream_merges_version_stems(tmp_path, monkeypatch):
    # La pass STEMS di _render_one deve produrre anche i file accorpati per
    # nome-base, senza toccare gli stem originali.
    import soundfile as sf

    yaml_dir = tmp_path / "yaml" / "stack"
    yaml_dir.mkdir(parents=True)
    doc = {"duration": 4, "streams": [
        {"stream_id": "fermo__d=1", "onset": 0, "duration": 2},
        {"stream_id": "fermo__d=2", "onset": 2, "duration": 2},
    ]}
    (yaml_dir / "stack.yml").write_text(yaml.safe_dump(doc))

    def fake(yaml_path, output_path, samples_dir, output_sr=48000,
             per_stream=False, use_cache=False, cache_dir=None, jobs=1):
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        if not per_stream:
            with open(output_path, "w") as fh:
                fh.write("x")
            return [output_path]
        base, ext = os.path.splitext(output_path)
        out = []
        with open(yaml_path, "r", encoding="utf-8") as fh:
            for stream in yaml.safe_load(fh)["streams"]:
                p = f"{base}__{stream['stream_id']}{ext}"
                _write_stem(p, seconds=2.0)
                out.append(p)
        return out

    monkeypatch.setattr(render_mod.engine_bridge, "render", fake)
    manifest = render_variants(
        variant_dir=str(tmp_path / "yaml"),
        audio_dir=str(tmp_path / "audio"),
        score_dir=None,
        samples_dir="unused",
        per_stream=True,
        cache_dir=str(tmp_path / "cache"),
        jobs=1,
    )
    assert len(manifest) == 1
    merged = manifest[0]["stems_merged"]
    assert [os.path.basename(p) for p in merged] == ["stack__fermo.aif"]
    data, sr = sf.read(merged[0], always_2d=True)
    assert len(data) == 4000
    # gli stem originali restano al loro posto
    assert os.path.exists(str(tmp_path / "audio" / "stack" / "stack__fermo__d=1.aif"))


def test_render_audio_basename_includes_study_prefix(tmp_path, monkeypatch):
    # Regressione PR #30: cmd_sv cerca {study}_{stream}_{variante}.aif, ma il
    # render scriveva {stream}_{variante}.aif. Con study= il basename audio
    # delle varianti sweep include il prefisso dello studio.
    variant_root = str(tmp_path / "yaml")
    spec = _spec("envelope")
    spec = __import__("dataclasses").replace(spec, stream_id="vox")
    write_variants(spec, os.path.join(variant_root, "sweep"))
    calls = []
    monkeypatch.setattr(render_mod.engine_bridge, "render", _fake_engine_render(calls))
    manifest = render_variants(
        variant_dir=variant_root,
        audio_dir=str(tmp_path / "audio"),
        score_dir=None,
        samples_dir="unused",
        jobs=1,
        study="s01",
    )
    names = [os.path.basename(e["audio"]) for e in manifest]
    assert names
    assert all(n.startswith("s01_vox_") for n in names)


def test_render_study_prefix_without_stream_subdir(tmp_path, monkeypatch):
    # Layout senza stream (yaml/sweep/envelope/<variante>.yml): cmd_sv si
    # aspetta {study}_{variante}.aif, quindi il prefisso si applica comunque.
    variant_root = str(tmp_path / "yaml")
    written = write_variants(_spec("envelope"), os.path.join(variant_root, "sweep"))
    calls = []
    monkeypatch.setattr(render_mod.engine_bridge, "render", _fake_engine_render(calls))
    manifest = render_variants(
        variant_dir=variant_root,
        audio_dir=str(tmp_path / "audio"),
        score_dir=None,
        samples_dir="unused",
        jobs=1,
        study="s01",
    )
    expected = sorted(
        "s01_" + os.path.splitext(os.path.basename(p))[0] + ".aif" for p in written
    )
    assert sorted(os.path.basename(e["audio"]) for e in manifest) == expected


def test_render_study_prefix_leaves_documents_alone(tmp_path, monkeypatch):
    # I documenti dei processi (stack/versions/percorso) restano senza
    # prefisso: cmd_sv li cerca per nome processo ({process}.aif).
    from granstudies.render import write_stack

    yaml_dir = str(tmp_path / "yaml")
    write_stack(_stack_specs(), yaml_dir)
    calls = []
    monkeypatch.setattr(render_mod.engine_bridge, "render", _fake_engine_render(calls))
    manifest = render_variants(
        variant_dir=yaml_dir,
        audio_dir=str(tmp_path / "audio"),
        score_dir=None,
        samples_dir="unused",
        jobs=1,
        study="s01",
    )
    assert [os.path.basename(e["audio"]) for e in manifest] == ["stack.aif"]


def test_render_stream_prefix_relative_to_mode_dir(tmp_path, monkeypatch):
    # Nuovo layout: yaml/sweep/envelope/<stream>/<nome>.yml — il basename audio
    # va prefissato col nome dello stream anche con la cartella sweep/ in mezzo.
    variant_root = str(tmp_path / "yaml")
    spec = _spec("envelope")
    spec = __import__("dataclasses").replace(spec, stream_id="vox")
    write_variants(spec, os.path.join(variant_root, "sweep"))
    calls = []
    monkeypatch.setattr(render_mod.engine_bridge, "render", _fake_engine_render(calls))
    manifest = render_variants(
        variant_dir=variant_root,
        audio_dir=str(tmp_path / "audio"),
        score_dir=None,
        samples_dir="unused",
        jobs=1,
    )
    audio = sorted(e["audio"] for e in manifest)
    assert all(os.sep + os.path.join("sweep", "envelope", "vox", "vox_") in a for a in audio)


# --- ripartizione dei job tra i due livelli di parallelismo -----------------


def test_split_jobs_single_variant_takes_whole_budget():
    # Il caso di grana-001-41: una variante lunghissima. Il pool esterno non ha
    # niente da parallelizzare, quindi tutto il budget va all'engine.
    assert render_mod._split_jobs(8, 1) == (1, 8)


def test_split_jobs_saturated_pool_keeps_engine_sequential():
    # Varianti >= budget: il pool esterno satura la macchina da solo, l'engine
    # resta sequenziale (comportamento storico).
    assert render_mod._split_jobs(4, 4) == (4, 1)
    assert render_mod._split_jobs(4, 40) == (4, 1)


def test_split_jobs_budget_one_is_fully_sequential():
    assert render_mod._split_jobs(1, 1) == (1, 1)
    assert render_mod._split_jobs(1, 10) == (1, 1)


def test_split_jobs_never_oversubscribes():
    for budget in range(1, 13):
        for pending in range(1, 13):
            workers, engine_jobs = render_mod._split_jobs(budget, pending)
            assert workers >= 1 and engine_jobs >= 1
            assert workers <= pending
            assert workers * engine_jobs <= budget


def test_render_passes_engine_jobs_to_bridge(tmp_path, monkeypatch):
    # Regressione: engine_bridge.render veniva chiamato senza `jobs`, quindi
    # l'engine restava a jobs=1 e il chunk-parallel non si attivava mai.
    variant_dir = str(tmp_path / "variants")
    os.makedirs(variant_dir)
    with open(os.path.join(variant_dir, "solo.yml"), "w", encoding="utf-8") as fh:
        yaml.safe_dump({"streams": [{"stream_id": "s", "onset": 0}]}, fh)

    seen = []

    def fake(yaml_path, output_path, samples_dir, output_sr=48000,
             per_stream=False, use_cache=False, cache_dir=None, jobs=1):
        seen.append(jobs)
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, "w") as fh:
            fh.write("x")
        return [output_path]

    monkeypatch.setattr(render_mod.engine_bridge, "render", fake)
    render_variants(
        variant_dir=variant_dir,
        audio_dir=str(tmp_path / "audio"),
        score_dir=None,
        samples_dir="unused",
        jobs=8,
    )
    # Una sola variante pendente: il pool esterno resta a 1 worker (path
    # in-process) e l'engine riceve l'intero budget.
    assert seen == [8]


# --- variant_paths: la stessa enumerazione, senza scrivere -----------------

def test_variant_paths_coincide_con_write_variants(tmp_path):
    """Il contratto su cui poggia `prune`: se i due divergono, prune cancella
    file buoni. Vale per tutte e tre le modalita'."""
    from granstudies.render import variant_paths

    for mode in ("discrete", "envelope", "both"):
        d = tmp_path / mode
        written = write_variants(_spec(mode), str(d))
        assert sorted(variant_paths(_spec(mode), str(d))) == sorted(written)


def test_variant_paths_non_scrive_niente(tmp_path):
    from granstudies.render import variant_paths

    paths = variant_paths(_spec("discrete"), str(tmp_path))
    assert paths
    assert os.listdir(str(tmp_path)) == []   # nessuna cartella 'discrete/' creata


def test_audio_for_mette_studio_e_stream_nel_basename(tmp_path):
    from granstudies.render import audio_for

    v, a = str(tmp_path / "yaml"), str(tmp_path / "audio")
    y = os.path.join(v, "discrete", "st", "o2__a=1.yml")
    name, audio = audio_for(y, v, a, "s01")
    assert name == os.path.join("discrete", "st", "o2__a=1")
    assert audio == os.path.join(a, "discrete", "st", "s01_st_o2__a=1.aif")


def test_audio_for_senza_sottocartella_di_stream(tmp_path):
    from granstudies.render import audio_for

    v, a = str(tmp_path / "yaml"), str(tmp_path / "audio")
    _, audio = audio_for(os.path.join(v, "discrete", "o2__a=1.yml"), v, a, "s01")
    assert audio == os.path.join(a, "discrete", "s01_o2__a=1.aif")
