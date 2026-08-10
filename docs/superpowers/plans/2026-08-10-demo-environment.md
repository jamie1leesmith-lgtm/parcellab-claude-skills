# demo-environment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `demo-environment` conductor skill that turns one intake interview into a complete parcelLab customer demo (branded template, 1–5 fraud-tagged orders with event journeys, optional Shopify dev-store build, one CDC demo request linking the real orders), per the approved spec `docs/superpowers/specs/2026-08-07-demo-environment-design.md`.

**Architecture:** A new conductor skill prepares a validated `demo-manifest.json` at intake, then drives the existing sub-skills (`branded-template` inline, `shopify-seed` as a background agent, `order-lifecycle` mechanics inline, `demo-request` submission at the end) through additive "Orchestrated runs" contracts. Two small stdlib-Python scripts (manifest validator, fraud-fragment preparer) make the deterministic parts testable.

**Tech Stack:** Claude Code SKILL.md instructions · Python 3 stdlib (`unittest`, no pytest, no pip) · Node ≥18 (existing `submit_demo_request.mjs`) · `parcellab` CLI · `shopify` CLI · Browser pane (`mcp__Claude_Browser__*`) · parcelLab MCP connector.

## Global Constraints

- Tests are stdlib `unittest` only. Run: `cd plugins/pl-tools/scripts && python3 -m unittest discover -s tests -v`. Never `pip install`; pytest is not installed.
- All file references inside skills use `${CLAUDE_PLUGIN_ROOT}/…`. Never `~/.claude/skills/…`, never repo-relative paths.
- Skill frontmatter `name:` must equal its directory name exactly; the `description:` must contain the word "parcelLab" spelled out.
- Skill directory is `demo-environment` (no `pl-` prefix). No new plugin, no marketplace entry, no `version` field added to pl-tools.
- Edits to the four existing skills are **additive only** — one new "Orchestrated runs" section each; no existing step changes.
- Never accept or print credentials in chat. CDC values live in `~/.claude/parcellab-demo-request.env` or the settings env block, set up via `/pl-setup`.
- Any parcelLab account write is preceded (once per run, at intake) by name confirmation via `parcellab account account show <id>` and an `account-restricted` edit-mode check. Shopify writes go to the confirmed **dev store only**.
- Event files `NN-<status>.json` never contain `event_timestamp` or `account`; events are identified by `courier` + `tracking_number`.
- Proven event statuses are exactly: `InTransit`, `OutForDelivery`, `Delivered`, `WarehouseDelay`. Anything else is offered but labelled unproven.
- CDC order-type enum is exactly: `fraud_high`, `fraud_medium`, `fraud_low`, `manual_return`, `return_tracking`.
- All work happens on branch `feat/demo-environment`; push only to `jamie1leesmith-lgtm/parcellab-claude-skills` (check `git branch --show-current` and `git remote -v` before every push).
- No currency symbols hardcoded in any generated figure or report line.

## Shared interfaces (referenced by many tasks)

- **Run directory:** `$HOME/parcellab-demo-runs/<brand-handle>-<timestamp>/` containing:
  - `demo-manifest.json` — the manifest (schema in Task 2 / Task 8).
  - `results/branded-template.json`, `results/shopify-seed.json`, `results/demo-request.json` — machine-readable lane outcomes.
  - `results/linked-orders.json` — `[{"order_number": str, "order_type": <enum>}]`, written by Phase 2, consumed by Phase 3.
  - `orders/<nn>-<label>/` — per-order dir: `create.json`, `NN-<status>.json` event files, `order.json` (see Task 7), `run.log`.
  - `seed/seed-products.json`, `seed/seed-shaped.json` — Shopify path only.
- **Scripts (Task 1, Task 2):**
  - `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/prepare_fraud_fragment.py --level <low|medium|high> --shop-url <domain> [--source <path>] [--now <ISO8601>]` → stdout JSON `{"tags": [...], "additional_attributes": {"riskAssessment": [...]}}`, exit 1 + stderr message on bad input.
  - `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/validate_manifest.py <manifest-path>` → exit 0 silent-ish (`MANIFEST OK`), exit 1 with one `MANIFEST INVALID: <reason>` line per failure.
- **Env keys:** `CDC_DEMO_API_TOKEN`, `CDC_DEMO_API_BASE_URL`, `CDC_ACCOUNT_CONFIG_SHOPIFY`, `CDC_ACCOUNT_CONFIG_STANDARD` (all read from process env first, then `~/.claude/parcellab-demo-request.env`).

---

### Task 1: Fraud-fragment source + `prepare_fraud_fragment.py`

**Files:**
- Create: `plugins/pl-tools/skills/demo-environment/references/fraud_risk_payloads.json`
- Create: `plugins/pl-tools/scripts/prepare_fraud_fragment.py`
- Test: `plugins/pl-tools/scripts/tests/test_prepare_fraud_fragment.py`

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: the CLI contract in *Shared interfaces*. Source JSON has top-level keys `low|medium|high`, each `{"tags": ["FraudRisk<Level>"], "riskAssessment": [...]}`. The source's demo domain is the literal string `cdc-demo-store.myshopify.com`.

- [ ] **Step 1: Fetch the canonical source JSON**

```bash
mkdir -p plugins/pl-tools/skills/demo-environment/references
gh api repos/parcelLab/custom-demo-creator/contents/fraud_risk_payloads.json \
  --jq '.content' | base64 -d \
  > plugins/pl-tools/skills/demo-environment/references/fraud_risk_payloads.json
python3 -c "import json;d=json.load(open('plugins/pl-tools/skills/demo-environment/references/fraud_risk_payloads.json'));assert set(d)=={'low','medium','high'};print('source OK')"
```

If `gh` lacks access to `parcelLab/custom-demo-creator`, stop and report — do not hand-write the fragments. (Open item: Jamie may supply a newer payload; if he has by execution time, use his file instead and note the swap in the commit message.)

- [ ] **Step 2: Write the failing tests**

`plugins/pl-tools/scripts/tests/test_prepare_fraud_fragment.py`:

```python
import json
import subprocess
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
SCRIPT = SCRIPTS / "prepare_fraud_fragment.py"
SOURCE = (SCRIPTS.parent / "skills" / "demo-environment" / "references"
          / "fraud_risk_payloads.json")
NOW = "2026-08-11T12:00:00+00:00"


def run(*args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True, text=True,
    )


class TestPrepareFraudFragment(unittest.TestCase):
    def fragment(self, level):
        r = run("--level", level, "--shop-url", "jamie-demo.myshopify.com",
                "--source", str(SOURCE), "--now", NOW)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def test_tags_match_level(self):
        self.assertEqual(self.fragment("high")["tags"], ["FraudRiskHigh"])
        self.assertEqual(self.fragment("low")["tags"], ["FraudRiskLow"])

    def test_output_shape(self):
        out = self.fragment("medium")
        self.assertEqual(set(out), {"tags", "additional_attributes"})
        ra = out["additional_attributes"]["riskAssessment"]
        self.assertIsInstance(ra, list)
        self.assertGreater(len(ra), 0)

    def test_source_domain_fully_replaced(self):
        blob = json.dumps(self.fragment("high"))
        self.assertNotIn("cdc-demo-store.myshopify.com", blob)
        self.assertIn("jamie-demo.myshopify.com", blob)

    def test_timestamps_freshened(self):
        now = datetime.fromisoformat(NOW)
        for pred in self.fragment("high")["additional_attributes"]["riskAssessment"]:
            for key in ("created_at", "updated_at", "prediction_date"):
                if key in pred and pred[key]:
                    ts = datetime.fromisoformat(pred[key])
                    self.assertLessEqual(now - ts, timedelta(days=7),
                                         f"{key} not freshened: {pred[key]}")
                    self.assertLessEqual(ts, now)

    def test_unknown_level_fails(self):
        r = run("--level", "extreme", "--shop-url", "x.myshopify.com",
                "--source", str(SOURCE))
        self.assertEqual(r.returncode, 1)
        self.assertIn("level", r.stderr.lower())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd plugins/pl-tools/scripts && python3 -m unittest tests.test_prepare_fraud_fragment -v`
Expected: errors — `prepare_fraud_fragment.py` does not exist yet.

- [ ] **Step 4: Write the implementation**

`plugins/pl-tools/scripts/prepare_fraud_fragment.py`:

