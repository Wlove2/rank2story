#!/usr/bin/env python3
'''Start the shared auditable market-scan workflow.'''

from pathlib import Path
import runpy
import sys


TARGET = Path(__file__).resolve().parents[2] / 'novel-analyzer' / 'scripts' / 'scan_start.py'
if not TARGET.is_file():
    raise SystemExit(f'shared scan engine missing: {TARGET}')
sys.path.insert(0, str(TARGET.parent))
runpy.run_path(str(TARGET), run_name='__main__')
