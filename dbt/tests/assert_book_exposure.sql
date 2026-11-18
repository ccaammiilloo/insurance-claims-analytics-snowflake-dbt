{{ config(enabled=var('book_scope', 'full') == 'full') }}

-- Reconciles exposure to the profiled total of 358499.45 policy years
-- when rounded to two decimals. The exact sum is documented in
-- docs/data_profile.md.
select 1 as check_row
from {{ ref('fct_policy_exposure') }}
having round(sum(exposure_years), 2) <> 358499.45
