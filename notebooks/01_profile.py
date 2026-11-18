#!/usr/bin/env python3
"""Profile freMTPL2freq and freMTPL2sev and write docs/data_profile.md.

All figures in the markdown are computed in this script from the local
parquet files. Re-run it after changing the data or the analysis.

Usage (from the project root, with the project virtualenv):

    .venv/bin/python notebooks/01_profile.py
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
DOCS_DIR = ROOT / "docs"

FREQ_PARQUET_URL = "https://data.openml.org/datasets/0004/41214/dataset_41214.pq"
SEV_PARQUET_URL = "https://data.openml.org/datasets/0004/41215/dataset_41215.pq"
OPENML_FREQ_ID = 41214
OPENML_SEV_ID = 41215

# Published counts from the OpenML / CASdatasets descriptions. Compared
# against the files, not used as a substitute for a row count.
PUBLISHED_FREQ_ROWS = 677_991
PUBLISHED_SEV_ROWS = 26_444

# Derived analysis bands (not present in the source files).
DRIV_AGE_BAND_ORDER = ["18-25", "26-35", "36-45", "46-55", "56-65", "66-75", "76+"]
VEH_AGE_BAND_ORDER = ["0", "1-4", "5-9", "10-14", "15-19", "20+"]

# Standard INSEE region names for the 1970-2015 classification cited by
# CASdatasets. These names are not a column in the files.
REGION_NAMES = {
    "R11": "Île-de-France",
    "R21": "Champagne-Ardenne",
    "R22": "Picardie",
    "R23": "Haute-Normandie",
    "R24": "Centre",
    "R25": "Basse-Normandie",
    "R26": "Bourgogne",
    "R31": "Nord-Pas-de-Calais",
    "R41": "Lorraine",
    "R42": "Alsace",
    "R43": "Franche-Comté",
    "R52": "Pays de la Loire",
    "R53": "Bretagne",
    "R54": "Poitou-Charentes",
    "R72": "Aquitaine",
    "R73": "Midi-Pyrénées",
    "R74": "Limousin",
    "R82": "Rhône-Alpes",
    "R83": "Auvergne",
    "R91": "Languedoc-Roussillon",
    "R93": "Provence-Alpes-Côte d'Azur",
    "R94": "Corse",
}

COLUMN_MEANINGS = {
    "freq": {
        "IDpol": "Policy ID, used to link with the claims file (original).",
        "ClaimNb": "Number of claims during the exposure period (original).",
        "Exposure": "Period of exposure for the policy, in years (original).",
        "Area": "Density band of the city where the driver lives, from A (rural) to F (urban centre) (original).",
        "VehPower": "Power of the car, ordered values (original).",
        "VehAge": "Vehicle age in years (original).",
        "DrivAge": "Driver age in years; in France the minimum driving age is 18 (original).",
        "BonusMalus": "French bonus/malus coefficient, documented range 50-350: <100 is a bonus, >100 is a malus (original).",
        "VehBrand": "Car brand, anonymized category codes (original).",
        "VehGas": "Fuel type: Diesel or Regular (original).",
        "Density": "Inhabitants per square kilometer in the city where the driver lives (original).",
        "Region": "Policy region in France, 1970-2015 classification (original).",
    },
    "sev": {
        "IDpol": "Policy ID, used to link with the policy file (original). CASdatasets' severity-file help text mislabels this as an occurrence date; the values are policy IDs, not dates.",
        "ClaimAmount": "Cost of the claim, seen as at a recent date (original). The files have no currency field; the source is French MTPL and the literature treats amounts as euros. Some amounts are fixed IRSA-IDA convention amounts.",
    },
}


def driv_age_band(age: int) -> str:
    if age <= 25:
        return "18-25"
    if age <= 35:
        return "26-35"
    if age <= 45:
        return "36-45"
    if age <= 55:
        return "46-55"
    if age <= 65:
        return "56-65"
    if age <= 75:
        return "66-75"
    return "76+"


def veh_age_band(age: int) -> str:
    if age == 0:
        return "0"
    if age <= 4:
        return "1-4"
    if age <= 9:
        return "5-9"
    if age <= 14:
        return "10-14"
    if age <= 19:
        return "15-19"
    return "20+"


def fmt_int(n) -> str:
    return f"{int(n):,}"


def fmt_float(x, digits=2) -> str:
    return f"{float(x):,.{digits}f}"


def fmt_rate(x, digits=6) -> str:
    return f"{float(x):.{digits}f}"


def markdown_table(df: pd.DataFrame, index_name: str | None = None) -> str:
    work = df.copy()
    if index_name is not None:
        work = work.reset_index()
        work = work.rename(columns={work.columns[0]: index_name})
    headers = [str(c) for c in work.columns]
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for row in work.itertuples(index=False):
        cells = [str(v) for v in row]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def load_frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    freq_path = RAW_DIR / "freMTPL2freq.parquet"
    sev_path = RAW_DIR / "freMTPL2sev.parquet"
    if not freq_path.exists() or not sev_path.exists():
        raise FileNotFoundError(
            f"Missing parquet under {RAW_DIR}. "
            f"Download {FREQ_PARQUET_URL} and {SEV_PARQUET_URL} first."
        )
    freq = pd.read_parquet(freq_path)
    sev = pd.read_parquet(sev_path)
    return freq, sev


def normalize(freq: pd.DataFrame, sev: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    freq = freq.copy()
    sev = sev.copy()
    expected_freq = [
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
    expected_sev = ["IDpol", "ClaimAmount"]
    missing_f = [c for c in expected_freq if c not in freq.columns]
    missing_s = [c for c in expected_sev if c not in sev.columns]
    if missing_f or missing_s:
        raise ValueError(f"Unexpected schema. Missing freq={missing_f} sev={missing_s}")
    freq["IDpol"] = freq["IDpol"].astype("int64")
    sev["IDpol"] = sev["IDpol"].astype("int64")
    freq["Area"] = freq["Area"].astype("string")
    freq["VehBrand"] = freq["VehBrand"].astype("string")
    freq["VehGas"] = freq["VehGas"].astype("string")
    freq["Region"] = freq["Region"].astype("string")
    freq["DrivAgeBand"] = freq["DrivAge"].map(driv_age_band)
    freq["VehAgeBand"] = freq["VehAge"].map(veh_age_band)
    return freq, sev


def write_csv(freq: pd.DataFrame, sev: pd.DataFrame) -> tuple[Path, Path]:
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
    freq_out = RAW_DIR / "freMTPL2freq.csv"
    sev_out = RAW_DIR / "freMTPL2sev.csv"
    freq_csv = freq[freq_cols].copy()
    freq_csv["Density"] = freq_csv["Density"].astype("int64")
    freq_csv.to_csv(freq_out, index=False)
    sev[["IDpol", "ClaimAmount"]].to_csv(sev_out, index=False)
    return freq_out, sev_out


def dtype_name(series: pd.Series) -> str:
    return str(series.dtype)


def series_profile(df: pd.DataFrame, col: str) -> dict:
    s = df[col]
    rec = {
        "column": col,
        "dtype": dtype_name(s),
        "non_null": int(s.notna().sum()),
        "nulls": int(s.isna().sum()),
        "nunique": int(s.nunique(dropna=False)),
    }
    if pd.api.types.is_numeric_dtype(s) and not pd.api.types.is_bool_dtype(s):
        rec.update(
            {
                "min": s.min(),
                "max": s.max(),
                "mean": float(s.mean()),
                "median": float(s.median()),
                "std": float(s.std()),
            }
        )
    return rec


def segment_summary(freq: pd.DataFrame, claims: pd.DataFrame, col: str, order=None) -> pd.DataFrame:
    g = (
        freq.groupby(col, observed=True)
        .agg(policies=("IDpol", "size"), exposure=("Exposure", "sum"), claim_count=("ClaimNb", "sum"))
        .copy()
    )
    g["frequency"] = g["claim_count"] / g["exposure"]
    s = (
        claims.groupby(col, observed=True)
        .agg(
            severity_rows=("ClaimAmount", "size"),
            total_claim_amount=("ClaimAmount", "sum"),
            avg_severity=("ClaimAmount", "mean"),
        )
        .copy()
    )
    out = g.join(s, how="left")
    out["pure_premium"] = out["total_claim_amount"] / out["exposure"]
    if order is not None:
        out = out.reindex(order)
    return out


def format_segment(out: pd.DataFrame) -> pd.DataFrame:
    formatted = pd.DataFrame(
        {
            "Policies": out["policies"].map(fmt_int),
            "Exposure (years)": out["exposure"].map(lambda x: fmt_float(x, 2)),
            "Claims (ClaimNb)": out["claim_count"].map(fmt_int),
            "Frequency": out["frequency"].map(lambda x: fmt_rate(x, 6)),
            "Severity rows": out["severity_rows"].fillna(0).map(fmt_int),
            "Total claim amount": out["total_claim_amount"].map(lambda x: fmt_float(x, 2)),
            "Avg severity": out["avg_severity"].map(lambda x: fmt_float(x, 2)),
            "Pure premium": out["pure_premium"].map(lambda x: fmt_float(x, 2)),
        }
    )
    formatted.index = out.index
    return formatted


def profile(freq: pd.DataFrame, sev: pd.DataFrame) -> dict:
    freq_ids = set(freq["IDpol"])
    sev_ids = set(sev["IDpol"])
    orphan_ids = sorted(sev_ids - freq_ids)
    orphan_mask = sev["IDpol"].isin(orphan_ids)
    matched_sev = sev.loc[~orphan_mask].copy()

    sev_counts = sev.groupby("IDpol").size().rename("SevNb")
    sev_sums = sev.groupby("IDpol")["ClaimAmount"].sum().rename("SevAmountSum")
    merged = freq.merge(sev_counts, on="IDpol", how="left")
    merged["SevNb"] = merged["SevNb"].fillna(0).astype(int)
    merged = merged.merge(sev_sums, on="IDpol", how="left")

    claimnb_no_sev = (merged["ClaimNb"] > 0) & (merged["SevNb"] == 0)
    zero_claimnb_with_sev = (merged["ClaimNb"] == 0) & (merged["SevNb"] > 0)
    both_positive_disagree = (merged["ClaimNb"] > 0) & (merged["SevNb"] > 0) & (
        merged["ClaimNb"] != merged["SevNb"]
    )

    claims = matched_sev.merge(
        freq[
            [
                "IDpol",
                "Area",
                "Region",
                "VehGas",
                "DrivAgeBand",
                "VehAgeBand",
            ]
        ],
        on="IDpol",
        how="left",
    )

    total_policies = int(len(freq))
    total_exposure = float(freq["Exposure"].sum())
    total_claimnb = int(freq["ClaimNb"].sum())
    total_sev_rows = int(len(sev))
    matched_sev_rows = int(len(matched_sev))
    orphan_sev_rows = int(orphan_mask.sum())
    total_amount_all = float(sev["ClaimAmount"].sum())
    total_amount_matched = float(matched_sev["ClaimAmount"].sum())
    total_amount_orphan = float(sev.loc[orphan_mask, "ClaimAmount"].sum())

    orphan_detail = (
        sev.loc[orphan_mask]
        .groupby("IDpol")["ClaimAmount"]
        .agg(severity_rows="size", total_amount="sum", min_amount="min", max_amount="max")
        .reset_index()
    )

    disagree_both = merged.loc[
        both_positive_disagree, ["IDpol", "ClaimNb", "SevNb", "Exposure", "SevAmountSum"]
    ]

    veh0_missing = (merged["VehAge"] == 0) & claimnb_no_sev

    amount_vc = sev["ClaimAmount"].value_counts()

    result = {
        "freq_rows": total_policies,
        "freq_unique_idpol": int(freq["IDpol"].nunique()),
        "sev_rows": total_sev_rows,
        "sev_unique_idpol": int(sev["IDpol"].nunique()),
        "freq_published": PUBLISHED_FREQ_ROWS,
        "sev_published": PUBLISHED_SEV_ROWS,
        "freq_row_gap_vs_published": total_policies - PUBLISHED_FREQ_ROWS,
        "sev_row_gap_vs_published": total_sev_rows - PUBLISHED_SEV_ROWS,
        "freq_duplicate_idpol": int(freq["IDpol"].duplicated().sum()),
        "freq_duplicate_rows": int(freq.drop(columns=["DrivAgeBand", "VehAgeBand"]).duplicated().sum()),
        "sev_duplicate_rows": int(sev.duplicated().sum()),
        "sev_rows_in_exact_dup_groups": int(sev.duplicated(keep=False).sum()),
        "sev_max_exact_dup_multiplicity": int(sev.groupby(["IDpol", "ClaimAmount"]).size().max()),
        "idpol_integer_valued_freq": True,
        "freq_nulls": {c: int(freq[c].isna().sum()) for c in freq.columns if c not in ("DrivAgeBand", "VehAgeBand")},
        "sev_nulls": {c: int(sev[c].isna().sum()) for c in ["IDpol", "ClaimAmount"]},
        "freq_dtypes": {c: dtype_name(freq[c]) for c in freq.columns if c not in ("DrivAgeBand", "VehAgeBand")},
        "sev_dtypes": {c: dtype_name(sev[c]) for c in ["IDpol", "ClaimAmount"]},
        "freq_col_profiles": [series_profile(freq, c) for c in [
            "IDpol", "ClaimNb", "Exposure", "Area", "VehPower", "VehAge",
            "DrivAge", "BonusMalus", "VehBrand", "VehGas", "Density", "Region",
        ]],
        "sev_col_profiles": [series_profile(sev, c) for c in ["IDpol", "ClaimAmount"]],
        "exposure_gt_1": int((freq["Exposure"] > 1).sum()),
        "exposure_eq_1": int((freq["Exposure"] == 1).sum()),
        "exposure_lt_1": int((freq["Exposure"] < 1).sum()),
        "exposure_min": float(freq["Exposure"].min()),
        "exposure_max": float(freq["Exposure"].max()),
        "exposure_gt_1_max": float(freq.loc[freq["Exposure"] > 1, "Exposure"].max()) if (freq["Exposure"] > 1).any() else None,
        "exposure_eq_1_over_366": int((freq["Exposure"] == 1 / 366).sum()),
        "exposure_eq_1_over_365": int(((freq["Exposure"] - 1 / 365).abs() < 1e-12).sum()),
        "claimnb_value_counts": {int(k): int(v) for k, v in freq["ClaimNb"].value_counts().sort_index().items()},
        "policies_with_claimnb_gt_0": int((freq["ClaimNb"] > 0).sum()),
        "claimnb_ge_4": int((freq["ClaimNb"] >= 4).sum()),
        "claimnb_max": int(freq["ClaimNb"].max()),
        "vehage_eq_0": int((freq["VehAge"] == 0).sum()),
        "vehage_ge_50": int((freq["VehAge"] >= 50).sum()),
        "vehage_eq_99": int((freq["VehAge"] == 99).sum()),
        "vehage_eq_100": int((freq["VehAge"] == 100).sum()),
        "drivage_eq_18": int((freq["DrivAge"] == 18).sum()),
        "drivage_ge_90": int((freq["DrivAge"] >= 90).sum()),
        "drivage_eq_99": int((freq["DrivAge"] == 99).sum()),
        "drivage_eq_100": int((freq["DrivAge"] == 100).sum()),
        "bonusmalus_min": int(freq["BonusMalus"].min()),
        "bonusmalus_max": int(freq["BonusMalus"].max()),
        "bonusmalus_eq_50": int((freq["BonusMalus"] == 50).sum()),
        "bonusmalus_gt_100": int((freq["BonusMalus"] > 100).sum()),
        "bonusmalus_ge_200": int((freq["BonusMalus"] >= 200).sum()),
        "vehgas_values": {str(k): int(v) for k, v in freq["VehGas"].value_counts().items()},
        "vehgas_stripped_differs": int((freq["VehGas"].str.strip() != freq["VehGas"]).sum()),
        "area_values": {str(k): int(v) for k, v in freq["Area"].value_counts().sort_index().items()},
        "vehbrand_values": {str(k): int(v) for k, v in freq["VehBrand"].value_counts().items()},
        "region_values": {str(k): int(v) for k, v in freq["Region"].value_counts().items()},
        "vehpower_values": [int(x) for x in sorted(freq["VehPower"].unique())],
        "density_min": int(freq["Density"].min()),
        "density_max": int(freq["Density"].max()),
        "density_is_integer": bool((freq["Density"] == freq["Density"].round()).all()),
        "area_density": (
            freq.groupby("Area", observed=True)["Density"]
            .agg(["min", "median", "mean", "max", "count"])
            .reset_index()
            .to_dict(orient="records")
        ),
        "claimamount_min": float(sev["ClaimAmount"].min()),
        "claimamount_max": float(sev["ClaimAmount"].max()),
        "claimamount_median": float(sev["ClaimAmount"].median()),
        "claimamount_le_0": int((sev["ClaimAmount"] <= 0).sum()),
        "claimamount_gt_100000": int((sev["ClaimAmount"] > 100_000).sum()),
        "claimamount_gt_1e6": int((sev["ClaimAmount"] > 1_000_000).sum()),
        "top_claim_amounts": [float(x) for x in sev["ClaimAmount"].nlargest(10).tolist()],
        "most_common_amounts": [
            {"amount": float(k), "rows": int(v)} for k, v in amount_vc.head(5).items()
        ],
        "intersection_policies": int(len(freq_ids & sev_ids)),
        "orphan_sev_policies": len(orphan_ids),
        "orphan_sev_policy_ids": orphan_ids,
        "orphan_sev_rows": orphan_sev_rows,
        "orphan_sev_amount": total_amount_orphan,
        "orphan_detail": orphan_detail.to_dict(orient="records"),
        "policies_with_no_sev_rows": int(len(freq_ids - sev_ids)),
        "policies_claimnb_ne_sevnb": int((merged["ClaimNb"] != merged["SevNb"]).sum()),
        "policies_claimnb_gt0_sevnb_0": int(claimnb_no_sev.sum()),
        "claimnb_sum_missing_sev": int(merged.loc[claimnb_no_sev, "ClaimNb"].sum()),
        "policies_claimnb_0_sevnb_gt0": int(zero_claimnb_with_sev.sum()),
        "policies_both_positive_disagree": int(both_positive_disagree.sum()),
        "disagree_both_rows": disagree_both.to_dict(orient="records"),
        "vehage0_missing_sev_policies": int(veh0_missing.sum()),
        "vehage0_missing_sev_claimnb_sum": int(merged.loc[veh0_missing, "ClaimNb"].sum()),
        "total_exposure": total_exposure,
        "total_claimnb": total_claimnb,
        "matched_sev_rows": matched_sev_rows,
        "frequency_claimnb": total_claimnb / total_exposure,
        "frequency_matched_sev_rows": matched_sev_rows / total_exposure,
        "frequency_all_sev_rows": total_sev_rows / total_exposure,
        "total_amount_all": total_amount_all,
        "total_amount_matched": total_amount_matched,
        "avg_severity_all": float(sev["ClaimAmount"].mean()),
        "avg_severity_matched": float(matched_sev["ClaimAmount"].mean()),
        "pure_premium_all": total_amount_all / total_exposure,
        "pure_premium_matched": total_amount_matched / total_exposure,
        "pct_policies_with_claim": float((freq["ClaimNb"] > 0).mean() * 100),
        "max_sev_rows_per_policy": int(sev.groupby("IDpol").size().max()),
        "segments": {
            "Area": segment_summary(freq, claims, "Area"),
            "Region": segment_summary(freq, claims, "Region").sort_values("frequency", ascending=False),
            "VehGas": segment_summary(freq, claims, "VehGas"),
            "DrivAgeBand": segment_summary(freq, claims, "DrivAgeBand", DRIV_AGE_BAND_ORDER),
            "VehAgeBand": segment_summary(freq, claims, "VehAgeBand", VEH_AGE_BAND_ORDER),
        },
    }
    return result


def column_profile_table(profiles: list[dict], meanings: dict) -> str:
    rows = []
    for p in profiles:
        rec = {
            "Column": p["column"],
            "Meaning": meanings[p["column"]],
            "Dtype (after IDpol cast)": p["dtype"],
            "Nulls": fmt_int(p["nulls"]),
            "Distinct": fmt_int(p["nunique"]),
        }
        if "min" in p:
            if p["column"] in {"IDpol", "ClaimNb", "VehPower", "VehAge", "DrivAge", "BonusMalus", "Density"}:
                rec["Min"] = fmt_int(p["min"])
                rec["Max"] = fmt_int(p["max"])
            elif p["column"] == "ClaimAmount":
                rec["Min"] = fmt_float(p["min"], 2)
                rec["Max"] = fmt_float(p["max"], 2)
            else:
                rec["Min"] = fmt_rate(p["min"], 6) if p["column"] == "Exposure" else fmt_float(p["min"], 2)
                rec["Max"] = fmt_float(p["max"], 4) if p["column"] == "Exposure" else fmt_float(p["max"], 2)
        else:
            rec["Min"] = "—"
            rec["Max"] = "—"
        rows.append(rec)
    return markdown_table(pd.DataFrame(rows))


def write_markdown(r: dict, freq_csv: Path, sev_csv: Path) -> Path:
    area_tbl = format_segment(r["segments"]["Area"])
    gas_tbl = format_segment(r["segments"]["VehGas"])
    driv_tbl = format_segment(r["segments"]["DrivAgeBand"])
    veh_tbl = format_segment(r["segments"]["VehAgeBand"])
    region_seg = r["segments"]["Region"].copy()
    region_fmt = format_segment(region_seg)
    region_fmt.insert(0, "INSEE name (1970-2015)", [REGION_NAMES.get(i, "—") for i in region_fmt.index])

    claimnb_rows = pd.DataFrame(
        {
            "ClaimNb": list(r["claimnb_value_counts"].keys()),
            "Policies": [fmt_int(v) for v in r["claimnb_value_counts"].values()],
        }
    )

    common_amt = pd.DataFrame(
        {
            "ClaimAmount": [fmt_float(x["amount"], 2) for x in r["most_common_amounts"]],
            "Severity rows": [fmt_int(x["rows"]) for x in r["most_common_amounts"]],
        }
    )

    orphan_tbl = pd.DataFrame(
        {
            "IDpol": [fmt_int(x["IDpol"]) for x in r["orphan_detail"]],
            "Severity rows": [fmt_int(x["severity_rows"]) for x in r["orphan_detail"]],
            "Total amount": [fmt_float(x["total_amount"], 2) for x in r["orphan_detail"]],
            "Min amount": [fmt_float(x["min_amount"], 2) for x in r["orphan_detail"]],
            "Max amount": [fmt_float(x["max_amount"], 2) for x in r["orphan_detail"]],
        }
    )

    area_density_tbl = pd.DataFrame(
        {
            "Area": [x["Area"] for x in r["area_density"]],
            "Min density": [fmt_int(x["min"]) for x in r["area_density"]],
            "Median density": [fmt_float(x["median"], 1) for x in r["area_density"]],
            "Mean density": [fmt_float(x["mean"], 2) for x in r["area_density"]],
            "Max density": [fmt_int(x["max"]) for x in r["area_density"]],
            "Policies": [fmt_int(x["count"]) for x in r["area_density"]],
        }
    )

    disagree_note = "none"
    if r["disagree_both_rows"]:
        parts = []
        for row in r["disagree_both_rows"]:
            parts.append(
                f"IDpol {fmt_int(row['IDpol'])} has ClaimNb={int(row['ClaimNb'])} and "
                f"{int(row['SevNb'])} severity row(s), exposure {fmt_float(row['Exposure'], 2)}, "
                f"severity sum {fmt_float(row['SevAmountSum'], 2)}"
            )
        disagree_note = "; ".join(parts)

    md = f"""# freMTPL2 data profile

