-- Raw telemetry. 1:1 reflection of the consumer's Parquet output, with
-- explicit casts and a parsed timestamp column. No business logic here.
{{ config(materialized='view') }}

select
    cast(sat_id as varchar) as sat_id,
    cast(sim_time_iso as varchar) as sim_time_iso,
    cast(sim_time_iso as timestamp) as sim_time,

    -- Geometry (ECI, km / km/s)
    cast(position_eci_km_x as double) as position_eci_km_x,
    cast(position_eci_km_y as double) as position_eci_km_y,
    cast(position_eci_km_z as double) as position_eci_km_z,
    cast(velocity_eci_km_s_x as double) as velocity_eci_km_s_x,
    cast(velocity_eci_km_s_y as double) as velocity_eci_km_s_y,
    cast(velocity_eci_km_s_z as double) as velocity_eci_km_s_z,
    cast(sun_vector_eci_x as double) as sun_vector_eci_x,
    cast(sun_vector_eci_y as double) as sun_vector_eci_y,
    cast(sun_vector_eci_z as double) as sun_vector_eci_z,
    cast(eclipsed as boolean) as eclipsed,
    cast(latitude_deg as double) as latitude_deg,
    cast(longitude_deg as double) as longitude_deg,
    cast(altitude_km as double) as altitude_km,

    -- EPS
    cast(solar_power_w as double) as solar_power_w,
    cast(bus_power_w as double) as bus_power_w,
    cast(net_power_w as double) as net_power_w,
    cast(battery_soc as double) as battery_soc,
    cast(battery_charge_wh as double) as battery_charge_wh,

    -- Thermal
    cast(bus_temperature_k as double) as bus_temperature_k,
    cast(bus_temperature_c as double) as bus_temperature_c,
    cast(solar_heat_input_w as double) as solar_heat_input_w,
    cast(earth_ir_input_w as double) as earth_ir_input_w,
    cast(radiative_heat_output_w as double) as radiative_heat_output_w,
    cast(net_heat_w as double) as net_heat_w

from read_parquet('{{ var("telemetry_parquet_glob") }}', hive_partitioning=true)
