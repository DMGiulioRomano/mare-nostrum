from granstudies.states import parse_states
from granstudies.kinship import (
    similarity,
    kinship_matrix,
    derive_edges,
    adjacency,
    Weights,
)


def _states():
    return parse_states(
        {
            "states": [
                {
                    "id": "a",
                    "params": {"density": 5, "distribution": 0.0},
                    "tags": ["sparso"],
                },
                {
                    "id": "b",
                    "params": {"density": 5, "distribution": 0.0},
                    "tags": ["sparso"],
                },
                {
                    "id": "c",
                    "params": {"density": 4000, "distribution": 1.0},
                    "tags": ["denso"],
                },
            ]
        }
    )


def test_identity_similarity_is_one():
    s = _states()
    assert similarity(s[0], s[0]) == 1.0


def test_identical_states_similarity_one():
    s = _states()
    assert similarity(s[0], s[1]) == 1.0   # a e b identici


def test_distant_states_low_similarity():
    s = _states()
    assert similarity(s[0], s[2]) < 0.2    # a vs c: estremi opposti


def test_matrix_symmetry_and_diagonal():
    s = _states()
    kin = kinship_matrix(s)
    m = kin["matrix"]
    n = len(s)
    for i in range(n):
        assert m[i][i] == 1.0
        for j in range(n):
            assert abs(m[i][j] - m[j][i]) < 1e-12


def test_derive_edges_threshold():
    s = _states()
    kin = kinship_matrix(s)
    edges = derive_edges(kin, threshold=0.9)
    # a-b vicini (sim 1.0), c isolato
    assert set(edges["a"]) == {"b"}
    assert set(edges["b"]) == {"a"}
    assert edges["c"] == []


def test_adjacency_manual_override():
    s = parse_states(
        {
            "states": [
                {"id": "a", "params": {"density": 5}, "children": ["c"]},
                {"id": "b", "params": {"density": 5}},
                {"id": "c", "params": {"density": 4000}},
            ]
        }
    )
    kin = kinship_matrix(s)
    adj = adjacency(s, kin, threshold=0.9)
    # 'a' usa l'override esplicito, non gli archi derivati
    assert adj["a"] == ["c"]
