# demo-environment Unified Intake + Progress UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace demo-environment's broken Artifact-based intake questionnaire and its separate progress-tracking Artifact with one local HTTP server serving a single page that has two phases (Intake → Building/Live).

**Architecture:** A stdlib `http.server` subclass (`run_server.py`) serves one static HTML page (`run_app_template.html`) with parcelLab brand tokens substituted in at request time, plus two JSON endpoints: `POST /submit` writes validated intake answers to `<run dir>/intake.json`, and `GET /state` returns run-state plus per-lane drill-down detail assembled from the run dir's existing files. The page switches phases client-side and polls `/state` while the run is building. The conductor waits for `<run dir>/intake.json` to appear on disk — the file *is* the submitted flag, so no HTTP client is needed conductor-side.

**Tech Stack:** Python 3 stdlib only (`http.server`, `json`, `pathlib`) — no new dependencies, no pip installs. Vanilla HTML/CSS/JS with Tailwind via CDN (no React, no build step — explicit user decision). Tests are stdlib `unittest`.

**Spec:** `docs/superpowers/specs/2026-08-19-demo-environment-unified-intake-progress-design.md`

## Global Constraints

- **Tests are stdlib `unittest` only.** `pytest` is not installed. Never `pip install`. Run tests with: `cd plugins/pl-tools/scripts && python3 -m unittest discover -s tests -v`
- **No new runtime dependency.** Python stdlib only, server-side.
- **No React and no build step.** Vanilla JS + Tailwind CDN, per explicit user decision recorded in the spec.
- **Reuse `plugins/pl-tools/scripts/pl_brand.py` verbatim.** It already exists and needs no rework: `PRIMARY` = `#3E39D3`, `TEXT` = `#1A1A1A`, `TINT` = `#F1F1FC`, `CARD` = `#F5F5F5`, `FONT_FAMILY` = `'Poppins', system-ui, sans-serif`, plus `GOOGLE_FONTS_LINK` and `LOGO_SVG`.
- **Reference files via `${CLAUDE_PLUGIN_ROOT}` in all SKILL.md docs.** Never `~/.claude/skills/…`, never a repo-relative path. Installed users run from `~/.claude/plugins/cache/parcellab-skills/pl-tools/<version>/`.
- **Do not resurrect the Artifact transport** from the superseded spec at `docs/superpowers/specs/2026-08-19-demo-environment-intake-questionnaire-design.md`.
- **Never prefix new skill directories with `pl-`** (not applicable here — no new skills — but no filename should imply one).
- **Branch:** work continues on `wip/demo-environment-questionnaire-artifact`, already checked out. Do not commit to `main`.

### Vocabularies fixed by existing validators — do not widen

These are enforced by `validate_manifest.py` and `resolve_auto_defaults.py`. Any form value outside them produces a manifest the validator rejects.

- `brand.region` / `destination_country`: **`US`, `UK`, `DE` only.** `validate_manifest.BRAND_REGIONS` is `{"US", "UK", "DE"}` and `resolve_auto_defaults.infer_country` only ever returns one of those three.
- Courier defaults per region, from `create-order`'s documented *Defaults & dummy data* table: `DE` → `dhl-germany`, `UK` → `royal-mail`, `US` → `usps`.
- Fraud levels: `low`, `medium`, `high`.
- Scenarios: `happy`, `stuck-delay`, `recovered`, `locker`, `manual_return`, `return_tracking`, `custom`.
- Modes: `babysit`, `auto`.
- Gate C: `send-as-is`, `extras`.
- Weight units: `kg`, `g`, `lbs`, `oz`.

### Two deliberate deviations from the approved mockups

Both mockups are UX proofs, not production code. Two of their values are wrong against the real system and must **not** be copied:

1. **Region options.** `intake-mockup-v5.html` offers Spain/GB/Germany/France/US with couriers `correos-es`/`dpd-uk`/`dhl-de`/`colissimo-fr`/`ups`. Those region codes and courier codes are invented. Use `US`/`UK`/`DE` with `usps`/`royal-mail`/`dhl-germany` as above.
2. **`split` is not a scenario value.** The old `render_intake_questionnaire.py` had `"split"` inside its `SCENARIOS` set. In the new schema `split` is a per-order boolean that forks the order into two parcels, each carrying its own scenario from the list above.

---

## File Structure

**Created:**

- `plugins/pl-tools/scripts/intake_schema.py` — intake vocabularies, form defaults, region→courier map, and `parse_answers()`. Pure functions, no I/O. One responsibility: what a valid intake answer set is.
- `plugins/pl-tools/scripts/state_payload.py` — assembles the `GET /state` JSON from a run dir's existing files (`run-state.json`, `demo-manifest.json`, `scrape/assets.json`, `results/shopify-seed.json`). One responsibility: turning on-disk run artifacts into the page's data contract.
- `plugins/pl-tools/scripts/run_app_template.html` — the single-page app: both phases, shared step indicator, all CSS and JS inline. Contains `{{BRAND_*}}` / `{{CONTEXT_JSON}}` placeholder markers.
- `plugins/pl-tools/scripts/run_server.py` — the HTTP server: routing, page rendering (template + brand tokens + baked-in context), and wiring to the two modules above.
- `plugins/pl-tools/scripts/tests/test_intake_schema.py`
- `plugins/pl-tools/scripts/tests/test_state_payload.py`
- `plugins/pl-tools/scripts/tests/test_run_server.py`

**Modified:**

- `plugins/pl-tools/skills/demo-environment/SKILL.md` — the "Intake questionnaire", "The run page", and Phase 0 steps 1–2 sections, plus every `render_run_page.py` / republish reference throughout.
- `plugins/pl-tools/skills/demo-environment/references/intake-script.md` — documents the new field set.

**Deleted:**

- `plugins/pl-tools/scripts/render_intake_questionnaire.py` and `plugins/pl-tools/scripts/tests/test_render_intake_questionnaire.py`
- `plugins/pl-tools/scripts/render_run_page.py` and `plugins/pl-tools/scripts/tests/test_render_run_page.py`
- `plugins/pl-tools/skills/demo-environment/references/run-page.md`

**Deliberately untouched:**

- `plugins/pl-tools/scripts/pl_brand.py` — reused as-is.
- `plugins/pl-tools/scripts/run_state.py` — still the single source of truth for run state; `record_render`/`record_publish` stay in place (unused) so `build_telemetry_row.py` keeps working. It already tolerates empty lists via `page.get("renders") or []`.
- `plugins/pl-tools/scripts/inline_assets.py` — still needed; the page reads `scrape/assets.json` for product images.

---

### Task 1: Intake answer schema

**Files:**
- Create: `plugins/pl-tools/scripts/intake_schema.py`
- Test: `plugins/pl-tools/scripts/tests/test_intake_schema.py`

**Interfaces:**
- Consumes: nothing (first task).
- Produces:
  - `REGIONS = ("US", "UK", "DE")`
  - `REGION_COURIERS = {"US": "usps", "UK": "royal-mail", "DE": "dhl-germany"}`
  - `FRAUD_LEVELS`, `SCENARIOS`, `MODES`, `GATE_C_VALUES`, `WEIGHT_UNITS`, `EXTRA_KEYS` (all frozensets/tuples of str)
  - `default_answers(region="US") -> dict` — the form's pre-fill
  - `parse_answers(raw_json: str) -> dict` — raises `ValueError` with a specific reason; returns the normalised answer dict

- [ ] **Step 1: Write the failing test**

Create `plugins/pl-tools/scripts/tests/test_intake_schema.py`:

