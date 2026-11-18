with source as (
    select
        driver_sk,
        policy_sk,
        policy_id,
        driv_age,
        src_system,
        src_file_name,
        src_row_number,
        loaded_at
    from {{ source('raw', 'drivers') }}
)

select
    driver_sk,
    policy_sk,
    cast(policy_id as {{ dbt.type_bigint() }}) as policy_id,
    cast(driv_age as {{ dbt.type_int() }}) as driv_age,
    {{ driv_age_band('driv_age') }} as driv_age_band,
    src_system,
    src_file_name,
    cast(src_row_number as {{ dbt.type_bigint() }}) as src_row_number,
    loaded_at,
    case when driv_age in (99, 100) then true else false end as is_driver_age_sentinel
from source
