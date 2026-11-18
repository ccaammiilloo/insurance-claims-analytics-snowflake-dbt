#!/usr/bin/env python3
"""Generate the InsurancePortfolio PBIP (TMDL + PBIR) from live MARTS metadata.

No Snowflake credentials are written into the output. Connection parameters
are server, warehouse, and role only. Run from the repo; outputs go to
powerbi/. This script is deterministic (stable IDs and lineage tags).
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import uuid
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "powerbi"
PROJECT = "InsurancePortfolio"
THEME_CANDIDATES = [
    Path("/tmp/pbi-examples/CY26SU02.json"),
    Path("/tmp/pbi-poc/templates_pbir-base-theme_CY26SU02.json"),
    ROOT / "powerbi" / f"{PROJECT}.Report" / "StaticResources" / "SharedResources" / "BaseThemes" / "CY26SU02.json",
]
THEME_URL = "https://raw.githubusercontent.com/solid-data-public/powerbi-poc/main/templates/pbir-base-theme/CY26SU02.json"

SERVER = "wngvror-ly04177.snowflakecomputing.com"
WAREHOUSE = "COMPUTE_WH"
DATABASE = "INSURANCE_PORTFOLIO"
SCHEMA = "MARTS"
ROLE = "INSURANCE_PBI_READONLY"



def lid(*parts: str) -> str:
    name = "insurance-portfolio:" + ":".join(parts)
    return str(uuid.uuid5(uuid.NAMESPACE_URL, name))


def hid(*parts: str) -> str:
    name = "insurance-portfolio:" + ":".join(parts)
    return hashlib.sha1(name.encode("utf-8")).hexdigest()[:20]


def t(*lines: str) -> str:
    """Join lines and ensure trailing newline. Callers pass already-tabbed text."""
    text = "\n".join(lines).rstrip() + "\n"
    return text


def col(
    name: str,
    data_type: str,
    *,
    table: str,
    hidden: bool = False,
    key: bool = False,
    unique: bool = False,
    format_string: str | None = None,
    sort_by: str | None = None,
    source: str | None = None,
    description: str | None = None,
) -> str:
    lines: list[str] = []
    if description:
        lines.append(f"\t/// {description}")
    lines.append(f"\tcolumn {name}")
    lines.append(f"\t\tdataType: {data_type}")
    if format_string:
        lines.append(f"\t\tformatString: {format_string}")
    lines.append(f"\t\tlineageTag: {lid('col', table, name)}")
    if source is not None:
        lines.append(f"\t\tsourceColumn: {source}")
    if sort_by:
        lines.append(f"\t\tsortByColumn: {sort_by}")
    lines.append("\t\tsummarizeBy: none")
    if key:
        lines.append("\t\tisKey")
    if unique:
        lines.append("\t\tisUnique")
    if hidden:
        lines.append("\t\tisHidden")
    lines.append("")
    lines.append("\t\tannotation SummarizationSetBy = Automatic")
    lines.append("")
    return "\n".join(lines)


def calc_col(name: str, dax: str, *, table: str, hidden: bool = True) -> str:
    # Keep DAX on following indented lines or a single line
    return (
        f"\tcolumn {name} =\n"
        f"\t\t\t{dax}\n"
        f"\t\tdataType: int64\n"
        f"\t\tformatString: 0\n"
        f"\t\tlineageTag: {lid('col', table, name)}\n"
        f"\t\tsummarizeBy: none\n"
        + ("\t\tisHidden\n" if hidden else "")
        + "\n"
    )


def m_partition(table: str) -> str:
    # Indented M expression (TMDL strips the outer indent).
    return (
        f"\tpartition {table} = m\n"
        f"\t\tmode: import\n"
        f"\t\tsource =\n"
        f"\t\t\tlet\n"
        f"\t\t\t\tSource = Snowflake.Databases(SnowflakeServer, SnowflakeWarehouse, [Role=SnowflakeRole, Implementation=\"2.0\"]),\n"
        f"\t\t\t\t#\"Db\" = Source{{[Name=\"{DATABASE}\",Kind=\"Database\"]}}[Data],\n"
        f"\t\t\t\t#\"Schema\" = #\"Db\"{{[Name=\"{SCHEMA}\",Kind=\"Schema\"]}}[Data],\n"
        f"\t\t\t\t#\"DataTable\" = #\"Schema\"{{[Name=\"{table}\",Kind=\"Table\"]}}[Data]\n"
        f"\t\t\tin\n"
        f"\t\t\t\t#\"DataTable\"\n"
    )


def table_file(name: str, description: str, columns_tmdl: str) -> str:
    return (
        f"/// {description}\n"
        f"table {name}\n"
        f"\tlineageTag: {lid('table', name)}\n"
        f"\n"
        f"{columns_tmdl}"
        f"{m_partition(name)}"
    )


def measure(name: str, dax: str, fmt: str, folder: str, description: str) -> str:
    # Multi-line DAX: indent body one level deeper than properties.
    dax = dax.strip()
    if "\n" in dax:
        body = "\n".join("\t\t\t" + line if line else "" for line in dax.split("\n"))
        expr = f"\tmeasure '{name}' =\n{body}\n"
    else:
        expr = f"\tmeasure '{name}' = {dax}\n"
    return (
        f"\t/// {description}\n"
        f"{expr}"
        f"\t\tformatString: {fmt}\n"
        f"\t\tdisplayFolder: {folder}\n"
        f"\t\tlineageTag: {lid('measure', name)}\n"
        f"\n"
    )


# ---------------------------------------------------------------------------
# Semantic model
# ---------------------------------------------------------------------------

DIM_POLICY_COLS = (
    col("POLICY_SK", "string", hidden=True, key=True, unique=True, source="POLICY_SK", table="DIM_POLICY")
    + col("POLICY_ID", "int64", format_string="0", source="POLICY_ID", table="DIM_POLICY")
    + col("AREA", "string", source="AREA", table="DIM_POLICY")
    + col("BONUS_MALUS", "int64", format_string="0", source="BONUS_MALUS", table="DIM_POLICY")
    + col("BONUS_MALUS_BAND", "string", source="BONUS_MALUS_BAND", sort_by="BONUS_MALUS_BAND_SORT", table="DIM_POLICY")
    + calc_col(
        "BONUS_MALUS_BAND_SORT",
        'SWITCH ( \'DIM_POLICY\'[BONUS_MALUS_BAND], "50 (maximum bonus)", 50, "51-80", 51, "81-99", 81, "100 (reference)", 100, "101-150", 101, "151+", 151, 99 )',
        table="DIM_POLICY")
    + col("DENSITY", "int64", format_string="#,0", source="DENSITY", table="DIM_POLICY")
    + col("REGION", "string", source="REGION", table="DIM_POLICY")
    + col("REGION_NAME", "string", source="REGION_NAME", sort_by="REGION", table="DIM_POLICY")
    + col("BOOK_PERIOD_LABEL", "string", source="BOOK_PERIOD_LABEL", table="DIM_POLICY")
    + col("IS_EXPOSURE_GT_ONE", "boolean", source="IS_EXPOSURE_GT_ONE", table="DIM_POLICY")
    + col("IS_EXTREME_CLAIM_COUNT", "boolean", source="IS_EXTREME_CLAIM_COUNT", table="DIM_POLICY")
)

DIM_VEHICLE_COLS = (
    col("VEHICLE_SK", "string", hidden=True, key=True, unique=True, source="VEHICLE_SK", table="DIM_VEHICLE")
    + col("POLICY_SK", "string", hidden=True, source="POLICY_SK", table="DIM_VEHICLE")
    + col("POLICY_ID", "int64", format_string="0", source="POLICY_ID", table="DIM_VEHICLE")
    + col("VEH_POWER", "int64", format_string="0", source="VEH_POWER", table="DIM_VEHICLE")
    + col("VEH_AGE", "int64", format_string="0", source="VEH_AGE", table="DIM_VEHICLE")
    + col("VEH_AGE_BAND", "string", source="VEH_AGE_BAND", sort_by="VEH_AGE_BAND_SORT", table="DIM_VEHICLE")
    + calc_col(
        "VEH_AGE_BAND_SORT",
        'SWITCH ( \'DIM_VEHICLE\'[VEH_AGE_BAND], "0", 0, "1-4", 1, "5-9", 5, "10-14", 10, "15-19", 15, "20+", 20, 99 )',
        table="DIM_VEHICLE")
    + col("VEH_BRAND", "string", source="VEH_BRAND", table="DIM_VEHICLE")
    + col("VEH_GAS", "string", source="VEH_GAS", table="DIM_VEHICLE")
    + col("IS_NEW_VEHICLE", "boolean", source="IS_NEW_VEHICLE", table="DIM_VEHICLE")
    + col("IS_VEHICLE_AGE_SENTINEL", "boolean", source="IS_VEHICLE_AGE_SENTINEL", table="DIM_VEHICLE")
)

DIM_DRIVER_COLS = (
    col("DRIVER_SK", "string", hidden=True, key=True, unique=True, source="DRIVER_SK", table="DIM_DRIVER")
    + col("POLICY_SK", "string", hidden=True, source="POLICY_SK", table="DIM_DRIVER")
    + col("POLICY_ID", "int64", format_string="0", source="POLICY_ID", table="DIM_DRIVER")
    + col("DRIV_AGE", "int64", format_string="0", source="DRIV_AGE", table="DIM_DRIVER")
    + col("DRIV_AGE_BAND", "string", source="DRIV_AGE_BAND", sort_by="DRIV_AGE_BAND_SORT", table="DIM_DRIVER")
    + calc_col(
        "DRIV_AGE_BAND_SORT",
        'SWITCH ( \'DIM_DRIVER\'[DRIV_AGE_BAND], "18-25", 18, "26-35", 26, "36-45", 36, "46-55", 46, "56-65", 56, "66-75", 66, "76+", 76, 99 )',
        table="DIM_DRIVER")
    + col("IS_DRIVER_AGE_SENTINEL", "boolean", source="IS_DRIVER_AGE_SENTINEL", table="DIM_DRIVER")
)

FCT_CLAIMS_COLS = (
    col("CLAIM_SK", "string", hidden=True, key=True, unique=True, source="CLAIM_SK", table="FCT_CLAIMS")
    + col("CLAIM_SEQUENCE", "int64", format_string="0", source="CLAIM_SEQUENCE", table="FCT_CLAIMS")
    + col("POLICY_ID", "int64", format_string="0", source="POLICY_ID", table="FCT_CLAIMS")
    + col("POLICY_SK", "string", hidden=True, source="POLICY_SK", table="FCT_CLAIMS")
    + col("VEHICLE_SK", "string", hidden=True, source="VEHICLE_SK", table="FCT_CLAIMS")
    + col("DRIVER_SK", "string", hidden=True, source="DRIVER_SK", table="FCT_CLAIMS")
    + col("CLAIM_AMOUNT", "decimal", format_string="#,0.00", source="CLAIM_AMOUNT", table="FCT_CLAIMS")
    + col("IS_ORPHAN_CLAIM", "boolean", source="IS_ORPHAN_CLAIM", table="FCT_CLAIMS")
    + col("IS_DUPLICATE_AMOUNT_ROW", "boolean", source="IS_DUPLICATE_AMOUNT_ROW", table="FCT_CLAIMS")
    + col("SRC_ROW_NUMBER", "int64", format_string="0", source="SRC_ROW_NUMBER", table="FCT_CLAIMS")
)

FCT_EXPOSURE_COLS = (
    col("POLICY_SK", "string", hidden=True, key=True, unique=True, source="POLICY_SK", table="FCT_POLICY_EXPOSURE")
    + col("POLICY_ID", "int64", format_string="0", source="POLICY_ID", table="FCT_POLICY_EXPOSURE")
    + col("VEHICLE_SK", "string", hidden=True, source="VEHICLE_SK", table="FCT_POLICY_EXPOSURE")
    + col("DRIVER_SK", "string", hidden=True, source="DRIVER_SK", table="FCT_POLICY_EXPOSURE")
    + col("EXPOSURE_YEARS", "double", format_string="#,0.00", source="EXPOSURE_YEARS", table="FCT_POLICY_EXPOSURE")
    + col("CLAIM_COUNT", "int64", format_string="#,0", source="CLAIM_COUNT", table="FCT_POLICY_EXPOSURE")
    + col("SEVERITY_ROW_COUNT", "int64", format_string="#,0", source="SEVERITY_ROW_COUNT", table="FCT_POLICY_EXPOSURE")
    + col("MATCHED_CLAIM_AMOUNT", "decimal", format_string="#,0.00", source="MATCHED_CLAIM_AMOUNT", table="FCT_POLICY_EXPOSURE")
    + col("CLAIM_COUNT_MATCHES_SEVERITY_ROWS", "boolean", source="CLAIM_COUNT_MATCHES_SEVERITY_ROWS", table="FCT_POLICY_EXPOSURE")
    + col("HAS_MISSING_SEVERITY", "boolean", source="HAS_MISSING_SEVERITY", table="FCT_POLICY_EXPOSURE")
    + col("HAS_UNEXPECTED_SEVERITY", "boolean", source="HAS_UNEXPECTED_SEVERITY", table="FCT_POLICY_EXPOSURE")
    + col("HAS_COUNT_MISMATCH_BOTH_POSITIVE", "boolean", source="HAS_COUNT_MISMATCH_BOTH_POSITIVE", table="FCT_POLICY_EXPOSURE")
    + col("MISSING_SEVERITY_CLAIM_UNITS", "int64", format_string="#,0", source="MISSING_SEVERITY_CLAIM_UNITS", table="FCT_POLICY_EXPOSURE")
    + col("IS_EXPOSURE_GT_ONE", "boolean", source="IS_EXPOSURE_GT_ONE", table="FCT_POLICY_EXPOSURE")
    + col("IS_EXTREME_CLAIM_COUNT", "boolean", source="IS_EXTREME_CLAIM_COUNT", table="FCT_POLICY_EXPOSURE")
)

MART_SEGMENTS_COLS = (
    col("SEGMENT_TYPE", "string", source="SEGMENT_TYPE", table="MART_RISK_SEGMENTS")
    + col("SEGMENT_VALUE", "string", source="SEGMENT_VALUE", table="MART_RISK_SEGMENTS")
    + col("SEGMENT_LABEL", "string", source="SEGMENT_LABEL", table="MART_RISK_SEGMENTS")
    + col("POLICY_COUNT", "int64", format_string="#,0", source="POLICY_COUNT", table="MART_RISK_SEGMENTS")
    + col("EXPOSURE_YEARS", "double", format_string="#,0.00", source="EXPOSURE_YEARS", table="MART_RISK_SEGMENTS")
    + col("CLAIM_COUNT", "int64", format_string="#,0", source="CLAIM_COUNT", table="MART_RISK_SEGMENTS")
    + col("CLAIM_FREQUENCY", "double", format_string="0.000000", source="CLAIM_FREQUENCY", table="MART_RISK_SEGMENTS")
    + col("SEVERITY_ROW_COUNT", "int64", format_string="#,0", source="SEVERITY_ROW_COUNT", table="MART_RISK_SEGMENTS")
    + col("MATCHED_CLAIM_AMOUNT", "decimal", format_string="#,0.00", source="MATCHED_CLAIM_AMOUNT", table="MART_RISK_SEGMENTS")
    + col("AVERAGE_SEVERITY", "double", format_string="#,0.00", source="AVERAGE_SEVERITY", table="MART_RISK_SEGMENTS")
    + col("PURE_PREMIUM", "double", format_string="#,0.00", source="PURE_PREMIUM", table="MART_RISK_SEGMENTS")
)

MEASURES = [
    (
        "Policy Count",
        "COUNTROWS ( 'FCT_POLICY_EXPOSURE' )",
        "#,0",
        "Portfolio",
        "Number of policies in the exposure fact. Book total is 678,013.",
    ),
    (
        "Exposure",
        "SUM ( 'FCT_POLICY_EXPOSURE'[EXPOSURE_YEARS] )",
        "#,0.00",
        "Portfolio",
        "Sum of exposure years. Book total is 358,499.45.",
    ),
    (
        "Claim Count",
        "SUM ( 'FCT_POLICY_EXPOSURE'[CLAIM_COUNT] )",
        "#,0",
        "Portfolio",
        "Sum of ClaimNb on the exposure fact, not the severity row count. Book total is 36,102.",
    ),
    (
        "Claim Frequency",
        "DIVIDE ( [Claim Count], [Exposure] )",
        "0.000000",
        "Portfolio",
        "Claim Count divided by Exposure. Book total is 0.100703. This is claims per exposure year, not a percentage.",
    ),
    (
        "Matched Claim Amount",
        "SUM ( 'FCT_POLICY_EXPOSURE'[MATCHED_CLAIM_AMOUNT] )",
        "#,0.00",
        "Portfolio",
        "Matched claim amount on the exposure fact. Book total is 59,909,216.50. Must agree with Matched Claim Amount From Claims.",
    ),
    (
        "Matched Severity Rows",
        "SUM ( 'FCT_POLICY_EXPOSURE'[SEVERITY_ROW_COUNT] )",
        "#,0",
        "Portfolio",
        "Severity rows that match a policy. Book total is 26,444.",
    ),
    (
        "Average Severity",
        "DIVIDE ( [Matched Claim Amount], [Matched Severity Rows] )",
        "#,0.00",
        "Portfolio",
        "Matched claim amount divided by matched severity rows. Book total is 2,265.51. Orphan claims are excluded.",
    ),
    (
        "Pure Premium",
        "DIVIDE ( [Matched Claim Amount], [Exposure] )",
        "#,0.00",
        "Portfolio",
        "Matched claim amount divided by exposure. Book total is 167.11. There is no loss ratio because the source has no premium.",
    ),
    (
        "Policies With Claims",
        "CALCULATE (\n    COUNTROWS ( 'FCT_POLICY_EXPOSURE' ),\n    'FCT_POLICY_EXPOSURE'[CLAIM_COUNT] > 0\n)",
        "#,0",
        "Portfolio",
        "Policies with Claim Count greater than zero. Book total is 34,060.",
    ),
    (
        "Policies With Claims %",
        "DIVIDE ( [Policies With Claims], [Policy Count] )",
        "0.00%",
        "Portfolio",
        "Share of policies with at least one claim. Book total is 5.02%.",
    ),
    (
        "Policies With Missing Severity",
        "CALCULATE (\n    COUNTROWS ( 'FCT_POLICY_EXPOSURE' ),\n    'FCT_POLICY_EXPOSURE'[HAS_MISSING_SEVERITY] = TRUE ()\n)",
        "#,0",
        "Quality",
        "Policies with Claim Count greater than zero and no severity row. Book total is 9,116.",
    ),
    (
        "Missing Severity Claim Units",
        "SUM ( 'FCT_POLICY_EXPOSURE'[MISSING_SEVERITY_CLAIM_UNITS] )",
        "#,0",
        "Quality",
        "Claim units with no matching severity row, including the one policy with a count mismatch. Book total is 9,658.",
    ),
    (
        "Exposure Over One Year",
        "CALCULATE (\n    COUNTROWS ( 'FCT_POLICY_EXPOSURE' ),\n    'FCT_POLICY_EXPOSURE'[IS_EXPOSURE_GT_ONE] = TRUE ()\n)",
        "#,0",
        "Quality",
        "Policies whose exposure is greater than one year. Book total is 1,224. The maximum exposure is 2.01 years.",
    ),
    (
        "Extreme Claim Count Policies",
        "CALCULATE (\n    COUNTROWS ( 'FCT_POLICY_EXPOSURE' ),\n    'FCT_POLICY_EXPOSURE'[IS_EXTREME_CLAIM_COUNT] = TRUE ()\n)",
        "#,0",
        "Quality",
        "Policies flagged with an extreme claim count (ClaimNb of 4 or more). Book total is 16.",
    ),
    (
        "Policies With Count Mismatch",
        "CALCULATE (\n    COUNTROWS ( 'FCT_POLICY_EXPOSURE' ),\n    'FCT_POLICY_EXPOSURE'[HAS_COUNT_MISMATCH_BOTH_POSITIVE] = TRUE ()\n)",
        "#,0",
        "Quality",
        "Policies where Claim Count and severity row count are both positive and different. Book total is 1 (IDpol 4,158,255).",
    ),
    (
        "Claim Amount All Rows",
        "SUM ( 'FCT_CLAIMS'[CLAIM_AMOUNT] )",
        "#,0.00",
        "Claims detail",
        "Sum of claim amount on every severity row, including orphans. Book total is 60,697,930.68.",
    ),
    (
        "Matched Claim Amount From Claims",
        "CALCULATE (\n    SUM ( 'FCT_CLAIMS'[CLAIM_AMOUNT] ),\n    'FCT_CLAIMS'[IS_ORPHAN_CLAIM] = FALSE ()\n)",
        "#,0.00",
        "Claims detail",
        "Claim amount on non-orphan severity rows. Must equal Matched Claim Amount at book level: 59,909,216.50.",
    ),
    (
        "Orphan Claim Amount",
        "CALCULATE (\n    SUM ( 'FCT_CLAIMS'[CLAIM_AMOUNT] ),\n    'FCT_CLAIMS'[IS_ORPHAN_CLAIM] = TRUE ()\n)",
        "#,0.00",
        "Quality",
        "Claim amount on orphan severity rows (no matching policy). Book total is 788,714.18. Excluded from official Average Severity and Pure Premium.",
    ),
    (
        "Orphan Claim Rows",
        "CALCULATE (\n    COUNTROWS ( 'FCT_CLAIMS' ),\n    'FCT_CLAIMS'[IS_ORPHAN_CLAIM] = TRUE ()\n)",
        "#,0",
        "Quality",
        "Orphan severity rows with no matching policy. Book total is 195 rows across 6 policy IDs.",
    ),
    (
        "Orphan Claim IDs",
        "CALCULATE (\n    DISTINCTCOUNT ( 'FCT_CLAIMS'[POLICY_ID] ),\n    'FCT_CLAIMS'[IS_ORPHAN_CLAIM] = TRUE ()\n)",
        "#,0",
        "Quality",
        "Distinct policy IDs that appear only in the severity file. Book total is 6.",
    ),
    (
        "Duplicate Amount Rows",
        "CALCULATE (\n    COUNTROWS ( 'FCT_CLAIMS' ),\n    'FCT_CLAIMS'[IS_DUPLICATE_AMOUNT_ROW] = TRUE ()\n)",
        "#,0",
        "Quality",
        "Severity rows flagged as duplicate amount rows. Book total is 496.",
    ),
    (
        "Average Severity From Claims",
        "DIVIDE (\n    [Matched Claim Amount From Claims],\n    CALCULATE (\n        COUNTROWS ( 'FCT_CLAIMS' ),\n        'FCT_CLAIMS'[IS_ORPHAN_CLAIM] = FALSE ()\n    )\n)",
        "#,0.00",
        "Claims detail",
        "Matched claim amount from the claims fact divided by non-orphan claim rows. Must agree with Average Severity at book level: 2,265.51.",
    ),
]


def measures_table() -> str:
    parts = [
        "/// Dedicated measures table. Official portfolio, quality, and claim-detail measures live here.\n"
        "table '_Measures'\n"
        f"\tlineageTag: {lid('table', '_Measures')}\n"
        "\n"
    ]
    for item in MEASURES:
        parts.append(measure(*item))
    parts.append(
        "\tcolumn Measure\n"
        "\t\tdataType: string\n"
        f"\t\tlineageTag: {lid('col', '_Measures.Measure')}\n"
        "\t\tsummarizeBy: none\n"
        "\t\tisHidden\n"
        "\n"
        "\tpartition '_Measures' = calculated\n"
        "\t\tmode: import\n"
        "\t\tsource =\n"
        "\t\t\tROW ( \"Measure\", BLANK () )\n"
    )
    return "".join(parts)


def expressions_tmdl() -> str:
    return (
        "/// Non-secret Snowflake connection parameters for Power BI Desktop import.\n"
        "/// Credentials stay in Desktop's credential store and are matched by server.\n"
        f'expression SnowflakeServer = "{SERVER}" meta [IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]\n'
        f'expression SnowflakeWarehouse = "{WAREHOUSE}" meta [IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]\n'
        f'expression SnowflakeRole = "{ROLE}" meta [IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]\n'
    )


def model_tmdl() -> str:
    refs = "\n".join(
        f"ref table {n}"
        for n in [
            "DIM_POLICY",
            "DIM_VEHICLE",
            "DIM_DRIVER",
            "FCT_POLICY_EXPOSURE",
            "FCT_CLAIMS",
            "MART_RISK_SEGMENTS",
            "'_Measures'",
        ]
    )
    return (
        "model Model\n"
        "\tculture: en-US\n"
        "\tdefaultPowerBIDataSourceVersion: powerBI_V3\n"
        "\tdiscourageImplicitMeasures\n"
        "\tsourceQueryCulture: en-US\n"
        "\tdataAccessOptions\n"
        "\t\tlegacyRedirects\n"
        "\t\treturnErrorValuesAsNull\n"
        "\n"
        "annotation __PBI_TimeIntelligenceEnabled = 0\n"
        "\n"
        'annotation PBI_QueryOrder = ["SnowflakeServer","SnowflakeWarehouse","SnowflakeRole","DIM_POLICY","DIM_VEHICLE","DIM_DRIVER","FCT_POLICY_EXPOSURE","FCT_CLAIMS","MART_RISK_SEGMENTS"]\n'
        "\n"
        f"{refs}\n"
    )


def relationships_tmdl() -> str:
    pairs = [
        ("FCT_POLICY_EXPOSURE_DIM_POLICY", "FCT_POLICY_EXPOSURE.POLICY_SK", "DIM_POLICY.POLICY_SK"),
        ("FCT_POLICY_EXPOSURE_DIM_VEHICLE", "FCT_POLICY_EXPOSURE.VEHICLE_SK", "DIM_VEHICLE.VEHICLE_SK"),
        ("FCT_POLICY_EXPOSURE_DIM_DRIVER", "FCT_POLICY_EXPOSURE.DRIVER_SK", "DIM_DRIVER.DRIVER_SK"),
        ("FCT_CLAIMS_DIM_POLICY", "FCT_CLAIMS.POLICY_SK", "DIM_POLICY.POLICY_SK"),
        ("FCT_CLAIMS_DIM_VEHICLE", "FCT_CLAIMS.VEHICLE_SK", "DIM_VEHICLE.VEHICLE_SK"),
        ("FCT_CLAIMS_DIM_DRIVER", "FCT_CLAIMS.DRIVER_SK", "DIM_DRIVER.DRIVER_SK"),
    ]
    blocks = []
    for name, frm, to in pairs:
        blocks.append(
            f"relationship {name}\n"
            f"\tfromCardinality: many\n"
            f"\ttoCardinality: one\n"
            f"\tcrossFilteringBehavior: oneDirection\n"
            f"\tfromColumn: {frm}\n"
            f"\ttoColumn: {to}\n"
        )
    return "\n".join(blocks)


def database_tmdl() -> str:
    return "database\n\tcompatibilityLevel: 1604\n"


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(obj, indent=2, ensure_ascii=False)
    path.write_text(text + "\n", encoding="utf-8", newline="\n")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not text.endswith("\n"):
        text += "\n"
    path.write_text(text, encoding="utf-8", newline="\n")


# ---------------------------------------------------------------------------
# Report (PBIR) helpers
# ---------------------------------------------------------------------------

SCHEMA_VISUAL = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.7.0/schema.json"
SCHEMA_PAGE = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/2.1.0/schema.json"
SCHEMA_PAGES = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/pagesMetadata/1.0.0/schema.json"
SCHEMA_REPORT = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/report/3.2.0/schema.json"
SCHEMA_VERSION = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/versionMetadata/1.0.0/schema.json"
SCHEMA_PBIR = "https://developer.microsoft.com/json-schemas/fabric/item/report/definitionProperties/2.0.0/schema.json"
SCHEMA_PBISM = "https://developer.microsoft.com/json-schemas/fabric/item/semanticModel/definitionProperties/1.0.0/schema.json"
SCHEMA_PBIP = "https://developer.microsoft.com/json-schemas/fabric/pbip/pbipProperties/1.0.0/schema.json"
SCHEMA_PLATFORM = "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json"

MEASURES_ENTITY = "_Measures"


def literal(value: str) -> dict:
    return {"expr": {"Literal": {"Value": value}}}


def theme_color(color_id: int, percent: float = 0) -> dict:
    return {"expr": {"ThemeDataColor": {"ColorId": color_id, "Percent": percent}}}


def measure_field(name: str) -> dict:
    return {
        "field": {
            "Measure": {
                "Expression": {"SourceRef": {"Entity": MEASURES_ENTITY}},
                "Property": name,
            }
        },
        "queryRef": f"{MEASURES_ENTITY}.{name}",
        "nativeQueryRef": name,
    }


def column_field(entity: str, name: str, active: bool | None = None) -> dict:
    proj: dict = {
        "field": {
            "Column": {
                "Expression": {"SourceRef": {"Entity": entity}},
                "Property": name,
            }
        },
        "queryRef": f"{entity}.{name}",
        "nativeQueryRef": name,
    }
    if active is not None:
        proj["active"] = active
    return proj


def hide_chrome(title: str | None = None) -> dict:
    objs: dict = {
        "border": [{"properties": {"show": literal("false")}}],
        "visualHeader": [
            {
                "properties": {
                    "showCopyVisualImageButton": literal("false"),
                    "showFilterRestatementButton": literal("false"),
                    "showFocusModeButton": literal("false"),
                    "showPinButton": literal("false"),
                }
            }
        ],
    }
    if title:
        objs["title"] = [
            {
                "properties": {
                    "show": literal("true"),
                    "text": literal(f"'{title}'"),
                }
            }
        ]
    else:
        objs["title"] = [{"properties": {"show": literal("false")}}]
    return objs


def container(name: str, x: float, y: float, w: float, h: float, z: int, visual: dict, tab: int | None = None) -> dict:
    pos = {"x": x, "y": y, "z": z, "height": h, "width": w}
    if tab is not None:
        pos["tabOrder"] = tab
    else:
        pos["tabOrder"] = z
    return {
        "$schema": SCHEMA_VISUAL,
        "name": name,
        "position": pos,
        "visual": visual,
    }


def card(page: str, key: str, measure_name: str, x, y, w, h, z) -> tuple[str, dict]:
    name = hid("visual", page, key)
    visual = {
        "visualType": "cardVisual",
        "query": {"queryState": {"Data": {"projections": [measure_field(measure_name)]}}},
        "visualContainerObjects": hide_chrome(),
        "drillFilterOtherVisuals": True,
    }
    return name, container(name, x, y, w, h, z, visual)


def chart(
    page: str,
    key: str,
    visual_type: str,
    entity: str,
    column: str,
    measure_name: str,
    x, y, w, h, z,
    title: str,
    sort: str = "category_asc",
    tooltips: list[str] | None = None,
) -> tuple[str, dict]:
    name = hid("visual", page, key)
    query_state: dict = {
        "Category": {"projections": [column_field(entity, column, active=True)]},
        "Y": {"projections": [measure_field(measure_name)]},
    }
    tips = tooltips or [
        "Average Severity",
        "Pure Premium",
        "Claim Count",
        "Matched Severity Rows",
        "Exposure",
        "Policy Count",
    ]
    query_state["Tooltips"] = {"projections": [measure_field(m) for m in tips]}
    if sort == "category_asc":
        sort_def = {
            "sort": [{"field": column_field(entity, column)["field"], "direction": "Ascending"}],
            "isDefaultSort": True,
        }
    else:
        sort_def = {
            "sort": [{"field": measure_field(measure_name)["field"], "direction": "Descending"}],
            "isDefaultSort": True,
        }
    visual = {
        "visualType": visual_type,
        "query": {"queryState": query_state, "sortDefinition": sort_def},
        "objects": {
            "categoryAxis": [{"properties": {"axisType": literal("'Categorical'")}}],
            "labels": [{"properties": {"show": literal("true")}}],
        },
        "visualContainerObjects": hide_chrome(title),
        "drillFilterOtherVisuals": True,
    }
    return name, container(name, x, y, w, h, z, visual)


def table_visual(page: str, key: str, projections: list[dict], x, y, w, h, z, title: str) -> tuple[str, dict]:
    name = hid("visual", page, key)
    visual = {
        "visualType": "tableEx",
        "query": {"queryState": {"Values": {"projections": projections}}},
        "visualContainerObjects": hide_chrome(title),
        "drillFilterOtherVisuals": True,
    }
    return name, container(name, x, y, w, h, z, visual)


def textbox(page: str, key: str, paragraphs: list[dict], x, y, w, h, z, transparent: bool = True) -> tuple[str, dict]:
    name = hid("visual", page, key)
    vco = hide_chrome()
    if transparent:
        vco["background"] = [{"properties": {"show": literal("false")}}]
    visual = {
        "visualType": "textbox",
        "objects": {"general": [{"properties": {"paragraphs": paragraphs}}]},
        "visualContainerObjects": vco,
        "drillFilterOtherVisuals": True,
    }
    return name, container(name, x, y, w, h, z, visual)


def para(runs: list[dict], halign: str | None = None) -> dict:
    p: dict = {"textRuns": runs}
    if halign:
        p["horizontalTextAlignment"] = halign
    return p


def run(text: str, size: str, color: str, bold: bool = False) -> dict:
    style = {"fontSize": size, "color": color}
    if bold:
        style["fontFamily"] = "Segoe UI Semibold"
        style["fontWeight"] = "bold"
    else:
        style["fontFamily"] = "Segoe UI"
    return {"value": text, "textStyle": style}


def header_shape(page: str, color: str = "#1B365D") -> tuple[str, dict]:
    name = hid("visual", page, "header-bar")
    visual = {
        "visualType": "shape",
        "objects": {
            "shape": [{"properties": {"tileShape": literal("'rectangle'")}}],
            "fill": [
                {
                    "properties": {
                        "fillColor": {"solid": {"color": {"expr": {"Literal": {"Value": f"'{color}'"}}}}},
                        "show": literal("true"),
                    },
                    "selector": {"id": "default"},
                }
            ],
            "outline": [{"properties": {"show": literal("false")}}],
        },
        "visualContainerObjects": {
            "background": [
                {
                    "properties": {
                        "show": literal("true"),
                        "color": {"solid": {"color": {"expr": {"Literal": {"Value": f"'{color}'"}}}}},
                    }
                }
            ],
            "border": [{"properties": {"show": literal("false")}}],
            "title": [{"properties": {"show": literal("false")}}],
        },
        "drillFilterOtherVisuals": True,
    }
    return name, container(name, 0, 0, 1280, 72, 0, visual, tab=-1000)


def header_texts(page: str, title: str, subtitle: str) -> list[tuple[str, dict]]:
    t1 = textbox(
        page,
        "header-title",
        [para([run(title, "18pt", "#FFFFFF", bold=True)])],
        16, 8, 1248, 32, 100,
    )
    t2 = textbox(
        page,
        "header-sub",
        [para([run(subtitle, "9pt", "#D6DEE8")])],
        16, 40, 1248, 26, 110,
    )
    return [t1, t2]


def card_row(page: str, measures: list[str], y: float, z0: int, height: float = 108) -> list[tuple[str, dict]]:
    n = len(measures)
    margin = 16
    gap = 8
    width = (1280 - margin * 2 - gap * (n - 1)) / n
    out = []
    for i, m in enumerate(measures):
        x = margin + i * (width + gap)
        key = f"card-{m}"
        out.append(card(page, key, m, round(x, 2), y, round(width, 2), height, z0 + i * 10))
    return out


def page_json(name: str, display: str) -> dict:
    return {
        "$schema": SCHEMA_PAGE,
        "name": name,
        "displayName": display,
        "displayOption": "FitToPage",
        "height": 720,
        "width": 1280,
    }


# ---------------------------------------------------------------------------
# Page definitions
# ---------------------------------------------------------------------------

PAGE_OVERVIEW = hid("page", "overview")
PAGE_RISK = hid("page", "risk-drivers")
PAGE_QUALITY = hid("page", "data-quality")


def build_overview() -> list[tuple[str, dict]]:
    items: list[tuple[str, dict]] = []
    items.append(header_shape("overview"))
    items.extend(
        header_texts(
            "overview",
            "Insurance Portfolio Overview",
            "Qlik to Power BI migration  |  freMTPL2 observation book (approximately 2011 to 2013)  |  Official measures exclude orphan claims",
        )
    )
    kpis = [
        "Policy Count",
        "Exposure",
        "Claim Count",
        "Claim Frequency",
        "Average Severity",
        "Pure Premium",
        "Policies With Claims %",
        "Matched Claim Amount",
    ]
    items.extend(card_row("overview", kpis, 84, 200))
    items.append(
        chart(
            "overview",
            "freq-area",
            "clusteredColumnChart",
            "DIM_POLICY",
            "AREA",
            "Claim Frequency",
            16, 204, 412, 276, 400,
            "Claim Frequency by Area",
            sort="category_asc",
        )
    )
    items.append(
        chart(
            "overview",
            "pp-region",
            "clusteredBarChart",
            "DIM_POLICY",
            "REGION_NAME",
            "Pure Premium",
            436, 204, 420, 276, 410,
            "Pure Premium by Region",
            sort="measure_desc",
        )
    )
    items.append(
        chart(
            "overview",
            "freq-gas",
            "clusteredColumnChart",
            "DIM_VEHICLE",
            "VEH_GAS",
            "Claim Frequency",
            864, 204, 400, 276, 420,
            "Claim Frequency by Fuel Type",
            sort="category_asc",
        )
    )
    items.append(
        table_visual(
            "overview",
            "area-gas-table",
            [
                column_field("DIM_POLICY", "AREA"),
                column_field("DIM_VEHICLE", "VEH_GAS"),
                measure_field("Policy Count"),
                measure_field("Exposure"),
                measure_field("Claim Frequency"),
                measure_field("Average Severity"),
                measure_field("Pure Premium"),
            ],
            16, 488, 860, 216, 500,
            "Area and fuel type",
        )
    )
    note_paras = [
        para([run("About this book", "11pt", "#1B365D", bold=True)]),
        para([run("", "5pt", "#1B365D")]),
        para([run("These figures are for the public freMTPL2 observation book, approximately 2011 to 2013. They are not a live Guidewire extract. The star schema in Snowflake is the layer that would sit behind a Qlik to Power BI migration.", "9pt", "#3B3B3B")]),
        para([run("", "5pt", "#3B3B3B")]),
        para([run("Claim Frequency uses Claim Count (ClaimNb), not the severity row count. Average Severity and Pure Premium use matched claim amounts only. There is no premium in the source, so this model has no Loss Ratio measure.", "9pt", "#3B3B3B")]),
        para([run("", "5pt", "#3B3B3B")]),
        para([run("Book period: ", "9pt", "#3B3B3B", bold=True), run("freMTPL2 observation book (approximately 2011 to 2013)", "9pt", "#3B3B3B")]),
    ]
    items.append(textbox("overview", "about-note", note_paras, 888, 488, 376, 216, 510, transparent=False))
    return items


def build_risk() -> list[tuple[str, dict]]:
    items: list[tuple[str, dict]] = []
    items.append(header_shape("risk"))
    items.extend(
        header_texts(
            "risk",
            "Risk Drivers",
            "Claim frequency by driver, vehicle, territory, and bonus malus. Hover for average severity, pure premium, claim count, and matched severity rows. New vehicles have a large missing severity gap.",
        )
    )
    charts = [
        ("freq-driv-age", "clusteredBarChart", "DIM_DRIVER", "DRIV_AGE_BAND", 16, 84, 412, 248, "Claim Frequency by Driver Age", "category_asc"),
        ("freq-veh-age", "clusteredBarChart", "DIM_VEHICLE", "VEH_AGE_BAND", 436, 84, 412, 248, "Claim Frequency by Vehicle Age", "category_asc"),
        ("freq-veh-power", "clusteredColumnChart", "DIM_VEHICLE", "VEH_POWER", 856, 84, 408, 248, "Claim Frequency by Vehicle Power", "category_asc"),
        ("freq-area", "clusteredColumnChart", "DIM_POLICY", "AREA", 16, 340, 412, 200, "Claim Frequency by Area", "category_asc"),
        ("freq-region", "clusteredBarChart", "DIM_POLICY", "REGION_NAME", 436, 340, 412, 200, "Claim Frequency by Region", "measure_desc"),
        ("freq-bm", "clusteredBarChart", "DIM_POLICY", "BONUS_MALUS_BAND", 856, 340, 408, 200, "Claim Frequency by Bonus Malus", "category_asc"),
    ]
    z = 200
    for key, vtype, entity, column, x, y, w, h, title, sort in charts:
        items.append(chart("risk", key, vtype, entity, column, "Claim Frequency", x, y, w, h, z, title, sort=sort))
        z += 10
    items.append(
        table_visual(
            "risk",
            "veh-age-gap",
            [
                column_field("DIM_VEHICLE", "VEH_AGE_BAND"),
                measure_field("Policy Count"),
                measure_field("Exposure"),
                measure_field("Claim Count"),
                measure_field("Matched Severity Rows"),
                measure_field("Claim Frequency"),
                measure_field("Average Severity"),
                measure_field("Pure Premium"),
            ],
            16, 548, 1248, 156, 400,
            "Vehicle age band: compare Claim Count with Matched Severity Rows (new vehicles have a large gap)",
        )
    )
    return items


def build_quality() -> list[tuple[str, dict]]:
    items: list[tuple[str, dict]] = []
    items.append(header_shape("quality"))
    items.extend(
        header_texts(
            "quality",
            "Data Quality and Reconciliation",
            "Source issues stay visible in the Power BI model, the same way they should during a Qlik to Power BI migration. Official Average Severity and Pure Premium exclude orphan claims.",
        )
    )
    row1 = [
        "Policies With Missing Severity",
        "Missing Severity Claim Units",
        "Orphan Claim Rows",
        "Orphan Claim Amount",
    ]
    row2 = [
        "Duplicate Amount Rows",
        "Exposure Over One Year",
        "Extreme Claim Count Policies",
        "Policies With Count Mismatch",
    ]
    row3 = [
        "Matched Claim Amount",
        "Matched Claim Amount From Claims",
        "Claim Amount All Rows",
        "Orphan Claim IDs",
    ]
    items.extend(card_row("quality", row1, 84, 200))
    items.extend(card_row("quality", row2, 200, 300))
    items.extend(card_row("quality", row3, 316, 400))
    note_paras = [
        para([run("Reconciliation notes (full book)", "12pt", "#1B365D", bold=True)]),
        para([run("", "6pt", "#1B365D")]),
        para([run("Missing severity. ", "9pt", "#1B365D", bold=True), run("9,116 policies have a claim count greater than zero and no severity row. Those rows account for 9,658 missing claim units. That total includes one extra unit from IDpol 4,158,255, which has a Claim Count of 2 and only one severity row (the Policies With Count Mismatch card should show 1).", "9pt", "#3B3B3B")]),
        para([run("", "4pt", "#3B3B3B")]),
        para([run("Orphan claims. ", "9pt", "#1B365D", bold=True), run("195 severity rows (6 policy IDs) have no matching policy. Their amount is 788,714.18. They stay in FCT_CLAIMS with a blank policy relationship and are excluded from official Average Severity and Pure Premium.", "9pt", "#3B3B3B")]),
        para([run("", "4pt", "#3B3B3B")]),
        para([run("Other checks. ", "9pt", "#1B365D", bold=True), run("496 severity rows are flagged as duplicate amount rows. 1,224 policies have exposure greater than one year (maximum 2.01). 16 policies have an extreme claim count (4 or more).", "9pt", "#3B3B3B")]),
        para([run("", "4pt", "#3B3B3B")]),
        para([run("Amount tie-out. ", "9pt", "#1B365D", bold=True), run("Matched Claim Amount and Matched Claim Amount From Claims must both equal 59,909,216.50. Claim Amount All Rows is 60,697,930.68 (matched plus orphan). There is no Loss Ratio measure because the source has no premium.", "9pt", "#3B3B3B")]),
    ]
    items.append(textbox("quality", "recon-notes", note_paras, 16, 436, 1248, 268, 500, transparent=False))
    return items


# ---------------------------------------------------------------------------
# Writers
# ---------------------------------------------------------------------------

def emit_semantic_model(sm: Path) -> None:
    write_json(
        sm / "definition.pbism",
        {"$schema": SCHEMA_PBISM, "version": "4.2", "settings": {}},
    )
    write_json(
        sm / ".platform",
        {
            "$schema": SCHEMA_PLATFORM,
            "metadata": {"type": "SemanticModel", "displayName": PROJECT},
            "config": {"version": "2.0", "logicalId": lid("platform", "semantic-model")},
        },
    )
    write_text(sm / "definition" / "database.tmdl", database_tmdl())
    write_text(sm / "definition" / "model.tmdl", model_tmdl())
    write_text(sm / "definition" / "expressions.tmdl", expressions_tmdl())
    write_text(sm / "definition" / "relationships.tmdl", relationships_tmdl())
    tables = {
        "DIM_POLICY": (
            "Policy dimension. Grain is one row per policy. BOOK_PERIOD_LABEL is a reporting convention, not a start or loss date.",
            DIM_POLICY_COLS,
        ),
        "DIM_VEHICLE": (
            "Vehicle dimension. Grain is one vehicle per policy in this book.",
            DIM_VEHICLE_COLS,
        ),
        "DIM_DRIVER": (
            "Driver dimension. Grain is one recorded driver per policy.",
            DIM_DRIVER_COLS,
        ),
        "FCT_POLICY_EXPOSURE": (
            "Policy exposure fact. Grain is one row per policy. Use this table for exposure, claim counts, frequency, and pure premium.",
            FCT_EXPOSURE_COLS,
        ),
        "FCT_CLAIMS": (
            "Claims fact. Grain is one row per severity record. Orphan claims have a null POLICY_SK and stay in the table. Official severity and pure premium exclude them.",
            FCT_CLAIMS_COLS,
        ),
        "MART_RISK_SEGMENTS": (
            "Disconnected reference table of pre-aggregated risk segments. Do not mix its columns with official star schema measures in the same visual.",
            MART_SEGMENTS_COLS,
        ),
    }
    for name, (desc, cols) in tables.items():
        write_text(sm / "definition" / "tables" / f"{name}.tmdl", table_file(name, desc, cols))
    write_text(sm / "definition" / "tables" / "_Measures.tmdl", measures_table())


def write_visuals(page_dir: Path, items: list[tuple[str, dict]]) -> None:
    names = set()
    for name, payload in items:
        if name in names:
            raise ValueError(f"duplicate visual name {name}")
        if not re.fullmatch(r"[0-9a-f]{20}", name):
            raise ValueError(f"visual name is not 20 lowercase hex: {name}")
        names.add(name)
        if payload["name"] != name:
            raise ValueError(f"name mismatch {name}")
        write_json(page_dir / "visuals" / name / "visual.json", payload)


def emit_report(rpt: Path, theme_src: Path) -> None:
    write_json(
        rpt / "definition.pbir",
        {
            "$schema": SCHEMA_PBIR,
            "version": "4.0",
            "datasetReference": {"byPath": {"path": f"../{PROJECT}.SemanticModel"}},
        },
    )
    write_json(
        rpt / ".platform",
        {
            "$schema": SCHEMA_PLATFORM,
            "metadata": {"type": "Report", "displayName": PROJECT},
            "config": {"version": "2.0", "logicalId": lid("platform", "report")},
        },
    )
    write_json(rpt / "definition" / "version.json", {"$schema": SCHEMA_VERSION, "version": "2.0.0"})
    write_json(
        rpt / "definition" / "report.json",
        {
            "$schema": SCHEMA_REPORT,
            "themeCollection": {
                "baseTheme": {
                    "name": "CY26SU02",
                    "reportVersionAtImport": {"visual": "2.6.0", "report": "3.1.0", "page": "2.3.0"},
                    "type": "SharedResources",
                }
            },
            "objects": {
                "section": [{"properties": {"verticalAlignment": literal("'Top'")}}],
                "outspacePane": [{"properties": {"expanded": literal("false")}}],
            },
            "resourcePackages": [
                {
                    "name": "SharedResources",
                    "type": "SharedResources",
                    "items": [
                        {"name": "CY26SU02", "path": "BaseThemes/CY26SU02.json", "type": "BaseTheme"}
                    ],
                }
            ],
            "settings": {
                "useStylableVisualContainerHeader": True,
                "exportDataMode": "AllowSummarized",
                "defaultDrillFilterOtherVisuals": True,
                "allowChangeFilterTypes": True,
                "allowInlineExploration": True,
                "useEnhancedTooltips": True,
                "useDefaultAggregateDisplayName": True,
            },
        },
    )
    theme_dest = rpt / "StaticResources" / "SharedResources" / "BaseThemes" / "CY26SU02.json"
    theme_dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(theme_src, theme_dest)
    # Ensure theme is valid JSON and UTF-8 no BOM
    theme = json.loads(theme_dest.read_text(encoding="utf-8"))
    write_json(theme_dest, theme)

    pages = [
        (PAGE_OVERVIEW, "Portfolio Overview", build_overview()),
        (PAGE_RISK, "Risk Drivers", build_risk()),
        (PAGE_QUALITY, "Data Quality", build_quality()),
    ]
    page_names = []
    for page_id, display, visuals in pages:
        if not re.fullmatch(r"[0-9a-f]{20}", page_id):
            raise ValueError(f"page name is not 20 lowercase hex: {page_id}")
        page_names.append(page_id)
        page_dir = rpt / "definition" / "pages" / page_id
        write_json(page_dir / "page.json", page_json(page_id, display))
        write_visuals(page_dir, visuals)
    write_json(
        rpt / "definition" / "pages" / "pages.json",
        {
            "$schema": SCHEMA_PAGES,
            "pageOrder": page_names,
            "activePageName": page_names[0],
        },
    )


def emit_pbip(out: Path) -> None:
    write_json(
        out / f"{PROJECT}.pbip",
        {
            "$schema": SCHEMA_PBIP,
            "version": "1.0",
            "artifacts": [{"report": {"path": f"{PROJECT}.Report"}}],
            "settings": {"enableAutoRecovery": True},
        },
    )


# ---------------------------------------------------------------------------
# Docs
# ---------------------------------------------------------------------------

EXPECTED_MD = """# Power BI expected numbers checklist