```python
"""Unit tests for intake_schema. Stdlib unittest — no pytest."""
import json
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import intake_schema  # noqa: E402


def _valid():
    return {
        "shopify_opp": True,
        "reuse_pool": None,
        "region": "DE",
        "courier": "dhl-germany",
        "orders": [
            {"label": "#1", "fraud": "low", "split": False,
             "scenario": "happy", "courier": None},
            {"label": "#2", "fraud": "medium", "split": True,
             "parcels": [
                 {"label": "A", "scenario": "happy", "courier": None},
                 {"label": "B", "scenario": "stuck-delay", "courier": "ups"},
             ]},
        ],
        "gate_c": "send-as-is",
        "extras": {},
        "mode": "babysit",
    }


class TestVocabularies(unittest.TestCase):
    def test_regions_match_validate_manifest(self):
        self.assertEqual(tuple(intake_schema.REGIONS), ("US", "UK", "DE"))

    def test_every_region_has_a_courier_default(self):
        for region in intake_schema.REGIONS:
            self.assertIn(region, intake_schema.REGION_COURIERS)

    def test_split_is_not_a_scenario(self):
        self.assertNotIn("split", intake_schema.SCENARIOS)

    def test_scenario_vocabulary_is_the_documented_one(self):
        self.assertEqual(
            set(intake_schema.SCENARIOS),
            {"happy", "stuck-delay", "recovered", "locker",
             "manual_return", "return_tracking", "custom"})


class TestDefaultAnswers(unittest.TestCase):
    def test_defaults_parse_clean(self):
        defaults = intake_schema.default_answers(region="UK")
        parsed = intake_schema.parse_answers(json.dumps(defaults))
        self.assertEqual(parsed["region"], "UK")
        self.assertEqual(parsed["courier"], "royal-mail")

    def test_defaults_include_a_split_order_when_multiple(self):
        defaults = intake_schema.default_answers()
        self.assertGreaterEqual(len(defaults["orders"]), 2)
        self.assertTrue(any(o["split"] for o in defaults["orders"]))


class TestParseAnswers(unittest.TestCase):
    def test_valid_payload_round_trips(self):
        parsed = intake_schema.parse_answers(json.dumps(_valid()))
        self.assertTrue(parsed["shopify_opp"])
        self.assertEqual(len(parsed["orders"]), 2)
        self.assertEqual(parsed["orders"][1]["parcels"][1]["scenario"],
                         "stuck-delay")

    def test_rejects_malformed_json(self):
        with self.assertRaisesRegex(ValueError, "not valid JSON"):
            intake_schema.parse_answers("{nope")

    def test_rejects_unknown_region(self):
        payload = _valid()
        payload["region"] = "ES"
        with self.assertRaisesRegex(ValueError, "region"):
            intake_schema.parse_answers(json.dumps(payload))

    def test_rejects_split_used_as_a_scenario(self):
        payload = _valid()
        payload["orders"][0]["scenario"] = "split"
        with self.assertRaisesRegex(ValueError, "scenario"):
            intake_schema.parse_answers(json.dumps(payload))

    def test_rejects_zero_orders(self):
        payload = _valid()
        payload["orders"] = []
        with self.assertRaisesRegex(ValueError, "between 1 and 5"):
            intake_schema.parse_answers(json.dumps(payload))

    def test_rejects_more_than_five_orders(self):
        payload = _valid()
        one = {"label": "#x", "fraud": "low", "split": False,
               "scenario": "happy", "courier": None}
        payload["orders"] = [dict(one, label=f"#{i}") for i in range(6)]
        with self.assertRaisesRegex(ValueError, "between 1 and 5"):
            intake_schema.parse_answers(json.dumps(payload))

    def test_rejects_duplicate_order_labels(self):
        payload = _valid()
        payload["orders"][1]["label"] = "#1"
        with self.assertRaisesRegex(ValueError, "duplicate"):
            intake_schema.parse_answers(json.dumps(payload))

    def test_split_order_requires_exactly_two_parcels(self):
        payload = _valid()
        payload["orders"][1]["parcels"] = [
            {"label": "A", "scenario": "happy", "courier": None}]
        with self.assertRaisesRegex(ValueError, "two parcels"):
            intake_schema.parse_answers(json.dumps(payload))

    def test_multi_order_run_needs_at_least_one_split(self):
        payload = _valid()
        payload["orders"][1] = {"label": "#2", "fraud": "medium",
                                "split": False, "scenario": "happy",
                                "courier": None}
        with self.assertRaisesRegex(ValueError, "at least one split"):
            intake_schema.parse_answers(json.dumps(payload))

    def test_single_order_run_needs_no_split(self):
        payload = _valid()
        payload["orders"] = [payload["orders"][0]]
        parsed = intake_schema.parse_answers(json.dumps(payload))
        self.assertEqual(len(parsed["orders"]), 1)

    def test_send_as_is_rejects_populated_extras(self):
        payload = _valid()
        payload["extras"] = {"announced_delivery_date": "2026-09-01"}
        with self.assertRaisesRegex(ValueError, "send-as-is"):
            intake_schema.parse_answers(json.dumps(payload))

    def test_extras_gate_rejects_empty_extras(self):
        payload = _valid()
        payload["gate_c"] = "extras"
        with self.assertRaisesRegex(ValueError, "empty"):
            intake_schema.parse_answers(json.dumps(payload))

    def test_extras_rejects_unknown_key(self):
        payload = _valid()
        payload["gate_c"] = "extras"
        payload["extras"] = {"teleportation": True}
        with self.assertRaisesRegex(ValueError, "unknown extras"):
            intake_schema.parse_answers(json.dumps(payload))

    def test_promise_date_must_be_plain_date(self):
        payload = _valid()
        payload["gate_c"] = "extras"
        payload["extras"] = {"announced_delivery_date": "2026-09-01T10:00:00Z"}
        with self.assertRaisesRegex(ValueError, "YYYY-MM-DD"):
            intake_schema.parse_answers(json.dumps(payload))

    def test_weight_unit_must_be_known(self):
        payload = _valid()
        payload["gate_c"] = "extras"
        payload["extras"] = {"article_weights": {"SKU1": {"weight": 300,
                                                          "weight_unit": "stone"}}}
        with self.assertRaisesRegex(ValueError, "weight_unit"):
            intake_schema.parse_answers(json.dumps(payload))

    def test_rejects_unknown_mode(self):
        payload = _valid()
        payload["mode"] = "yolo"
        with self.assertRaisesRegex(ValueError, "mode"):
            intake_schema.parse_answers(json.dumps(payload))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd plugins/pl-tools/scripts && python3 -m unittest tests.test_intake_schema -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'intake_schema'`

- [ ] **Step 3: Write the implementation**

Create `plugins/pl-tools/scripts/intake_schema.py`:

```python
"""What a valid demo-environment intake answer set is.

Pure functions only — no I/O, no HTTP — so the server, the tests and any
future CLI all agree on one definition. Every vocabulary here is pinned to
what `validate_manifest.py` already accepts: widening one of these sets
without widening the validator produces a manifest that fails at Phase 1,
after the operator has already answered everything.
"""
import json
import re

# validate_manifest.BRAND_REGIONS is exactly these three, and
# resolve_auto_defaults.infer_country only ever returns one of them.
REGIONS = ("US", "UK", "DE")

# Couriers from create-order's "Defaults & dummy data" table, which is the
# only place in this repo that documents a real courier code per country.
REGION_COURIERS = {"US": "usps", "UK": "royal-mail", "DE": "dhl-germany"}

FRAUD_LEVELS = frozenset({"low", "medium", "high"})

# `split` is deliberately absent: a split is a per-order boolean that forks
# the order into two parcels, each with its own scenario from this set.
SCENARIOS = frozenset({
    "happy", "stuck-delay", "recovered", "locker",
    "manual_return", "return_tracking", "custom",
})

MODES = frozenset({"babysit", "auto"})
GATE_C_VALUES = frozenset({"send-as-is", "extras"})
WEIGHT_UNITS = frozenset({"kg", "g", "lbs", "oz"})

PROMISE_DATE_FIELDS = ("announced_delivery_date",
                       "announced_delivery_date_min",
                       "announced_delivery_date_max")

# The Gate C menu order-lifecycle documents, plus article_weights, which is
# a synthetic container rather than an Order API field name.
EXTRA_KEYS = frozenset(set(PROMISE_DATE_FIELDS) | {
    "additional_recipients", "tax_amount", "net_amount", "discount_amount",
    "extra_articles", "tags", "additional_attributes",
    "delivery_method", "courier_service_level", "signature_required",
    "article_weights",
})

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

MAX_ORDERS = 5


def default_answers(region="US"):
    """The form's pre-fill: three orders, fraud varied, #2 split.

    Mirrors intake-script.md's documented default matrix, trimmed to three
    rows because the two return-flow rows depend on the retain path being
    chosen, which this form asks about in the same submission.
    """
    if region not in REGIONS:
        region = "US"
    return {
        "shopify_opp": False,
        "reuse_pool": None,
        "region": region,
        "courier": REGION_COURIERS[region],
        "orders": [
            {"label": "#1", "fraud": "low", "split": False,
             "scenario": "happy", "courier": None},
            {"label": "#2", "fraud": "medium", "split": True,
             "parcels": [
                 {"label": "A", "scenario": "happy", "courier": None},
                 {"label": "B", "scenario": "stuck-delay", "courier": None},
             ]},
            {"label": "#3", "fraud": "high", "split": False,
             "scenario": "recovered", "courier": None},
        ],
        "gate_c": "send-as-is",
        "extras": {},
        "mode": "babysit",
    }


def _check_parcel(parcel, where):
    if not isinstance(parcel, dict):
        raise ValueError(f"{where}: parcel must be an object")
    if not parcel.get("label"):
        raise ValueError(f"{where}: parcel is missing a label")
    if parcel.get("scenario") not in SCENARIOS:
        raise ValueError(
            f"{where}: parcel {parcel['label']} has an invalid scenario "
            f"{parcel.get('scenario')!r}; expected one of {sorted(SCENARIOS)}")
    courier = parcel.get("courier")
    if courier is not None and not isinstance(courier, str):
        raise ValueError(f"{where}: parcel courier must be a string or null")


def _check_order(order, where):
    if not isinstance(order, dict):
        raise ValueError(f"{where}: order must be an object")
    if not order.get("label"):
        raise ValueError(f"{where}: order is missing a label")
    if order.get("fraud") not in FRAUD_LEVELS:
        raise ValueError(
            f"{where}: invalid fraud level {order.get('fraud')!r}; "
            f"expected one of {sorted(FRAUD_LEVELS)}")
    if not isinstance(order.get("split"), bool):
        raise ValueError(f"{where}: split must be true or false")

    if order["split"]:
        parcels = order.get("parcels")
        if not isinstance(parcels, list) or len(parcels) != 2:
            raise ValueError(
                f"{where}: a split order needs exactly two parcels")
        for parcel in parcels:
            _check_parcel(parcel, where)
    else:
        if order.get("scenario") not in SCENARIOS:
            raise ValueError(
                f"{where}: invalid scenario {order.get('scenario')!r}; "
                f"expected one of {sorted(SCENARIOS)}")
        courier = order.get("courier")
        if courier is not None and not isinstance(courier, str):
            raise ValueError(f"{where}: courier must be a string or null")


def _check_extras(extras, gate_c):
    if not isinstance(extras, dict):
        raise ValueError("extras must be an object")

    if gate_c == "send-as-is" and extras:
        raise ValueError("gate_c is 'send-as-is' but extras carries fields")
    if gate_c == "extras" and not extras:
        raise ValueError("gate_c is 'extras' but extras is empty")

    unknown = sorted(set(extras) - EXTRA_KEYS)
    if unknown:
        raise ValueError(f"unknown extras key(s): {unknown}")

    for field in PROMISE_DATE_FIELDS:
        value = extras.get(field)
        if value is not None and not _DATE_RE.match(str(value)):
            raise ValueError(
                f"extras.{field} must be YYYY-MM-DD, not a full ISO "
                f"datetime (got {value!r})")

    weights = extras.get("article_weights") or {}
    if not isinstance(weights, dict):
        raise ValueError("extras.article_weights must be an object keyed by "
                         "product id")
    for pid, entry in weights.items():
        if not isinstance(entry, dict):
            raise ValueError(
                f"extras.article_weights[{pid}] must be an object")
        weight = entry.get("weight")
        if not isinstance(weight, (int, float)) or isinstance(weight, bool) \
                or weight <= 0:
            raise ValueError(
                f"extras.article_weights[{pid}].weight must be a positive "
                f"number (got {weight!r})")
        if entry.get("weight_unit") not in WEIGHT_UNITS:
            raise ValueError(
                f"extras.article_weights[{pid}].weight_unit must be one of "
                f"{sorted(WEIGHT_UNITS)} (got {entry.get('weight_unit')!r})")


def parse_answers(raw_json):
    """Validate and normalise a submitted answer set.

    Raises ValueError with one specific reason. The server turns that reason
    into a 400 the page shows inline, so the operator fixes it on the same
    form rather than falling through to a chat interview.
    """
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise ValueError(f"not valid JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError("answers must be a JSON object")

    required = {"shopify_opp", "reuse_pool", "region", "courier",
                "orders", "gate_c", "extras", "mode"}
    missing = sorted(required - set(data))
    if missing:
        raise ValueError(f"missing field(s): {missing}")

    if not isinstance(data["shopify_opp"], bool):
        raise ValueError("shopify_opp must be true or false")

    if data["reuse_pool"] is not None \
            and not isinstance(data["reuse_pool"], bool):
        raise ValueError("reuse_pool must be true, false, or null")

    if data["region"] not in REGIONS:
        raise ValueError(
            f"region must be one of {list(REGIONS)} (got {data['region']!r}) "
            f"— validate_manifest.py accepts no others")

    if not data["courier"] or not isinstance(data["courier"], str):
        raise ValueError("courier must be a non-empty string")

    if data["mode"] not in MODES:
        raise ValueError(f"mode must be one of {sorted(MODES)}")

    if data["gate_c"] not in GATE_C_VALUES:
        raise ValueError(f"gate_c must be one of {sorted(GATE_C_VALUES)}")

    orders = data["orders"]
    if not isinstance(orders, list) or not 1 <= len(orders) <= MAX_ORDERS:
        raise ValueError(
            f"orders must contain between 1 and {MAX_ORDERS} entries")

    seen = set()
    for index, order in enumerate(orders):
        where = f"order {index + 1}"
        _check_order(order, where)
        if order["label"] in seen:
            raise ValueError(f"{where}: duplicate order label "
                             f"{order['label']!r}")
        seen.add(order["label"])

    # Same rule validate_manifest.py enforces on the manifest, checked here
    # so the operator hears it on the form instead of at Phase 1.
    if len(orders) >= 2 and not any(o["split"] for o in orders):
        raise ValueError("runs of 2+ orders need at least one split order")

    _check_extras(data["extras"], data["gate_c"])

    return {
        "shopify_opp": data["shopify_opp"],
        "reuse_pool": data["reuse_pool"],
        "region": data["region"],
        "courier": data["courier"],
        "orders": orders,
        "gate_c": data["gate_c"],
        "extras": data["extras"],
        "mode": data["mode"],
    }
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd plugins/pl-tools/scripts && python3 -m unittest tests.test_intake_schema -v`
Expected: PASS, all tests.

