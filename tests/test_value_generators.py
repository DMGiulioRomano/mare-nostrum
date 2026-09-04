import pytest

from granstudies.value_generators import (
    _interp_breakpoints,
    _threshold_at,
    band,
    band_at,
    ramp,
    resolve,
)


# --- curve: piega non lineare u^k del segmento (S1) ------------------------------

def test_curve_quadratic_on_known_segment():
    # u=0.5 su [[0,0],[1,10]]: lineare -> 5, curve 2 -> u^2=0.25 -> 2.5.
    assert _interp_breakpoints([[0, 0], [1, 10]], 0.5, curve=2) == 2.5


def test_curve_one_equals_linear():
    pts = [[0, 0], [1, 10]]
    for frac in (0.0, 0.25, 0.5, 0.75, 1.0):
        assert _interp_breakpoints(pts, frac, curve=1) == _interp_breakpoints(pts, frac)


def test_curve_convex_opposite_below_one():
    # curve 0.5: u^0.5 > u -> sale piu' ripido all'inizio (valore > lineare).
    assert _interp_breakpoints([[0, 0], [1, 10]], 0.25, curve=0.5) == pytest.approx(5.0)


def test_curve_holds_at_borders_unchanged():
    # Fuori dai bordi la curve e' irrilevante: hold sul valore d'estremo.
    pts = [[0, 5], [1, 10]]
    assert _interp_breakpoints(pts, -0.1, curve=2) == 5
    assert _interp_breakpoints(pts, 1.5, curve=2) == 10


def test_curve_in_threshold_dict_form():
    spec = {"points": [[0, 0], [1, 10]], "curve": 2}
    assert _threshold_at(spec, 0.5) == 2.5


def test_curve_rejects_non_positive():
    with pytest.raises(ValueError):
        _interp_breakpoints([[0, 0], [1, 10]], 0.5, curve=0)
    with pytest.raises(ValueError):
        _interp_breakpoints([[0, 0], [1, 10]], 0.5, curve=-1)


def test_curve_with_step_type_raises():
    # type: step non ha rampa da piegare: curve != 1 e' un errore di config.
    with pytest.raises(ValueError):
        _threshold_at({"type": "step", "points": [[0, 0], [1, 10]], "curve": 2}, 0.5)


def test_curve_one_with_step_type_ok():
    # curve 1 (default esplicito) e' un no-op: convive con step.
    assert _threshold_at({"type": "step", "points": [[0, 0], [1, 10]], "curve": 1}, 0.5) == 0


def test_band_deterministic_within_band():
    a = band(n=8, base=0.001, range=0.009, seed=1988)
    b = band(n=8, base=0.001, range=0.009, seed=1988)
    assert a == b                       # stesso seed -> stessa sequenza
    assert len(a) == 8
    assert all(0.001 <= v <= 0.01 for v in a)


def test_band_different_seed_differs():
    assert band(n=8, base=0, range=1, seed=1) != band(n=8, base=0, range=1, seed=2)


def test_band_time_varying_band_interpolates():
    # Banda collassata (range omesso, base mobile): valore forzato all'interpolazione.
    assert band(n=3, base=[0.0, 1.0], seed=0) == [0.0, 0.5, 1.0]


def test_band_breakpoints_control_when_it_changes():
    # base come [[t, v], ...]: tieni 0 fino a t=0.5, poi sali a 10.
    # Banda collassata (range omesso) -> valore forzato all'interpolazione.
    bp = [[0, 0], [0.5, 0], [1, 10]]
    assert band(n=3, base=bp, seed=0) == [0.0, 0.0, 10.0]


def test_band_step_interpolation_holds_then_jumps():
    # type: step tiene il valore sinistro e salta al breakpoint.
    # points [[0,0],[1,10]], n=3 (frac 0/0.5/1): step -> [0,0,10] (linear -> [0,5,10]).
    bp = {"type": "step", "points": [[0, 0], [1, 10]]}
    assert band(n=3, base=bp, seed=0) == [0.0, 0.0, 10.0]


