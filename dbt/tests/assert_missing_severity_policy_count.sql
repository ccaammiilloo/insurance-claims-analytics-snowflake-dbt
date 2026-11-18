{{ config(enabled=var('book_scope', 'full') == 'full') }}

-- Documents the known 9116 policies with ClaimNb greater than 0 and no
-- severity rows. The test fails if that count changes.
select 1 as check_row
from {{ ref('int_policy_claim_reconciliation') }}
where has_missing_severity = true
having count(*) <> 9116
