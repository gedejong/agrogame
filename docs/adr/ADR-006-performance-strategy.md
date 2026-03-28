# ADR-006: Performance Strategy

## Status: Proposed

## Context

The simulation engine runs a 150-day season in approximately 1-2 seconds on a modern laptop (Apple M2, Python 3.10). This is marginally acceptable for interactive gameplay but leaves no headroom for multi-field scenarios. ADR-004 requires season execution to feel instant — the player submits a plan and sees results within 1 second. ADR-005 sets an API response time budget of < 1s for the `/advance` endpoint. ADR-002 envisions up to 50 fields per game, multiplying the per-season cost.

Profiling shows the hot paths are:

1. **Water model** (`CascadingBucketWaterModel`): layer-by-layer loop over 10-20 soil layers per day, 150 days. ~40% of runtime.
2. **Nitrogen cycle** (`NitrogenCycle`): mineralization, nitrification, denitrification, leaching across layers. ~25% of runtime.
3. **SOM decomposition** (`SOMRuntime`): multi-pool organic matter turnover per layer. ~15% of runtime.
4. **Phosphorus cycle, ET, phenology, roots:** remaining ~20%, individually small.

All hot paths share the same pattern: nested loops over `(days x layers)` with arithmetic on floats. This is the worst case for CPython and the best case for vectorization or compiled code.

## Decision

**Phased optimization: NumPy vectorization first, Numba JIT second, Cython fallback third, lookup tables fourth. All phases remain within the Python ecosystem.**

### Phase 1: NumPy Vectorization (target: 2-5x speedup)

- Replace layer-by-layer Python loops in water, nitrogen, and SOM modules with numpy array operations.
- Soil state becomes `np.ndarray` (shape: `n_layers`) instead of `list[float]`. Daily drivers become arrays.
- Where day-over-day dependencies prevent full vectorization (e.g., water cascading from layer 0 to layer N), use `numpy` for the per-layer arithmetic but keep the layer loop in Python.
- This is a refactor of internals only. Public APIs (`step_day()`, module constructors, state dataclasses) do not change. State dataclasses gain `to_array()` / `from_array()` convenience methods.
- Estimated effort: 2-3 weeks. Low risk — numpy is already a dependency.
- Given the current ~1-2s baseline, NumPy vectorization alone may bring single-field execution comfortably under 1s, potentially making later phases unnecessary for single-field gameplay.

### Phase 2: Numba JIT for Hot Inner Loops (target: 10-50x speedup over CPython, near-C performance)

