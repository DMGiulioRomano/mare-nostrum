import pytest

from granstudies.x_strategies import linear, resolve_x, walk, x_owns_n


# --- linear (default: tempi equispaziati) ---------------------------------------

def test_linear_five_points_equispaced():
    assert linear(n=5) == [0.0, 0.25, 0.5, 0.75, 1.0]


def test_linear_single_point():
    assert linear(n=1) == [0.0]


def test_linear_two_points_are_extremes():
    assert linear(n=2) == [0.0, 1.0]


def test_linear_rejects_non_positive_n():
    with pytest.raises(ValueError):
        linear(n=0)


# --- resolve_x (linear = assenza dell'asse dal blocco stack) ---------------------

def test_resolve_x_default_is_linear():
    # Config vuota o assente -> linear (n dalla Y).
    assert resolve_x({}, n=3) == [0.0, 0.5, 1.0]
    assert resolve_x(None, n=3) == [0.0, 0.5, 1.0]


def test_resolve_x_rejects_walk_with_external_n():
    # Una entry con 'base' e' una camminata (possiede n): non risolvibile con
    # un n dalla Y.
    with pytest.raises(ValueError):
        resolve_x({"base": 5}, n=10)


def test_resolve_x_rejects_entry_without_base():
    # Una entry sotto stack senza 'base' e' malformata (niente piu' nome-strategy).
    with pytest.raises(ValueError):
        resolve_x({"seed": 3}, n=5)


# --- walk (i tempi emergono dalla frequenza, la X possiede n) --------------------

def test_walk_deterministic_with_seed():
    a = walk(duration=25.0, base=[[0, 3], [1, 10]], range=[[0, 1], [1, 1]], seed=7)
    b = walk(duration=25.0, base=[[0, 3], [1, 10]], range=[[0, 1], [1, 1]], seed=7)
    assert a == b


def test_walk_different_seed_differs():
    a = walk(duration=25.0, base=[[0, 3], [1, 10]], range=[[0, 1], [1, 1]], seed=1)
    b = walk(duration=25.0, base=[[0, 3], [1, 10]], range=[[0, 1], [1, 1]], seed=2)
    assert a != b


def test_walk_times_sorted_normalized_start_at_zero():
    times = walk(duration=10.0, base=5, range=2, seed=0)
    assert times[0] == 0.0
    assert times == sorted(times)
    assert all(0.0 <= t < 1.0 for t in times)


def test_walk_n_emerges_from_frequency():
    # Banda collassata (range 0): f=5 Hz esatti su 10 s -> passo 0.2 s -> 50 punti.
    times = walk(duration=10.0, base=5, range=0, seed=0)
    assert len(times) == 50


def test_walk_deterministic_branch_never_hits_t_one():
    # range assente = camminata deterministica: come la stocastica, mai un punto
    # esatto su t=1.0 (il bordo e' coperto dall'hold dell'envelope).
    times = walk(duration=10.0, base=5)
    assert all(t < 1.0 for t in times)


def test_walk_higher_frequency_more_points():
    lo = walk(duration=10.0, base=2, range=0.5, seed=3)
    hi = walk(duration=10.0, base=20, range=0.5, seed=3)
    assert len(hi) > len(lo)


def test_walk_frequency_envelope_densifies_where_high():
    # Frequenza bassa nella prima meta', alta nella seconda: piu' punti dopo 0.5.
    base = {"type": "step", "points": [[0, 2], [0.5, 40]]}
    times = walk(duration=10.0, base=base, range=0, seed=0)
    first = [t for t in times if t < 0.5]
    second = [t for t in times if t >= 0.5]
    assert len(second) > len(first)


def test_walk_curve_warps_frequency_envelope():
    # curve dentro l'Env di base: la frequenza scende con u^2 -> resta alta piu'
    # a lungo (piu' punti nella prima meta') rispetto alla discesa lineare.
    lin = walk(duration=10.0, base=[[0, 10], [1, 1]], seed=0)
    crv = walk(duration=10.0, base={"points": [[0, 10], [1, 1]], "curve": 2}, seed=0)
    assert len([t for t in crv if t < 0.5]) > len([t for t in lin if t < 0.5])


def test_walk_rejects_non_positive_frequency():
    with pytest.raises(ValueError):
        walk(duration=10.0, base=0, range=0, seed=0)


def test_walk_caps_runaway_frequency():
    with pytest.raises(ValueError):
        walk(duration=10.0, base=1e9, range=0, seed=0)


def test_walk_rejects_non_positive_duration():
    with pytest.raises(ValueError):
        walk(duration=0.0, base=5, range=0, seed=0)


# --- distribution e drift nella camminata (issue #16) ------------------------------

def test_walk_default_unchanged_with_explicit_uniform():
    # Retrocompat: distribution uniform esplicita = stessa camminata di sempre.
    a = walk(duration=10.0, base=3, range=4, seed=7)
    b = walk(duration=10.0, base=3, range=4, seed=7, distribution="uniform")
    assert a == b


def test_walk_gaussian_deterministic_and_valid():
    a = walk(duration=10.0, base=3, range=4, seed=7, distribution="gaussian")
    b = walk(duration=10.0, base=3, range=4, seed=7, distribution="gaussian")
    assert a == b
    assert a != walk(duration=10.0, base=3, range=4, seed=7)
    assert a[0] == 0.0 and a == sorted(a) and all(0 <= t < 1 for t in a)


