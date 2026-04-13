# Swap Products & Instruments (instruments/)

This document outlines the modular separation of complex derivatives, the DBOS registry integration, and the design rules around multi-curve structures (`discount` vs `projection` layers).

We note that in this initial proposal (aka PR-B) the instruments are relatively standalone, and have minimal use of dates, prefering simpler times. We are focused instead in generating the computation complexity to test the engine scaling.  There is a later PR to come that builds richer hierarchy of re-usable IRLegs, use dates for scheduling and curve interpolation, produces CashFlows series to support concepts like settlements and counterparty credit analysis.


## 1. Centralized Scheduling
To map an arbitrary multi-period Interest Rate Swap out natively into dynamic algebraic expressions across thousands of potential points:
- `instruments/ir_scheduling.py` isolates structural calendar boundaries (e.g. `rack_dates(5.0)`) decoupled completely from arbitrary numerical logic or objects.
- `payment_dates` skips `t=0.0`.
- `reset_dates` skips the ultimate maturity `t=T`.
- **Daily Compounding (OIS/SOFR)**: `compounded_rate()` handles the daily accumulation logic for Overnight Indexed Swaps. It supports historical fixings for "aged" periods and the **telescopic approximation** ($P_{start}/P_{end} - 1$) for future periods.

## 2. Approximate vs. Explicit Swaps
The architecture iteratively constructs and measures swaps against 3 specific levels of fidelity logic natively:

### `IRSwapFixedFloatApprox` (1 Curve)
The "floating leg approximation" swap structurally relies completely heavily upon a mathematical telescoping identity:
- Floating PV = `notional × (1.0 - DF_maturity)`.
- It relies purely on the identical exact continuous curve for *all* projection parameters AND discounting parameters. 
- Structurally requires defining a unified explicit `curve` directly onto the schema definition matrix.

### `IRSwapFixedFloat` (2 Curves)
The IRSwapFixedFloat is modelled on traditional Libor swaps, and allows us to decouple project and funding curves, but assumes one float fixing per payment: 
- Floating PV = `Σ (rate_i * dt_i * df_i)` organically across the term structure.
- Organically relies mathematically upon extracting an explicit algebraic structural projection `fwd(start, end)` natively directly out of `projection_curve(t)`.
- Organically explicitly discounts the face value natively against `discount_curve.df(end)`.
- Replaces the generic schema `curve` parameter entirely against explicitly segmented DBOS `discount_curve` and `projection_curve` attributes recursively organically globally.

### `IRSwapFixedOIS` (OIS Compounding)
Post Libor most currencies trade OIS benchmark swaps, with rolled up daily fixings paid periodically.  
- **Index Resolution**: Automatically maps currency (USD, EUR, GBP, JPY, etc.) to the appropriate index (SOFR, ESTR, SONIA, TONAR, etc.).
- **Aged Periods**: Automatically detects if the current period has started and leverages historical fixing rates.
- **Future Periods**: Leverages the **Telescopic Property** for projection. By using the ratio of discount factors at the start and end of the accrual period, we maintain 100% numerical parity with QuantLib's `OvernightIndexedCoupon` while significantly reducing expression complexity.
- **Risk Propagation**: Fully compatible with the `CurveFitter` for benchmark bootstrap and analytic bucket risk (via Implicit Function Theorem).

### `IRSwapFloatFloat` (4 Curves)
Extends the Libor era swap to basis swaps, required to fit discount curves in when different collateral to payment currency. We add to help test a multi-ccy curve fitting environment, to ensure our engines can scale to more complex risks and solvers.  `leg1_` and `leg2_` schema parameter definition boundary natively (Basis Swaps, Cross-Currency Swaps, Tenor Swaps).
- Configures 4 potential distinct curves analytically natively: `leg1_discount_curve`, `leg1_projection_curve`, `leg2_discount_curve`, `leg2_projection_curve` respectively across the object structure dynamically globally recursively. 
- Integrates a dimensional `exchange_notional` parameter native hook logic boundary (adds Principal Payment algebraic expressions globally recursively across `targets[-1]` parameters dynamically).

### `IRSwapXCCYOIS` (Cross-Currency OIS)
A multi-currency basis swap where both legs use RFR daily compounding, that more commonly traded post-Libor:
- **Dual Index Resolution**: Independently maps Leg 1 and Leg 2 currencies to their respective overnight indices (e.g., JPY TONAR + Spread vs. USD SOFR).
- **Basis Spread**: Configurable basis spread applied to Leg 1 floating payments.
- **Notional Exchange**: Standard initial/final exchange logic included in the NPV expression tree.
- **Cross-Curve Risk**: The platform's symbolic engine naturally differentiates the NPV with respect to both currencies' yield curves simultaneously (∂NPV / ∂JPY_Pillar and ∂NPV / ∂USD_Pillar).


## 3. The `__key__` Ticking Subsystem
Because massive streaming databases dynamically evaluate `SwapPortfolio` vectors recursively:
- Objects mathematically inheriting `@ticking` internally register their state across the object store streaming boundary dynamically.
- `from streaming import ticking` requires explicit internal resolution tracking organically. Thus, all structural swaps define `__key__ = "symbol"`. 
- Multi-dimensional schemas automatically construct streaming memory addresses intrinsically without overriding dynamic `.tick()` hooks internally dynamically. All internal variables naturally resolve algebraically internally safely globally dynamically natively.
- **Serialization Boundaries:** Complex relational dependencies (`curve` objects) and dynamically computed multi-dimensional maps generated by Expr differentiation (`risk` arrays via `CallableDict`) cannot natively serialize into contiguous PyArrow table architectures. They must be explicitly excluded from internal streamers: `@ticking(exclude={"curve", "risk"})`.

---

## 4. Hybrid Validation & Execution Architecture

To balance financial safety (strict product definitions) with high-throughput performance (10k+ swap risk), the instruments use a hybrid validation strategy:

- **Static Validation (Pydantic)**: All instruments (`Storable`) use `pydantic.dataclasses`. This enforces type-correctness and schema consistency during construction and database persistence.
- **Dynamic Execution (@traceable)**: The pricing logic is extracted into a symbolic `Expr` DAG. This bypasses Pydantic’s validation overhead during high-speed reactive updates and vectorized math execution in NumPy, DuckDB, or Deephaven.

This separation ensures that a 10,000-swap portfolio can be strictly validated once at build-time, while still achieving sub-second risk calculations during live market ticks.

## 5. Performance & Scalability (10k Benchmark)

The architecture has been verified at a 10,000-swap scale across a global mixed scenario (USD, JPY, XCCY).

| Metric               | Result (10k Swaps) | Notes                                     |
|----------------------|--------------------|-------------------------------------------|
| **Build Time**       | ~91.4 s            | One-time Pydantic validation cost at scale|
| **NumPy NPV**        | ~242.3 ms          | Vectorized math (Pydantic bypassed)       |
| **NumPy Port. Risk** | ~119.8 ms          | Full Jacobian (15 pillars)                |
| **DuckDB Skinny**    | ~941.7 ms          | SQL-based evaluation (13.1M atoms/sec)   |

