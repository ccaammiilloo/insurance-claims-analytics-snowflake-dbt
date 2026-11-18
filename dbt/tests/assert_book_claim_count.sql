{{ config(enabled=var('book_scope', 'full') == 'full') }}

-- Reconciles claim_count (original ClaimNb) to the profiled total of 36102.
select 1 as check_row
from {{ ref('fct_policy_exposure') }}
having sum(claim_count) <> 36102
