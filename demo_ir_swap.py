#!/usr/bin/env python3
"""
IRS Stabilized Reactive Dashboard - FINAL
==========================================
"""

import asyncio, json, logging, os, sys, threading, time
from collections import defaultdict

sys.path.insert(0, os.path.dirname(__file__))

# 1. Init Deephaven JVM
from streaming.admin import StreamingServer
streaming = StreamingServer(port=10000)
streaming.start()
streaming.register_alias("demo")

print("=" * 70)
print("  Interest Rate Swap — Stabilized Ticking Demo")
print("=" * 70)

# Import dependencies after JVM is ready
from streaming import agg, flush, get_tables
from streaming.table import snapshot
from marketdata.admin import MarketDataServer

from pricing.marketmodels.ir_curve_integrated_rate import IntegratedRatePoint, IntegratedShortRateCurve
from pricing.marketmodels.ir_curve_fitter import CurveFitter
from pricing.marketmodels.symbols import fit_symbol
from pricing.marketmodels.ir_curve_swap import SwapQuote, SwapQuoteRisk
from pricing.instruments.ir_swap_fixed_float import IRSwapFixedFloat
from reactive.evaluation import eval_cached

# 2. Setup Assets
print("  Building objects...")
swap_quotes = {
    "IR_USD_OIS_QUOTE.1Y":  SwapQuote(symbol="IR_USD_OIS_QUOTE.1Y",  tenor=1.0,  rate=0.02),
    "IR_USD_OIS_QUOTE.5Y":  SwapQuote(symbol="IR_USD_OIS_QUOTE.5Y",  tenor=5.0,  rate=0.03),
    "IR_USD_OIS_QUOTE.10Y": SwapQuote(symbol="IR_USD_OIS_QUOTE.10Y", tenor=10.0, rate=0.05),
    "IR_USD_OIS_QUOTE.20Y": SwapQuote(symbol="IR_USD_OIS_QUOTE.20Y", tenor=20.0, rate=0.06),
}
swap_quotes_risk = {}
for sym in swap_quotes:
    r = SwapQuoteRisk(symbol=sym, risk=0.0, equiv_notional=0.0)
    r.tick() # Force row creation in DH
    swap_quotes_risk[sym] = r

from pricing.marketmodels.ir_curve_yield import LinearTermDiscountCurve, YieldCurvePoint

USE_LINEAR_CURVE = True

curve_points = {}
if USE_LINEAR_CURVE:
    for q_sym, q in swap_quotes.items():
        label = fit_symbol("USD", q_sym.split(".")[-1])
        curve_points[label] = YieldCurvePoint(name=label, symbol=label, tenor_years=q.tenor, currency="USD", quote_ref=q)
    usd_curve = LinearTermDiscountCurve(name="USD-OIS", currency="USD", points=list(curve_points.values()))
else:
    for q_sym, q in swap_quotes.items():
        label = fit_symbol("USD", q_sym.split(".")[-1])
        curve_points[label] = IntegratedRatePoint(name=label, symbol=label, tenor_years=q.tenor, currency="USD", quote_ref=q)
    usd_curve = IntegratedShortRateCurve(name="USD-OIS", currency="USD", points=list(curve_points.values()), is_local=True)


swaps = {
    "BENCH-1Y":  IRSwapFixedFloat(symbol="BENCH-1Y", currency="USD", notional=100_000_000, fixed_rate=0.02, tenor_years=1.0, discount_curve=usd_curve, projection_curve=usd_curve),
    "BENCH-5Y":  IRSwapFixedFloat(symbol="BENCH-5Y", currency="USD", notional=100_000_000, fixed_rate=0.03, tenor_years=5.0, discount_curve=usd_curve, projection_curve=usd_curve),
    "BENCH-10Y": IRSwapFixedFloat(symbol="BENCH-10Y", currency="USD", notional=100_000_000, fixed_rate=0.05, tenor_years=10.0, discount_curve=usd_curve, projection_curve=usd_curve),
    "BENCH-20Y": IRSwapFixedFloat(symbol="BENCH-20Y", currency="USD", notional=100_000_000, fixed_rate=0.06, tenor_years=20.0, discount_curve=usd_curve, projection_curve=usd_curve),
    "USD-7Y":    IRSwapFixedFloat(symbol="USD-7Y", currency="USD", notional=100_000_000, fixed_rate=0.04, tenor_years=7.0, discount_curve=usd_curve, projection_curve=usd_curve)
}

bench_swaps = [swaps[k] for k in ["BENCH-1Y", "BENCH-5Y", "BENCH-10Y", "BENCH-20Y"]]
for s in bench_swaps:
    s._static_pay_tenors = [float(t) for t in s.target_dates()]
    s._static_taus = [s._static_pay_tenors[i] - (0.0 if i==0 else s._static_pay_tenors[i-1]) for i in range(len(s._static_pay_tenors))]

