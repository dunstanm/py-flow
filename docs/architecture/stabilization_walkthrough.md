# Walkthrough: Stabilizing the Reactive Pricing Engine and Benchmarks

We have successfully stabilized the reactive pricing engine and restored the performance of the benchmarking suite across all execution engines (Python, NumPy, DuckDB, and Deephaven). This work ensures the scalability and reliability of the platform for large-scale portfolios and complex curve models.

## 1. Key Accomplishments

### Reactive Engine Stabilization
- **Numerical Robustness**: Implemented safety guards for the power operator (`**`) in `reactive/evaluation.py` to prevent `OverflowError` during symbolic differentiation of high-order polynomials.
- **Instrument Property Alignment**: Standardized property access in `IRSwapFloatFloat` to resolve `TypeError` when accessing symbolic `Sum` expressions during tracing.
- **Basis Extraction Utility**: Updated the `BasisExtractor` to use `_PURE_FUNCS`, ensuring correct translation of mathematical primitives (exp, log, abs) into target-specific vector code.

### Benchmarking Suite Recovery (`scripts/benchmark_suite.py`)
- **NumPy Vectorization**: Refined the basis template compiler to automatically map bare and prefixed math functions to their NumPy equivalents.
- **Dynamic Variable Joins**: Extended the Deephaven script generation to support basis functions with an arbitrary number of variable dependencies ($X_1 \dots X_N$), critical for cubic spline models.
- **Schema Normalization**: Implemented dynamic null-handling and padding for missing variable columns in the component DataFrame, preventing `FormulaCompilationException` during joins.

### Infrastructure & Portability
- **Streaming Docker Integration**: Configured explicit volume mounts in `streaming/admin.py` to map host libraries to `/apps/libs` inside the container.
- **Portable Data Paths**: Synchronized Parquet file loading between the host and container by detecting the execution environment (Docker vs. In-Process) and adjusting paths accordingly.
- **Cross-Platform Support**: Enabled `FORCE_DOCKER_STREAMING=1` to allow remote code path testing on non-ARM environments (x86), avoiding interpreter deadlocks in Shared JPY mode.

## 2. Benchmark Summary (100 Swaps Mix)

Recent stabilization efforts enable successful execution across all engines with consistent results parity:

| Engine | Scenario: Global Mixed | Status | Notes |
| :--- | :--- | :--- | :--- |
| **Python Symbolic** | ~50ms (NPV) | ✅ Stable | Reliable for small-to-medium portfolios. |
| **NumPy Vectorized** | ~15ms (NPV) | ✅ Optimized | Highly scalable for desktop interactive use. |
| **DuckDB Skinny** | ~4.0s (NPV) | ✅ Functional | Higher overhead due to SQL compilation/IO. |
| **Deephaven** | ~70ms (NPV) | ✅ Restored | Powerful for real-time streaming updates. |

## 3. Verified Implementation

### Running the Full Benchmark
The benchmark suite is now the primary validation tool for engine changes:
```bash
# Force Docker mode for Deephaven and run 100 swaps
FORCE_DOCKER_STREAMING=1 NUM_SWAPS=100 uv run python scripts/benchmark_suite.py
```

### Technical Debt Resolved
- Eliminated `OverflowError` in symbolic differentiation.
- Resolved `TypeError` in `Sum` property calls.
- Fixed `FileNotFoundError` in the Deephaven remote path.
- Standardized variable naming for higher-order basis functions in the SQL/Vector registry.

> [!IMPORTANT]
> The engine and benchmarking suite are now stable. Future work will focus on optimizing the DuckDB execution path to reduce the fixed overhead for smaller portfolios.
