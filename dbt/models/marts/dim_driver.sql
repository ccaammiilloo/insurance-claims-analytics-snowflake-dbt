select
    driver_sk,
    policy_sk,
    policy_id,
    driv_age,
    driv_age_band,
    is_driver_age_sentinel
from {{ ref('stg_drivers') }}
