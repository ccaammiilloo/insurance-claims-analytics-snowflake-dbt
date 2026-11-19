#!/usr/bin/env python3
"""Build a long-format paste table for Power BI Service Enter data."""

from __future__ import annotations

import csv
import sys
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from snowflake_env import load_snowflake_env  # noqa: E402

OUT_DIR = ROOT / "powerbi" / "service"
TSV = OUT_DIR / "pbi_paste_table.tsv"
CSV_PATH = OUT_DIR / "pbi_paste_table.csv"

EXPECTED = {
    "policy_count": 678013,
    "exposure": Decimal("358499.45"),
    "claim_count": 36102,
    "matched_claim_amount": Decimal("59909216.50"),
    "matched_severity_rows": 26444,
    "policies_with_claims": 34060,
}

MONEY = Decimal("0.01")
COLUMNS = [
    "segment_type",
    "segment_label",
    "sort_order",
    "policy_count",
    "exposure",
    "claim_count",
    "matched_claim_amount",
    "matched_severity_rows",
    "policies_with_claims",
    "dq_value",
    "dq_description",
]

# User-facing segment_type names and SQL grouping expressions
SEGMENT_SPECS = [
    (
        "driver_age_band",
        "d.DRIV_AGE_BAND",
        """CASE d.DRIV_AGE_BAND
            WHEN '18-25' THEN 18 WHEN '26-35' THEN 26 WHEN '36-45' THEN 36
            WHEN '46-55' THEN 46 WHEN '56-65' THEN 56 WHEN '66-75' THEN 66
            WHEN '76+' THEN 76 ELSE 99 END""",
        None,
    ),
    (
        "vehicle_age_band",
        "v.VEH_AGE_BAND",
        """CASE v.VEH_AGE_BAND
            WHEN '0' THEN 0 WHEN '1-4' THEN 1 WHEN '5-9' THEN 5
            WHEN '10-14' THEN 10 WHEN '15-19' THEN 15 WHEN '20+' THEN 20
            ELSE 99 END""",
        None,
    ),
    (
        "area",
        "p.AREA",
        "ASCII(p.AREA) - ASCII('A') + 1",
        None,
    ),
    (
        "region",
        "p.REGION_NAME",
        "TO_NUMBER(SUBSTR(p.REGION, 2))",  # sort by region code; label is name
        "COUNT_IF(p.REGION_NAME IS NULL) AS null_labels, COUNT_IF(p.REGION IS NULL) AS null_keys",
    ),
    (
        "vehicle_power",
        "TO_VARCHAR(v.VEH_POWER)",
        "v.VEH_POWER",
        None,
    ),
    (
        "bonus_malus_band",
        "p.BONUS_MALUS_BAND",
        """CASE p.BONUS_MALUS_BAND
            WHEN '50 (maximum bonus)' THEN 50 WHEN '51-80' THEN 51
            WHEN '81-99' THEN 81 WHEN '100 (reference)' THEN 100
            WHEN '101-150' THEN 101 WHEN '151+' THEN 151 ELSE 99 END""",
        None,
    ),
    (
        "fuel",
        "v.VEH_GAS",
        "CASE v.VEH_GAS WHEN 'Diesel' THEN 1 WHEN 'Regular' THEN 2 ELSE 99 END",
        None,
    ),
]


def money(value) -> Decimal:
    return Decimal(str(value)).quantize(MONEY, rounding=ROUND_HALF_UP)


def connect():
    import snowflake.connector

    cfg = load_snowflake_env()
    missing = [k for k in ("SNOWFLAKE_ACCOUNT", "SNOWFLAKE_USER", "SNOWFLAKE_PASSWORD") if not cfg.get(k)]
    if missing:
        raise SystemExit(f"Missing Snowflake settings: {', '.join(missing)}")
    conn = snowflake.connector.connect(
        account=cfg["SNOWFLAKE_ACCOUNT"],
        user=cfg["SNOWFLAKE_USER"],
        password=cfg["SNOWFLAKE_PASSWORD"],
        warehouse=cfg.get("SNOWFLAKE_WAREHOUSE", "COMPUTE_WH"),
        database=cfg.get("SNOWFLAKE_DATABASE", "INSURANCE_PORTFOLIO"),
        role="INSURANCE_PBI_READONLY",
    )
    cur = conn.cursor()
    cur.execute("USE SECONDARY ROLES NONE")
    cur.execute("SELECT CURRENT_ROLE(), CURRENT_WAREHOUSE(), CURRENT_DATABASE()")
    role, wh, db = cur.fetchone()
    print(f"session role={role} warehouse={wh} database={db}")
    return conn, cur


