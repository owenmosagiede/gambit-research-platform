#!/usr/bin/env python3
"""Retired batch CLI. This command never opens a workspace or starts research."""
import sys


def main():
    print('Research batches have been retired. Submit one explicitly reviewed experiment through the ordinary research queue.', file=sys.stderr)
    return 2


if __name__ == '__main__':
    raise SystemExit(main())
