# Stack 3 & 4: Solvers and Analytics Dashboards

### Stack 3: Curve Fitter & Mathematical Solvers
With the domain models cleanly established in `pricing/` and the engine traceabilities in `reactive/`, this PR introduces the heavy quantitative lifting without polluting the architecture.

* **Contents**: `CurveFitter`, standard interpolation techniques (Quadratic, Cubic Local/Smooth).
* **Approach**: Exposes standalone math libraries that operate on pure static datasets (eliminating the complexity of deep market data ticking during testing).
* **Benefit**: Reviewers can validate the math logic and numerical boundaries independently of the reactive framework.

### Stack 4: Application & Analytics Dashboard
Reintroducing the UI and sandbox notebooks.

* **Contents**: `dashboard/apps/swap_curve.py`, Plotly analytics, and real-time streaming integrations.
* **Approach**: Links the stable pricing engines to the Deephaven Lakehouse backend mapping out live ticking metrics.
* **Benefit**: Because the underlying mathematical structure has been vetted in PR 1-3, this PR strictly functions as presentation logic, vastly shrinking review overhead.
