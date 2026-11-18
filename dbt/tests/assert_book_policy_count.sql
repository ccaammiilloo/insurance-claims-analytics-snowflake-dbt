{{ config(enabled=var('book_scope', 'full') == 'full') }}

-- Reconciles the policy fact to the profiled book size of 678013 policies.
select 1 as check_row
from {{ ref('fct_policy_exposure') }}
having count(*) <> 678013
