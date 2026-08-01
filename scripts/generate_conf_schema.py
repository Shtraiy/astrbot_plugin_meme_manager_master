#!/usr/bin/env python3
"""Regenerate _conf_schema.json from runtime_config.PluginConfig.to_schema().

Usage:
    python scripts/generate_conf_schema.py --check   # exit 1 on drift
    python scripts/generate_conf_schema.py --write   # regenerate the file
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "_conf_schema.json"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from runtime_config import PluginConfig  # noqa: E402


def generate_schema_text() -> str:
    return json.dumps(PluginConfig.to_schema(), ensure_ascii=False, indent=2) + "\n"


def schema_matches_file(path: Path = SCHEMA_PATH) -> bool:
    try:
        return path.read_text(encoding="utf-8") == generate_schema_text()
    except OSError:
        return False


def main() -> int:
    if "--check" in sys.argv:
        if schema_matches_file():
            print("schema is in sync")
            return 0
        print("schema drift detected; run with --write to regenerate", file=sys.stderr)
        return 1
    if "--write" in sys.argv:
        SCHEMA_PATH.write_text(generate_schema_text(), encoding="utf-8")
        print(f"wrote {SCHEMA_PATH}")
        return 0
    print("usage: python scripts/generate_conf_schema.py [--check|--write]")
    return 2


if __name__ == "__main__":
    sys.exit(main())
