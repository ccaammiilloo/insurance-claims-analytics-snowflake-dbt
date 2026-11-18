select
    policies.policy_sk,
    policies.policy_id,
    vehicles.vehicle_sk,
    drivers.driver_sk,
    policies.exposure_years,
    policies.claim_count,
    reconciliation.severity_row_count,
    reconciliation.severity_amount as matched_claim_amount,
    reconciliation.claim_count_matches_severity_rows,
    reconciliation.has_missing_severity,
    reconciliation.has_unexpected_severity,
    reconciliation.has_count_mismatch_both_positive,
    reconciliation.missing_severity_claim_units,
    policies.is_exposure_gt_one,
    policies.is_extreme_claim_count
from {{ ref('stg_policies') }} as policies
inner join {{ ref('stg_vehicles') }} as vehicles
    on policies.policy_sk = vehicles.policy_sk
inner join {{ ref('stg_drivers') }} as drivers
    on policies.policy_sk = drivers.policy_sk
inner join {{ ref('int_policy_claim_reconciliation') }} as reconciliation
    on policies.policy_sk = reconciliation.policy_sk
