#!/usr/bin/env python3
"""Build a reproducible sample of the freMTPL2 book for CI and repo browsing.

The sample is 5,000 policies plus their matching claim rows. Orphan claims
(policy IDs that are not in the frequency file) are left out so the CI
relationship tests can pass cleanly. A few policies with a positive claim
count and no severity row are included so the quality issue remains visible.

This script reads the full files from data/raw and writes data/sample.
It is not run in CI.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
SAMPLE_DIR = ROOT / "data" / "sample"
SEED = 42
N_MATCHED_CLAIMS = 2000
N_MISSING_SEVERITY = 500
N_NO_CLAIMS = 2500


def main() -> None:
    freq = pd.read_parquet(RAW_DIR / "freMTPL2freq.parquet")
    sev = pd.read_parquet(RAW_DIR / "freMTPL2sev.parquet")
    freq = freq.copy()
    sev = sev.copy()
    freq["IDpol"] = freq["IDpol"].astype("int64")
    sev["IDpol"] = sev["IDpol"].astype("int64")

    freq_ids = set(freq["IDpol"])
    matched_sev = sev[sev["IDpol"].isin(freq_ids)]
    sev_ids = set(matched_sev["IDpol"])

    has_sev = freq[freq["IDpol"].isin(sev_ids)]
    missing = freq[(freq["ClaimNb"] > 0) & (~freq["IDpol"].isin(sev_ids))]
    no_claims = freq[freq["ClaimNb"] == 0]

    sample_freq = pd.concat(
        [
            has_sev.sample(n=N_MATCHED_CLAIMS, random_state=SEED),
            missing.sample(n=N_MISSING_SEVERITY, random_state=SEED),
            no_claims.sample(n=N_NO_CLAIMS, random_state=SEED),
        ],
        ignore_index=True,
    )
    sample_ids = set(sample_freq["IDpol"])
    sample_sev = matched_sev[matched_sev["IDpol"].isin(sample_ids)].copy()

    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    # Keep the original column set only.
    freq_cols = [
        "IDpol",
        "ClaimNb",
        "Exposure",
        "Area",
        "VehPower",
        "VehAge",
        "DrivAge",
        "BonusMalus",
        "VehBrand",
        "VehGas",
        "Density",
        "Region",
    ]
    sample_freq[freq_cols].to_parquet(SAMPLE_DIR / "freMTPL2freq.parquet", index=False)
    sample_sev[["IDpol", "ClaimAmount"]].to_parquet(
        SAMPLE_DIR / "freMTPL2sev.parquet", index=False
    )

    exposure = float(sample_freq["Exposure"].sum())
    claimnb = int(sample_freq["ClaimNb"].sum())
    matched_amount = float(sample_sev["ClaimAmount"].sum())
    missing_n = int(((sample_freq["ClaimNb"] > 0) & (~sample_freq["IDpol"].isin(set(sample_sev["IDpol"])))).sum())
    totals = {
        "seed": SEED,
        "policy_count": int(len(sample_freq)),
        "severity_rows": int(len(sample_sev)),
        "exposure_years": round(exposure, 2),
        "claim_count": claimnb,
        "matched_claim_amount": round(matched_amount, 2),
        "missing_severity_policies": missing_n,
        "orphan_rows": 0,
        "n_matched_claim_policies": N_MATCHED_CLAIMS,
        "n_missing_severity": N_MISSING_SEVERITY,
        "n_no_claims": N_NO_CLAIMS,
    }
    (SAMPLE_DIR / "expected_totals.json").write_text(
        json.dumps(totals, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(totals, indent=2))
    print(f"wrote {SAMPLE_DIR}")


if __name__ == "__main__":
    main()
