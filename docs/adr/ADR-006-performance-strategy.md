# ADR-006: Performance Strategy

## Status: Proposed

## Context

The simulation engine runs a 150-day season in approximately 10-30 seconds on a modern laptop (Apple M2, Python 3.10). This is acceptable for batch scientific runs but completely unacceptable for interactive gameplay. ADR-004 requires season execution to feel instant — the player submits a plan and sees results within 1 second. ADR-005 sets an API response time budget of < 1s for the `/advance` endpoint. ADR-002 envisions up to 50 fields per game, multiplying the per-season cost.

Profiling shows the hot paths are:

1. **Water model** (`CascadingBucketWaterModel`): layer-by-layer loop over 10-20 soil layers per day, 150 days. ~40% of runtime.
2. **Nitrogen cycle** (`NitrogenCycle`): mineralization, nitrification, denitrification, leaching across layers. ~25% of runtime.
3. **SOM decomposition** (`SOMRuntime`): multi-pool organic matter turnover per layer. ~15% of runtime.
4. **Phosphorus cycle, ET, phenology, roots:** remaining ~20%, individually small.

All hot paths share the same pattern: nested loops over `(days x layers)` with arithmetic on floats. This is the worst case for CPython and the best case for vectorization or compiled code.

## Decision

**Phased optimization: numpy vectorization first, Rust via PyO3 second, lookup tables third.**

### Phase 1: Numpy Vectorization (target: 3-5x speedup, ~3-6s per season)

- Replace layer-by-layer Python loops in water, nitrogen, and SOM modules with numpy array operations.
- Soil state becomes `np.ndarray` (shape: `n_layers`) instead of `list[float]`. Daily drivers become arrays.
- Where day-over-day dependencies prevent full vectorization (e.g., water cascading from layer 0 to layer N), use `numpy` for the per-layer arithmetic but keep the layer loop in Python.
- This is a refactor of internals only. Public APIs (`step_day()`, module constructors, state dataclasses) do not change. State dataclasses gain `to_array()` / `from_array()` convenience methods.
- Estimated effort: 2-3 weeks. Low risk — numpy is already a dependency.

### Phase 2: Rust Inner Loops via PyO3 (target: 10-50x speedup, < 1s per season)

- Identify the remaining hot inner loops after Phase 1 (likely: water cascade, SOM pool interactions, N transformation chains).
- Rewrite these as Rust functions compiled into a Python extension module (`agrogame._core`) using PyO3 + maturin.
- Rust functions accept numpy arrays (via `numpy` crate or raw pointers) and return numpy arrays. No Rust-side allocation of Python objects.
- The Python orchestration layer (`SimulationOrchestrator`, `GameTurnManager`) remains pure Python. Only numerical kernels move to Rust.
- The Rust extension is optional at build time. If it is not available (e.g., development without Rust toolchain), the code falls back to the numpy implementation from Phase 1. Feature detection at import time:
  ```python
  try:
      from agrogame._core import water_cascade_rust as water_cascade
  except ImportError:
      from agrogame.soil.water._numpy import water_cascade_numpy as water_cascade
  ```
- Estimated effort: 4-6 weeks. Medium risk — introduces Rust toolchain to CI, but PyO3/maturin are mature.

### Phase 3: Pre-computed Lookup Tables (target: near-instant for common scenarios)

- For the most common crop x soil x climate combinations, pre-compute season results (yield curves, water balance, nutrient trajectories) and store as compressed numpy arrays or Parquet files.
- At runtime, if the player's scenario matches a pre-computed case within tolerance, interpolate from the lookup table instead of running the full simulation.
- This is a caching optimization, not a replacement. Novel scenarios still run the full engine.
- Estimated effort: 2-3 weeks. Low risk but limited applicability — useful only for "tutorial" or "quick play" modes where scenarios are constrained.

### Performance Budget

| Scenario | Phase 1 | Phase 2 | Phase 3 |
|---|---|---|---|
| 1 field, 1 season (150 days) | 3-6s | 0.3-1.0s | < 0.1s |
| 50 fields, 1 season | 150-300s | 15-50s | < 5s |
| 50 fields, 1 season (parallel) | 30-60s | 3-10s | < 1s |

Phase 2 with multiprocessing (one field per core) meets the < 1s single-field target and keeps 50-field turns under 10s. Phase 3 brings common cases to near-instant.

## Consequences

**Positive:**
- Phased approach delivers incremental value. Phase 1 alone makes development-time iteration faster. Phase 2 is the gameplay enabler. Phase 3 is polish.
- Python stays as the orchestration and game logic layer — rapid iteration, easy debugging, readable code.
- Rust extension is optional, so contributors without Rust can still develop and test (at slower speed).
- Numpy vectorization improves code clarity in many cases (array operations are more declarative than explicit loops).
- The performance budget is conservative. Real gains are likely better than estimated.

**Negative:**
- Phase 1 requires touching every numerical module's internals. High test coverage is essential to avoid regression. Current test suite must be the safety net.
- Phase 2 introduces Rust as a build dependency. CI must build wheels for Linux, macOS (x86 + ARM), and Windows. Maturin handles this, but it adds pipeline complexity.
- Numpy array state is less debuggable than named fields on dataclasses. We mitigate this by keeping dataclass APIs and adding `__repr__` methods that show meaningful values.
- Lookup tables (Phase 3) create a maintenance burden: they must be regenerated when model parameters change. Stale tables produce incorrect results silently.
- The optional Rust fallback means two code paths for critical numerical code. Both must be tested. Property-based tests (Hypothesis) comparing outputs of both paths will be mandatory.

## Alternatives Considered

**Cython.** Rejected. Cython provides 2-5x speedup over CPython for numerical code, which is insufficient to reach < 1s. It requires `.pyx` files with type annotations that are neither Python nor C, complicating maintenance. Cython's build tooling is more fragile than maturin's. If we are going to introduce a compiled language, Rust offers dramatically better performance and safety guarantees.

**Full Rust rewrite.** Rejected. The simulation engine is 15k+ lines of validated agronomic models with extensive test coverage. Rewriting loses that validation, introduces translation bugs, and removes the ability to rapidly iterate on model science in Python. The hybrid approach (Python orchestration + Rust kernels) captures 90% of the performance benefit at 20% of the rewrite cost.

**GPU acceleration (CUDA/OpenCL via CuPy or JAX).** Rejected. The problem size is small (~20 layers x 150 days x 50 fields). GPU kernel launch overhead dominates at this scale. GPU adds hardware requirements that exclude most players. The complexity is unjustified.

**PyPy.** Rejected. PyPy's numpy support is incomplete (via `numpy` compatibility layer that is slower than CPython + numpy for array operations). Extension module compatibility (PyO3, C extensions) is poor. It would block Phase 2 entirely.

**Numba JIT.** Considered as an alternative to Phase 2. Numba can JIT-compile numpy-style code to LLVM with `@njit` decorators, achieving 10-100x speedups. Advantages: no new language, no build toolchain. Disadvantages: Numba's supported Python subset is restrictive (no classes, no dicts, limited string handling), cold-start compilation adds 2-5s on first call, and Numba is a heavy dependency (~200MB). If Phase 2 Rust proves too costly, Numba is the fallback plan. But Rust is preferred for its predictable performance, zero cold-start, and smaller binary size.
