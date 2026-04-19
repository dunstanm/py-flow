import marimo

__generated_with = "0.23.0"
app = marimo.App(width="full")


@app.cell
def _():
    import marimo as mo
    import numpy as np
    import pandas as pd
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    import time
    from dataclasses import dataclass, field
    import sys
    import os

    # Ensure project root is in path
    project_root = os.path.abspath(os.path.join(os.getcwd(), ".."))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    # Internal Imports
    from pricing.instruments.eq_option import EquityOption
    from pricing.instruments.eq_forward import EquityForward
    from pricing.marketmodels.eq_curve_dividend import DividendCurve
    from pricing.marketmodels.ir_curve_integrated_rate import IntegratedShortRateCurve, IntegratedRatePoint
    from pricing.marketmodels.ir_curve_fitter import CurveFitter
    from pricing.marketmodels.ir_curve_yield import YieldCurvePoint, LinearTermDiscountCurve
    from pricing.instruments.ir_swap_fixed_floatapprox import IRSwapFixedFloatApprox
    from pricing.marketmodels.ir_curve_swap import SwapQuote

    return (
        CurveFitter,
        DividendCurve,
        EquityForward,
        EquityOption,
        IRSwapFixedFloatApprox,
        IntegratedShortRateCurve,
        LinearTermDiscountCurve,
        SwapQuote,
        YieldCurvePoint,
        go,
        mo,
        np,
        pd,
        time,
    )


@app.cell
def _(mo):
    mo.md(r"""
    # 📐 Curve Fitting Sandbox
    This notebook provides a decoupled environment for testing and debugging swap curve fitting algorithms using static market data.
    """)
    return


@app.cell
def _(mo):
    # Static Quote Data
    default_quotes = {
        "1Y": 0.0450,
        "2Y": 0.0420,
        "3Y": 0.0405,
        "5Y": 0.0385,
        "7Y": 0.0375,
        "10Y": 0.0370,
        "12Y": 0.0372,
        "15Y": 0.0375,
        "20Y": 0.0380,
        "30Y": 0.0365,
    }

    quote_inputs = {
        tenor: mo.ui.number(value=rate*100, step=0.01, label=f"{tenor} (%)")
        for tenor, rate in default_quotes.items()
    }

    mo.md(
        f"""
        ### 📥 Input Market Quotes
        Adjust the par swap rates (in %) for the USD OIS curve.

        {mo.hstack(list(quote_inputs.values()), wrap=True)}
        """
    )
    return (quote_inputs,)


@app.cell
def _(
    CurveFitter,
    IRSwapFixedFloatApprox,
    IntegratedShortRateCurve,
    LinearTermDiscountCurve,
    SwapQuote,
    YieldCurvePoint,
    quote_inputs,
):
    def setup_curve_and_fitter(degree=2, is_local=False, name="test_curve"):
        # 1. Tenors
        tenors = [float(t.replace("Y", "")) for t in quote_inputs.keys()]

        # 2. Quotes
        quotes = [
            SwapQuote(symbol=f"QUOTE_{t}Y", tenor=float(t), rate=quote_inputs[f"{t}Y"].value / 100.0)
            for t in [str(int(x)) for x in tenors]
        ]

        # 3. Curve & Points
        points = [
            YieldCurvePoint(name=f"{name}_PT_{t}Y", tenor_years=t, is_fitted=True)
            for t in tenors
        ]

        if degree == 1:
            curve = LinearTermDiscountCurve(name=name, points=points)
        else:
            curve = IntegratedShortRateCurve(
                name=name, 
                currency="USD", 
                points=points, 
                degree=degree, 
                is_local=is_local
            )

        # Link quotes to points
        for pt, q in zip(points, quotes):
            pt.quote_ref = q

        # 4. Target Swaps
        target_swaps = [
            IRSwapFixedFloatApprox(
                symbol=f"SWAP_{int(q.tenor)}Y",
                tenor_years=q.tenor,
                fixed_rate=q.rate,
                curve=curve,
                notional=10e6
            ) for q in quotes
        ]

        # 5. Fitter
        fitter = CurveFitter(
            name=f"FITTER_{name}",
            curve=curve,
            points=points,
            quotes=quotes,
            target_swaps=target_swaps
        )

        return fitter, curve, target_swaps

    return (setup_curve_and_fitter,)


