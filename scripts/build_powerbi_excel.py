#!/usr/bin/env python3
"""Export Snowflake MARTS to an Excel workbook for Power BI Service.

Uses role INSURANCE_PBI_READONLY. Never writes credentials into the workbook
or prints the password.
"""

from __future__ import annotations

import sys
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from snowflake_env import load_snowflake_env  # noqa: E402

OUT = ROOT / "powerbi" / "service" / "insurance_marts_powerbi.xlsx"

EXPECTED = {
    "policy_count": 678013,
    "exposure": Decimal("358499.45"),
    "claim_count": 36102,
    "matched_claim_amount": Decimal("59909216.50"),
    "average_severity": Decimal("2265.51"),
    "pure_premium": Decimal("167.11"),
    "policies_with_claims": 34060,
}

POLICY_COLUMNS = [
    "idpol",
    "exposure",
    "claim_count",
    "matched_claim_amount",
    "matched_severity_rows",
    "has_claim",
    "region_name",
    "area",
    "driv_age_band",
    "veh_age_band",
    "veh_power",
    "veh_brand",
    "veh_gas",
    "bonus_malus_band",
    "density_band",
]

MONEY = Decimal("0.01")
SIX = Decimal("0.000001")


def money(value) -> Decimal:
    return Decimal(str(value)).quantize(MONEY, rounding=ROUND_HALF_UP)


def six_dec(value) -> Decimal:
    return Decimal(str(value)).quantize(SIX, rounding=ROUND_HALF_UP)


def connect():
    import snowflake.connector

    cfg = load_snowflake_env()
    missing = [k for k in ("SNOWFLAKE_ACCOUNT", "SNOWFLAKE_USER", "SNOWFLAKE_PASSWORD", "SNOWFLAKE_WAREHOUSE") if not cfg.get(k)]
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


def fetch_policy_exposure(cur):
    import pandas as pd

    sql = """
        SELECT
            e.POLICY_ID AS idpol,
            e.EXPOSURE_YEARS AS exposure,
            e.CLAIM_COUNT AS claim_count,
            e.MATCHED_CLAIM_AMOUNT AS matched_claim_amount,
            e.SEVERITY_ROW_COUNT AS matched_severity_rows,
            IFF(e.CLAIM_COUNT > 0, 1, 0) AS has_claim,
            p.REGION_NAME AS region_name,
            p.AREA AS area,
            d.DRIV_AGE_BAND AS driv_age_band,
            v.VEH_AGE_BAND AS veh_age_band,
            v.VEH_POWER AS veh_power,
            v.VEH_BRAND AS veh_brand,
            v.VEH_GAS AS veh_gas,
            p.BONUS_MALUS_BAND AS bonus_malus_band,
            CASE p.AREA
                WHEN 'A' THEN 'A (rural)'
                WHEN 'F' THEN 'F (urban centre)'
                ELSE p.AREA
            END AS density_band
        FROM INSURANCE_PORTFOLIO.MARTS.FCT_POLICY_EXPOSURE AS e
        INNER JOIN INSURANCE_PORTFOLIO.MARTS.DIM_POLICY AS p
            ON e.POLICY_SK = p.POLICY_SK
        INNER JOIN INSURANCE_PORTFOLIO.MARTS.DIM_VEHICLE AS v
            ON e.VEHICLE_SK = v.VEHICLE_SK
        INNER JOIN INSURANCE_PORTFOLIO.MARTS.DIM_DRIVER AS d
            ON e.DRIVER_SK = d.DRIVER_SK
        ORDER BY e.POLICY_ID
    """
    cur.execute(sql)
    df = cur.fetch_pandas_all()
    df.columns = [c.lower() for c in df.columns]
    missing = [c for c in POLICY_COLUMNS if c not in df.columns]
    if missing:
        raise SystemExit(f"policy_exposure missing columns: {missing}")
    df = df[POLICY_COLUMNS]
    return df


