"""
integrated_rate_curve — Integrated short rate interpolation curve.

Supports both Quadratic (C0 short rate) and Cubic (C0 or C1 short rate) 
formulations for the integral I(t).

Parameterizes the curve by R_i = (1/t_i) ∫₀ᵗⁱ r(s) ds  (average short rate)
so R_i has rate-like units.  Discount factors use  DF(T) = exp(-R(T) × T).

Interpolation modes:
  - Quadratic (degree=2): piecewise-linear short rate.
  - Cubic (degree=3): piecewise-quadratic short rate.
  
Locality modes:
  - Local (is_local=True): constraints use average slopes of intervals. 
    Produces tridiagonal Jacobians (bandwidth <= 3).
  - Global/Smooth (is_local=False): constraints match actual derivatives 
    from previous intervals. Causes "backward influence" where changing 
    a short-dated pillar ripples through later curve segments.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from store import Storable
from reactive.traceable import traceable
from reactive.computed import effect
from reactive.expr import VariableMixin
from streaming import ticking
from pricing.marketmodels.curve_base import CurveBase, _point_tenor_key


# ── Domain model for the integrated rate point ───────────────────────────

@ticking(exclude={"quote_ref", "fitted_rate"})
@dataclass
class IntegratedRatePoint(Storable, VariableMixin):
    """Single curve knot storing the average short rate R_i = (1/t_i) ∫₀ᵗⁱ r(s)ds.

    R_i has rate-like units (e.g. ~5% for 5Y), making pillar_rates directly
    comparable to zero rates.  The cumulative integral is I_i = R_i × t_i.

    Discount factor: DF(t_i) = exp(-R_i × t_i)

    This is the Expr leaf node — diff(expr, point.name) differentiates
    with respect to R_i.
    """
    __key__ = "name"

    name: str = ""
    symbol: str = ""           # e.g. IR_USD_OIS_FIT.R.5Y
    tenor_years: float = 0.0
    fitted_rate: float = 0.0   # R_i — set by CurveFitter
    currency: str = "USD"
    quote_ref: object = None
    is_fitted: bool = False

    @traceable
    def rate(self):
        """The average short rate R_i = (1/t_i) ∫₀ᵗⁱ r(s) ds.

        Has the same units as a zero rate, making it easy to reason about.
        The cumulative integral is R_i × t_i.
        """
        if self.is_fitted:
            return self.fitted_rate

        if self.quote_ref is None:
            return 0.0
        # Default: use quoted rate directly (it's already in rate units)
        r = getattr(self.quote_ref, 'rate', 0.0)
        if r is None:
            return 0.0
        return float(r)

    def set_fitted_rate(self, value: float):
        """Update R_i from a solver."""
        self.fitted_rate = value
        import pricing.marketmodels.ir_curve_fitter
        if not pricing.marketmodels.ir_curve_fitter.IS_SOLVING:
            self.tick()

    def initial_guess(self) -> float:
        """Initial guess for the fitter: R_i ≈ quote_rate.

        Since R_i is now in rate units (average short rate), the par swap
        rate is a natural starting point without any scaling.
        """
        if self.quote_ref is None:
            return self.fitted_rate
        r = getattr(self.quote_ref, 'rate', 0.0)
        if r is None:
            return 0.0
        return float(r)

    @traceable
    def zero_rate(self):
        """Equivalent zero rate — for continuous compounding, R_i IS the zero rate."""
        return self.rate

    @traceable
    def discount_factor(self):
        """DF(t_i) = exp(-R_i × t_i)."""
        arg = -self.rate * self.tenor_years
        if arg > 700: return 1e100
        if arg < -700: return 0.0
        return math.exp(arg)

    @effect("rate")
    def on_rate(self, value):
        import pricing.marketmodels.ir_curve_fitter
        if pricing.marketmodels.ir_curve_fitter.IS_SOLVING:
            return
        self.tick()


# ── Integrated short rate curve ──────────────────────────────────────────

@ticking(exclude={"points", "jacobian"})
@dataclass
class IntegratedShortRateCurve(Storable, CurveBase):
    """
    Unified formulation for Quadratic and Cubic integrated curves.
    
    Constraints:
      - I(T_i) = R_i * T_i  (level matching at knots)
      - Continuity depends on degree and is_local.
    """
    __key__ = "name"

    name: str = ""
    currency: str = "USD"
    points: list = field(default_factory=list)
    jacobian: list = field(default_factory=list)

    # Configuration parameters
    degree: int = 2          # 2 (Quadratic) or 3 (Cubic)
    is_local: bool = False    # True (Average Slopes) or False (Match Slope/Hessian)

    def _sorted_points(self):
        """Sort points by tenor — helper to avoid lambda in @computed."""
        from pricing.marketmodels.curve_base import _point_tenor_key
        return sorted(self.points, key=_point_tenor_key)

    def set_rates_numerical(self, rates: np.ndarray):
        """Bypass the reactive system: update internal rates and clear cache.
        Used by the CurveFitter to avoid 1000s of redundant reactive ticks.
        """
        # We manually update the pillar_rates cache if it exists,
        # and clear the numerical coefficients.
        pts = self._sorted_points()
        for i, r in enumerate(rates):
            # Update the underlying fitted_rate without triggering effects
            pts[i].fitted_rate = float(r)
        
        # Reset numerical polynomial cache
        object.__setattr__(self, '_coef_cache', None)
        # Clear reactive cache for pillar_rates so the next swap.npv read sees it
        if hasattr(self, '_pillar_rates_cache'):
            object.__setattr__(self, '_pillar_rates_cache', None)

    @traceable
    def pillar_tenors(self) -> list[float]:
        """Sorted pillar tenors."""
        pts = self._sorted_points()
        return [p.tenor_years for p in pts]

    @traceable
    def pillar_rates(self) -> list[float]:
        """Sorted pillar rates (Integrated Average Rates R_i)."""
        pts = self._sorted_points()
        return [p.rate for p in pts]

    @traceable
    def pillar_names(self) -> list[str]:
        """Sorted pillar variable names."""
        pts = self._sorted_points()
        return [p.name for p in pts]

    @traceable
    def point_count(self) -> int:
        return len(self.points)

    def _reset_numerical_cache(self):
        """Reset the internal numerical coefficient cache."""
        object.__setattr__(self, '_coef_cache', None)

    def _compute_coefs(self) -> list[tuple[float, float, float, float]]:
        """Compute the polynomial coefficients for each interval.
        Returns for each interval i: (c0, c1, c2, c3) where 
        I(tau) = c0 + c1*tau + c2*tau^2 + c3*tau^3 and tau = t - T[i]
        """
        # Return cached if available
        cache = getattr(self, '_coef_cache', None)
        if cache is not None:
            return cache

        pts = self._sorted_points()
        n = len(pts)
        if n <= 1:
            return []

        R = [p.rate for p in pts]
        T = [p.tenor_years for p in pts]
        I_vals = [R[i] * T[i] for i in range(n)]

        coefs = []
        
        # State trackers for non-local (smooth) propagation
        curr_r = R[0]
        curr_r_prime = 0.0
        
        for i in range(n - 1):
            h = T[i+1] - T[i]
            if h <= 0: h = 1e-10
            dI = I_vals[i+1] - I_vals[i]
            
            c0 = I_vals[i]
            c1, c2, c3 = 0.0, 0.0, 0.0
            
            if self.degree == 2:
                # Quadratic I(t) -> Linear r(t)
                if self.is_local:
                    # Match average slope of prev (chord) at start of current
                    if i == 0:
                        c1 = R[0]
                    else:
                        h_prev = T[i] - T[i-1]
                        c1 = (I_vals[i] - I_vals[i-1]) / h_prev if h_prev > 0 else R[i]
                else:
                    # Match actual slope from prev (Smooth C0 short rate)
                    c1 = curr_r
                
                # I_i + c1*h + c2*h^2 = I_{i+1}
                c2 = (dI - c1 * h) / (h * h)
                c3 = 0.0
                
                # Update state for next interval
                curr_r = c1 + 2.0 * c2 * h
                
            else:
                # Cubic I(t) -> Quadratic r(t)
                if self.is_local:
                    # LOCAL CUBIC (Bessel/Hermite style): Stable and Local.
                    # Estimate knot short rates r_i by averaging adjacent forward rates.
                    def get_knot_r(idx):
                        if idx <= 0: return R[0]
                        if idx >= n - 1: return (I_vals[n-1] - I_vals[n-2]) / (T[n-1] - T[n-2])
                        h_p, h_n = T[idx] - T[idx-1], T[idx+1] - T[idx]
                        fwd_p, fwd_n = (I_vals[idx] - I_vals[idx-1]) / h_p, (I_vals[idx+1] - I_vals[idx]) / h_n
                        return (fwd_p * h_n + fwd_n * h_p) / (h_p + h_n)

                    r_s, r_e = get_knot_r(i), get_knot_r(i+1)
                    c1 = r_s
                    c2 = (3.0 * dI - h * (2.0 * r_s + r_e)) / (h * h)
                    c3 = (r_e + r_s - 2.0 * dI / h) / (h * h * h)
                else:
                    # SMOOTH CUBIC (Forward Sequential): Unstable.
                    # Errors in early pillars amplify exponentially down the curve.
                    c1 = curr_r
                    c2 = 0.5 * curr_r_prime
                    c3 = (dI - c1*h - c2*h*h) / (h*h*h)
                    curr_r = c1 + 2.0 * c2 * h + 3.0 * c3 * h * h
                    curr_r_prime = 2.0 * c2 + 6.0 * c3 * h
            
            # Numerical Guard: prevent explosion in unstable smooth modes or bad solver steps
            if not all(math.isfinite(c) for c in [c0, c1, c2, c3]) or abs(c3) > 1e10:
                if i < 3 or i > n - 5: # Log only edges to avoid spam
                    logger.debug(f"[{self.name}] Extreme coeff in interval {i} ({T[i]}Y): c3={c3:.2e}. Stability guard active.")
                
                # Fallback to local flat rate if c3 explodes
                c1 = (I_vals[i+1] - I_vals[i]) / h
                c2 = 0.0
                c3 = 0.0
                # reset propagation state for smooth modes
                curr_r = c1
                curr_r_prime = 0.0

            coef_tuple = (float(c0), float(c1), float(c2), float(c3))
            coefs.append(coef_tuple)
            
        object.__setattr__(self, '_coef_cache', coefs)
        return coefs

    def df_array(self, tenors: list[float]) -> list[float]:
        """Batch numerical discount factors — O(N + M) implementation."""
        if not tenors:
            return []
        
        pts = self._sorted_points()
        n = len(pts)
        if n == 0:
            return [1.0] * len(tenors)
        
        T = [p.tenor_years for p in pts]
        R = [p.rate for p in pts]
        I_vals = [R[i] * T[i] for i in range(n)]
        
        # Hoist coefficient resolution out of the loop
        coefs = self._compute_coefs()
        if not coefs:
            return [1.0] * len(tenors)

        # Sort query tenors but remember original order
        indexed = sorted(enumerate(tenors), key=lambda x: x[1])
        result = [0.0] * len(tenors)
        j = 0  # pillar index
        
        # Extrapolation info
        last_c0, last_c1, last_c2, last_c3 = coefs[-1]
        h_last = T[-1] - T[-2] if n > 1 else 0.0
        r_end = last_c1 + (2.0 * last_c2 + 3.0 * last_c3 * h_last) * h_last
        
        for orig_idx, t in indexed:
            if t <= 0:
                i_val = 0.0
            elif t <= T[0]:
                i_val = R[0] * t
            elif t >= T[-1]:
                i_val = I_vals[-1] + r_end * (t - T[-1])
            else:
                # Advance pillar pointer
                while j < n - 2 and T[j + 1] < t:
                    j += 1
                
                c0, c1, c2, c3 = coefs[j]
                tau = t - T[j]
                i_val = c0 + tau * (c1 + tau * (c2 + tau * c3))
            
            # DF(t) = exp(-I(t)) with safety clamping
            if i_val < -700: result[orig_idx] = 1e100
            elif i_val > 700: result[orig_idx] = 0.0
            else: result[orig_idx] = math.exp(-i_val)
            
        return result

    def fwd_array(self, tenors: list[float], period: float = 1.0) -> list[float]:
        """Batch numerical forward rates: (I(t+p) - I(t)) / p."""
        if not tenors:
            return []
        if period <= 0:
            return [0.0] * len(tenors)
            
        # We need I(t) and I(t+p) for all t.
        # This is 2x more efficient than calling fwd_at in a loop.
        all_tenors = []
        for t in tenors:
            all_tenors.append(t)
            all_tenors.append(t + period)
            
        # Instead of calling df_array (which does exp), we work with I(t) directly
        pts = self._sorted_points()
        n = len(pts)
        R = [p.rate for p in pts]
        T = [p.tenor_years for p in pts]
        I_vals = [R[k] * T[k] for k in range(n)]
        coefs = self._compute_coefs()
        
        # Last interval extrapolation info
        last_c0, last_c1, last_c2, last_c3 = coefs[-1] if coefs else (0,0,0,0)
        h_last = T[-1] - T[-2] if n > 1 else 0.0
        if self.degree == 2:
            r_end = last_c1 + 2.0 * last_c2 * h_last
        else:
            r_end = last_c1 + 2.0 * last_c2 * h_last + 3.0 * last_c3 * h_last * h_last

        def _get_I(t_val, curr_idx_hint):
            if t_val <= 0: return 0.0, curr_idx_hint
            if t_val <= T[0]: return R[0] * t_val, curr_idx_hint
            if t_val >= T[-1]: return I_vals[-1] + r_end * (t_val - T[-1]), curr_idx_hint
            
            # Simple linear search forward from hint (tenors is sorted)
            idx = curr_idx_hint
            while idx < n - 2 and T[idx + 1] < t_val:
                idx += 1
            while idx > 0 and T[idx] > t_val:
                idx -= 1
                
            tau = t_val - T[idx]
            c0, c1, c2, c3 = coefs[idx]
            # Use Horner's method for stability
            val = c0 + tau * (c1 + tau * (c2 + tau * c3))
            return val, idx

        results = []
        curr_idx = 0
        for t in tenors:
            i_start, curr_idx = _get_I(t, curr_idx)
            i_end, curr_idx = _get_I(t + period, curr_idx)
            results.append((i_end - i_start) / period)
            
        return results

    def _I_at(self, t: float) -> float:
        """Numerical cumulative integral I(t) = ∫₀ᵗ r(s) ds at any tenor."""
        pts = self._sorted_points()
        n = len(pts)
        if n == 0:
            return 0.0

        R = [p.rate for p in pts]
        T = [p.tenor_years for p in pts]
        I_vals = [R[i] * T[i] for i in range(n)]

        if t <= 0:
            return 0.0
        if n == 1:
            return R[0] * t

        if t <= T[0]:
            return R[0] * t

        coefs = self._compute_coefs()

        if t >= T[-1]:
            # Extrapolate using the last state
            tau = t - T[-1]
            last_c0, last_c1, last_c2, last_c3 = coefs[-1]
            h_last = T[-1] - T[-2]
            # Slope at end of last interval
            if self.degree == 2:
                r_end = last_c1 + 2.0 * last_c2 * h_last
            else:
                r_end = last_c1 + 2.0 * last_c2 * h_last + 3.0 * last_c3 * h_last * h_last
            return I_vals[-1] + r_end * tau

        for i in range(n - 1):
            if T[i] <= t <= T[i + 1]:
                tau = t - T[i]
                c0, c1, c2, c3 = coefs[i]
                return c0 + c1*tau + c2*tau*tau + c3*tau*tau*tau

        return I_vals[-1]

    def _R_at(self, t: float) -> float:
        """Backward-compat alias for _I_at (cumulative integral)."""
        return self._I_at(t)

    def df_at(self, tenor: float) -> float:
        """DF(t) = exp(-I(t)) = exp(-R(t) × t)."""
        I_val = self._I_at(tenor)
        if I_val < -700: return 1e100
        if I_val > 700: return 0.0
        return math.exp(-I_val)


    def fwd_at(self, tenor: float, period: float = 1.0) -> float:
        """Forward rate: (I(t+p) - I(t)) / p."""
        I_start = self._I_at(tenor)
        I_end = self._I_at(tenor + period)
        if period <= 0:
            return 0.0
        return (I_end - I_start) / period

    # ── Symbolic Expr builders ────────────────────────────────────────────

    def _reset_v_cache(self):
        """Reset the internal symbolic coefficient cache."""
        object.__setattr__(self, '_v_coef_cache', None)

    def _v_compute_coefs(self) -> tuple[list, list, list, list]:
        """Build symbolic Expr trees for each interval's coefficients.
        Returns (V_c0, V_c1, V_c2, V_c3) where each is a list of Expr for intervals.
        """
        # Return cached if available
        cache = getattr(self, '_v_coef_cache', None)
        if cache is not None:
            return cache

        from reactive.expr import Const, Variable
        pts = self._sorted_points()
        n = len(pts)
        if n <= 1:
            return [], [], [], []

        T = [p.tenor_years for p in pts]
        def _leaf(point):
            return Variable(point.name)
            
        V_R = [_leaf(pts[i]) for i in range(n)]
        V_I = [V_R[i] * Const(T[i]) for i in range(n)]

        # Build symbolic coefficients similarly to numerical coeffs
        V_c0 = [Const(0.0)] * (n - 1)
        V_c1 = [Const(0.0)] * (n - 1)
        V_c2 = [Const(0.0)] * (n - 1)
        V_c3 = [Const(0.0)] * (n - 1)

        V_curr_r = V_R[0]
        V_curr_r_prime = Const(0.0)

        for i in range(n - 1):
            h_val = T[i+1] - T[i] if T[i+1] > T[i] else 1e-10
            h = Const(h_val)
            dI = V_I[i+1] - V_I[i]
            
            V_c0[i] = V_I[i]
            
            if self.degree == 2:
                if self.is_local:
                    if i == 0:
                        V_c1[i] = V_R[0]
                    else:
                        h_prev = Const(T[i] - T[i-1] if T[i] > T[i-1] else 1e-10)
                        V_c1[i] = (V_I[i] - V_I[i-1]) / h_prev
                else:
                    V_c1[i] = V_curr_r
                
                V_c2[i] = (dI - V_c1[i] * h) / (h * h)
                V_c3[i] = Const(0.0)
                
                V_curr_r = V_c1[i] + Const(2.0) * V_c2[i] * h
            else:
                if self.is_local:
                    # Symbolic Local Cubic
                    def V_get_knot_r(idx):
                        if idx <= 0: return V_R[0]
                        if idx >= n - 1: return (V_I[n-1] - V_I[n-2]) / Const(T[n-1] - T[n-2])
                        h_p, h_n = Const(T[idx] - T[idx-1]), Const(T[idx+1] - T[idx])
                        V_fwd_p = (V_I[idx] - V_I[idx-1]) / h_p
                        V_fwd_n = (V_I[idx+1] - V_I[idx]) / h_n
                        return (V_fwd_p * h_n + V_fwd_n * h_p) / (h_p + h_n)

                    V_r_s, V_r_e = V_get_knot_r(i), V_get_knot_r(i+1)
                    V_c1[i] = V_r_s
                    V_c2[i] = (Const(3.0) * dI - h * (Const(2.0) * V_r_s + V_r_e)) / (h * h)
                    V_c3[i] = (V_r_e + V_r_s - Const(2.0) * dI / h) / (h * h * h)
                else:
                    # Symbolic Smooth Cubic (Warning: Unstable)
                    V_c1[i] = V_curr_r
                    V_c2[i] = Const(0.5) * V_curr_r_prime
                    V_c3[i] = (dI - V_c1[i]*h - V_c2[i]*h*h) / (h*h*h)
                    
                    V_curr_r = V_c1[i] + Const(2.0) * V_c2[i] * h + Const(3.0) * V_c3[i] * h * h
                    V_curr_r_prime = Const(2.0) * V_c2[i] + Const(6.0) * V_c3[i] * h
        
        result = (V_c0, V_c1, V_c2, V_c3)
        object.__setattr__(self, '_v_coef_cache', result)
        return result

    def interp(self, t: float) -> "Expr":
        """Build an Expr tree mapping curve variables to the Integral evaluation."""
        cache = getattr(self, '_interp_cache', None)
        if cache is None:
            cache = {}
            object.__setattr__(self, '_interp_cache', cache)
        if t in cache:
            return cache[t]

        from reactive.expr import Const

        pts = self._sorted_points()
        n = len(pts)

        if n == 0:
            expr = Const(0.0)
            cache[t] = expr
            return expr

        T = [p.tenor_years for p in pts]
        
        if t <= 0:
            return Const(0.0)
        if n == 1:
            from reactive.expr import Variable
            return Variable(pts[0].name) * Const(t)

        V_c0, V_c1, V_c2, V_c3 = self._v_compute_coefs()
        V_I = [V_c0[i] if i < (n-1) else V_c0[-1] for i in range(n)] # Simplified approximation for end-points
        # Correction: V_I actually needs level matching at knots
        from reactive.expr import Variable
        V_R = [Variable(pts[i].name) for i in range(n)]
        V_I_actual = [V_R[i] * Const(T[i]) for i in range(n)]

        if t <= T[0]:
            expr = V_R[0] * Const(t)
            cache[t] = expr
            return expr

        if t >= T[-1]:
            tau = Const(t - T[-1])
            h_last = Const(T[-1] - T[-2] if n > 1 else 1.0)
            if self.degree == 2:
                V_r_end = V_c1[-1] + Const(2.0) * V_c2[-1] * h_last
            else:
                V_r_end = V_c1[-1] + Const(2.0) * V_c2[-1] * h_last + Const(3.0) * V_c3[-1] * h_last * h_last
            expr = V_I_actual[-1] + V_r_end * tau
            cache[t] = expr
            return expr

        for i in range(n - 1):
            if T[i] <= t <= T[i + 1]:
                tau = Const(t - T[i])
                expr = V_c0[i] + V_c1[i]*tau + V_c2[i]*tau*tau + V_c3[i]*tau*tau*tau
                cache[t] = expr
                return expr

        expr = V_I_actual[-1]
        cache[t] = expr
        return expr

    def _df_expr(self, t: float) -> "Expr":
        """Build a cached Expr tree for DF(t) = exp(-I(t))."""
        cache = getattr(self, '_df_cache', None)
        if cache is None:
            cache = {}
            object.__setattr__(self, '_df_cache', cache)
        if t in cache:
            return cache[t]

        from reactive.expr import Exp
        I_expr = self.interp(t)
        expr = Exp(-I_expr)
        cache[t] = expr
        return expr

    def df(self, t: float):
        """DF(t) = exp(-I(t)) = exp(-R(t) × t).

        Returns:
            TracedFloat — when tracing is active (@traceable trace mode)
            Expr        — when building is active (@traceable)
            float       — otherwise (default debug mode)
        """
        from reactive.traced import _is_tracing, _is_building
        if _is_tracing():
            from reactive.traced import TracedFloat
            return TracedFloat(self.df_at(t), self._df_expr(t))
        if _is_building():
            return self._df_expr(t)
        return self.df_at(t)

    def fwd(self, start: float, end: float) -> "Expr":
        """Build an Expr tree for the forward rate."""
        from reactive.expr import Const
        dt = end - start
        if dt <= 0:
            return Const(0.0)

        I_start = self.interp(start)
        I_end = self.interp(end)
        return (I_end - I_start) / Const(dt)

    # ── Cache invalidation ────────────────────────────────────────────────

    def invalidate_symbolic_caches(self):
        """Clear Expr trees when curve structure (tenors, degree) changes."""
        if hasattr(self, '_interp_cache'):
            object.__setattr__(self, '_interp_cache', {})
        if hasattr(self, '_df_cache'):
            object.__setattr__(self, '_df_cache', {})
        if hasattr(self, '_v_coef_cache'):
            object.__setattr__(self, '_v_coef_cache', None)

    def invalidate_caches(self):
        """Clear Numerical coefficient cache when rates change."""
        self._reset_numerical_cache()

    @effect("pillar_rates")
    def on_rates_change(self, value):
        # Numerical coefficients depend on rates; Symbolic Expr trees do NOT.
        # Clearing only the numerical cache speeds up the solver by 100x.
        self._reset_numerical_cache()
        import pricing.marketmodels.ir_curve_fitter
        if pricing.marketmodels.ir_curve_fitter.IS_SOLVING:
            return
        self.tick()
