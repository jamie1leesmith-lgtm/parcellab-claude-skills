#!/usr/bin/env python3
"""Emit a fresh fraud-risk fragment for one order.

Reads the canned CDC payloads, repoints every occurrence of the source demo
domain at the active store, and rewrites prediction timestamps so the risk
data reads as recent rather than months old. Output goes on the order as
top-level `tags` plus `additional_attributes.riskAssessment`.
"""

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

SOURCE_DOMAIN = "cdc-demo-store.myshopify.com"
LEVELS = ("low", "medium", "high")
DEFAULT_SOURCE = (Path(__file__).resolve().parent.parent / "skills"
                  / "demo-environment" / "references"
                  / "fraud_risk_payloads.json")
TS_KEYS = ("created_at", "updated_at", "prediction_date")


def freshen(pred, now):
    for key in TS_KEYS:
        if pred.get(key):
            offset = timedelta(days=2) if key == "prediction_date" else timedelta(hours=1)
            pred[key] = (now - offset).isoformat()
    return pred


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--level", required=True)
    ap.add_argument("--shop-url", required=True)
    ap.add_argument("--source", default=str(DEFAULT_SOURCE))
    ap.add_argument("--now", default=None,
                    help="ISO8601 override for deterministic tests")
    args = ap.parse_args()

    if args.level not in LEVELS:
        sys.exit(f"unknown level {args.level!r}: choose from {', '.join(LEVELS)}")

    now = (datetime.fromisoformat(args.now) if args.now
           else datetime.now(timezone.utc))

    raw = json.loads(Path(args.source).read_text())
    if args.level not in raw:
        sys.exit(f"source file has no {args.level!r} key")
    blob = json.dumps(raw[args.level]).replace(SOURCE_DOMAIN, args.shop_url)
    entry = json.loads(blob)

    fragment = {
        "tags": entry["tags"],
        "additional_attributes": {
            "riskAssessment": [freshen(p, now) for p in entry["riskAssessment"]],
        },
    }
    json.dump(fragment, sys.stdout, indent=2)
    print()


if __name__ == "__main__":
    main()
