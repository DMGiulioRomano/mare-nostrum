import pytest

from granstudies.states import parse_states, states_by_id


def _data():
    return {
        "states": [
            {
                "id": "a",
                "params": {"density": 5, "grain.duration": 0.2},
                "dwell": [4, 10],
                "transition_speed": 3.0,
                "tags": ["sparso"],
            },
            {
                "id": "b",
                "params": {"density": 50},
                "dwell": 5,
            },
        ]
    }


def test_parse_basic():
    states = parse_states(_data())
    assert [s.id for s in states] == ["a", "b"]
    a = states_by_id(states)["a"]
    assert a.dwell == (4.0, 10.0)
    assert a.transition_speed == 3.0
    assert a.tags == ["sparso"]
    # default transition_speed quando assente
    assert states_by_id(states)["b"].transition_speed == 1.0
    # dwell scalare -> (v, v)
    assert states_by_id(states)["b"].dwell == (5.0, 5.0)


def test_rejects_duplicate_id():
    d = {"states": [{"id": "x"}, {"id": "x"}]}
    with pytest.raises(ValueError):
        parse_states(d)


def test_rejects_bad_dwell():
    d = {"states": [{"id": "x", "dwell": [10, 1]}]}
    with pytest.raises(ValueError):
        parse_states(d)


def test_rejects_nonpositive_speed():
    d = {"states": [{"id": "x", "transition_speed": 0}]}
    with pytest.raises(ValueError):
        parse_states(d)


def test_rejects_empty():
    with pytest.raises(ValueError):
        parse_states({"states": []})
