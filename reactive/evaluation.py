from typing import Any
from .expr import Expr, Const, BinOp, UnaryOp, Func, If, Field, Variable, VariableMixin
from .sum_expr import Sum

# ---------------------------------------------------------------------------
# Cached evaluation (for DAGs produced by memoized diff)
# ---------------------------------------------------------------------------

def eval_cached(expr: Expr, ctx: dict, _cache: dict | None = None) -> Any:
    """Evaluate an Expr DAG with sub-expression caching.

    After memoized diff(), the derivative is a DAG (not a tree).
    Naive expr.eval(ctx) would re-evaluate shared sub-nodes exponentially.
    This function caches by node id(), evaluating each unique node once.

    ITERATIVE implementation — uses an explicit stack to avoid
    hitting Python's recursion limit on deep expression trees.

    Usage:
        deriv = diff(npv_expr, "USD_OIS_5Y")
        val = eval_cached(deriv, ctx)  # fast
    """
    if _cache is None:
        _cache = {}

    key = id(expr)
    if key in _cache:
        return _cache[key]

    # ── Iterative post-order evaluation ──
    stack: list = [(expr, 0)]
    result_stack: list = []

    while stack:
        node, phase, *_ = stack.pop()

        nkey = id(node)
        if nkey in _cache:
            result_stack.append(_cache[nkey])
            continue

        # ── Leaf nodes ──
        if isinstance(node, Const):
            r = node.eval(ctx)
            _cache[nkey] = r
            result_stack.append(r)
            continue

        if isinstance(node, (Variable, VariableMixin)):
            r = node.expr_eval(ctx)
            _cache[nkey] = r
            result_stack.append(r)
            continue

        if isinstance(node, Field):
            r = node.eval(ctx)
            _cache[nkey] = r
            result_stack.append(r)
            continue

        # ── Sum ──
        if isinstance(node, Sum):
            if phase == 0:
                stack.append((node, 1))
                for term in reversed(node.terms):
                    if id(term) not in _cache:
                        stack.append((term, 0))
            else:
                total = 0.0
                for term in node.terms:
                    tk = id(term)
                    if tk in _cache:
                        total += _cache[tk]
                    else:
                        total += result_stack.pop()
                _cache[nkey] = total
                result_stack.append(total)
            continue

        # ── BinOp ──
        if isinstance(node, BinOp):
            if phase == 0:
                stack.append((node, 1))
                if id(node.right) not in _cache:
                    stack.append((node.right, 0))
                if id(node.left) not in _cache:
                    stack.append((node.left, 0))
            else:
                lk, rk = id(node.left), id(node.right)
                lv = _cache[lk] if lk in _cache else result_stack.pop()
                rv = _cache[rk] if rk in _cache else result_stack.pop()
                if lk not in _cache:
                    _cache[lk] = lv
                if rk not in _cache:
                    _cache[rk] = rv

                op = node.op
                if op == "+":
                    r = lv + rv
                elif op == "-":
                    r = lv - rv
                elif op == "*":
                    r = lv * rv
                elif op == "/":
                    r = lv / rv if rv != 0 else 0
                elif op == "**":
                    r = lv ** rv
                elif op == ">":
                    r = lv > rv
                elif op == "<":
                    r = lv < rv
                elif op == ">=":
                    r = lv >= rv
                elif op == "<=":
                    r = lv <= rv
                elif op == "==":
                    r = lv == rv
                elif op == "!=":
                    r = lv != rv
                else:
                    raise ValueError(f"eval_cached: unsupported BinOp '{op}'")
                _cache[nkey] = r
                result_stack.append(r)
            continue

        # ── UnaryOp ──
        if isinstance(node, UnaryOp):
            if phase == 0:
                stack.append((node, 1))
                if id(node.operand) not in _cache:
                    stack.append((node.operand, 0))
            else:
                ok = id(node.operand)
                ov = _cache[ok] if ok in _cache else result_stack.pop()
                if ok not in _cache:
                    _cache[ok] = ov
                if node.op == "neg":
                    r = -ov
                elif node.op == "abs":
                    r = abs(ov)
                else:
                    raise ValueError(f"eval_cached: unsupported UnaryOp '{node.op}'")
                _cache[nkey] = r
                result_stack.append(r)
            continue

        # ── Func ──
        if isinstance(node, Func):
            if phase == 0:
                stack.append((node, 1))
                for a in reversed(node.args):
                    if id(a) not in _cache:
                        stack.append((a, 0))
            else:
                vals = []
                for a in node.args:
                    ak = id(a)
                    if ak in _cache:
                        vals.append(_cache[ak])
                    else:
                        vals.append(result_stack.pop())
                fn = Func._PYTHON_FUNCS.get(node.name)
                if fn is None:
                    raise ValueError(f"eval_cached: unknown Func '{node.name}'")
                r = fn(*vals)
                
                _cache[nkey] = r
                result_stack.append(r)
            continue

        # ── If ──
        if isinstance(node, If):
            if phase == 0:
                # Evaluate condition first
                stack.append((node, 1))
                if id(node.condition) not in _cache:
                    stack.append((node.condition, 0))
            elif phase == 1:
                # Condition evaluated, now pick the branch
                ck = id(node.condition)
                cond = _cache[ck] if ck in _cache else result_stack.pop()
                if ck not in _cache:
                    _cache[ck] = cond
                branch = node.then_ if cond else node.else_
                bk = id(branch)
                if bk in _cache:
                    _cache[nkey] = _cache[bk]
                    result_stack.append(_cache[bk])
                else:
                    stack.append((node, 2))
                    stack.append((branch, 0))
            else:
                # Phase 2: branch evaluated
                r = result_stack.pop()
                _cache[nkey] = r
                result_stack.append(r)
            continue

        # Fallback for other node types
        r = node.eval(ctx)
        _cache[nkey] = r
        result_stack.append(r)

    return result_stack[-1]

