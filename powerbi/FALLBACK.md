# Fallback if the report layer does not open cleanly

The semantic model in `InsurancePortfolio.SemanticModel` is the part to keep. It has the Snowflake import partitions, the star schema relationships, and the official DAX measures.

If Power BI Desktop opens the `.pbip` file and loads the model, but a page or visual shows an error, do this:

1. Stay in the same project. Do not start from a blank `.pbix` unless the file will not open at all.
2. Delete only the broken visual, then add it again from the Data pane. Use the measure names in `docs/power_bi_design.md` and `docs/powerbi_expected_numbers.md`.
3. If the entire report folder fails to open, create a new report in Desktop against this semantic model (File > Open the `.pbip`, or open the model and insert a new report) and rebuild the three pages:
   - Portfolio Overview: KPI cards for Policy Count, Exposure, Claim Count, Claim Frequency, Average Severity, Pure Premium, Policies With Claims %, and Matched Claim Amount, plus segment charts for area, region, and fuel type.
   - Risk Drivers: Claim Frequency by driver age band, vehicle age band, vehicle power, area, region, and bonus malus band, with a table that compares Claim Count and Matched Severity Rows by vehicle age.
   - Data Quality: the quality and reconciliation measures listed in the checklist.
4. After a successful refresh, confirm the checklist totals, then save. You can keep saving as PBIP.

The connection parameters `SnowflakeServer`, `SnowflakeWarehouse`, and `SnowflakeRole` are already in `definition/expressions.tmdl`. You should only need to enter credentials.
