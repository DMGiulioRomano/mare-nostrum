"""e2e del ramo sweep: study.yml su disco -> CLI -> albero YAML (issue #4).

Copre le casistiche 1, 2 e 4 della issue: generazione da un file vero per
tutti e quattro gli ordini, golden del documento intero (discrete ed
envelope), modalita' ``both`` esercitata fino ai file scritti.

I numeri asseriti qui — 15 file envelope, 4/6/4/1 per ordine, 25/85/265/805
secondi — sono quelli della issue, e discendono dalla forma della fixture
(quattro assi, tre valori, plateau 5, transition 5). Se cambiano, o e'
cambiata la fixture o e' cambiata la combinatoria: in entrambi i casi vanno
riletti, non riallineati.
"""
import os

import pytest

pytestmark = pytest.mark.e2e


# Nomi attesi degli envelope, per ordine. L'ordine dei nomi dentro ogni file
# e' quello di dichiarazione degli assi in study.yml, non alfabetico.
EXPECTED_ENVELOPE = {
    1: [
        "e1__density",
        "e1__distribution",
        "e1__grain.duration",
        "e1__pitch.semitones",
    ],
    2: [
        "e2__density__distribution",
        "e2__density__grain.duration",
        "e2__density__pitch.semitones",
        "e2__grain.duration__distribution",
        "e2__grain.duration__pitch.semitones",
        "e2__pitch.semitones__distribution",
    ],
    3: [
        "e3__density__grain.duration__distribution",
        "e3__density__grain.duration__pitch.semitones",
        "e3__density__pitch.semitones__distribution",
        "e3__grain.duration__pitch.semitones__distribution",
    ],
    4: ["e4__density__grain.duration__pitch.semitones__distribution"],
}

# Durata per ordine: N plateau da 5 s separati da N-1 transizioni da 5 s,
# con N = 3**ordine (tre valori per asse).
EXPECTED_DURATION = {1: 25.0, 2: 85.0, 3: 265.0, 4: 805.0}


@pytest.fixture
def swept(sweep_repo):
    """Il repo finto dopo un `granstudies sweep` completo."""
    sweep_repo.run("sweep", sweep_repo.study)
    return sweep_repo


# --- casistica 4: mode both materializza entrambi i set -------------------------

def test_both_writes_discrete_and_envelope(swept):
    assert os.path.isdir(swept.yaml_dir("sweep", "discrete"))
    assert os.path.isdir(swept.yaml_dir("sweep", "envelope"))
    assert swept.written("sweep", "discrete")
    assert swept.written("sweep", "envelope")


# --- casistica 1: tutti e quattro gli ordini, dal file reale --------------------

def test_envelope_file_count_per_order(swept):
    names = swept.names("sweep", "envelope")
    assert len(names) == 15
    for order, expected in EXPECTED_ENVELOPE.items():
        assert sorted(n for n in names if n.startswith(f"e{order}__")) == sorted(
            expected
        ), f"ordine {order}"


@pytest.mark.parametrize("order", [1, 2, 3, 4])
def test_envelope_duration_per_order(swept, order):
    for name in EXPECTED_ENVELOPE[order]:
        doc = swept.document("sweep", "envelope", f"{name}.yml")
        assert doc["duration"] == EXPECTED_DURATION[order], name
        # La durata del documento e quella dello stream sono la stessa cosa:
        # i file envelope sono mono-stream e normalizzati su di essa.
        assert doc["streams"][0]["duration"] == EXPECTED_DURATION[order], name


@pytest.mark.parametrize("order", [1, 2, 3, 4])
def test_envelope_files_are_normalized(swept, order):
    for name in EXPECTED_ENVELOPE[order]:
        stream = swept.document("sweep", "envelope", f"{name}.yml")["streams"][0]
        assert stream["time_mode"] == "normalized", name


def _points(stream, path):
    node = stream
    for part in path.split("."):
        node = node[part]
    return node["points"]