Use this list after you open `InsurancePortfolio.pbip`, enter your Snowflake credentials, and refresh. The values were computed from `INSURANCE_PORTFOLIO.MARTS` with the `INSURANCE_PBI_READONLY` role. They match the full book totals in `docs/data_profile.md` and `docs/power_bi_design.md`.

Format the cards the same way the measures are formatted. Small rounding differences on the last decimal are not a fail if the unrounded value matches.

## Official portfolio measures (page 1)

These come from `FCT_POLICY_EXPOSURE`. Orphan claims are not in this fact, so they do not move these cards.

| Measure | Expected value | How to read it |
| --- | --- | --- |
| Policy Count | 678,013 | One row per policy |
| Exposure | 358,499.45 | Sum of exposure years |
| Claim Count | 36,102 | Sum of ClaimNb, not severity row count |
| Claim Frequency | 0.100703 | Claim Count / Exposure. This is claims per year, not a percentage |
| Matched Claim Amount | 59,909,216.50 | Matched amounts only |
| Matched Severity Rows | 26,444 | Severity rows that match a policy |
| Average Severity | 2,265.51 | Matched Claim Amount / Matched Severity Rows |
| Pure Premium | 167.11 | Matched Claim Amount / Exposure |
| Policies With Claims | 34,060 | Policies with Claim Count greater than 0 |
| Policies With Claims % | 5.02% | 34,060 / 678,013 |