def test_band_moving_range_widens_band():
    # range mobile [0 -> 1] su base fissa: al primo passo la banda e' collassata
    # (valore == base), all'ultimo e' [5, 6].
    out = band(n=3, base=5, range=[0.0, 1.0], seed=0)
    assert out[0] == 5.0
    assert all(5.0 <= v <= 6.0 for v in out)


def test_band_rejects_bad_config():
    with pytest.raises(ValueError):
        band(n=0, base=0, range=1)
    with pytest.raises(ValueError):
        band(n=3, base=1, range=-1)   # range negativo


def test_band_at_deterministic_at_given_fracs():
    fracs = [0.0, 0.37, 0.81, 1.0]
    a = band_at(fracs, base=0.001, range=0.009, seed=1988)
    b = band_at(fracs, base=0.001, range=0.009, seed=1988)
    assert a == b
    assert len(a) == len(fracs)
    assert all(0.001 <= v <= 0.01 for v in a)


def test_band_at_evaluated_at_real_times():
    # Banda collassata (range omesso, base mobile): il valore e' l'interpolazione
    # al frac REALE del punto, non all'indice i/(n-1) — coupling con la X-walk.
    bp = [[0, 0], [1, 10]]
    assert band_at([0.0, 0.25, 0.9], base=bp, seed=0) == [0.0, 2.5, 9.0]


def test_band_at_rejects_negative_range():
    with pytest.raises(ValueError):
        band_at([0.0, 0.5], base=1, range=-1)


def test_band_at_rejects_empty_fracs():
    with pytest.raises(ValueError):
        band_at([], base=0, range=1)


def test_resolve_explicit_values_passthrough():
    assert resolve({"path": "x", "values": [1, 2, 3]}) == [1, 2, 3]


def test_resolve_dispatches_to_ramp():
    assert resolve({"path": "x", "ramp": {"start": 1, "stop": 3, "step": 1}}) == [1, 2, 3]


def test_resolve_dispatches_to_band():
    # base piatto marca la banda; con n la Y possiede il conteggio.
    out = resolve({"path": "x", "n": 4, "base": 5, "range": 0})
    assert out == [5.0, 5.0, 5.0, 5.0]


def test_resolve_band_without_n_raises():
    # banda senza n fuori dal coupling con X-walk: errore chiaro.
    with pytest.raises(ValueError):
        resolve({"path": "x", "base": 5, "range": 1})


def test_resolve_rejects_no_generator_key():
    with pytest.raises(ValueError):
        resolve({"path": "x", "baseline": 0})


def test_resolve_rejects_multiple_generator_keys():
    with pytest.raises(ValueError):
        resolve({"path": "x", "values": [1], "ramp": {"start": 1, "stop": 3, "step": 1}})


def test_ramp_ascending_includes_endpoint_no_drift():
    # Il caso reale del diario: 0.003 -> 0.005 a passo 0.00025 = 9 gradini.
    assert ramp(0.003, 0.005, 0.00025) == [
        0.003, 0.00325, 0.0035, 0.00375, 0.004,
        0.00425, 0.0045, 0.00475, 0.005,
    ]


def test_ramp_step_not_dividing_does_not_overshoot():
    # 0.0021 / 0.00025 = 8.4 -> 8 gradini, ultimo 0.005 <= stop, mai oltre.
    out = ramp(0.003, 0.0051, 0.00025)
    assert out[-1] == 0.005
    assert out[-1] <= 0.0051


def test_ramp_rejects_non_positive_step():
    with pytest.raises(ValueError):
        ramp(0.003, 0.005, 0)


def test_ramp_descending():
    assert ramp(0.005, 0.003, 0.00025) == [
        0.005, 0.00475, 0.0045, 0.00425, 0.004,
        0.00375, 0.0035, 0.00325, 0.003,
    ]


# --- generatori annidati: espansione nodo -> breakpoint (plan nested-generators) --

