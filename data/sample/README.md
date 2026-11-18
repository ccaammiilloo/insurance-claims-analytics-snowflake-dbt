# Committed sample

This sample is a reproducible subset of freMTPL2, built by `scripts/build_sample.py` with random seed 42.

It contains:

- 2,000 policies that have at least one matching severity row
- 500 policies with a positive `ClaimNb` and no severity row
- 2,500 policies with `ClaimNb` equal to 0
- The severity rows that match those 5,000 policies

Orphan claims (severity rows whose policy ID is not in the frequency file) are not included. GitHub Actions loads this sample into DuckDB and runs dbt against it. Book totals in `docs/data_profile.md` and the project README come from the full files, not from this sample. The expected sample totals are in `expected_totals.json`.