def fetchone_dict(cur, sql: str) -> dict:
    cur.execute(sql)
    cols = [d[0].lower() for d in cur.description]
    return dict(zip(cols, cur.fetchone()))


def fetchall_dicts(cur, sql: str) -> list[dict]:
    cur.execute(sql)
    cols = [d[0].lower() for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


BASE_FROM = """
FROM INSURANCE_PORTFOLIO.MARTS.FCT_POLICY_EXPOSURE AS e
INNER JOIN INSURANCE_PORTFOLIO.MARTS.DIM_POLICY AS p
    ON e.POLICY_SK = p.POLICY_SK
INNER JOIN INSURANCE_PORTFOLIO.MARTS.DIM_VEHICLE AS v
    ON e.VEHICLE_SK = v.VEHICLE_SK
INNER JOIN INSURANCE_PORTFOLIO.MARTS.DIM_DRIVER AS d
    ON e.DRIVER_SK = d.DRIVER_SK
"""

METRICS = """
    COUNT(*) AS policy_count,
    CAST(SUM(e.EXPOSURE_YEARS) AS NUMBER(18, 8)) AS exposure,
    SUM(e.CLAIM_COUNT) AS claim_count,
    SUM(e.MATCHED_CLAIM_AMOUNT) AS matched_claim_amount,
    SUM(e.SEVERITY_ROW_COUNT) AS matched_severity_rows,
    COUNT_IF(e.CLAIM_COUNT > 0) AS policies_with_claims
"""


def metrics_tuple(row: dict, *, round_exposure: bool = False) -> dict:
    exposure = Decimal(str(row["exposure"]))
    if round_exposure:
        exposure = money(exposure)
    return {
        "policy_count": int(row["policy_count"]),
        "exposure": exposure,
        "claim_count": int(row["claim_count"]),
        "matched_claim_amount": money(row["matched_claim_amount"]),
        "matched_severity_rows": int(row["matched_severity_rows"]),
        "policies_with_claims": int(row["policies_with_claims"]),
    }


def fmt_num(value, places=None):
    if value is None or value == "":
        return ""
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if places is not None:
        d = Decimal(str(value)).quantize(Decimal(10) ** -places, rounding=ROUND_HALF_UP)
        return f"{d:.{places}f}"
    return str(value)


def fact_row(segment_type, label, sort_order, metrics) -> dict:
    return {
        "segment_type": segment_type,
        "segment_label": label,
        "sort_order": int(sort_order),
        "policy_count": metrics["policy_count"],
        "exposure": metrics["exposure"],
        "claim_count": metrics["claim_count"],
        "matched_claim_amount": metrics["matched_claim_amount"],
        "matched_severity_rows": metrics["matched_severity_rows"],
        "policies_with_claims": metrics["policies_with_claims"],
        "dq_value": None,
        "dq_description": None,
    }


def dq_row(label, sort_order, value, description) -> dict:
    return {
        "segment_type": "data_quality",
        "segment_label": label,
        "sort_order": int(sort_order),
        "policy_count": None,
        "exposure": None,
        "claim_count": None,
        "matched_claim_amount": None,
        "matched_severity_rows": None,
        "policies_with_claims": None,
        "dq_value": value,
        "dq_description": description,
    }


def main() -> None:
    conn, cur = connect()
    try:
        portfolio = fetchone_dict(
            cur,
            f"SELECT {METRICS} {BASE_FROM}",
        )
        # null / completeness checks for grouping keys
        completeness = fetchone_dict(
            cur,
            f"""
            SELECT
                COUNT(*) AS row_count,
                COUNT_IF(p.AREA IS NULL) AS null_area,
                COUNT_IF(p.REGION_NAME IS NULL) AS null_region_name,
                COUNT_IF(p.REGION IS NULL) AS null_region,
                COUNT_IF(p.BONUS_MALUS_BAND IS NULL) AS null_bonus_malus,
                COUNT_IF(d.DRIV_AGE_BAND IS NULL) AS null_driv_age,
                COUNT_IF(v.VEH_AGE_BAND IS NULL) AS null_veh_age,
                COUNT_IF(v.VEH_POWER IS NULL) AS null_veh_power,
                COUNT_IF(v.VEH_GAS IS NULL) AS null_veh_gas
            {BASE_FROM}
            """,
        )
        print("completeness", {k: int(v) for k, v in completeness.items()})

        quality_exp = fetchone_dict(
            cur,
            """
            SELECT
                COUNT_IF(HAS_MISSING_SEVERITY) AS policies_missing_severity,
                SUM(MISSING_SEVERITY_CLAIM_UNITS) AS missing_severity_claim_units,
                COUNT_IF(IS_EXPOSURE_GT_ONE) AS exposure_gt_one,
                COUNT_IF(IS_EXTREME_CLAIM_COUNT) AS extreme_claim_count,
                COUNT_IF(HAS_COUNT_MISMATCH_BOTH_POSITIVE) AS count_mismatch
            FROM INSURANCE_PORTFOLIO.MARTS.FCT_POLICY_EXPOSURE
            """,
        )
        quality_cl = fetchone_dict(
            cur,
            """
            SELECT
                COUNT(*) AS claim_rows,
                COUNT_IF(IS_ORPHAN_CLAIM) AS orphan_rows,
                COUNT(DISTINCT CASE WHEN IS_ORPHAN_CLAIM THEN POLICY_ID END) AS orphan_ids,
                SUM(CLAIM_AMOUNT) AS claim_amount_all_rows,
                SUM(IFF(IS_ORPHAN_CLAIM, CLAIM_AMOUNT, 0)) AS orphan_claim_amount,
                SUM(IFF(NOT IS_ORPHAN_CLAIM, CLAIM_AMOUNT, 0)) AS matched_from_claims,
                COUNT_IF(NOT IS_ORPHAN_CLAIM) AS matched_claim_rows,
                COUNT_IF(IS_DUPLICATE_AMOUNT_ROW) AS duplicate_amount_rows
            FROM INSURANCE_PORTFOLIO.MARTS.FCT_CLAIMS
            """,
        )

        segment_rows: dict[str, list[dict]] = {}
        for name, label_expr, sort_expr, _extra in SEGMENT_SPECS:
            sql = f"""
                SELECT
                    {label_expr} AS segment_label,
                    {sort_expr} AS sort_order,
                    {METRICS}
                {BASE_FROM}
                GROUP BY 1, 2
                ORDER BY 2, 1
            """
            segment_rows[name] = fetchall_dicts(cur, sql)
            print(f"{name} groups={len(segment_rows[name])}")
    finally:
        cur.close()
        conn.close()

    port = metrics_tuple(portfolio, round_exposure=True)
    print("portfolio", {k: (str(v) if isinstance(v, Decimal) else v) for k, v in port.items()})
    for key, expected in EXPECTED.items():
        if port[key] != expected:
            raise SystemExit(f"Portfolio {key} {port[key]} != official {expected}")

    checks = []
    metric_keys = list(EXPECTED)
    for name, rows in segment_rows.items():
        summed = {
            "policy_count": sum(int(r["policy_count"]) for r in rows),
            "exposure": money(sum((Decimal(str(r["exposure"])) for r in rows), Decimal("0"))),
            "claim_count": sum(int(r["claim_count"]) for r in rows),
            "matched_claim_amount": money(sum((Decimal(str(r["matched_claim_amount"])) for r in rows), Decimal("0"))),
            "matched_severity_rows": sum(int(r["matched_severity_rows"]) for r in rows),
            "policies_with_claims": sum(int(r["policies_with_claims"]) for r in rows),
        }
        mismatches = {k: (summed[k], port[k]) for k in metric_keys if summed[k] != port[k]}
        nulls_in_label = any(r["segment_label"] is None or r["segment_label"] == "" for r in rows)
        checks.append(
            {
                "segment_type": name,
                "groups": len(rows),
                "ok": not mismatches and not nulls_in_label,
                "mismatches": {k: (str(a), str(e)) for k, (a, e) in mismatches.items()},
                "null_labels": nulls_in_label,
            }
        )
        status = "OK" if not mismatches else f"MISMATCH {mismatches}"
        print(f"sum {name}: {status}")

    rows_out: list[dict] = []
    rows_out.append(fact_row("portfolio", "Book total", 0, port))
    for name, _label, _sort, _ in SEGMENT_SPECS:
        for r in segment_rows[name]:
            rows_out.append(fact_row(name, str(r["segment_label"]), r["sort_order"], metrics_tuple(r)))

    dq = [
        dq_row("Policies with missing severity", 1, int(quality_exp["policies_missing_severity"]), "Policies with a claim count greater than 0 and no severity row."),
        dq_row("Missing severity claim units", 2, int(quality_exp["missing_severity_claim_units"]), "Claim units with no matching severity row, including the one extra unit from the count-mismatch policy."),
        dq_row("Policies with count mismatch", 3, int(quality_exp["count_mismatch"]), "Policies where claim count and severity row count are both positive and different. This is IDpol 4158255 (claim count 2, one severity row)."),
        dq_row("Orphan claim rows", 4, int(quality_cl["orphan_rows"]), "Severity rows with no matching policy. Excluded from official average severity and pure premium."),
        dq_row("Orphan claim IDs", 5, int(quality_cl["orphan_ids"]), "Distinct policy IDs that appear only in the severity file."),
        dq_row("Orphan claim amount", 6, money(quality_cl["orphan_claim_amount"]), "Claim amount on orphan severity rows. Not included in official matched claim amount."),
        dq_row("Duplicate amount rows", 7, int(quality_cl["duplicate_amount_rows"]), "Severity rows flagged IS_DUPLICATE_AMOUNT_ROW."),
        dq_row("Exposure over one year", 8, int(quality_exp["exposure_gt_one"]), "Policies whose exposure is greater than one year. The maximum exposure is 2.01 years."),
        dq_row("Extreme claim count policies", 9, int(quality_exp["extreme_claim_count"]), "Policies flagged with an extreme claim count (ClaimNb of 4 or more)."),
        dq_row("Claim rows (all)", 10, int(quality_cl["claim_rows"]), "All severity rows in FCT_CLAIMS, including orphans."),
        dq_row("Matched severity rows", 11, int(quality_cl["matched_claim_rows"]), "Non-orphan severity rows. Must equal official matched severity rows."),
        dq_row("Matched claim amount (from claims)", 12, money(quality_cl["matched_from_claims"]), "Sum of claim amount on non-orphan rows. Must equal official matched claim amount."),
        dq_row("Claim amount all rows", 13, money(quality_cl["claim_amount_all_rows"]), "Matched claim amount plus orphan claim amount."),
    ]
    rows_out.extend(dq)

    if len(rows_out) > 150:
        raise SystemExit(f"Too many rows: {len(rows_out)}")
    if len(COLUMNS) > 12:
        raise SystemExit(f"Too many columns: {len(COLUMNS)}")

    # Write TSV and CSV with plain numbers
    def cell(col, rec):
        val = rec[col]
        if col == "matched_claim_amount":
            return fmt_num(val, 2)
        if col == "exposure":
            # Keep extra decimals so group SUMs still round to 358499.45.
            # Rounding each group to 2 decimals first can be off by 0.01.
            if val is None or val == "":
                return ""
            if rec.get("segment_type") == "portfolio":
                return fmt_num(val, 2)
            return fmt_num(val, 8)
        if col == "dq_value":
            if val is None:
                return ""
            if isinstance(val, Decimal) or (isinstance(val, float)):
                return fmt_num(val, 2)
            return fmt_num(val)
        if col in {"policy_count", "claim_count", "matched_severity_rows", "policies_with_claims", "sort_order"}:
            return fmt_num(val)
        if val is None:
            return ""
        return str(val)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with TSV.open("w", encoding="utf-8", newline="\n") as f:
        f.write("\t".join(COLUMNS) + "\n")
        for rec in rows_out:
            f.write("\t".join(cell(c, rec) for c in COLUMNS) + "\n")

    with CSV_PATH.open("w", encoding="utf-8", newline="\n") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(COLUMNS)
        for rec in rows_out:
            writer.writerow([cell(c, rec) for c in COLUMNS])

    # Re-read TSV and verify additive sums + official portfolio row
    import pandas as pd

    parsed = pd.read_csv(TSV, sep="\t", dtype=str, keep_default_na=False)
    if list(parsed.columns) != COLUMNS:
        raise SystemExit(f"TSV columns {list(parsed.columns)}")
    if len(parsed) != len(rows_out):
        raise SystemExit(f"TSV row count {len(parsed)}")

    def col_sum(frame, col, places=None):
        vals = [Decimal(v) for v in frame[col] if v != ""]
        total = sum(vals, Decimal("0"))
        if places is not None:
            return total.quantize(Decimal(10) ** -places, rounding=ROUND_HALF_UP)
        return int(total) if all(v == v.to_integral() for v in vals) else total

    port_row = parsed[parsed["segment_type"] == "portfolio"]
    if len(port_row) != 1:
        raise SystemExit("Expected one portfolio row")
    pr = port_row.iloc[0]
    got_port = {
        "policy_count": int(pr["policy_count"]),
        "exposure": money(pr["exposure"]),
        "claim_count": int(pr["claim_count"]),
        "matched_claim_amount": money(pr["matched_claim_amount"]),
        "matched_severity_rows": int(pr["matched_severity_rows"]),
        "policies_with_claims": int(pr["policies_with_claims"]),
    }
    for k, exp in EXPECTED.items():
        if got_port[k] != exp:
            raise SystemExit(f"TSV portfolio {k} {got_port[k]} != {exp}")

    print("--- verification ---")
    print(f"rows={len(parsed)} cols={len(parsed.columns)}")
    for name in [s[0] for s in SEGMENT_SPECS]:
        sub = parsed[parsed["segment_type"] == name]
        summed = {
            "policy_count": col_sum(sub, "policy_count"),
            "exposure_raw": col_sum(sub, "exposure"),
            "exposure": col_sum(sub, "exposure", 2),
            "claim_count": col_sum(sub, "claim_count"),
            "matched_claim_amount": col_sum(sub, "matched_claim_amount", 2),
            "matched_severity_rows": col_sum(sub, "matched_severity_rows"),
            "policies_with_claims": col_sum(sub, "policies_with_claims"),
        }
        # Official exposure is the 2-decimal rounded book total.
        ok = all(summed[k] == EXPECTED[k] for k in EXPECTED)
        print(
            f"{name}: groups={len(sub)} exposure_raw={summed['exposure_raw']} "
            f"{'OK' if ok else 'FAIL ' + str(summed)}"
        )
        if not ok:
            raise SystemExit(f"{name} does not sum to portfolio")

    dq_parsed = parsed[parsed["segment_type"] == "data_quality"]
    if any(dq_parsed[c].astype(str).str.len().gt(0).any() for c in [
        "policy_count", "exposure", "claim_count", "matched_claim_amount",
        "matched_severity_rows", "policies_with_claims",
    ]):
        raise SystemExit("data_quality rows must leave additive fact columns blank")
    print(f"data_quality: rows={len(dq_parsed)} fact_cols_blank=OK")
    print(f"wrote {TSV} bytes={TSV.stat().st_size}")
    print(f"wrote {CSV_PATH} bytes={CSV_PATH.stat().st_size}")
    # counts by type
    print("rows_by_type")
    print(parsed["segment_type"].value_counts().to_string())
    print("CHECKS", checks)
    print("OK")


if __name__ == "__main__":
    main()