- [ ] **Step 5: Run the whole suite to confirm nothing regressed**

Run: `cd plugins/pl-tools/scripts && python3 -m unittest discover -s tests -v`
Expected: PASS (the old `test_render_intake_questionnaire.py` still passes — it is deleted in Task 7).

- [ ] **Step 6: Commit**

```bash
git add plugins/pl-tools/scripts/intake_schema.py plugins/pl-tools/scripts/tests/test_intake_schema.py
git commit -m "feat(demo-environment): add intake answer schema for the unified form"
```

---

### Task 2: State payload assembly

**Files:**
- Create: `plugins/pl-tools/scripts/state_payload.py`
- Test: `plugins/pl-tools/scripts/tests/test_state_payload.py`

**Interfaces:**
- Consumes: `run_state.load()` (existing), `intake_schema` (not needed here).
- Produces: `build(run_dir) -> dict` with keys `phase`, `run_id`, `account_name`, `path`, `finished`, `updated_at`, `lanes`, `orders`, `schedule`, `failures`, `detail`. `detail` has sub-keys `scrape`, `template`, `seed`, `cdc`, each either `None` or a dict. Consumed by `run_server.py` (Task 3) and rendered by the page's JS (Task 5).

- [ ] **Step 1: Write the failing test**

Create `plugins/pl-tools/scripts/tests/test_state_payload.py`:

```python
"""Unit tests for state_payload. Stdlib unittest — no pytest."""
import json
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import run_state  # noqa: E402
import state_payload  # noqa: E402


class TestStatePayload(unittest.TestCase):
    def setUp(self):
        self.dir = pathlib.Path(tempfile.mkdtemp())
        (self.dir / "scrape").mkdir()
        (self.dir / "results").mkdir()
        run_state.init(str(self.dir), "pccomponentes-20260819-1546",
                       "retain-shopify", "Demo - JLS")

    def test_phase_is_intake_until_intake_json_exists(self):
        self.assertEqual(state_payload.build(self.dir)["phase"], "intake")

    def test_phase_is_building_once_intake_json_exists(self):
        (self.dir / "intake.json").write_text("{}")
        self.assertEqual(state_payload.build(self.dir)["phase"], "building")

    def test_carries_run_state_basics(self):
        payload = state_payload.build(self.dir)
        self.assertEqual(payload["run_id"], "pccomponentes-20260819-1546")
        self.assertEqual(payload["account_name"], "Demo - JLS")
        self.assertEqual(payload["path"], "retain-shopify")
        self.assertFalse(payload["finished"])
        self.assertEqual(payload["lanes"]["scrape"]["status"], "pending")

    def test_detail_keys_are_present_even_when_empty(self):
        detail = state_payload.build(self.dir)["detail"]
        for key in ("scrape", "template", "seed", "cdc"):
            self.assertIn(key, detail)

    def test_scrape_detail_comes_from_assets(self):
        (self.dir / "scrape" / "assets.json").write_text(json.dumps({
            "tokens": {"primary": "#e2001a", "text": "#1a1a1a",
                       "font": "Inter"},
            "logo_data_uri": "data:image/svg+xml;base64,AAA",
            "products": {
                "SKU1": {"name": "RTX 4070", "product_type": "graphics card",
                         "price": "649.00", "data_uri": "data:image/png;base64,BBB"},
            },
        }))
        scrape = state_payload.build(self.dir)["detail"]["scrape"]
        self.assertEqual(scrape["swatches"], ["#e2001a", "#1a1a1a"])
        self.assertEqual(scrape["logo"], "data:image/svg+xml;base64,AAA")
        self.assertEqual(len(scrape["products"]), 1)
        self.assertEqual(scrape["products"][0]["name"], "RTX 4070")

    def test_scrape_detail_skips_non_colour_tokens(self):
        (self.dir / "scrape" / "assets.json").write_text(json.dumps({
            "tokens": {"font": "Inter", "primary": "#abc"}, "products": {}}))
        scrape = state_payload.build(self.dir)["detail"]["scrape"]
        self.assertEqual(scrape["swatches"], ["#abc"])

    def test_seed_detail_carries_products_and_demos(self):
        (self.dir / "results" / "shopify-seed.json").write_text(json.dumps({
            "status": "ok",
            "products": [{"title": "RTX 4070", "seeded_price": "299.00",
                          "adjusted": True,
                          "variants": [{"id": "gid://1"}, {"id": "gid://2"}]}],
            "demos": {"in_product_even": {"product": "RTX 4070",
                                          "option": "Memory",
                                          "swap": "12GB → 16GB"},
                      "cross_product_even": ["Mouse", "RAM"],
                      "uneven_upward": {"from": "Mouse", "to": "RTX 4070",
                                        "balance": "170.00"},
                      "uneven_downward": None},
            "warnings": [],
            "error": None,
        }))
        seed = state_payload.build(self.dir)["detail"]["seed"]
        self.assertEqual(seed["status"], "ok")
        self.assertEqual(seed["products"][0]["variant_count"], 2)
        self.assertEqual(seed["demos"]["cross_product_even"], ["Mouse", "RAM"])

    def test_cdc_detail_reports_generate_orders_from_manifest(self):
        (self.dir / "demo-manifest.json").write_text(json.dumps({
            "cdc": {"generate_orders": False, "orders": []}}))
        cdc = state_payload.build(self.dir)["detail"]["cdc"]
        self.assertFalse(cdc["generate_orders"])

    def test_template_detail_reports_path_and_lane_status(self):
        run_state.set_lane(str(self.dir), "template", "published",
                           layout_id=20701)
        template = state_payload.build(self.dir)["detail"]["template"]
        self.assertEqual(template["status"], "published")
        self.assertEqual(template["layout_id"], 20701)
        self.assertEqual(template["path"], "retain-shopify")

    def test_orders_carry_shipment_progress(self):
        run_state.add_order(str(self.dir), "01-fraud-low", "pl-1041", [
            {"label": "A", "tracking_number": "TN1", "courier": "dhl-germany",
             "planned": ["InTransit", "Delivered"]}])
        run_state.confirm_event(str(self.dir), "TN1", "InTransit",
                                "2026-08-19T15:31:05Z", 204)
        orders = state_payload.build(self.dir)["orders"]
        self.assertEqual(orders[0]["order_number"], "pl-1041")
        self.assertEqual(orders[0]["shipments"][0]["confirmed"][0]["status"],
                         "InTransit")

    def test_malformed_side_file_does_not_break_the_payload(self):
        (self.dir / "scrape" / "assets.json").write_text("{ broken")
        payload = state_payload.build(self.dir)
        self.assertIsNone(payload["detail"]["scrape"])
        self.assertEqual(payload["run_id"], "pccomponentes-20260819-1546")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd plugins/pl-tools/scripts && python3 -m unittest tests.test_state_payload -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'state_payload'`

- [ ] **Step 3: Write the implementation**

Create `plugins/pl-tools/scripts/state_payload.py`:

