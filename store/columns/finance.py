"""
Finance domain columns — bid, ask, strike, volatility, notional, etc.

Columns for market data, options, bonds, FX, and risk entities.
"""

from store.columns import REGISTRY

# ── Market Data ───────────────────────────────────────────────────

REGISTRY.define("bid", float,
    description="Best bid price",
    semantic_type="currency_amount",
    role="measure",
    unit="USD",
    format=",.4f",
    display_name="Bid",
    category="market_data",
    synonyms=["bid price"],
)

REGISTRY.define("ask", float,
    description="Best ask/offer price",
    semantic_type="currency_amount",
    role="measure",
    unit="USD",
    format=",.4f",
    display_name="Ask",
    category="market_data",
    synonyms=["ask price", "offer", "offer price"],
)

REGISTRY.define("last", float,
    description="Last traded price",
    semantic_type="currency_amount",
    role="measure",
    unit="USD",
    format=",.4f",
    display_name="Last",
    category="market_data",
    synonyms=["last price", "last trade"],
)

REGISTRY.define("volume", int,
    description="Trading volume",
    semantic_type="count",
    role="measure",
    unit="shares",
    aggregation="sum",
    display_name="Volume",
    category="market_data",
    synonyms=["vol", "trading volume"],
)

REGISTRY.define("rate", float,
    description="Exchange or interest rate",
    semantic_type="ratio",
    role="measure",
    unit="ratio",
    format=",.6f",
    display_name="Rate",
    category="market_data",
)

# ── Position / Portfolio ──────────────────────────────────────────

REGISTRY.define("avg_cost", float,
    description="Average cost basis per unit",
    semantic_type="currency_amount",
    role="measure",
    unit="USD",
    format=",.2f",
    display_name="Avg Cost",
    category="portfolio",
    synonyms=["average cost", "cost basis"],
)

REGISTRY.define("current_price", float,
    description="Current market price",
    semantic_type="currency_amount",
    role="measure",
    unit="USD",
    format=",.2f",
    display_name="Current Price",
    category="portfolio",
)

# ── Options ───────────────────────────────────────────────────────

REGISTRY.define("underlying_price", float,
    description="Price of the underlying instrument",
    semantic_type="currency_amount",
    role="measure",
    unit="USD",
    format=",.2f",
    display_name="Underlying Price",
    category="derivatives",
)

REGISTRY.define("strike", float,
    description="Option strike price",
    semantic_type="currency_amount",
    role="measure",
    unit="USD",
    format=",.2f",
    display_name="Strike",
    category="derivatives",
    synonyms=["strike price", "exercise price"],
)

REGISTRY.define("time_to_expiry", float,
    description="Time to option expiry",
    semantic_type="duration",
    role="measure",
    unit="years",
    format=".4f",
    display_name="Time to Expiry",
    category="derivatives",
    synonyms=["tte", "time to maturity", "tenor"],
)

REGISTRY.define("volatility", float,
    description="Annualized volatility",
    semantic_type="percentage",
    role="measure",
    unit="ratio",
    format=".2%",
    display_name="Volatility",
    category="derivatives",
    synonyms=["vol", "implied vol", "iv"],
)

REGISTRY.define("risk_free_rate", float,
    description="Risk-free interest rate",
    semantic_type="percentage",
    role="measure",
    unit="ratio",
    format=".2%",
    display_name="Risk-Free Rate",
    category="derivatives",
    synonyms=["rfr", "risk free", "rate"],
)

# ── FX ────────────────────────────────────────────────────────────

REGISTRY.define("pair", str,
    description="Currency pair (e.g. EUR/USD)",
    semantic_type="identifier",
    role="dimension",
    display_name="Pair",
    category="fx",
    synonyms=["currency pair", "ccy pair"],
)

# ── Bonds ─────────────────────────────────────────────────────────

REGISTRY.define("isin", str,
    description="International Securities Identification Number",
    semantic_type="identifier",
    role="dimension",
    max_length=12,
    display_name="ISIN",
    category="fixed_income",
)

REGISTRY.define("face_value", float,
    description="Bond face/par value",
    semantic_type="currency_amount",
    role="measure",
    unit="USD",
    format=",.2f",
    display_name="Face Value",
    category="fixed_income",
    synonyms=["par value", "nominal"],
)