There is no Loss Ratio measure. The source has no premium.

## Reconciliation between the two facts (page 3)

| Measure | Expected value | Note |
| --- | --- | --- |
| Matched Claim Amount | 59,909,216.50 | From the exposure fact |
| Matched Claim Amount From Claims | 59,909,216.50 | From `FCT_CLAIMS` where `IS_ORPHAN_CLAIM` is false. Must tie to the row above |
| Average Severity From Claims | 2,265.51 | Must tie to official Average Severity |
| Claim Amount All Rows | 60,697,930.68 | Matched plus orphan amounts |

## Data quality measures (page 3)

| Measure | Expected value | Note |
| --- | --- | --- |
| Policies With Missing Severity | 9,116 | Claim Count greater than 0 and no severity row |
| Missing Severity Claim Units | 9,658 | Includes 9,657 zero-severity claim units plus 1 unit from the count mismatch policy |
| Policies With Count Mismatch | 1 | IDpol 4,158,255 has Claim Count 2 and one severity row |
| Orphan Claim Rows | 195 | Severity rows with no matching policy |
| Orphan Claim IDs | 6 | Distinct policy IDs that appear only in the severity file |
| Orphan Claim Amount | 788,714.18 | Excluded from official Average Severity and Pure Premium |
| Duplicate Amount Rows | 496 | Rows flagged `IS_DUPLICATE_AMOUNT_ROW` |
| Exposure Over One Year | 1,224 | Maximum exposure is 2.01 years |
| Extreme Claim Count Policies | 16 | ClaimNb of 4 or more |

