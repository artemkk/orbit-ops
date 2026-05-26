-- Per-satellite, per-minute rollup. The grain that dashboards graph against.
-- Aggregates per-tick measurements into mins/maxs/means over each minute.
{{
  config(
    materialized='external',
    location=var('external_root') ~ '/' ~ this.name ~ '.parquet'
  )
}}

with eps as (
    select * from {{ ref('stg_eps') }}
),
thermal as (
    select * from {{ ref('stg_thermal') }}
),
geometry as (
    select * from {{ ref('stg_geometry') }}
),
joined as (
    select
        e.sat_id,
        date_trunc('minute', e.sim_time) as minute_bucket,

        -- EPS aggregates
        avg(e.battery_soc) as battery_soc_mean,
        min(e.battery_soc) as battery_soc_min,
        max(e.battery_soc) as battery_soc_max,
        avg(e.solar_power_w) as solar_power_w_mean,
        avg(e.bus_power_w) as bus_power_w_mean,
        avg(e.net_power_w) as net_power_w_mean,
        sum(e.is_charging) / count(*)::double as charging_fraction,

        -- Thermal aggregates
        avg(t.bus_temperature_k) as bus_temperature_k_mean,
        min(t.bus_temperature_k) as bus_temperature_k_min,
        max(t.bus_temperature_k) as bus_temperature_k_max,
        avg(t.net_heat_w) as net_heat_w_mean,

        -- Eclipse fraction
        sum(case when e.eclipsed then 1 else 0 end) / count(*)::double as eclipse_fraction,

        -- Geometry aggregates
        avg(g.altitude_km) as altitude_km_mean,
        avg(g.position_magnitude_km) as position_magnitude_km_mean,
        avg(g.orbital_speed_km_s) as orbital_speed_km_s_mean

    from eps e
    inner join thermal t on e.sat_id = t.sat_id and e.sim_time = t.sim_time
    inner join geometry g on e.sat_id = g.sat_id and e.sim_time = g.sim_time
    group by e.sat_id, date_trunc('minute', e.sim_time)
)
select * from joined
