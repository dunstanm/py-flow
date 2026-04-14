from typing import Any
from .expr import Expr, Const, BinOp, UnaryOp, Func, If, Field, Variable, VariableMixin
from .sum_expr import Sum

# ---------------------------------------------------------------------------
# Cached evaluation (for DAGs produced by memoized diff)
# ---------------------------------------------------------------------------

def eval_cached(expr: Expr, ctx: dict, _cache: dict | None = None) -> Any:
    """Evaluate an Expr DAG with sub-expression caching.

    Uses an iterative post-order traversal via an explicit stack.
    Communication between child and parent nodes is handled entirely
    through the _cache (keyed by id(node)), ensuring correctness for DAGs.
    """
    if hasattr(expr, "__expr__"):
        expr = expr.__expr__()
        
    if not isinstance(expr, Expr):
        # Already evaluated or constant
        return expr

    if _cache is None:
        _cache = {}

    root_key = id(expr)
    if root_key in _cache:
        return _cache[root_key]

    # stack: list of (node, phase)
    # phase 0: first visit, push children
    # phase 1: second visit, children are done, compute result
    stack: list[tuple[Expr, int]] = [(expr, 0)]

    while stack:
        node, phase = stack.pop()
        nkey = id(node)

        if nkey in _cache:
            continue

        if phase == 0:
            # First visit: check if it's a leaf or has children
            if isinstance(node, Const):
                _cache[nkey] = node.eval(ctx)
                continue
            if isinstance(node, (Variable, VariableMixin)):
                _cache[nkey] = node.expr_eval(ctx)
                continue
            if isinstance(node, Field):
                _cache[nkey] = node.eval(ctx)
                continue

            # Composite node: go to Phase 1 and push children
            stack.append((node, 1))
            
            if isinstance(node, Sum):
                for term in reversed(node.terms):
                    if id(term) not in _cache:
                        stack.append((term, 0))
            elif isinstance(node, BinOp):
                if id(node.right) not in _cache:
                    stack.append((node.right, 0))
                if id(node.left) not in _cache:
                    stack.append((node.left, 0))
            elif isinstance(node, UnaryOp):
                if id(node.operand) not in _cache:
                    stack.append((node.operand, 0))
            elif isinstance(node, Func):
                for a in reversed(node.args):
                    if id(a) not in _cache:
                        stack.append((a, 0))
            elif isinstance(node, If):
                # For If, we skip phase-based and just push condition first
                # Actually, to be truly iterative and dag-safe for all branches:
                stack.pop() # Remove (node, 1)
                stack.append((node, 2)) # Picking branch
                if id(node.condition) not in _cache:
                    stack.append((node.condition, 0))
            else:
                # Fallback for unknown Expr types (recursive eval)
                _cache[nkey] = node.eval(ctx)
        
        elif phase == 1:
            # Phase 1: All children are GUARANTEED to be in _cache
            if isinstance(node, Sum):
                _cache[nkey] = sum(_cache[id(t)] for t in node.terms)
            elif isinstance(node, BinOp):
                lv = _cache[id(node.left)]
                rv = _cache[id(node.right)]
                op = node.op
                if op == "+": r = lv + rv
                elif op == "-": r = lv - rv
                elif op == "*": r = lv * rv
                elif op == "/": r = lv / rv if rv != 0 else 0
                elif op == "**":
                    try:
                        # Force to float to catch overflow early
                        r = float(lv) ** float(rv)
                    except (OverflowError, FloatingPointError, ZeroDivisionError):
                        if rv < 0: r = 1e308 # Approximation for 1/0
                        else: r = 0.0
                elif op == ">": r = lv > rv
                elif op == "<": r = lv < rv
                elif op == ">=": r = lv >= rv
                elif op == "<=": r = lv <= rv
                elif op == "==": r = lv == rv
                elif op == "!=": r = lv != rv
                else: raise ValueError(f"eval_cached: unsupported BinOp '{op}'")
                _cache[nkey] = r
            elif isinstance(node, UnaryOp):
                ov = _cache[id(node.operand)]
                if node.op == "neg": r = -ov
                elif node.op == "abs": r = abs(ov)
                else: raise ValueError(f"eval_cached: unsupported UnaryOp '{node.op}'")
                _cache[nkey] = r
            elif isinstance(node, Func):
                vals = [_cache[id(a)] for a in node.args]
                fn = Func._PYTHON_FUNCS.get(node.name)
                if fn is None: raise ValueError(f"eval_cached: unknown Func '{node.name}'")
                _cache[nkey] = fn(*vals)
        
        elif phase == 2:
            # Phase 2: Specially for 'If' (condition is done)
            cond = _cache[id(node.condition)]
            branch = node.then_ if cond else node.else_
            if id(branch) in _cache:
                _cache[nkey] = _cache[id(branch)]
            else:
                # Branch not done, push it and come back for final assignment
                stack.append((node, 3))
                stack.append((branch, 0))
                
        elif phase == 3:
            # Phase 3: 'If' branch is done
            branch = node.then_ if _cache[id(node.condition)] else node.else_
            _cache[nkey] = _cache[id(branch)]

    return _cache[root_key]