## Other useful checks

- `DIM_POLICY`, `DIM_VEHICLE`, `DIM_DRIVER`, and `FCT_POLICY_EXPOSURE` each have 678,013 rows.
- `FCT_CLAIMS` has 26,639 rows (26,444 matched + 195 orphan).
- `MART_RISK_SEGMENTS` has 49 rows and is disconnected on purpose. Do not drop its columns onto visuals that already use the official measures.
- `SEEDS.REGION_NAMES` is not in the model. `REGION_NAME` is already on `DIM_POLICY`.
- Book period label: freMTPL2 observation book (approximately 2011 to 2013).

## Risk driver context (page 2)

These are not card totals. They are useful when you read the charts after refresh.

- Drivers aged 18 to 25 have the highest frequency (0.175069) and the highest average severity (5,121.62).
- Frequency rises from rural Area A (0.081702) to urban Area F (0.139127).
- New vehicles (vehicle age 0) have a very high Claim Count frequency (0.311322), but only 1,181 matched severity rows against 5,205 claim counts. Use the table at the bottom of page 2 to see that gap.
"""

SPANISH_GUIDE = """# Cómo abrir el reporte de Power BI

Esta guía es para abrir el proyecto de Power BI en tu computador, actualizarlo contra Snowflake y tomar las capturas de cada página. El archivo no incluye usuario ni contraseña. Esas credenciales las pides Power BI Desktop en el primer refresh.

