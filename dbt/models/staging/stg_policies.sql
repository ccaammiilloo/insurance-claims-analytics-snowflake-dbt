with source as (
    select
        policy_sk,
        policy_id,
        claim_count,
        exposure_years,
        area,
        bonus_malus,
        density,
        region,
        src_system,
        src_file_name,
        src_row_number,
        loaded_at
    from {{ source('raw', 'policies') }}
)

select
    policy_sk,
    cast(policy_id as {{ dbt.type_bigint() }}) as policy_id,
    cast(claim_count as {{ dbt.type_int() }}) as claim_count,
    cast(exposure_years as {{ dbt.type_float() }}) as exposure_years,
    cast(area as {{ dbt.type_string() }}) as area,
    cast(bonus_malus as {{ dbt.type_int() }}) as bonus_malus,
    {{ bonus_malus_band('bonus_malus') }} as bonus_malus_band,
    cast(density as {{ dbt.type_int() }}) as density,
    cast(region as {{ dbt.type_string() }}) as region,
    src_system,
    src_file_name,
    cast(src_row_number as {{ dbt.type_bigint() }}) as src_row_number,
    loaded_at,
    case when exposure_years > 1 then true else false end as is_exposure_gt_one,
    case when claim_count >= 4 then true else false end as is_extreme_claim_count
from source
