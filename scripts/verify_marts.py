#!/usr/bin/env python3
"""Compare mart totals to expected values from the data profile or the sample."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = Path(os.environ.get("DUCKDB_PATH", ROOT / "data" / "warehouse" / "insurance.duckdb"))

FULL_EXPECTED = {
    "policy_count": 678013,
    "exposure_years": 358499.45,
    "claim_count": 36102,
    "matched_claim_amount": 59909216.50,
    "missing_severity_policies": 9116,
    "orphan_rows": 195,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Reconcile DuckDB marts to expected totals.")
    parser.add_argument(
        "--scope",
        choices=["full", "sample"],
        default=os.environ.get("BOOK_SCOPE", "full"),
        help="full uses the documented book totals. sample uses data/sample/expected_totals.json.",
    )
    parser.add_argument(
        "--expected",
        default=os.environ.get("EXPECTED_TOTALS", ""),
        help="Optional path to a JSON file of expected totals.",
    )
    return parser.parse_args()


def load_expected(scope: str, expected_path: str) -> dict:
    if expected_path:
        path = Path(expected_path)
    elif scope == "sample":
        path = ROOT / "data" / "sample" / "expected_totals.json"
    else:
        return dict(FULL_EXPECTED)
    data = json.loads(path.read_text(encoding="utf-8"))
    return {
        "policy_count": int(data["policy_count"]),
        "exposure_years": float(data["exposure_years"]),
        "claim_count": int(data["claim_count"]),
        "matched_claim_amount": float(data["matched_claim_amount"]),
        "missing_severity_policies": int(data["missing_severity_policies"]),
        "orphan_rows": int(data.get("orphan_rows", 0)),
    }


def main() -> int:
    args = parse_args()
    expected = load_expected(args.scope, args.expected)
    if not DB_PATH.exists():
        print(f"DuckDB file not found: {DB_PATH}", file=sys.stderr)
        return 1
    con = duckdb.connect(str(DB_PATH), read_only=True)
    row = con.execute(
        """
        select
            count(*) as policy_count,
            round(sum(exposure_years), 2) as exposure_years,
            sum(claim_count) as claim_count,
            round(sum(matched_claim_amount), 2) as matched_claim_amount
        from marts.fct_policy_exposure
        """
    ).fetchall()[0]
    claims = con.execute(
        """
        select
            count(*) as claim_rows,
            count(*) filter (where is_orphan_claim) as orphan_rows,
            round(sum(claim_amount) filter (where not is_orphan_claim), 2) as matched_from_claims
        from marts.fct_claims
        """
    ).fetchall()[0]
    missing = con.execute(
        """
        select count(*)
        from intermediate.int_policy_claim_reconciliation
        where has_missing_severity
        """
    ).fetchall()[0][0]
    con.close()

    actual = {
        "policy_count": int(row[0]),
        "exposure_years": float(row[1]),
        "claim_count": int(row[2]),
        "matched_claim_amount": float(row[3]),
        "missing_severity_policies": int(missing),
        "orphan_rows": int(claims[1]),
    }
    print(f"scope={args.scope}")
    print("fct_policy_exposure totals")
    ok = True
    for key in (
        "policy_count",
        "exposure_years",
        "claim_count",
        "matched_claim_amount",
        "missing_severity_policies",
        "orphan_rows",
    ):
        value = actual[key]
        exp = expected[key]
        match = value == exp
        ok = ok and match
        print(f"  {key}: {value} (expected {exp}) {'OK' if match else 'MISMATCH'}")
    print(
        f"fct_claims: rows={claims[0]}, orphan_rows={claims[1]}, "
        f"matched_amount={claims[2]}"
    )
    if float(claims[2]) != expected["matched_claim_amount"]:
        ok = False
        print("MISMATCH: fct_claims matched amount does not equal the expected total.")
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