def fetch_risk_segments(cur):
    cur.execute(
        """
        SELECT
            SEGMENT_TYPE AS segment_type,
            SEGMENT_VALUE AS segment_value,
            SEGMENT_LABEL AS segment_label,
            POLICY_COUNT AS policy_count,
            EXPOSURE_YEARS AS exposure_years,
            CLAIM_COUNT AS claim_count,
            CLAIM_FREQUENCY AS claim_frequency,
            SEVERITY_ROW_COUNT AS severity_row_count,
            MATCHED_CLAIM_AMOUNT AS matched_claim_amount,
            AVERAGE_SEVERITY AS average_severity,
            PURE_PREMIUM AS pure_premium
        FROM INSURANCE_PORTFOLIO.MARTS.MART_RISK_SEGMENTS
        ORDER BY SEGMENT_TYPE, SEGMENT_VALUE
        """
    )
    df = cur.fetch_pandas_all()
    df.columns = [c.lower() for c in df.columns]
    return df


def fetch_quality_and_claims(cur) -> dict:
    cur.execute(
        """
        SELECT
            COUNT(*) AS policy_count,
            SUM(EXPOSURE_YEARS) AS exposure,
            SUM(CLAIM_COUNT) AS claim_count,
            SUM(MATCHED_CLAIM_AMOUNT) AS matched_claim_amount,
            SUM(SEVERITY_ROW_COUNT) AS matched_severity_rows,
            COUNT_IF(CLAIM_COUNT > 0) AS policies_with_claims,
            COUNT_IF(HAS_MISSING_SEVERITY) AS policies_missing_severity,
            SUM(MISSING_SEVERITY_CLAIM_UNITS) AS missing_severity_claim_units,
            COUNT_IF(IS_EXPOSURE_GT_ONE) AS exposure_gt_one,
            COUNT_IF(IS_EXTREME_CLAIM_COUNT) AS extreme_claim_count,
            COUNT_IF(HAS_COUNT_MISMATCH_BOTH_POSITIVE) AS count_mismatch_both_positive
        FROM INSURANCE_PORTFOLIO.MARTS.FCT_POLICY_EXPOSURE
        """
    )
    exp_cols = [d[0].lower() for d in cur.description]
    exp = dict(zip(exp_cols, cur.fetchone()))
    cur.execute(
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
        """
    )
    cl_cols = [d[0].lower() for d in cur.description]
    claims = dict(zip(cl_cols, cur.fetchone()))
    return {"exposure": exp, "claims": claims}


def build_quality_frame(stats: dict):
    import pandas as pd

    e, c = stats["exposure"], stats["claims"]
    rows = [
        (
            "Policies with missing severity",
            int(e["policies_missing_severity"]),
            "Policies with a claim count greater than 0 and no severity row.",
        ),
        (
            "Missing severity claim units",
            int(e["missing_severity_claim_units"]),
            "Claim units with no matching severity row, including the one extra unit from the count-mismatch policy.",
        ),
        (
            "Policies with count mismatch",
            int(e["count_mismatch_both_positive"]),
            "Policies where claim count and severity row count are both positive and different. This is IDpol 4158255 (claim count 2, one severity row).",
        ),
        (
            "Orphan claim rows",
            int(c["orphan_rows"]),
            "Severity rows with no matching policy. Excluded from official average severity and pure premium.",
        ),
        (
            "Orphan claim IDs",
            int(c["orphan_ids"]),
            "Distinct policy IDs that appear only in the severity file.",
        ),
        (
            "Orphan claim amount",
            float(money(c["orphan_claim_amount"])),
            "Claim amount on orphan severity rows. Not included in official matched claim amount.",
        ),
        (
            "Duplicate amount rows",
            int(c["duplicate_amount_rows"]),
            "Severity rows flagged IS_DUPLICATE_AMOUNT_ROW.",
        ),
        (
            "Exposure over one year",
            int(e["exposure_gt_one"]),
            "Policies whose exposure is greater than one year. The maximum exposure is 2.01 years.",
        ),
        (
            "Extreme claim count policies",
            int(e["extreme_claim_count"]),
            "Policies flagged with an extreme claim count (ClaimNb of 4 or more).",
        ),
        (
            "Claim rows (all)",
            int(c["claim_rows"]),
            "All severity rows in FCT_CLAIMS, including orphans.",
        ),
        (
            "Matched severity rows",
            int(c["matched_claim_rows"]),
            "Non-orphan severity rows. Must equal SUM(policy_exposure[matched_severity_rows]).",
        ),
        (
            "Matched claim amount (from claims)",
            float(money(c["matched_from_claims"])),
            "Sum of claim amount on non-orphan rows. Must equal SUM(policy_exposure[matched_claim_amount]).",
        ),
        (
            "Claim amount all rows",
            float(money(c["claim_amount_all_rows"])),
            "Matched claim amount plus orphan claim amount.",
        ),
    ]
    return pd.DataFrame(rows, columns=["check_name", "value", "description"])


def build_kpi_frame(policy_totals: dict, stats: dict):
    import pandas as pd

    e = stats["exposure"]
    t = policy_totals
    rows = [
        ("Policy Count", int(t["policy_count"]), "COUNTROWS of policy_exposure. Official book total is 678,013."),
        ("Exposure", float(t["exposure"]), "SUM of exposure. Official book total is 358,499.45 policy years."),
        ("Claim Count", int(t["claim_count"]), "SUM of claim_count (ClaimNb), not severity row count. Official book total is 36,102."),
        ("Claim Frequency", float(t["claim_frequency"]), "Claim Count / Exposure. Official book total is 0.100703. This is claims per year, not a percentage."),
        ("Matched Claim Amount", float(t["matched_claim_amount"]), "SUM of matched_claim_amount. Official book total is 59,909,216.50."),
        ("Matched Severity Rows", int(t["matched_severity_rows"]), "SUM of matched_severity_rows. Official book total is 26,444."),
        ("Average Severity", float(t["average_severity"]), "Matched Claim Amount / Matched Severity Rows. Official book total is 2,265.51."),
        ("Pure Premium", float(t["pure_premium"]), "Matched Claim Amount / Exposure. Official book total is 167.11. There is no loss ratio because the source has no premium."),
        ("Policies With Claims", int(t["policies_with_claims"]), "SUM of has_claim. Official book total is 34,060."),
        ("Policies With Claims %", float(t["policies_with_claims_pct"]), "Policies With Claims / Policy Count. Official book total is 5.02%."),
    ]
    # Cross-check the Snowflake fact totals against the frame we will write
    assert int(e["policy_count"]) == t["policy_count"]
    return pd.DataFrame(rows, columns=["kpi_name", "value", "description"])


def policy_totals_from_df(df) -> dict:
    policy_count = int(len(df))
    exposure = money(df["exposure"].sum())
    claim_count = int(df["claim_count"].sum())
    matched_amount = money(df["matched_claim_amount"].sum())
    matched_rows = int(df["matched_severity_rows"].sum())
    policies_with_claims = int(df["has_claim"].sum())
    return {
        "policy_count": policy_count,
        "exposure": exposure,
        "claim_count": claim_count,
        "matched_claim_amount": matched_amount,
        "matched_severity_rows": matched_rows,
        "policies_with_claims": policies_with_claims,
        "claim_frequency": six_dec(Decimal(claim_count) / Decimal(exposure)),
        "average_severity": money(Decimal(matched_amount) / Decimal(matched_rows)),
        "pure_premium": money(Decimal(matched_amount) / Decimal(exposure)),
        "policies_with_claims_pct": six_dec(Decimal(policies_with_claims) / Decimal(policy_count)),
    }


def assert_expected(totals: dict) -> None:
    checks = [
        ("policy_count", totals["policy_count"], EXPECTED["policy_count"]),
        ("exposure", totals["exposure"], EXPECTED["exposure"]),
        ("claim_count", totals["claim_count"], EXPECTED["claim_count"]),
        ("matched_claim_amount", totals["matched_claim_amount"], EXPECTED["matched_claim_amount"]),
        ("average_severity", totals["average_severity"], EXPECTED["average_severity"]),
        ("pure_premium", totals["pure_premium"], EXPECTED["pure_premium"]),
        ("policies_with_claims", totals["policies_with_claims"], EXPECTED["policies_with_claims"]),
    ]
    failed = [(n, a, e) for n, a, e in checks if a != e]
    if failed:
        raise SystemExit(f"Totals do not match official book values: {failed}")


def _cell(value):
    if value is None:
        return None
    try:
        if value != value:  # NaN
            return None
    except Exception:
        pass
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, Decimal):
        return float(value)
    return value


def write_table(workbook, sheet_name, table_name, df) -> None:
    ws = workbook.add_worksheet(sheet_name)
    ws.freeze_panes(1, 0)
    headers = list(df.columns)
    # Write header and data, then define a ListObject over that range.
    for col, name in enumerate(headers):
        ws.write(0, col, name)
    values = df.to_numpy(dtype=object)
    n = len(df)
    for r in range(n):
        row = values[r]
        for c in range(len(headers)):
            v = _cell(row[c])
            if v is None:
                continue
            ws.write(r + 1, c, v)
    last_row = max(n, 1)  # table needs a header; one empty data row if needed
    if n == 0:
        last_row = 1
    else:
        last_row = n
    ws.add_table(
        0,
        0,
        last_row,
        len(headers) - 1,
        {
            "name": table_name,
            "style": "Table Style Medium 2",
            "columns": [{"header": h} for h in headers],
            "header_row": True,
        },
    )
    # Autofit is expensive on the 678k-row sheet; set practical widths instead.
    widths = {
        "idpol": 12,
        "exposure": 12,
        "claim_count": 12,
        "matched_claim_amount": 18,
        "matched_severity_rows": 20,
        "has_claim": 10,
        "region_name": 28,
        "area": 8,
        "driv_age_band": 14,
        "veh_age_band": 14,
        "veh_power": 12,
        "veh_brand": 14,
        "veh_gas": 12,
        "bonus_malus_band": 22,
        "density_band": 18,
        "segment_type": 18,
        "segment_value": 22,
        "segment_label": 28,
        "policy_count": 14,
        "exposure_years": 14,
        "claim_frequency": 14,
        "severity_row_count": 18,
        "average_severity": 16,
        "pure_premium": 14,
        "check_name": 36,
        "value": 16,
        "description": 80,
        "kpi_name": 28,
    }
    for col, name in enumerate(headers):
        ws.set_column(col, col, widths.get(name, 16))
    ws.set_default_row(hide_unused_rows=True)


def write_workbook(path: Path, policy, segments, quality, kpis) -> None:
    import xlsxwriter

    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    workbook = xlsxwriter.Workbook(
        path,
        {
            "strings_to_urls": False,
            "nan_inf_to_errors": True,
            "constant_memory": False,
        },
    )
    try:
        write_table(workbook, "policy_exposure", "policy_exposure", policy)
        write_table(workbook, "risk_segments", "risk_segments", segments)
        write_table(workbook, "data_quality", "data_quality", quality)
        write_table(workbook, "kpi_summary", "kpi_summary", kpis)
    finally:
        workbook.close()


def verify_workbook(path: Path, expected_totals: dict) -> dict:
    import openpyxl

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        tables = {}
        for ws in wb.worksheets:
            names = list(ws.tables.keys()) if hasattr(ws, "tables") else []
            # read_only workbooks may not expose tables the same way
            tables[ws.title] = names
        # Sum policy_exposure from cells
        ws = wb["policy_exposure"]
        rows = ws.iter_rows(min_row=1, values_only=True)
        header = next(rows)
        header = [str(h).lower() if h is not None else "" for h in header]
        idx = {name: header.index(name) for name in [
            "exposure", "claim_count", "matched_claim_amount",
            "matched_severity_rows", "has_claim",
        ]}
        n = 0
        exposure = Decimal("0")
        claim_count = 0
        amount = Decimal("0")
        sev_rows = 0
        has_claim = 0
        for row in rows:
            if row is None or all(v is None for v in row):
                continue
            n += 1
            exposure += Decimal(str(row[idx["exposure"]]))
            claim_count += int(row[idx["claim_count"]])
            amount += Decimal(str(row[idx["matched_claim_amount"] or 0]))
            sev_rows += int(row[idx["matched_severity_rows"] or 0])
            has_claim += int(row[idx["has_claim"] or 0])
        got = {
            "policy_count": n,
            "exposure": money(exposure),
            "claim_count": claim_count,
            "matched_claim_amount": money(amount),
            "matched_severity_rows": sev_rows,
            "policies_with_claims": has_claim,
            "average_severity": money(amount / Decimal(sev_rows)),
            "pure_premium": money(amount / exposure),
            "claim_frequency": six_dec(Decimal(claim_count) / exposure),
        }
    finally:
        wb.close()

    # Confirm ListObjects exist by reading workbook.xml / table XML from the zip
    import zipfile
    import re

    table_names = set()
    with zipfile.ZipFile(path) as zf:
        for name in zf.namelist():
            if re.search(r"xl/tables/table\d+\.xml$", name):
                xml = zf.read(name).decode("utf-8")
                m = re.search(r'name="([^"]+)"', xml)
                if m:
                    table_names.add(m.group(1))
    needed = {"policy_exposure", "risk_segments", "data_quality", "kpi_summary"}
    if not needed.issubset(table_names):
        raise SystemExit(f"Missing Excel tables {needed - table_names}; found {table_names}")

    assert_expected(got)
    for key in ("policy_count", "exposure", "claim_count", "matched_claim_amount", "policies_with_claims"):
        if got[key] != expected_totals[key]:
            raise SystemExit(f"Workbook {key} {got[key]} != frame {expected_totals[key]}")
    got["excel_tables"] = sorted(table_names)
    return got


def main() -> None:
    # openpyxl is used only to re-read and verify the written workbook
    try:
        import openpyxl  # noqa: F401
    except ImportError:
        raise SystemExit("openpyxl is required to verify the workbook")

    conn, cur = connect()
    try:
        print("fetching policy_exposure")
        policy = fetch_policy_exposure(cur)
        print(f"policy_exposure rows={len(policy)}")
        if len(policy) != EXPECTED["policy_count"]:
            raise SystemExit(f"Unexpected policy row count {len(policy)}")
        print("fetching risk_segments")
        segments = fetch_risk_segments(cur)
        print(f"risk_segments rows={len(segments)}")
        print("fetching quality totals")
        stats = fetch_quality_and_claims(cur)
    finally:
        cur.close()
        conn.close()

    totals = policy_totals_from_df(policy)
    print("frame_totals", {k: (str(v) if isinstance(v, Decimal) else v) for k, v in totals.items()})
    assert_expected(totals)
    quality = build_quality_frame(stats)
    kpis = build_kpi_frame(totals, stats)

    print(f"writing {OUT}")
    write_workbook(OUT, policy, segments, quality, kpis)
    size = OUT.stat().st_size
    print(f"wrote bytes={size}")
    print("verifying workbook sums")
    verified = verify_workbook(OUT, totals)
    print(
        "verified",
        {k: (str(v) if isinstance(v, Decimal) else v) for k, v in verified.items()},
    )
    mb = size / (1024 * 1024)
    if mb >= 100:
        raise SystemExit(f"Workbook is {mb:.1f} MB, over the 100 MB budget")
    print(f"OK path={OUT} size_mb={mb:.2f}")


if __name__ == "__main__":
    main()
