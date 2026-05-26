-- Thermal subsystem per-tick view with heat-balance computation.
{{ config(materialized='view') }}

select
    sat_id,
    sim_time,
    eclipsed,
    bus_temperature_k,
    bus_temperature_c,
    solar_heat_input_w,
    earth_ir_input_w,
    radiative_heat_output_w,
    net_heat_w,

    -- Total heat input (sun + earth IR)
    solar_heat_input_w + earth_ir_input_w as total_heat_input_w,

    -- Sign of net heat: warming, cooling, or steady
    case
        when net_heat_w > 1 then 'warming'
        when net_heat_w < -1 then 'cooling'
        else 'steady'
    end as thermal_regime

from {{ ref('raw_telemetry') }}
