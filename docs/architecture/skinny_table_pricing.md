# Skinny Table & Basis Extraction Architecture

## 1. Motivation
Pricing a portfolio of 100,000+ swaps across millions of scenarios requires massive parallelization. Simply unrolling a unique expression tree for every trade is too memory-intensive for distributed SQL engines.

The **Skinny Table** architecture (or "Advanced Basis Extraction") solves this by decoupling the trade definition from the scenario valuation.

## 2. Advanced Basis Extraction (`BasisExtractor`)
Instead of treating a swap as a unique black box, we decompose its `npv()` expression into a sum of **Basis Functions**.

### The Extraction Process:
1. **Trace**: The `npv()` of an instrument is traced into a symbolic DAG.
2. **Decompose**: The `BasisExtractor` recursively breaks the DAG into additive components.
3. **Fingerprint**: Each non-additive component is fingerprinted by its mathematical structure (e.g. `(p1 + X1)**-p2`).
4. **Parameterize**: Variables (pillars) are mapped to `X_i` and constants to `p_i`.

**Result**: A swap is reduced to a set of rows:
- `Swap_Id`, `Basis_Type_Id`, `Variables`, `Parameters`, `Weight`.

## 3. The Skinny Table Join
In a high-performance engine (like `SkinnyEngineNumPy` or `SQLEngineDuckDB`), we perform a many-to-many join:
1. **Scenarios**: `(Scenario_Id, Pillar, Rate)`
2. **Swaps**: `(Swap_Id, Pillar, Weight, Basis_Type)`

The price is calculated by evaluating the basis function for each `Scenario x Swap` combination:
```sql
SELECT 
  Scenario_Id, 
  Swap_Id, 
  SUM(Weight * EvaluateBasis(Basis_Type, Pillar_Rates, Params))
FROM Swaps JOIN Scenarios ON ...
GROUP BY Scenario_Id, Swap_Id
```

## 4. Execution Engines (`pricing/engines/`)

We provide multiple strategies for executing this architecture:

### `SkinnyEngineNumPy`
- Evaluates the Basis Functions using vectorized NumPy arrays.
- Ideal for medium-scale portfolios (10k-50k swaps) on a single workstation.

### `SQLEngineCTE` / `SkinnyEngineDuckDB`
- Projects the Basis Functions into optimized SQL Common Table Expressions (CTEs).
- Offloads evaluation to high-performance OLAP engines like DuckDB or Deephaven.

## 5. Unified Risk Support
The Skinny Engines natively support both Analytic and Numerical risk:
- **Analytic**: Extracts basis functions for the *Jacobian* expressions (`∂NPV/∂r`).
- **Numerical**: Extractions components with `Const` weights representing the bumped results.

## 6. Performance & Scalability
- **O(1) Compilation**: The number of unique Basis Functions is determined by the *product variety*, not the *portfolio size*.
- **Payload Compression**: Transmitting weights and knot-ids is significantly smaller than transmitting unique expression trees.
- **Througput**: Verified at **13M+ atomic evaluations per second** using DuckDB on standard hardware.
