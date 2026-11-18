select
    vehicle_sk,
    policy_sk,
    policy_id,
    veh_power,
    veh_age,
    veh_age_band,
    veh_brand,
    veh_gas,
    is_new_vehicle,
    is_vehicle_age_sentinel
from {{ ref('stg_vehicles') }}
