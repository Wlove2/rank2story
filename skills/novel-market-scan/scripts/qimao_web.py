#!/usr/bin/env python3
'''Run the shared Qimao Web collector or browser-snapshot parser.'''

from pathlib import Path
import runpy
import sys


TARGET = Path(__file__).resolve().parents[2] / 'novel-analyzer' / 'scripts' / 'collect_qimao_web_ranks.py'
if not TARGET.is_file():
    raise SystemExit(f'shared Qimao collector missing: {TARGET}')
sys.path.insert(0, str(TARGET.parent))
runpy.run_path(str(TARGET), run_name='__main__')
