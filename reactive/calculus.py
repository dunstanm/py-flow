from typing import Any
from .expr import Expr, Const, BinOp, UnaryOp, Func, If, Field, Variable, VariableMixin
from .sum_expr import Sum

# ---------------------------------------------------------------------------
# Symbolic Differentiation (iterative — no recursion depth limit)
# ---------------------------------------------------------------------------

def diff(expr: Expr, wrt: str, _memo: dict | None = None) -> Expr:
    """Symbolic differentiation: ∂expr/∂Variable(wrt).

    Returns a new Expr tree representing the derivative.
    This enables risk calculations that compile to any target:
        risk = diff(npv_expr, "USD_OIS_5Y")
        risk.eval(ctx)   → Python float
        risk.to_sql()    → SQL expression

    Memoized: the same sub-expression differentiated w.r.t. the same
    variable returns the same Expr object.  This is critical because
    Uses an iterative post-order traversal via an explicit stack.
    Memoization is handled entirely through _memo (keyed by (id(node), wrt)),
    ensuring correct DAG sharing and operand order for non-commutative operations.
    """
    if _memo is None:
        _memo = {}

    root_key = (id(expr), wrt)
    if root_key in _memo:
        return _memo[root_key]

    _ZERO = Const(0.0)
    _ONE = Const(1.0)

    # stack: list of (node, phase)
    stack: list[tuple[Expr, int]] = [(expr, 0)]

    while stack:
        node, phase = stack.pop()
        nkey = (id(node), wrt)

        if nkey in _memo:
            continue

        if phase == 0:
            # First visit
            if wrt not in node.variables:
                _memo[nkey] = _ZERO
                continue
            if isinstance(node, (Variable, VariableMixin)):
                _memo[nkey] = _ONE if node.name == wrt else _ZERO
                continue
            if isinstance(node, Const) or isinstance(node, Field):
                _memo[nkey] = _ZERO
                continue

            # Composite node
            stack.append((node, 1))

            if isinstance(node, Sum):
                for term in reversed(node.terms):
                    if (id(term), wrt) not in _memo:
                        stack.append((term, 0))
            elif isinstance(node, BinOp):
                if (id(node.right), wrt) not in _memo:
                    stack.append((node.right, 0))
                if (id(node.left), wrt) not in _memo:
                    stack.append((node.left, 0))
            elif isinstance(node, UnaryOp):
                if (id(node.operand), wrt) not in _memo:
                    stack.append((node.operand, 0))
            elif isinstance(node, Func):
                for a in reversed(node.args):
                    if (id(a), wrt) not in _memo:
                        stack.append((a, 0))
            elif isinstance(node, If):
                # Always differentiate condition, then, else
                if (id(node.else_), wrt) not in _memo:
                    stack.append((node.else_, 0))
                if (id(node.then_), wrt) not in _memo:
                    stack.append((node.then_, 0))
                # Note: condition is NOT differentiated (treated as constant bridge)
            else:
                raise ValueError(f"diff: unsupported Expr type '{type(node).__name__}'")

        elif phase == 1:
            # Phase 1: All child derivatives GUARANTEED to be in _memo
            if isinstance(node, Sum):
                dterms = [_memo[(id(t), wrt)] for t in node.terms]
                nonzero = [dt for dt in dterms if not (isinstance(dt, Const) and dt.value == 0.0)]
                if not nonzero: r = _ZERO
                elif len(nonzero) == 1: r = nonzero[0]
                else: r = Sum(nonzero)
                _memo[nkey] = r
            
            elif isinstance(node, BinOp):
                dl = _memo[(id(node.left), wrt)]
                dr = _memo[(id(node.right), wrt)]
                
                if node.op == "+":
                    r = dl + dr
                elif node.op == "-":
                    r = dl - dr
                elif node.op == "*":
                    r = dl * node.right + node.left * dr
                elif node.op == "/":
                    # Quotient rule: (f'g - fg') / g^2
                    r = (dl * node.right - node.left * dr) / (node.right ** Const(2.0))
                elif node.op == "**":
                    n = node.right
                    f = node.left
                    r = n * (f ** (n - Const(1.0))) * dl
                else:
                    raise ValueError(f"diff: unsupported BinOp '{node.op}'")
                _memo[nkey] = r

            elif isinstance(node, Func):
                f = node.args[0]
                df = _memo[(id(f), wrt)]
                if node.name == "exp":
                    r = node * df
                elif node.name == "log":
                    r = df / f
                elif node.name == "sqrt":
                    r = df / (Const(2.0) * node)
                else:
                    raise ValueError(f"diff: unknown Func '{node.name}'")
                _memo[nkey] = r

            elif isinstance(node, UnaryOp):
                df = _memo[(id(node.operand), wrt)]
                if node.op == "neg": r = -df
                elif node.op == "abs":
                    f = node.operand
                    r = If(f > Const(0.0), df, If(f < Const(0.0), -df, _ZERO))
                else:
                    raise ValueError(f"diff: unsupported UnaryOp '{node.op}'")
                _memo[nkey] = r

            elif isinstance(node, If):
                dt = _memo[(id(node.then_), wrt)]
                de = _memo[(id(node.else_), wrt)]
                r = If(node.condition, dt, de)
                _memo[nkey] = r

    return _memo[root_key]