from granstudies.value_generators import (  # noqa: E402
    MAX_ENV_DEPTH,
    expand_env,
    expand_params,
    is_generator_node,
    stable_seed,
)


def test_is_generator_node_recognizes_markers_only():
    assert is_generator_node({"values": [1, 2]})
    assert is_generator_node({"ramp": {"start": 1, "stop": 2, "step": 1}})
    assert is_generator_node({"n": 3, "base": 0, "range": 1})
    # le forme statiche NON sono nodi
    assert not is_generator_node(3.0)
    assert not is_generator_node([1, 5])
    assert not is_generator_node([[0, 1], [1, 5]])
    assert not is_generator_node({"type": "step", "points": [[0, 1], [1, 5]]})


def test_expand_env_passthrough_static_forms():
    for spec in (3.0, [1, 5], [[0, 1], [1, 5]],
                 {"type": "step", "points": [[0, 1], [1, 5]], "curve": 1}):
        assert expand_env(spec, seed=0, path="base") == spec


def test_expand_values_node_spreads_on_linear_grid():
    assert expand_env({"linear_env": {"values": [1, 2, 3]}}, seed=0, path="base") == [
        [0.0, 1], [0.5, 2], [1.0, 3],
    ]


def test_expand_ramp_node():
    assert expand_env({"linear_env": {"ramp": {"start": 1, "stop": 3, "step": 1}}},
                      seed=0, path="base") == [
        [0.0, 1], [0.5, 2], [1.0, 3],
    ]


def test_expand_band_node_matches_band_with_same_seed():
    got = expand_env({"linear_env": {"n": 3, "base": 0, "range": 10, "seed": 5}},
                     seed=0, path="base")
    want = band(3, 0, 10, seed=5)
    assert got == [[0.0, want[0]], [0.5, want[1]], [1.0, want[2]]]


def test_expand_node_with_type_step_returns_dict_form():
    got = expand_env({"type": "step", "linear_env": {"values": [1, 2]}},
                     seed=0, path="base")
    assert got == {"type": "step", "points": [[0.0, 1], [1.0, 2]]}


def test_expand_node_with_curve_returns_dict_form():
    got = expand_env({"curve": 2, "linear_env": {"values": [0, 10]}},
                     seed=0, path="base")
    assert got == {"type": "linear", "points": [[0.0, 0], [1.0, 10]], "curve": 2}
    assert _threshold_at(got, 0.5) == 2.5


def test_expand_node_single_value_holds():
    got = expand_env({"linear_env": {"values": [7]}}, seed=0, path="base")
    assert got == [[0.0, 7]]
    assert _threshold_at(got, 0.9) == 7


def test_expand_band_node_without_n_raises():
    with pytest.raises(ValueError, match="base"):
        expand_env({"linear_env": {"base": 0, "range": 1}}, seed=0, path="base")


def test_expand_node_two_markers_raises():
    with pytest.raises(ValueError):
        expand_env({"linear_env": {"values": [1],
                                   "ramp": {"start": 1, "stop": 2, "step": 1}}},
                   seed=0, path="base")


def test_expand_node_type_cubic_raises():
    with pytest.raises(ValueError, match="cubic"):
        expand_env({"type": "cubic", "linear_env": {"values": [1, 2]}},
                   seed=0, path="base")


def test_expand_node_curve_with_step_raises_with_path():
    with pytest.raises(ValueError, match="base"):
        expand_env({"type": "step", "curve": 2, "linear_env": {"values": [1, 2]}},
                   seed=0, path="base")


def test_expand_recursion_three_levels():
    node = {
        "linear_env": {
            "n": 4,
            "base": {"linear_env": {
                "n": 3, "base": 0,
                "range": {"linear_env": {"ramp": {"start": 1, "stop": 3,
                                                  "step": 1}}},
            }},
            "range": 1,
        }
    }
    a = expand_env(node, seed=42, path="base")
    b = expand_env(node, seed=42, path="base")
    assert a == b
    assert len(a) == 4