```python
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd plugins/pl-tools/scripts && python3 -m unittest tests.test_prepare_fraud_fragment -v`
Expected: all 5 PASS. Also run the full suite (`python3 -m unittest discover -s tests -v`) to confirm nothing else broke.

- [ ] **Step 6: Commit**

```bash
git add plugins/pl-tools/skills/demo-environment/references/fraud_risk_payloads.json \
        plugins/pl-tools/scripts/prepare_fraud_fragment.py \
        plugins/pl-tools/scripts/tests/test_prepare_fraud_fragment.py
git commit -m "feat(demo-environment): fraud fragment source + preparer script"
```

---

### Task 2: `validate_manifest.py`

**Files:**
- Create: `plugins/pl-tools/scripts/validate_manifest.py`
- Test: `plugins/pl-tools/scripts/tests/test_validate_manifest.py`

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: CLI contract in *Shared interfaces*; exported constants `PROVEN_EVENTS = {"InTransit", "OutForDelivery", "Delivered", "WarehouseDelay"}`, `CDC_SLOTS = {"fraud_high", "fraud_medium", "fraud_low", "manual_return", "return_tracking"}`, `FRAUD_LEVELS = {"low", "medium", "high"}`, `PATHS = {"engage", "retain", "retain-shopify"}`; function `validate(manifest: dict) -> list[str]` (empty list = valid). The manifest schema this validator defines is the one Task 8 writes.

- [ ] **Step 1: Write the failing tests**

`plugins/pl-tools/scripts/tests/test_validate_manifest.py`:

```python
import copy
import unittest

from validate_manifest import validate


def valid_manifest():
    return {
        "run": {"created_at": "2026-08-11T09:00:00+00:00",
                "run_dir": "/Users/x/parcellab-demo-runs/acme-20260811",
                "skill_version": "abc123"},
        "path": "retain-shopify",
        "brand": {"name": "Acme", "url": "https://acme.example.com",
                  "handle": "acme", "region": "UK", "category": "Fashion"},
        "account": {"id": 1626718, "name": "Jamie Demo",
                    "confirmed_at": "2026-08-11T09:01:00+00:00",
                    "edit_mode_verified": True},
        "cdc": {"selected_account_config_id": None, "config_source": "none",
                "generate_orders": False, "order_types": []},
        "shopify": {"enabled": True, "store": "jamie-demo.myshopify.com",
                    "location_id": "gid://shopify/Location/123"},
        "destination_country": "GBR",
        "products": [
            {"id": f"p{i}", "name": f"Product {i}", "product_type": t,
             "price": "20.00", "options": [{"name": "Size", "values": ["S", "M"]}],
             "image_url": "https://img.example.com/x.jpg", "image_verified": True,
             "pdp_url": "https://acme.example.com/p", "sku": f"sku{i}"}
            for i, t in enumerate(["Shirt", "Shoe", "Hat", "Bag", "Coat"], start=1)
        ],
        "selection": {"core4": ["p1", "p2", "p3", "p4"], "shopify_extra": ["p5"]},
        "brand_tokens": {"tokens": {"BRAND_NAME": "Acme"},
                         "logo": {"type": "url", "value": "https://acme.example.com/l.png"},
                         "hero": {"url": "https://acme.example.com/h.jpg", "alt": "hero"}},
        "orders": [
            {"label": "clean-low", "dir": "orders/01-clean-low",
             "cdc_slot": "fraud_low", "fraud_level": "low",
             "customer": {"name": "Alice Smith", "email": "alice@example.com"},
             "products": ["p1"],
             "shipments": [{"label": "A", "scenario": "happy", "courier": "dpd-uk",
                            "products": ["p1"],
                            "events": ["InTransit", "OutForDelivery", "Delivered"]}]},
            {"label": "split-medium", "dir": "orders/02-split-medium",
             "cdc_slot": "fraud_medium", "fraud_level": "medium",
             "customer": {"name": "Bob Jones", "email": "bob@example.com"},
             "products": ["p2", "p3"],
             "shipments": [
                 {"label": "A", "scenario": "happy", "courier": "dpd-uk",
                  "products": ["p2"],
                  "events": ["InTransit", "OutForDelivery", "Delivered"]},
                 {"label": "B", "scenario": "stuck-delay", "courier": "dpd-uk",
                  "products": ["p3"], "events": ["InTransit", "WarehouseDelay"]}]},
        ],
        "gates": {"order_lifecycle": {"gate_b_answered": True,
                                      "gate_c": "send-as-is", "extras": {}}},
        "approvals": {"products_approved_at": "2026-08-11T09:05:00+00:00",
                      "intake_completed_at": "2026-08-11T09:05:00+00:00"},
    }


def broken(mutator):
    m = valid_manifest()
    mutator(m)
    return m


class TestValidateManifest(unittest.TestCase):
    def test_valid_manifest_passes(self):
        self.assertEqual(validate(valid_manifest()), [])

    def test_bad_path(self):
        errs = validate(broken(lambda m: m.update(path="both")))
        self.assertTrue(any("path" in e for e in errs))

    def test_core4_must_have_four_distinct_types(self):
        errs = validate(broken(
            lambda m: m["selection"].update(core4=["p1", "p2", "p3"])))
        self.assertTrue(any("core4" in e for e in errs))
        m = valid_manifest()
        m["products"][1]["product_type"] = m["products"][0]["product_type"]
        self.assertTrue(any("distinct" in e for e in validate(m)))

    def test_unverified_image_fails(self):
        m = valid_manifest()
        m["products"][0]["image_verified"] = False
        self.assertTrue(any("image" in e for e in validate(m)))

    def test_order_count_bounds(self):
        m = valid_manifest()
        m["orders"] = []
        self.assertTrue(any("orders" in e for e in validate(m)))
        m = valid_manifest()
        m["orders"] = [copy.deepcopy(m["orders"][0]) for _ in range(6)]
        self.assertTrue(any("5" in e for e in validate(m)))

    def test_split_required_for_multi_order_runs(self):
        m = valid_manifest()
        m["orders"][1]["shipments"] = [m["orders"][1]["shipments"][0]]
        self.assertTrue(any("split" in e for e in validate(m)))

    def test_single_order_run_needs_no_split(self):
        m = valid_manifest()
        m["orders"] = [m["orders"][0]]
        self.assertEqual(validate(m), [])

    def test_duplicate_customer_and_slot(self):
        m = valid_manifest()
        m["orders"][1]["customer"] = dict(m["orders"][0]["customer"])
        self.assertTrue(any("customer" in e for e in validate(m)))
        m = valid_manifest()
        m["orders"][1]["cdc_slot"] = "fraud_low"
        self.assertTrue(any("cdc_slot" in e for e in validate(m)))

    def test_fraud_level_required(self):
        m = valid_manifest()
        del m["orders"][0]["fraud_level"]
        self.assertTrue(any("fraud_level" in e for e in validate(m)))

    def test_retain_needs_a_delivered_order(self):
        m = valid_manifest()
        for o in m["orders"]:
            for s in o["shipments"]:
                s["events"] = ["InTransit", "WarehouseDelay"]
                s["scenario"] = "stuck-delay"
        self.assertTrue(any("Delivered" in e for e in validate(m)))

    def test_unproven_event_needs_label(self):
        m = valid_manifest()
        m["orders"][0]["shipments"][0]["events"].append("Delivered-ParcelLocker")
        self.assertTrue(any("unproven" in e for e in validate(m)))
        m["orders"][0]["shipments"][0]["unproven_events"] = ["Delivered-ParcelLocker"]
        self.assertEqual(validate(m), [])

    def test_shopify_consistency(self):
        m = valid_manifest()
        m["shopify"] = {"enabled": False}
        self.assertTrue(any("retain-shopify" in e for e in validate(m)))
        m = valid_manifest()
        m["shopify"]["location_id"] = "123"
        self.assertTrue(any("location" in e for e in validate(m)))

    def test_account_and_gates(self):
        m = valid_manifest()
        m["account"]["edit_mode_verified"] = False
        self.assertTrue(any("edit-mode" in e for e in validate(m)))
        m = valid_manifest()
        m["approvals"]["products_approved_at"] = ""
        self.assertTrue(any("approval" in e for e in validate(m)))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd plugins/pl-tools/scripts && python3 -m unittest tests.test_validate_manifest -v`
Expected: import error — module missing.

- [ ] **Step 3: Write the implementation**

