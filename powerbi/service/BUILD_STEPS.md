# Build the report in Power BI Service (browser)

Plan B is the path that works on this Pro-trial shared capacity. Do not use **New item > Semantic model > Excel** or Power Query Online to import the xlsx files. That route fails here with `CapacityDoesNotSupportPremiumFilesException`, even at 1.6 MB. Use **Create > Paste or manually enter data** (Enter data) with `pbi_paste_table.tsv`.

The paste file is one long-format table, 75 data rows plus a header, 11 columns. Official totals still come from SUM / DIVIDE, but only when the visual is filtered to a single `segment_type`. An unfiltered SUM of `policy_count` would count the book several times (once per segment type) and is wrong.

Work at 1280x800. After each major screen loads, collapse the left workspace nav (hamburger) so the canvas has room. Do not use Fabric, and do not connect this report to Snowflake.

## 1. Paste the table (Enter data)

1. Sign in at [https://app.powerbi.com](https://app.powerbi.com).
2. Open `pbi_paste_table.tsv` in a text editor (Notepad, VS Code). Do not open it in Excel first; Excel can change decimals or encoding. Select all, copy.
3. In the left nav, select **My workspace**.
4. Select **Create** (or **New item** / **New**), then **Paste or manually enter data** (also called **Enter data**).
5. Click the upper-left cell in the grid (the first header cell) and paste (Ctrl+V). You should get a header row and 75 data rows, 11 columns. If the first row is not the header, undo and click the top-left cell again before pasting.
6. At the bottom of the dialog, name the table `segments`. Do not leave the default name `Table`.
7. Select **Create**. Wait for the semantic model and a blank report, or go back to **My workspace** and open the new semantic model.

The Fields pane should show one table named `segments`. If you see `Table` or `segments1`, rename the table to `segments` in the data model before adding DAX.

## 2. Add the DAX measures in web modeling

1. In **My workspace**, on the new semantic model, open **...** and select **Open data model** (or **Open semantic model**).
2. Switch from **Viewing** to **Editing** at the top right. Changes save automatically.
3. Select the `segments` table, then **New measure**. Paste one formula, press Enter, set the format, and repeat.

```dax
Policy Count = SUM ( segments[policy_count] )
```

Format: Whole number, thousands separator (`#,0`).

```dax
Exposure = SUM ( segments[exposure] )
```

Format: Decimal number, 2 decimal places (`#,0.00`).

```dax
Claim Count = SUM ( segments[claim_count] )
```

Format: Whole number, thousands separator (`#,0`).

```dax
Claim Frequency = DIVIDE ( SUM ( segments[claim_count] ), SUM ( segments[exposure] ) )
```

Format: Decimal number, 6 decimal places (`0.000000`). This is claims per year, not a percentage.

```dax
Matched Claim Amount = SUM ( segments[matched_claim_amount] )
```

Format: Decimal number, 2 decimal places (`#,0.00`).

```dax
Matched Severity Rows = SUM ( segments[matched_severity_rows] )
```

Format: Whole number, thousands separator (`#,0`).

```dax
Average Severity = DIVIDE ( SUM ( segments[matched_claim_amount] ), SUM ( segments[matched_severity_rows] ) )
```

Format: Decimal number, 2 decimal places (`#,0.00`).

```dax
Pure Premium = DIVIDE ( SUM ( segments[matched_claim_amount] ), SUM ( segments[exposure] ) )
```

Format: Decimal number, 2 decimal places (`#,0.00`).

```dax
Policies With Claims = SUM ( segments[policies_with_claims] )
```

Format: Whole number, thousands separator (`#,0`).

```dax
Policies With Claims % = DIVIDE ( SUM ( segments[policies_with_claims] ), SUM ( segments[policy_count] ) )
```

Format: Percentage, 2 decimal places (`0.00%`).

Do not add a Loss Ratio measure. Do not add a date table. These measures are only valid on a visual (or page) filtered to one `segment_type`.

After the ten measures exist, return to **My workspace** if needed and **Create report** on this semantic model, or use the blank report that opened after paste.

## 3. Report setup

View > Page view: **Fit to page**. Page size: **16:9** (1280 x 720). Name the pages **Portfolio Overview**, **Risk Drivers**, and **Data Quality**. Do not add slicers for the screenshot pass.

On every visual that uses official measures, set **Filters on this visual**: `segments[segment_type]` is the value in the table below. Do not set a page-level `segment_type` filter on page 1 or 2; cards and charts on the same page need different values. For category charts, use `segments[segment_label]` on the axis, and sort by `segments[sort_order]` ascending (add `sort_order` to the visual, for example as a tooltip, if the sort list does not show it).

## 4. Page 1 — Portfolio Overview

Title text box: `Insurance Portfolio Overview`. Subtitle: `Qlik to Power BI migration  |  freMTPL2 observation book (approximately 2011 to 2013)`.

Eight **Card** visuals in one row. Filter each card: `segment_type` is `portfolio`.

| Title | Field | Expected |
| --- | --- | --- |
| Policies | `Policy Count` | 678,013 |
| Exposure | `Exposure` | 358,499.45 |
| Claim Count | `Claim Count` | 36,102 |
| Claim Frequency | `Claim Frequency` | 0.100703 |
| Average Severity | `Average Severity` | 2,265.51 |
| Pure Premium | `Pure Premium` | 167.11 |
| Policies With Claims % | `Policies With Claims %` | 5.02% |
| Matched Claim Amount | `Matched Claim Amount` | 59,909,216.50 |

Three charts in one row:

| Type | Axis | Values | Filter `segment_type` | Title | Sort |
| --- | --- | --- | --- | --- | --- |
| Clustered column chart | `segment_label` | `Claim Frequency` | `area` | Claim Frequency by Area | `sort_order` ascending |
| Clustered bar chart | `segment_label` | `Pure Premium` | `region` | Pure Premium by Region | `Pure Premium` descending |
| Clustered column chart | `segment_label` | `Claim Frequency` | `fuel` | Claim Frequency by Fuel Type | `sort_order` ascending |

Bottom left, a **Table**: `segment_label`, `Policy Count`, `Exposure`, `Claim Frequency`, `Average Severity`, `Pure Premium`. Filter: `segment_type` is `area`. Title: `Area`.

Bottom right, a **Text box**: `These figures are for the public freMTPL2 observation book, approximately 2011 to 2013. They are not a live Guidewire extract. Claim Frequency uses Claim Count, not the severity row count. Average Severity and Pure Premium use matched claim amounts only. There is no Loss Ratio measure because the source has no premium.`

## 5. Page 2 — Risk Drivers

Title: `Risk Drivers`. Subtitle: `Claim frequency by driver, vehicle, territory, and bonus malus. New vehicles have a large missing severity gap.`

Six charts, two rows of three. Each uses `Claim Frequency` (except where noted), axis `segment_label`, and a visual filter on `segment_type`.

| Type | Filter `segment_type` | Title | Sort |
| --- | --- | --- | --- |
| Clustered bar chart | `driver_age_band` | Claim Frequency by Driver Age | `sort_order` ascending |
| Clustered bar chart | `vehicle_age_band` | Claim Frequency by Vehicle Age | `sort_order` ascending |
| Clustered column chart | `vehicle_power` | Claim Frequency by Vehicle Power | `sort_order` ascending |
| Clustered column chart | `area` | Claim Frequency by Area | `sort_order` ascending |
| Clustered bar chart | `region` | Claim Frequency by Region | `Claim Frequency` descending |
| Clustered bar chart | `bonus_malus_band` | Claim Frequency by Bonus Malus | `sort_order` ascending |

On these charts, add tooltips: `Average Severity`, `Pure Premium`, `Claim Count`, `Matched Severity Rows`, `Exposure`, `Policy Count`.

Bottom, a **Table**: `segment_label`, `Policy Count`, `Exposure`, `Claim Count`, `Matched Severity Rows`, `Claim Frequency`, `Average Severity`, `Pure Premium`. Filter: `segment_type` is `vehicle_age_band`. Title: `Vehicle age band: compare Claim Count with Matched Severity Rows`. Vehicle age `0` should show a large gap (5,205 claim count vs 1,181 matched severity rows).

## 6. Page 3 — Data Quality

Title: `Data Quality and Reconciliation`. Subtitle: `Source issues stay visible. Official Average Severity and Pure Premium exclude orphan claims.`

Two **Card** visuals, filter `segment_type` is `portfolio`: `Matched Claim Amount` (59,909,216.50) and `Matched Severity Rows` (26,444).

One **Table**, filter `segment_type` is `data_quality`. Fields: `segments[segment_label]`, `segments[dq_value]`, `segments[dq_description]`. Title: `Reconciliation checks`. Do not put official measures on this table, and do not SUM `dq_value` (it mixes counts and amounts). You should see 13 rows, including missing severity policies 9,116; missing severity claim units 9,658; orphan rows 195; orphan IDs 6; orphan amount 788,714.18; duplicate amount rows 496; exposure over one year 1,224; extreme claim count 16; count mismatch 1.

Text box: `Matched Claim Amount must equal the claims-fact tie-out 59,909,216.50. Orphan claims (195 rows, 6 IDs, 788,714.18) stay out of official Average Severity and Pure Premium. IDpol 4,158,255 is the one policy with a claim count of 2 and only one severity row.`

## 7. Save and screenshot

1. Rename the report to `Insurance Portfolio` if it is still Untitled.
2. Confirm the eight page 1 cards against the totals above (each card must be filtered to `portfolio`).
3. Screenshot each of the three pages at book level, Fit to page, 1280x800 viewport.
4. Leave **My workspace**.
