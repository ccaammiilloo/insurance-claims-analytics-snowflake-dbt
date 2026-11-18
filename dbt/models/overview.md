{% docs __overview__ %}
This dbt project turns the public freMTPL2 policy and claims files into a star schema for Power BI. The raw tables are built by scripts/load_raw.py. Staging models clean types and add quality flags. An intermediate model reconciles policy claim counts with severity rows. Marts are the tables that Power BI should import.

The default target is DuckDB. A Snowflake prod profile reads account settings from environment variables and never stores a password in the repo. Until those credentials are available, all builds run locally or in GitHub Actions on DuckDB.

Official book totals come from docs/data_profile.md and are asserted by tests: 678013 policies, 358499.45 exposure years, 36102 claims, and 59909216.50 matched claim amount. There is no premium in the source, so the project does not compute a loss ratio.
{% enddocs %}
