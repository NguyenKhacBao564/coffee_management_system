#!/usr/bin/env python3
"""Prepare a bounded diverse-image review using the D05b labeler."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'edge-agent'))
from offline_vision.diverse_review import prepare
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--incoming',type=Path,required=True)
parser.add_argument('--output',type=Path,required=True)
parser.add_argument('--per-source',type=int,default=32)
args=parser.parse_args()
print(json.dumps(prepare(args.incoming,args.output,args.per_source),ensure_ascii=False,indent=2))
