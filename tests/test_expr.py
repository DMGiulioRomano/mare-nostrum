import pytest

from granstudies.expr import eval_expr, is_expr_node, parse_expr_node


# --- scalari -----------------------------------------------------------------

def test_precedence_and_parens():
    assert eval_expr("2 + 3 * 4", {}) == 14
    assert eval_expr("(2 + 3) * 4", {}) == 20


def test_names_resolve_in_scope():
    assert eval_expr("a * (i + 1)", {"a": 50, "i": 3}) == 200


def test_unary_minus_and_pow():
    assert eval_expr("-a ** 2", {"a": 3}) == -9   # precedenza python: -(3**2)
    assert eval_expr("(-a) ** 2", {"a": 3}) == 9


def test_progress_fraction():
    assert eval_expr("i / (n - 1)", {"i": 2, "n": 5}) == 0.5


def test_no_free_names_empty_scope():
    assert eval_expr("1 + 2", {}) == 3


def test_result_rounded_9_decimals():
    assert eval_expr("1 / 3", {}) == round(1 / 3, 9)


# --- Env ⊙ scalare -----------------------------------------------------------

def test_env_breakpoints_times_scalar_scales_y_keeps_t():
    env = [[0, 1], [0.1583, 1.5]]
    assert eval_expr("env * 50", {"env": env}) == [[0, 50], [0.1583, 75]]


def test_env_plus_scalar_shifts_y():
    env = [[0, 0], [0.1583, 0.5]]
    assert eval_expr("env + 50", {"env": env}) == [[0, 50], [0.1583, 50.5]]


def test_env_shorthand_two_scalars():
    assert eval_expr("env * 2", {"env": [10, 20]}) == [20, 40]


def test_env_dict_form_preserves_type_and_curve():
    env = {"type": "linear", "points": [[0, 1], [1, 2]], "curve": 2}
    out = eval_expr("env * 10", {"env": env})
    assert out == {"type": "linear", "points": [[0, 10], [1, 20]], "curve": 2}


def test_scalar_minus_env_respects_order():
    env = [[0, 10], [1, 20]]
    assert eval_expr("100 - env", {"env": env}) == [[0, 90], [1, 80]]


def test_env_div_scalar():
    env = [[0, 10], [1, 20]]
    assert eval_expr("env / 2", {"env": env}) == [[0, 5], [1, 10]]


def test_unary_minus_on_env():
    assert eval_expr("-env", {"env": [[0, 1], [1, 2]]}) == [[0, -1], [1, -2]]


def test_env_result_does_not_alias_scope():
    env = [[0, 1], [1, 2]]
    out = eval_expr("env", {"env": env})
    assert out == env
    out[0][1] = 99
    assert env[0][1] == 1


def test_compound_env_expression():
    env = [[0, 1], [0.1583, 1.5]]
    out = eval_expr("env * a * (i + 1)", {"env": env, "a": 50, "i": 1})
    assert out == [[0, 100], [0.1583, 150]]


# --- operatori % e // ----------------------------------------------------------

def test_modulo_and_floordiv():
    assert eval_expr("10 % 3", {}) == 1
    assert eval_expr("7 // 2", {}) == 3
    assert eval_expr("-7 % 3", {}) == 2   # semantica Python: segno del divisore


def test_modulo_on_env_elementwise():
    env = [[0, 5], [1, 7]]
    assert eval_expr("env % 4", {"env": env}) == [[0, 1], [1, 3]]


def test_modulo_by_zero():
    with pytest.raises(ValueError, match="zero"):
        eval_expr("10 % 0", {})


# --- funzioni primitive e costanti ----------------------------------------------

def test_rounding_functions():
    assert eval_expr("floor(2.7)", {}) == 2
    assert eval_expr("ceil(2.1)", {}) == 3
    assert eval_expr("abs(0 - 3)", {}) == 3


def test_sqrt_exp_log():
    assert eval_expr("sqrt(9)", {}) == 3
    assert eval_expr("exp(0)", {}) == 1
    assert eval_expr("log(e)", {}) == 1
    assert eval_expr("log(8, 2)", {}) == 3


