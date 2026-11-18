select
    claims.claim_sk,
    claims.claim_sequence,
    claims.policy_id,
    claims.policy_sk,
    vehicles.vehicle_sk,
    drivers.driver_sk,
    claims.claim_amount,
    claims.is_orphan_claim,
    claims.is_duplicate_amount_row,
    claims.src_row_number
from {{ ref('stg_claims') }} as claims
left join {{ ref('stg_vehicles') }} as vehicles
    on claims.policy_sk = vehicles.policy_sk
left join {{ ref('stg_drivers') }} as drivers
    on claims.policy_sk = drivers.policy_sk
