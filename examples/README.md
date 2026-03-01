# Examples

Client scripts that connect to a running streaming server and create persona-specific views.

## Prerequisites

Start the trading server in a separate terminal:

```bash
python3 demo_trading.py
# Starts StreamingServer (port 10000) + MarketDataServer (port 8000)
# Publishes: prices_raw, prices_live, risk_raw, risk_live,
#            portfolio_summary, top_movers, volume_leaders
```

## Run a client

In another terminal:

```bash
python3 examples/quant_client.py    # watchlist + spread analysis
python3 examples/pm_client.py       # P&L snapshots + portfolio tracking
python3 examples/risk_client.py     # exposure monitoring + Greeks
```

Each client creates server-side derived tables visible to all other clients and the web IDE at http://localhost:10000.

## Options

```bash
python3 examples/pm_client.py --host localhost --port 10000
```
