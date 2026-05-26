-- Electrical Power Subsystem per-tick view with computed columns
-- useful for both dashboards and anomaly detection.
{{ config(materialized='view') }}

select
    sat_id,
    sim_time,
    eclipsed,
    solar_power_w,
    bus_power_w,
    net_power_w,
    battery_soc,
    battery_charge_wh,

    -- Power balance flag: is the bus charging right now?
    case when net_power_w > 0 then 1 else 0 end as is_charging,

    -- Hour-of-day for time-of-day analysis
    extract(hour from sim_time) as sim_hour,

    -- Hour-of-orbit approximation (mod 90 minutes from epoch start)
    cast(extract(epoch from sim_time) as bigint) % 5400 as seconds_into_orbit

from {{ ref('raw_telemetry') }}