El proyecto está en formato PBIP: un archivo `.pbip`, una carpeta `InsurancePortfolio.SemanticModel` (modelo en TMDL) y una carpeta `InsurancePortfolio.Report` (reporte en PBIR).

## 1. Descargar y descomprimir

1. Entra al repositorio privado y descarga el zip `powerbi/InsurancePortfolio-PBIP.zip`, o clona el repositorio y entra a la carpeta `powerbi`.
2. Si descargaste el zip, descomprímelo en una carpeta local, por ejemplo `Documentos\\InsurancePortfolio`.
3. Debes ver estos elementos al mismo nivel:
   - `InsurancePortfolio.pbip`
   - `InsurancePortfolio.SemanticModel`
   - `InsurancePortfolio.Report`
   - `EXPECTED_NUMBERS.md` (lista de totales esperados)
   - `LEEME.md` (esta guía, si viene dentro del zip)

No abras un `.pbix`. Este proyecto se abre con el archivo `.pbip`.

## 2. Abrir el proyecto en Power BI Desktop

1. Abre Power BI Desktop en Windows.
2. Si tu versión es anterior a la que ya trae PBIP y PBIR activados por defecto, ve a **Archivo > Opciones y configuración > Opciones > Características de vista previa** y activa el almacenamiento de informes en formato PBIR (o Power BI Project / PBIP, según el nombre que muestre tu versión). Cierra y vuelve a abrir Desktop.
3. En el Explorador de archivos, haz doble clic en `InsurancePortfolio.pbip`, o en Desktop usa **Archivo > Abrir** y elige ese archivo.
4. Espera a que cargue el modelo y las tres páginas: **Portfolio Overview**, **Risk Drivers** y **Data Quality**.