`plugins/pl-tools/scripts/validate_manifest.py`:

```python
#!/usr/bin/env python3
"""Fail-loud completeness check for demo-manifest.json, run before Phase 1.

Every rule mirrors the spec's Order model + manifest section. Exit 0 with
"MANIFEST OK", or exit 1 printing one "MANIFEST INVALID: <reason>" per line.
"""

import json
import sys

PROVEN_EVENTS = {"InTransit", "OutForDelivery", "Delivered", "WarehouseDelay"}
CDC_SLOTS = {"fraud_high", "fraud_medium", "fraud_low",
             "manual_return", "return_tracking"}
FRAUD_LEVELS = {"low", "medium", "high"}
PATHS = {"engage", "retain", "retain-shopify"}


def validate(m):
    errs = []

    def need(cond, msg):
        if not cond:
            errs.append(msg)

    need(m.get("path") in PATHS, f"path must be one of {sorted(PATHS)}")

    products = {p.get("id"): p for p in m.get("products", [])}
    core4 = m.get("selection", {}).get("core4", [])
    extra = m.get("selection", {}).get("shopify_extra", [])
    need(len(core4) == 4, "core4 must name exactly 4 products")
    for pid in core4 + extra:
        need(pid in products, f"selection references unknown product {pid}")
    core_products = [products[p] for p in core4 if p in products]
    types = [p.get("product_type") for p in core_products]
    need(len(set(types)) == len(types), "core4 product types must be distinct")
    for pid in core4 + extra:
        if pid in products:
            need(products[pid].get("image_verified") is True,
                 f"image for {pid} not verified")

    shopify = m.get("shopify", {})
    if m.get("path") == "retain-shopify":
        need(shopify.get("enabled") is True,
             "path retain-shopify requires shopify.enabled true")
    if shopify.get("enabled"):
        need(bool(shopify.get("store")), "shopify.store missing")
        need(str(shopify.get("location_id", "")).startswith("gid://shopify/Location/"),
             "shopify.location_id must be a gid://shopify/Location/ id")

    orders = m.get("orders", [])
    need(1 <= len(orders) <= 5, "orders must contain between 1 and 5 entries")
    if len(orders) >= 2:
        need(any(len(o.get("shipments", [])) >= 2 for o in orders),
             "runs of 2+ orders need at least one split-shipment order")

    seen_customers, seen_slots, seen_labels = set(), set(), set()
    any_delivered = False
    for o in orders:
        label = o.get("label", "?")
        need(label not in seen_labels, f"duplicate order label {label}")
        seen_labels.add(label)
        cust = (o.get("customer", {}).get("name"), o.get("customer", {}).get("email"))
        need(all(cust), f"order {label}: customer name and email required")
        need(cust not in seen_customers, f"order {label}: duplicate customer {cust}")
        seen_customers.add(cust)
        need(o.get("fraud_level") in FRAUD_LEVELS,
             f"order {label}: fraud_level required (low|medium|high)")
        slot = o.get("cdc_slot")
        if slot is not None:
            need(slot in CDC_SLOTS, f"order {label}: unknown cdc_slot {slot}")
            need(slot not in seen_slots, f"order {label}: duplicate cdc_slot {slot}")
            seen_slots.add(slot)
        need(bool(o.get("shipments")), f"order {label}: needs at least one shipment")
        for s in o.get("shipments", []):
            events = s.get("events", [])
            need(bool(events), f"order {label}/{s.get('label')}: needs events")
            unproven = set(s.get("unproven_events", []))
            for e in events:
                need(e in PROVEN_EVENTS or e in unproven,
                     f"order {label}/{s.get('label')}: event {e} outside the "
                     f"proven set must be listed in unproven_events")
            if events and events[-1] == "Delivered":
                any_delivered = True

    if m.get("path") in ("retain", "retain-shopify"):
        need(any_delivered,
             "Retain runs need at least one shipment ending Delivered")

    acct = m.get("account", {})
    need(bool(acct.get("id")) and bool(acct.get("name")),
         "account id and resolved name required")
    need(bool(acct.get("confirmed_at")), "account not confirmed at intake")
    need(acct.get("edit_mode_verified") is True, "edit-mode guard not verified")

    gates = m.get("gates", {}).get("order_lifecycle", {})
    need(gates.get("gate_b_answered") is True, "gate B answer missing")
    approvals = m.get("approvals", {})
    need(bool(approvals.get("products_approved_at")),
         "product approval timestamp missing")
    need(bool(approvals.get("intake_completed_at")),
         "intake approval timestamp missing")

    tokens = m.get("brand_tokens", {})
    need(bool(tokens.get("tokens")), "brand_tokens.tokens missing")
    need(bool(m.get("destination_country")), "destination_country missing")
    return errs


def main():
    if len(sys.argv) != 2:
        sys.exit("usage: validate_manifest.py <manifest-path>")
    manifest = json.loads(open(sys.argv[1]).read())
    errs = validate(manifest)
    if errs:
        for e in errs:
            print(f"MANIFEST INVALID: {e}")
        sys.exit(1)
    print("MANIFEST OK")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd plugins/pl-tools/scripts && python3 -m unittest tests.test_validate_manifest -v`
Expected: all PASS. Then the full suite.

- [ ] **Step 5: Commit**

```bash
git add plugins/pl-tools/scripts/validate_manifest.py \
        plugins/pl-tools/scripts/tests/test_validate_manifest.py
git commit -m "feat(demo-environment): manifest validator with spec ground rules"
```

---

### Task 3: Extend `submit_demo_request.mjs` + refresh `api-payload.md`

**Files:**
- Modify: `plugins/pl-tools/skills/demo-request/scripts/submit_demo_request.mjs` (validation block, lines ~53–89)
- Modify: `plugins/pl-tools/skills/demo-request/references/api-payload.md` (full rewrite)

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: the submit script accepts and passes through `selected_account_config_id` (already validated), `generate_orders` (boolean), `order_types` (array from the CDC enum), `linked_orders` (`[{order_number, order_type}]`), `products[].category_override` (`Home|Electronics|Fashion`). Invalid enum values fail before any network call, naming the offender.

- [ ] **Step 1: Add validation for the new fields**

In `validatePayload`, after the existing `selected_account_config_id` block, insert:

```javascript
  const ORDER_TYPES = new Set([
    'fraud_high', 'fraud_medium', 'fraud_low', 'manual_return', 'return_tracking',
  ]);

  if (payload.generate_orders != null && typeof payload.generate_orders !== 'boolean') {
    throw new Error('generate_orders must be a boolean when provided.');
  }

  if (payload.order_types != null) {
    if (!Array.isArray(payload.order_types)) {
      throw new Error('order_types must be an array when provided.');
    }
    const bad = payload.order_types.filter((t) => !ORDER_TYPES.has(t));
    if (bad.length) {
      throw new Error(`order_types contains invalid values: ${bad.join(', ')}`);
    }
  }

  if (payload.linked_orders != null) {
    if (!Array.isArray(payload.linked_orders)) {
      throw new Error('linked_orders must be an array when provided.');
    }
    payload.linked_orders.forEach((o, i) => {
      if (!String(o?.order_number ?? '').trim()) {
        throw new Error(`linked_orders[${i}].order_number is required.`);
      }
      if (!ORDER_TYPES.has(o?.order_type)) {
        throw new Error(`linked_orders[${i}].order_type is invalid: ${o?.order_type}`);
      }
    });
  }
```

And inside the existing `payload.products.forEach` loop, after the image check:

```javascript
    if (product?.category_override != null
        && !VALID_CATEGORIES.has(product.category_override)) {
      throw new Error(`products[${index}].category_override must be Home, Electronics, or Fashion.`);
    }
```

- [ ] **Step 2: Verify validation behaviour without touching the network**