def test_expand_depth_guard():
    node = {"linear_env": {"n": 2, "base": 0, "range": 1}}
    for _ in range(MAX_ENV_DEPTH):
        node = {"linear_env": {"n": 2, "base": node, "range": 1}}
    with pytest.raises(ValueError, match="profondit"):
        expand_env(node, seed=0, path="base")


# --- generatori annidati: derivazione del seed ------------------------------------

def test_nested_seed_derived_from_parent_and_path():
    got = expand_env({"linear_env": {"n": 3, "base": 0, "range": 10}},
                     seed=99, path="base")
    want = band(3, 0, 10, seed=stable_seed("99:base"))
    assert [v for _, v in got] == want


def test_nested_base_and_range_decorrelated():
    params = {"n": 5, "base": {"linear_env": {"n": 3, "base": 0, "range": 10}},
              "range": {"linear_env": {"n": 3, "base": 0, "range": 10}}, "seed": 7}
    out = expand_params(params, seed=7)
    assert out["base"] != out["range"]


def test_nested_explicit_seed_wins():
    got = expand_env({"linear_env": {"n": 3, "base": 0, "range": 10, "seed": 5}},
                     seed=99, path="base")
    want = band(3, 0, 10, seed=5)
    assert [v for _, v in got] == want


def test_changing_parent_seed_reseeds_subtree():
    node = {"linear_env": {"n": 3, "base": 0, "range": 10}}
    a = expand_env(node, seed=1, path="base")
    b = expand_env(node, seed=2, path="base")
    assert a != b


def test_expand_params_walks_generic_dict():
    params = {"n": 4, "base": {"linear_env": {"values": [0, 10]}},
              "range": 0.5, "seed": 3}
    out = expand_params(params, seed=3)
    assert out["base"] == [[0.0, 0], [1.0, 10]]
    assert out["range"] == 0.5
    assert out["n"] == 4


def test_constant_width_band_with_nested_base():
    # base annidato + range scalare: la banda trasla a larghezza costante.
    params = expand_params(
        {"n": 50, "base": {"linear_env": [0, 100]}, "range": 1, "seed": 1}, seed=1
    )
    values = band(**params)
    for i, v in enumerate(values):
        lo = 100 * i / 49
        assert lo <= v <= lo + 1


# --- ramp con step: Env (accelerando/ritardando) ----------------------------------

def test_ramp_env_step_with_step_type_deterministic():
    # step: 2 nella prima meta' del progresso, 1 nella seconda.
    out = ramp(0, 10, {"type": "step", "points": [[0, 2], [0.5, 1]]})
    assert out == [0, 2, 4, 6, 7, 8, 9, 10]


def test_ramp_env_accelerando_steps_shrink():
    out = ramp(5, 100, [10, 1])
    diffs = [b - a for a, b in zip(out, out[1:])]
    assert all(d > 0 for d in diffs)
    assert diffs[0] > diffs[-1]
    assert out[0] == 5 and out[-1] <= 100


def test_ramp_env_descending():
    out = ramp(10, 0, {"type": "step", "points": [[0, 2], [0.5, 1]]})
    assert out == [10, 8, 6, 4, 3, 2, 1, 0]


def test_ramp_scalar_branch_unchanged():
    assert ramp(0.003, 0.005, 0.00025) == [
        0.003, 0.00325, 0.0035, 0.00375, 0.004,
        0.00425, 0.0045, 0.00475, 0.005,
    ]


def test_ramp_env_step_reaching_zero_raises():
    with pytest.raises(ValueError):
        ramp(0, 10, [1, 0])


def test_ramp_env_runaway_points_raises():
    with pytest.raises(ValueError, match="punti"):
        ramp(0, 10, [[0, 1e-6], [1, 1e-6]])


def test_ramp_start_equals_stop_single_point():
    assert ramp(5, 5, [1, 2]) == [5]