Si Desktop pide actualizar un formato o aplicar un cambio de esquema, acepta y guarda una copia en la misma carpeta.

## 3. Credenciales de Snowflake y actualización

La conexión ya está definida, sin contraseña, con estos valores:

- Servidor: `wngvror-ly04177.snowflakecomputing.com`
- Warehouse: `COMPUTE_WH`
- Base de datos: `INSURANCE_PORTFOLIO`
- Esquema: `MARTS`
- Rol: `INSURANCE_PBI_READONLY`
- Modo: Import

Pasos:

1. En la cinta, pulsa **Actualizar** (Refresh).
2. Cuando Desktop pida credenciales de Snowflake, elige autenticación con usuario y contraseña.
3. Escribe tu usuario y tu contraseña de Snowflake. No cambies el servidor ni el warehouse si aparecen prellenados.
4. Si te pregunta el rol, usa `INSURANCE_PBI_READONLY`.
5. Confirma y espera a que termine la importación. Hay unas 678,013 pólizas en varias tablas. En un warehouse X-Small puede tardar unos minutos.

Las credenciales quedan guardadas en tu computador, no en los archivos del proyecto. No copies `localSettings.json` ni `cache.abf` de la carpeta `.pbi` al repositorio.

## 4. Revisar los números y tomar capturas

