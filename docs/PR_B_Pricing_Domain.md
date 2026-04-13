# PR-B : Pricing Domain Models

This is a large PR, but mostly new files, hopefully reducing sensitivity of the change. We build on the ideas in the original demo_ir_swap.py, making large updates to that and its documentation: 

**👉 Overview and Demonstration [IRS_DEMO.md](IRS_DEMO.md)**

We aim to introduce sufficient pricing complexity to test the compution engine concepts, not be accurate. We introduce and test evaluation options for: standard Python, compiled NumPy, SQL in DuckDb, expressions in Deephaven.

We use IR Swaps as an example pricing task that needs a calibration step, interpolation step, and pricing loops.  We describe these in more details in the following documents:

**👉 Payoffs [docs/architecture/instruments_swaps.md](docs/architecture/instruments_swaps.md)**
**👉 Curves [docs/architecture/marketmodel_curves.md](docs/architecture/marketmodel_curves.md)**
**👉 Maths & Engines [docs/architecture/basis_functions_skinny_table_pricing.md](docs/architecture/basis_functions_skinny_table_pricing.md)**
**👉 Scaling [docs/architecture/benchmarking_swaps.md](docs/architecture/benchmarking_swaps.md)**


### Code layout
Following feedback on PR-3:  the codebase currently has a demo_ir_swap that contains a swap instrument payoff, and a market data curve. We want to grow these features substantially. PR-3 proposed a split of curves to a market interpolation folder (`marketmodel/`) and tradables to another folder (`instruments/`), both directly in the root directory. PR #4 suggested pulling IR domain models into a dedicated `ir/` package containing models, graphs, and risk scenarios. 

This PR proposes a single cross asset `pricing/` folder at root level, then merges the ideas from PR-3 and PR-4 into it. We propose there is useful commonality between types of pricing functions across asset classes, so split by asset type only as a prefix not a folder. We extend with some date functions, and try a common base curve shared between ir_swap curves and eq_dividend curves.

* **`pricing/instruments/`**: (e.g. `IRSwapFixedFloatApprox`, calendar conventions).
* **`pricing/marketmodels/`**: (e.g. `YieldCurvePoint`, `IntegratedShortRateCurve`).
* **`pricing/dates/`**: (Shared daycount fraction and holiday schedules).
* **`pricing/scenarios/`**: (Absorbs `ir/graph.py` from PR 4—factory logic for scenario creation).
* **`pricing/risk/`**: (Absorbs `ir/risk.py` from PR 4—bump-and-reprice metrics).

### Sensitive Changes
We propse a change to the core store/registry.py to allow for richer types, for example optional parameters in swap instrument defintions. 

We seek a common naming convention for market data labels, used across market quotes and derived fitted quantities. We change existing FXTick to align, and introduce CurveTick and JacobianTick. We propose a change to the core MaketData publisher to be able to publish multiple ticks in a package. This helps ensure swap curve benchmark quote updates are delivered and fitted together.  


### Tesing
We provide demonstration tests at high level, and unit tests for instruments and curves. Demonstrations display results in Deephaven tables. To allow the curve fitting to complete in a live market data environment we add a is_target flag to break the update stream.  For unit tests we mock out ticking live feeds. We note that it is relatively hard to study curve fitting stability in such demos or unit tests. This motivates the next PR-C, where we propose a MarketSnapshot concept.  We propose Panel dashboards with live curve plots for demos, and ways to run the code with static explicit inputs from Marimo notebooks. 

We include a scripts/run_isolated_tests.sh to run tests as more indenependent steps to help make robust on smaller machines.  We make changes to merge some steps in existing tests, where they previously assume state preserved from one test to the next, to ensure all run at once. 

