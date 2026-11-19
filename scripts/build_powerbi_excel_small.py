#!/usr/bin/env python3
"""Build a compact Excel workbook for Power BI Service shared capacity.

Aggregates the per-policy extract into policy_segments. Never prints secrets.
"""

from __future__ import annotations

import re
import zipfile
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVICE = ROOT / "powerbi" / "service"
SRC = SERVICE / "insurance_marts_powerbi.xlsx"
OUT = SERVICE / "insurance_marts_powerbi_small.xlsx"

EXPECTED = {
    "policy_count": 678013,
    "exposure": Decimal("358499.45"),
    "claim_count": 36102,
    "matched_claim_amount": Decimal("59909216.50"),
    "matched_severity_rows": 26444,
    "average_severity": Decimal("2265.51"),
    "pure_premium": Decimal("167.11"),
    "policies_with_claims": 34060,
}

# density_band duplicates area (0 extra groups). veh_brand is not used on the
# three planned pages. bonus_malus_band is dropped to get under 50k groups;
# that chart uses risk_segments instead.
DIMS_KEPT = [
    "region_name",
    "area",
    "driv_age_band",
    "veh_age_band",
    "veh_power",
    "veh_gas",
]
DIMS_DROPPED = ["density_band", "veh_brand", "bonus_malus_band"]

MONEY = Decimal("0.01")
SIX = Decimal("0.000001")


def money(value) -> Decimal:
    return Decimal(str(value)).quantize(MONEY, rounding=ROUND_HALF_UP)


def six_dec(value) -> Decimal:
    return Decimal(str(value)).quantize(SIX, rounding=ROUND_HALF_UP)


def load_sheet(path: Path, sheet: str):
    import pandas as pd

    return pd.read_excel(path, sheet_name=sheet, engine="openpyxl")


def aggregate(policy):
    import pandas as pd

    grouped = (
        policy.groupby(DIMS_KEPT, dropna=False, as_index=False, sort=True)
        .agg(
            policy_count=("idpol", "size"),
            exposure=("exposure", "sum"),
            claim_count=("claim_count", "sum"),
            matched_claim_amount=("matched_claim_amount", "sum"),
            matched_severity_rows=("matched_severity_rows", "sum"),
            policies_with_claims=("has_claim", "sum"),
        )
    )
    cols = DIMS_KEPT + [
        "policy_count",
        "exposure",
        "claim_count",
        "matched_claim_amount",
        "matched_severity_rows",
        "policies_with_claims",
    ]
    return grouped[cols]


def totals_from_segments(df) -> dict:
    policy_count = int(df["policy_count"].sum())
    exposure = money(df["exposure"].sum())
    claim_count = int(df["claim_count"].sum())
    matched_amount = money(df["matched_claim_amount"].sum())
    matched_rows = int(df["matched_severity_rows"].sum())
    policies_with_claims = int(df["policies_with_claims"].sum())
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
        ("matched_severity_rows", totals["matched_severity_rows"], EXPECTED["matched_severity_rows"]),
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
        if value != value:
            return None
    except Exception:
        pass
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, Decimal):
        return float(value)
    return value


