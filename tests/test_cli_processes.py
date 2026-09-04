"""Separazione dei processi stack/versions (fase 0 di percorso-v1).

``stack`` e ``versions`` sono processi indipendenti come ``sweep`` e
``stack``: stesso ``study.yml``, sottocomandi e cartelle di output propri.
``cmd_stack`` ignora il blocco ``versions:`` (lo stack com'e' scritto e'
l'istanza di partenza del percorso); ``cmd_versions`` lo richiede e scrive
in ``yaml/versions/versions.yml``.
"""
import os

import pytest
import yaml

from granstudies import __main__ as cli
from granstudies.errors import SpecError


# Documento con blocco versions E default nel let: valido anche senza
# iniezione (stile documentato: il default tiene lo studio renderizzabile
# come stack puro, decisione "partenza-nel-materiale").
DOC_WITH_DEFAULT = {
    "study_id": "s_processes",
    "seed": 7,
    "samples_dir": "samples",
    "base": {"onset": 0, "sample": "corpus.wav", "duration": 10},
    "axes": {
        "density": {
            "path": "density",
            "baseline": 50,
            "n": 4,
            "base": {"expr": "env + d", "let": {"env": [[0, 40], [1, 60]], "d": 0}},
            "range": 0,
        },
    },
    "stack": {},
    "streams": {"fermo": {}, "mobile": {}},
    "versions": {"duration": 10, "d": {"values": [1, 2]}},
}


def _write_study(tmp_path, monkeypatch, doc):
    sdir = tmp_path / "studies" / doc["study_id"]
    sdir.mkdir(parents=True)
    (sdir / "study.yml").write_text(yaml.safe_dump(doc, sort_keys=False))
    monkeypatch.setattr(cli, "study_dir", lambda study: os.path.join(str(tmp_path), "studies", study))
    monkeypatch.setattr(cli, "gen_dir", lambda s: os.path.join(str(tmp_path), "generated", s))
    return doc["study_id"]


# --- cmd_stack ignora versions -----------------------------------------------

def test_cmd_stack_with_versions_block_writes_pure_stack(tmp_path, monkeypatch):
    """Il blocco versions non tocca lo stack: stream_id nudi, niente repliche."""
    study = _write_study(tmp_path, monkeypatch, DOC_WITH_DEFAULT)
    assert cli.cmd_stack(study) == 0
    out = os.path.join(str(tmp_path), "generated", study, "yaml", "stack", "stack.yml")
    with open(out) as fh:
        doc = yaml.safe_load(fh)
    ids = [s["stream_id"] for s in doc["streams"]]
    assert ids == ["fermo", "mobile"]
    assert doc["duration"] == 10


def test_cmd_stack_without_let_default_raises(tmp_path, monkeypatch):
    """Senza default nel let lo stack puro non e' risolvibile: errore, non
    fallback silenzioso su versions (il confine tra i processi e' netto)."""
    doc = yaml.safe_load(yaml.safe_dump(DOC_WITH_DEFAULT))
    doc["study_id"] = "s_nodefault"
    del doc["axes"]["density"]["base"]["let"]["d"]
    study = _write_study(tmp_path, monkeypatch, doc)
    with pytest.raises(SpecError):
        cli.cmd_stack(study)


# --- cmd_versions --------------------------------------------------------------

def test_cmd_versions_writes_document_in_own_dir(tmp_path, monkeypatch):
    study = _write_study(tmp_path, monkeypatch, DOC_WITH_DEFAULT)
    assert cli.cmd_versions(study) == 0
    out = os.path.join(str(tmp_path), "generated", study, "yaml", "versions", "versions__d=1.yml")
    with open(out) as fh:
        doc = yaml.safe_load(fh)
    ids = [s["stream_id"] for s in doc["streams"]]
    assert ids == ["fermo__d=1", "mobile__d=1"]
    assert doc["duration"] == 10
    # Lo stack non viene scritto dal processo versions.
    stack_out = os.path.join(str(tmp_path), "generated", study, "yaml", "stack", "stack.yml")
    assert not os.path.exists(stack_out)


def test_cmd_versions_without_block_is_noop(tmp_path, monkeypatch):
    """Attivazione per presenza, come sweep e stack: senza blocco, messaggio
    e uscita pulita."""
    doc = yaml.safe_load(yaml.safe_dump(DOC_WITH_DEFAULT))
    doc["study_id"] = "s_noversions"
    del doc["versions"]
    study = _write_study(tmp_path, monkeypatch, doc)
    assert cli.cmd_versions(study) == 0
    out = os.path.join(str(tmp_path), "generated", study, "yaml", "versions", "versions.yml")
    assert not os.path.exists(out)