def test_ramp_env_step_nested_generator_via_expand():
    params = expand_params(
        {"start": 1, "stop": 10,
         "step": {"linear_env": {"n": 3, "base": 1, "range": 2, "seed": 1}}},
        seed=1,
    )
    a = ramp(**params)
    b = ramp(**params)
    assert a == b
    assert a[0] == 1 and a[-1] <= 10
    assert all(y > x for x, y in zip(a, a[1:]))


# --- distribution: come si pesca dentro la banda (issue #16) -----------------------

import random  # noqa: E402
import statistics  # noqa: E402


def test_uniform_default_bit_identical_to_manual_rng():
    # Regressione retrocompat: senza distribution/drift la sequenza e' la stessa
    # estrazione uniforme di sempre, bit a bit.
    rng = random.Random(1988)
    want = [round(rng.uniform(0.001, 0.01), 9) for _ in range(8)]
    assert band(n=8, base=0.001, range=0.009, seed=1988) == want
    assert band(n=8, base=0.001, range=0.009, seed=1988,
                distribution="uniform") == want


def test_gaussian_deterministic_within_band():
    a = band(n=64, base=0.001, range=0.009, seed=7, distribution="gaussian")
    b = band(n=64, base=0.001, range=0.009, seed=7, distribution="gaussian")
    assert a == b
    assert all(0.001 <= v <= 0.01 for v in a)


def test_gaussian_differs_from_uniform_and_concentrates_at_center():
    uni = band(n=400, base=0, range=10, seed=3)
    gau = band(n=400, base=0, range=10, seed=3, distribution="gaussian")
    assert uni != gau
    # Sigma = larghezza/6: la gaussiana sta stretta sul centro banda (5).
    assert statistics.pstdev(gau) < statistics.pstdev(uni)
    assert abs(statistics.fmean(gau) - 5.0) < 0.5


def test_gaussian_collapsed_band_follows_base():
    # Larghezza 0: nessuna varianza, il valore e' il centro (== base).
    assert band(n=3, base=[0.0, 1.0], seed=0, distribution="gaussian") == [0.0, 0.5, 1.0]


def test_gaussian_in_band_at_real_fracs():
    fracs = [0.0, 0.37, 0.81]
    a = band_at(fracs, base=5, range=2, seed=9, distribution="gaussian")
    b = band_at(fracs, base=5, range=2, seed=9, distribution="gaussian")
    assert a == b
    assert all(5 <= v <= 7 for v in a)


def test_unknown_distribution_raises():
    with pytest.raises(ValueError, match="distribution"):
        band(n=3, base=0, range=1, seed=0, distribution="poisson")
    with pytest.raises(ValueError, match="distribution"):
        band_at([0.0], base=0, range=1, seed=0, distribution="poisson")


# --- drift: random walk correlato dentro la banda (issue #16) ----------------------

def test_drift_deterministic_within_band():
    a = band(n=50, base=0, range=10, seed=4, drift={"step": 0.1})
    b = band(n=50, base=0, range=10, seed=4, drift={"step": 0.1})
    assert a == b
    assert all(0 <= v <= 10 for v in a)


def test_drift_steps_bounded_by_step_fraction_of_band():
    # uniform: il passo e' U(-s, +s) con s = step * larghezza. Nessun salto
    # oltre s (banda fissa: niente clamp/riflessione che accorci il confronto).
    out = band(n=100, base=0, range=10, seed=4, drift={"step": 0.05})
    diffs = [abs(b - a) for a, b in zip(out, out[1:])]
    assert max(diffs) <= 0.5 + 1e-9


def test_drift_correlated_vs_independent_draws():
    # La deriva a passi piccoli si muove molto meno del pescaggio indipendente.
    ind = band(n=200, base=0, range=10, seed=4)
    dri = band(n=200, base=0, range=10, seed=4, drift={"step": 0.02})
    mean_jump = lambda xs: statistics.fmean(  # noqa: E731
        abs(b - a) for a, b in zip(xs, xs[1:])
    )
    assert mean_jump(dri) < mean_jump(ind) / 5