```python
"""Assemble the GET /state payload the run page renders itself from.

Everything here is derived from files the run already writes — run-state.json
is the source of truth for progress, and the per-lane drill-down detail comes
from the same side files the old run-page renderer read. Nothing writes.

Every side file is read defensively: a half-written or missing file leaves its
detail section None rather than failing the whole poll, because the page
polling every two seconds will inevitably catch a write mid-flight.
"""
import json
import pathlib

import run_state


def _read_json(path):
    """None on anything unreadable — a poll must never fail on a side file."""
    try:
        return json.loads(pathlib.Path(path).read_text())
    except (OSError, ValueError):
        return None


def _scrape_detail(run_dir):
    assets = _read_json(run_dir / "scrape" / "assets.json")
    if not assets:
        return None
    tokens = assets.get("tokens") or {}
    swatches = [v for v in tokens.values()
                if isinstance(v, str) and v.startswith("#")]
    products = [
        {
            "sku": sku,
            "name": entry.get("name") or "",
            "product_type": entry.get("product_type") or "",
            "price": entry.get("price") or "",
            "image": entry.get("data_uri"),
        }
        for sku, entry in (assets.get("products") or {}).items()
    ]
    return {
        "swatches": swatches,
        "font": tokens.get("font"),
        "logo": assets.get("logo_data_uri"),
        "logo_svg": assets.get("logo_svg"),
        "products": products,
    }


def _template_detail(state, manifest):
    lane = (state.get("lanes") or {}).get("template") or {}
    if not lane:
        return None
    detail = {
        "status": lane.get("status"),
        "at": lane.get("at"),
        "path": state.get("path"),
    }
    for key in ("layout_id", "store"):
        if key in lane:
            detail[key] = lane[key]
    brand = (manifest or {}).get("brand") or {}
    if brand.get("name"):
        detail["brand"] = brand["name"]
    return detail


def _seed_detail(run_dir):
    result = _read_json(run_dir / "results" / "shopify-seed.json")
    if not result:
        return None
    products = [
        {
            "title": p.get("title") or "",
            "seeded_price": p.get("seeded_price"),
            "adjusted": bool(p.get("adjusted")),
            "variant_count": len(p.get("variants") or []),
            "admin_url": p.get("admin_url"),
        }
        for p in (result.get("products") or [])
    ]
    return {
        "status": result.get("status"),
        "products": products,
        "demos": result.get("demos") or {},
        "warnings": result.get("warnings") or [],
        "error": result.get("error"),
    }


def _cdc_detail(run_dir, state, manifest):
    lane = (state.get("lanes") or {}).get("cdc") or {}
    cdc = (manifest or {}).get("cdc") or {}
    result = _read_json(run_dir / "results" / "demo-request.json")
    return {
        "status": lane.get("status") or "pending",
        "at": lane.get("at"),
        # Surfaced deliberately: a run that silently flipped this to true is
        # what produced the synthetic-order incident this UI now shows plainly.
        "generate_orders": bool(cdc.get("generate_orders")),
        "synthetic_orders": len(cdc.get("orders") or []),
        "url": (result or {}).get("url"),
        "error": (result or {}).get("error"),
    }


def build(run_dir):
    """Return the page's whole data contract for one poll."""
    run_dir = pathlib.Path(run_dir)
    state = run_state.load(str(run_dir))
    manifest = _read_json(run_dir / "demo-manifest.json")

    return {
        # The file is the flag: the conductor writes intake.json on a valid
        # submission, so its existence is what moves the page to phase two.
        "phase": "building" if (run_dir / "intake.json").exists() else "intake",
        "run_id": state.get("run_id"),
        "account_name": state.get("account_name"),
        "path": state.get("path"),
        "finished": bool(state.get("finished")),
        "updated_at": state.get("updated_at"),
        "mode": ((manifest or {}).get("run") or {}).get("mode"),
        "lanes": state.get("lanes") or {},
        "orders": state.get("orders") or [],
        "schedule": state.get("schedule") or {},
        "failures": state.get("failures") or [],
        "detail": {
            "scrape": _scrape_detail(run_dir),
            "template": _template_detail(state, manifest),
            "seed": _seed_detail(run_dir),
            "cdc": _cdc_detail(run_dir, state, manifest),
        },
    }
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd plugins/pl-tools/scripts && python3 -m unittest tests.test_state_payload -v`
Expected: PASS, all tests.

- [ ] **Step 5: Commit**

```bash
git add plugins/pl-tools/scripts/state_payload.py plugins/pl-tools/scripts/tests/test_state_payload.py
git commit -m "feat(demo-environment): assemble the run page's state payload from run-dir files"
```

---

### Task 3: The HTTP server

**Files:**
- Create: `plugins/pl-tools/scripts/run_server.py`
- Create (stub only, filled in Tasks 4–5): `plugins/pl-tools/scripts/run_app_template.html`
- Test: `plugins/pl-tools/scripts/tests/test_run_server.py`

**Interfaces:**
- Consumes: `intake_schema.parse_answers` / `default_answers` / `REGIONS` / `REGION_COURIERS` (Task 1), `state_payload.build` (Task 2), `pl_brand` (existing).
- Produces:
  - `render_page(run_dir, context) -> str` — template with brand tokens and context substituted
  - `build_context(run_dir, prospect_name, region, reuse_candidate) -> dict`
  - `make_handler(run_dir, context) -> type` — a `BaseHTTPRequestHandler` subclass
  - `serve(run_dir, context, port) -> None` — blocking
  - CLI: `python3 run_server.py <run_dir> --prospect-name NAME [--region US|UK|DE] [--reuse-candidate DATE] [--port 8097]`
  - Placeholder markers the template must contain: `{{BRAND_PRIMARY}}`, `{{BRAND_TEXT}}`, `{{BRAND_TINT}}`, `{{BRAND_CARD}}`, `{{BRAND_FONT}}`, `{{BRAND_FONTS_LINK}}`, `{{BRAND_LOGO}}`, `{{CONTEXT_JSON}}`

- [ ] **Step 1: Create the template stub so the server has something to serve**

Create `plugins/pl-tools/scripts/run_app_template.html` with exactly this content (Tasks 4 and 5 replace the body):

```html
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>parcelLab demo build</title>
{{BRAND_FONTS_LINK}}
<style>
  :root {
    --brand: {{BRAND_PRIMARY}};
    --fg: {{BRAND_TEXT}};
    --tint: {{BRAND_TINT}};
    --card: {{BRAND_CARD}};
  }
  body { font-family: {{BRAND_FONT}}; color: var(--fg); }
</style>
</head>
<body>
<div class="pl-logo">{{BRAND_LOGO}}</div>
<div id="app"></div>
<script>window.__CONTEXT__ = {{CONTEXT_JSON}};</script>
</body>
</html>
```

- [ ] **Step 2: Write the failing test**

Create `plugins/pl-tools/scripts/tests/test_run_server.py`:

```python
"""Unit tests for run_server. Stdlib unittest — no pytest.

The server is exercised over real HTTP on an ephemeral port: the routing and
the status codes are the contract the page depends on, and a handler called
directly would not prove either.
"""
import json
import pathlib
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import HTTPServer

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import intake_schema  # noqa: E402
import run_server  # noqa: E402
import run_state  # noqa: E402


class TestRenderPage(unittest.TestCase):
    def setUp(self):
        self.dir = pathlib.Path(tempfile.mkdtemp())
        run_state.init(str(self.dir), "brand-20260819-1546", "retain", "Demo")

    def test_every_placeholder_is_substituted(self):
        html = run_server.render_page(self.dir, {"prospect_name": "Brand"})
        self.assertNotIn("{{", html)
        self.assertIn("#3E39D3", html)
        self.assertIn("Poppins", html)

    def test_context_is_valid_json_in_the_page(self):
        context = {"prospect_name": "Brand", "region": "DE"}
        html = run_server.render_page(self.dir, context)
        blob = html.split("window.__CONTEXT__ = ")[1].split(";</script>")[0]
        self.assertEqual(json.loads(blob)["region"], "DE")

    def test_context_closing_tag_is_escaped(self):
        html = run_server.render_page(
            self.dir, {"prospect_name": "</script><script>alert(1)"})
        self.assertNotIn("</script><script>alert(1)", html)


class TestBuildContext(unittest.TestCase):
    def setUp(self):
        self.dir = pathlib.Path(tempfile.mkdtemp())

    def test_context_carries_vocabularies_and_defaults(self):
        context = run_server.build_context(
            self.dir, prospect_name="Brand", region="UK",
            reuse_candidate=None)
        self.assertEqual(context["regions"], list(intake_schema.REGIONS))
        self.assertEqual(context["region_couriers"],
                         intake_schema.REGION_COURIERS)
        self.assertEqual(context["defaults"]["courier"], "royal-mail")
        self.assertIsNone(context["reuse_candidate"])
        self.assertEqual(sorted(context["scenarios"]),
                         sorted(intake_schema.SCENARIOS))


class ServerTestCase(unittest.TestCase):
    def setUp(self):
        self.dir = pathlib.Path(tempfile.mkdtemp())
        (self.dir / "scrape").mkdir()
        (self.dir / "results").mkdir()
        run_state.init(str(self.dir), "brand-20260819-1546", "retain", "Demo")
        context = run_server.build_context(
            self.dir, prospect_name="Brand", region="US",
            reuse_candidate=None)
        handler = run_server.make_handler(self.dir, context)
        self.httpd = HTTPServer(("127.0.0.1", 0), handler)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever,
                                       daemon=True)
        self.thread.start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)

    def url(self, path):
        return f"http://127.0.0.1:{self.port}{path}"

    def get(self, path):
        with urllib.request.urlopen(self.url(path), timeout=5) as response:
            return response.status, response.read()

    def post(self, path, payload):
        request = urllib.request.Request(
            self.url(path), data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read())


class TestRoutes(ServerTestCase):
    def test_root_serves_the_page(self):
        status, body = self.get("/")
        self.assertEqual(status, 200)
        self.assertIn(b"__CONTEXT__", body)

    def test_state_serves_the_payload(self):
        status, body = self.get("/state")
        self.assertEqual(status, 200)
        payload = json.loads(body)
        self.assertEqual(payload["phase"], "intake")
        self.assertEqual(payload["run_id"], "brand-20260819-1546")

    def test_state_is_not_cached(self):
        with urllib.request.urlopen(self.url("/state"), timeout=5) as response:
            self.assertIn("no-store", response.headers.get("Cache-Control", ""))

    def test_unknown_path_is_404(self):
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.get("/nope")
        self.assertEqual(caught.exception.code, 404)

    def test_post_to_unknown_path_is_404(self):
        status, _ = self.post("/nope", {})
        self.assertEqual(status, 404)


class TestSubmit(ServerTestCase):
    def valid_payload(self):
        return intake_schema.default_answers(region="US")

    def test_valid_submission_writes_intake_json(self):
        status, body = self.post("/submit", self.valid_payload())
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])
        written = json.loads((self.dir / "intake.json").read_text())
        self.assertEqual(written["region"], "US")

    def test_valid_submission_flips_phase_to_building(self):
        self.post("/submit", self.valid_payload())
        _, body = self.get("/state")
        self.assertEqual(json.loads(body)["phase"], "building")

    def test_invalid_submission_is_400_with_the_reason(self):
        payload = self.valid_payload()
        payload["region"] = "ES"
        status, body = self.post("/submit", payload)
        self.assertEqual(status, 400)
        self.assertFalse(body["ok"])
        self.assertIn("region", body["error"])

    def test_invalid_submission_writes_nothing(self):
        payload = self.valid_payload()
        payload["orders"] = []
        self.post("/submit", payload)
        self.assertFalse((self.dir / "intake.json").exists())

    def test_malformed_body_is_400_not_a_traceback(self):
        request = urllib.request.Request(
            self.url("/submit"), data=b"{not json",
            headers={"Content-Type": "application/json"}, method="POST")
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(request, timeout=5)
        self.assertEqual(caught.exception.code, 400)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `cd plugins/pl-tools/scripts && python3 -m unittest tests.test_run_server -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'run_server'`

- [ ] **Step 4: Write the implementation**

Create `plugins/pl-tools/scripts/run_server.py`:

```python
#!/usr/bin/env python3
"""Serve one demo-environment run: the intake form, then live progress.

Replaces both the intake questionnaire Artifact and the separate run-page
Artifact. Artifacts cannot work here at all — the Browser pane runs a fresh
context with no claude.ai session, so a published page shows a sign-in screen
and the documented publish/poll/extract handoff never completes.

The handoff is a file, not a flag in memory: a valid POST /submit writes
`<run dir>/intake.json`, and the conductor waits for that file to appear. A
server restart therefore loses nothing, and the conductor needs no HTTP
client.
"""
import argparse
import json
import pathlib
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

