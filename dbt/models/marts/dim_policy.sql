select
    policies.policy_sk,
    policies.policy_id,
    policies.area,
    policies.bonus_malus,
    policies.bonus_malus_band,
    policies.density,
    policies.region,
    region_names.region_name,
    'freMTPL2 observation book (approximately 2011 to 2013)' as book_period_label,
    policies.is_exposure_gt_one,
    policies.is_extreme_claim_count
from {{ ref('stg_policies') }} as policies
left join {{ ref('region_names') }} as region_names
    on policies.region = region_names.region_code
