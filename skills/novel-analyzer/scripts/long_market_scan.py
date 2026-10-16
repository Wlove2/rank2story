#!/usr/bin/env python3
"""Public entry point and compatibility exports for long market scanning."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ENTRY_PATH = Path(__file__).with_name("long_market_scan_entry.py")
SPEC = importlib.util.spec_from_file_location("long_market_scan_entry", ENTRY_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"cannot load {ENTRY_PATH}")
ENTRY = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = ENTRY
SPEC.loader.exec_module(ENTRY)

CORE = ENTRY.CORE
normalized_entries = CORE.normalized_entries
build_matrix = CORE.build_matrix
trend_label = CORE.trend_label
source_date = ENTRY.source_date
stamp_entries = ENTRY.stamp_entries
correct_matrix_dates = ENTRY.correct_matrix_dates
render_report = ENTRY.render_report
main = ENTRY.main


if __name__ == "__main__":
    raise SystemExit(main())
