from granstudies.states import parse_states
from granstudies.walk import authored_path, Step
from granstudies.compose import (
    build_timeline,
    build_envelopes,
    total_duration,
    compose_document,
)


def _two_states():
    return parse_states(
        {
            "states": [
                {"id": "A", "params": {"density": 0}, "dwell": 2, "transition_speed": 1},
                {"id": "B", "params": {"density": 10}, "dwell": 2, "transition_speed": 1},
            ]
        }
    )


def test_timeline_absolute_times():
    steps = [Step("A", 2, 1), Step("B", 2, 0)]
    tl = build_timeline(steps)
    assert tl[0] == {"state_id": "A", "hold_start": 0, "hold_end": 2, "trans_end": 3}
    assert tl[1] == {"state_id": "B", "hold_start": 3, "hold_end": 5, "trans_end": 5}


def test_total_duration():
    steps = [Step("A", 2, 1), Step("B", 2, 0)]
    assert total_duration(steps) == 5


def test_envelope_breakpoints():
    s = _two_states()
    steps = [Step("A", 2, 1), Step("B", 2, 0)]
    env = build_envelopes(steps, s)
    assert env["density"] == [[0, 0], [2, 0], [3, 10], [5, 10]]
    # tempi monotoni crescenti
    times = [p[0] for p in env["density"]]
    assert times == sorted(times)


def test_compose_collapses_constant_envelope_to_scalar():
    s = _two_states()
    steps = [Step("A", 3, 0)]   # singola tappa: density costante
    doc = compose_document(steps, s, base_stream={"sample": "x.wav"})
    assert doc["streams"][0]["density"] == 0    # scalare, non envelope


def test_compose_document_structure():
    s = _two_states()
    steps = authored_path(s, [{"state": "A"}, {"state": "B"}])
    doc = compose_document(steps, s, base_stream={"sample": "x.wav", "volume": -6})
    stream = doc["streams"][0]
    assert stream["stream_id"]            # l'engine lo richiede
    assert stream["time_mode"] == "absolute"
    assert stream["onset"] == 0
    assert stream["sample"] == "x.wav"
    assert isinstance(stream["density"], list)   # envelope (A->B varia)
    assert doc["duration"] == total_duration(steps)
