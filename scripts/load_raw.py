#!/usr/bin/env python3
"""Build RAW.POLICIES, RAW.VEHICLES, RAW.DRIVERS, and RAW.CLAIMS.

Reads the local freMTPL2 parquet files and writes the Guidewire style raw
layer designed in docs/data_profile.md.

Derivations allowed here:
  * integer types for IDpol and Density (every value is integer valued)
  * deterministic surrogate keys (MD5 of a documented natural key)
  * claim_sequence, 1..n within policy_id in source file order
  * pipeline metadata: src_system, src_file_name, src_row_number, loaded_at

This script does not invent business dates, premium, VIN, or driver names.
It does not drop orphans, missing severity policies, or outliers.

Targets:
  * duckdb (default): data/warehouse/insurance.duckdb, schema raw
  * snowflake: uses write_pandas after applying sql/snowflake DDL

Snowflake is selected with --target snowflake or WAREHOUSE_TARGET=snowflake.
Required environment variables for Snowflake:
  SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER, SNOWFLAKE_PASSWORD,
  SNOWFLAKE_DATABASE, SNOWFLAKE_WAREHOUSE, SNOWFLAKE_SCHEMA

SNOWFLAKE_SCHEMA is the dbt target schema. Raw tables are written to
SNOWFLAKE_RAW_SCHEMA, which defaults to RAW.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
from snowflake_env import load_snowflake_env

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
DEFAULT_DUCKDB = ROOT / "data" / "warehouse" / "insurance.duckdb"
SNOWFLAKE_DDL = [
    ROOT / "sql" / "snowflake" / "01_create_schemas.sql",
    ROOT / "sql" / "snowflake" / "02_create_raw_tables.sql",
]

FREQ_FILE = "freMTPL2freq.parquet"
SEV_FILE = "freMTPL2sev.parquet"
SRC_FREQ = "FREMTPL2_FREQ"
SRC_SEV = "FREMTPL2_SEV"

SNOWFLAKE_ENV = [
    "SNOWFLAKE_ACCOUNT",
    "SNOWFLAKE_USER",
    "SNOWFLAKE_PASSWORD",
    "SNOWFLAKE_DATABASE",
    "SNOWFLAKE_WAREHOUSE",
    "SNOWFLAKE_SCHEMA",
]


def md5_key(*parts: object) -> str:
    payload = "|".join(str(p) for p in parts)
    return hashlib.md5(payload.encode("utf-8")).hexdigest()


def load_source_frames(data_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    freq_path = data_dir / FREQ_FILE
    sev_path = data_dir / SEV_FILE
    if not freq_path.exists() or not sev_path.exists():
        raise FileNotFoundError(
            f"Missing parquet in {data_dir}. "
            "Download the full files with scripts/download_raw.py "
            "or pass --data-dir data/sample."
        )
    freq = pd.read_parquet(freq_path)
    sev = pd.read_parquet(sev_path)
    return freq, sev


def build_raw_tables(loaded_at: datetime, data_dir: Path) -> dict[str, pd.DataFrame]:
    freq, sev = load_source_frames(data_dir)

    freq = freq.copy()
    freq["src_row_number"] = range(1, len(freq) + 1)
    freq["policy_id"] = freq["IDpol"].astype("int64")
    freq["policy_sk"] = freq["policy_id"].map(lambda x: md5_key("policy", int(x)))
    freq["claim_count"] = freq["ClaimNb"].astype("int64")
    freq["exposure_years"] = freq["Exposure"].astype("float64")
    freq["area"] = freq["Area"].astype(str)
    freq["bonus_malus"] = freq["BonusMalus"].astype("int64")
    freq["density"] = freq["Density"].astype("int64")
    freq["region"] = freq["Region"].astype(str)

    policies = pd.DataFrame(
        {
            "policy_sk": freq["policy_sk"],
            "policy_id": freq["policy_id"],
            "claim_count": freq["claim_count"],
            "exposure_years": freq["exposure_years"],
            "area": freq["area"],
            "bonus_malus": freq["bonus_malus"],
            "density": freq["density"],
            "region": freq["region"],
            "src_system": SRC_FREQ,
            "src_file_name": FREQ_FILE,
            "src_row_number": freq["src_row_number"].astype("int64"),
            "loaded_at": loaded_at,
        }
    )

    vehicles = pd.DataFrame(
        {
            "vehicle_sk": freq["policy_id"].map(lambda x: md5_key("vehicle", int(x))),
            "policy_sk": freq["policy_sk"],
            "policy_id": freq["policy_id"],
            "veh_power": freq["VehPower"].astype("int64"),
            "veh_age": freq["VehAge"].astype("int64"),
            "veh_brand": freq["VehBrand"].astype(str),
            "veh_gas": freq["VehGas"].astype(str),
            "src_system": SRC_FREQ,
            "src_file_name": FREQ_FILE,
            "src_row_number": freq["src_row_number"].astype("int64"),
            "loaded_at": loaded_at,
        }
    )

    drivers = pd.DataFrame(
        {
            "driver_sk": freq["policy_id"].map(lambda x: md5_key("driver", int(x))),
            "policy_sk": freq["policy_sk"],
            "policy_id": freq["policy_id"],
            "driv_age": freq["DrivAge"].astype("int64"),
            "src_system": SRC_FREQ,
            "src_file_name": FREQ_FILE,
            "src_row_number": freq["src_row_number"].astype("int64"),
            "loaded_at": loaded_at,
        }
    )

    policy_keys = freq[["policy_id", "policy_sk"]].drop_duplicates()

    sev = sev.copy()
    sev["src_row_number"] = range(1, len(sev) + 1)
    sev["policy_id"] = sev["IDpol"].astype("int64")
    sev["claim_amount"] = sev["ClaimAmount"].astype("float64")
    # Source file order is preserved by the existing row index.
    sev["claim_sequence"] = sev.groupby("policy_id", sort=False).cumcount() + 1
    sev = sev.merge(policy_keys, on="policy_id", how="left")
    sev["claim_sk"] = [
        md5_key("claim", int(pid), int(rownum))
        for pid, rownum in zip(sev["policy_id"], sev["src_row_number"])
    ]

    claims = pd.DataFrame(
        {
            "claim_sk": sev["claim_sk"],
            "claim_sequence": sev["claim_sequence"].astype("int64"),
            "policy_id": sev["policy_id"],
            "policy_sk": sev["policy_sk"],
            "claim_amount": sev["claim_amount"].round(2),
            "src_system": SRC_SEV,
            "src_file_name": SEV_FILE,
            "src_row_number": sev["src_row_number"].astype("int64"),
            "loaded_at": loaded_at,
        }
    )

    return {
        "policies": policies,
        "vehicles": vehicles,
        "drivers": drivers,
        "claims": claims,
    }


def _run(con, sql: str):
    # DuckDB 2 leaves a result open after fetchone(). Use fetchall() and do
    # not call close() on the object returned by execute(), because that
    # object is the connection itself.
    return con.execute(sql).fetchall()


def write_duckdb(tables: dict[str, pd.DataFrame], path: Path) -> None:
    import duckdb

    path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(path))
    try:
        _run(con, "create schema if not exists raw")
        for name, df in tables.items():
            view_name = f"_load_{name}"
            con.register(view_name, df)
            _run(con, f"create or replace table raw.{name} as select * from {view_name}")
            con.unregister(view_name)
            count = _run(con, f"select count(*) from raw.{name}")[0][0]
            print(f"duckdb raw.{name}: {count:,} rows")
    finally:
        con.close()


def _split_sql_statements(sql_text: str) -> list[str]:
    statements = []
    for part in sql_text.split(";"):
        lines = [
            line
            for line in part.splitlines()
            if line.strip() and not line.strip().startswith("--")
        ]
        cleaned = "\n".join(lines).strip()
        if cleaned:
            statements.append(cleaned)
    return statements


def write_snowflake(tables: dict[str, pd.DataFrame]) -> None:
    missing = [key for key in SNOWFLAKE_ENV if not os.environ.get(key)]
    if missing:
        raise SystemExit(
            "Snowflake target requested but these environment variables are "
            f"missing: {', '.join(missing)}. Leave the target as duckdb until "
            "the account is available."
        )
    try:
        import snowflake.connector
        from snowflake.connector.pandas_tools import write_pandas
    except ImportError as exc:
        raise SystemExit(
            "snowflake-connector-python is not installed. "
            "Install requirements-snowflake.txt and retry."
        ) from exc

    database = os.environ["SNOWFLAKE_DATABASE"]
    warehouse = os.environ["SNOWFLAKE_WAREHOUSE"]
    raw_schema = os.environ.get("SNOWFLAKE_RAW_SCHEMA", "RAW")
    connect_kwargs = {
        "account": os.environ["SNOWFLAKE_ACCOUNT"],
        "user": os.environ["SNOWFLAKE_USER"],
        "password": os.environ["SNOWFLAKE_PASSWORD"],
        "database": database,
        "warehouse": warehouse,
        "schema": os.environ["SNOWFLAKE_SCHEMA"],
    }
    if os.environ.get("SNOWFLAKE_ROLE"):
        connect_kwargs["role"] = os.environ["SNOWFLAKE_ROLE"]

    conn = snowflake.connector.connect(**connect_kwargs)
    try:
        cur = conn.cursor()
        cur.execute(f"use database {database}")
        cur.execute(f"use warehouse {warehouse}")
        for ddl_path in SNOWFLAKE_DDL:
            for statement in _split_sql_statements(ddl_path.read_text(encoding="utf-8")):
                cur.execute(statement)
        for name, df in tables.items():
            # Unquoted Snowflake identifiers fold to uppercase and match the DDL.
            upload = df.copy()
            upload.columns = [col.upper() for col in upload.columns]
            cur.execute(f"truncate table {raw_schema}.{name}")
            success, _, nrows, _ = write_pandas(
                conn,
                upload,
                table_name=name.upper(),
                database=database,
                schema=raw_schema,
                quote_identifiers=False,
                auto_create_table=False,
            )
            if not success:
                raise RuntimeError(f"write_pandas failed for {raw_schema}.{name}")
            print(f"snowflake {raw_schema}.{name}: {nrows:,} rows")
        cur.close()
    finally:
        conn.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Load freMTPL2 files into raw tables.")
    parser.add_argument(
        "--target",
        choices=["duckdb", "snowflake"],
        default=os.environ.get("WAREHOUSE_TARGET", "duckdb"),
        help="Warehouse target. Defaults to WAREHOUSE_TARGET or duckdb.",
    )
    parser.add_argument(
        "--duckdb-path",
        default=os.environ.get("DUCKDB_PATH", str(DEFAULT_DUCKDB)),
        help="DuckDB file path when --target duckdb is used.",
    )
    parser.add_argument(
        "--data-dir",
        default=os.environ.get("DATA_DIR", str(RAW_DIR)),
        help="Directory with freMTPL2freq.parquet and freMTPL2sev.parquet. "
        "Use data/sample for the committed sample, or data/raw for the full book.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.target == "snowflake":
        load_snowflake_env()
    data_dir = Path(args.data_dir)
    loaded_at = datetime.now(timezone.utc).replace(tzinfo=None)
    tables = build_raw_tables(loaded_at, data_dir)
    print(f"reading source files from {data_dir}")
    print(f"built raw frames at loaded_at={loaded_at.isoformat()} UTC")
    for name, df in tables.items():
        print(f"  {name}: {len(df):,} rows")
    if args.target == "duckdb":
        write_duckdb(tables, Path(args.duckdb_path))
    elif args.target == "snowflake":
        write_snowflake(tables)
    else:
        raise SystemExit(f"Unsupported target: {args.target}")


if __name__ == "__main__":
    main()
