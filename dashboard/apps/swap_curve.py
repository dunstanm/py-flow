import asyncio
import logging
import threading
from datetime import datetime, timezone
import json
import time
import sys
from typing import Optional

import numpy as np
import pandas as pd
import panel as pn
import param
from bokeh.plotting import figure
from bokeh.models import ColumnDataSource, HoverTool, Legend

from dashboard.core import Dashboard
from marketdata.bus import TickBus
from marketdata.client import MarketDataClient
from pricing.marketmodels.swap_curve import SwapQuote
from pricing.marketmodels.yield_curve import YieldCurvePoint, LinearTermDiscountCurve
from pricing.marketmodels.curve_fitter import CurveFitter
from pricing.instruments.ir_swap_fixed_floatapprox import IRSwapFixedFloatApprox

logger = logging.getLogger(__name__)

# ── Market Data Consumer ───────────────────────────────────────────────────

def _start_md_consumer(state: 'SwapCurveState'):
    """Daemon thread to consume ticks from the MarketDataServer."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    async def _consume():
        import websockets
        url = "ws://localhost:8000/md/subscribe"
        logger.info(f"Connecting to Market Data at {url}...")
        async with websockets.connect(url) as ws:
            logger.info("Market Data connection established.")
            await ws.send(json.dumps({"types": ["swap", "curve", "fx"]}))
            async for message in ws:
                msg = json.loads(message)
                if msg.get("type") == "batch":
                    ticks = msg.get("ticks", [])
                else:
                    ticks = [msg]
                state.on_batch(ticks)
    
    try:
        loop.run_until_complete(_consume())
    except Exception as e:
        logger.error(f"MD Consumer error: {e}")

# ── Business State ──────────────────────────────────────────────────────────

class SwapCurveState(param.Parameterized):
    """Reactive state for the Swap Curve app. Handles solver + DF snapshots."""
    
    last_tick_time = param.Date(default=None)
    tick_count = param.Integer(default=0)
    
    # DataFrames for UI
    quote_df = param.DataFrame()
    curve_df = param.DataFrame()
    forward_df = param.DataFrame()
    
    status_message = param.String(default="⏳ Awaiting market data...")
    last_ql_solve_time = 0.0
    last_ql_curve = None
    
    def __init__(self, **params):
        super().__init__(**params)
        self._lock = threading.RLock()
        self._snapshot_lock = threading.Lock()
        self._last_snapshot_time = 0.0
        self._setup_fitter()
        
    def _setup_fitter(self):
        """Build the curve, pillars, and fitter."""
        from pricing.marketmodels.integrated_rate_curve import IntegratedShortRateCurve
        
        # 1. Curve & Points
        self.points_linear = [
            YieldCurvePoint(name=f"USD_OIS_LIN_{t}Y", tenor_years=t, is_fitted=True)
            for t in [1.0, 2.0, 3.0, 5.0, 7.0, 10.0, 12.0, 15.0, 20.0, 30.0]
        ]
        self.points_smooth = [
            YieldCurvePoint(name=f"USD_OIS_SMOOTH_{t}Y", tenor_years=t, is_fitted=True)
            for t in [1.0, 2.0, 3.0, 5.0, 7.0, 10.0, 12.0, 15.0, 20.0, 30.0]
        ]
        self.points_cubic = [
            YieldCurvePoint(name=f"USD_OIS_CUBIC_{t}Y", tenor_years=t, is_fitted=True)
            for t in [1.0, 2.0, 3.0, 5.0, 7.0, 10.0, 12.0, 15.0, 20.0, 30.0]
        ]
        self.points_cubic_smooth = [
            YieldCurvePoint(name=f"USD_OIS_CUBIC_SM_{t}Y", tenor_years=t, is_fitted=True)
            for t in [1.0, 2.0, 3.0, 5.0, 7.0, 10.0, 12.0, 15.0, 20.0, 30.0]
        ]
        self.curve_linear = LinearTermDiscountCurve(name="USD_OIS_LIN", points=self.points_linear)
        self.curve_smooth = IntegratedShortRateCurve(
            name="USD_OIS_SMOOTH", currency="USD", points=self.points_smooth, degree=2, is_local=False
        )
        self.curve_cubic = IntegratedShortRateCurve(
            name="USD_OIS_CUBIC", currency="USD", points=self.points_cubic, degree=3, is_local=True
        )
        self.curve_cubic_smooth = IntegratedShortRateCurve(
            name="USD_OIS_CUBIC_SM", currency="USD", points=self.points_cubic_smooth, degree=3, is_local=False
        )
        
        # 2. Quotes & Target Swaps
        self.quotes = {
            f"IR_USD_OIS_QUOTE.{int(t)}Y": SwapQuote(symbol=f"IR_USD_OIS_QUOTE.{int(t)}Y", tenor=t)
            for t in [1, 2, 3, 5, 7, 10, 12, 15, 20, 30]
        }
        for pt in self.points_linear:
            pt.quote_ref = self.quotes[f"IR_USD_OIS_QUOTE.{int(pt.tenor_years)}Y"]
        for pt in self.points_smooth:
            pt.quote_ref = self.quotes[f"IR_USD_OIS_QUOTE.{int(pt.tenor_years)}Y"]
        for pt in self.points_cubic:
            pt.quote_ref = self.quotes[f"IR_USD_OIS_QUOTE.{int(pt.tenor_years)}Y"]
        for pt in self.points_cubic_smooth:
            pt.quote_ref = self.quotes[f"IR_USD_OIS_QUOTE.{int(pt.tenor_years)}Y"]
            
        self.target_swaps_linear = [
            IRSwapFixedFloatApprox(
                symbol=f"OIS_LIN_{int(t)}Y", 
                tenor_years=t, 
                curve=self.curve_linear,
                notional=10e6
            ) for t in [1, 2, 3, 5, 7, 10, 12, 15, 20, 30]
        ]
        self.target_swaps_smooth = [
            IRSwapFixedFloatApprox(
                symbol=f"OIS_SMOOTH_{int(t)}Y", 
                tenor_years=t, 
                curve=self.curve_smooth,
                notional=10e6
            ) for t in [1, 2, 3, 5, 7, 10, 12, 15, 20, 30]
        ]
        self.target_swaps_cubic = [
            IRSwapFixedFloatApprox(
                symbol=f"OIS_CUBIC_{int(t)}Y", 
                tenor_years=t, 
                curve=self.curve_cubic,
                notional=10e6
            ) for t in [1, 2, 3, 5, 7, 10, 12, 15, 20, 30]
        ]
        self.target_swaps_cubic_smooth = [
            IRSwapFixedFloatApprox(
                symbol=f"OIS_CUBIC_SM_{int(t)}Y", 
                tenor_years=t, 
                curve=self.curve_cubic_smooth,
                notional=10e6
            ) for t in [1, 2, 3, 5, 7, 10, 12, 15, 20, 30]
        ]
        
        # 3. Fitter
        self.fitter_linear = CurveFitter(
            name="USD_OIS_FITTER_LIN", 
            curve=self.curve_linear, 
            points=self.points_linear,
            quotes=list(self.quotes.values()),
            target_swaps=self.target_swaps_linear
        )
        self.fitter_smooth = CurveFitter(
            name="USD_OIS_FITTER_SMOOTH", 
            curve=self.curve_smooth, 
            points=self.points_smooth,
            quotes=list(self.quotes.values()),
            target_swaps=self.target_swaps_smooth
        )
        self.fitter_cubic = CurveFitter(
            name="USD_OIS_FITTER_CUBIC", 
            curve=self.curve_cubic, 
            points=self.points_cubic,
            quotes=list(self.quotes.values()),
            target_swaps=self.target_swaps_cubic
        )
        self.fitter_cubic_smooth = CurveFitter(
            name="USD_OIS_FITTER_CUBIC_SMOOTH", 
            curve=self.curve_cubic_smooth, 
            points=self.points_cubic_smooth,
            quotes=list(self.quotes.values()),
            target_swaps=self.target_swaps_cubic_smooth
        )
        
    def on_batch(self, ticks: list[dict]):
        """Update multiple quotes from a batch and trigger re-solve once."""
        updated = False
        with self._lock:
            for tick_data in ticks:
                sym = tick_data.get("symbol")
                if sym in self.quotes:
                    q = self.quotes[sym]
                    q.rate = float(tick_data["rate"])
                    q.bid = float(tick_data["bid"])
                    q.ask = float(tick_data["ask"])
                    
                    for swap in self.target_swaps_linear + self.target_swaps_smooth + self.target_swaps_cubic + self.target_swaps_cubic_smooth:
                        if swap.tenor_years == q.tenor:
                            swap.fixed_rate = q.rate
                            # Invalidate cached symbolic trees so objective re-reads fixed_rate
                            for attr in ["npv", "fixed_leg_pv", "float_leg_pv", "dv01"]:
                                cache_attr = f"_{attr}_expr_cache"
                                if hasattr(swap, cache_attr):
                                    delattr(swap, cache_attr)

                    updated = True

        if not updated:
            return

        start_time = time.time()
        self.status_message = f"📐 Solving (Batch of {len(ticks)})..."
        logger.info(f"Triggered fit for batch")
        
        try:
            self.fitter_linear.solve()
            self.fitter_smooth.solve()
            self.fitter_cubic.solve()
            
            # 1st Snapshot (after fast solvers)
            now = time.time()
            if now - self._last_snapshot_time > 2.0:
                self._last_snapshot_time = now
                threading.Thread(target=self._update_dfs, daemon=True).start()

            # The heavy one
            self.fitter_cubic_smooth.solve()
            self.tick_count += 1
            self.last_tick_time = datetime.now(timezone.utc)
            
            # 2nd Snapshot (after all solvers)
            threading.Thread(target=self._update_dfs, daemon=True).start()
            
            ms = (time.time() - start_time) * 1000
            self.status_message = f"✅ Converged ({ms:.1f}ms)"
            logger.info(f"Solver converged in {ms:.1f}ms")
            sys.stdout.flush()
        except Exception as e:
            self.status_message = f"❌ Error: {str(e)[:20]}"
            logger.error(f"Solver Error: {e}")
            sys.stdout.flush()

    def _solve_quantlib(self) -> Optional[object]:
        """Solve for the curve using QuantLib (LinearZero)."""
        try:
            import QuantLib as ql
        except ImportError:
            return None
        
        # 1. Constants
        today = ql.Date.todaysDate()
        ql.Settings.instance().evaluationDate = today
        calendar = ql.UnitedStates(ql.UnitedStates.Settlement)
        day_counter = ql.Actual360()
        
        # 2. Helpers
        helpers = []
        for sym, q in self.quotes.items():
            if q.rate <= 0: continue
            tenor = ql.Period(int(q.tenor), ql.Years)
            quote_handle = ql.QuoteHandle(ql.SimpleQuote(float(q.rate)))
            # Standard USD OIS setup (SOFR)
            helper = ql.OISRateHelper(2, tenor, quote_handle, ql.OvernightIndex("SOFR", 0, ql.USDCurrency(), calendar, day_counter))
            helpers.append(helper)
            
        if not helpers: return None
        
        # 3. Bootstrap (LinearZero matches py-flow's LinearTermDiscountCurve)
        try:
            ql_curve = ql.PiecewiseLinearZero(today, helpers, day_counter)
            ql_curve.enableExtrapolation()
            return ql_curve
        except Exception as e:
            logger.error(f"QuantLib Solve Error: {e}")
            return None

    def _update_dfs(self):
        """Build high-fidelity snapshots for UI comparison. (Runs in background)"""
        if not self._snapshot_lock.acquire(blocking=False):
            return
        
        try:
            import pricing.marketmodels.curve_fitter
            if pricing.marketmodels.curve_fitter.IS_SOLVING:
                # Never snapshot while a solver is currently bootstraping or iterating.
                # Inconsistent fitted_rates cause massive spikes in Cubic curves.
                return
            # --- Stage 1: Fast Data Update (Locked) ---
            with self._lock:
                # 1. Quote DF
                q_rows = []
                for q in self.quotes.values():
                    q_rows.append({
                        "Symbol": q.symbol,
                        "Tenor": f"{int(q.tenor)}Y",
                        "Bid (%)": q.bid * 100,
                        "Ask (%)": q.ask * 100,
                        "Mid (%)": (q.bid + q.ask) * 50,
                        "Market (%)": q.rate * 100,
                    })
                self.quote_df = pd.DataFrame(q_rows)
                
                # 2. Curve DF (Pillars) - Use smooth pillars for display
                c_rows = []
                for pt in self.points_smooth:
                    c_rows.append({
                        "Pillar": pt.name,
                        "Tenor": pt.tenor_years,
                        "Fitted Zero (%)": pt.fitted_rate * 100,
                    })
                self.curve_df = pd.DataFrame(c_rows)
                
            # --- Stage 2: Heavy Snapshotting (Unlocked) ---
            # 3. Forward Rate Comparison (Monthly Knots)
            print(f"    [Snapshot] Building forward curves (360 knots)...")
            sys.stdout.flush()
            tenors = np.linspace(0.0833, 30.0, 360) 
            period = 1.0 / 365.0  # Daily forward periods
            fitted_fwds_linear = self.curve_linear.fwd_array(tenors.tolist(), period=period)
            fitted_fwds_smooth = self.curve_smooth.fwd_array(tenors.tolist(), period=period)
            fitted_fwds_cubic = self.curve_cubic.fwd_array(tenors.tolist(), period=period)
            fitted_fwds_cubic_sm = self.curve_cubic_smooth.fwd_array(tenors.tolist(), period=period)
            
            # Diagnostic Magnitude Log
            max_fwd = max(max(fitted_fwds_linear), max(fitted_fwds_smooth), max(fitted_fwds_cubic), max(fitted_fwds_cubic_sm))
            min_fwd = min(min(fitted_fwds_linear), min(fitted_fwds_smooth), min(fitted_fwds_cubic), min(fitted_fwds_cubic_sm))
            
            print(f"    [Snapshot] py-flow curves ready. Count: {len(fitted_fwds_linear)}")
            print(f"               Range: [{min_fwd*100:.4f}%, {max_fwd*100:.4f}%]")
            
            # Log specific knot checks for spikes (1Y, 5Y, 10Y, 30Y)
            knot_indices = [11, 59, 119, 359] 
            for kidx in knot_indices:
                if kidx < len(tenors):
                    print(f"               @{tenors[kidx]:.1f}Y: Cub={fitted_fwds_cubic[kidx]*100:.4f}%, CubSm={fitted_fwds_cubic_sm[kidx]*100:.4f}%")
            sys.stdout.flush()
            
            # QuantLib benchmark (Throttled: only re-solve if needed)
            ql_fwds = [np.nan] * len(tenors)
            now = time.time()
            if now - self.last_ql_solve_time > 5.0 or self.last_ql_curve is None:
                print(f"⚖️ [Snapshot] Starting QuantLib benchmark solve...")
                sys.stdout.flush()
                self.last_ql_curve = self._solve_quantlib()
                self.last_ql_solve_time = now
                print(f"✅ [Snapshot] QuantLib benchmark ready.")
                sys.stdout.flush()
            
            if self.last_ql_curve:
                try:
                    for i, t in enumerate(tenors):
                        # Calculate QL forward (1-day discrete fwd rate to match Py-Flow)
                        ql_fwds[i] = self.last_ql_curve.forwardRate(t, t + period, 0, 0).rate() * 100
                except Exception as e:
                    logger.debug(f"QL forward evaluation error: {e}")

            # Naive Par-Zero Interpolation (Baseline) - Vectorized for speed
            with self._lock:
                # We take a quick lock just to grab the rates, then release
                orig_rates = np.array([q.rate for q in self.quotes.values()])
                orig_tenors = np.array([q.tenor for q in self.quotes.values()])
            
            # Vectorized numpy interpolation is 100x faster than loops
            interp_zeros = np.interp(tenors, orig_tenors, orig_rates)
            interp_zeros_plus = np.interp(tenors + period, orig_tenors, orig_rates)
            
            orig_dfs = (1.0 + interp_zeros)**(-tenors)
            orig_dfs_plus = (1.0 + interp_zeros_plus)**(-(tenors + period))
            orig_fwds = (orig_dfs/orig_dfs_plus - 1.0) / period

            # Update the final dataframe (triggers UI refresh if watched)
            new_df = pd.DataFrame({
                "Tenor": tenors,
                "py-flow Linear Fwd (%)": np.array(fitted_fwds_linear) * 100,
                "py-flow Quadratic Fwd (%)": np.array(fitted_fwds_smooth) * 100,
                "py-flow Cubic Fwd (%)": np.array(fitted_fwds_cubic) * 100,
                "py-flow Cubic Smooth Fwd (%)": np.array(fitted_fwds_cubic_sm) * 100,
                "QuantLib Forward (%)": ql_fwds,
                "Original Forward (%)": np.array(orig_fwds) * 100
            })

            # Robustness: Clip extreme values and handle NaNs to prevent Bokeh rendering failure
            # Rates > 100% or < -20% are likely solver/instability artifacts
            cols = [c for c in new_df.columns if "Fwd" in c or "Forward" in c]
            for col in cols:
                # Handle NaNs and Infs before clipping
                new_df[col] = np.nan_to_num(new_df[col], nan=0.0, posinf=100.0, neginf=-20.0)
                new_df[col] = np.clip(new_df[col], -20.0, 100.0)

            self.forward_df = new_df
            print(f"    [Snapshot] Dataframe updated (360 rows). Sample: {new_df['py-flow Quadratic Fwd (%)'].iloc[0]:.4f}%")
            sys.stdout.flush()

        except Exception as e:
            logger.error(f"Snapshot Error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self._snapshot_lock.release()

# ── UI App ──────────────────────────────────────────────────────────────────

def create_app():
    state = SwapCurveState()
    
    # Start background consumer
    thread = threading.Thread(target=_start_md_consumer, args=(state,), daemon=True)
    thread.start()
    
    db = Dashboard("Swap Curve Monitor", subtitle="USD OIS • Live Fitting")
    
    # --- Page 1: Quote Monitor ---
    p1 = db.add_page("Quotes", icon="📈")
    
    # KPI Strip
    kpi_row = pn.Row(sizing_mode="stretch_width")
    
    # Status Card first (enlarged for visibility)
    status_card = pn.pane.HTML("", width=350, css_classes=["card", "kpi-card"])
    def _update_status(e):
        status_card.object = f'<div class="kpi-title">Solver Status</div><div class="kpi-value" style="font-size:1rem; white-space:nowrap">{state.status_message}</div>'
    state.param.watch(_update_status, "status_message")
    _update_status(None)
    kpi_row.append(status_card)

    for t in [1, 5, 10, 30]:
        kpi = pn.pane.HTML("", width=200, css_classes=["card", "kpi-card"])
        def _update_kpi(target=kpi, tenor=t):
            df = state.quote_df
            if df is not None and not df.empty:
                val = df[df["Tenor"] == f"{tenor}Y"]["Market (%)"].iloc[0]
                target.object = f'<div class="kpi-title">{tenor}Y Par Rate</div><div class="kpi-value">{val:.3f}%</div>'
        state.param.watch(lambda e: _update_kpi(), "quote_df")
        kpi_row.append(kpi)
    
    p1.add_widget(pn.pane.Markdown("### Real-time Quotes"), span=12)
    p1.add_table(state.param.quote_df, title="OIS Market Quotes", span=12, height=400)
    p1.add_widget(kpi_row, span=12)

    # --- Page 2: Fitted Curve ---
    p2 = db.add_page("Analytics", icon="📐")
    
    # Forward Chart
    def _create_chart(df):
        if df is None or df.empty:
            return figure(title="Awaiting Data...")
        
        source = ColumnDataSource(df)
        p = figure(
            title="Forward Rate Structure (Daily Instantaneous Fwds)", 
            height=450, 
            sizing_mode="stretch_width",
            x_axis_label="Tenor (Years)",
            y_axis_label="Rate (%)",
            tools="pan,wheel_zoom,reset,save"
        )
        
        l1 = p.line("Tenor", "py-flow Quadratic Fwd (%)", source=source, color="#8b5cf6", line_width=1.5, legend_label="py-flow Quadratic (Smooth)")
        l_cub = p.line("Tenor", "py-flow Cubic Fwd (%)", source=source, color="#ef4444", line_width=2, legend_label="py-flow Cubic (Local)")
        l_cub_sm = p.line("Tenor", "py-flow Cubic Smooth Fwd (%)", source=source, color="#ec4899", line_width=3, legend_label="py-flow Cubic (Smooth)")
        l_lin = p.line("Tenor", "py-flow Linear Fwd (%)", source=source, color="#3b82f6", line_width=2, line_dash="dashed", legend_label="py-flow Linear")
        l_ql = p.line("Tenor", "QuantLib Forward (%)", source=source, color="#10b981", line_width=2.5, legend_label="QuantLib Ref")
        l2 = p.line("Tenor", "Original Forward (%)", source=source, color="#6b7280", line_width=1.5, line_dash="dotted", legend_label="Naive Baseline")
        
        p.add_tools(HoverTool(renderers=[l_cub_sm], tooltips=[
            ("Tenor", "@Tenor{0.0}Y"), 
            ("py-flow Cubic Smooth", "@{py-flow Cubic Smooth Fwd (%)}{0.000}%"), 
            ("py-flow Cubic Local", "@{py-flow Cubic Fwd (%)}{0.000}%"), 
            ("py-flow Quadratic", "@{py-flow Quadratic Fwd (%)}{0.000}%"), 
            ("py-flow Linear", "@{py-flow Linear Fwd (%)}{0.000}%"), 
            ("QuantLib", "@{QuantLib Forward (%)}{0.000}%"),
            ("Naive", "@{Original Forward (%)}{0.000}%")
        ]))
        
        p.legend.location = "top_right"
        p.legend.click_policy = "hide"
        p.legend.background_fill_alpha = 0.6
        
        return p

    chart_pane = pn.pane.Bokeh(sizing_mode="stretch_both")
    def _update_chart(event):
        chart_pane.object = _create_chart(event.new)
    
    state.param.watch(_update_chart, "forward_df")
    
    p2.add_chart(chart_pane, title="Forward Rates: Fitted vs Observed", span=8, height=500)
    p2.add_table(state.param.curve_df, title="Curve Pillars", span=4, height=500)
    p2.add_table(state.param.forward_df, title="Forward Rate Data (Monthly Knots)", span=12, height=300)

    return db

if __name__ == "__main__":
    app = create_app()
    app.serve(port=8050)