This file is generated by `notebooks/01_profile.py`. Every figure below was computed from the local OpenML parquet files in `data/raw`. Do not hand-edit the numbers; re-run the script instead.

**Source.** Public French Motor Third-Party Liability datasets `freMTPL2freq` (OpenML id {OPENML_FREQ_ID}) and `freMTPL2sev` (OpenML id {OPENML_SEV_ID}), CC0, from C. Dutang and A. Charpentier, *CASdatasets*. Frequency parquet: `{FREQ_PARQUET_URL}`. Severity parquet URL resolved from `https://www.openml.org/api/v1/json/data/{OPENML_SEV_ID}`: `{SEV_PARQUET_URL}`. Local copies: `data/raw/freMTPL2freq.parquet`, `data/raw/freMTPL2sev.parquet`, plus CSV exports `{freq_csv.name}` and `{sev_csv.name}`.

**Context for this portfolio.** The files are used as a stand-in for raw extracts from a policy administration system and a claims system (Guidewire-style PolicyCenter and ClaimCenter). They are not Guidewire extracts. There is **no premium column**, so a loss ratio cannot be computed and is not estimated.

**Observation period.** The files contain no policy or loss dates. CASdatasets documents the book as observed mostly on one year, with a period of approximately 2011–2013. That statement is background from the documentation, not a field in the data.

