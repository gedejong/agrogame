Canopy Rainfall Interception

Overview
- Interception capacity: `C = c_cap * LAI` (mm), default `c_cap=0.2 mm/LAI`.
- Daily sequence:
  1. Intercept rainfall up to remaining capacity → `intercepted`, remainder is `throughfall` to soil.
  2. Evaporate from the canopy store first (bounded by store and potential evaporation).
  3. Pass reduced potential evaporation to soil evaporation.

Events
- `CanopyIntercepted(amount_mm)` emitted when rainfall is stored on the canopy.
- `CanopyEvaporated(amount_mm)` emitted when canopy store evaporates.

Implementation
- `agrogame/soil/canopy/interception.py` provides `InterceptionState` with `intercept()` and `evaporate()`.
- Integrated in legacy `SoilWaterBalance` for day-level orchestration; scripts also demonstrate usage.

Notes
- Water balance: `rain = intercepted + throughfall + runoff + deep + ΔS`, with canopy evaporation included in total evaporation accounting.
- Parameters are intentionally simple; future work can add crop-specific coefficients.