REGISTRY.define("coupon_rate", float,
    description="Annual coupon rate",
    semantic_type="percentage",
    role="measure",
    unit="ratio",
    format=".2%",
    display_name="Coupon Rate",
    category="fixed_income",
    synonyms=["coupon"],
)

REGISTRY.define("yield_to_maturity", float,
    description="Yield to maturity",
    semantic_type="percentage",
    role="measure",
    unit="ratio",
    format=".2%",
    display_name="YTM",
    category="fixed_income",
    synonyms=["ytm", "yield"],
)

REGISTRY.define("years_to_maturity", float,
    description="Years until bond maturity",
    semantic_type="duration",
    role="measure",
    unit="years",
    format=".2f",
    display_name="Years to Maturity",
    category="fixed_income",
)

# ── Risk ──────────────────────────────────────────────────────────

REGISTRY.define("notional", float,
    description="Notional exposure amount",
    semantic_type="currency_amount",
    role="measure",
    unit="USD",
    format=",.2f",
    display_name="Notional",
    category="risk",
    synonyms=["notional amount", "exposure"],
    allowed_prefixes=["leg1", "leg2", "leg"],
)

REGISTRY.define("daily_vol", float,
    description="Daily volatility",
    semantic_type="percentage",
    role="measure",
    unit="ratio",
    format=".4f",
    display_name="Daily Vol",
    category="risk",
)

REGISTRY.define("z_score", float,
    description="Z-score for confidence interval",
    semantic_type="score",
    role="measure",
    unit="ratio",
    format=".3f",
    display_name="Z-Score",
    category="risk",
)

# ── Computed columns (finance) ──────────────────────────────────

REGISTRY.define("mid", float,
    description="Mid price ((bid + ask) / 2)",
    role="measure", unit="USD",
    category="market_data",
)

REGISTRY.define("spread", float,
    description="Bid-ask spread (ask - bid)",
    role="measure", unit="USD",
    category="market_data",
)

REGISTRY.define("spread_bps", float,
    description="Spread in basis points",
    role="measure", unit="bps",
    category="market_data",
)

REGISTRY.define("spread_pips", float,
    description="Spread in pips (FX)",
    role="measure", unit="pips",
    category="fx",
)

REGISTRY.define("intrinsic_call", float,
    description="Call option intrinsic value",
    role="measure", unit="USD",
    category="derivatives",
)

REGISTRY.define("moneyness", float,
    description="Option moneyness (underlying / strike)",
    role="measure", unit="ratio",
    category="derivatives",
)

REGISTRY.define("time_value_proxy", float,
    description="Time value proxy (volatility × sqrt(time))",
    role="measure", unit="ratio",
    category="derivatives",
)

REGISTRY.define("pricing_label", str,
    description="Option pricing label (ITM/ATM/OTM)",
    role="attribute",
    category="derivatives",
)

REGISTRY.define("model_upper", str,
    description="Upper-cased model name",
    role="attribute",
)

REGISTRY.define("eur_value", float,
    description="EUR-converted value",
    role="measure", unit="EUR",
    category="fx",
)

REGISTRY.define("annual_coupon", float,
    description="Annual coupon payment",
    role="measure", unit="USD",
    category="fixed_income",
)

REGISTRY.define("current_yield", float,
    description="Current yield (coupon / price)",
    role="measure", unit="ratio",
    category="fixed_income",
)

REGISTRY.define("duration_proxy", float,
    description="Duration proxy estimate",
    role="measure", unit="years",
    category="fixed_income",
)

REGISTRY.define("duration", float,
    description="Bond duration",
    role="measure", unit="years",
    category="fixed_income",
)

REGISTRY.define("price_impact_10bp", float,
    description="Price impact for 10bp rate move",
    role="measure", unit="USD",
    category="risk",
)

REGISTRY.define("var_1d", float,
    description="1-day Value at Risk",
    role="measure", unit="USD",
    category="risk",
)

REGISTRY.define("var_10d", float,
    description="10-day Value at Risk",
    role="measure", unit="USD",
    category="risk",
)

REGISTRY.define("confidence", float,
    description="Confidence level for VaR",
    role="measure", unit="ratio",
    category="risk",
)

