{{ config(enabled=var('book_scope', 'full') == 'full') }}

-- Reconciles matched claim amount to the profiled total of 59909216.50.
-- Orphan claims are excluded from this total.
select 1 as check_row
from {{ ref('fct_policy_exposure') }}
having round(sum(matched_claim_amount), 2) <> 59909216.50
