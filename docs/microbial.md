### Microbial biomass and enzyme activity (scaffold)

This introduces initial scaffolding for a microbial biomass module with enzyme production events. It currently:

- Defines events `MicrobialGrowth`, `MicrobialMortality`, `EnzymeProduced`
- Adds `MicrobialBiomassModule` with simple environmental response modifiers
- Wires a `MicrobesRuntime` to run on the `nutrients` phase of the daily calendar

Planned next steps (AGRO-78 acceptance criteria):

- Separate bacterial/fungal pools and validated turnover ranges
- Michaelis–Menten kinetics for enzyme-mediated decomposition
- Temperature–moisture–pH response surfaces (AGRO-70)
- Coupling to SOM substrate supply and N cycling

See also: [events](mdc:docs/events.md), [nitrogen](mdc:docs/nitrogen.md), [water](mdc:docs/water.md)