def test_trig_and_constants():
    import math

    assert eval_expr("sin(0)", {}) == 0
    assert eval_expr("cos(0)", {}) == 1
    assert eval_expr("tan(0)", {}) == 0
    assert eval_expr("atan(1)", {}) == round(math.pi / 4, 9)
    assert eval_expr("pi", {}) == round(math.pi, 9)
    assert eval_expr("cos(2 * pi)", {}) == 1


def test_scope_shadows_constants():
    assert eval_expr("pi", {"pi": 3}) == 3


def test_min_max_scalars():
    assert eval_expr("min(3, i)", {"i": 1}) == 1
    assert eval_expr("max(1, 2, 3)", {}) == 3


def test_nested_calls():
    assert eval_expr("floor(sqrt(10))", {}) == 3


def test_function_on_env_maps_y():
    env = [[0, 0], [1, 9]]
    assert eval_expr("sqrt(env)", {"env": env}) == [[0, 0], [1, 3]]


def test_min_clamps_env_y():
    env = [[0, 5], [1, 20]]
    assert eval_expr("min(env, 10)", {"env": env}) == [[0, 5], [1, 10]]


def test_max_on_env_shorthand():
    assert eval_expr("max(env, 0)", {"env": [-5, 5]}) == [0, 5]


def test_function_preserves_env_dict_form():
    env = {"type": "linear", "points": [[0, 1.7], [1, 2.2]], "curve": 2}
    out = eval_expr("floor(env)", {"env": env})
    assert out == {"type": "linear", "points": [[0, 1], [1, 2]], "curve": 2}


def test_unknown_function_lists_available():
    with pytest.raises(ValueError) as exc:
        eval_expr("foo(1)", {})
    assert "foo" in str(exc.value)
    assert "sin" in str(exc.value)


def test_wrong_arity_raises():
    with pytest.raises(ValueError, match="argoment"):
        eval_expr("sqrt(1, 2)", {})
    with pytest.raises(ValueError, match="argoment"):
        eval_expr("min(1)", {})


def test_keyword_args_rejected():
    with pytest.raises(ValueError, match="keyword"):
        eval_expr("log(8, base=2)", {})


def test_math_domain_error_is_clear():
    with pytest.raises(ValueError, match="dominio"):
        eval_expr("sqrt(0 - 1)", {})
    with pytest.raises(ValueError, match="dominio"):
        eval_expr("log(0)", {})


def test_call_with_two_envs_rejected():
    envs = {"e1": [[0, 1], [1, 2]], "e2": [[0, 3], [1, 4]]}
    with pytest.raises(ValueError, match="Env"):
        eval_expr("min(e1, e2)", envs)


def test_starred_args_rejected():
    with pytest.raises(ValueError):
        eval_expr("min(*e)", {"e": [[0, 1], [1, 2]]})


def test_complex_result_rejected():
    with pytest.raises(ValueError, match="compless"):
        eval_expr("(0 - 1) ** 0.5", {})


# --- errori ------------------------------------------------------------------

def test_unknown_name_lists_scope():
    with pytest.raises(ValueError) as exc:
        eval_expr("a * b", {"a": 1, "x": 2})
    assert "b" in str(exc.value)
    assert "a" in str(exc.value) and "x" in str(exc.value)


def test_env_times_env_rejected():
    envs = {"e1": [[0, 1], [1, 2]], "e2": [[0, 3], [1, 4]]}
    with pytest.raises(ValueError, match="Env"):
        eval_expr("e1 * e2", envs)


def test_call_on_non_name_rejected():
    with pytest.raises(ValueError):
        eval_expr("(1)(2)", {})


def test_subscript_rejected():
    with pytest.raises(ValueError):
        eval_expr("e[0]", {"e": [[0, 1], [1, 2]]})


def test_comparison_rejected():
    with pytest.raises(ValueError):
        eval_expr("1 < 2", {})


