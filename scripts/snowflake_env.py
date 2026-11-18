"""Load Snowflake settings from the box secrets file.

Values may be wrapped in single or double quotes so that a shell source
does not expand dollar signs. Quotes are stripped and the value is stored
literally. This module never prints secret values.
"""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_SECRET_FILE = Path("/home/box/.secrets/snowflake.env")


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def load_snowflake_env(path: Path | None = None) -> dict[str, str]:
    secret_path = path or Path(os.environ.get("SNOWFLAKE_ENV_FILE", DEFAULT_SECRET_FILE))
    if not secret_path.exists():
        return {}
    loaded: dict[str, str] = {}
    for line in secret_path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = _unquote(value)
        loaded[key] = value
        os.environ[key] = value
    return loaded
