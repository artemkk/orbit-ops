"""Subsystem physical parameters.

Numbers reflect a SkySat-class small satellite (Planet Labs, ~100 kg,
sun-synchronous LEO). Where a value is published, we cite it. Where it
isn't, we use a defensible estimate and label it as such.

These are constants, not configuration — they describe the physics of
the bus, not runtime behavior. A different bus (e.g., York's S-class)
would have a different set of these.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EpsParams:
    """Electrical Power Subsystem parameters."""

    # Solar array
    array_area_m2: float = 1.2
    """Total solar array area (m^2). Estimate: SkySat-class deployable array."""

    array_efficiency: float = 0.15
    """End-to-end array efficiency (-). Lower than raw cell efficiency
    (~0.28 for triple-junction GaAs) because this includes orbit-averaged
    cosine losses, temperature derating, wiring, and packing factor.
    Source: typical smallsat system-level sizing value."""

    solar_flux_w_m2: float = 1361.0
    """Solar constant at 1 AU (W/m^2). IAU standard."""

    # Battery
    battery_capacity_wh: float = 150.0
    """Usable battery capacity (Wh). Estimate: SkySat-class Li-ion pack."""

    battery_min_soc: float = 0.20
    """Lower operational SoC limit. Below this, loads would shed in real ops."""

    battery_max_soc: float = 1.00
    """Upper SoC limit. Charge controller prevents overcharge."""

    initial_soc: float = 0.85
    """SoC at sim start."""

    # Bus load
    bus_load_w: float = 90.0
    """Continuous sunlit bus load (W). Imaging payload + comms + ADCS +
    avionics for a SkySat-class satellite during normal operations.
    Estimate: published smallsat power-budget figures."""

    eclipse_load_w: float = 60.0
    """Reduced eclipse load (W). Payload off; heaters and survival loads on."""


@dataclass(frozen=True)
class ThermalParams:
    """Thermal subsystem parameters (single-node model)."""

    mass_kg: float = 110.0
    """Total dry mass (kg). SkySat-class published value."""

    specific_heat_j_kg_k: float = 900.0
    """Effective specific heat (J/kg/K). Aluminum-dominated structure ~900."""

    # Absorbed solar heat
    cross_section_m2: float = 0.35
    """Effective sun-facing cross-section for solar absorption (m^2).
    Estimate accounting for partial shadowing of the body by deployed arrays."""

    absorptivity: float = 0.4
    """Solar absorptivity (-). Typical MLI / paint mix."""

    # Radiative cooling
    radiating_area_m2: float = 1.2
    """Effective radiating area (m^2). Much smaller than geometric surface
    area because most surfaces are covered in multi-layer insulation (MLI)
    blankets that suppress radiation by ~100x. Real heat rejection happens
    through dedicated radiator panels and small uninsulated areas. Source:
    Gilmore, *Spacecraft Thermal Control Handbook*, vol. I, ch. 5; typical
    SkySat-class effective radiator area is 1.0-1.5 m^2."""

    emissivity: float = 0.85
    """Infrared emissivity (-). Typical white paint / radiator."""

    # Internal dissipation
    internal_dissipation_w: float = 30.0
    """Steady-state heat dissipation from electronics (W). Approximates bus_load."""

    earth_ir_w: float = 100.0
    """Earth infrared heat input (W). LEO satellites continuously absorb
    longwave radiation from Earth's surface and atmosphere (~240 W/m² leaving
    Earth, view factor ~0.30 at 500 km, IR emissivity ~0.85). This is the
    dominant reason eclipse temperatures don't crash toward deep-space values.
    Source: Gilmore, *Spacecraft Thermal Control Handbook*, vol. I, ch. 2."""

    # Initial condition
    initial_temperature_k: float = 285.0
    """Starting temperature (K). ~12 C, typical satellite thermal target."""


@dataclass(frozen=True)
class Constants:
    stefan_boltzmann_w_m2_k4: float = 5.670374419e-8
    """Stefan-Boltzmann constant (W/m^2/K^4)."""

    deep_space_temperature_k: float = 2.7
    """Cosmic microwave background temperature (K)."""


EPS = EpsParams()
THERMAL = ThermalParams()
CONST = Constants()