def test_bool_constant_rejected():
    with pytest.raises(ValueError):
        eval_expr("True", {})


def test_string_constant_rejected():
    with pytest.raises(ValueError):
        eval_expr("'x'", {})


def test_division_by_zero():
    with pytest.raises(ValueError, match="zero"):
        eval_expr("1 / 0", {})


def test_env_division_by_zero():
    with pytest.raises(ValueError, match="zero"):
        eval_expr("env / 0", {"env": [[0, 1], [1, 2]]})


def test_broken_syntax():
    with pytest.raises(ValueError):
        eval_expr("a *", {"a": 1})


def test_unrecognized_scope_form():
    with pytest.raises(ValueError, match="forma"):
        eval_expr("v * 2", {"v": {"ramp": {"start": 0, "step": 1}}})


def test_bool_in_scope_rejected():
    with pytest.raises(ValueError):
        eval_expr("v * 2", {"v": True})


# --- nodo-expr: riconoscimento e validazione ----------------------------------

def test_is_expr_node():
    assert is_expr_node({"expr": "a * 2", "let": {"a": 1}})
    assert is_expr_node({"expr": "1 + 1"})
    assert not is_expr_node({"ramp": {"start": 0}})
    assert not is_expr_node([[0, 1]])
    assert not is_expr_node(3)


def test_parse_expr_node_returns_text_and_let():
    text, let = parse_expr_node({"expr": "a * 2", "let": {"a": 1}})
    assert text == "a * 2"
    assert let == {"a": 1}


def test_parse_expr_node_let_optional():
    assert parse_expr_node({"expr": "1 + 1"}) == ("1 + 1", {})


def test_parse_expr_node_extra_keys_raise():
    with pytest.raises(ValueError, match="seed"):
        parse_expr_node({"expr": "1", "let": {}, "seed": 3})


def test_parse_expr_node_expr_not_string_raises():
    with pytest.raises(ValueError):
        parse_expr_node({"expr": 42})


def test_parse_expr_node_let_not_dict_raises():
    with pytest.raises(ValueError):
        parse_expr_node({"expr": "1", "let": [1, 2]})


def test_parse_expr_node_generator_in_let_raises():
    node = {"expr": "v * 2", "let": {"v": {"ramp": {"start": 0, "step": 1}}}}
    with pytest.raises(ValueError, match="statiche"):
        parse_expr_node(node)


# --- expr annidati dentro let (issue #28) --------------------------------------

def _nested(levels: int):
    """Un nodo-expr annidato sintatticamente per ``levels`` livelli di let."""
    node = {"expr": "1"}
    for _ in range(levels):
        node = {"expr": "v", "let": {"v": node}}
    return node


def test_parse_expr_node_accepts_nested_expr_in_let():
    node = {"expr": "b * 2", "let": {"a": 2, "b": {"expr": "a + 1"}}}
    text, let = parse_expr_node(node)
    assert text == "b * 2"
    assert let["b"] == {"expr": "a + 1"}


def test_parse_expr_node_validates_nested_node():
    # le regole del nodo-expr valgono anche annidato: chiavi extra sono errore
    node = {"expr": "b", "let": {"b": {"expr": "1", "seed": 3}}}
    with pytest.raises(ValueError, match="seed"):
        parse_expr_node(node)


def test_parse_expr_node_nested_depth_guard():
    assert parse_expr_node(_nested(8))  # al limite: valido
    with pytest.raises(ValueError, match="profondit"):
        parse_expr_node(_nested(9))


def test_nested_expr_resolves_sibling():
    scope = {"a": 2, "b": {"expr": "a + 1"}}
    assert eval_expr("b * 2", scope) == 6


def test_nested_expr_order_independent():
    # 'b' dichiarato prima di 'a': la risoluzione e' per dipendenze, non
    # per ordine di dichiarazione
    scope = {"b": {"expr": "a * 2"}, "a": 3}
    assert eval_expr("b", scope) == 6