fitter = CurveFitter(name="USD_OIS_FITTER", currency="USD", target_swaps=bench_swaps, quotes=list(swap_quotes.values()), curve=usd_curve, points=list(curve_points.values()))

print("  Initial fit...")
fitter.solve()
flush()

# 3. Tables
tables = get_tables()
tables["swap_summary"] = IRSwapFixedFloat._ticking_live.agg_by([agg.sum(["TotalNPV=npv", "TotalDV01=dv01"])], by=[])
tables["swap_risk_ladder"] = SwapQuoteRisk._ticking_live
tables["interest_rate_swap_live"] = IRSwapFixedFloat._ticking_live

for name, tbl in tables.items(): tbl.publish(name)

# 4. Market Data Thread
_md_server = MarketDataServer(port=8000)
asyncio.run(_md_server.start())

async def _consume():
    import websockets
    async with websockets.connect("ws://localhost:8000/md/subscribe") as ws:
        await ws.send(json.dumps({"types": ["swap"]}))
        async for msg in ws:
            tick = json.loads(msg)
            sq = swap_quotes.get(tick.get("symbol"))
            if sq: sq.batch_update(rate=tick["rate"])

def main():
    from deephaven.execution_context import get_exec_ctx
    threading.Thread(target=lambda ctx: (ctx.__enter__(), asyncio.new_event_loop().run_until_complete(_consume()))[1], args=(get_exec_ctx(),), daemon=True).start()

    print("\n  DEMO READY! Ticking IRS Grid. Web UI: http://localhost:10000\n")
    tick_count = 0
    try:
        while True:
            time.sleep(2.0)
            
            # Aggregate Risk over FULL portfolio
            bucketed_risk = defaultdict(float)
            jacobian = getattr(fitter, "latest_jacobian", [])
            
            total_p_risk = defaultdict(float)
            # The demo is restricted to just the USD-7Y swap to cleanly show isolated risk
            portfolio_swaps = [swaps["USD-7Y"]]
            for swap in portfolio_swaps:
                p_risk = swap.pillar_risk
                p_ctx = swap.pillar_context()
                for pk, pv_expr in p_risk.items():
                    total_p_risk[pk] += float(eval_cached(pv_expr, p_ctx))
            
            for entry in jacobian:
                # Correctly map the jacobian entry back to its generic pillar name
                pillar_name = entry.symbol.split("_SENS")[0]
                if pillar_name in total_p_risk:
                    pv = total_p_risk[pillar_name]
                    # pv is ∂NPV / ∂R_i (dollar change per 100% pillar move)
                    # entry.value is ∂R_i / ∂Q_j
                    # so pv * entry.value is ∂NPV / ∂Q_j.
                    bucketed_risk[entry.quote_symbol] += pv * entry.value
            
            if tick_count == 1:
                print(f"  [DEBUG] PV risk vector: {dict(total_p_risk)}")
                print(f"  [DEBUG] Jacobian Entry 0: {jacobian[0].symbol if jacobian else 'None'} | value: {jacobian[0].value if jacobian else 'None'}")
                print(f"  [DEBUG] type(swap.npv): {type(portfolio_swaps[0].npv)}")

            # Push to DH
            for q_sym, risk_val in bucketed_risk.items():
                risk_obj = swap_quotes_risk[q_sym]
                t_val = float(q_sym.split(".")[-1][:-1]) if "." in q_sym else 1.0
                
                # risk_val is ∂NPV / ∂Quote (per 1.0 or 100% shift)
                # Convert to DV01 (per 1 bp or 0.0001 shift)
                dv01 = risk_val * 0.0001
                en = dv01 / (t_val * 0.0001) if t_val > 0 else 0.0
                
                risk_obj.batch_update(risk=float(dv01), equiv_notional=en)
            
            flush()
            time.sleep(0.5) # Allow DH to process updates

            # CLI Summary
            npv_df = snapshot(tables["interest_rate_swap_live"])
            risk_df = snapshot(tables["swap_risk_ladder"])
            current_npv = float(eval_cached(swaps['USD-7Y'].npv, swaps['USD-7Y'].pillar_context()))
            print(f"  [TICK #{tick_count}] USD-7Y NPV: {current_npv:,.2f}")
            
            print("\n  [Risk Ladder]")
            print(risk_df[['symbol', 'risk', 'equiv_notional']].to_string(index=False))
            
            if not npv_df.empty:
                print("\n  [Portfolio NPV]")
                print(npv_df[['symbol', 'npv', 'dv01']].to_string(index=False))
            
            print("-" * 60)
            sys.stdout.flush()
            tick_count += 1
            
    except KeyboardInterrupt:
        asyncio.run(_md_server.stop())

if __name__ == "__main__": main()