```bash
cd plugins/pl-tools/skills/demo-request/scripts
BASE='{"prospect_name":"Acme","website_url":"https://acme.example.com","region":"UK","category":"Fashion","products":[{"name":"A"},{"name":"B"},{"name":"C"},{"name":"D"}]}'
# invalid order_type must fail naming the value:
echo "$BASE" | python3 -c "import json,sys;d=json.load(sys.stdin);d['order_types']=['fraud_high','bogus'];print(json.dumps(d))" > /tmp/p1.json
CDC_DEMO_API_TOKEN=dummy node submit_demo_request.mjs /tmp/p1.json; echo "exit=$?"
# expected: error mentioning "bogus", exit=1
# invalid linked_orders shape must fail:
echo "$BASE" | python3 -c "import json,sys;d=json.load(sys.stdin);d['linked_orders']=[{'order_type':'fraud_low'}];print(json.dumps(d))" > /tmp/p2.json
CDC_DEMO_API_TOKEN=dummy node submit_demo_request.mjs /tmp/p2.json; echo "exit=$?"
# expected: error "linked_orders[0].order_number is required.", exit=1
# valid payload must PASS validation and fail only at the network stage:
echo "$BASE" | python3 -c "import json,sys;d=json.load(sys.stdin);d['generate_orders']=False;d['linked_orders']=[{'order_number':'AB1','order_type':'fraud_low'}];print(json.dumps(d))" > /tmp/p3.json
CDC_DEMO_API_TOKEN=dummy CDC_DEMO_API_BASE_URL=http://127.0.0.1:9 node submit_demo_request.mjs /tmp/p3.json; echo "exit=$?"
# expected: fetch/connection error (NOT a validation message), exit=1
```

- [ ] **Step 3: Rewrite `api-payload.md`**

Replace the file's content with the current API surface (canonical source: the *Automation API Reference* Notion page — link it):

```markdown
# Custom Demo Creator Automation Payload

Canonical reference (always check before extending):
https://app.notion.com/p/parcellab/Automation-API-Reference-3b8c37dcb4c481789aa8c5e80fcfc730

Endpoint:

    POST /api/automation/demo-requests
    Authorization: Bearer cdc_live_...   (personal token, scope demo_requests:create)
    Content-Type: application/json

Fields:

- `prospect_name` (required): non-empty string.
- `website_url`: valid URL or empty. Triggers server-side brand/logo enrichment.
- `region` (required): `US` | `UK` | `DE`.
- `category` (required): `Home` | `Electronics` | `Fashion`.
- `notes`: optional string.
- `products` (required): exactly 4 items of
  `{ name (required), image_url?, category_override? }`.
- `selected_account_config_id`: optional UUID. Which parcelLab/Shopify account
  config orders are generated/linked against. **Omitted → the caller's default
  config.** No API exists to list or create configs — UUIDs come from the CDC UI.
- `generate_orders`: optional boolean, default `true`. `false` creates the
  request in `queued` status with no synthetic orders.
- `order_types`: optional array restricting synthetic generation. Enum:
  `fraud_high | fraud_medium | fraud_low | manual_return | return_tracking`.
- `linked_orders`: optional array of `{ order_number, order_type }` attaching
  orders that **already exist** in the target parcelLab account. Additive and
  best-effort: per-item failures land only in the request's activity log
  (`job_logs`) and never fail the HTTP call — verify attachment in-app.
  With token auth this is the ONLY moment linking is possible (the per-order
  endpoints require a session JWT).

Responses:

- `201 { id, status: "ready" | "queued", request_url }`
- `400 { error, details: { fieldErrors } }` — per-field messages.
- `401 / 403` — token missing/invalid or revoked.
- `500 { id, status: "failed", request_url, error }` — **the request still
  exists** and can be retried manually in-app. Report as "created but
  generation failed", never as "nothing happened".
```

- [ ] **Step 4: Commit**

```bash
git add plugins/pl-tools/skills/demo-request/scripts/submit_demo_request.mjs \
        plugins/pl-tools/skills/demo-request/references/api-payload.md
git commit -m "feat(demo-request): support order generation controls and linked_orders"
```

---

### Task 4: "Orchestrated runs" section — `demo-request/SKILL.md`

**Files:**
- Modify: `plugins/pl-tools/skills/demo-request/SKILL.md` (append one section before "Edge cases"; change nothing else)

**Interfaces:**
- Consumes: manifest fields `brand`, `selection.core4`, `products`, `cdc`; run-dir file `results/linked-orders.json` (Task 9/10 write it); Task 3's extended submit script.
- Produces: run-dir file `results/demo-request.json` = `{"id": str, "request_status": str, "request_url": str, "linked_submitted": [...]}`.

- [ ] **Step 1: Append the section**

```markdown
---

## Orchestrated runs (demo-environment)

When this skill is invoked by the `demo-environment` conductor with a run
directory containing `demo-manifest.json` whose
`approvals.products_approved_at` is set, the manifest replaces Steps 1–6:

- **No browsing, no questions.** Products, region and category were collected
  and approved at the conductor's intake. If anything needed is missing from
  the manifest, STOP and report the gap — never re-open the browser and never
  ask the user.
- **Build the payload from the manifest:** `prospect_name` = `brand.name`,
  `website_url` = `brand.url`, `region` = `brand.region`, `category` =
  `brand.category`, `products` = the four `selection.core4` entries as
  `{name, image_url}`. From `cdc`: `selected_account_config_id` (omit the key
  when null), `generate_orders`, and `order_types` (omit when empty).
- **Link the real orders:** if `results/linked-orders.json` exists in the run
  dir, pass its array verbatim as `linked_orders`.
- **Submit** exactly as Step 7 (same script, same env), then write
  `results/demo-request.json` in the run dir:
  `{"id", "request_status", "request_url", "linked_submitted": <the
  linked_orders array or []>}` — and report the same values in prose.
- **On HTTP 500:** the request still exists (`status: failed`) — record its
  id/URL in the results file and report "created but generation failed;
  retry manually in-app". Linking is best-effort per item: tell the user to
  eyeball the request's activity log, since per-item failures never fail the
  call.

Standalone behaviour (no manifest): everything above this section, unchanged.
```

- [ ] **Step 2: Verify the edit is additive and safe**

```bash
git diff --stat plugins/pl-tools/skills/demo-request/SKILL.md   # exactly one file, additions only
grep -c "CLAUDE_PLUGIN_ROOT" plugins/pl-tools/skills/demo-request/SKILL.md  # unchanged count vs git show HEAD:<file>
head -5 plugins/pl-tools/skills/demo-request/SKILL.md            # frontmatter untouched: name demo-request
```

- [ ] **Step 3: Commit**

```bash
git add plugins/pl-tools/skills/demo-request/SKILL.md
git commit -m "feat(demo-request): orchestrated-runs contract for demo-environment"
```

---

### Task 5: "Orchestrated runs" section — `branded-template/SKILL.md`

**Files:**
- Modify: `plugins/pl-tools/skills/branded-template/SKILL.md` (append one section at the end, after the "Differences from parcellab-brand-layout" table; change nothing else)

**Interfaces:**
- Consumes: manifest `brand_tokens` = `{"tokens": {<__BRAND_X__ name>: <value>}, "logo": {"type": "url"|"inline-svg", "value": str}, "hero": {"url": str, "alt": str} | null}`, `account.id`, `shopify.store` (for 9b store preference).
- Produces: run-dir file `results/branded-template.json` = `{"layout_id": int, "release_status": "published"|"not published", "store_assignment": str, "account": int}`. The Phase 2 gate (Tasks 9/10) reads `release_status`.

- [ ] **Step 1: Append the section**

```markdown
---

## Orchestrated runs (demo-environment)

When invoked by the `demo-environment` conductor with a run directory whose
`demo-manifest.json` carries `brand_tokens`, the manifest replaces Steps 1b–6:

- **Account:** use `account.id` from the manifest — it was already confirmed
  by name at the conductor's intake. Do not re-ask.
- **No scraping.** `brand_tokens.tokens` holds the Step 6 token map keyed by
  the template's `__BRAND_X__` names (e.g. `BRAND_NAME`, `CTA_BG`,
  `RADIUS_LG`); `brand_tokens.logo` is either a URL or inline-SVG markup
  (apply the Step 5 decision tree's fill/viewBox rules); `brand_tokens.hero`
  is a verified URL + alt, or null → skip the hero block per Step 4 rule 4.
  If a token the template needs is absent, STOP and report the gap to the
  conductor — do not open the brand site.
- **Steps 7–10 run unchanged**, including the Step 8 preview and its
  question — this is the whole run's one human checkpoint, never skip it.
- **Store assignment preference:** on a Shopify-path run (`shopify.enabled`),
  when 9b.2 offers multiple stores, pre-select the client whose `key` or
  `name` matches `shopify.store`; still follow 9b.3–9b.5 in full.
- **After Step 10**, additionally write `results/branded-template.json` in
  the run dir: `{"layout_id", "release_status", "store_assignment",
  "account"}` with the exact values Step 10 reported. `release_status` is
  what the conductor's publish gate reads — never write `published` unless
  Step 9a's response confirmed it.

Standalone behaviour (no manifest): everything above this section, unchanged.
```