1. Abre `EXPECTED_NUMBERS.md` o `docs/powerbi_expected_numbers.md` en el repositorio.
2. En la página **Portfolio Overview**, comprueba los KPI: 678,013 pólizas, 358,499.45 de exposición, 36,102 siniestros, frecuencia 0.100703, severidad media 2,265.51, prima pura 167.11, 5.02% de pólizas con siniestro y 59,909,216.50 de importe emparejado.
3. En **Risk Drivers**, revisa las barras por edad del conductor, edad del vehículo, potencia, área, región y bonus-malus. En la tabla inferior, las pólizas de vehículo nuevo (edad 0) deben mostrar un hueco grande entre Claim Count y Matched Severity Rows.
4. En **Data Quality**, comprueba los controles de calidad de la lista (9,116 pólizas sin severidad, 195 filas huérfanas, 496 duplicados, 1,224 exposiciones mayores a 1, y que los dos importes emparejados coincidan en 59,909,216.50).
5. Toma una captura de pantalla de cada una de las tres páginas, a página completa, con los filtros en el nivel del libro (sin filtros extra).

## Si algo falla al abrir el reporte

El modelo semántico (tablas, relaciones y medidas DAX) está en TMDL y sigue el esquema documentado. El reporte está en PBIR, que es el formato actual, pero un archivo generado fuera de Windows puede ser más frágil que uno guardado por Desktop.

- Si el `.pbip` no abre, actualiza Power BI Desktop e activa la característica de vista previa de PBIP o PBIR. Luego vuelve a abrir el archivo.
- Si el modelo carga y las medidas aparecen en el panel de datos, pero alguna visual no se dibuja, no borres el modelo. Recrea esa visual a mano con las mismas medidas. La guía de diseño está en `docs/power_bi_design.md`.
- Si el refresh falla por permisos, confirma que tu usuario tiene el rol `INSURANCE_PBI_READONLY` y que ese rol puede leer `INSURANCE_PORTFOLIO.MARTS`. El rol no debe leer `RAW`.
- Si el refresh pide un servidor distinto, no lo cambies. El parámetro `SnowflakeServer` ya apunta a `wngvror-ly04177.snowflakecomputing.com`.
- No hay tabla de fechas a propósito. El origen no trae fechas de póliza ni de siniestro, y no se inventaron.
- `MART_RISK_SEGMENTS` está desconectada a propósito. No la uses en los mismos visuales que las medidas oficiales.

Después del primer refresh exitoso, puedes guardar el proyecto. Si Desktop genera un `.pbix` de respaldo, no es necesario subirlo al repositorio.
"""

README_POWERBI = """# Insurance Portfolio Power BI project

This folder is a Power BI Project (PBIP) for Power BI Desktop. Open `InsurancePortfolio.pbip`, enter your Snowflake username and password when Desktop prompts you, then refresh. There are no credentials in these files.

The semantic model is TMDL. The report is PBIR, with three pages: Portfolio Overview, Risk Drivers, and Data Quality. The source is the Snowflake connector in import mode, using warehouse `COMPUTE_WH`, database `INSURANCE_PORTFOLIO`, schema `MARTS`, and role `INSURANCE_PBI_READONLY`.

Spanish step by step instructions are in `docs/powerbi_abrir_es.md`. The expected totals after refresh are in `docs/powerbi_expected_numbers.md` and in `EXPECTED_NUMBERS.md` inside the zip.

