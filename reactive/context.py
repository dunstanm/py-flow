import contextvars
from typing import Optional, Dict, Any

# A ContextVar that holds the current active market snapshot (dictionary of quotes)
_market_context_var: contextvars.ContextVar[Optional[Dict[str, Any]]] = contextvars.ContextVar(
    'market_context', default=None
)


class MarketContext:
    """
    A context manager that cleanly isolates domain evaluation from the live ticking engine.

    By wrapping execution in a MarketContext, all calls to `eval_cached(expr)` or 
    `property_read()` that evaluate Expr ASTs will automatically draw their variables
    from this isolated snapshot rather than triggering live ticks.

    Usage:
        sandbox = {"IR_USD_OIS.5Y": 0.051}
        with MarketContext(sandbox):
            # AST evaluation routes cleanly through the sandbox
            val = swap.npv_evaluated
    """
    
    def __init__(self, quotes: Dict[str, Any]):
        """
        Initialize an isolated evaluation context.
        :param quotes: A dictionary mapping Variable names (e.g., 'IR_USD_DISC.5Y') to their float values.
        """
        self.quotes = quotes
        self.token: Optional[contextvars.Token] = None

    def __enter__(self):
        """Bind this context dictionary to the thread-safe async-safe ContextVar."""
        self.token = _market_context_var.set(self.quotes)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Restore the previous snapshot (or None)."""
        if self.token is not None:
            _market_context_var.reset(self.token)

    @staticmethod
    def current() -> Optional[Dict[str, Any]]:
        """
        Retrieve the currently bound snapshot, or None if executing outside of a sandbox.
        """
        return _market_context_var.get()
