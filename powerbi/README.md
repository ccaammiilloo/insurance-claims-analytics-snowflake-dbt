# Insurance Portfolio Power BI project

This folder is a Power BI Project (PBIP) for Power BI Desktop. Open `InsurancePortfolio.pbip`, enter your Snowflake username and password when Desktop prompts you, then refresh. There are no credentials in these files.

The semantic model is TMDL. The report is PBIR, with three pages: Portfolio Overview, Risk Drivers, and Data Quality. The source is the Snowflake connector in import mode, using warehouse `COMPUTE_WH`, database `INSURANCE_PORTFOLIO`, schema `MARTS`, and role `INSURANCE_PBI_READONLY`.

Spanish step by step instructions are in `docs/powerbi_abrir_es.md`. The expected totals after refresh are in `docs/powerbi_expected_numbers.md` and in `EXPECTED_NUMBERS.md` inside the zip.

`MART_RISK_SEGMENTS` is imported as a disconnected reference table. `SEEDS.REGION_NAMES` is not imported, because `REGION_NAME` is already on `DIM_POLICY`. There is no date table and no Loss Ratio measure.
