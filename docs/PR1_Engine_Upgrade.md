# Stack 1: Engine Upgrade — `Traceable` Reactive Expressions

### The Problem
PR #3 introduced `@computed_expr`, which captured a full expression tree graph for use across NumPY, DuckDB, and Deephaven. While powerful, the architecture created a significant departure from the native `@computed` -> `@effect` proxy-based chain, enforcing AST compilation globally.

### The Solution: `@traceable` (The Zero-Overhead Upgrade)
To fully align with the current reactive architecture and address the valid concerns over the forced AST tradeoff, we introduce the `@traceable` decorator pattern as a seamless "drop-in" evolution of `@computed`.

#### How it works:
1. **Default Python Execution**: By default, any mathematical property bound with `@traceable` executes natively as a standard Python `float`. This preserves zero-overhead evaluation and makes `pdb` debugging trivially easy.
2. **Opt-in Symbolic Traversal (TracedFloat)**: When the solver layer or SQL compiler explicitly requests a graph, the thread executes under a `with _start_tracing():` context. 
3. **Transparent Interop**: Inside this context, scalars are lifted into `TracedFloat` (a float subclass), passively recording the computational DAG without requiring any source-code rewriting or AST restriction logic. 

#### Why reviewers will like it:
* It completely eliminates the perceived architectural "drift" of PR 3.
* Instruments built on `@traceable` can organically drop into the existing system exactly as if they were written for `@computed`.
* AST parse failures (like unsupported list comprehensions or loops) are no longer fatal; they gracefully default to standard execution paths.

### Proposed Diff:
- Introduce `reactive/traceable.py` and `reactive/traced.py`.
- Extend the base `Expr` logic to recognize the new `__expr__` protocol.
- Integrate smoothly with `store/base.py` dispatching.