@app.cell
def _(mo):
    mo.md("### ⚙️ Solver Configuration")

    curve_type = mo.ui.dropdown(
        options={
            "Linear (C0 Zero)": (1, False),
            "Quadratic Smooth": (2, False),
            "Cubic Local (Bessel)": (3, True),
            "Cubic Smooth (Forward)": (3, False),
        },
        value="Quadratic Smooth",
        label="Fitting Algorithm"
    )

    run_button = mo.ui.run_button(label="🚀 Re-Solve Curve")

    mo.hstack([curve_type, run_button])
    return curve_type, run_button


@app.cell
def _(curve_type, run_button, setup_curve_and_fitter, time):
    # This cell runs when the button is pressed or curve type changes
    run_button

    deg, loc = curve_type.value
    fitter, curve, swaps = setup_curve_and_fitter(degree=deg, is_local=loc, name="sandbox")

    start = time.time()
    fitter.solve()
    solve_time_ms = (time.time() - start) * 1000

    return curve, solve_time_ms, swaps


@app.cell
def _(curve, np, pd):
    # Snapshot plotting data
    plot_tenors = np.linspace(0.01, 31.0, 500)
    period = 1.0/365.0 # Daily forward

    fwds = curve.fwd_array(plot_tenors.tolist(), period=period)
    zeros = [curve.df_at(t)**(-1.0/t)-1.0 if t > 0 else curve.df_at(0.01)**(-1.0/0.01)-1.0 for t in plot_tenors]

    # Format results
    pillar_data = pd.DataFrame([
        {"Tenor": p.tenor_years, "Market Rate (%)": p.quote_ref.rate*100, "Fitted Zero (%)": p.fitted_rate*100}
        for p in curve._sorted_points()
    ])

    return fwds, pillar_data, plot_tenors, zeros


@app.cell
def _(fwds, go, mo, np, pillar_data, plot_tenors, solve_time_ms, zeros):
    fig = go.Figure()

    # Forward Rate
    fig.add_trace(go.Scatter(
        x=plot_tenors, 
        y=np.array(fwds) * 100, 
        name="Inst. Forward Rate (%)",
        line=dict(color="#8b5cf6", width=2.5)
    ))

    # Zero Rate
    fig.add_trace(go.Scatter(
        x=plot_tenors, 
        y=np.array(zeros) * 100, 
        name="Zero Rate (%)",
        line=dict(color="#10b981", width=1.5, dash="dash")
    ))

    # Pillars
    fig.add_trace(go.Scatter(
        x=pillar_data["Tenor"],
        y=pillar_data["Market Rate (%)"],
        mode="markers",
        name="Market Par Rates",
        marker=dict(size=10, color="#ef4444", symbol="diamond")
    ))

    fig.update_layout(
        title=f"Fitted Curve Analytics (Solved in {solve_time_ms:.2f}ms)",
        xaxis_title="Tenor (Years)",
        yaxis_title="Rate (%)",
        template="plotly_dark",
        height=600,
        hovermode="x unified",
        legend=dict(yanchor="top", y=0.99, xanchor="right", x=0.99)
    )

    mo.md(f"""
    {mo.as_html(fig)}
    """)
    return


@app.cell
def _(mo, pd, pillar_data, swaps):
    # Residuals and Pillar Stats
    residual_data = []
    for s in swaps:
        residual_data.append({
            "Swap": s.symbol,
            "Tenor": s.tenor_years,
            "NPV": s.npv,
            "DV01": s.dv01,
        })

    res_df = pd.DataFrame(residual_data)

    mo.md(
        f"""
        ### 📊 Solve Diagnostics

        {mo.hstack([
            mo.vstack([
                mo.md("#### Pillar Results"),
                mo.ui.table(pillar_data, selection=None)
            ], align="start"),
            mo.vstack([
                mo.md("#### Solver Residuals (NPV)"),
                mo.ui.table(res_df, selection=None)
            ], align="start")
        ], gap=4)}
        """
    )
    return


