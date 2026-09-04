"""e2e col render: gli YAML generati sono davvero validi per l'engine (issue #4).

E' la casistica che gli unit e i golden non possono coprire. Un documento puo'
avere la struttura giusta, i breakpoint giusti e i nomi giusti, e comunque
essere rifiutato dall'engine — o produrre silenzio. L'unico modo di saperlo e'
darglielo da renderizzare.

Le durate sono tagliate come suggerisce la issue (`plateau`/`transition`
piccoli, stream da un secondo) e si asserisce la sola **validita'** del render:
audio esistente, non vuoto, non silenzioso. Niente asserzioni sulla durata
reale del file — quella e' materia dell'engine, non di questa pipeline.

Guardato dalla presenza del submodule ``engine``, come ``test_engine_bridge``.
"""
import copy
import os
import shutil

import numpy as np
import pytest
import soundfile as sf
import yaml

from granstudies import engine_bridge
from granstudies.render import render_variants


pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        not os.path.isdir(engine_bridge.ENGINE_SRC),
        reason="submodule engine non inizializzato",
    ),
]


def _assert_audible(path: str) -> None:
    assert os.path.exists(path), path
    data, _ = sf.read(path)
    assert data.size > 0, f"audio vuoto: {path}"
    assert float(np.max(np.abs(data))) > 0.0, f"silenzio: {path}"


def _audio_paths(entry) -> list[str]:
    audio = entry["audio"]
    return audio if isinstance(audio, list) else [audio]


# --- il ramo multi-stream, attraverso la CLI ------------------------------------

def test_cli_render_of_stack_versions_percorso(processes_repo):
    """`stack`+`versions`+`percorso` e poi `render`: la catena all-study intera.

    Passa dalla CLI vera, quindi esercita anche la costruzione dei path di
    audio/ e score/ a partire da generated/<study>/yaml/.
    """
    for cmd in ("stack", "versions", "percorso"):
        processes_repo.run(cmd, processes_repo.study)
    processes_repo.run(
        "render", processes_repo.study, "--no-score", "--no-stem", "--no-cache"
    )

    audio_dir = os.path.join(processes_repo.generated, "audio")
    produced = [
        os.path.join(root, f)
        for root, _, files in os.walk(audio_dir)
        for f in files
        if f.endswith(".aif")
    ]
    # Un file per documento: stack, due versions, percorso.
    assert len(produced) == 4, sorted(produced)
    for path in produced:
        _assert_audible(path)


def test_cli_render_is_incremental(processes_repo):
    for cmd in ("stack", "versions", "percorso"):
        processes_repo.run(cmd, processes_repo.study)
    common = ("--no-score", "--no-stem", "--no-cache")
    processes_repo.run("render", processes_repo.study, *common)

    audio_dir = os.path.join(processes_repo.generated, "audio")
    stamps = {
        os.path.join(root, f): os.path.getmtime(os.path.join(root, f))
        for root, _, files in os.walk(audio_dir)
        for f in files
    }
    processes_repo.run("render", processes_repo.study, *common)
    again = {p: os.path.getmtime(p) for p in stamps}
    assert again == stamps, "il secondo render ha rifatto lavoro gia' fatto"


# --- il ramo sweep: un rappresentante per ogni ordine e ogni modalita' ----------

@pytest.fixture
def small_sweep(sweep_repo):
    """Lo studio sweep con i tempi tagliati, per renderizzare in fretta.

    Due valori per asse invece di tre (l'ordine 4 scende da 81 plateau a 16) e
    plateau/transition sotto il secondo: gli ordini restano tutti e quattro,
    che e' il punto, ma il file piu' lungo dura pochi secondi.
    """
    with open(sweep_repo.fixture("e2e_study.yml"), "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    data = copy.deepcopy(data)
    data["sweep"]["plateau"] = 0.2
    data["sweep"]["transition"] = 0.1
    data["base"]["duration"] = 0.5
    for name, cfg in data["axes"].items():
        if isinstance(cfg, dict) and "values" in cfg:
            cfg["values"] = cfg["values"][:2]
    sweep_repo.write_study(data)
    sweep_repo.run("sweep", sweep_repo.study)
    return sweep_repo


def _representatives(repo) -> dict[tuple[str, int], str]:
    """Un file per (modalita', ordine): il primo in ordine alfabetico."""
    picks: dict[tuple[str, int], str] = {}
    for mode, prefix in (("discrete", "o"), ("envelope", "e")):
        for path in repo.written("sweep", mode):
            name = os.path.basename(path)
            order = int(name[len(prefix)])
            picks.setdefault((mode, order), path)
    return picks


def test_every_order_and_mode_renders(small_sweep, tmp_path):
    picks = _representatives(small_sweep)
    assert sorted(picks) == [
        (mode, order) for mode in ("discrete", "envelope") for order in (1, 2, 3, 4)
    ]

    # Le sole varianti scelte, nell'albero che render_variants si aspetta
    # (una sotto-cartella per modalita', rispecchiata sotto audio/).
    picked_dir = tmp_path / "picked"
    for (mode, _order), path in picks.items():
        dest = picked_dir / mode
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, dest / os.path.basename(path))

    manifest = render_variants(
        variant_dir=str(picked_dir),
        audio_dir=str(tmp_path / "audio"),
        score_dir=None,
        samples_dir=small_sweep.samples,
    )
    assert len(manifest) == len(picks)
    for entry in manifest:
        assert not entry["skipped"], entry["name"]
        for path in _audio_paths(entry):
            _assert_audible(path)


def test_generated_documents_name_the_corpus_of_the_study(small_sweep):
    # Guardia sulla cucitura samples_dir: il documento deve nominare il sample
    # dello study.yml, e quel sample deve stare dove la CLI lo va a cercare.
    # Se cosi' non fosse il render qui sopra fallirebbe con un file mancante
    # invece che con un'asserzione leggibile.
    doc = small_sweep.document("sweep", "envelope", "e1__density.yml")
    assert doc["streams"][0]["sample"] == small_sweep.sample
    assert os.path.exists(os.path.join(small_sweep.samples, small_sweep.sample))
