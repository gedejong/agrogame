Canopy summary

- Interception: Beer–Lambert `fraction = 1 - exp(-k * LAI)`
- Biomass: `biomass = intercepted_PAR * RUE * temp_factor * min(water, N)`
- LAI: `ΔLAI = SLA * new_leaf_biomass * (1 - LAI/LAImax) - LAI * sen_rate`
- Phenology: higher senescence in grain fill
- Events: `LightIntercepted`, `BiomassAccumulated`, `LAIUpdated`

### Rainfall interception

Capacity per day: `C = capacity_coef_mm_per_lai * LAI` (mm). The canopy stores intercepted water up to remaining capacity; any excess becomes throughfall. During the daily ET step, canopy evaporation is prioritized before soil evaporation.

Sequencing in a day:

1) Interception: `(intercepted, throughfall) = intercept(LAI, rainfall)`
2) Soil water update with `throughfall` and evaporation driver set to 0
3) Potential ET split into evaporation/transpiration; canopy `evaporate(potential_evap)` reduces soil evaporation by the amount taken from the canopy store

Events:
- `CanopyIntercepted(amount_mm)` emitted when interception occurs
- `CanopyEvaporated(amount_mm)` emitted when canopy evaporation reduces the store


