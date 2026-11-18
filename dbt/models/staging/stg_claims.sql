with source as (
    select
        claim_sk,
        claim_sequence,
        policy_id,
        policy_sk,
        claim_amount,
        src_system,
        src_file_name,
        src_row_number,
        loaded_at
    from {{ source('raw', 'claims') }}
)

select
    claim_sk,
    cast(claim_sequence as {{ dbt.type_int() }}) as claim_sequence,
    cast(policy_id as {{ dbt.type_bigint() }}) as policy_id,
    policy_sk,
    cast(claim_amount as numeric(18, 2)) as claim_amount,
    src_system,
    src_file_name,
    cast(src_row_number as {{ dbt.type_bigint() }}) as src_row_number,
    loaded_at,
    case when policy_sk is null then true else false end as is_orphan_claim,
    case
        when count(*) over (partition by policy_id, claim_amount) > 1 then true
        else false
    end as is_duplicate_amount_row
from source
