#!/usr/bin/env python3
"""D05i Phase 1: reuse D05e crop review; build or import human readability labels."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'edge-agent'))
from offline_vision.crop_readability import build_review, import_review  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    build = commands.add_parser('prepare')
    build.add_argument('--dataset', type=Path, required=True)
    build.add_argument('--labels', type=Path, required=True)
    build.add_argument('--comparison', type=Path, action='append', default=[])
    build.add_argument('--pending-inventory', type=Path)
    build.add_argument('--output', type=Path, required=True)
    load = commands.add_parser('import')
    load.add_argument('--review-root', type=Path, required=True)
    load.add_argument('--labels', type=Path, required=True)
    load.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'prepare':
        result = build_review(args.dataset, args.labels, args.output,
            comparisons=args.comparison, pending_path=args.pending_inventory)
    else:
        result = import_review(args.review_root, args.labels, args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
