#!/usr/bin/env python3
"""Register shared FX Feature recipes without creating observations."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from data.reusable_features import register_reusable_fx_recipes


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    args=parser.parse_args()
    print(json.dumps(register_reusable_fx_recipes(args.root),indent=2,sort_keys=True))


if __name__=='__main__':main()
