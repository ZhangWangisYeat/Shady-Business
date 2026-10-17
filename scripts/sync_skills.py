#!/usr/bin/env python3
"""Mirror portable Codex Agent Skills to Claude skills; optionally check drift."""
import argparse
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / '.agents' / 'skills'
DST = ROOT / '.claude' / 'skills'

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    source_files = sorted(p for p in SRC.rglob('*') if p.is_file())
    if not source_files:
        print('No canonical skills found', file=sys.stderr); return 1
    mismatched = []
    for p in source_files:
        q = DST / p.relative_to(SRC)
        if args.check:
            if not q.is_file() or q.read_bytes() != p.read_bytes():
                mismatched.append(str(q.relative_to(ROOT)))
        else:
            q.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p,q)
    if args.check:
        extras = [p for p in DST.rglob('*') if p.is_file() and not (SRC / p.relative_to(DST)).exists()] if DST.exists() else []
        mismatched += [str(p.relative_to(ROOT)) for p in extras]
    if mismatched:
        print('Skill mirrors out of sync:\n'+'\n'.join(mismatched)); return 1
    print('Skill mirrors verified' if args.check else f'Mirrored {len(source_files)} files')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