@pytest.mark.parametrize("order", [2, 3, 4])
def test_moved_axes_share_the_same_time_grid(swept, order):
    # Il senso dell'ordine k: k assi che si muovono *insieme*. Se le griglie
    # temporali divergessero, i plateau non sarebbero piu' simultanei e il
    # file non sarebbe piu' un ascolto di una combinazione alla volta.
    paths = {
        "density": "density",
        "grain.duration": "grain.duration",
        "pitch.semitones": "pitch.semitones",
        "distribution": "distribution",
    }
    for name in EXPECTED_ENVELOPE[order]:
        stream = swept.document("sweep", "envelope", f"{name}.yml")["streams"][0]
        moved = name.split("__")[1:]
        grids = [[t for t, _ in _points(stream, paths[m])] for m in moved]
        assert all(g == grids[0] for g in grids), name
        # 3**order plateau, due breakpoint ciascuno
        assert len(grids[0]) == 2 * (3 ** order), name


def test_still_axes_stay_scalar_at_their_baseline(swept):
    # e1__density: solo density e' un envelope, gli altri tre restano scalari
    # al baseline. distribution non ha 'baseline' in study.yml: il suo valore
    # arriva dal default engine.
    from granstudies.engine_bridge import parameter_defaults

    stream = swept.document("sweep", "envelope", "e1__density.yml")["streams"][0]
    assert isinstance(stream["density"], dict)          # mosso
    assert stream["grain"]["duration"] == 0.05
    assert stream["pitch"]["semitones"] == 0
    assert stream["distribution"] == parameter_defaults()["distribution"]


# --- casistica 2: golden del documento intero ----------------------------------

def test_golden_discrete_document(swept):
    # Documento discrete completo, letto da disco. E' il golden che mancava:
    # gli unit ne avevano uno solo per il ramo envelope.
    doc = swept.document("sweep", "discrete", "o1__density=5.yml")
    assert doc == {
        "title": "e2e_study01 :: o1__density=5",
        "seed": 1988,
        "duration": 6,
        "streams": [
            {
                "onset": 0,
                "duration": 6,
                "sample": "e2e_corpus.wav",
                "time_mode": "normalized",
                "grain": {"envelope": "hanning", "duration": 0.05},
                "pointer": {"speed_ratio": 0},
                "stream_id": "stream",
                "density": 5,
                "pitch": {"semitones": 0},
                "distribution": 0.0,
            }
        ],
    }


def test_golden_e1_envelope_document(swept):
    # Stesso golden dal lato envelope: tre plateau da 5 s con transizioni da
    # 5 s, tempi normalizzati sui 25 s totali.
    doc = swept.document("sweep", "envelope", "e1__density.yml")
    assert doc == {
        "title": "e2e_study01 :: e1__density",
        "seed": 1988,
        "duration": 25.0,
        "streams": [
            {
                "onset": 0,
                "duration": 25.0,
                "sample": "e2e_corpus.wav",
                "time_mode": "normalized",
                "grain": {"envelope": "hanning", "duration": 0.05},
                "pointer": {"speed_ratio": 0},
                "stream_id": "stream",
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
                "pitch": {"semitones": 0},
                "distribution": 0.0,
            }
        ],
    }


# --- discrete: la base.duration e' la durata dei file statici ------------------

def test_discrete_files_use_base_duration(swept):
    for path in swept.written("sweep", "discrete"):
        doc = swept.load(path)
        assert doc["duration"] == 6, path
        assert doc["streams"][0]["duration"] == 6, path


def test_discrete_covers_every_order(swept):
    names = swept.names("sweep", "discrete")
    for order in (1, 2, 3, 4):
        assert any(n.startswith(f"o{order}__") for n in names), f"ordine {order}"


# --- idempotenza: rigenerare non cambia niente ---------------------------------

def test_second_sweep_leaves_the_documents_identical(swept):
    before = {p: swept.load(p) for p in swept.written("sweep")}
    swept.run("sweep", swept.study)
    after = {p: swept.load(p) for p in swept.written("sweep")}
    assert after == before