def test_nested_expr_chain():
    scope = {"a": 1, "b": {"expr": "a + 1"}, "c": {"expr": "b * 10"}}
    assert eval_expr("c + b", scope) == 22


def test_nested_expr_env_result_enters_arithmetic():
    scope = {"env": [[0, 1], [1, 2]], "s": {"expr": "env * 2"}}
    assert eval_expr("s + 1", scope) == [[0, 3], [1, 5]]


def test_nested_expr_own_let_shadows_outer():
    scope = {"a": 1, "v": {"expr": "a + 1", "let": {"a": 10}}}
    assert eval_expr("v", scope) == 11
    # l'ombreggiatura resta locale: fuori 'a' e' ancora quello esterno
    assert eval_expr("v + a", scope) == 12


def test_nested_expr_own_let_inherits_outer_scope():
    scope = {"k": 5, "v": {"expr": "k + w", "let": {"w": 2}}}
    assert eval_expr("v", scope) == 7


def test_nested_expr_same_name_at_different_levels_is_not_a_cycle():
    # 'x' esterno dipende da 'm', che ombreggia 'x' nel proprio let:
    # binding diversi con lo stesso nome, nessun ciclo
    scope = {
        "x": {
            "expr": "m",
            "let": {"m": {"expr": "x * 2", "let": {"x": {"expr": "5"}}}},
        },
    }
    assert eval_expr("x", scope) == 10


def test_nested_expr_cycle_raises():
    scope = {"a": {"expr": "b"}, "b": {"expr": "a"}}
    with pytest.raises(ValueError, match="ciclo"):
        eval_expr("a", scope)


def test_nested_expr_self_reference_raises():
    with pytest.raises(ValueError, match="ciclo"):
        eval_expr("a", {"a": {"expr": "a * 2"}})


def test_nested_expr_shadowing_cannot_reference_shadowed():
    # un nome ridefinito in un let interno non vede il nome esterno che
    # ombreggia: e' un auto-riferimento, quindi ciclo
    scope = {"a": 1, "v": {"expr": "a", "let": {"a": {"expr": "a + 1"}}}}
    with pytest.raises(ValueError, match="ciclo"):
        eval_expr("v", scope)


def test_nested_expr_dependency_chain_depth_guard():
    # catena piatta di dipendenze: 8 risoluzioni in volo passano, 9 no
    ok = {f"v{k}": {"expr": f"v{k + 1} + 1"} for k in range(8)}
    ok["v8"] = 1
    assert eval_expr("v0", ok) == 9
    deep = {f"v{k}": {"expr": f"v{k + 1} + 1"} for k in range(9)}
    deep["v9"] = 1
    with pytest.raises(ValueError, match="profondit"):
        eval_expr("v0", deep)


def test_nested_expr_error_names_the_variable():
    with pytest.raises(ValueError) as exc:
        eval_expr("v", {"v": {"expr": "boh"}})
    assert "let.v" in str(exc.value)
    assert "boh" in str(exc.value)


def test_nested_expr_two_env_results_still_rejected():
    scope = {
        "e1": {"expr": "env * 2"},
        "e2": {"expr": "env + 1"},
        "env": [[0, 1], [1, 2]],
    }
    with pytest.raises(ValueError, match="Env"):
        eval_expr("e1 * e2", scope)


def test_nested_expr_feeds_mix():
    scope = {
        "a": {"expr": "env"},
        "env": [[0, 0], [1, 10]],
    }
    assert eval_expr("mix(a, 0, 0.5)", scope) == [[0, 0], [1, 5]]


def test_nested_expr_generator_in_nested_let_raises():
    node = {
        "expr": "v",
        "let": {"v": {"expr": "w", "let": {"w": {"ramp": {"start": 0, "step": 1}}}}},
    }
    with pytest.raises(ValueError, match="statiche"):
        parse_expr_node(node)


def test_nested_expr_result_does_not_alias_scope():
    env = [[0, 1], [1, 2]]
    scope = {"env": env, "v": {"expr": "env"}}
    out = eval_expr("v", scope)
    assert out == env
    out[0][1] = 99
    assert env[0][1] == 1