# ── Interest Rate Swaps / Yield Curve ─────────────────────────────

REGISTRY.define("tenor_years", float,
    description="Tenor in years (e.g. 1.0, 5.0, 10.0)",
    semantic_type="duration",
    role="measure",
    unit="years",
    format=".1f",
    display_name="Tenor",
    category="fixed_income",
    synonyms=["tenor", "maturity"],
)

REGISTRY.define("fixed_rate", float,
    description="Fixed leg coupon rate on a swap",
    semantic_type="percentage",
    role="measure",
    unit="ratio",
    format=".4%",
    display_name="Fixed Rate",
    category="fixed_income",
)

REGISTRY.define("float_rate", float,
    description="Floating leg reference rate on a swap",
    semantic_type="percentage",
    role="measure",
    unit="ratio",
    format=".4%",
    display_name="Float Rate",
    category="fixed_income",
)

REGISTRY.define("currency", str,
    description="ISO currency code (e.g. USD, EUR, JPY)",
    semantic_type="identifier",
    role="dimension",
    max_length=3,
    display_name="Currency",
    category="fx",
    synonyms=["ccy"],
    allowed_prefixes=["leg1", "leg2", "collateral", "leg"],
)

REGISTRY.define("discount_factor", float,
    description="Discount factor = 1 / (1 + rate) ^ tenor",
    role="measure", unit="ratio",
    category="fixed_income",
)

REGISTRY.define("fixed_leg_pv", float,
    description="Present value of fixed leg cash flows",
    role="measure", unit="USD",
    category="fixed_income",
    allowed_prefixes=["leg1", "leg2", "leg"],
)

REGISTRY.define("float_leg_pv", float,
    description="Present value of floating leg cash flows",
    role="measure", unit="USD",
    category="fixed_income",
    allowed_prefixes=["leg1", "leg2", "leg"],
)

REGISTRY.define("npv", float,
    description="Net present value (float_leg_pv - fixed_leg_pv)",
    role="measure", unit="USD",
    category="fixed_income",
)

REGISTRY.define("dv01", float,
    description="Dollar value of a basis point (rate sensitivity)",
    role="measure", unit="USD",
    category="risk",
)

REGISTRY.define("pnl_status", str,
    description="P&L status label (PROFIT / LOSS / FLAT)",
    role="attribute",
    category="risk",
)

REGISTRY.define("base_rate", float,
    description="Base reference rate before adjustments",
    role="measure", unit="ratio",
    format=".4%",
    category="fixed_income",
)

REGISTRY.define("sensitivity", float,
    description="Rate sensitivity to underlying factor moves",
    role="measure", unit="ratio",
    category="risk",
)

REGISTRY.define("fx_base_mid", float,
    description="Base FX mid price used for rate derivation",
    role="measure", unit="price",
    category="fx",
)

REGISTRY.define("fitted_rate", float,
    description="Rate produced by the curve solver/fitter",
    semantic_type="percentage",
    role="measure",
    unit="ratio",
    format=".4%",
    display_name="Fitted Rate",
    category="fixed_income",
)

REGISTRY.define("initial_fx", float,
    description="Initial FX rate for multi-currency instruments",
    role="measure", unit="ratio",
    category="fx",
)

REGISTRY.define("exchange_notional", bool,
    description="Whether notional is exchanged at start/end",
    role="attribute",
    category="fixed_income",
)

REGISTRY.define("is_fitted", bool,
    description="If True, the rate is set by a Solver (not pass-through)",
    role="attribute",
    category="fixed_income",
)

REGISTRY.define("quote_ref", object,
    description="Reference to the input SwapQuote/MarketQuote object",
    role="attribute",
    category="market_data",
)

REGISTRY.define("fx_ref", object,
    description="Cross-entity reference to an FXSpot instance",
    role="attribute",
    category="fx",
)

REGISTRY.define("curve_ref", object,
    description="Cross-entity reference to a YieldCurvePoint instance",
    role="attribute",
    category="fixed_income",
)

REGISTRY.define("avg_rate", float,
    description="Average rate across yield curve points",
    role="measure", unit="ratio",
    category="fixed_income",
)

REGISTRY.define("curve_slope", float,
    description="Yield curve slope (long rate - short rate)",
    role="measure", unit="ratio",
    category="fixed_income",
)

