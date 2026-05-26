-- Latest-known state per satellite. Used by the fleet-view dashboard
-- to show "where every sat is right now."
{{
  config(
    materialized='external',
    location=var('external_root') ~ '/' ~ this.name ~ '.parquet'
  )
}}

with latest as (
    select
        sat_id,
        max(sim_time) as latest_sim_time
    from {{ ref('raw_telemetry') }}
    group by sat_id
)
select
    r.sat_id,
    r.sim_time as latest_sim_time,
    r.battery_soc,
    r.bus_temperature_k,
    r.bus_temperature_c,
    r.eclipsed,
    r.latitude_deg,
    r.longitude_deg,
    r.altitude_km,
    r.solar_power_w,
    r.net_power_w,
    -- Health classification: simple banding for the fleet heat-map.
    case
        when r.battery_soc < 0.25 then 'critical'
        when r.battery_soc < 0.50 then 'degraded'
        else 'nominal'
    end as battery_health_band,
    case
        when r.bus_temperature_c < -20 or r.bus_temperature_c > 50 then 'critical'
        when r.bus_temperature_c < -10 or r.bus_temperature_c > 40 then 'degraded'
        else 'nominal'
    end as thermal_health_band
from {{ ref('raw_telemetry') }} r
inner join latest l on r.sat_id = l.sat_id and r.sim_time = l.latest_sim_time
