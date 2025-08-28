Evapotranspiration (ET)

Overview

- Methods: Priestley–Taylor (PT) and Penman–Monteith (PM, FAO-56 style)
- Partitioning: ET0 is split into potential evaporation and transpiration using Beer–Lambert canopy cover.
- VPD response: Transpiration is reduced under high vapour pressure deficit (VPD) to represent stomatal closure.

Key Equations

- PT: \(ET_0 = \alpha \cdot \frac{\Delta}{\Delta + \gamma} \cdot R_n / \lambda\)
- PM (daily): FAO-56 reference crop with aerodynamic and surface resistance (see code for constants and units).
- Saturation vapour pressure: \(e_s(T) = 0.6108 \cdot e^{\frac{17.27T}{T+237.3}}\) [kPa]
- VPD: \(VPD = e_s - e_a\), with \(e_a = e_s \cdot RH\)

Implementation Notes

- Constants (FAO-56): collected in `agrogame/weather/constants.py` with citations.
- VPD-aware partitioning: `Evapotranspiration.potential_components_with_vpd(et0_mm, lai, vpd_kpa)` scales potential transpiration by a stomatal factor:
  - `stomatal = max(0.2, 1 - vpd_sensitivity * max(0, VPD - vpd_ref))`
  - Parameters live in `agrogame/atmosphere/et/params.py`.
- PM pathway already uses VPD in the aerodynamic term via psychrometric scaling; the above partitioning additionally reduces canopy demand under high VPD.

Visualizations

- `scripts/plot_et_timeseries.py`: compares PT vs PM and overlays VPD (kPa) and the stomatal factor.
- `scripts/plot_full_integration.py`: overlays VPD and stomatal factor in the ET panel for integrated runs.

Acceptance Behaviours

- Higher VPD lowers potential (and typically actual) transpiration holding other drivers constant.
- Evaporation is unaffected by the stomatal factor; it responds to available energy and topsoil water.

References

- FAO-56: Allen, R. G., Pereira, L. S., Raes, D., & Smith, M. (1998). Crop evapotranspiration – Guidelines for computing crop water requirements.