REGISTRY.define("swaps", list,
    description="List of interest rate swap objects",
    role="attribute",
    category="fixed_income",
)

REGISTRY.define("curve_points", list,
    description="List of yield curve point objects",
    role="attribute",
    category="fixed_income",
)

REGISTRY.define("total_npv", float,
    description="Total NPV across all swaps in portfolio",
    role="measure", unit="USD",
    category="risk",
)

REGISTRY.define("total_dv01", float,
    description="Total DV01 across all swaps in portfolio",
    role="measure", unit="USD",
    category="risk",
)

REGISTRY.define("max_npv", float,
    description="Maximum NPV among portfolio swaps",
    role="measure", unit="USD",
    category="risk",
)

REGISTRY.define("min_npv", float,
    description="Minimum NPV among portfolio swaps",
    role="measure", unit="USD",
    category="risk",
)

REGISTRY.define("swap_count", int,
    description="Number of swaps in portfolio",
    role="measure", unit="units",
    category="fixed_income",
)

# ── Portfolio Risk ───────────────────────────────────────────────

REGISTRY.define("sector", str,
    description="Market sector classification (e.g. Technology, Financials)",
    semantic_type="label",
    role="dimension",
    display_name="Sector",
    category="portfolio",
    synonyms=["industry", "sector classification"],
)

REGISTRY.define("implied_vol", float,
    description="Implied volatility (annualized)",
    semantic_type="percentage",
    role="measure",
    unit="ratio",
    format=".2%",
    display_name="Implied Vol",
    category="risk",
    synonyms=["iv", "implied volatility"],
)

REGISTRY.define("beta", float,
    description="Beta relative to market benchmark",
    semantic_type="ratio",
    role="measure",
    unit="ratio",
    format=".2f",
    display_name="Beta",
    category="risk",
)

REGISTRY.define("var_1d_95", float,
    description="1-day 95% parametric Value at Risk",
    role="measure", unit="USD",
    category="risk",
)

REGISTRY.define("var_1d_99", float,
    description="1-day 99% parametric Value at Risk",
    role="measure", unit="USD",
    category="risk",
)

REGISTRY.define("total_value", float,
    description="Total portfolio market value",
    role="measure", unit="USD",
    category="portfolio",
)

REGISTRY.define("total_unrealized_pnl", float,
    description="Total unrealized P&L across positions",
    role="measure", unit="USD",
    category="risk",
)

REGISTRY.define("portfolio_var_95", float,
    description="Diversified portfolio 1-day 95% VaR",
    role="measure", unit="USD",
    category="risk",
)

REGISTRY.define("portfolio_var_99", float,
    description="Diversified portfolio 1-day 99% VaR",
    role="measure", unit="USD",
    category="risk",
)

REGISTRY.define("var_pct_95", float,
    description="VaR as percentage of portfolio (95%)",
    role="measure", unit="ratio",
    category="risk",
)

REGISTRY.define("var_pct_99", float,
    description="VaR as percentage of portfolio (99%)",
    role="measure", unit="ratio",
    category="risk",
)

REGISTRY.define("hhi", float,
    description="Herfindahl-Hirschman Index for concentration",
    role="measure", unit="ratio",
    category="risk",
)


# ── Interest Rate Curve Fitting & Jacobians ────────────────────────

REGISTRY.define("output_tenor", float,
    description="The output tenor of a Jacobian entry or fitting point",
    role="measure", unit="years",
    category="fixed_income",
)

REGISTRY.define("input_tenor", float,
    description="The input tenor of a Jacobian entry",
    role="measure", unit="years",
    category="fixed_income",
)

REGISTRY.define("quote_symbol", str,
    description="The symbol of the input quote being sensitized",
    role="dimension",
    category="market_data",
)

REGISTRY.define("jacobian", list,
    description="Matrix of sensitivies (∂fitted / ∂quoted)",
    role="attribute",
    category="fixed_income",
)

REGISTRY.define("points", list,
    description="Collection of curve knot points",
    role="attribute",
    category="fixed_income",
)

REGISTRY.define("point_count", int,
    description="Number of knot points in the curve",
    role="measure", unit="units",
    category="fixed_income",
)