# --- mix(A, B, w): il morphing tra due forme (unica porta Env⊙Env) -------------

def _at(env, t):
    """Campiona una forma statica di Env al tempo ``t`` (per i bound test)."""
    from granstudies.value_generators import _threshold_at

    return _threshold_at(env, t)


def test_mix_scalar_lerp():
    assert eval_expr("mix(3, 8, 0.5)", {}) == 5.5


def test_mix_scalar_endpoints():
    assert eval_expr("mix(3, 8, 0)", {}) == 3
    assert eval_expr("mix(3, 8, 1)", {}) == 8


def test_mix_no_clamp_extrapolates():
    assert eval_expr("mix(0, 10, 1.5)", {}) == 15
    assert eval_expr("mix(0, 10, -0.5)", {}) == -5


def test_mix_linear_linear_union_exact():
    a = [[0, 10], [0.6, 2], [1, 0.1]]
    b = [[0, 2], [1, 2]]
    out = eval_expr("mix(a, b, 0.5)", {"a": a, "b": b})
    # breakpoint sull'unione dei tempi, lerp esatto in ognuno
    assert out == [[0, 6], [0.6, 2], [1, 1.05]]


def test_mix_linear_exact_everywhere():
    # il fast-path emette la forma piecewise-linear vera: esatta in ogni punto,
    # non solo sui breakpoint
    a = [[0, 0], [1, 10]]
    b = [[0, 10], [0.5, 0], [1, 10]]
    out = eval_expr("mix(a, b, 0.25)", {"a": a, "b": b})
    assert out == [[0, 2.5], [0.5, 3.75], [1, 10]]


def test_mix_broadcast_scalar_to_env():
    # lo scalare diventa Env costante: il risultato vive sui tempi dell'Env
    a = [[0, 0], [1, 10]]
    assert eval_expr("mix(a, 4, 0.5)", {"a": a}) == [[0, 2], [1, 7]]
    assert eval_expr("mix(4, a, 0.5)", {"a": a}) == [[0, 2], [1, 7]]


def test_mix_shorthand_is_linear():
    out = eval_expr("mix(a, b, 0.5)", {"a": [0, 10], "b": [10, 0]})
    assert out == [[0, 5], [1, 5]]


def test_mix_dict_linear_curve_one_is_exact():
    a = {"type": "linear", "points": [[0, 0], [1, 10]], "curve": 1}
    b = [[0, 10], [1, 0]]
    out = eval_expr("mix(a, b, 0.5)", {"a": a, "b": b})
    assert out == [[0, 5], [1, 5]]


def test_mix_w_env_scalar_forms_exact():
    # w-Env con A e B scalari: il risultato segue w, esatto sui suoi tempi
    w = [[0, 0], [0.5, 1], [1, 0]]
    out = eval_expr("mix(0, 10, w)", {"w": w})
    assert out == [[0, 0], [0.5, 10], [1, 0]]


def test_mix_step_step_union():
    a = {"type": "step", "points": [[0, 1], [0.5, 3]]}
    b = {"type": "step", "points": [[0, 11], [0.25, 7]]}
    out = eval_expr("mix(a, b, 0.5)", {"a": a, "b": b})
    assert out == {"type": "step", "points": [[0, 6], [0.25, 4], [0.5, 5]]}


def test_mix_step_step_w_step_snaps():
    # morphing a scatti (w step) tra forme step: mondo omogeneo, esatto
    a = {"type": "step", "points": [[0, 0]]}
    b = {"type": "step", "points": [[0, 10]]}
    w = {"type": "step", "points": [[0, 0], [0.5, 1]]}
    out = eval_expr("mix(a, b, w)", {"a": a, "b": b, "w": w})
    assert out == {"type": "step", "points": [[0, 0], [0.5, 10]]}


