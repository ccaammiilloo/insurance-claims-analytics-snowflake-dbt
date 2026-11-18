{{ config(enabled=var('book_scope', 'full') == 'full') }}

-- Documents the known orphan severity records. Six policy identifiers and
-- 195 rows have no match in the policy file. The test fails if those
-- counts change.
select 1 as check_row
from {{ ref('stg_claims') }}
where is_orphan_claim = true
having count(*) <> 195
    or count(distinct policy_id) <> 6
