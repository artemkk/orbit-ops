-- Orbital geometry per tick, with computed altitude/velocity magnitudes
-- and a derived "ground-track quadrant" for quick filtering in dashboards.
{{ config(materialized='view') }}

select
    sat_id,
    sim_time,
    sim_time_iso,
    position_eci_km_x,
    position_eci_km_y,
    position_eci_km_z,
    velocity_eci_km_s_x,
    velocity_eci_km_s_y,
    velocity_eci_km_s_z,
    sun_vector_eci_x,
    sun_vector_eci_y,
    sun_vector_eci_z,
    eclipsed,
    latitude_deg,
    longitude_deg,
    altitude_km,

    -- Derived: position magnitude (distance from Earth's center, km)
    sqrt(
        position_eci_km_x * position_eci_km_x
        + position_eci_km_y * position_eci_km_y
        + position_eci_km_z * position_eci_km_z
    ) as position_magnitude_km,

    -- Derived: orbital speed magnitude (km/s)
    sqrt(
        velocity_eci_km_s_x * velocity_eci_km_s_x
        + velocity_eci_km_s_y * velocity_eci_km_s_y
        + velocity_eci_km_s_z * velocity_eci_km_s_z
    ) as orbital_speed_km_s,

    -- Quadrant of sub-satellite point: NE, NW, SE, SW (for dashboard filtering)
    case
        when latitude_deg >= 0 and longitude_deg >= 0 then 'NE'
        when latitude_deg >= 0 and longitude_deg < 0 then 'NW'
        when latitude_deg < 0 and longitude_deg >= 0 then 'SE'
        else 'SW'
    end as ground_quadrant

from {{ ref('raw_telemetry') }}