@app.cell
def _(mo):
    mo.md(r"""
    ### 🧪 Sensitivity Testing
    Use the table below to manually tweak the fitted rates if you want to explore the shape of the forward curve without re-solving.
    """)
    return


@app.cell
def _(curve, mo):
    # Manual pillars tweak
    manual_pts = curve._sorted_points()
    manual_inputs = [
        mo.ui.number(value=p.fitted_rate*100, step=0.01, label=f"{p.tenor_years}Y")
        for p in manual_pts
    ]

    mo.md(
        f"""
        #### 🦾 Manual Pillar Overrides
        {mo.hstack(manual_inputs, wrap=True)}
        """
    )
    return (manual_inputs,)


@app.cell
def _(curve, fwds, go, manual_inputs, mo, np, plot_tenors):
    # Live update from manual inputs
    for i, inp in enumerate(manual_inputs):
        curve._sorted_points()[i].fitted_rate = inp.value / 100.0

    curve.invalidate_caches()

    m_fwds = curve.fwd_array(plot_tenors.tolist(), period=1.0/365.0)
    m_zeros = [curve.df_at(t)**(-1.0/t)-1.0 if t > 0 else 0.0 for t in plot_tenors]

    m_fig = go.Figure()
    m_fig.add_trace(go.Scatter(x=plot_tenors, y=np.array(m_fwds)*100, name="Manual Forward", line=dict(color="#ec4899", width=3)))
    m_fig.add_trace(go.Scatter(x=plot_tenors, y=np.array(fwds)*100, name="Last Solved Forward", line=dict(color="#8b5cf6", width=1, dash="dot")))

    m_fig.update_layout(
        title="Manual Forward Rate Tweak (Live)",
        xaxis_title="Tenor (Years)",
        yaxis_title="Rate (%)",
        template="plotly_dark",
        height=400
    )

    mo.md(f"{mo.as_html(m_fig)}")
    return


@app.cell
def _(mo):
    mo.md(r"""
    ---
    # 📈 Equity Options Lab (@traceable cascade)
    Testing the purely reactive Black-Scholes pricing engine using the natively refactored `eq_option` domain models.
    """)
    return


@app.cell
def _(
    DividendCurve,
    EquityForward,
    EquityOption,
    IntegratedShortRateCurve,
    YieldCurvePoint,
    curve,
    mo,
):
    # Base setup using the IR curve generated above
    spot_price = 4500.0
    div_yield = 0.015

    # 1. Dividend curve
    div_curve = DividendCurve(
        name="SPX_DIV",
        base_yield=div_yield
    )

    # 2. Equity Forward Tracker (ties Spot, Yield Curve, and Div Curve)
    fwd_model = EquityForward(
        symbol="SPX_FWD",
        spot=spot_price,
        discount_curve=curve,          # References the interactively fitted Sandbox curve!
        dividend_curve=div_curve
    )

    # 3. Option
    strike = 4600.0
    expiry_years = 1.0
    volatility = 0.18

    option = EquityOption(
        symbol="SPX_CALL",
        forward_model=fwd_model,
        strike=strike,
        expiry_years=expiry_years,
        is_call=True,
        volatility=volatility
    )

    # Trigger reactive cascade
    pv = option.npv

    # Trace dependencies automatically
    try:
        from reactive.traceable import ExecutionTracer
        tracer = ExecutionTracer()
        trace_str = "\n".join([f"• {dep.name}" for dep in tracer._dependencies])
    except Exception:
        trace_str = "Tracer not available"

    mo.md(
        f"""
        ### Option Configuration
        * **Option**: 1Y Call over SPX (Strike: {strike})
        * **Market Forward**: {fwd_model.forward_at(expiry_years):.2f} (Uses Sandbox curve)
        * **Vol**: {volatility*100}%

        ### Valuation
        * **Black-Scholes NPV**: `${pv:.2f}`

        ### `@traceable` Dependency Graph Activation
        The computation successfully traversed:
        {trace_str}
        """
    )
    return div_curve, div_yield, expiry_years, fwd_model, option, pv, spot_price, strike, trace_str, tracer, volatility


if __name__ == "__main__":
    app.run()
