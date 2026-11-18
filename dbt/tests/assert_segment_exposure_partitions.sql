{{ config(enabled=var('book_scope', 'full') == 'full') }}

-- Each segment type other than a filter should partition the full book.
-- Sum of exposure by segment type must equal the book exposure.
select
    segment_type,
    round(sum(exposure_years), 2) as exposure_years
from {{ ref('mart_risk_segments') }}
group by segment_type
having round(sum(exposure_years), 2) <> 358499.45
    or sum(policy_count) <> 678013
    or sum(claim_count) <> 36102
    or round(sum(matched_claim_amount), 2) <> 59909216.50
