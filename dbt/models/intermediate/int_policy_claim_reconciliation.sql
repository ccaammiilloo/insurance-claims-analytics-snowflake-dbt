with claims as (
    select
        policy_id,
        count(*) as severity_row_count,
        sum(claim_amount) as severity_amount
    from {{ ref('stg_claims') }}
    where is_orphan_claim = false
    group by policy_id
)

select
    policies.policy_sk,
    policies.policy_id,
    policies.claim_count,
    coalesce(claims.severity_row_count, 0) as severity_row_count,
    cast(coalesce(claims.severity_amount, 0) as numeric(18, 2)) as severity_amount,
    case
        when policies.claim_count = coalesce(claims.severity_row_count, 0) then true
        else false
    end as claim_count_matches_severity_rows,
    case
        when policies.claim_count > 0 and coalesce(claims.severity_row_count, 0) = 0 then true
        else false
    end as has_missing_severity,
    case
        when policies.claim_count = 0 and coalesce(claims.severity_row_count, 0) > 0 then true
        else false
    end as has_unexpected_severity,
    case
        when policies.claim_count > 0
            and coalesce(claims.severity_row_count, 0) > 0
            and policies.claim_count <> claims.severity_row_count then true
        else false
    end as has_count_mismatch_both_positive,
    case
        when policies.claim_count > coalesce(claims.severity_row_count, 0)
            then policies.claim_count - coalesce(claims.severity_row_count, 0)
        else 0
    end as missing_severity_claim_units
from {{ ref('stg_policies') }} as policies
left join claims
    on policies.policy_id = claims.policy_id