def write_table(workbook, name, df) -> None:
    ws = workbook.add_worksheet(name)
    ws.freeze_panes(1, 0)
    headers = list(df.columns)
    for col, header in enumerate(headers):
        ws.write(0, col, header)
    values = df.to_numpy(dtype=object)
    n = len(df)
    for r in range(n):
        row = values[r]
        for c in range(len(headers)):
            v = _cell(row[c])
            if v is None:
                continue
            ws.write(r + 1, c, v)
    last_row = n if n else 1
    ws.add_table(
        0,
        0,
        last_row,
        len(headers) - 1,
        {
            "name": name,
            "style": "Table Style Medium 2",
            "columns": [{"header": h} for h in headers],
            "header_row": True,
        },
    )
    widths = {
        "region_name": 28,
        "area": 8,
        "driv_age_band": 14,
        "veh_age_band": 14,
        "veh_power": 12,
        "veh_gas": 12,
        "policy_count": 14,
        "exposure": 14,
        "claim_count": 12,
        "matched_claim_amount": 18,
        "matched_severity_rows": 20,
        "policies_with_claims": 20,
        "segment_type": 18,
        "segment_value": 22,
        "segment_label": 28,
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
    for col, header in enumerate(headers):
        ws.set_column(col, col, widths.get(header, 16))
    ws.set_default_row(hide_unused_rows=True)


def write_workbook(path: Path, tables: dict) -> None:
    import xlsxwriter

    if path.exists():
        path.unlink()
    workbook = xlsxwriter.Workbook(
        path,
        {"strings_to_urls": False, "nan_inf_to_errors": True},
    )
    try:
        for name, df in tables.items():
            write_table(workbook, name, df)
    finally:
        workbook.close()


def write_csvs(folder: Path, tables: dict) -> dict:
    sizes = {}
    for name, df in tables.items():
        dest = folder / f"{name}.csv"
        df.to_csv(dest, index=False, encoding="utf-8")
        sizes[name] = dest.stat().st_size
    return sizes


def excel_table_names(path: Path) -> set[str]:
    names = set()
    with zipfile.ZipFile(path) as zf:
        for item in zf.namelist():
            if re.search(r"xl/tables/table\d+\.xml$", item):
                xml = zf.read(item).decode("utf-8")
                m = re.search(r'name="([^"]+)"', xml)
                if m:
                    names.add(m.group(1))
    return names


def verify_workbook(path: Path, expected_totals: dict) -> dict:
    import openpyxl

    found = excel_table_names(path)
    needed = {"policy_segments", "risk_segments", "data_quality", "kpi_summary"}
    if not needed.issubset(found):
        raise SystemExit(f"Missing Excel tables {needed - found}; found {found}")

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        ws = wb["policy_segments"]
        rows = ws.iter_rows(min_row=1, values_only=True)
        header = [str(h).lower() if h is not None else "" for h in next(rows)]
        idx = {name: header.index(name) for name in [
            "policy_count", "exposure", "claim_count", "matched_claim_amount",
            "matched_severity_rows", "policies_with_claims",
        ]}
        policy_count = 0
        exposure = Decimal("0")
        claim_count = 0
        amount = Decimal("0")
        sev_rows = 0
        with_claims = 0
        n = 0
        for row in rows:
            if row is None or all(v is None for v in row):
                continue
            n += 1
            policy_count += int(row[idx["policy_count"]])
            exposure += Decimal(str(row[idx["exposure"]]))
            claim_count += int(row[idx["claim_count"]])
            amount += Decimal(str(row[idx["matched_claim_amount"] or 0]))
            sev_rows += int(row[idx["matched_severity_rows"] or 0])
            with_claims += int(row[idx["policies_with_claims"] or 0])
        for name in ("risk_segments", "data_quality", "kpi_summary"):
            _ = wb[name]
    finally:
        wb.close()

    got = {
        "segment_rows": n,
        "policy_count": policy_count,
        "exposure": money(exposure),
        "claim_count": claim_count,
        "matched_claim_amount": money(amount),
        "matched_severity_rows": sev_rows,
        "policies_with_claims": with_claims,
        "average_severity": money(amount / Decimal(sev_rows)),
        "pure_premium": money(amount / exposure),
        "claim_frequency": six_dec(Decimal(claim_count) / exposure),
        "policies_with_claims_pct": six_dec(Decimal(with_claims) / Decimal(policy_count)),
        "excel_tables": sorted(found),
    }
    assert_expected(got)
    for key in (
        "policy_count", "exposure", "claim_count", "matched_claim_amount",
        "matched_severity_rows", "policies_with_claims",
    ):
        if got[key] != expected_totals[key]:
            raise SystemExit(f"Workbook {key} {got[key]} != frame {expected_totals[key]}")
    return got


def fmt(totals: dict) -> dict:
    return {k: (str(v) if isinstance(v, Decimal) else v) for k, v in totals.items()}


def main() -> None:
    if not SRC.exists():
        raise SystemExit(f"Missing source workbook {SRC}")
    print(f"reading {SRC}")
    policy = load_sheet(SRC, "policy_exposure")
    risk = load_sheet(SRC, "risk_segments")
    quality = load_sheet(SRC, "data_quality")
    kpis = load_sheet(SRC, "kpi_summary")
    print(f"source policy rows={len(policy)}")

    segments = aggregate(policy)
    print(f"policy_segments rows={len(segments)} dims_kept={DIMS_KEPT} dims_dropped={DIMS_DROPPED}")
    if len(segments) > 50000:
        raise SystemExit(f"policy_segments still has {len(segments)} rows, over the 50k cap")

    totals = totals_from_segments(segments)
    print("frame_totals", fmt(totals))
    assert_expected(totals)

    tables = {
        "policy_segments": segments,
        "risk_segments": risk,
        "data_quality": quality,
        "kpi_summary": kpis,
    }
    print(f"writing {OUT}")
    write_workbook(OUT, tables)
    csv_sizes = write_csvs(SERVICE, tables)
    size = OUT.stat().st_size
    mb = size / (1024 * 1024)
    print(f"wrote bytes={size} size_mb={mb:.2f}")
    print("csv_bytes", csv_sizes)
    if mb >= 5:
        raise SystemExit(f"Workbook is {mb:.2f} MB, over the 5 MB target")
    print("verifying workbook sums")
    verified = verify_workbook(OUT, totals)
    print("verified", fmt(verified))
    print(f"OK path={OUT} size_mb={mb:.2f} rows={len(segments)}")


if __name__ == "__main__":
    main()