def test_mix_w_step_scalar_forms_is_step():
    # scalari (costanti, neutri) con w step: risultato step sui tempi di w
    w = {"type": "step", "points": [[0, 0], [0.5, 1]]}
    out = eval_expr("mix(3, 8, w)", {"w": w})
    assert out == {"type": "step", "points": [[0, 3], [0.5, 8]]}


def test_mix_adaptive_curve_bound():
    # curve != 1: campionamento adattivo — il test verifica il bound, non i
    # punti esatti (scarto sotto l'1% dell'escursione)
    a = {"type": "linear", "points": [[0, 0], [1, 10]], "curve": 2}
    b = [[0, 10], [1, 0]]
    out = eval_expr("mix(a, b, 0.5)", {"a": a, "b": b})
    assert isinstance(out, list)
    for i in range(101):
        t = i / 100
        expected = 0.5 * (10 * t ** 2) + 0.5 * (10 - 10 * t)
        assert abs(_at(out, t) - expected) <= 0.1


def test_mix_adaptive_w_env_moving_forms_bound():
    # w-Env con forme mobili: il prodotto e' quadratico, serve l'adattivo
    a = [[0, 0], [1, 10]]
    b = [[0, 10], [1, 0]]
    w = [[0, 0], [1, 1]]
    out = eval_expr("mix(a, b, w)", {"a": a, "b": b, "w": w})
    for i in range(101):
        t = i / 100
        expected = (1 - t) * (10 * t) + t * (10 - 10 * t)
        assert abs(_at(out, t) - expected) <= 0.1


def test_mix_nested():
    a = [[0, 0], [1, 10]]
    b = [[0, 10], [1, 0]]
    out = eval_expr("mix(mix(a, b, 0.5), c, 0.5)", {"a": a, "b": b, "c": 0})
    assert out == [[0, 2.5], [1, 2.5]]


def test_mix_result_enters_arithmetic():
    a = [[0, 0], [1, 10]]
    assert eval_expr("mix(a, 0, 0.5) * 2", {"a": a}) == [[0, 0], [1, 10]]


def test_env_times_env_still_rejected_outside_mix():
    envs = {"e1": [[0, 1], [1, 2]], "e2": [[0, 3], [1, 4]]}
    with pytest.raises(ValueError, match="Env"):
        eval_expr("e1 * e2", envs)
    with pytest.raises(ValueError, match="Env"):
        eval_expr("min(e1, e2)", envs)


def test_mix_rigid_signature():
    with pytest.raises(ValueError, match="argoment"):
        eval_expr("mix(1, 2)", {})
    with pytest.raises(ValueError, match="argoment"):
        eval_expr("mix(1, 2, 3, 4)", {})
    with pytest.raises(ValueError, match="keyword"):
        eval_expr("mix(1, 2, w=0.5)", {})


def test_mix_step_with_continuous_rejected():
    # discontinuita' pesata (step dentro morphing continuo): fuori dal v1,
    # errore esplicito — nessuna semantica inventata
    a = {"type": "step", "points": [[0, 1], [0.5, 3]]}
    b = [[0, 0], [1, 10]]
    with pytest.raises(ValueError, match="step"):
        eval_expr("mix(a, b, 0.5)", {"a": a, "b": b})


def test_mix_w_step_with_continuous_forms_rejected():
    a = [[0, 0], [1, 10]]
    w = {"type": "step", "points": [[0, 0], [0.5, 1]]}
    with pytest.raises(ValueError, match="step"):
        eval_expr("mix(a, 5, w)", {"a": a, "w": w})


def test_mix_unknown_type_rejected():
    a = {"type": "cubic", "points": [[0, 1], [1, 3]]}
    with pytest.raises(ValueError, match="cubic"):
        eval_expr("mix(a, 0, 0.5)", {"a": a})


def test_mix_step_with_curve_rejected():
    a = {"type": "step", "points": [[0, 1], [0.5, 3]], "curve": 2}
    b = {"type": "step", "points": [[0, 0]]}
    with pytest.raises(ValueError, match="curve"):
        eval_expr("mix(a, b, 0.5)", {"a": a, "b": b})