def test_walk_drift_deterministic_and_valid():
    a = walk(duration=10.0, base=3, range=4, seed=7, drift={"step": 0.1})
    b = walk(duration=10.0, base=3, range=4, seed=7, drift={"step": 0.1})
    assert a == b
    assert a != walk(duration=10.0, base=3, range=4, seed=7)
    assert a[0] == 0.0 and a == sorted(a) and all(0 <= t < 1 for t in a)


def test_walk_drift_intervals_change_gradually():
    # Deriva a passi piccoli: gli intervalli tra breakpoint variano poco tra
    # passi adiacenti rispetto al pescaggio indipendente della frequenza.
    def mean_jump(times):
        dts = [b - a for a, b in zip(times, times[1:])]
        return sum(abs(y - x) for x, y in zip(dts, dts[1:])) / (len(dts) - 1)

    ind = walk(duration=60.0, base=2, range=8, seed=7)
    dri = walk(duration=60.0, base=2, range=8, seed=7, drift={"step": 0.02})
    assert mean_jump(dri) < mean_jump(ind) / 3


def test_walk_unknown_distribution_raises():
    with pytest.raises(ValueError, match="distribution"):
        walk(duration=10.0, base=3, range=4, seed=7, distribution="poisson")


def test_walk_drift_malformed_raises():
    with pytest.raises(ValueError, match="step"):
        walk(duration=10.0, base=3, range=4, seed=7, drift={})


# --- unit della camminata: hz (default) | s (periodo) ------------------------------

def test_walk_unit_hz_explicit_equals_default():
    a = walk(duration=10.0, base=3, range=4, seed=7)
    b = walk(duration=10.0, base=3, range=4, seed=7, unit="hz")
    assert a == b


def test_walk_unit_s_deterministic_period():
    # Banda collassata: periodo 2 s esatti su 10 s -> punti a 0, 2, 4, 6, 8 s.
    times = walk(duration=10.0, base=2, range=0, unit="s")
    assert times == [0.0, 0.2, 0.4, 0.6, 0.8]
    # Equivalenza col reciproco: 0.5 Hz = un punto ogni 2 s.
    assert times == walk(duration=10.0, base=0.5, range=0)


def test_walk_unit_s_band_draws_periods_in_seconds():
    # Banda [10, 30] s: ogni intervallo reale tra punti cade nella banda.
    duration = 300.0
    times = walk(duration=duration, base=10, range=20, seed=7, unit="s")
    dts = [(b - a) * duration for a, b in zip(times, times[1:])]
    assert dts and all(10 - 1e-6 <= dt <= 30 + 1e-6 for dt in dts)


def test_walk_unit_s_envelope_interpolated_in_period_space():
    # Periodo che si stringe nella seconda meta': densifica dove e' corto.
    base = {"type": "step", "points": [[0, 2], [0.5, 0.25]]}
    times = walk(duration=10.0, base=base, range=0, unit="s")
    first = [t for t in times if t < 0.5]
    second = [t for t in times if t >= 0.5]
    assert len(second) > len(first)


def test_walk_unit_s_is_not_a_relabeled_hz():
    # Stessa banda numerica, spazio diverso: uniforme in periodo non e'
    # uniforme in frequenza, le camminate differiscono a parita' di seed.
    a = walk(duration=10.0, base=0.5, range=0.5, seed=7)
    b = walk(duration=10.0, base=0.5, range=0.5, seed=7, unit="s")
    assert a != b


def test_walk_unit_s_rejects_non_positive_period():
    with pytest.raises(ValueError, match="periodo"):
        walk(duration=10.0, base=0, range=0, unit="s")


def test_walk_unit_s_caps_runaway_period():
    # Periodo minuscolo = milioni di punti: stesso tetto anti-runaway.
    with pytest.raises(ValueError):
        walk(duration=10.0, base=1e-9, range=0, unit="s")


def test_walk_unknown_unit_raises():
    with pytest.raises(ValueError, match="unit"):
        walk(duration=10.0, base=2, range=0, unit="ms")


def test_walk_unit_bpm_deterministic_pulse():
    # Banda collassata: 60 bpm = un punto al secondo su 10 s -> 10 punti.
    times = walk(duration=10.0, base=60, range=0, unit="bpm")
    assert times == [round(i / 10, 9) for i in range(10)]
    # Equivalenza col rate: 60 bpm = 1 Hz.
    assert times == walk(duration=10.0, base=1, range=0)


def test_walk_unit_bpm_is_rescaled_hz_space():
    # bpm e' lo spazio-rate riscalato (bpm = 60*hz): la banda [60, 120] bpm
    # produce la stessa camminata della banda [1, 2] Hz, a parita' di seed.
    a = walk(duration=10.0, base=60, range=60, seed=7, unit="bpm")
    b = walk(duration=10.0, base=1, range=1, seed=7, unit="hz")
    assert a == pytest.approx(b)


def test_walk_unit_bpm_rejects_non_positive():
    with pytest.raises(ValueError, match="bpm"):
        walk(duration=10.0, base=0, range=0, unit="bpm")


# --- n-ownership -----------------------------------------------------------------

def test_x_owns_n_true_when_base_present():
    assert x_owns_n({"base": 5}) is True
    assert x_owns_n({"base": [[0, 3], [1, 10]], "range": 1, "seed": 7}) is True
    assert x_owns_n({}) is False
    assert x_owns_n({"seed": 3}) is False
    assert x_owns_n(None) is False
