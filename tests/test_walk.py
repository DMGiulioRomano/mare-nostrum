import pytest

from granstudies.states import parse_states
from granstudies.walk import random_walk, authored_path


def _states():
    return parse_states(
        {
            "states": [
                {"id": "a", "params": {"density": 5}, "dwell": [2, 8], "transition_speed": 3.0},
                {"id": "b", "params": {"density": 50}, "dwell": [1, 4], "transition_speed": 2.0},
                {"id": "c", "params": {"density": 400}, "dwell": 3, "transition_speed": 1.5},
            ]
        }
    )


def _full_adjacency():
    return {"a": ["b", "c"], "b": ["a", "c"], "c": ["a", "b"]}


def test_random_walk_deterministic():
    s = _states()
    adj = _full_adjacency()
    w1 = random_walk(s, adj, start="a", steps=6, seed=42)
    w2 = random_walk(s, adj, start="a", steps=6, seed=42)
    assert [x.state_id for x in w1] == [x.state_id for x in w2]
    assert [x.dwell for x in w1] == [x.dwell for x in w2]
    assert len(w1) == 6
    assert w1[0].state_id == "a"


def test_random_walk_last_step_no_transition():
    s = _states()
    w = random_walk(s, _full_adjacency(), start="a", steps=4, seed=1)
    assert w[-1].transition == 0.0
    assert all(x.transition > 0 for x in w[:-1])


def test_random_walk_dead_end_stops():
    s = _states()
    adj = {"a": [], "b": [], "c": []}
    w = random_walk(s, adj, start="a", steps=5, seed=1)
    assert len(w) == 1
    assert w[0].state_id == "a"


def test_random_walk_dwell_within_range():
    s = _states()
    w = random_walk(s, _full_adjacency(), start="a", steps=10, seed=7)
    by_id = {x.id: x for x in s}
    for step in w:
        lo, hi = by_id[step.state_id].dwell
        assert lo <= step.dwell <= hi


def test_authored_path_defaults_and_validation():
    s = _states()
    steps = authored_path(s, [{"state": "a", "dwell": 5}, {"state": "c"}])
    assert steps[0].state_id == "a" and steps[0].dwell == 5
    assert steps[0].transition == 3.0       # transition_speed di 'a'
    assert steps[1].transition == 0.0       # ultimo step
    # dwell di default = punto medio del range di 'c' (3,3) -> 3
    assert steps[1].dwell == 3.0


def test_authored_path_unknown_state():
    with pytest.raises(KeyError):
        authored_path(_states(), [{"state": "zzz"}])
