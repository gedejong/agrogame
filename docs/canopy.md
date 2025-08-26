Canopy summary

- Interception: Beer–Lambert `fraction = 1 - exp(-k * LAI)`
- Biomass: `biomass = intercepted_PAR * RUE * temp_factor * min(water, N)`
- LAI: `ΔLAI = SLA * new_leaf_biomass * (1 - LAI/LAImax) - LAI * sen_rate`
- Phenology: higher senescence in grain fill
- Events: `LightIntercepted`, `BiomassAccumulated`, `LAIUpdated`


