with source as (
    select
        vehicle_sk,
        policy_sk,
        policy_id,
        veh_power,
        veh_age,
        veh_brand,
        veh_gas,
        src_system,
        src_file_name,
        src_row_number,
        loaded_at
    from {{ source('raw', 'vehicles') }}
)

select
    vehicle_sk,
    policy_sk,
    cast(policy_id as {{ dbt.type_bigint() }}) as policy_id,
    cast(veh_power as {{ dbt.type_int() }}) as veh_power,
    cast(veh_age as {{ dbt.type_int() }}) as veh_age,
    {{ veh_age_band('veh_age') }} as veh_age_band,
    cast(veh_brand as {{ dbt.type_string() }}) as veh_brand,
    cast(veh_gas as {{ dbt.type_string() }}) as veh_gas,
    src_system,
    src_file_name,
    cast(src_row_number as {{ dbt.type_bigint() }}) as src_row_number,
    loaded_at,
    case when veh_age = 0 then true else false end as is_new_vehicle,
    case when veh_age in (99, 100) then true else false end as is_vehicle_age_sentinel
from source