def test_drift_initial_value_is_ordinary_draw():
    # Il primo valore e' il pescaggio di sempre (stesso RNG della banda).
    rng = random.Random(4)
    want = round(rng.uniform(0, 10), 9)
    out = band(n=10, base=0, range=10, seed=4, drift={"step": 0.1})
    assert out[0] == want


def test_drift_reflects_at_band_border():
    # Passo enorme (10x la banda): il valore rimbalza e resta dentro.
    out = band(n=100, base=0, range=1, seed=4, drift={"step": 10})
    assert all(0 <= v <= 1 for v in out)


def test_drift_clamped_into_moving_band():
    # La banda trasla via dal valore corrente: clamp immediato dentro i nuovi
    # limiti (poi si cammina). Passo ~0: il valore insegue il bordo della banda.
    out = band(n=5, base=[0, 100], range=1, seed=4, drift={"step": 1e-12})
    for i, v in enumerate(out):
        lo = 100 * i / 4
        assert lo - 1e-6 <= v <= lo + 1 + 1e-6


def test_drift_step_env_freezes_where_zero():
    # step come Env: 0 nella seconda meta' -> il valore si congela.
    step = {"type": "step", "points": [[0, 0.2], [0.5, 0]]}
    out = band(n=11, base=0, range=10, seed=4, drift={"step": step})
    tail = out[6:]
    assert all(v == tail[0] for v in tail)


def test_drift_gaussian_deterministic_and_in_band():
    a = band(n=50, base=0, range=10, seed=4, distribution="gaussian",
             drift={"step": 0.1})
    b = band(n=50, base=0, range=10, seed=4, distribution="gaussian",
             drift={"step": 0.1})
    assert a == b
    assert all(0 <= v <= 10 for v in a)
    assert a != band(n=50, base=0, range=10, seed=4, drift={"step": 0.1})


def test_drift_collapsed_band_follows_base():
    assert band(n=3, base=[0.0, 1.0], seed=0, drift={"step": 0.5}) == [0.0, 0.5, 1.0]


def test_drift_seed_derived_from_band_seed():
    # Senza seed proprio il drift deriva stable_seed(f"{seed}:drift") — il seed
    # esplicito equivalente produce la stessa sequenza, uno diverso no.
    auto = band(n=20, base=0, range=10, seed=9, drift={"step": 0.1})
    same = band(n=20, base=0, range=10, seed=9,
                drift={"step": 0.1, "seed": stable_seed("9:drift")})
    other = band(n=20, base=0, range=10, seed=9, drift={"step": 0.1, "seed": 123})
    assert auto == same
    assert auto != other
    assert auto[0] == other[0]  # il pescaggio iniziale e' della banda, non del drift


def test_drift_in_band_at():
    fracs = [0.0, 0.1, 0.25, 0.6, 1.0]
    a = band_at(fracs, base=0, range=10, seed=4, drift={"step": 0.1})
    b = band_at(fracs, base=0, range=10, seed=4, drift={"step": 0.1})
    assert a == b
    assert all(0 <= v <= 10 for v in a)


def test_drift_requires_step():
    with pytest.raises(ValueError, match="step"):
        band(n=3, base=0, range=1, seed=0, drift={})


def test_drift_rejects_unknown_keys():
    with pytest.raises(ValueError, match="drift"):
        band(n=3, base=0, range=1, seed=0, drift={"step": 0.1, "sigma": 2})


def test_drift_rejects_non_dict():
    with pytest.raises(ValueError, match="drift"):
        band(n=3, base=0, range=1, seed=0, drift=0.1)


def test_drift_negative_step_raises():
    with pytest.raises(ValueError, match="step"):
        band(n=5, base=0, range=1, seed=0, drift={"step": -0.1})


