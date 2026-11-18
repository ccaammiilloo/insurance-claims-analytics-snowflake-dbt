# Power BI design for the HDI Global style reporting layer

This document describes the Power BI model that will sit on the curated marts. The business goal matches the HDI Global data analyst role. The team is moving its reporting layer from Qlik to Power BI after the data platform has moved to Snowflake and dbt. This project uses the same shape. Raw data stands in for policy and claims systems. dbt prepares the star schema. Power BI is the visualization layer that business users would open instead of a Qlik app.

The measures below are the contract for the migration. Frequency, severity, and pure premium are defined here so a reviewer can see exactly how a Qlik expression should be replaced. The files have no premium, so a loss ratio is not part of this model and must not be invented. All book totals must match docs/data_profile.md. Those totals were computed from the source files and are checked by dbt tests.

Local development uses DuckDB. The same models are intended to run on Snowflake once account credentials are available. Power BI Service would then connect to the Snowflake marts. That connection is not built in this step.

## Star schema

Import the marts from the `marts` schema, plus the `region_names` seed only if you want it as a separate table. The region name is already on `dim_policy`, so the seed is optional in Power BI.

Fact tables:

- `fct_policy_exposure`. Grain is one row per policy. Use this table for exposure, claim counts, frequency, and pure premium.
- `fct_claims`. Grain is one row per severity record. Use this table for claim amount distributions and large claims. Orphan claims have a null `policy_sk`. Keep them in the table and exclude them from official severity and pure premium measures.

Dimension tables:

- `dim_policy`. Grain is one row per policy. Attributes include area, region, region name, density, bonus malus, and bonus malus band. `book_period_label` is a reporting convention from the CASdatasets documentation. It is not a policy start date or a loss date. The source files have no dates.
- `dim_vehicle`. Grain is one vehicle per policy in this book. Attributes include power, age, age band, brand, and fuel type.
- `dim_driver`. Grain is one recorded driver per policy. The source provides only driver age and the derived age band.

Relationships, all single direction from dimension to fact, one to many:

- `dim_policy[policy_sk]` to `fct_policy_exposure[policy_sk]`.
- `dim_vehicle[vehicle_sk]` to `fct_policy_exposure[vehicle_sk]`.
- `dim_driver[driver_sk]` to `fct_policy_exposure[driver_sk]`.
- `dim_policy[policy_sk]` to `fct_claims[policy_sk]`.
- `dim_vehicle[vehicle_sk]` to `fct_claims[vehicle_sk]`.
- `dim_driver[driver_sk]` to `fct_claims[driver_sk]`.

`fct_claims` will have rows that do not match a policy. Leave the relationship with an unmatched row (blank dimension) rather than dropping those claims. Official measures filter them out with `is_orphan_claim`.

Because this book is one vehicle and one recorded driver per policy, the three dimensions are one to one with each other. Keep them as separate tables anyway. That layout mirrors a policy system with coverables and contacts, and it stays valid if a later source has more than one vehicle or driver.

Do not load staging or intermediate models into Power BI. They are build layers. `mart_risk_segments` is an optional aggregated table for a quick segment page or for a check against the profile. If you import it, do not also add its measures to the same visuals as the star schema, or totals will be mixed.

## DAX measures

Place the measures in a dedicated measures table or on `fct_policy_exposure`. Use `DIVIDE` so a zero exposure slice returns blank rather than an error. Do not hide the missing severity gap by replacing `claim_count` with the severity row count.

```dax
Exposure =
SUM ( fct_policy_exposure[exposure_years] )

Policy Count =
COUNTROWS ( fct_policy_exposure )

Claim Count =
SUM ( fct_policy_exposure[claim_count] )

Claim Frequency =
DIVIDE ( [Claim Count], [Exposure] )

Matched Claim Amount =
SUM ( fct_policy_exposure[matched_claim_amount] )

Matched Severity Rows =
SUM ( fct_policy_exposure[severity_row_count] )

Average Severity =
DIVIDE ( [Matched Claim Amount], [Matched Severity Rows] )

Pure Premium =
DIVIDE ( [Matched Claim Amount], [Exposure] )

Policies With Missing Severity =
CALCULATE (
    COUNTROWS ( fct_policy_exposure ),
    fct_policy_exposure[has_missing_severity] = TRUE ()
)

Exposure Over One Year =
CALCULATE (
    COUNTROWS ( fct_policy_exposure ),
    fct_policy_exposure[is_exposure_gt_one] = TRUE ()
)
```

Claim amount from the claim fact, for detail pages only:

```dax
Claim Amount All Rows =
SUM ( fct_claims[claim_amount] )

Matched Claim Amount From Claims =
CALCULATE (
    SUM ( fct_claims[claim_amount] ),
    fct_claims[is_orphan_claim] = FALSE ()
)

Orphan Claim Amount =
CALCULATE (
    SUM ( fct_claims[claim_amount] ),
    fct_claims[is_orphan_claim] = TRUE ()
)

Average Severity From Claims =
DIVIDE (
    [Matched Claim Amount From Claims],
    CALCULATE (
        COUNTROWS ( fct_claims ),
        fct_claims[is_orphan_claim] = FALSE ()
    )
)
```

`Matched Claim Amount` and `Matched Claim Amount From Claims` must agree at book level. The documented book values are 678,013 policies, 358,499.45 exposure years, 36,102 claims, and 59,909,216.50 matched claim amount. Use those four values as the acceptance check after the first Power BI refresh.

There is no written premium and no earned premium in the model. Do not add a Loss Ratio measure.

## Planned report pages

The pages follow the questions a reporting team would migrate from Qlik. Each page should show the filter context, the measure definition in a tooltip or info button, and the book period label from `dim_policy`.

1. Executive overview. Cards for Policy Count, Exposure, Claim Count, Claim Frequency, Average Severity, and Pure Premium. A small table of area and fuel type. A short note that these figures are for the freMTPL2 observation book, approximately 2011 to 2013, and that they are not a live Guidewire extract.

2. Territory risk. Claim Frequency, Average Severity, and Pure Premium by area and by region. Area is a density band from rural A to urban F. Region uses the INSEE 1970 to 2015 names. This page replaces a typical Qlik geography sheet.

3. Driver and vehicle risk. The same three measures by driver age band, vehicle age band, fuel type, vehicle power, and brand. New vehicles have a high Claim Frequency and a large missing severity gap. The page must show Matched Severity Rows next to Claim Count so that gap is visible.

4. Bonus malus and portfolio mix. Pure premium and frequency by bonus malus band, with policy mix on the 50 maximum bonus versus malus values above 100.

5. Data quality and migration trust. Counts of policies with missing severity, orphan claims, exposure greater than one year, extreme claim counts, and the one policy whose ClaimNb and severity row count are both positive and different. During a Qlik to Power BI migration this page is how the team shows that the new model is honest about source issues rather than silently cleaning them.

6. Claim detail. A distribution of matched claim amounts, a list of the largest claims, and a way to filter by area, region, and vehicle attributes. Orphan claims can appear in a separate visual. They must not move the official Average Severity or Pure Premium cards.

## Migration notes

Keep measure names stable. If a later Qlik app used a different definition, such as severity row counts instead of ClaimNb, document the difference rather than changing the official Claim Frequency here.

Do not build a date table from invented policy or loss dates. If a calendar is required for Power BI Service refresh history, use the dataset refresh timestamp only, and keep it out of the business model.

Refresh path once Snowflake is available: dbt build on the prod target, then a Power BI import or DirectQuery against the marts schema. Until then, the DuckDB marts can be exported to CSV or Parquet for a local Power BI Desktop prototype.