def test_parser_has_versions_subcommand():
    args = cli.build_parser().parse_args(["versions", "s_x"])
    assert args.command == "versions"
    assert args.study == "s_x"


# --- cmd_sv: ramo versions ------------------------------------------------------

def test_cmd_sv_exports_versions_document(tmp_path, monkeypatch):
    """Con blocco versions e artefatti presenti, sv emette la sessione del
    documento versions accanto a quella dello stack (workflow d'ascolto)."""
    study = _write_study(tmp_path, monkeypatch, DOC_WITH_DEFAULT)
    g = os.path.join(str(tmp_path), "generated", study)
    for sub, name in (("stack", "stack"), ("versions", "versions")):
        os.makedirs(os.path.join(g, "yaml", sub), exist_ok=True)
        os.makedirs(os.path.join(g, "audio", sub), exist_ok=True)
        with open(os.path.join(g, "yaml", sub, f"{name}.yml"), "w") as fh:
            fh.write("streams: []\n")
        with open(os.path.join(g, "audio", sub, f"{name}.aif"), "wb") as fh:
            fh.write(b"")

    calls = []
    import granstudies.sv_export as sv_export
    monkeypatch.setattr(sv_export, "stack_to_sv",
                        lambda variant, audio, out, layout, axis_paths=None: calls.append(("doc", variant, out)))
    monkeypatch.setattr(sv_export, "stack_stems_to_sv",
                        lambda variant, audio_dir, out, process="stack", axis_paths=None: False)

    assert cli.cmd_sv(study, layout="multi") == 0
    variants = [c[1] for c in calls]
    assert any(os.path.join("yaml", "stack", "stack.yml") in v for v in variants)
    assert any(os.path.join("yaml", "versions", "versions.yml") in v for v in variants)
    outs = [c[2] for c in calls]
    assert any(os.path.join("sv", "versions", f"{study}_versions.sv") in o for o in outs)


# --- cmd_percorso (percorso-v1, fase 4) -------------------------------------------

DOC_WITH_PERCORSO = {
    "study_id": "s_percorso",
    "seed": 7,
    "samples_dir": "samples",
    # base.duration serve a cmd_stack (che ignora il blocco percorso); il
    # percorso la ombreggia con la durata di ogni istanza (arco/passo).
    "base": {"onset": 0, "sample": "corpus.wav", "duration": 10},
    "axes": {
        "density": {
            "path": "density",
            "baseline": 50,
            "n": 4,
            "base": {"expr": "env + w * 10", "let": {"env": [[0, 40], [1, 60]], "w": 0}},
            "range": 0,
        },
    },
    "stack": {},
    "streams": {"fermo": {}, "mobile": {}},
    "percorso": {"arco": 20, "passo": 10, "w": {"base": [[0, 0], [1, 1]]}},
}


def test_cmd_percorso_writes_document_in_own_dir(tmp_path, monkeypatch):
    study = _write_study(tmp_path, monkeypatch, DOC_WITH_PERCORSO)
    assert cli.cmd_percorso(study) == 0
    out = os.path.join(str(tmp_path), "generated", study, "yaml", "percorso", "percorso.yml")
    with open(out) as fh:
        doc = yaml.safe_load(fh)
    ids = [s["stream_id"] for s in doc["streams"]]
    assert ids == ["fermo__k=1", "mobile__k=1", "fermo__k=2", "mobile__k=2"]
    assert [s["onset"] for s in doc["streams"]] == [0, 0, 10, 10]
    assert doc["duration"] == 20
    # lo stack non viene scritto dal processo percorso
    stack_out = os.path.join(str(tmp_path), "generated", study, "yaml", "stack", "stack.yml")
    assert not os.path.exists(stack_out)


def test_cmd_percorso_without_block_is_noop(tmp_path, monkeypatch):
    doc = yaml.safe_load(yaml.safe_dump(DOC_WITH_PERCORSO))
    doc["study_id"] = "s_nopercorso"
    del doc["percorso"]
    study = _write_study(tmp_path, monkeypatch, doc)
    assert cli.cmd_percorso(study) == 0
    out = os.path.join(str(tmp_path), "generated", study, "yaml", "percorso", "percorso.yml")
    assert not os.path.exists(out)