REGISTRY.define("pillar_tenors", list,
    description="Sorted list of pillar tenors",
    role="attribute",
    category="fixed_income",
)

REGISTRY.define("pillar_rates", list,
    description="Sorted list of pillar rates",
    role="attribute",
    category="fixed_income",
)

REGISTRY.define("pillar_names", list,
    description="Sorted list of pillar names",
    role="attribute",
    category="fixed_income",
)

REGISTRY.define("zero_rate", float,
    description="The continuously compounded zero rate",
    role="measure", unit="ratio",
    category="fixed_income",
)

REGISTRY.define("integrated_rate", float,
    description="The integral of the short rate (used for DFs)",
    role="measure", unit="ratio",
    category="fixed_income",
)

REGISTRY.define("short_rate", float,
    description="The instantaneous short rate",
    role="measure", unit="ratio",
    category="fixed_income",
)

REGISTRY.define("mean_reversion", float,
    description="Mean reversion speed (kappa)",
    role="measure", unit="ratio",
    category="fixed_income",
)

REGISTRY.define("degree", int,
    description="Polynomial degree for splines (2=Quadratic, 3=Cubic)",
    role="attribute",
    category="fixed_income",
)

REGISTRY.define("is_local", bool,
    description="If True, uses local spline conditions; if False, match slopes",
    role="attribute",
    category="fixed_income",
)

REGISTRY.define("collateral_currency", str,
    description="ISO currency code for collateral discounting",
    role="dimension",
    category="fx",
)

REGISTRY.define("is_target", bool,
    description="If True, this instrument is a target for the CurveFitter",
    role="attribute",
    category="fixed_income",
)


REGISTRY.define("curve", object,
    description="Reference to a curve implementation (CurveBase)",
    role="attribute",
    category="fixed_income",
)

REGISTRY.define("projection_curve", object,
    description="Reference to a curve used for forward rate projections",
    role="attribute",
    category="fixed_income",
    allowed_prefixes=["leg1", "leg2", "leg"],
)

REGISTRY.define("discount_curve", object,
    description="Reference to a curve used for discounting cash flows",
    role="attribute",
    category="fixed_income",
    allowed_prefixes=["leg1", "leg2", "leg"],
)

REGISTRY.define("float_spread", float,
    description="Spread added to the floating rate (in bps or decimal)",
    role="measure", unit="ratio",
    category="fixed_income",
)

REGISTRY.define("target_swaps", list,
    description="List of target instruments for the CurveFitter",
    role="attribute",
    category="fixed_income",
)

REGISTRY.define("quotes", list,
    description="List of market quotes used as inputs for curve fitting",
    role="attribute",
    category="market_data",
)

REGISTRY.define("quote_trigger", float,
    description="Cumulative trigger value computed from input quote rates",
    role="measure", unit="ratio",
    category="market_data",
)

REGISTRY.define("tenor", float,
    description="Benchmark tenor in years (e.g. 1.0, 5.0)",
    role="measure", unit="years",
    category="fixed_income",
)

REGISTRY.define("portfolio", str,
    description="Name of the portfolio being risk-analyzed",
    role="dimension",
    category="risk",
)

REGISTRY.define("quote", str,
    description="Symbol of the benchmark quote for risk ladder mapping",
    role="dimension",
    category="market_data",
)

REGISTRY.define("equiv_notional", float,
    description="Equivalent notional amount for a basis point move",
    role="measure", unit="USD",
    category="risk",
)

REGISTRY.define("par_rate", float,
    description="Fixed rate at which the swap NPV is zero",
    role="measure", unit="ratio",
    category="fixed_income",
)

REGISTRY.define("pillar_risk", dict,
    description="Dictionary of symbolic sensitivities (Greeks)",
    role="attribute",
    category="risk",
)

REGISTRY.define("concentration_level", str,
    description="Portfolio concentration level (diversified/moderate/concentrated)",
    role="attribute",
    category="risk",
)

REGISTRY.define("sector_weights", dict,
    description="Sector weight breakdown as percentage map",
    role="attribute",
    category="portfolio",
)

REGISTRY.define("top_risk_contributors", list,
    description="Positions ranked by VaR contribution",
    role="attribute",
    category="risk",
)