- Identify the remaining hot inner loops after Phase 1 (likely: water cascade, SOM pool interactions, N transformation chains).
- Apply `@numba.njit` (no-Python mode) decorators to these functions. Numba compiles them to native machine code via LLVM, achieving near-C performance with zero new language.
- Functions decorated with `@numba.njit` must use the Numba-compatible subset of Python/NumPy (no classes, no dicts, no string manipulation — but the hot loops are pure float arithmetic on arrays, which is Numba's sweet spot).
- Graceful fallback: Numba is an optional dependency. If not installed, the code falls back to the NumPy implementation from Phase 1:
  ```python
  try:
      from numba import njit
  except ImportError:
      def njit(*args, **kwargs):
          def decorator(func):
              return func
          return decorator if args and callable(args[0]) is False else decorator(args[0]) if args else decorator
  ```
- Cold-start compilation adds 1-3s on first invocation per function. Mitigated by Numba's ahead-of-time caching (`cache=True`) — subsequent runs start instantly.
- Estimated effort: 2-3 weeks. Low risk — no new language, no build toolchain changes.

### Phase 3: Cython Fallback (only if Numba cannot handle specific patterns)

- If specific hot loops use Python patterns that Numba's `njit` mode cannot compile (e.g., complex branching, callback functions), rewrite those functions as Cython `.pyx` modules.
- This is a targeted fallback, not a wholesale approach. Cython provides 5-20x speedups for typed loops and integrates with NumPy arrays via typed memoryviews.
- Estimated effort: 1-2 weeks per module. Medium risk — introduces `.pyx` build step.

### Phase 4: Pre-computed Lookup Tables (target: near-instant for common scenarios)

- For the most common crop x soil x climate combinations, pre-compute season results (yield curves, water balance, nutrient trajectories) and store as compressed numpy arrays or Parquet files.
- At runtime, if the player's scenario matches a pre-computed case within tolerance, interpolate from the lookup table instead of running the full simulation.
- This is a caching optimization, not a replacement. Novel scenarios still run the full engine.
- Note: crop presets currently include wheat (winter and spring) and maize. Future crops (potato, barley, etc.) will be added as presets are validated.
- Estimated effort: 2-3 weeks. Low risk but limited applicability — useful only for "tutorial" or "quick play" modes where scenarios are constrained.

### Performance Budget

| Scenario | Phase 1 (NumPy) | Phase 2 (Numba) | Phase 4 (LUT) |
|---|---|---|---|
| 1 field, 1 season (150 days) | 0.3-1.0s | 0.05-0.2s | < 0.05s |
| 50 fields, 1 season | 15-50s | 2.5-10s | < 2.5s |
| 50 fields, 1 season (parallel) | 3-10s | 0.5-2s | < 0.5s |

Phase 1 alone likely meets the < 1s single-field target. Phase 2 provides headroom for multi-field scenarios and future model complexity. Phase 4 brings common cases to near-instant.

## Consequences

**Positive:**
- Phased approach delivers incremental value. Phase 1 alone makes single-field gameplay responsive. Phase 2 is the multi-field enabler. Phase 4 is polish.
- The entire optimization stack stays within the Python ecosystem. No new languages, no new build toolchains, no cross-language debugging pain.
- Numba's `@njit` decorator is minimally invasive — the decorated function remains readable Python. Fallback to plain NumPy is automatic when Numba is not installed.
- Contributors need only Python skills. No Rust toolchain, no C compiler (unless Phase 3 Cython is triggered).
- Python orchestration and game logic layer is preserved — rapid iteration, easy debugging, readable code.
- NumPy vectorization improves code clarity in many cases (array operations are more declarative than explicit loops).
- CI/CD remains simple: pure Python wheels, no cross-compilation matrix, no maturin/PyO3 version pinning.

**Negative:**
- Phase 1 requires touching every numerical module's internals. High test coverage is essential to avoid regression. Current test suite must be the safety net.
- Numba is a substantial dependency (~150-200MB) and pins LLVM versions. It can conflict with other LLVM-using libraries. This is acceptable for a game application but would be problematic for a library.
- Numba's cold-start compilation (1-3s per function on first call) is noticeable. `cache=True` mitigates this for subsequent runs, but the first launch after install or cache invalidation is slower.
- Numba's supported Python subset is restrictive. Hot-loop functions must be written in a "Numba-friendly" style (no Python objects, no dynamic dispatch). This constrains how those functions are structured.
- NumPy array state is less debuggable than named fields on dataclasses. We mitigate this by keeping dataclass APIs and adding `__repr__` methods that show meaningful values.
- Lookup tables (Phase 4) create a maintenance burden: they must be regenerated when model parameters change. Stale tables produce incorrect results silently.

## Alternatives Considered

**Rust inner loops via PyO3.** Rejected. While Rust offers excellent performance and memory safety, it introduces a second language and toolchain to the project. PyO3 version pinning and cross-platform wheel building (maturin) adds significant CI/CD complexity. Cross-boundary debugging (Python calling Rust) is painful — stack traces are opaque, breakpoints do not cross the boundary. Numba achieves comparable performance for our use case (float arithmetic on arrays) without any of these costs. The maintenance bottleneck of requiring Rust expertise for a Python-first team is not justified.

**Full Rust rewrite.** Rejected. The simulation engine is 15k+ lines of validated agronomic models with extensive test coverage. Rewriting loses that validation, introduces translation bugs, and removes the ability to rapidly iterate on model science in Python. The cost is not justified when Python-native tools can meet performance targets.

**Cython as primary Phase 2.** Rejected as primary strategy (retained as Phase 3 fallback). Cython requires `.pyx` files with type annotations that are neither Python nor C, complicating maintenance. Its build tooling is more fragile than Numba's decorator-based approach. For pure float-array inner loops, Numba provides equal or better performance with less code overhead.

**GPU acceleration (CUDA/OpenCL via CuPy or JAX).** Rejected. The problem size is small (~20 layers x 150 days x 50 fields). GPU kernel launch overhead dominates at this scale. GPU adds hardware requirements that exclude most players. The complexity is unjustified.

**PyPy.** Rejected. PyPy's numpy support is incomplete (via compatibility layer that is slower than CPython + numpy for array operations). Extension module compatibility is poor. It would block Numba and Cython entirely.
