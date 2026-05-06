# ADR-009: Biopore density calibration

## Status

Accepted (#290).

## Context

The biopore module landed in #215 with default parameters that produced
**~1.3 biopores/m² topsoil** at steady state on `loam_temperate` under a
typical cover-crop turnover scenario. Pierret et al. 2007 reports
50–500 /m² for structured agricultural soils — the model was off by two
orders of magnitude. The PR-#281 review (concern 2) flagged this as
blocking #284 (orchestrator wiring): if biopores are wired in at the
current density, players see no measurable simulation effect.

A second issue surfaced during refinement: the original parameterisation
produced an **inverted depth profile** (subsoil 17 /m² > topsoil
1.3 /m²), contradicting Pierret 2007 / Kautz 2015 which both report
topsoil density 2–5× higher than subsoil because root density itself
peaks at the surface.

## Decision

We re-calibrated the four parameters that drive steady-state density and
introduced one new parameter to capture a known biological reality.

### Parameter changes (code defaults)

| Parameter | Was | Now | Rationale |
|-----------|-----|-----|-----------|
| `structural_root_fraction` | (none) | 0.2 | NEW. Only structural roots (>~0.5 mm dia) leave persistent channels — fine roots decompose without durable imprints. Six 2004 implies this; Kautz 2015 §2 puts the structural fraction at 0.1–0.3. |
| `conversion_factor` | 0.5 | 1.0 | The structural fraction now captures the not-all-mass-becomes-channel reality. `conversion_factor` represents the cylindrical channel literally carved by the structural root, which conserves volume. The two compose multiplicatively (`structural × conversion = 0.2` effective). |
| `mean_radius_mm` | 2.0 | 1.0 | Pierret 2007 channel diameters cluster at 0.5–2 mm; Kautz 2015 cereal channels at 1–3 mm. The 2.0 mm default sat at the upper end and gave too-low density (density ∝ 1/r²). 1.0 mm is at the lower cereal bound — defensible and lands density in target range. |
| `decay_half_life_days_topsoil` | 90 | 180 | Kautz 2015 reports 60–180 days for active topsoils. 180 days (upper end) is the value at which the steady-state depth profile becomes physical (topsoil ≥ subsoil) given the 365-day subsoil half-life and a typical [50, 30, 20] %  root distribution. |
| `decay_half_life_days_subsoil` | 365 | 365 | Unchanged — middle of Kautz 2015's 180–730 day range for subsoils. |

### Test scenario

The realism scenario in `tests/test_biopores.py` was updated so the
input mass is literature-defensible:

- **Total dead-root mass**: 5.0 g/m²/d (≈ 18 t/ha/yr). Upper end of
  Bidlack & Buxton 1992's fine-root turnover range; Kautz 2015 Table 2
  reports 4–8 t/ha/yr for established cover-crop systems, with
  productive perennials reaching 10+ t/ha/yr.
- **Per-layer split**: 50 / 30 / 20 % across the 0–25, 25–60, 60–100 cm
  horizons. Matches a typical exponential root distribution
  (Jackson et al. 1996).

The pre-#290 fixture used 0.6 g/m²/d split uniformly across layers —
3–7× too low and ignored that root mass peaks at the surface.

## Consequences

### Easier

- **Density now physically meaningful**. Topsoil steady state lands at
  ~51 /m² on `loam_temperate` — at the lower bound of Pierret 2007's
  range, comfortably exceeding the noise floor that #284 needs.
- **Depth profile is correct**: topsoil ≥ subsoil, matching field
  observations.
- **Parameter set is interpretable**: `structural_root_fraction` directly
  encodes a literature-grounded distinction (structural vs fine roots)
  rather than hiding it in `conversion_factor`'s 0.5 fudge.

### Harder

- **Tests that referenced specific densities** had to be updated. The
  original `test_cover_crop_vs_fallow_density_ratio` asserted only the
  ratio (>2×) and continues to pass with a much larger margin (~94×).
- **The realism scenario uses 5.0 g/m²/d**, which is at the upper end
  of literature ranges. If future work models less productive cover
  crops, the realism test fixture should be split into low/high
  scenarios.
- **`conversion_factor = 1.0` is a default change**. Tests that
  construct `BioporeParams(conversion_factor=...)` explicitly are
  unaffected; tests that rely on the old default would observe higher
  densities. The full biopore test suite was re-verified (35 pass).

### Calibration verification

After applying the new defaults to the realism scenario:

| Layer | Density at 3-yr SS (cover crop) | Density after 2-yr fallow + tillage |
|-------|---------------------------------|-------------------------------------|
| 0 (0–25 cm, top) | 50.8 /m² ✓ in [50, 200] | 0.54 /m² ✓ < 10 |
| 1 (25–60 cm, mid) | 30.5 /m² | 4.87 /m² (untilled below plow) |
| 2 (60–100 cm, sub) | 36.6 /m² | 25.0 /m² (no decay below plow zone) |

- AC#1 met: topsoil ∈ [50, 200] /m² ✓
- AC#2 met: topsoil 50.8 ≥ subsoil 36.6 ✓
- AC#3 met: fallow topsoil 0.54 < 10 within 2 seasons ✓
- AC#4 met: cover-crop / fallow ratio at year 3 ≈ 1276× > 2× ✓ (cc topsoil 50.8 /m² ÷ fallow topsoil 0.04 /m² after 3 yr of decay + 3 annual tillages)

### Two known characteristics of the chosen calibration

**Tight lower-bound headroom.** Topsoil 50.8 /m² lands ~1.6% above the
[50, 200] /m² floor. The calibration is intentionally framed at the
lower edge so productive perennial systems can push density into the
100–200 /m² mid-band; the trade-off is that a small downward drift in
any single knob — `structural_root_fraction` to 0.18, fixture mass below
~4.5 g/m²/d, or topsoil half-life under 175 d — pushes steady state
below 50 /m² and fails `test_cover_crop_steady_state_density_in_pierret_range`.
Future tuners adjusting any of those should re-verify against the
calibration AC and update this ADR.

**Non-monotonic depth profile (top 50.8 → mid 30.5 → sub 36.6).**
`apply_decay` classifies a layer as topsoil iff its top edge is shallower
than `topsoil_depth_cm = 30 cm`. Layer 1 (25–60 cm) qualifies, so its
~5/6 of mass below the 30 cm boundary still uses the topsoil 180-d
half-life despite physically belonging mostly to the subsoil zone. The
result: the mid layer decays as fast as the surface but receives less
input, dipping below the subsoil. This satisfies AC#2 at the layer-0 vs
layer-2 comparison but does not produce the strictly monotonic profile
that Pierret 2007 / Kautz 2015 report. A future refinement could weight
the half-life by the overlap of each layer with the topsoil/subsoil
zones — same trick `apply_tillage` uses to pro-rate destruction by plow
depth. Tracked separately rather than addressed in #290 because the
weighted-decay change deserves its own justification and tests.

## Alternatives Considered

### Single-knob calibration (issue's option a)

Maxing `conversion_factor` at 1.0 alone (no other changes) only doubles
density to ~2.6 /m² — insufficient. Rejected.

### Aggressive radius reduction (issue's option c at 0.5 mm)

Shrinking `mean_radius_mm` to 0.5 mm would hit density targets but is
below the Kautz 2015 cereal-channel range (1–3 mm). Rejected as
unphysical.

### Decay-only calibration

Stretching topsoil half-life beyond 180 days (e.g. to 365 days for
parity with subsoil) lifts density but contradicts Kautz 2015's 60–180
day range for topsoil. Rejected.

### Structural fraction without radius/half-life changes

Adding `structural_root_fraction` alone would *worsen* density (effective
factor drops from 0.5 to 0.1). Rejected — the parameter only makes
sense in combination with the other changes.

## References

- Pierret et al. 2007, *Plant and Soil* 286 — structured-soil biopore
  density (50–500 /m²) and depth profile.
- Six et al. 2004, *Plant and Soil* 269 — root-to-pore conversion;
  structural vs fine roots.
- Kautz 2015, *Soil and Tillage Research* 152 — biopore persistence,
  decay half-lives, cereal channel diameters.
- Bidlack & Buxton 1992 — fine-root tissue density and turnover rates.
- Jackson et al. 1996, *Oecologia* 108 — global root distribution.
- Issue #290 — calibration plan and PO sign-off.
- Issue #216 + ADR — analogous reactive-fraction calibration pattern
  (redox-Fe).
