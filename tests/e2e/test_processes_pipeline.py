"""e2e del ramo multi-stream: stack, versions, percorso (issue #4).

La issue e' del giugno 2026 e conosceva un solo processo, lo sweep. Da allora
la pipeline viva — `make all-study` — e' `sweep stack versions percorso
render`: un e2e che si fermasse allo sweep coprirebbe un quarto di quello che
gira davvero. Questo modulo copre gli altri tre, con lo stesso metodo: CLI
vera, study.yml su disco, asserzioni sui documenti scritti.

Ogni processo si attiva **per presenza** del proprio blocco, e i tre leggono
lo stesso `study.yml` in modi diversi: stack lo prende com'e' scritto,
versions ne fa il prodotto cartesiano delle manopole, percorso ne distribuisce
le istanze sulla timeline reale. Le asserzioni qui guardano proprio quel
punto — che i tre non si pestino i piedi sugli stessi nomi e sugli stessi
tempi.
"""
import os

import pytest

pytestmark = pytest.mark.e2e


@pytest.fixture
def built(processes_repo):
    """Il repo finto dopo stack + versions + percorso."""
    for cmd in ("stack", "versions", "percorso"):
        processes_repo.run(cmd, processes_repo.study)
    return processes_repo


def _stream_ids(doc):
    return [s["stream_id"] for s in doc["streams"]]


# --- attivazione per presenza --------------------------------------------------

def test_sweep_is_a_noop_without_its_block(processes_repo):
    # La fixture non ha 'sweep:': il comando esce 0 e non scrive niente.
    processes_repo.run("sweep", processes_repo.study)
    assert not os.path.isdir(processes_repo.yaml_dir("sweep"))


def test_each_process_writes_its_own_directory(built):
    assert os.path.exists(built.yaml_dir("stack", "stack.yml"))
    assert os.path.exists(built.yaml_dir("percorso", "percorso.yml"))
    assert built.names("versions")


def test_expanded_streams_is_written_but_is_not_a_variant(built):
    # streams_expanded.yml sta accanto ai documenti ma non e' uno di loro:
    # e' l'artefatto di sola ispezione che anche render_variants salta.
    assert os.path.exists(built.yaml_dir("streams_expanded.yml"))
    assert "streams_expanded" not in built.names()


# --- stack: le voci dello spread suonano insieme -------------------------------

def test_stack_expands_the_spread_into_sibling_streams(built):
    doc = built.document("stack", "stack.yml")
    assert _stream_ids(doc) == ["voci_1", "voci_2"]
    # Stesso onset: lo stack e' ascolto verticale, non successione.
    assert {s["onset"] for s in doc["streams"]} == {0}


def test_stack_voices_differ_only_by_the_reading_point(built):
    doc = built.document("stack", "stack.yml")
    starts = [s["pointer"]["start"] for s in doc["streams"]]
    assert starts == [0.0, 0.2]


# --- versions: una manopola mossa, un documento per valore ---------------------

def test_versions_splits_files_on_the_first_variable(built):
    # d0 e' la prima variabile dichiarata: e' il confine di file. g0 non lo e'
    # — concatena dentro ogni file.
    assert built.names("versions") == ["versions__d0=12", "versions__d0=24"]


def test_versions_concatenates_the_inner_variable_on_its_own_step(built):
    # 'versions.duration: 2' e' il passo: dentro un file, la combinazione
    # successiva parte 2 s dopo. Post-#42 il passo e' una chiave di
    # 'versions:', non la durata top-level del documento.
    doc = built.document("versions", "versions__d0=12.yml")
    onset_by_id = {s["stream_id"]: s["onset"] for s in doc["streams"]}
    assert onset_by_id["voci_1__d0=12__g0=0.03"] == 0
    assert onset_by_id["voci_1__d0=12__g0=0.06"] == 2
    # e la durata del documento e' dedotta, non scritta: 2 s di passo + 1 s
    # dell'ultimo stream
    assert doc["duration"] == 3.0


def test_versions_names_every_stream_with_its_combination(built):
    doc = built.document("versions", "versions__d0=24.yml")
    assert _stream_ids(doc) == [
        "voci_1__d0=24__g0=0.03",
        "voci_2__d0=24__g0=0.03",
        "voci_1__d0=24__g0=0.06",
        "voci_2__d0=24__g0=0.06",
    ]


def test_versions_moves_the_knobs_it_declares(built):
    # d0 e' il centro della banda density, g0 quello della grana: il primo
    # separa i file, il secondo separa le combinazioni dentro un file.
    first = built.document("versions", "versions__d0=12.yml")
    second = built.document("versions", "versions__d0=24.yml")
    assert [s["density"] for s in first["streams"]] != [
        s["density"] for s in second["streams"]
    ]
    grains = [s["grain"]["duration"] for s in first["streams"]]
    assert grains[0] < grains[2]   # g0=0.03 prima di g0=0.06


# --- percorso: le istanze sulla timeline reale ---------------------------------

def test_percorso_places_one_instance_per_declared_onset(built):
    doc = built.document("percorso", "percorso.yml")
    assert sorted({s["onset"] for s in doc["streams"]}) == [0, 2]


def test_percorso_keeps_the_voices_of_every_instance(built):
    doc = built.document("percorso", "percorso.yml")
    # Due istanze x due voci di spread: quattro stream, nomi tutti distinti.
    assert len(doc["streams"]) == 4
    assert len(set(_stream_ids(doc))) == 4


# --- idempotenza ---------------------------------------------------------------

def test_regenerating_leaves_the_documents_identical(built):
    before = {p: built.load(p) for p in built.written()}
    for cmd in ("stack", "versions", "percorso"):
        built.run(cmd, built.study)
    after = {p: built.load(p) for p in built.written()}
    assert after == before
