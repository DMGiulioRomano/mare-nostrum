"""Guardia di migrazione: uno snapshot fisso di study01_grain_density deve
parsare e produrre output coerenti con entrambi i processi (sweep + stack)
dopo la rimozione di combine: parallel.

Usa una fixture (tests/fixtures/study01_migrated_stack.yml), non il file di
lavoro reale in studies/ — quel file è curato a mano dall'utente e cambia
liberamente; questo test non deve dipendere dal suo contenuto corrente.
"""
import os

import yaml

from granstudies.envelope_sweep import generate_envelope_variants
from granstudies.stack import generate_stack_document
from granstudies.study_spec import resolve_streams

_STUDY = os.path.join(
    os.path.dirname(__file__), "fixtures", "study01_migrated_stack.yml"
)


def _specs():
    with open(_STUDY, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return data, resolve_streams(data, "study01_grain_density")


def test_study01_parses_and_has_stack_block():
    data, specs = _specs()
    assert "stack" in data
    assert all(s.stack is not None for s in specs)


def test_study01_migrated_streams_out_of_sweep():
    # I due stream ex-parallel non producono piu' varianti sweep: vivono in stack.
    _, specs = _specs()
    by_id = {s.stream_id: s for s in specs}
    for sid in ("lettura_avanzata_parallel", "lettura_avanzata_c"):
        assert generate_envelope_variants(by_id[sid]) == []


def test_study01_stack_document_collapses_all_streams():
    _, specs = _specs()
    doc = generate_stack_document(specs)
    assert len(doc["streams"]) == len(specs)
    ids = [s["stream_id"] for s in doc["streams"]]
    assert "lettura_avanzata_parallel" in ids
    assert "lettura_avanzata_c" in ids


def test_study01_coupled_axes_share_times_in_migrated_stream():
    # L'accoppiamento ex-parallel: stessa X (linear) e stesso n -> breakpoint
    # agli stessi tempi, valori appaiati per indice.
    _, specs = _specs()
    doc = generate_stack_document(specs)
    stream = next(
        s for s in doc["streams"] if s["stream_id"] == "lettura_avanzata_parallel"
    )
    t_density = [t for t, _ in stream["density"]["points"]]
    t_grain = [t for t, _ in stream["grain"]["duration"]["points"]]
    assert t_density == t_grain
    assert len(t_density) == 20                      # le due ramp da 20 valori