import intake_schema
import pl_brand
import state_payload

DEFAULT_PORT = 8097          # 8098 belongs to branded-template's layout-preview
TEMPLATE = pathlib.Path(__file__).resolve().parent / "run_app_template.html"
MAX_BODY_BYTES = 1 << 20     # an intake payload is a few KB; refuse anything wild


def _context_json(context):
    """JSON safe to inline in a <script> block.

    A prospect name containing `</script>` would otherwise close the block
    early and inject whatever follows it into the page.
    """
    return json.dumps(context).replace("</", "<\\/")


def render_page(run_dir, context):
    """The page, with brand tokens and this run's context substituted in.

    Plain str.replace rather than str.format or a template engine: the file
    is full of CSS and JS braces, so any brace-based formatter would have to
    escape all of them.
    """
    html = TEMPLATE.read_text()
    for marker, value in (
        ("{{BRAND_PRIMARY}}", pl_brand.PRIMARY),
        ("{{BRAND_TEXT}}", pl_brand.TEXT),
        ("{{BRAND_TINT}}", pl_brand.TINT),
        ("{{BRAND_CARD}}", pl_brand.CARD),
        ("{{BRAND_FONT}}", pl_brand.FONT_FAMILY),
        ("{{BRAND_FONTS_LINK}}", pl_brand.GOOGLE_FONTS_LINK),
        ("{{BRAND_LOGO}}", pl_brand.LOGO_SVG),
        ("{{CONTEXT_JSON}}", _context_json(context)),
    ):
        html = html.replace(marker, value)
    return html


def build_context(run_dir, prospect_name, region, reuse_candidate):
    """Everything the form needs to render itself, baked into the page.

    Kept as one blob rather than a second endpoint: the page needs all of it
    before first paint, so fetching it separately would only add a round trip
    and a loading state.
    """
    return {
        "prospect_name": prospect_name,
        "run_id": pathlib.Path(run_dir).name,
        "reuse_candidate": reuse_candidate,
        "regions": list(intake_schema.REGIONS),
        "region_couriers": dict(intake_schema.REGION_COURIERS),
        "fraud_levels": sorted(intake_schema.FRAUD_LEVELS),
        "scenarios": sorted(intake_schema.SCENARIOS),
        "modes": sorted(intake_schema.MODES),
        "weight_units": sorted(intake_schema.WEIGHT_UNITS),
        "max_orders": intake_schema.MAX_ORDERS,
        "defaults": intake_schema.default_answers(region=region),
    }


def make_handler(run_dir, context):
    run_dir = pathlib.Path(run_dir)

    class Handler(BaseHTTPRequestHandler):
        # Quiet by default: this runs in the background for the whole run and
        # a line per poll would bury anything that matters.
        def log_message(self, *args):
            pass

        def _send(self, status, body, content_type):
            payload = body.encode() if isinstance(body, str) else body
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)

        def _send_json(self, status, payload):
            self._send(status, json.dumps(payload), "application/json")

        def do_GET(self):
            path = self.path.split("?", 1)[0]
            if path == "/":
                self._send(200, render_page(run_dir, context),
                           "text/html; charset=utf-8")
            elif path == "/state":
                self._send_json(200, state_payload.build(run_dir))
            else:
                self._send_json(404, {"ok": False, "error": "not found"})

        def do_POST(self):
            if self.path.split("?", 1)[0] != "/submit":
                self._send_json(404, {"ok": False, "error": "not found"})
                return

            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY_BYTES:
                self._send_json(400, {"ok": False,
                                      "error": "payload too large"})
                return
            raw = self.rfile.read(length).decode("utf-8", "replace")

            try:
                answers = intake_schema.parse_answers(raw)
            except ValueError as exc:
                # 400 with the reason, so the page shows it inline and the
                # operator fixes it on the same form.
                self._send_json(400, {"ok": False, "error": str(exc)})
                return

            # Written last and only on success: the file's existence is what
            # tells the conductor intake is done, so it must never appear for
            # a payload that failed validation.
            (run_dir / "intake.json").write_text(
                json.dumps(answers, indent=2))
            self._send_json(200, {"ok": True})

    return Handler