def test_drift_step_nested_generator_via_expand():
    # drift.step e' un Env: un nodo-generatore dentro si espande alla seam
    # (path drift.step, seed derivato dalla catena gerarchica).
    params = expand_params(
        {"n": 30, "base": 0, "range": 10, "seed": 5,
         "drift": {"step": {"linear_env": {"n": 3, "base": 0.01,
                                           "range": 0.1}}}},
        seed=5,
    )
    assert isinstance(params["drift"]["step"], list)  # compilato in breakpoint
    want = band(3, 0.01, 0.1, seed=stable_seed("5:drift.step"))
    assert [v for _, v in params["drift"]["step"]] == want
    a = band(**params)
    b = band(**params)
    assert a == b
    assert all(0 <= v <= 10 for v in a)


# --- nodo-expr: {expr, let} come forma di Threshold (plan expr-env-arithmetic) ----

def test_expand_env_expr_node_breakpoints():
    node = {"expr": "env * 50", "let": {"env": [[0, 1], [0.1583, 1.5]]}}
    assert expand_env(node, seed=0, path="base") == [[0, 50], [0.1583, 75]]


def test_expand_env_expr_node_scalar():
    assert expand_env({"expr": "2 * 25"}, seed=0, path="base") == 50


def test_expand_env_expr_node_nested_let():
    # expr annidato in let (issue #28): 's' fattorizza una sagoma calcolata
    node = {
        "expr": "s * 2",
        "let": {"env": [[0, 1], [1, 2]], "s": {"expr": "env + 1"}},
    }
    assert expand_env(node, seed=0, path="base") == [[0, 4], [1, 6]]


def test_expand_env_expr_node_nested_cycle_carries_path():
    node = {"expr": "a", "let": {"a": {"expr": "b"}, "b": {"expr": "a"}}}
    with pytest.raises(ValueError, match=r"base.*ciclo"):
        expand_env(node, seed=0, path="base")


def test_expand_params_routes_expr_node_in_band_base():
    params = {
        "base": {"expr": "env + 1", "let": {"env": [[0, 0], [1, 1]]}},
        "range": 0,
    }
    out = expand_params(params, seed=0)
    assert out["base"] == [[0, 1], [1, 2]]
    assert out["range"] == 0


def test_expand_params_expr_node_in_drift_step():
    # drift non e' un nodo: expand_params lo attraversa e trova l'expr dentro.
    params = {"drift": {"step": {"expr": "s / 2", "let": {"s": 0.2}}}}
    out = expand_params(params, seed=0)
    assert out["drift"]["step"] == 0.1


def test_expr_node_eval_error_carries_path():
    with pytest.raises(ValueError, match=r"range\.step"):
        expand_env({"expr": "boh * 2"}, seed=0, path="range.step")


def test_expr_node_extra_key_raises():
    with pytest.raises(ValueError, match="seed"):
        expand_env({"expr": "1", "seed": 3}, seed=0, path="base")


def test_expr_node_result_env_validated_immediately():
    # il risultato passa da _threshold_at: curve con type step e' rifiutata qui,
    # col path, non a valle.
    node = {
        "expr": "env * 2",
        "let": {"env": {"type": "step", "points": [[0, 1], [1, 2]], "curve": 2}},
    }
    with pytest.raises(ValueError, match="base"):
        expand_env(node, seed=0, path="base")


def test_threshold_at_rejects_unexpanded_expr_node():
    with pytest.raises(ValueError, match="espanso"):
        _threshold_at({"expr": "1 + 1"}, 0.0)


def test_expr_node_resolves_end_to_end_in_axis_band():
    from granstudies.study_spec import resolve_streams

    doc = {
        "study_id": "s",
        "base": {"onset": 0},
        "axes": {
            "a": {
                "path": "density", "baseline": 20, "n": 2, "range": 0,
                "base": {"expr": "env * 50", "let": {"env": [[0, 1], [1, 1.5]]}},
            },
        },
    }
    (spec,) = resolve_streams(doc)
    (axis,) = spec.axes
    assert axis.values == [50.0, 75.0]  # banda collassata sull'Env valutato
