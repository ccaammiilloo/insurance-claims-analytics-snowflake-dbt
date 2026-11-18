with book as (
    select
        policies.policy_sk,
        policies.area,
        policies.region,
        region_names.region_name,
        vehicles.veh_gas,
        drivers.driv_age_band,
        vehicles.veh_age_band,
        policies.bonus_malus_band,
        policies.exposure_years,
        policies.claim_count,
        reconciliation.severity_row_count,
        reconciliation.severity_amount
    from {{ ref('stg_policies') }} as policies
    inner join {{ ref('stg_vehicles') }} as vehicles
        on policies.policy_sk = vehicles.policy_sk
    inner join {{ ref('stg_drivers') }} as drivers
        on policies.policy_sk = drivers.policy_sk
    inner join {{ ref('int_policy_claim_reconciliation') }} as reconciliation
        on policies.policy_sk = reconciliation.policy_sk
    left join {{ ref('region_names') }} as region_names
        on policies.region = region_names.region_code
),

segmented as (
    select 'area' as segment_type, area as segment_value, cast(null as {{ dbt.type_string() }}) as segment_label,
        exposure_years, claim_count, severity_row_count, severity_amount
    from book

    union all

    select 'region' as segment_type, region as segment_value, region_name as segment_label,
        exposure_years, claim_count, severity_row_count, severity_amount
    from book

    union all

    select 'veh_gas' as segment_type, veh_gas as segment_value, cast(null as {{ dbt.type_string() }}) as segment_label,
        exposure_years, claim_count, severity_row_count, severity_amount
    from book

    union all

    select 'driv_age_band' as segment_type, driv_age_band as segment_value, cast(null as {{ dbt.type_string() }}) as segment_label,
        exposure_years, claim_count, severity_row_count, severity_amount
    from book

    union all

    select 'veh_age_band' as segment_type, veh_age_band as segment_value, cast(null as {{ dbt.type_string() }}) as segment_label,
        exposure_years, claim_count, severity_row_count, severity_amount
    from book

    union all

    select 'bonus_malus_band' as segment_type, bonus_malus_band as segment_value, cast(null as {{ dbt.type_string() }}) as segment_label,
        exposure_years, claim_count, severity_row_count, severity_amount
    from book
)

select
    segment_type,
    segment_value,
    segment_label,
    count(*) as policy_count,
    sum(exposure_years) as exposure_years,
    sum(claim_count) as claim_count,
    cast(sum(claim_count) as {{ dbt.type_float() }}) / nullif(sum(exposure_years), 0) as claim_frequency,
    sum(severity_row_count) as severity_row_count,
    cast(sum(severity_amount) as numeric(18, 2)) as matched_claim_amount,
    cast(sum(severity_amount) as {{ dbt.type_float() }}) / nullif(sum(severity_row_count), 0) as average_severity,
    cast(sum(severity_amount) as {{ dbt.type_float() }}) / nullif(sum(exposure_years), 0) as pure_premium
from segmented
group by
    segment_type,
    segment_value,
    segment_label