- [ ] **Step 2: Verify additive + frontmatter intact** (same three checks as Task 4 Step 2, against this file)

- [ ] **Step 3: Commit**

```bash
git add plugins/pl-tools/skills/branded-template/SKILL.md
git commit -m "feat(branded-template): orchestrated-runs contract for demo-environment"
```

---

### Task 6: "Orchestrated runs" section — `shopify-seed/SKILL.md`

**Files:**
- Modify: `plugins/pl-tools/skills/shopify-seed/SKILL.md` (append one section after Step 9; change nothing else)

**Interfaces:**
- Consumes: manifest `shopify.store`, `shopify.location_id`, `brand.handle`; run-dir file `seed/seed-products.json` (written by the conductor at intake: same shape Step 3 documents — `{products, location_id, prospect_handle}` where products = core4 ∪ shopify_extra in the scrape shape).
- Produces: run-dir file `results/shopify-seed.json` = `{"status": "ok"|"failed", "products": [{"title", "id", "admin_url", "seeded_price", "variants", "adjusted"}], "demos": <shape script demos output>, "warnings": [...], "error": str|null}`.

- [ ] **Step 1: Append the section**

```markdown
---

## Orchestrated runs (demo-environment)

When invoked as a background agent by the `demo-environment` conductor, the
brief names a run directory; `demo-manifest.json` and `seed/seed-products.json`
inside it replace Steps 1, 2, 3 and 5:

- **Store and location come from the manifest** (`shopify.store`,
  `shopify.location_id`) — both were confirmed/resolved at intake. State the
  store name in output; do not re-ask, do not run `store auth list`.
- **Products come from `seed/seed-products.json`** — already in Step 3's
  input shape with images verified at intake. Skip all browsing.
- **The Step 5 approval is already given** (`approvals.products_approved_at`
  in the manifest). Do not wait for a yes.
- **Agent ground rules:** never open the Browser pane; never ask the user
  anything. A gap (missing file, image Shopify won't fetch, push failure) is
  a failure report, not a question: write it to the results file and stop.
- **Steps 0, 4, 6, 7, 8 run unchanged** (preflight, shaping via
  `shape_product_mix.py`, archive, push, verify by returned IDs).
- **Instead of the Step 9 prose-only report**, write
  `results/shopify-seed.json` in the run dir:
  `{"status": "ok"|"failed", "products": [{"title", "id", "admin_url",
  "seeded_price", "variants", "adjusted"}], "demos": <the shape script's
  demos output verbatim>, "warnings": [...], "error": null|"<message>"}` —
  then give the usual Step 9 tables as the agent's returned summary.

Standalone behaviour (no brief/manifest): everything above this section,
unchanged.
```

- [ ] **Step 2: Verify additive + frontmatter intact** (same checks as Task 4 Step 2)

- [ ] **Step 3: Commit**

```bash
git add plugins/pl-tools/skills/shopify-seed/SKILL.md
git commit -m "feat(shopify-seed): orchestrated-runs contract for demo-environment"
```

---

### Task 7: "Orchestrated runs" section — `order-lifecycle/SKILL.md`

**Files:**
- Modify: `plugins/pl-tools/skills/order-lifecycle/SKILL.md` (append one section at the end; change nothing else)

**Interfaces:**
- Consumes: manifest `orders[]`, `gates.order_lifecycle`, `destination_country`, `account`; Task 1's `prepare_fraud_fragment.py`.
- Produces: per-order `orders/<nn>-<label>/order.json` = `{"order_number": str, "customer": {"name","email"}, "cdc_slot": str|null, "fraud_level": str, "trackings": [{"shipment": "A", "courier": str, "tracking_number": str}]}` — consumed by Phase 2's `results/linked-orders.json` build and the Phase 4 report.

- [ ] **Step 1: Append the section**

```markdown
---

## Orchestrated runs (demo-environment)

When the `demo-environment` conductor drives this skill, `demo-manifest.json`
answers the gates — the manifest's recorded approvals ARE the user's answers,
given at the conductor's intake (this is not inference):

- **Gate A** (product approval): `approvals.products_approved_at`.
- **Gate B** (journey/scenario): each manifest order's `shipments[]` carries
  the chosen scenario, courier and exact `events` sequence. Scenarios beyond
  the proven happy/unhappy shapes (e.g. `recovered` =
  `InTransit → WarehouseDelay → OutForDelivery → Delivered`, or locker
  endings) are **custom-path sequences the user explicitly chose at intake**;
  keep this skill's confidence labelling when reporting them, and never
  silently reorder a sequence.
- **Gate C** (enrichment): `gates.order_lifecycle.gate_c` — `"send-as-is"`
  unless `extras` carries fields, which are applied exactly as the Gate C
  table specifies.
- **Destination country** comes from `destination_country`; the account was
  confirmed by name at intake — do not re-confirm mid-run.

**Multi-order runs.** Each manifest order gets its own directory
(`orders/<nn>-<label>/` inside the run dir), its own `create.json`,
`NN-<status>.json` files, and its own detached driver — the "every run is
isolated" rule applies per order. Drivers run concurrently; a split-shipment
order follows the *Split shipments* rules unchanged within its own directory.

**Fraud data on direct-path orders.** Before sending `create.json`, generate
the order's fragment and merge it in at the top level:

    python3 ${CLAUDE_PLUGIN_ROOT}/scripts/prepare_fraud_fragment.py \
      --level <order.fraud_level> --shop-url <shopify.store, or the
      brand handle + ".myshopify.com" when no store is configured>

The output's `tags` and `additional_attributes` become `create.json`'s
top-level `tags` and `additional_attributes` fields.

**After the order + add_tracking writes succeed**, write
`orders/<nn>-<label>/order.json`:
`{"order_number", "customer": {"name","email"}, "cdc_slot", "fraud_level",
"trackings": [{"shipment", "courier", "tracking_number"}]}` — the conductor
builds the CDC linking file and the final report from these.

Everything else — payload rules, `tracking.articles` mirroring, the driver,
timing, reporting, failure modes — is unchanged from the sections above.

Standalone behaviour (no manifest): everything above this section, unchanged.
```

- [ ] **Step 2: Verify additive + frontmatter intact** (same checks as Task 4 Step 2)

- [ ] **Step 3: Commit**

```bash
git add plugins/pl-tools/skills/order-lifecycle/SKILL.md
git commit -m "feat(order-lifecycle): orchestrated-runs contract for demo-environment"
```

---

### Task 8: Conductor skill part 1 — frontmatter, intake, manifest

**Files:**
- Create: `plugins/pl-tools/skills/demo-environment/SKILL.md` (frontmatter + sections up to and including "Phase 0")

**Interfaces:**
- Consumes: Task 2's validator CLI.
- Produces: the manifest schema exactly as Task 2's `valid_manifest()` fixture (same keys, same shapes) — later tasks and the four orchestrated contracts all read it.

- [ ] **Step 1: Create the skill file with frontmatter and Phase 0**

Frontmatter (the `name:` MUST equal the directory name; keep "parcelLab" in the description):

```markdown
---
name: demo-environment
description: Build a complete parcelLab customer demo environment from one intake interview — branded email template, 1–5 realistic orders with fraud-risk data walking through good and bad delivery journeys, optional Shopify dev-store build over the real parcelLab integration, and a CDC demo request linking the real orders. Trigger on phrases like "build a parcelLab demo environment for [brand]", "set up the full demo for [prospect]", "run the whole demo build", "prep the demo environment for [brand]". Orchestrates the branded-template, shopify-seed, order-lifecycle and demo-request skills; requires the parcellab CLI, the Browser pane, and (for Shopify opps) the Shopify CLI.
argument-hint: <prospect-url>
---
```

