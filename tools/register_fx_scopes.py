#!/usr/bin/env python3
"""Register the approved fixed FX universe definitions and membership snapshots."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from data.scopes import register_fx_scopes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--request', type=Path, required=True, help='Exact approved user request text')
    args = parser.parse_args()
    result = register_fx_scopes(args.root, args.request.read_text(encoding='utf-8'))
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
