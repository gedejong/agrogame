# Architecture Overview

The engine advances on a daily timestep, coordinating soil water, nutrients, and crop modules via a simple orchestrator.

Water balance is provided by a small abstraction so different implementations can be swapped without changing call sites.
See [Water Model Abstraction](water_model_abstraction.md) for the `SoilWaterModel` interface and events.
