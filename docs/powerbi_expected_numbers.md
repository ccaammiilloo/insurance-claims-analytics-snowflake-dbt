# Power BI expected numbers checklist

Use this list after you open `InsurancePortfolio.pbip`, enter your Snowflake credentials, and refresh. The values were computed from `INSURANCE_PORTFOLIO.MARTS` with the `INSURANCE_PBI_READONLY` role. They match the full book totals in `docs/data_profile.md` and `docs/power_bi_design.md`.

Format the cards the same way the measures are formatted. Small rounding differences on the last decimal are not a fail if the unrounded value matches.

## Official portfolio measures (page 1)

These come from `FCT_POLICY_EXPOSURE`. Orphan claims are not in this fact, so they do not move these cards.

| Measure | Expected value | How to read it |
| --- | --- | --- |
| Policy Count | 678,013 | One row per policy |
| Exposure | 358,499.45 | Sum of exposure years |
| Claim Count | 36,102 | Sum of ClaimNb, not severity row count |
| Claim Frequency | 0.100703 | Claim Count / Exposure. This is claims per year, not a percentage |
| Matched Claim Amount | 59,909,216.50 | Matched amounts only |
| Matched Severity Rows | 26,444 | Severity rows that match a policy |
| Average Severity | 2,265.51 | Matched Claim Amount / Matched Severity Rows |
| Pure Premium | 167.11 | Matched Claim Amount / Exposure |
| Policies With Claims | 34,060 | Policies with Claim Count greater than 0 |
| Policies With Claims % | 5.02% | 34,060 / 678,013 |

There is no Loss Ratio measure. The source has no premium.

## Reconciliation between the two facts (page 3)

| Measure | Expected value | Note |
| --- | --- | --- |
| Matched Claim Amount | 59,909,216.50 | From the exposure fact |
| Matched Claim Amount From Claims | 59,909,216.50 | From `FCT_CLAIMS` where `IS_ORPHAN_CLAIM` is false. Must tie to the row above |
| Average Severity From Claims | 2,265.51 | Must tie to official Average Severity |
| Claim Amount All Rows | 60,697,930.68 | Matched plus orphan amounts |

## Data quality measures (page 3)

| Measure | Expected value | Note |
| --- | --- | --- |
| Policies With Missing Severity | 9,116 | Claim Count greater than 0 and no severity row |
| Missing Severity Claim Units | 9,658 | Includes 9,657 zero-severity claim units plus 1 unit from the count mismatch policy |
| Policies With Count Mismatch | 1 | IDpol 4,158,255 has Claim Count 2 and one severity row |
| Orphan Claim Rows | 195 | Severity rows with no matching policy |
| Orphan Claim IDs | 6 | Distinct policy IDs that appear only in the severity file |
| Orphan Claim Amount | 788,714.18 | Excluded from official Average Severity and Pure Premium |
| Duplicate Amount Rows | 496 | Rows flagged `IS_DUPLICATE_AMOUNT_ROW` |
| Exposure Over One Year | 1,224 | Maximum exposure is 2.01 years |
| Extreme Claim Count Policies | 16 | ClaimNb of 4 or more |

## Other useful checks

- `DIM_POLICY`, `DIM_VEHICLE`, `DIM_DRIVER`, and `FCT_POLICY_EXPOSURE` each have 678,013 rows.
- `FCT_CLAIMS` has 26,639 rows (26,444 matched + 195 orphan).
- `MART_RISK_SEGMENTS` has 49 rows and is disconnected on purpose. Do not drop its columns onto visuals that already use the official measures.
- `SEEDS.REGION_NAMES` is not in the model. `REGION_NAME` is already on `DIM_POLICY`.
- Book period label: freMTPL2 observation book (approximately 2011 to 2013).

## Risk driver context (page 2)

These are not card totals. They are useful when you read the charts after refresh.

- Drivers aged 18 to 25 have the highest frequency (0.175069) and the highest average severity (5,121.62).
- Frequency rises from rural Area A (0.081702) to urban Area F (0.139127).
- New vehicles (vehicle age 0) have a very high Claim Count frequency (0.311322), but only 1,181 matched severity rows against 5,205 claim counts. Use the table at the bottom of page 2 to see that gap.