def test_cmd_stack_ignores_percorso_block(tmp_path, monkeypatch):
    doc = yaml.safe_load(yaml.safe_dump(DOC_WITH_PERCORSO))
    doc["study_id"] = "s_stack_puro"
    study = _write_study(tmp_path, monkeypatch, doc)
    assert cli.cmd_stack(study) == 0
    out = os.path.join(str(tmp_path), "generated", study, "yaml", "stack", "stack.yml")
    with open(out) as fh:
        stack_doc = yaml.safe_load(fh)
    assert [s["stream_id"] for s in stack_doc["streams"]] == ["fermo", "mobile"]


def test_parser_has_percorso_subcommand():
    args = cli.build_parser().parse_args(["percorso", "s_x"])
    assert args.command == "percorso"
    assert args.study == "s_x"


def test_cmd_sv_exports_percorso_document(tmp_path, monkeypatch):
    study = _write_study(tmp_path, monkeypatch, DOC_WITH_PERCORSO)
    g = os.path.join(str(tmp_path), "generated", study)
    for sub, name in (("stack", "stack"), ("percorso", "percorso")):
        os.makedirs(os.path.join(g, "yaml", sub), exist_ok=True)
        os.makedirs(os.path.join(g, "audio", sub), exist_ok=True)
        with open(os.path.join(g, "yaml", sub, f"{name}.yml"), "w") as fh:
            fh.write("streams: []\n")
        with open(os.path.join(g, "audio", sub, f"{name}.aif"), "wb") as fh:
            fh.write(b"")

    calls = []
    stem_processes = []
    import granstudies.sv_export as sv_export
    monkeypatch.setattr(sv_export, "stack_to_sv",
                        lambda variant, audio, out, layout, axis_paths=None: calls.append(("doc", variant, out)))
    # Registra il 'process' con cui viene chiamato: e' il fix del bug PR #30
    # (il prefisso stem dev'essere quello del processo, non 'stack' cablato).
    monkeypatch.setattr(sv_export, "stack_stems_to_sv",
                        lambda variant, audio_dir, out, process="stack", axis_paths=None: stem_processes.append(process) or False)

    assert cli.cmd_sv(study, layout="multi") == 0
    variants = [c[1] for c in calls]
    assert any(os.path.join("yaml", "percorso", "percorso.yml") in v for v in variants)
    outs = [c[2] for c in calls]
    assert any(os.path.join("sv", "percorso", f"{study}_percorso.sv") in o for o in outs)
    # Lo stem export del percorso riceve process='percorso', non 'stack'.
    assert "percorso" in stem_processes


# --- allineamento render/sv sulle varianti sweep (regressione PR #30) --------------

DOC_WITH_SWEEP = {
    "study_id": "s_sweepsv",
    "samples_dir": "samples",
    "base": {"sample": "x.wav", "duration": 6, "time_mode": "normalized"},
    "axes": {
        "density": {"path": "density", "baseline": 20, "values": [5, 50]},
    },
    "sweep": {"mode": "envelope", "orders": [1], "plateau": 5, "transition": 5},
    "streams": {"vox": {}},
}


def test_sweep_render_sv_basenames_align(tmp_path, monkeypatch, capsys):
    """sweep → render → sv: il render scrive l'audio con lo stesso basename
    che cmd_sv si aspetta ({study}_{stream}_{variante}), quindi nessuna
    variante viene saltata per 'audio mancante' (regressione PR #30)."""
    study = _write_study(tmp_path, monkeypatch, DOC_WITH_SWEEP)
    import granstudies.render as render_mod

    def fake_render(yaml_path, output_path, samples_dir, output_sr=48000,
                    per_stream=False, use_cache=False, cache_dir=None):
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, "w") as fh:
            fh.write("x")
        return [output_path]

    monkeypatch.setattr(render_mod.engine_bridge, "render", fake_render)
    assert cli.cmd_sweep(study) == 0
    assert cli.cmd_render(study, no_score=True) == 0

    import granstudies.sv_export as sv_export
    exported = []
    monkeypatch.setattr(
        sv_export, "variant_to_sv",
        lambda variant, audio, out, layout, markers, markers_scope: exported.append(audio),
    )
    assert cli.cmd_sv(study, layout="multi") == 0
    err = capsys.readouterr().err
    assert "audio mancante" not in err
    env_dir = os.path.join(
        str(tmp_path), "generated", study, "yaml", "sweep", "envelope", "vox"
    )
    n_variants = len([f for f in os.listdir(env_dir) if f.endswith(".yml")])
    assert n_variants > 0
    assert len(exported) == n_variants
    assert all(os.path.basename(a).startswith(f"{study}_vox_") for a in exported)
