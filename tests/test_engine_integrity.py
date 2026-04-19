
# import pytest
from reactive.expr import Variable, Const, Exp, Log, If
from reactive.evaluation import eval_cached
from reactive.calculus import diff

def test_engine_non_commutative_ops():
    """Verify that subtraction and division don't have operand-swapping bugs."""
    x = Variable("x")
    y = Variable("y")
    ctx = {"x": 10.0, "y": 2.0}

    # 1. Division
    expr_div = x / y
    assert eval_cached(expr_div, ctx) == 5.0

    # 2. Subtraction
    expr_sub = x - y
    assert eval_cached(expr_sub, ctx) == 8.0

    # 3. Power
    expr_pow = x ** y
    assert eval_cached(expr_pow, ctx) == 100.0

def test_engine_quotient_rule():
    """Verify d/dy (x / y) = -x / y^2"""
    x = Variable("x")
    y = Variable("y")
    expr = x / y
    ctx = {"x": 10.0, "y": 2.0}

    deriv_y = diff(expr, "y")
    # -10 / 4 = -2.5
    assert eval_cached(deriv_y, ctx) == -2.5

    deriv_x = diff(expr, "x")
    # 1 / 2 = 0.5
    assert eval_cached(deriv_x, ctx) == 0.5

def test_engine_dag_sharing():
    """Verify that shared nodes in a DAG are only evaluated once."""
    x = Variable("x")
    shared = x * x
    expr = shared + shared
    ctx = {"x": 3.0}
    
    _cache = {}
    val = eval_cached(expr, ctx, _cache=_cache)
    assert val == 18.0
    # The 'shared' node should appear exactly once in the cache
    assert id(shared) in _cache
    # No other redundant nodes for the same 'shared' object

def test_engine_complex_chain():
    """Verify a mix of nested functions and conditions."""
    x = Variable("x")
    y = Variable("y")
    # if x > 5 then exp(y) else log(y)
    expr = If(x > Const(5.0), Exp(y), Log(y))
    
    ctx_true = {"x": 10.0, "y": 0.0}
    assert eval_cached(expr, ctx_true) == 1.0 # exp(0)
    
    ctx_false = {"x": 0.0, "y": 1.0}
    assert eval_cached(expr, ctx_false) == 0.0 # log(1)

def test_engine_sum_flattening():
    """Verify that Sum nodes are correctly handled iterative."""
    from reactive.sum_expr import Sum
    x = Variable("x")
    terms = [x, Const(1.0), x, Const(2.0)]
    expr = Sum(terms)
    ctx = {"x": 10.0}
    # 10 + 1 + 10 + 2 = 23
    assert eval_cached(expr, ctx) == 23.0

    # Differentiation wrt x should be 1 + 0 + 1 + 0 = 2
    deriv = diff(expr, "x")
    assert eval_cached(deriv, ctx) == 2.0

if __name__ == "__main__":
    # Run tests manually if pytest is missing
    test_engine_non_commutative_ops()
    test_engine_quotient_rule()
    test_engine_dag_sharing()
    test_engine_complex_chain()
    test_engine_sum_flattening()
    print("All engine integrity tests PASSED.")
