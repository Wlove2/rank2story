#!/usr/bin/env python3
'''Run the live initializer, then route every claimed run through its frozen snapshot.'''

import os
from pathlib import Path
import runpy
import sys


LIVE_SCRIPTS = Path(__file__).resolve().parents[2] / 'novel-analyzer' / 'scripts'


def filesystem_path(path: Path) -> Path:
    if os.name != 'nt':
        return path
    text = os.path.abspath(str(path))
    if text.startswith('\\\\?\\'):
        return Path(text)
    if text.startswith('\\\\'):
        return Path('\\\\?\\UNC\\' + text[2:])
    return Path('\\\\?\\' + text)


def claim_argument() -> Path | None:
    if '--claim' not in sys.argv:
        return None
    index = sys.argv.index('--claim')
    if index + 1 >= len(sys.argv):
        raise SystemExit('--claim requires a path')
    return Path(sys.argv[index + 1]).resolve()


command = sys.argv[1] if len(sys.argv) > 1 else ''
claim = claim_argument()
if command == 'run':
    target = LIVE_SCRIPTS / 'candidate_workflow.py'
elif claim is not None:
    snapshot_scripts = claim.parent / '_bundle_snapshot'
    if command == 'execute':
        target = snapshot_scripts / 'candidate_executor.py'
        sys.argv.pop(1)
    else:
        target = snapshot_scripts / 'candidate_workflow.py'
else:
    target = LIVE_SCRIPTS / 'candidate_workflow.py'

target_filesystem = filesystem_path(target)
if not target_filesystem.is_file():
    raise SystemExit(f'candidate runtime missing: {target}')
sys.path.insert(0, str(target_filesystem.parent))
runpy.run_path(str(target_filesystem), run_name='__main__')