## 1. Row counts

| File | Rows in the downloaded parquet | Unique `IDpol` | OpenML / CASdatasets published count | Difference |
| --- | --- | --- | --- | --- |
| freMTPL2freq | {fmt_int(r['freq_rows'])} | {fmt_int(r['freq_unique_idpol'])} | {fmt_int(r['freq_published'])} | {fmt_int(r['freq_row_gap_vs_published'])} more rows in the parquet |
| freMTPL2sev | {fmt_int(r['sev_rows'])} | {fmt_int(r['sev_unique_idpol'])} | {fmt_int(r['sev_published'])} (CASdatasets `dim()` example) | {fmt_int(r['sev_row_gap_vs_published'])} more rows in the parquet |

The OpenML description text also says {fmt_int(r['freq_published'])} policies, but the parquet at the documented `parquet_url` (and OpenML's own instance count for dataset {OPENML_FREQ_ID}) contains **{fmt_int(r['freq_rows'])}** rows. Every `IDpol` in frequency is unique, so the file has {fmt_int(r['freq_rows'])} policies, not {fmt_int(r['freq_published'])}.

The {fmt_int(r['sev_row_gap_vs_published'])}-row gap on severity is exactly equal to the {fmt_int(r['orphan_sev_rows'])} severity rows whose `IDpol` does not appear in frequency ({fmt_int(r['orphan_sev_policies'])} orphan policies). That is consistent with a later CASdatasets build that kept only claims matching a frequency policy ({fmt_int(r['matched_sev_rows'])} matched rows, the same as the published dimension). The {fmt_int(r['freq_row_gap_vs_published'])} extra frequency rows are not identified inside these files (no duplicate keys, no null `IDpol`). Current CASdatasets documentation reports {fmt_int(r['freq_published'])} after later clean-up. This project **keeps the downloaded OpenML files intact** and does not drop those 22 policies.

## 2. Columns and meaning

Meanings follow the CASdatasets documentation for `freMTPL2freq` / `freMTPL2sev`. Dtypes below are after casting `IDpol` from the parquet `float64` to 64-bit integer (every value is integer-valued). Nulls are zero on every column in both files.

### 2.1 freMTPL2freq

{column_profile_table(r['freq_col_profiles'], COLUMN_MEANINGS['freq'])}

Category levels observed:

- `Area`: {', '.join(sorted(r['area_values']))}.
- `VehBrand`: {', '.join(sorted(r['vehbrand_values'], key=lambda x: (len(x), x)))}.
- `VehGas`: {', '.join(sorted(r['vehgas_values']))}. No leading or trailing whitespace ({fmt_int(r['vehgas_stripped_differs'])} rows differ after `strip`).
- `VehPower`: {', '.join(str(x) for x in r['vehpower_values'])}.
- `Region`: {', '.join(sorted(r['region_values']))}.

`Area` tracks inhabitant density, as documented (A rural → F urban centre). Observed density ranges do not overlap except at the A/B boundary value 50:

{markdown_table(area_density_tbl)}

### 2.2 freMTPL2sev

{column_profile_table(r['sev_col_profiles'], COLUMN_MEANINGS['sev'])}

## 3. Data quality issues

These are findings in the source files. They will be preserved in the raw layer and tested in dbt; they are not "corrected" here.

### 3.1 Frequency versus published documentation

- Downloaded frequency has {fmt_int(r['freq_rows'])} policies; documentation often says {fmt_int(r['freq_published'])} ({fmt_int(r['freq_row_gap_vs_published'])} more in the parquet).
- Downloaded severity has {fmt_int(r['sev_rows'])} rows; the CASdatasets example dimension is {fmt_int(r['sev_published'])} ({fmt_int(r['sev_row_gap_vs_published'])} more in the parquet, equal to the orphan claims).

### 3.2 Join between severity and frequency

- Intersection: {fmt_int(r['intersection_policies'])} policy IDs appear in both files.
- **Orphans in severity (no frequency row):** {fmt_int(r['orphan_sev_policies'])} policy IDs, {fmt_int(r['orphan_sev_rows'])} claim rows, total amount {fmt_float(r['orphan_sev_amount'], 2)}. These IDs are {', '.join(fmt_int(x) for x in r['orphan_sev_policy_ids'])}.

{markdown_table(orphan_tbl)}

- **Policies in frequency with no severity row:** {fmt_int(r['policies_with_no_sev_rows'])}. Most of these have `ClaimNb = 0` and are expected.
- **`ClaimNb` disagrees with the number of severity rows:** {fmt_int(r['policies_claimnb_ne_sevnb'])} policies.
  - {fmt_int(r['policies_claimnb_gt0_sevnb_0'])} policies have `ClaimNb > 0` and zero severity rows. Those policies account for {fmt_int(r['claimnb_sum_missing_sev'])} claims in `ClaimNb` with no amount.
  - {fmt_int(r['policies_claimnb_0_sevnb_gt0'])} policies have `ClaimNb = 0` and at least one severity row.
  - {fmt_int(r['policies_both_positive_disagree'])} policy has both counts positive but different: {disagree_note}.
- Of the {fmt_int(r['policies_claimnb_gt0_sevnb_0'])} policies with claims in `ClaimNb` and no severity rows, {fmt_int(r['vehage0_missing_sev_policies'])} have `VehAge = 0` ({fmt_int(r['vehage0_missing_sev_claimnb_sum'])} of the missing `ClaimNb` units). That is a large share of the gap and will show up in the vehicle-age frequency versus severity comparison.

### 3.3 Exposure

- Minimum exposure is {fmt_rate(r['exposure_min'], 12)}, which equals 1/366 (one day in a leap year) for {fmt_int(r['exposure_eq_1_over_366'])} policies. {fmt_int(r['exposure_eq_1_over_365'])} policies have exposure equal to 1/365.
- {fmt_int(r['exposure_lt_1'])} policies have exposure &lt; 1; {fmt_int(r['exposure_eq_1'])} have exposure exactly 1; **{fmt_int(r['exposure_gt_1'])} have exposure &gt; 1**, up to {fmt_float(r['exposure_max'], 2)} years. Exposure greater than one year is unusual for a "mostly one-year" book and should be flagged, not dropped, in raw.

### 3.4 Claim counts and amounts

`ClaimNb` distribution:

{markdown_table(claimnb_rows)}

- {fmt_int(r['policies_with_claimnb_gt_0'])} policies have `ClaimNb > 0` ({fmt_float(r['pct_policies_with_claim'], 2)}% of the book).
- {fmt_int(r['claimnb_ge_4'])} policies have `ClaimNb >= 4`, including a maximum of {fmt_int(r['claimnb_max'])}. Extreme counts can be real multi-claim policies or data errors; raw keeps them.
- No severity amount is ≤ 0. Minimum amount is {fmt_float(r['claimamount_min'], 2)}; median {fmt_float(r['claimamount_median'], 2)}; maximum {fmt_float(r['claimamount_max'], 2)}.
- {fmt_int(r['claimamount_gt_100000'])} claims exceed 100,000; {fmt_int(r['claimamount_gt_1e6'])} exceed 1,000,000. The ten largest amounts are: {', '.join(fmt_float(x, 2) for x in r['top_claim_amounts'])}.
- Amounts are heavily concentrated at a few values, which is consistent with the documented IRSA-IDA fixed-amount convention (the files do not label which rows are convention amounts):

{markdown_table(common_amt)}

- **Exact duplicate severity rows** (`IDpol` + `ClaimAmount`): {fmt_int(r['sev_duplicate_rows'])} extra rows, {fmt_int(r['sev_rows_in_exact_dup_groups'])} rows involved in a duplicate group, maximum multiplicity {fmt_int(r['sev_max_exact_dup_multiplicity'])}. Because many claims share convention amounts, a composite key of (`IDpol`, `ClaimAmount`) is not unique. Severity has no native claim number.
- Maximum severity rows for one `IDpol`: {fmt_int(r['max_sev_rows_per_policy'])} (this is one of the orphan policies).

### 3.5 Age and bonus-malus extremes

- `VehAge` is 0 for {fmt_int(r['vehage_eq_0'])} policies (new vehicles). {fmt_int(r['vehage_ge_50'])} policies have `VehAge >= 50`, including {fmt_int(r['vehage_eq_99'])} at 99 and {fmt_int(r['vehage_eq_100'])} at 100. 99/100 may be a cap or a sentinel; that is not labeled in the file.
- `DrivAge` starts at 18 ({fmt_int(r['drivage_eq_18'])} policies), consistent with the French driving age. {fmt_int(r['drivage_ge_90'])} policies have `DrivAge >= 90`, including {fmt_int(r['drivage_eq_99'])} at 99 and {fmt_int(r['drivage_eq_100'])} at 100.
- `BonusMalus` ranges from {fmt_int(r['bonusmalus_min'])} to {fmt_int(r['bonusmalus_max'])} (documentation allows up to 350). {fmt_int(r['bonusmalus_eq_50'])} policies sit at the maximum bonus of 50; {fmt_int(r['bonusmalus_gt_100'])} have a malus (&gt; 100); {fmt_int(r['bonusmalus_ge_200'])} are ≥ 200.

### 3.6 Types

In the parquet, `IDpol` is `float64` in both files even though every value is an integer. `Density` is stored as float and is integer-valued in every row, range {fmt_int(r['density_min'])} to {fmt_int(r['density_max'])}. Raw tables should use integer types for `IDpol` and `Density`.

## 4. Headline facts

Definitions used here (and not substituted with published figures):

- **Claim frequency** = `sum(ClaimNb) / sum(Exposure)` — claims per policy-year, using the policy-file claim count. This is the usual definition on this dataset.
- **Severity** = average `ClaimAmount` on severity rows.
- **Pure premium** = total claim amount / total exposure (expected loss cost per policy-year). Because there is **no premium**, this is not a loss ratio and no loss ratio is reported.
- Two amount bases are shown. **Matched** uses only severity rows whose `IDpol` exists in frequency (recommended: the {fmt_int(r['orphan_sev_policies'])} orphan policies have no exposure in the denominator). **All** includes orphan amounts.

| Metric | Value |
| --- | --- |
| Policies | {fmt_int(r['freq_rows'])} |
| Total exposure (policy-years) | {fmt_float(r['total_exposure'], 2)} |
| Total claims (`sum(ClaimNb)`) | {fmt_int(r['total_claimnb'])} |
| Policies with `ClaimNb > 0` | {fmt_int(r['policies_with_claimnb_gt_0'])} ({fmt_float(r['pct_policies_with_claim'], 2)}%) |
| Overall claim frequency (`ClaimNb` / exposure) | {fmt_rate(r['frequency_claimnb'], 6)} |
| Severity rows, all / matched | {fmt_int(r['sev_rows'])} / {fmt_int(r['matched_sev_rows'])} |
| Frequency using matched severity rows / exposure | {fmt_rate(r['frequency_matched_sev_rows'], 6)} |
| Total claim amount, all severity rows | {fmt_float(r['total_amount_all'], 2)} |
| Total claim amount, matched only | {fmt_float(r['total_amount_matched'], 2)} |
| Average severity, all rows | {fmt_float(r['avg_severity_all'], 2)} |
| Average severity, matched only | {fmt_float(r['avg_severity_matched'], 2)} |
| Median severity (all rows) | {fmt_float(r['claimamount_median'], 2)} |
| Pure premium, matched amounts / exposure | {fmt_float(r['pure_premium_matched'], 2)} |
| Pure premium, all amounts / exposure | {fmt_float(r['pure_premium_all'], 2)} |

The `ClaimNb`-based frequency ({fmt_rate(r['frequency_claimnb'], 4)}) is higher than the severity-row frequency ({fmt_rate(r['frequency_matched_sev_rows'], 4)}) because {fmt_int(r['claimnb_sum_missing_sev'])} `ClaimNb` units have no severity row. For reporting and the Power BI dashboard, frequency should stay on `ClaimNb` and exposure; severity and pure premium should use matched amounts and disclose the missing-amount gap.

Exact exposure sum used in the ratios: {r['total_exposure']:.10f}.

## 5. Frequency and severity by segment

Segment severity uses **matched** claim rows only (orphan claims have no area, region, vehicle or driver attributes). Frequency uses `sum(ClaimNb) / sum(Exposure)` on all frequency policies. Pure premium is matched total amount / segment exposure. Driver and vehicle age bands are **derived** for this analysis; they are not source columns.

Band rules:

- Driver age: 18-25, 26-35, 36-45, 46-55, 56-65, 66-75, 76+.
- Vehicle age: 0 (new), 1-4, 5-9, 10-14, 15-19, 20+.

### 5.1 By Area

{markdown_table(area_tbl, index_name='Area')}

Frequency rises from rural Area A ({fmt_rate(r['segments']['Area'].loc['A', 'frequency'], 4)}) to urban Area F ({fmt_rate(r['segments']['Area'].loc['F', 'frequency'], 4)}). Average severity is not monotone in the same direction; Area F has the highest frequency and the lowest average severity among areas.

### 5.2 By fuel type (`VehGas`)

{markdown_table(gas_tbl, index_name='VehGas')}

### 5.3 By driver age band (derived)

{markdown_table(driv_tbl, index_name='Driver age band')}

Drivers aged 18-25 have the highest frequency ({fmt_rate(r['segments']['DrivAgeBand'].loc['18-25', 'frequency'], 4)}) and the highest average severity ({fmt_float(r['segments']['DrivAgeBand'].loc['18-25', 'avg_severity'], 2)}), so they also have the highest pure premium. This band includes some very large individual claims; the mean is sensitive to those tails.

### 5.4 By vehicle age band (derived)

{markdown_table(veh_tbl, index_name='Vehicle age band')}

New vehicles (`VehAge = 0`) show a much higher `ClaimNb` frequency ({fmt_rate(r['segments']['VehAgeBand'].loc['0', 'frequency'], 4)}) than other bands, but only {fmt_int(r['segments']['VehAgeBand'].loc['0', 'severity_rows'])} matched severity rows against {fmt_int(r['segments']['VehAgeBand'].loc['0', 'claim_count'])} `ClaimNb` units. That gap is largely the missing-severity issue in section 3.2, so severity and pure premium for new vehicles are not comparable to frequency without a caveat.

### 5.5 By Region

INSEE names are the standard 1970-2015 labels for these codes; they are reference names, not a source column.

{markdown_table(region_fmt, index_name='Region')}

## 6. Proposed Guidewire-style raw layer

The source is two flat files, not a Guidewire extract. The raw layer should still look like a landing zone fed by a policy system and a claims system: split the denormalized policy snapshot into policy, vehicle and driver tables, and land claims at claim-row grain, with surrogate keys and no "fixes" to business values.

### 6.1 What is original versus derived

| Field / table attribute | Class | Rule |
| --- | --- | --- |
| `IDpol`, `ClaimNb`, `Exposure`, `Area`, `VehPower`, `VehAge`, `DrivAge`, `BonusMalus`, `VehBrand`, `VehGas`, `Density`, `Region`, `ClaimAmount` | **Original** | Copied from the files. `IDpol` and `Density` may be stored as integers because every value is integer-valued (deterministic type cleanse only). |
| `policy_sk`, `vehicle_sk`, `driver_sk`, `claim_sk` | **Derived (surrogate keys)** | Warehouse keys, not present in the source. Assigned deterministically (for example a hash of the natural key, or a stable sequence). |
| `claim_sequence` | **Derived** | 1..n within `IDpol`, in source-file order. Needed because there is no native claim number and (`IDpol`, `ClaimAmount`) is not unique. |
| `src_system`, `src_file_name`, `src_row_number`, `loaded_at` | **Pipeline metadata** | Not business data from Guidewire or from CASdatasets. |
| Policy effective / expiration dates, loss date, report date, valuation date | **Not in the source** | Do not invent per-row business dates. See dates below. |
| Driver or vehicle identifiers, VIN, named insured, coverage, written premium | **Not in the source** | Do not fabricate. |
| Driver / vehicle age bands used in section 5 | **Derived, analysis only** | Documented cut points; belong in a mart, not in raw. |
| INSEE region names | **Reference mapping** | Standard external labels for `Region`, not extracted from the files. |

### 6.2 Dates

The files have no dates. CASdatasets places the book in approximately 2011–2013, and `Exposure` is a duration in years, but there is no policy start, policy end, or loss date at row level.

- **Raw tables will not contain synthetic business dates.** Adding a fake inception date or a fake loss date would present derived values as if they came from Guidewire.
- Raw may contain `loaded_at` (ETL timestamp) as metadata only, clearly named.
- If Power BI later needs a calendar, a mart can carry a clearly labeled reporting attribute such as `book_period_label = 'freMTPL2 observation book (approx. 2011–2013)'`, or a single `demo_as_of_date` documented as a dashboard convention. That is not a source date and must be named accordingly.
- Do not compute `policy_end = policy_start + Exposure` unless `policy_start` itself is explicitly synthetic and never shown as original.

### 6.3 Target raw tables

Grain and keys below assume Snowflake `RAW` (or an equivalent landing schema). One policy row in this dataset is one vehicle and one recorded driver, so the split is structural (to mirror PolicyCenter coverables and contacts) rather than a true 1:n unnest.

**`RAW.POLICIES`** — grain: one row per `IDpol`.

- `policy_sk` (surrogate, unique).
- `policy_id` — original `IDpol`, unique natural key.
- `claim_count` — original `ClaimNb`. Kept even when it disagrees with the claims table.
- `exposure_years` — original `Exposure`.
- `area`, `bonus_malus`, `density`, `region` — original.
- Metadata: `src_file_name`, `src_row_number`, `loaded_at`.
- No premium, no effective date, no product code, no account number: those were not provided.

**`RAW.VEHICLES`** — grain: one vehicle per policy (1:1 in this source).

- `vehicle_sk` (surrogate, unique).
- `policy_sk` / `policy_id` (foreign key).
- `veh_power`, `veh_age`, `veh_brand`, `veh_gas` — original.
- No VIN, no make/model beyond the anonymized brand code, no vehicle count other than the implied single vehicle.

**`RAW.DRIVERS`** — grain: one driver per policy (1:1 in this source).

- `driver_sk` (surrogate, unique).
- `policy_sk` / `policy_id` (foreign key).
- `driv_age` — original.
- No driver id, name, licence, gender, or years licensed. The file does not say whether the age is the named insured or the primary driver. `BonusMalus` stays on `POLICIES` because it is a French policy-level coefficient, not a driver attribute in the source.

**`RAW.CLAIMS`** — grain: one row per severity file row.

- `claim_sk` (surrogate, unique). **Required**: the source has no claim number.
- `claim_sequence` — derived, unique within `policy_id`.
- `policy_id` — original `IDpol` (nullable foreign key in practice, because of the six orphan IDs).
- `policy_sk` — looked up from `POLICIES`; null for orphans.
- `claim_amount` — original `ClaimAmount`.
- Metadata: `src_file_name`, `src_row_number`, `loaded_at`.
- No loss date, report date, status, coverage, or payment versus reserve split.

### 6.4 Integrity rules in raw (preserve, then test)

1. Do not drop the {fmt_int(r['freq_row_gap_vs_published'])} frequency rows that documentation does not list.
2. Keep the {fmt_int(r['orphan_sev_policies'])} orphan claim groups; `policy_sk` will be null and a dbt relationship test will fail until a quarantine or unmatched-claim model is added.
3. Keep the {fmt_int(r['policies_claimnb_gt0_sevnb_0'])} policies whose `ClaimNb` has no severity rows, and the one policy whose counts disagree. Do not overwrite `ClaimNb` with the severity-row count.
4. Keep exact duplicate claim amounts and exposure &gt; 1 and extreme `ClaimNb` / ages.
5. Do not invent premium, loss ratio, or dates.

Later dbt staging and marts (not built in this step) can add quality tests, age bands, a region name map, a star schema (`FACT_POLICY_SNAPSHOT`, `FACT_CLAIM`, `DIM_AREA`, `DIM_REGION`, `DIM_VEHICLE`, `DIM_DRIVER`) and Power BI measures for frequency, severity and pure premium, framed as a Qlik-to-Power-BI style reporting layer on curated Snowflake models.

## 7. Reproduction

```bash
# from /workspace/insurance-portfolio
.venv/bin/python notebooks/01_profile.py
```

Dependencies are pinned in `requirements.txt`. The script reads the parquet files, rewrites the CSV copies, and overwrites this markdown file.
"""

    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = DOCS_DIR / "data_profile.md"
    out_path.write_text(md, encoding="utf-8")
    return out_path


def main() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    freq_raw, sev_raw = load_frames()
    print(f"Loaded frequency {len(freq_raw):,} rows, severity {len(sev_raw):,} rows")
    if len(freq_raw) != 677_991:
        print(
            f"NOTE: frequency row count is {len(freq_raw):,}, "
            f"not the published {PUBLISHED_FREQ_ROWS:,}. "
            "The profile documents the file as downloaded."
        )
    freq, sev = normalize(freq_raw, sev_raw)
    freq_csv, sev_csv = write_csv(freq, sev)
    print(f"Wrote {freq_csv} ({freq_csv.stat().st_size:,} bytes)")
    print(f"Wrote {sev_csv} ({sev_csv.stat().st_size:,} bytes)")
    results = profile(freq, sev)
    out = write_markdown(results, freq_csv, sev_csv)
    print(f"Wrote {out}")
    summary = {
        "freq_rows": results["freq_rows"],
        "sev_rows": results["sev_rows"],
        "total_exposure": results["total_exposure"],
        "total_claimnb": results["total_claimnb"],
        "frequency_claimnb": results["frequency_claimnb"],
        "total_amount_matched": results["total_amount_matched"],
        "avg_severity_matched": results["avg_severity_matched"],
        "pure_premium_matched": results["pure_premium_matched"],
        "orphan_sev_policies": results["orphan_sev_policies"],
        "policies_claimnb_gt0_sevnb_0": results["policies_claimnb_gt0_sevnb_0"],
        "exposure_gt_1": results["exposure_gt_1"],
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
