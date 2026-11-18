#!/usr/bin/env python3
"""Download the full freMTPL2 parquet files from OpenML into data/raw.

The committed GitHub sample lives in data/sample. Use this script when you
want the complete book for a local or Snowflake run.

Frequency: OpenML dataset 41214
Severity:  OpenML dataset 41215
"""

from __future__ import annotations

import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"

FREQ_URL = "https://data.openml.org/datasets/0004/41214/dataset_41214.pq"
SEV_URL = "https://data.openml.org/datasets/0004/41215/dataset_41215.pq"

FILES = {
    "freMTPL2freq.parquet": FREQ_URL,
    "freMTPL2sev.parquet": SEV_URL,
}


def download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"downloading {url}")
    with urllib.request.urlopen(url) as response, dest.open("wb") as out:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            out.write(chunk)
    print(f"wrote {dest} ({dest.stat().st_size:,} bytes)")


def main() -> None:
    for name, url in FILES.items():
        download(url, RAW_DIR / name)
    print("done. next: python scripts/load_raw.py --target duckdb --data-dir data/raw")


if __name__ == "__main__":
    main()
