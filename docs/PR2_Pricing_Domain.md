# Stack 2: Pricing Domain Models

### The Problem
The codebase currently mixes market components (`marketmodel/`) and generic swap definitions (`instruments/`) directly in the root directory. PR #4 suggested pulling IR domain models into a dedicated `ir/` package containing models, graphs, and risk scenarios.

### The Solution: The `pricing/` Top-Level Namespace
Instead of locking the architecture to a single asset class (`ir/`), we establish a universal `pricing/` domain namespace. This structure incorporates the excellent scenario/risk design from PR #4 while giving our new `@traceable` instruments their dedicated home.

### Directory Structure:
We propose consolidating the scattered pricing logic into:
* **`pricing/instruments/`**: (e.g. `IRSwapFixedFloatApprox`, calendar conventions).
* **`pricing/marketmodels/`**: (e.g. `YieldCurvePoint`, `IntegratedShortRateCurve`).
* **`pricing/dates/`**: (Shared daycount fraction and holiday schedules).
* **`pricing/scenarios/`**: (Absorbs `ir/graph.py` from PR 4—factory logic for scenario creation).
* **`pricing/risk/`**: (Absorbs `ir/risk.py` from PR 4—bump-and-reprice metrics).

#### Why reviewers will like it:
* Validates and incorporates the structural feedback from PR #4.
* Scales gracefully beyond Interest Rates (e.g., preparing for Equities and FX).
* Modularizes the code perfectly for the solver engines introduced in subsequent PRs.