Then the body for Phase 0 (write it verbatim; the run-dir/manifest shapes must match Task 2's fixture exactly):

```markdown
# parcelLab — Unified Demo Environment Builder

One interview, one browser pass, one template checkpoint → a complete demo:
published branded layout, 1–5 fraud-tagged orders running their journeys,
(if Shopify) a seeded dev store with real orders on the real integration,
and one CDC demo request linking those orders.

Read `${CLAUDE_PLUGIN_ROOT}/skills/demo-environment/references/flows.md` if
you need the phase/gate picture; the four sub-skills' own SKILL.md files are
the single source of truth for their mechanics — this skill only prepares
their answers and sequences them (each has an "Orchestrated runs" section
defining its contract).

## Paths

Ask **"Are returns in scope for this demo?"** first.
- No → **engage** path.
- Yes → ask **"Is this a Shopify opp?"** → no → **retain** · yes →
  **retain-shopify**. An Engage-only run never asks the Shopify question;
  Retain covers the Engage story automatically.

## Phase 0 — Intake

1. **Create the run directory** `$HOME/parcellab-demo-runs/<handle>-<ts>/`
   (handle derived from the prospect URL exactly as shopify-seed Step 3
   derives `prospect_handle`; ts = YYYYMMDD-HHMM). Create `results/` and
   `orders/` inside it.
2. **Interview** (batch with AskUserQuestion where possible; one round for
   path + country + order count, a second for the order plan):
   - returns in scope? · Shopify opp? (per *Paths*)
   - destination country — **never assume it**
   - order plan: how many orders (1–5, default 3), and per order a fraud
     level + scenario. Offer the default matrix first: #1 low/happy,
     #2 medium/split (A happy, B stuck-delay), #3 high/recovered. On
     retain paths offer #4 manual_return and #5 return_tracking (both
     happy → Delivered). Scenario vocabulary: happy · stuck-delay ·
     recovered (`InTransit → WarehouseDelay → OutForDelivery → Delivered`,
     label: chain unproven) · locker (`… → Delivered-ParcelLocker`, label:
     status unproven) · custom (user-specified sequence, label per
     order-lifecycle's confidence rules). Runs of 2+ orders need at least
     one split-shipment order. Every order gets a distinct synthetic
     customer (region-appropriate name + email) — generate and show them.
   - CDC region (US|UK|DE) and category (Home|Electronics|Fashion) —
     inferred from the site later, confirmed at the approval gate.
3. **Shopify resolution (retain-shopify only):** confirm the dev store by
   name from `~/.claude/parcellab-shopify-seed.env` (else
   `shopify store auth list`), then resolve the location GID immediately —
   follow shopify-seed Steps 1–2 exactly, including the fulfils-online-orders
   preference rules. Record both in the manifest.
4. **Account confirmation (every run):** resolve
   `${PARCELLAB_ACCOUNT_ID:-$PARCELLAB_USER_ID}`; `parcellab account account
   show <id>` for the human name; ask "Using **<name>** (<id>) — correct?";
   verify `parcellab settings edit-mode show` says `account-restricted` for
   that same account, offering the fix if not. This single confirmation
   covers every parcelLab write in the run.
5. **CDC config:** read `CDC_ACCOUNT_CONFIG_SHOPIFY` /
   `CDC_ACCOUNT_CONFIG_STANDARD` (process env, then
   `~/.claude/parcellab-demo-request.env`). retain-shopify → the Shopify
   UUID; otherwise the standard one. Missing → `selected_account_config_id:
   null`, `config_source: "none"` (the CDC will use the caller's default —
   say so in the final report).
6. **One browser pass** (the run's only browsing):
   - Brand tokens: run branded-template's Step 3–6 extraction snippets
     (`${CLAUDE_PLUGIN_ROOT}/skills/branded-template/SKILL.md`) and build
     the full `__BRAND_X__` token map + logo + hero.
   - Product pool: collect ≥8 PDP candidates in the superset shape
     (`{id, name, product_type, price, options, image_url, pdp_url, sku}`)
     following `${CLAUDE_PLUGIN_ROOT}/skills/shopify-seed/references/product-scrape.md`
     — variant axes are required only on retain-shopify; elsewhere capture
     what the PDP shows without extra navigation.
   - Validate every candidate image:
     `node ${CLAUDE_PLUGIN_ROOT}/skills/demo-request/scripts/check_images.mjs`
     semantics (200 + image/*; ranged-GET retry). Mark `image_verified`.
7. **Propose the plan** and gate on approval (✋ — the intake's one gate):
   core 4 (four distinct product types) · per-order product distribution ·
   (retain-shopify) the seed set = core 4 + extras at distinct price points ·
   the order/scenario/fraud matrix with expected comm per event (mark
   unproven items) · CDC region/category/config source · the account by
   name. One explicit yes covers all of it; any tweak loops back here.
8. **Write the manifest** to `demo-manifest.json` (schema: `run`, `path`,
   `brand{name,url,handle,region,category}`, `account{id,name,confirmed_at,
   edit_mode_verified}`, `cdc{selected_account_config_id,config_source,
   generate_orders,order_types}`, `shopify{enabled,store?,location_id?}`,
   `destination_country`, `products[]`, `selection{core4,shopify_extra}`,
   `brand_tokens{tokens,logo,hero}`, `orders[]` with per-order
   `{label,dir,cdc_slot,fraud_level,customer{name,email},products,
   shipments[{label,scenario,courier,products,events,unproven_events?,
   unproven_chain?}]}`, `gates{order_lifecycle{gate_b_answered,gate_c,
   extras}}`, `approvals{products_approved_at,intake_completed_at}`).
   On retain-shopify also write `seed/seed-products.json`
   (`{products: core4 ∪ shopify_extra in scrape shape, location_id,
   prospect_handle}`).
9. **Validate:**
   `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/validate_manifest.py <run>/demo-manifest.json`
   — on `MANIFEST INVALID`, fix the named gaps (re-asking if needed) and
   re-validate. **Never start Phase 1 on an invalid manifest.**
```

- [ ] **Step 2: Create the flows reference stub**

Create `plugins/pl-tools/skills/demo-environment/references/flows.md` containing the phase/gate summary (copy the "Architecture — five phases" section headings + the paths table from the spec, condensed to ~40 lines — content, not a pointer to the spec, since installed users don't have the repo docs).

- [ ] **Step 3: Verify skill inventory safety**

```bash
grep -A1 "^name:" plugins/pl-tools/skills/demo-environment/SKILL.md | head -2
# name: demo-environment  ← must equal directory name
grep -c "parcelLab" plugins/pl-tools/skills/demo-environment/SKILL.md   # ≥ 1 in description
grep -n "~/.claude/skills" plugins/pl-tools/skills/demo-environment/SKILL.md; echo "exit=$? (expect 1 = no match)"
```

- [ ] **Step 4: Commit**

```bash
git add plugins/pl-tools/skills/demo-environment/
git commit -m "feat(demo-environment): conductor skill — intake and manifest (Phase 0)"
```

---

### Task 9: Conductor part 2 — Phase 1 (template ∥ seed agent) + Phase 2 direct engine

**Files:**
- Modify: `plugins/pl-tools/skills/demo-environment/SKILL.md` (append Phases 1–2)

**Interfaces:**
- Consumes: Task 5's `results/branded-template.json`, Task 6's agent contract + `results/shopify-seed.json`, Task 7's per-order contract, Task 1's fragment script.
- Produces: `results/linked-orders.json` (shape in *Shared interfaces*); the publish-gate behaviour Phase 2 Shopify (Task 10) also obeys.

- [ ] **Step 1: Append Phases 1–2 (direct engine)**

```markdown
## Phase 1 — Template ∥ seed

**Dispatch the seed agent first (retain-shopify only)**, so it runs while
you build the template. Use the Agent tool (general-purpose subagent,
background) with exactly this brief, filling the placeholders:

> Invoke the pl-tools:shopify-seed skill and execute its "Orchestrated runs
> (demo-environment)" contract for the run directory `<run dir>`. The
> manifest and `seed/seed-products.json` are already there. Ground rules,
> non-negotiable: never open the Browser pane; never ask the user anything —
> a gap is a failure report; write your outcome to
> `<run dir>/results/shopify-seed.json` exactly as the contract specifies,
> and return a one-paragraph summary plus the product/demo tables.

**Then run branded-template inline** (main session): invoke the
pl-tools:branded-template skill; its "Orchestrated runs (demo-environment)"
contract consumes the manifest's `brand_tokens` and account. Its Step 8
preview question is ★ the run's one checkpoint — wait for the user there as
that skill specifies. It finishes by writing
`results/branded-template.json`.

## The publish gate

Phase 2 must not start until `results/branded-template.json` shows
`"release_status": "published"` — order creation fires the
order-confirmation comm immediately on every path, and an unpublished
template means that first email goes out unbranded. If it says
`not published`, offer exactly three ways forward and wait:
1. fix and re-publish (follow branded-template Step 9a's failure table);
2. the user publishes manually in the portal, then confirms here;
3. explicitly proceed accepting unbranded comms (record the choice in the
   report).

**retain-shopify additionally waits for the seed**: `results/shopify-seed.json`
must show `"status": "ok"` before Shopify orders are created (their line
items reference seeded variants). A failed seed lane stops only the order
stage of the Shopify path: report it, offer to re-run the seed inline from
the same manifest (the fallback), and leave every other lane alone.

## Phase 2 — Orders (direct engine: engage and retain paths)

For each manifest order, in its `orders/<nn>-<label>/` directory, follow
order-lifecycle's "Orchestrated runs (demo-environment)" contract:

1. Fraud fragment: run `prepare_fraud_fragment.py` for the order's level and
   merge `tags` + `additional_attributes` into `create.json`.
2. Build `create.json` + the single PUT with all `add_tracking` mutations
   (order-lifecycle's payload rules verbatim: randomised format-correct
   tracking numbers, courier per shipment, `tracking.articles` mirrored,
   split rules for 2-shipment orders).
3. Write the `NN-<status>.json` event files from the shipment's `events`.
4. `DRYRUN=1` pass; then launch `run-lifecycle.sh` detached
   (`run_in_background`, `GAP_SECONDS` default 180) — one driver per order,
   all orders concurrent.
5. Write `order.json` per the contract.

When every order's `order.json` exists, build
`results/linked-orders.json`: every order with a non-null `cdc_slot` becomes
`{"order_number": <order.json order_number>, "order_type": <cdc_slot>}`.
An order whose creation failed is excluded (and reported); one order's
failure never stops another's driver.
```

- [ ] **Step 2: Verify the sub-skill references resolve**

```bash
grep -o 'pl-tools:[a-z-]*' plugins/pl-tools/skills/demo-environment/SKILL.md | sort -u
# expect exactly: pl-tools:branded-template, pl-tools:shopify-seed (order-lifecycle/demo-request appear in later tasks)
grep -n 'results/branded-template.json\|results/shopify-seed.json\|results/linked-orders.json' plugins/pl-tools/skills/demo-environment/SKILL.md
```

- [ ] **Step 3: Commit**

```bash
git add plugins/pl-tools/skills/demo-environment/SKILL.md
git commit -m "feat(demo-environment): Phase 1 concurrency, publish gate, direct order engine"
```

---

### Task 10: Conductor part 3 — Shopify order engine

**Files:**
- Create: `plugins/pl-tools/skills/demo-environment/references/shopify-order-engine.md`
- Modify: `plugins/pl-tools/skills/demo-environment/SKILL.md` (append the Phase 2 Shopify section)

**Interfaces:**
- Consumes: `results/shopify-seed.json` product/variant IDs; manifest orders; Task 1's fragment script; Task 7's `order.json` contract.
- Produces: the same `order.json` files and `results/linked-orders.json` entries as the direct engine, so Phase 3/4 are engine-agnostic.

- [ ] **Step 1: Write `references/shopify-order-engine.md`**

Include, in this order (all commands concrete):

1. **Scope check (once per run):** `shopify store auth list` output alone doesn't show scopes; attempt a cheap read of orders — `shopify store execute -s "$SHOPIFY_DEMO_STORE" --query '{ orders(first: 1) { nodes { id } } }'` — an access error means the store auth needs re-consenting: `shopify store auth -s <store> --scopes write_products,write_inventory,read_orders,write_orders,write_fulfillments` (browser consent window opens; warn the user). Record which scopes were actually needed as a finding for this reference.
2. **Create order — candidate mutation** (verify against the store's schema before first use: `shopify store execute -s "$SHOPIFY_DEMO_STORE" --query '{ __type(name: "Mutation") { fields { name } } }'` and check `orderCreate` exists; if it does not, fall back to `draftOrderCreate` → `draftOrderComplete` and record the substitution):

```graphql
mutation CreateDemoOrder($order: OrderCreateOrderInput!, $options: OrderCreateOptionsInput) {
  orderCreate(order: $order, options: $options) {
    order { id name email }
    userErrors { field message }
  }
}
```

with variables (one order):

```json
{
  "order": {
    "email": "<customer.email>",
    "lineItems": [{ "variantId": "<gid from results/shopify-seed.json>", "quantity": 1 }],
    "shippingAddress": { "firstName": "<first>", "lastName": "<last>",
      "address1": "<region-appropriate street>", "city": "<city>",
      "zip": "<zip>", "countryCode": "<GB|US|DE from destination_country>" },
    "financialStatus": "PAID"
  },
  "options": { "sendReceipt": false, "sendFulfillmentReceipt": false }
}
```

`--allow-mutations` required. Check `userErrors` on every call. Record `order.name` (e.g. `#1001`) — **this is the order_number pL will know**.
3. **Poll ingestion:** loop (up to 12 × 10s) on
   `parcellab api request GET "/v4/track/orders/info/?account=<account-id>&orderNo=<order.name>" -o json` (adjust the exact query params to whatever order-lifecycle's Reporting section uses for order-info lookups — keep them consistent); success = the order document exists. On timeout: report the order as not-ingested, skip its remaining steps, continue other orders.
4. **Enrich with fraud data:** `prepare_fraud_fragment.py --level <fraud_level> --shop-url "$SHOPIFY_DEMO_STORE"`, then
   `parcellab api request PUT /v4/track/orders/ --data @enrich.json -o json` where `enrich.json` = `{"account": <id>, "order_number": "<order.name>", "tags": [...], "additional_attributes": {...}}` (upsert semantics — verified in live test 3; if the PUT replaces rather than merges fields, capture the order's existing fields in the payload and record the finding here).
5. **Fulfil with tracking:** look up the fulfillment order, then fulfil per shipment:

```graphql
query GetFO($id: ID!) { order(id: $id) { fulfillmentOrders(first: 5) { nodes { id lineItems(first: 20) { nodes { id remainingQuantity } } } } } }
```

```graphql
mutation Fulfil($fulfillment: FulfillmentInput!) {
  fulfillmentCreate(fulfillment: $fulfillment) {
    fulfillment { id trackingInfo { number company } }
    userErrors { field message }
  }
}
```

variables: `{"fulfillment": {"lineItemsByFulfillmentOrder": [{"fulfillmentOrderId": "<gid>", "fulfillmentOrderLineItems": [{"id": "<gid>", "quantity": 1}]}], "trackingInfo": {"number": "<randomised, format-correct>", "company": "<carrier pL recognises — use the shipment's courier from the manifest, e.g. UPS/DPD>"}, "notifyCustomer": false}}` — for split orders, two fulfillmentCreate calls with distinct tracking numbers, splitting the line items per shipment. (Schema drift note: if `fulfillmentCreate` is absent, introspect for `fulfillmentCreateV2` and record the substitution.)
6. **Wait for the tracking in pL** (same polling pattern, now until the tracking with that number exists), then **push events** exactly as order-lifecycle's driver does — the `NN-<status>.json` files use the fulfilment's tracking number and the pL courier the integration mapped (read it from the order-info response, don't guess).

- [ ] **Step 2: Append the Phase 2 Shopify section to SKILL.md**

```markdown
## Phase 2 — Orders (Shopify engine: retain-shopify path)

Gate: publish gate passed AND `results/shopify-seed.json` status ok.
For each manifest order, in its `orders/<nn>-<label>/` directory, follow
`${CLAUDE_PLUGIN_ROOT}/skills/demo-environment/references/shopify-order-engine.md`:
create the order in Shopify (line items = the order's `products` mapped to
seeded variant gids) → poll pL ingestion → enrich with the fraud fragment →
fulfil per shipment with tracking → poll the pL tracking → build the
`NN-<status>.json` files and launch the driver, exactly as the direct
engine's steps 3–4. Then write `order.json` (order_number = the Shopify
order name, e.g. "#1001") and, once all orders are processed, build
`results/linked-orders.json` the same way as the direct engine.

Per-order failure isolation: ingestion timeout, enrichment failure or
fulfilment failure marks THAT order partial in `order.json`
(`"status": "partial", "failed_at": "<step>"`) — its events are not pushed,
other orders continue, and the report says exactly which step failed.
```

- [ ] **Step 3: Commit**

```bash
git add plugins/pl-tools/skills/demo-environment/
git commit -m "feat(demo-environment): Shopify order engine reference and Phase 2 wiring"
```

---

### Task 11: Conductor part 4 — Phase 3 CDC call, Phase 4 report, fallback rules

**Files:**
- Modify: `plugins/pl-tools/skills/demo-environment/SKILL.md` (append Phases 3–4 + failure handling)

**Interfaces:**
- Consumes: `results/linked-orders.json`, `results/*.json`, Task 4's demo-request contract, `orders/*/order.json`, `orders/*/run.log`.
- Produces: the finished skill.

- [ ] **Step 1: Append Phases 3–4 and the failure table**

```markdown
## Phase 3 — The one CDC call

Exactly one CDC interaction per run, after Phase 2 — with a `cdc_live_`
token, linking existing orders is only possible on the creation call.
Invoke the pl-tools:demo-request skill's "Orchestrated runs
(demo-environment)" contract against the run dir: it builds the payload
from the manifest + `results/linked-orders.json` and submits once. Do not
retry a 500 (the request already exists — the results file records it).

## Phase 4 — Report

**Beat 1 — environment built** (immediately after Phase 3): layout id +
release status + store assignment (+ any 9b country-override warning,
repeated verbatim) · per order: number, customer, fraud level, slot,
courier(s) + tracking number(s), scenario, and the expected comm per event
with confidence labels · (retain-shopify) the seed table + demos +
adjustments from `results/shopify-seed.json` · CDC request id/URL, which
orders were submitted for linking, and the config source (say "caller's
default config" when `config_source` is `none`). No currency symbols.

**Beat 2 — verified** (after each order's driver finishes AND ≥5 minutes
after its final event — comms lag, delivered comms the longest): per order,
public order-info lookup by courier + tracking_number; report checkpoints
attached vs planned and `contacted_with_messages` vs the expected comms —
explicitly covering the good AND bad arcs the run promised. For every
unproven event or chain that fired correctly, offer to record it in
`${CLAUDE_PLUGIN_ROOT}/skills/order-lifecycle/references/status-codes.md`.

## Failure handling

| Lane fails | Blocks | Response |
|---|---|---|
| seed agent | Shopify orders only | report, offer inline re-run from the same manifest |
| template publish | Phase 2 (all orders) | the three-way publish-gate offer |
| one order (any engine) | nothing else | mark partial in its order.json; report the exact step |
| CDC call | nothing | report; 500 = request exists, retry manually in-app |

Fallback rule (Approach B): any agent lane can be re-run inline in the main
session from the same manifest — the brief and the contract are identical.
Never silently continue past a failed lane; every lane ends in a results
file or a reported failure, and Beat 1 lists any lane still outstanding.
```

- [ ] **Step 2: Whole-skill consistency check**

```bash
F=plugins/pl-tools/skills/demo-environment/SKILL.md
grep -c '^## ' $F                                   # expect ~9 sections
grep -n 'results/' $F | grep -v 'results/branded-template.json\|results/shopify-seed.json\|results/demo-request.json\|results/linked-orders.json'  # expect no strays
grep -n '\${CLAUDE_PLUGIN_ROOT}' $F                  # every cross-file reference uses it
```

- [ ] **Step 3: Commit**

```bash
git add plugins/pl-tools/skills/demo-environment/SKILL.md
git commit -m "feat(demo-environment): CDC call, two-beat report, failure handling"
```

---

### Task 12: `/pl-setup` CDC config values + README rows

**Files:**
- Modify: `plugins/pl-tools/commands/pl-setup.md` (add one optional step)
- Modify: `README.md` and `plugins/pl-tools/README.md` (skill tables/lists)

**Interfaces:**
- Consumes: nothing.
- Produces: the env keys Task 8's Phase 0 step 5 reads.

- [ ] **Step 1: Add the optional CDC-config step to pl-setup.md**

Find the existing CDC credentials step (it sets `CDC_DEMO_API_TOKEN` / `CDC_DEMO_API_BASE_URL` in `~/.claude/parcellab-demo-request.env`) and append after it:

```markdown
### Optional: CDC account-config UUIDs (for demo-environment)

The `demo-environment` skill selects a CDC account configuration by path:
Shopify demos vs everything else. If the user has the UUIDs (visible in the
CDC UI when editing an account config — there is no API to list them), append
to `~/.claude/parcellab-demo-request.env`:

    CDC_ACCOUNT_CONFIG_SHOPIFY=<uuid>
    CDC_ACCOUNT_CONFIG_STANDARD=<uuid>

Both optional. Missing values are fine — the CDC then uses the caller's
default config and demo-environment says so in its report. Never ask for
these in chat as pasted secrets — they are ids, not credentials, but still
belong in the env file, not the transcript.
```

- [ ] **Step 2: Add the README rows**

In `README.md` and `plugins/pl-tools/README.md`, find the skills list/table and add (matching each file's existing format):

> `demo-environment` — one interview → a full parcelLab demo: branded template, 1–5 fraud-tagged orders with good/bad journeys, optional Shopify build, CDC request linking the real orders.

- [ ] **Step 3: Verify + commit**

```bash
grep -rn "demo-environment" README.md plugins/pl-tools/README.md plugins/pl-tools/commands/pl-setup.md
git add README.md plugins/pl-tools/README.md plugins/pl-tools/commands/pl-setup.md
git commit -m "docs: register demo-environment skill; optional CDC config UUIDs in pl-setup"
```

---

### Task 13: Staged live verification (interactive — run with Jamie, not a subagent)

**Files:**
- Modify (findings only): `plugins/pl-tools/skills/order-lifecycle/references/status-codes.md`, `plugins/pl-tools/skills/demo-environment/references/shopify-order-engine.md`

**Interfaces:**
- Consumes: everything.
- Produces: proven/unproven status updates; corrections to the Shopify engine reference from reality.

This task requires Jamie present (account confirmation, template checkpoint, and judgment calls). It is three runs, in order, each gated on the previous one passing. After each run, fix what reality disagrees with, commit the fix, and re-run only the failed stage.

- [ ] **Run 1 — engage path, 1 order, happy:** invoke the skill with a real brand URL on account 1626718. Pass = template published + assigned; order created with fraud tags visible in app; all three comms verified in Beat 2; CDC request created with the order linked in `fraud_low`.
- [ ] **Run 2 — retain path (non-Shopify), default 3:** pass = all three arcs verified (clean comms, delay comm on the stuck shipment, delay + recovery comms on order 3). Record the `recovered` chain result in `status-codes.md` (proven, or what actually happened).
- [ ] **Run 3 — retain-shopify, default 3 + slots 4–5:** pass = seed verified; three Shopify orders synced into pL with fraud enrichment visible; fulfilments created pL trackings; events fired comms; returns portal can open order 4; CDC request links all five slots. Correct `shopify-order-engine.md` wherever introspection or reality differed (scopes, mutation names, enrichment merge semantics, courier mapping) and record the actual values.
- [ ] **Close out:** update the spec's Open items section with what was resolved; commit; push the branch; hand off to `superpowers:finishing-a-development-branch`.

---

## Self-Review (performed while writing)

1. **Spec coverage:** paths/intake → T8; browser pass → T8; manifest+validator → T2/T8; template lane + checkpoint + publish gate → T5/T9; seed agent → T6/T9; direct engine + fraud-in-payload → T1/T7/T9; Shopify engine + enrichment → T10; one CDC call + linked_orders → T3/T4/T11; two-beat report → T11; failure/fallback table → T11; pl-setup + READMEs → T12; staged live tests → T13. Gap check: agent ground rules appear in both the brief (T9) and the seed contract (T6) — intentional duplication, briefs must stand alone.
2. **Placeholder scan:** the two Shopify GraphQL mutations are explicitly marked *candidate + introspect-verify + record substitution* — that is a designed verification step (schema versions drift per store), not a TBD. No other "later/TBD/appropriate" language present.
3. **Type consistency:** manifest keys in T2's fixture match T8's schema list and T4–T7's contract references (`selection.core4`, `brand_tokens.tokens`, `orders[].cdc_slot`, `shipments[].unproven_events`); results filenames are identical across T4/T5/T6/T9/T10/T11; the fragment CLI (`--level/--shop-url/--source/--now`) matches between T1 and T7/T10.
