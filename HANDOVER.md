# py-flow Project Handover Notes

## 1. Current State of the Architecture
You are taking over the repository currently tracking on the `pr-B-focus` branch. The primary priority here is unblocking and scaling the analytical pricing engine benchmark suite.

### Recent Milestones Achieved:
* **Pricing Engine Scalability Benchmarks**: We've performed extensive benchmarking against varying swap portfolio volumes (micro: 10 swaps, institutional: 2,000+ swaps) measuring the exact crossover execution limits between Python-based object models and relational DuckDB/Deephaven batch executions. Log traces have been generated across `bench_10k.log` and `bench_2000.log`.
* **Risk Unification API**: The project now successfully unifies and stabilizes numerical risk and analytic frameworks into standardized `pricing/` domain `ExecutionEngine` implementations. Python, SQL, and Skinny engine calls are decoupled from the core `Portfolio` object.
* **Reactive Core & Fitter Smoothing**: On the time-series side, the short-rate curve fitters (`IntegratedShortRateCurve`) have received extensive thread-safe coefficient caching guards. This has drastically stabilized the frontend UI against market data streaming loops that previously overloaded CPU cycles on slower architectures.

## 2. Next Steps For the New Machine
1. Follow the exact procedure outlined in **`SETUP_ARM64.md`** to stand up your environment inside the WSL abstraction layer. Pay special attention to the `tonistiigi/binfmt` container execution needed to intercept x86 dependencies properly if native `aarch64` wheels are unpublished.
2. Initialize py-flow and immediately assert the execution engine benchmarks against the newer Snapdragon/ARM processor natively. Check `benchmark_output.txt` against prior metrics to measure pure hardware throughput compared between x64 VS Code Hosts and WSL ARM.
3. If tests start breaking down sequentially around PostgreSQL dependency timeouts (`pgserver`), refer directly to the Antigravity context protocols (or `ANTIGRAVITY_CONTEXT.md`) for shim details regarding `pixeltable_pgserver`.