`MART_RISK_SEGMENTS` is imported as a disconnected reference table. `SEEDS.REGION_NAMES` is not imported, because `REGION_NAME` is already on `DIM_POLICY`. There is no date table and no Loss Ratio measure.
"""

FALLBACK_MD = """# Fallback if the report layer does not open cleanly

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
"""


def emit_docs() -> None:
    write_text(OUT / "README.md", README_POWERBI)
    write_text(OUT / "EXPECTED_NUMBERS.md", EXPECTED_MD)
    write_text(OUT / "FALLBACK.md", FALLBACK_MD)
    write_text(OUT / "LEEME.md", SPANISH_GUIDE)
    write_text(ROOT / "docs" / "powerbi_expected_numbers.md", EXPECTED_MD)
    write_text(ROOT / "docs" / "powerbi_abrir_es.md", SPANISH_GUIDE)


def make_zip(out: Path) -> Path:
    zip_path = out / "InsurancePortfolio-PBIP.zip"
    if zip_path.exists():
        zip_path.unlink()
    include_roots = [
        out / f"{PROJECT}.pbip",
        out / f"{PROJECT}.Report",
        out / f"{PROJECT}.SemanticModel",
        out / "EXPECTED_NUMBERS.md",
        out / "LEEME.md",
        out / "FALLBACK.md",
        out / "README.md",
    ]
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for root in include_roots:
            if root.is_file():
                zf.write(root, arcname=f"{PROJECT}/{root.name}")
            else:
                for file in sorted(root.rglob("*")):
                    if not file.is_file():
                        continue
                    if ".pbi" in file.parts:
                        continue
                    rel = file.relative_to(out)
                    zf.write(file, arcname=f"{PROJECT}/{rel.as_posix()}")
    return zip_path


def find_theme() -> Path:
    for cand in THEME_CANDIDATES:
        if cand.exists() and cand.stat().st_size > 1000:
            json.loads(cand.read_text(encoding="utf-8"))
            return cand
    dest = Path("/tmp/CY26SU02.json")
    import urllib.request

    urllib.request.urlretrieve(THEME_URL, dest)
    json.loads(dest.read_text(encoding="utf-8"))
    return dest


def validate_tree(out: Path) -> list[str]:
    problems: list[str] = []
    json_files = list(out.rglob("*.json")) + list(out.glob("*.pbip")) + list((out / f"{PROJECT}.Report").rglob("*.pbir")) + list((out / f"{PROJECT}.SemanticModel").rglob("*.pbism"))
    json_files += list((out / f"{PROJECT}.Report").glob(".platform"))
    json_files += list((out / f"{PROJECT}.SemanticModel").glob(".platform"))
    for f in json_files:
        if ".pbi" in f.parts:
            continue
        try:
            text = f.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            problems.append(f"encoding {f}: {exc}")
            continue
        if text.startswith("\ufeff"):
            problems.append(f"BOM in {f}")
        try:
            json.loads(text)
        except json.JSONDecodeError as exc:
            problems.append(f"json {f}: {exc}")
    # Visual and page names
    pages_root = out / f"{PROJECT}.Report" / "definition" / "pages"
    for page_dir in pages_root.iterdir():
        if not page_dir.is_dir():
            continue
        if not re.fullmatch(r"[0-9a-f]{20}", page_dir.name):
            problems.append(f"page folder name {page_dir.name}")
        visuals = page_dir / "visuals"
        if visuals.exists():
            for vdir in visuals.iterdir():
                if not re.fullmatch(r"[0-9a-f]{20}", vdir.name):
                    problems.append(f"visual folder name {vdir.name}")
                vjson = json.loads((vdir / "visual.json").read_text(encoding="utf-8"))
                if vjson.get("name") != vdir.name:
                    problems.append(f"visual name mismatch {vdir}")
    # TMDL: tabs, balanced backticks, first token
    for tmdl in (out / f"{PROJECT}.SemanticModel").rglob("*.tmdl"):
        text = tmdl.read_text(encoding="utf-8")
        if "\ufeff" in text[:1]:
            problems.append(f"BOM in {tmdl}")
        if text.count("```") % 2 != 0:
            problems.append(f"unbalanced backticks in {tmdl}")
        for i, line in enumerate(text.splitlines(), 1):
            if line.startswith(" ") and not line.strip().startswith(("let", "in", "Source", "#", "ROW", "SWITCH", "CALCULATE", "DIVIDE", "COUNTROWS", "SUM", "DISTINCTCOUNT")):
                # TMDL object lines must use tabs. M/DAX bodies may use spaces after tabs.
                if re.match(r"^ +[a-zA-Z]", line) and "\t" not in line[:8]:
                    problems.append(f"space indent at {tmdl}:{i}: {line[:40]!r}")
        if any(s in text.lower() for s in ["password", "pwd=", "accountidentifier"]):
            # server URL is fine; password must not appear
            if re.search(r"password\s*=", text, re.I):
                problems.append(f"possible secret in {tmdl}")
    # Unique lineage tags
    tags = []
    for tmdl in (out / f"{PROJECT}.SemanticModel").rglob("*.tmdl"):
        for i, line in enumerate(tmdl.read_text(encoding="utf-8").splitlines(), 1):
            mm = re.search(r"lineageTag:\s*([0-9a-fA-F-]+)", line)
            if mm:
                tags.append((mm.group(1).lower(), f"{tmdl}:{i}"))
    seen = {}
    for tag, loc in tags:
        if tag in seen:
            problems.append(f"duplicate lineageTag {tag} at {loc} and {seen[tag]}")
        else:
            seen[tag] = loc

    # No secrets in any generated text
    skip_names = {"CY26SU02.json"}
    for f in out.rglob("*"):
        if not f.is_file():
            continue
        if f.suffix.lower() in {".zip", ".png", ".abf"} or f.name in skip_names:
            continue
        try:
            blob = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if re.search(r"SNOWFLAKE_PASSWORD|PASSWORD\s*=\s*['\"]", blob):
            problems.append(f"password assignment in {f}")
    return problems


def schema_validate(out: Path) -> list[str]:
    problems: list[str] = []
    try:
        import jsonschema
    except ImportError:
        return problems
    schema_map = {
        out / f"{PROJECT}.pbip": Path("/tmp/pbi-schemas/pbipProperties.json"),
        out / f"{PROJECT}.SemanticModel" / "definition.pbism": Path("/tmp/pbi-schemas/fabric_item_semanticModel_definitionProperties_1.0.0_schema.json")
        if Path("/tmp/pbi-schemas/fabric_item_semanticModel_definitionProperties_1.0.0_schema.json").exists()
        else Path("/tmp/pbi-schemas/definitionProperties_sm.json"),
        out / f"{PROJECT}.Report" / "definition.pbir": Path("/tmp/pbi-schemas/definitionProperties_report.json"),
        out / f"{PROJECT}.Report" / "definition" / "version.json": Path("/tmp/pbi-schemas/fabric_item_report_definition_versionMetadata_1.0.0_schema.json"),
        out / f"{PROJECT}.Report" / "definition" / "pages" / "pages.json": Path("/tmp/pbi-schemas/fabric_item_report_definition_pagesMetadata_1.0.0_schema.json"),
    }
    # These local schemas often $ref other files; validate when possible
    for path, schema_path in schema_map.items():
        if not path.exists() or not schema_path.exists():
            continue
        try:
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            instance = json.loads(path.read_text(encoding="utf-8"))
            jsonschema.validate(instance=instance, schema=schema)
        except Exception as exc:
            # Remote $ref failures are not fatal; record them.
            msg = str(exc).splitlines()[0][:200]
            problems.append(f"schema {path.name}: {type(exc).__name__}: {msg}")

    # Local required-field checks for visuals and pages (no remote $ref)
    report_schema = Path("/tmp/pbi-schemas/fabric_item_report_definition_report_3.2.0_schema.json")
    page_schema = Path("/tmp/pbi-schemas/fabric_item_report_definition_page_2.1.0_schema.json")
    visual_schema = Path("/tmp/pbi-schemas/fabric_item_report_definition_visualContainer_2.7.0_schema.json")
    for path, schema_path, required_only in [
        (out / f"{PROJECT}.Report" / "definition" / "report.json", report_schema, True),
    ]:
        if path.exists() and schema_path.exists():
            instance = json.loads(path.read_text(encoding="utf-8"))
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            missing = [k for k in schema.get("required", []) if k not in instance]
            if missing:
                problems.append(f"required fields missing in {path.name}: {missing}")
    if page_schema.exists():
        schema = json.loads(page_schema.read_text(encoding="utf-8"))
        for page in (out / f"{PROJECT}.Report" / "definition" / "pages").glob("*/page.json"):
            instance = json.loads(page.read_text(encoding="utf-8"))
            missing = [k for k in schema.get("required", []) if k not in instance]
            if missing:
                problems.append(f"required fields missing in {page}: {missing}")
    if visual_schema.exists():
        schema = json.loads(visual_schema.read_text(encoding="utf-8"))
        for visual in (out / f"{PROJECT}.Report").rglob("visual.json"):
            instance = json.loads(visual.read_text(encoding="utf-8"))
            missing = [k for k in schema.get("required", []) if k not in instance]
            if missing:
                problems.append(f"required fields missing in {visual}: {missing}")
    return problems


def main() -> None:
    theme = find_theme()
    if OUT.exists():
        # Remove previous generated project folders only, keep nothing stale
        for name in (f"{PROJECT}.pbip", f"{PROJECT}.Report", f"{PROJECT}.SemanticModel", "InsurancePortfolio-PBIP.zip", "README.md", "EXPECTED_NUMBERS.md", "FALLBACK.md", "LEEME.md"):
            p = OUT / name
            if p.is_dir():
                shutil.rmtree(p)
            elif p.exists():
                p.unlink()
    OUT.mkdir(parents=True, exist_ok=True)
    emit_pbip(OUT)
    emit_semantic_model(OUT / f"{PROJECT}.SemanticModel")
    emit_report(OUT / f"{PROJECT}.Report", theme)
    emit_docs()
    problems = validate_tree(OUT)
    schema_probs = schema_validate(OUT)
    zip_path = make_zip(OUT)
    print(f"theme={theme} size={theme.stat().st_size}")
    print(f"zip={zip_path} size={zip_path.stat().st_size}")
    print(f"page_overview={PAGE_OVERVIEW}")
    print(f"page_risk={PAGE_RISK}")
    print(f"page_quality={PAGE_QUALITY}")
    if problems:
        print("VALIDATION_PROBLEMS")
        for p in problems:
            print(" -", p)
    else:
        print("VALIDATION_OK")
    if schema_probs:
        print("SCHEMA_NOTES")
        for p in schema_probs:
            print(" -", p)
    else:
        print("SCHEMA_OK")


if __name__ == "__main__":
    main()