def serve(run_dir, context, port=DEFAULT_PORT):
    handler = make_handler(run_dir, context)
    httpd = HTTPServer(("127.0.0.1", port), handler)
    print(f"serving {run_dir} on http://127.0.0.1:{port}", flush=True)
    httpd.serve_forever()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("run_dir")
    ap.add_argument("--prospect-name", required=True)
    ap.add_argument("--region", default="US", choices=list(intake_schema.REGIONS))
    ap.add_argument("--reuse-candidate", default=None,
                    help="date of a reusable prior scrape, if one was found")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = ap.parse_args(argv)

    run_dir = pathlib.Path(args.run_dir)
    if not run_dir.is_dir():
        print(f"run_server: no such run dir {run_dir}", file=sys.stderr)
        return 1

    context = build_context(run_dir, args.prospect_name, args.region,
                            args.reuse_candidate)
    try:
        serve(run_dir, context, args.port)
    except OSError as exc:
        # The conductor's documented response is the chat fallback, so say
        # plainly which port is taken rather than dumping a traceback.
        print(f"run_server: cannot bind port {args.port}: {exc}",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd plugins/pl-tools/scripts && python3 -m unittest tests.test_run_server -v`
Expected: PASS, all tests.

- [ ] **Step 6: Commit**

```bash
git add plugins/pl-tools/scripts/run_server.py plugins/pl-tools/scripts/run_app_template.html plugins/pl-tools/scripts/tests/test_run_server.py
git commit -m "feat(demo-environment): serve the run page and intake handoff over a local server"
```

---

### Task 4: Intake phase in the page

**Files:**
- Modify: `plugins/pl-tools/scripts/run_app_template.html` (replace the stub body)
- Test: `plugins/pl-tools/scripts/tests/test_run_server.py` (add template-contract tests)

**Interfaces:**
- Consumes: `window.__CONTEXT__` (Task 3's `build_context` shape), `POST /submit`, `GET /state`.
- Produces: a page that collects a payload matching `intake_schema.parse_answers`' contract, and JS functions `collectAnswers()`, `renderOrderCards()`, `switchPhase(phase)` used by Task 5.

**Source material:** `.superpowers/brainstorm/63507-1787164204/content/intake-mockup-v5.html` — reuse its markup, CSS classes and interaction JS. Two values must change per this plan's *Two deliberate deviations* section: the region list becomes `US`/`UK`/`DE` (driven from `window.__CONTEXT__.regions`, not hardcoded), and its courier map comes from `window.__CONTEXT__.region_couriers`.

- [ ] **Step 1: Write the failing test**

Append to `plugins/pl-tools/scripts/tests/test_run_server.py` (inside a new class at the end, before `if __name__`):

```python
class TestIntakeTemplate(unittest.TestCase):
    """The template is HTML, so these check its contract with the server and
    the schema rather than its appearance — a missing hook here is exactly the
    kind of break that renders a silently non-functional form."""

    def setUp(self):
        self.html = run_server.TEMPLATE.read_text()

    def test_no_unsubstituted_placeholder_names_are_invented(self):
        known = {"{{BRAND_PRIMARY}}", "{{BRAND_TEXT}}", "{{BRAND_TINT}}",
                 "{{BRAND_CARD}}", "{{BRAND_FONT}}", "{{BRAND_FONTS_LINK}}",
                 "{{BRAND_LOGO}}", "{{CONTEXT_JSON}}"}
        import re
        found = set(re.findall(r"\{\{[A-Z_]+\}\}", self.html))
        self.assertEqual(found - known, set())

    def test_posts_to_submit(self):
        self.assertIn("/submit", self.html)

    def test_polls_state(self):
        self.assertIn("/state", self.html)

    def test_does_not_hardcode_a_region_list(self):
        for invented in ("correos-es", "dpd-uk", "colissimo-fr", "dhl-de"):
            self.assertNotIn(invented, self.html)

    def test_reads_vocabularies_from_context(self):
        for key in ("regions", "region_couriers", "scenarios", "defaults"):
            self.assertIn(key, self.html)

    def test_has_both_phase_containers(self):
        self.assertIn('id="phase-intake"', self.html)
        self.assertIn('id="phase-building"', self.html)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd plugins/pl-tools/scripts && python3 -m unittest tests.test_run_server.TestIntakeTemplate -v`
Expected: FAIL — `test_has_both_phase_containers` and `test_posts_to_submit` fail against the stub.

- [ ] **Step 3: Build the intake phase**

Replace `plugins/pl-tools/scripts/run_app_template.html` entirely. Structure it as:

```html
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>parcelLab demo build</title>
{{BRAND_FONTS_LINK}}
<script src="https://cdn.tailwindcss.com"></script>
<style>
  :root {
    --brand: {{BRAND_PRIMARY}};
    --fg: {{BRAND_TEXT}};
    --tint: {{BRAND_TINT}};
    --card: {{BRAND_CARD}};
  }
  body { font-family: {{BRAND_FONT}}; color: var(--fg); background: #fff; }

  /* Expand/collapse without layout jank. Animating max-height stutters
     because the browser cannot interpolate to a content-derived height;
     0fr -> 1fr on a grid row can. */
  .panel { display: grid; grid-template-rows: 0fr; opacity: 0;
           transition: grid-template-rows .25s ease, opacity .2s ease; }
  .panel > div { overflow: hidden; min-height: 0; }
  .panel.open { grid-template-rows: 1fr; opacity: 1; margin-top: 1rem; }

  .pill-btn { transition: background-color .15s ease, color .15s ease,
              border-color .15s ease; }
  .card-in { animation: card-in .2s cubic-bezier(.2,.8,.2,1) both; }
  @keyframes card-in { from { opacity: 0; transform: translateY(4px); }
                       to { opacity: 1; transform: translateY(0); } }
</style>
</head>
<body class="min-h-screen">

<div class="mx-auto max-w-4xl px-6 py-10">

  <header class="mb-8 flex items-center gap-3" style="color: var(--brand)">
    {{BRAND_LOGO}}
  </header>

  <!-- Shared step indicator, driven by switchPhase() -->
  <nav class="mb-8" id="steps"><!-- three steps: Intake / Building / Live --></nav>

  <section id="phase-intake"><!-- the form, from intake-mockup-v5.html --></section>
  <section id="phase-building" hidden><!-- Task 5 fills this in --></section>

</div>

<script>window.__CONTEXT__ = {{CONTEXT_JSON}};</script>
<script>
  // Task 4 JS: form rendering + collectAnswers() + submit
  // Task 5 JS: pollState() + lane drill-downs + order feed
</script>
</body>
</html>
```

Port these from `intake-mockup-v5.html`, keeping its ids and classes so the mockup stays a readable reference:

- **Prospect section**: website input (pre-filled from `__CONTEXT__.prospect_name`), region `<select id="region-select">` built by looping `__CONTEXT__.regions`, courier `<select id="courier-select">` built from `__CONTEXT__.region_couriers`, and `onRegionChange()` which sets the courier to `__CONTEXT__.region_couriers[region]`. Keep the Shopify on/off toggle (`shopify-toggle` / `shopify-knob` / `shopify-hint`) exactly as the mockup has it, including the hint text flipping between `retain-shopify` and `retain`.
- **Reuse question**: render only when `__CONTEXT__.reuse_candidate` is non-null — a radio pair (reuse / scrape fresh) whose value becomes `reuse_pool`. When it is null, submit `reuse_pool: null`.
- **Order matrix**: the `count-btn` segmented picker (`1..__CONTEXT__.max_orders`), the `matrix-toggle` on/off switch, and `renderOrderCards()` producing one card per order with `fraudPills()`, a `split shipment` checkbox, and — when split — Parcel A/B rows each with `scenarioSelect()` and `courierInput()`. Build the scenario `<option>` list from `__CONTEXT__.scenarios`, not a hardcoded array. Seed `orderState` from `__CONTEXT__.defaults.orders` so the pre-fill matches `default_answers()`.
- **Customisation**: the `extras-toggle` switch revealing the multi-select dropdown (`dd-btn` / `dd-panel` / `dd-label`) whose seven items reveal `field-*` groups. Each field group's inputs must write into keys from `intake_schema.EXTRA_KEYS` — `announced_delivery_date` / `_min` / `_max`, `tax_amount`, `net_amount`, `discount_amount`, `extra_articles`, `tags`, `additional_attributes`, `additional_recipients`, `delivery_method`, `courier_service_level`, `signature_required`, `article_weights`.
- **Mode**: babysit / auto select, from `__CONTEXT__.modes`.
- **`collectAnswers()`**: returns exactly the eight top-level keys `parse_answers` requires — `shopify_opp`, `reuse_pool`, `region`, `courier`, `orders`, `gate_c`, `extras`, `mode`. `gate_c` is `"extras"` when the customisation toggle is on and at least one extra is selected, else `"send-as-is"` with `extras: {}` (the validator rejects any other combination).
- **Submit handler**: `POST /submit` with `collectAnswers()`. On 200, call `switchPhase("building")` and start polling. On 400, show `body.error` inline above the submit button and leave the form editable — never navigate away.
- **`switchPhase(phase)`**: toggles the `hidden` attribute on the two sections and updates `#steps`.
- **Boot**: `fetch('/state')` once on load; if `phase` is already `"building"` (a reload mid-run), go straight to the building phase.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd plugins/pl-tools/scripts && python3 -m unittest tests.test_run_server -v`
Expected: PASS, all tests including `TestIntakeTemplate`.

- [ ] **Step 5: Verify the form in a browser**

Start the server against a scratch run dir and drive it:

```bash
mkdir -p /tmp/plrun/scrape /tmp/plrun/results && python3 -c "import sys; sys.path.insert(0, 'plugins/pl-tools/scripts'); import run_state; run_state.init('/tmp/plrun', 'brand-20260819-1546', 'retain', 'Demo - JLS')"
```

Add a launch entry and open it:

```bash
python3 plugins/pl-tools/scripts/ensure_launch_config.py .claude/launch.json '{"name": "demo-run-server", "runtimeExecutable": "python3", "runtimeArgs": ["plugins/pl-tools/scripts/run_server.py", "/tmp/plrun", "--prospect-name", "PcComponentes", "--region", "DE"], "port": 8097}'
```

Then `preview_start` → `{name: "demo-run-server"}`, and check with `read_page` / `computer`:
- the region select offers exactly US, UK, DE, and changing it updates the courier select
- the Shopify toggle flips its hint text
- turning on "customise each order individually" reveals three order cards; ticking `split shipment` on one forks it into Parcel A/B with independent scenario selects
- turning on customisation and selecting two extras reveals both field groups
- submitting writes `/tmp/plrun/intake.json` (`cat` it and confirm it parses: `python3 -c "import sys; sys.path.insert(0,'plugins/pl-tools/scripts'); import intake_schema, pathlib; intake_schema.parse_answers(pathlib.Path('/tmp/plrun/intake.json').read_text()); print('ok')"`)
- forcing an invalid payload (deselect every order via the count picker if reachable, or POST `{"region":"ES",...}` by hand with `javascript_tool`) shows the error inline and leaves the form usable

Check `read_console_messages` for errors, and clean up afterwards: `preview_stop`, then remove the `demo-run-server` entry from `.claude/launch.json`.

- [ ] **Step 6: Commit**

```bash
git add plugins/pl-tools/scripts/run_app_template.html plugins/pl-tools/scripts/tests/test_run_server.py
git commit -m "feat(demo-environment): build the intake phase of the unified run page"
```

---

### Task 5: Building phase, lane drill-downs and order feed

**Files:**
- Modify: `plugins/pl-tools/scripts/run_app_template.html` (fill in `#phase-building`)
- Test: `plugins/pl-tools/scripts/tests/test_run_server.py` (add building-phase contract tests)

**Interfaces:**
- Consumes: `GET /state` (Task 2's `state_payload.build` shape), `switchPhase()` (Task 4).
- Produces: `pollState()`, `renderLanes(payload)`, `renderLaneDetail(name, detail)`, `renderOrderFeed(orders, schedule)`, `toggleLane(name)`.

**Source material:** `.superpowers/brainstorm/63507-1787164204/content/progress-mockup-v3.html` — reuse its markup, animations and `toggleLane` accordion. Its content is hardcoded sample data; every value must instead come from the `/state` payload.

- [ ] **Step 1: Write the failing test**

Append to `plugins/pl-tools/scripts/tests/test_run_server.py`:

```python
class TestBuildingTemplate(unittest.TestCase):
    def setUp(self):
        self.html = run_server.TEMPLATE.read_text()

    def test_has_a_panel_per_lane(self):
        for lane in ("scrape", "template", "seed", "orders", "cdc"):
            self.assertIn(f'id="panel-{lane}"', self.html)

    def test_has_a_lane_button_per_lane(self):
        for lane in ("scrape", "template", "seed", "orders", "cdc"):
            self.assertIn(f"toggleLane('{lane}')", self.html)

    def test_renders_seed_exchange_demos(self):
        for demo in ("in_product_even", "cross_product_even",
                     "uneven_upward", "uneven_downward"):
            self.assertIn(demo, self.html)

    def test_surfaces_generate_orders(self):
        self.assertIn("generate_orders", self.html)

    def test_has_no_hardcoded_sample_data_from_the_mockup(self):
        for sample in ("Sarah Mitchell", "James Carter", "Maria Gonzalez",
                       "pl-1041", "pl-1042", "pl-1043"):
            self.assertNotIn(sample, self.html)

    def test_polls_on_an_interval(self):
        self.assertIn("setInterval", self.html)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd plugins/pl-tools/scripts && python3 -m unittest tests.test_run_server.TestBuildingTemplate -v`
Expected: FAIL — no lane panels exist yet.

- [ ] **Step 3: Build the building phase**

Fill `#phase-building` in `run_app_template.html`, porting from `progress-mockup-v3.html`:

- **Header block**: run id and account name from the payload, `path` as a subtitle, the `.live-bar` indeterminate stripe, the three `.dot-pulse` dots and a `updated <n>s ago` freshness stamp computed from `payload.updated_at`. Hide the stripe and the dots once `payload.finished` is true — the motion means "still working", so leaving it running on a finished run says something false.
- **Auto-mode banner**: when `payload.mode === "auto"`, show the banner. Keep the mockup's off-brand orange gradient (`#ff6b35` → `#f7931e`) rather than the brand indigo — it exists to jump out as "this ran unattended", which warm colours do and the brand colour does not. This is the one deliberate off-brand element on the page.
- **Lane row**: five `.lane-btn` buttons built from `payload.lanes`, each showing the lane name and its status, coloured by status (`ok`/`published` green, `running` brand, `failed` red, `pending`/`skipped` grey). The running lane gets `.card-active`.
- **Lane panels**: one `.panel` per lane, opened by `toggleLane(name)` (accordion — opening one closes any other), each rendered from `payload.detail[name]`:
  - `scrape`: swatch chips from `detail.scrape.swatches`, the font name, the logo (`logo_svg` inline if present, else `<img src=logo>`), and a product grid from `detail.scrape.products` using each product's `image` data URI with a grey "image unavailable" placeholder when it is null.
  - `template`: status, `layout_id`, `store`, `brand`, and the resolved `path`. Link to the local layout preview rather than embedding it.
  - `seed`: the seeded-product table (title, seeded price with an "adjusted" marker when `adjusted` is true, `variant_count`) plus the four exchange scenarios from `detail.seed.demos` — `in_product_even` (`product`, `option`, `swap`), `cross_product_even` (a two-name array), `uneven_upward` (`from`, `to`, `balance`), `uneven_downward` (`from`, `to`, `refund`, or "not available" when null). Render `warnings` and `error` when present.
  - `orders`: a one-line summary counting delivered / in-progress / queued, pointing at the feed below.
  - `cdc`: status, and `generate_orders` shown explicitly with `synthetic_orders`. Say plainly when `generate_orders` is false and no synthetic orders will be created; when it is true, mark it as a warning — that state is what produced a contaminated run once.
- **Order feed**: one card per `payload.orders` entry — customer/label, `order_number`, fraud pill, and a status pill derived from its shipments. For each shipment render a timeline from `planned` and `confirmed`: confirmed events green (most recent first), the next planned event as the live one on the running shipment, the rest as dashed "expected". A split order (two shipments) renders its shipments as two side-by-side columns. Give the actively-running order `.card-active`.
- **`pollState()`**: `setInterval` every 2000 ms, `fetch('/state')`, re-render. On a fetch failure, leave the last-rendered state on screen and show a muted "reconnecting…" note — never blank the page. Stop polling once `payload.finished` is true.
- **Failures**: render `payload.failures` as a red band above the lane row when non-empty.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd plugins/pl-tools/scripts && python3 -m unittest tests.test_run_server -v`
Expected: PASS, all classes.

- [ ] **Step 5: Verify the building phase in a browser against real-shaped state**

Reuse `/tmp/plrun` from Task 4 (it now has `intake.json`, so the page boots into the building phase). Populate state so every panel has content:

```bash
python3 - <<'PY'
import json, pathlib, sys
sys.path.insert(0, 'plugins/pl-tools/scripts')
import run_state
d = '/tmp/plrun'
run_state.set_lane(d, 'scrape', 'ok')
run_state.set_lane(d, 'template', 'published', layout_id=20701, store='Demo Store')
run_state.set_lane(d, 'seed', 'ok')
run_state.mark(d, 'lane', 'orders', 'start')
run_state.set_schedule(d, '2026-08-19T15:30:00Z', 300)
run_state.add_order(d, '01-fraud-low', 'pl-1041', [
    {'label': 'A', 'tracking_number': 'TN1', 'courier': 'dhl-germany',
     'planned': ['InTransit', 'OutForDelivery', 'Delivered']}])
run_state.add_order(d, '02-fraud-medium', 'pl-1042', [
    {'label': 'A', 'tracking_number': 'TN2', 'courier': 'dhl-germany',
     'planned': ['InTransit', 'OutForDelivery', 'Delivered']},
    {'label': 'B', 'tracking_number': 'TN3', 'courier': 'dhl-germany',
     'planned': ['InTransit', 'WarehouseDelay']}])
run_state.confirm_event(d, 'TN1', 'InTransit', '2026-08-19T15:31:05Z', 204)
run_state.confirm_event(d, 'TN1', 'OutForDelivery', '2026-08-19T15:36:05Z', 204)
run_state.confirm_event(d, 'TN2', 'InTransit', '2026-08-19T15:31:07Z', 204)
run_state.confirm_event(d, 'TN3', 'WarehouseDelay', '2026-08-19T15:39:08Z', 204)
pathlib.Path(d, 'results', 'shopify-seed.json').write_text(json.dumps({
    'status': 'ok',
    'products': [
        {'title': 'RTX 4070 SUPER', 'seeded_price': '299.00', 'adjusted': True,
         'variants': [{'id': 'gid://1'}, {'id': 'gid://2'}]},
        {'title': 'G Pro X Superlight', 'seeded_price': '129.00', 'adjusted': True,
         'variants': [{'id': 'gid://3'}, {'id': 'gid://4'}]}],
    'demos': {
        'in_product_even': {'product': 'RTX 4070 SUPER', 'option': 'Memory',
                            'swap': '12GB → 16GB'},
        'cross_product_even': ['G Pro X Superlight', 'FURY 32GB DDR5'],
        'uneven_upward': {'from': 'G Pro X Superlight', 'to': 'RTX 4070 SUPER',
                          'balance': '170.00'},
        'uneven_downward': {'from': 'G Pro X Superlight', 'to': 'BlackWidow V4',
                            'refund': '40.00'}},
    'warnings': [], 'error': None}))
pathlib.Path(d, 'scrape', 'assets.json').write_text(json.dumps({
    'tokens': {'primary': '#e2001a', 'text': '#1a1a1a', 'font': 'Inter'},
    'logo_data_uri': None, 'logo_svg': None,
    'products': {'SKU1': {'name': 'RTX 4070 SUPER', 'product_type': 'graphics card',
                          'price': '649.00', 'data_uri': None}}}))
pathlib.Path(d, 'demo-manifest.json').write_text(json.dumps({
    'run': {'mode': 'babysit'}, 'cdc': {'generate_orders': False, 'orders': []}}))
print('seeded')
PY
```

Restart the preview and confirm in the pane: the page boots straight into the building phase; each of the five lane pills opens its own panel and closes the previous one; the seed panel shows both products and all four exchange scenarios (including the downward refund); the CDC panel states `generate_orders: false`; order `#2` renders as two parcel columns with B stuck at the delay; the freshness stamp advances. Then set `run_state.finish(d)` and confirm the live stripe and dots stop.

Take a screenshot for the record. Clean up: `preview_stop`, remove the launch entry, `rm -rf /tmp/plrun`.

- [ ] **Step 6: Commit**

```bash
git add plugins/pl-tools/scripts/run_app_template.html plugins/pl-tools/scripts/tests/test_run_server.py
git commit -m "feat(demo-environment): build the live progress phase with lane drill-downs"
```

---

### Task 6: Wire the conductor to the server

**Files:**
- Modify: `plugins/pl-tools/skills/demo-environment/SKILL.md` — "Intake questionnaire" section, "The run page" section, Phase 0 steps 1–2
- Modify: `plugins/pl-tools/skills/demo-environment/references/intake-script.md`

**Interfaces:**
- Consumes: `run_server.py`'s CLI from Task 3, `intake.json`'s shape from Task 1.
- Produces: the documented conductor procedure every later phase's re-render references depend on.

There is no unit test for a Markdown procedure; the verification step below is a real read-through against the scripts, which is what catches a documented flag that does not exist.

- [ ] **Step 1: Replace the "Intake questionnaire" section**

Rewrite it to say: Phase 0 step 2 starts a local server and waits for `<run dir>/intake.json`. Keep the existing statements that survive unchanged — every question is answered by one up-front form in both modes; mode is a form field, never inferred from trigger phrasing; mode's only effect is at the two hard gates; destination country / brand region / category / pace still come from `resolve_auto_defaults.py`.

Add these facts:

- The form asks region and courier, so `resolve_auto_defaults.py`'s `infer_country` output is now a **pre-fill** for the region field rather than the final value. Write the submitted `region` to both `brand.region` and `destination_country`; write `brand.category` and `run.pace` from the script exactly as before.
- The form offers only `US`, `UK`, `DE`, because `validate_manifest.py` accepts no other `brand.region`.
- `intake.json` carries per-order `split` plus per-parcel `scenario` and `courier`. Map each order's parcels onto manifest `shipments`, and each parcel's `courier` (or the run's default when null) onto that shipment's courier.
- There is no Artifact anywhere in intake. Do not publish one, and do not poll a DOM.

- [ ] **Step 2: Rewrite Phase 0 step 1**

Replace the `render_run_page.py` + republish call with: initialise run state as now, then no render — the page renders itself from `/state`. Keep the "never hand-edit" warning but retarget it: record facts through `run_state.py`; the page picks them up on its next poll, within two seconds.

- [ ] **Step 3: Rewrite Phase 0 step 2**

Document exactly this procedure:

1. Detect a reuse candidate as today — scan `$HOME/parcellab-demo-runs/` for a prior run with this handle holding both `scrape/brand-tokens.json` and `scrape/product-pool.json`; most recent wins.
2. Pre-resolve the region for the form's default with `resolve_auto_defaults.py --prospect-url`. When no product pool exists yet, pass the prospect URL alone and take the TLD/path inference.
3. **Stop any server left running from a previous run before starting this one.** Call `preview_list`; if a `demo-run-server` entry is running, `preview_stop` it. Its `runtimeArgs` carry the *previous* run's directory, and `preview_start` reuses a running server — skipping this serves the last run's state to this run's operator with no error anywhere.
4. Upsert the launch entry:

   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/scripts/ensure_launch_config.py \
     "$PWD/.claude/launch.json" \
     '{"name": "demo-run-server", "runtimeExecutable": "python3",
       "runtimeArgs": ["${CLAUDE_PLUGIN_ROOT}/scripts/run_server.py",
                       "<run dir>", "--prospect-name", "<brand name>",
                       "--region", "<pre-resolved region>",
                       "--reuse-candidate", "<date, only if found>"],
       "port": 8097}'
   ```

5. `preview_start` → `{name: "demo-run-server"}`, note the returned `tabId`, and tell the operator to fill in the form.
6. Poll for `<run dir>/intake.json`. It appears only on a submission that passed validation, so its presence means intake is complete — read it and write `path` (`shopify_opp` → `retain-shopify`, else `retain`), `run.mode`, `gates.order_lifecycle.gate_c`, `gates.order_lifecycle.extras`, `brand.region`, `destination_country`, the per-order matrix and the courier defaults into the manifest. A rejected submission never writes the file; the operator sees the reason inline and resubmits on the same page.
7. **Fallback, if the server cannot start** (`run_server: cannot bind port …`, or `preview_start` fails): fall back to a plain chat interview asking, in order — Shopify opp, the reuse question if a candidate exists, region, courier, the order matrix, customisation, mode. The UI is never load-bearing, the same posture the run page always had.

- [ ] **Step 4: Replace the "The run page" section**

Delete the publish/republish contract entirely and replace it with: the run keeps one live page, served by `run_server.py` from Phase 0 step 2 for the whole run. It re-renders itself from `GET /state` every two seconds, so there is nothing to republish and no URL to carry — `run.page_url` is the local URL (`http://127.0.0.1:8097/`).

State plainly that the `Page renders` / `Page publishes` / `Page URL changes` telemetry columns now stay at zero by design: they existed to catch a conductor skipping an Artifact republish, and with a self-updating page that failure mode no longer exists. `build_telemetry_row.py` already handles empty lists, so nothing there changes.

- [ ] **Step 5: Strip every stale re-render instruction from the rest of SKILL.md**

Find them all and remove the render/republish half of each, keeping the `run_state.py` call that precedes it:

```bash
grep -n "render_run_page\|republish\|record_publish\|run-page.html\|run-page.md" plugins/pl-tools/skills/demo-environment/SKILL.md
```

Expect hits around the scrape lane (step 3), the ★ template gate (step 8), the ✋ plan gate (step 9), and Phase 2's watcher. Every one becomes "record it via `run_state.py`" with no page step. Confirm zero remaining hits when done.

- [ ] **Step 6: Rewrite `references/intake-script.md`**

Update the field table to the new set: Shopify opp, reuse pool (conditional), **region**, **default courier**, order matrix (count + per-order fraud/split/scenario/courier, per-parcel when split), customisation (the seven extras with their real field names), mode. Replace the old default matrix table with `intake_schema.default_answers()`'s three-order shape and say the function is the source of truth. Move region out of the "deliberately does not ask" table into the asked set, noting it is pre-filled from `infer_country` and limited to `US`/`UK`/`DE`. Keep category in the not-asked table, with the existing reasoning plus a pointer that per-product categories are a known separate gap. Delete the "detail asked in chat after the form" wording — extras are collected in the form now.

- [ ] **Step 7: Verify every documented flag and path actually exists**

```bash
python3 plugins/pl-tools/scripts/run_server.py --help
grep -c "render_run_page\|republish" plugins/pl-tools/skills/demo-environment/SKILL.md
grep -rn "CLAUDE_PLUGIN_ROOT" plugins/pl-tools/skills/demo-environment/SKILL.md | grep -c run_server
```

Expected: `--help` lists `--prospect-name`, `--region`, `--reuse-candidate`, `--port`; the second command prints `0`; the third is non-zero. Read the two rewritten sections end to end and confirm no step references a file or flag that does not exist.

- [ ] **Step 8: Commit**

```bash
git add plugins/pl-tools/skills/demo-environment/SKILL.md plugins/pl-tools/skills/demo-environment/references/intake-script.md
git commit -m "docs(demo-environment): drive intake and progress from the local run server"
```

---

### Task 7: Remove the superseded renderers

**Files:**
- Delete: `plugins/pl-tools/scripts/render_intake_questionnaire.py`, `plugins/pl-tools/scripts/tests/test_render_intake_questionnaire.py`
- Delete: `plugins/pl-tools/scripts/render_run_page.py`, `plugins/pl-tools/scripts/tests/test_render_run_page.py`
- Delete: `plugins/pl-tools/skills/demo-environment/references/run-page.md`
- Modify: `docs/superpowers/specs/2026-08-19-demo-environment-intake-questionnaire-design.md` (mark superseded)

**Interfaces:**
- Consumes: Task 6's documentation rewrite (nothing may still reference these files when they go).
- Produces: nothing — this is removal.

- [ ] **Step 1: Prove nothing references them any more**

```bash
grep -rn "render_run_page\|render_intake_questionnaire\|run-page.md\|run-page.html" \
  plugins/ docs/ README.md 2>/dev/null | grep -v "docs/superpowers/specs/"
```

Expected: no output. Any hit must be fixed before deleting — a dangling reference in a SKILL.md is a silent break, since the conductor follows it and hits a missing file mid-run.

- [ ] **Step 2: Delete the four files and the reference doc**

```bash
git rm plugins/pl-tools/scripts/render_intake_questionnaire.py \
       plugins/pl-tools/scripts/tests/test_render_intake_questionnaire.py \
       plugins/pl-tools/scripts/render_run_page.py \
       plugins/pl-tools/scripts/tests/test_render_run_page.py \
       plugins/pl-tools/skills/demo-environment/references/run-page.md
```

- [ ] **Step 3: Mark the superseded spec**

Add directly under the `Status:` line of `docs/superpowers/specs/2026-08-19-demo-environment-intake-questionnaire-design.md`:

```markdown
> **Superseded** by `2026-08-19-demo-environment-unified-intake-progress-design.md`.
> Its Artifact-based transport (publish the questionnaire, poll the DOM for a
> submitted banner, extract JSON) cannot work: the Browser pane has no
> claude.ai session, so the published page shows a sign-in screen. Kept for
> the reasoning behind front-loading intake and the parcelLab branding, both
> of which the superseding spec carries forward.
```

- [ ] **Step 4: Run the whole suite**

Run: `cd plugins/pl-tools/scripts && python3 -m unittest discover -s tests -v`
Expected: PASS. The two deleted test modules are gone; `test_run_state.py`, `test_build_telemetry_row.py`, `test_pl_brand.py` and the rest still pass — none of them imported the deleted renderers.

- [ ] **Step 5: Confirm the plugin still validates**

Run: `claude plugin validate .`
Expected: valid. The `pl-tools` "No version specified" warning is expected and must not be fixed — its version resolves to the git SHA so every push is a new version.

- [ ] **Step 6: Commit**

```bash
git add -A docs/superpowers/specs/2026-08-19-demo-environment-intake-questionnaire-design.md
git commit -m "refactor(demo-environment): remove the superseded Artifact renderers"
```

---

## Self-Review

**1. Spec coverage**

| Spec requirement | Task |
|---|---|
| One page, two phases, switched in place | 4 (`switchPhase`), 5 |
| Local server replacing Artifact transport | 3 |
| `POST /submit` → `intake.json` | 3 |
| `GET /state` polled every ~2s | 3 (endpoint), 5 (polling) |
| File-as-flag handoff, no HTTP client conductor-side | 2 (`phase`), 3, 6 |
| Full field set with real controls | 1 (schema), 4 (UI) |
| Region + courier defaults, overridable per order/parcel | 1, 4 |
| Split forks into Parcel A/B | 1 (validation), 4 (UI) |
| Real scenario vocabulary | 1, 4 |
| Customisation extras with real fields | 1 (`EXTRA_KEYS`), 4 |
| 5 clickable lanes with drill-down detail | 2 (`detail`), 5 |
| Seed panel with even/uneven exchange pricing | 2 (`_seed_detail`), 5 |
| parcelLab branding via `pl_brand.py` | 3 (substitution), 4, 5 |
| No new dependency, no React, no build step | Global Constraints; 3, 4, 5 |
| Port-conflict handling | 3 (clear bind error), 6 (stale-server stop + fallback) |
| Client validation mirroring the validator, server still authoritative | 1, 4, 6 |
| Chat fallback when the server can't start | 6 step 3.7 |
| stdlib `unittest` coverage of both endpoints | 3 |
| Manual browser verification | 4 step 5, 5 step 5 |
| Article category left as a parked non-goal | Not implemented, by design |

Two spec details were tightened during planning and are called out where they land: the spec's "in-memory submitted flag" is dropped in favour of `intake.json`'s existence (simpler, survives a restart, needs no HTTP client — Task 2/3), and the spec's claim that `ensure_launch_config.py` handles port conflicts is inaccurate — it does not touch ports at all, so Task 3 fails with a clear bind error and Task 6 documents stopping a stale server plus the chat fallback.

**2. Placeholder scan**

No "TBD", no "add appropriate error handling", no "similar to Task N". Tasks 4–6's steps are prose-directed rather than full code blocks because they port two already-written, user-approved mockup files and rewrite Markdown; each step names the exact ids, functions, payload keys and file paths involved, and both have executable verification steps.

**3. Type consistency**

Checked across tasks: `parse_answers` / `default_answers` / `REGIONS` / `REGION_COURIERS` / `EXTRA_KEYS` / `MAX_ORDERS` (Task 1) are consumed under those exact names by `run_server.build_context` (Task 3) and asserted in Task 3's tests. `state_payload.build(run_dir)` (Task 2) returns the `phase` / `lanes` / `orders` / `detail.{scrape,template,seed,cdc}` keys that Task 3 serves and Task 5 renders. The eight top-level keys `collectAnswers()` produces (Task 4) match `parse_answers`' `required` set exactly. The seed `demos` keys (`in_product_even`, `cross_product_even`, `uneven_upward`, `uneven_downward`) match `shape_product_mix.py`'s real output. The eight `{{...}}` markers in the Task 3 stub are the same eight Task 4's test pins.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-08-19-demo-environment-unified-intake-progress.md`. Two execution options:

**1. Subagent-Driven (recommended)** — a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
