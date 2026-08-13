# demo-environment auto mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an auto mode to `pl-tools:demo-environment` that answers nearly every intake question and both hard gates itself, asking the operator only Q1 (returns in scope) and Q2 (Shopify opp) live, and stopping only on genuine blockers — babysit mode (today's fully interactive flow) is unchanged and remains the default.

**Architecture:** Two pure, testable Python scripts do the new decision-making (`resolve_auto_defaults.py` for country/category inference and answers-doc merge; an extension to `validate_manifest.py` for the two new manifest fields). The orchestration logic — mode detection, when to ask Q1/Q2 vs. auto-resolve everything else, gate auto-approval, blocker handling, Beat 1 reporting — lives in prose in `SKILL.md` and `references/intake-script.md`, edited through the project's mandated `skill-creator` workflow rather than by hand.

**Tech Stack:** Python 3 stdlib only (`json`, `re`, `argparse`, `unittest` — no `pytest`, per this repo's conventions), Markdown for the skill files.

**Spec:** [docs/superpowers/specs/2026-08-13-demo-environment-auto-mode-design.md](../specs/2026-08-13-demo-environment-auto-mode-design.md)

## Global Constraints

- Tests are stdlib `unittest`; never `pip install`. Run with:
  `cd plugins/pl-tools/scripts && python3 -m unittest discover -s tests -v`
- Skill files (`SKILL.md`, `references/*.md`) are edited via
  `/anthropic-skills:skill-creator`, never hand-rolled or copy-edited —
  this is a hard rule in this repo's own `CLAUDE.md`.
- Never rename any of the protected `parcellab-*` strings listed in this
  repo's `CLAUDE.md`.
- Q1 (returns in scope) and Q2 (Shopify opp) are **always** asked live,
  in both modes — never defaulted, never read from an answers doc.
- `run.mode` absent in the manifest means babysit — matches the existing
  `run.pace` convention (absent means standard).
- Auto-mode default/inference/blocker values are exactly those listed in
  the spec's Q4–Q14 table; do not invent additional ones.

---

## File Structure

New:
- `plugins/pl-tools/scripts/resolve_auto_defaults.py` — pure functions:
  infer destination country from a prospect URL + scraped product pool,
  infer CDC category from the same, and merge an optional answers doc
  over the built-in defaults, tagging each resolved field's source.
- `plugins/pl-tools/scripts/tests/test_resolve_auto_defaults.py`

Modified:
- `plugins/pl-tools/scripts/validate_manifest.py` — validate the two new
  manifest fields, `run.mode` and `run.answers_doc`.
- `plugins/pl-tools/scripts/tests/test_validate_manifest.py` — cases for
  the above.
- `plugins/pl-tools/skills/demo-environment/SKILL.md` — mode detection,
  answers-doc consumption, gate auto-approval, blocker handling, Beat 1
  reporting line, manifest schema additions. Edited via skill-creator.
- `plugins/pl-tools/skills/demo-environment/references/intake-script.md`
  — per-question auto-mode resolution column, Q1/Q2 always-asked note.
  Edited via skill-creator.

---

### Task 1: `resolve_auto_defaults.py` — country and category inference

**Files:**
- Create: `plugins/pl-tools/scripts/resolve_auto_defaults.py`
- Test: `plugins/pl-tools/scripts/tests/test_resolve_auto_defaults.py`

**Interfaces:**
- Produces: `infer_country(prospect_url: str, product_pool: list[dict]) -> str`
  — returns one of `"US"`, `"UK"`, `"DE"`.
- Produces: `infer_category(product_pool: list[dict]) -> str` — returns
  one of `"Home"`, `"Electronics"`, `"Fashion"`.
- Produces: `resolve_auto_fields(prospect_url: str, product_pool: list[dict], answers_doc: dict | None = None) -> dict`
  — returns `{field: {"value": ..., "source": "default"|"inferred"|"doc"}, ...}`
  plus a top-level `"_ignored_doc_keys": [str, ...]` entry. `Task 3` (the
  SKILL.md edit) consumes this shape verbatim for its Beat 1 reporting
  line and for writing the manifest's Q4–Q14 fields.

- [ ] **Step 1: Write the failing tests for `infer_country`**

```python
# plugins/pl-tools/scripts/tests/test_resolve_auto_defaults.py
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from resolve_auto_defaults import infer_country, infer_category, resolve_auto_fields


class InferCountryTests(unittest.TestCase):
    def test_de_tld(self):
        self.assertEqual(infer_country("https://www.brand.de/shop", []), "DE")

    def test_uk_co_dot_uk_tld(self):
        self.assertEqual(infer_country("https://www.brand.co.uk/shop", []), "UK")

    def test_uk_dot_uk_tld(self):
        self.assertEqual(infer_country("https://brand.uk", []), "UK")

    def test_currency_symbol_fallback_euro(self):
        pool = [{"name": "Tee", "price": "€29.00"}]
        self.assertEqual(infer_country("https://brand.com", pool), "DE")

    def test_currency_symbol_fallback_pound(self):
        pool = [{"name": "Tee", "price": "£29.00"}]
        self.assertEqual(infer_country("https://brand.com", pool), "UK")

    def test_no_signal_defaults_to_us(self):
        pool = [{"name": "Tee", "price": "29.00"}]
        self.assertEqual(infer_country("https://brand.com", pool), "US")

    def test_tld_wins_over_currency(self):
        # a .de site pricing in USD is still a DE site
        pool = [{"name": "Tee", "price": "$29.00"}]
        self.assertEqual(infer_country("https://brand.de", pool), "DE")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd plugins/pl-tools/scripts && python3 -m unittest tests.test_resolve_auto_defaults -v`
Expected: FAIL/ERROR — `resolve_auto_defaults` module does not exist yet.

- [ ] **Step 3: Implement `infer_country`**

```python
# plugins/pl-tools/scripts/resolve_auto_defaults.py
"""Auto-mode resolution: country/category inference and answers-doc merge.

Pure functions only — no network, no filesystem — so the demo-environment
skill's Phase 0 can call these against data it has already scraped, and so
they stay unit-testable without a live run.
"""

import re
from urllib.parse import urlparse

DEFAULT_COUNTRY = "US"
DEFAULT_CATEGORY = "Fashion"

_TLD_COUNTRY = {
    "de": "DE",
    "uk": "UK",
}

_CURRENCY_COUNTRY = {
    "€": "DE",
    "£": "UK",
}


def infer_country(prospect_url, product_pool):
    """Infer the destination country from the site's TLD, else scraped prices.

    TLD wins outright — a .de site pricing test data in USD is still a DE
    site. Falls back to a currency symbol found in any scraped price, then
    to DEFAULT_COUNTRY when neither gives a signal.
    """
    host = (urlparse(prospect_url).netloc or prospect_url).lower()
    labels = host.split(".")
    for label in reversed(labels):
        if label in _TLD_COUNTRY:
            return _TLD_COUNTRY[label]

    for product in product_pool or []:
        price = str(product.get("price") or "")
        for symbol, country in _CURRENCY_COUNTRY.items():
            if symbol in price:
                return country

    return DEFAULT_COUNTRY
```

- [ ] **Step 4: Run tests to verify `infer_country` passes**

Run: `cd plugins/pl-tools/scripts && python3 -m unittest tests.test_resolve_auto_defaults.InferCountryTests -v`
Expected: PASS (the `infer_category`/`resolve_auto_fields` imports will
still fail at collection — that's expected until Steps 5–8).

- [ ] **Step 5: Write the failing tests for `infer_category`**

```python
# append to test_resolve_auto_defaults.py

class InferCategoryTests(unittest.TestCase):
    def test_electronics_match(self):
        pool = [{"name": "Phone case", "product_type": "Electronic Accessory"}]
        self.assertEqual(infer_category(pool), "Electronics")

    def test_home_match(self):
        pool = [{"name": "Vase", "product_type": "Home Decor"}]
        self.assertEqual(infer_category(pool), "Home")

    def test_fashion_match(self):
        pool = [{"name": "Trainer", "product_type": "Shoe"}]
        self.assertEqual(infer_category(pool), "Fashion")

    def test_no_products_defaults_to_fashion(self):
        self.assertEqual(infer_category([]), "Fashion")

    def test_no_type_match_defaults_to_fashion(self):
        pool = [{"name": "Mystery Item", "product_type": "Widget"}]
        self.assertEqual(infer_category(pool), "Fashion")

    def test_majority_type_wins_over_first_seen(self):
        pool = [
            {"name": "Vase", "product_type": "Home Decor"},
            {"name": "Shoe", "product_type": "Sneaker"},
            {"name": "Boot", "product_type": "Boot"},
        ]
        self.assertEqual(infer_category(pool), "Fashion")
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `cd plugins/pl-tools/scripts && python3 -m unittest tests.test_resolve_auto_defaults.InferCategoryTests -v`
Expected: FAIL/ERROR — `infer_category` not defined yet.

- [ ] **Step 7: Implement `infer_category`**

```python
# append to resolve_auto_defaults.py

_CATEGORY_KEYWORDS = {
    "Electronics": ("phone", "laptop", "tablet", "electronic", "device", "audio"),
    "Home": ("home", "kitchen", "decor", "furnish"),
}


def _match_category(product_type):
    text = product_type.lower()
    for category, keywords in _CATEGORY_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            return category
    return None


def infer_category(product_pool):
    """Best match between scraped product_types and the CDC's category menu.

    Counts matches per category across the whole pool and returns whichever
    has the most; ties and no-match both fall back to DEFAULT_CATEGORY,
    since Fashion is the safe default for an unclassifiable or empty pool.
    """
    counts = {}
    for product in product_pool or []:
        category = _match_category(str(product.get("product_type") or ""))
        if category:
            counts[category] = counts.get(category, 0) + 1

    if not counts:
        return DEFAULT_CATEGORY

    best = max(counts.values())
    winners = sorted(c for c, n in counts.items() if n == best)
    return winners[0]
```

- [ ] **Step 8: Run tests to verify `infer_category` passes**

Run: `cd plugins/pl-tools/scripts && python3 -m unittest tests.test_resolve_auto_defaults.InferCategoryTests -v`
Expected: PASS

- [ ] **Step 9: Write the failing tests for `resolve_auto_fields`**

```python
# append to test_resolve_auto_defaults.py

class ResolveAutoFieldsTests(unittest.TestCase):
    def setUp(self):
        self.url = "https://brand.de"
        self.pool = [{"name": "Vase", "product_type": "Home Decor", "price": "€10"}]

    def test_defaults_with_no_answers_doc(self):
        result = resolve_auto_fields(self.url, self.pool)
        self.assertEqual(result["destination_country"], {"value": "DE", "source": "inferred"})
        self.assertEqual(result["cdc.region"], {"value": "DE", "source": "inferred"})
        self.assertEqual(result["cdc.category"], {"value": "Home", "source": "inferred"})
        self.assertEqual(result["run.pace"], {"value": "standard", "source": "default"})
        self.assertEqual(
            result["gates.order_lifecycle.gate_c"], {"value": "send-as-is", "source": "default"}
        )
        self.assertEqual(result["_ignored_doc_keys"], [])

    def test_answers_doc_overrides_known_field(self):
        result = resolve_auto_fields(self.url, self.pool, answers_doc={"run.pace": "fast"})
        self.assertEqual(result["run.pace"], {"value": "fast", "source": "doc"})
        # untouched fields keep their own default/inferred value
        self.assertEqual(result["destination_country"], {"value": "DE", "source": "inferred"})

    def test_answers_doc_can_override_inferred_field(self):
        result = resolve_auto_fields(
            self.url, self.pool, answers_doc={"destination_country": "US"}
        )
        self.assertEqual(result["destination_country"], {"value": "US", "source": "doc"})

    def test_unknown_doc_key_is_ignored_and_reported(self):
        result = resolve_auto_fields(self.url, self.pool, answers_doc={"not_a_field": "x"})
        self.assertEqual(result["_ignored_doc_keys"], ["not_a_field"])
        self.assertEqual(result["run.pace"], {"value": "standard", "source": "default"})

    def test_never_ask_fields_absent(self):
        result = resolve_auto_fields(self.url, self.pool)
        self.assertNotIn("returns_in_scope", result)
        self.assertNotIn("shopify_opp", result)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 10: Run tests to verify they fail**

Run: `cd plugins/pl-tools/scripts && python3 -m unittest tests.test_resolve_auto_defaults.ResolveAutoFieldsTests -v`
Expected: FAIL/ERROR — `resolve_auto_fields` not defined yet.

- [ ] **Step 11: Implement `resolve_auto_fields`**

```python
# append to resolve_auto_defaults.py

# Every field auto-mode can resolve without asking, and its non-doc default.
# Q1 (returns_in_scope) and Q2 (shopify_opp) are deliberately absent: the
# spec requires those always be asked live, in both modes, never defaulted
# or doc-supplied.
_STATIC_DEFAULTS = {
    "run.pace": "standard",
    "gates.order_lifecycle.gate_c": "send-as-is",
    "edit_mode_fix": True,
}

_NEVER_ASK_FIELDS = frozenset({"returns_in_scope", "shopify_opp"})


def resolve_auto_fields(prospect_url, product_pool, answers_doc=None):
    """Merge inferred/default values with an optional answers doc.

    Precedence per field: answers_doc value, if present and known, else the
    inferred or static default. Unknown doc keys are never applied — they
    are collected in "_ignored_doc_keys" so the caller can report them
    (Beat 1), rather than silently dropped or treated as an error.
    """
    doc = {k: v for k, v in (answers_doc or {}).items() if k not in _NEVER_ASK_FIELDS}

    country = infer_country(prospect_url, product_pool)
    category = infer_category(product_pool)

    fields = {
        "destination_country": {"value": country, "source": "inferred"},
        "cdc.region": {"value": country, "source": "inferred"},
        "cdc.category": {"value": category, "source": "inferred"},
    }
    for key, value in _STATIC_DEFAULTS.items():
        fields[key] = {"value": value, "source": "default"}

    ignored = []
    for key, value in doc.items():
        if key in fields:
            fields[key] = {"value": value, "source": "doc"}
        else:
            ignored.append(key)

    fields["_ignored_doc_keys"] = sorted(ignored)
    return fields
```

- [ ] **Step 12: Run the full test file to verify everything passes**

Run: `cd plugins/pl-tools/scripts && python3 -m unittest tests.test_resolve_auto_defaults -v`
Expected: PASS, all cases green.

- [ ] **Step 13: Add a CLI entry point for use from the skill's shell steps**

```python
# append to resolve_auto_defaults.py, replacing any prior `if __name__` block

def main():
    import argparse
    import json
    import sys

    ap = argparse.ArgumentParser()
    ap.add_argument("--prospect-url", required=True)
    ap.add_argument("--product-pool-file", required=True,
                     help="path to scrape/product-pool.json")
    ap.add_argument("--answers-doc-file", default=None,
                     help="optional path to an auto-mode answers doc")
    args = ap.parse_args()

    try:
        pool = json.loads(Path(args.product_pool_file).read_text())
        answers = None
        if args.answers_doc_file:
            answers = json.loads(Path(args.answers_doc_file).read_text())
        print(json.dumps(resolve_auto_fields(args.prospect_url, pool, answers), indent=2))
    except (ValueError, OSError) as exc:
        print(f"resolve_auto_defaults: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
```

Add `from pathlib import Path` to the imports at the top of the file
alongside the existing `re` and `urllib.parse` imports.

- [ ] **Step 14: Run the full test suite once more to confirm the CLI addition didn't break anything**

Run: `cd plugins/pl-tools/scripts && python3 -m unittest discover -s tests -v`
Expected: PASS, no regressions in any other test file.

- [ ] **Step 15: Commit**

```bash
git add plugins/pl-tools/scripts/resolve_auto_defaults.py plugins/pl-tools/scripts/tests/test_resolve_auto_defaults.py
git commit -m "feat(demo-environment): add auto-mode field resolution (country/category inference, answers-doc merge)"
```

---

### Task 2: `validate_manifest.py` — validate `run.mode` and `run.answers_doc`

**Files:**
- Modify: `plugins/pl-tools/scripts/validate_manifest.py`
- Test: `plugins/pl-tools/scripts/tests/test_validate_manifest.py`

**Interfaces:**
- Consumes: nothing from Task 1 — this task only validates the manifest
  shape, independent of how those fields got their values.
- Produces: manifest validation accepts `run.mode` (absent, `"babysit"`,
  or `"auto"`) and `run.answers_doc` (absent, or any non-empty string).
  Later SKILL.md edits (Task 3) write these fields; this task is what
  makes `validate_manifest.py` accept them instead of rejecting them as
  unknown.

- [ ] **Step 1: Read the existing pace validation to match its style**

```bash
grep -n "PACES\|pace = m.get" plugins/pl-tools/scripts/validate_manifest.py
```

Confirm the exact surrounding code before editing — Task 2 mirrors this
pattern exactly, so read it fresh rather than assuming the shape.

- [ ] **Step 2: Write the failing tests**

Open `plugins/pl-tools/scripts/tests/test_validate_manifest.py`, find an
existing test that builds a minimal valid manifest fixture and calls the
validator (e.g. a `test_pace_*` test), and add, following that file's
existing fixture-building helper rather than duplicating one:

```python
def test_run_mode_absent_is_valid(self):
    manifest = self._minimal_valid_manifest()
    manifest["run"].pop("mode", None)
    ok, errors = validate(manifest, pre_gate=True)
    self.assertTrue(ok, errors)

def test_run_mode_auto_is_valid(self):
    manifest = self._minimal_valid_manifest()
    manifest["run"]["mode"] = "auto"
    ok, errors = validate(manifest, pre_gate=True)
    self.assertTrue(ok, errors)

def test_run_mode_babysit_is_valid(self):
    manifest = self._minimal_valid_manifest()
    manifest["run"]["mode"] = "babysit"
    ok, errors = validate(manifest, pre_gate=True)
    self.assertTrue(ok, errors)

def test_run_mode_invalid_value_rejected(self):
    manifest = self._minimal_valid_manifest()
    manifest["run"]["mode"] = "yolo"
    ok, errors = validate(manifest, pre_gate=True)
    self.assertFalse(ok)
    self.assertTrue(any("run.mode" in e for e in errors))

def test_run_answers_doc_absent_is_valid(self):
    manifest = self._minimal_valid_manifest()
    manifest["run"].pop("answers_doc", None)
    ok, errors = validate(manifest, pre_gate=True)
    self.assertTrue(ok, errors)

def test_run_answers_doc_string_is_valid(self):
    manifest = self._minimal_valid_manifest()
    manifest["run"]["answers_doc"] = "/tmp/answers.json"
    ok, errors = validate(manifest, pre_gate=True)
    self.assertTrue(ok, errors)

def test_run_answers_doc_non_string_rejected(self):
    manifest = self._minimal_valid_manifest()
    manifest["run"]["answers_doc"] = 123
    ok, errors = validate(manifest, pre_gate=True)
    self.assertFalse(ok)
    self.assertTrue(any("run.answers_doc" in e for e in errors))
```

Use whatever the file's actual validator entry point and minimal-fixture
helper are named — read the file first (Step 1's grep plus a look at the
top of the test file) and match those exact names; do not introduce a
second helper if one already exists.

- [ ] **Step 3: Run the new tests to verify they fail**

Run: `cd plugins/pl-tools/scripts && python3 -m unittest tests.test_validate_manifest -v`
Expected: the four value/rejection tests fail (unknown-field or
no-error-raised), the three absent/valid tests may already pass if the
validator currently ignores unrecognized fields — note which is which
before moving on, since that tells you whether validation is additive or
newly strict.

- [ ] **Step 4: Implement the validation**

Next to the existing `pace = m.get("run", {}).get("pace")` block, add:

```python
MODES = {"babysit", "auto"}

mode = m.get("run", {}).get("mode")
if mode is not None:
    need(mode in MODES, f"run.mode must be one of {sorted(MODES)}")

answers_doc = m.get("run", {}).get("answers_doc")
if answers_doc is not None:
    need(
        isinstance(answers_doc, str) and answers_doc.strip(),
        "run.answers_doc must be a non-empty string when present",
    )
```

Place this immediately after the existing pace block so the file's
`run.*` validations stay grouped together. Use whatever the file's actual
error-collection helper is named (the tests above assume it is called
`need`, matching the existing `pace` check — confirm this from Step 1's
grep and adjust if the real name differs).

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd plugins/pl-tools/scripts && python3 -m unittest tests.test_validate_manifest -v`
Expected: PASS, all seven new cases green.

- [ ] **Step 6: Run the full test suite for regressions**

Run: `cd plugins/pl-tools/scripts && python3 -m unittest discover -s tests -v`
Expected: PASS, no regressions.

- [ ] **Step 7: Commit**

```bash
git add plugins/pl-tools/scripts/validate_manifest.py plugins/pl-tools/scripts/tests/test_validate_manifest.py
git commit -m "feat(demo-environment): validate run.mode and run.answers_doc manifest fields"
```

---

### Task 3: `references/intake-script.md` — auto-mode resolution column

**Files:**
- Modify: `plugins/pl-tools/skills/demo-environment/references/intake-script.md`

**Interfaces:**
- Consumes: the field names produced by Task 1's `resolve_auto_fields`
  (`destination_country`, `cdc.region`, `cdc.category`, `run.pace`,
  `gates.order_lifecycle.gate_c`, `edit_mode_fix`) — this task's prose
  must refer to those exact names so a future reader can trace a
  manifest field back to the script that computed it.
- Produces: an "Auto mode" column/section other skill-file readers (and
  Task 4) can point to when describing which questions are unattended.

This is a documentation-only task edited through the mandated
skill-creator workflow, not by hand — per this repo's `CLAUDE.md` rule
that skill files are never hand-rolled or copy-edited.

- [ ] **Step 1: Invoke skill-creator to add the auto-mode resolution content**

Invoke `/anthropic-skills:skill-creator` to edit the existing
`pl-tools:demo-environment` skill, specifically
`references/intake-script.md`. Give it this exact content to add:

1. A new paragraph directly under the "## Round 1" heading:

   > **Auto mode never changes Round 1.** Q1 (returns in scope) and Q2
   > (Shopify opp) are always asked live, exactly as below, in both
   > babysit and auto mode — they decide the build path and are never
   > defaulted or read from an answers doc.

2. A new column, **Auto mode**, added to the Round 2 question table
   (the one with columns `#`, `Question`, `Options`, `Condition`), with
   these exact values per row:

   | # | Auto mode |
   |---|---|
   | 4 | Inferred via `resolve_auto_defaults.infer_country` (TLD, else scraped currency symbol, else `US`) |
   | 5 | Existing default matrix, unchanged |
   | 6 | `standard` |
   | 7 | `send-as-is` |
   | 8 | Region = Q4's resolved value; category via `resolve_auto_defaults.infer_category` |
   | 9 | User's own demo account (existing default) |
   | 10 | Auto-confirmed |
   | 11 | Fix it |
   | 12 | **Blocker** — never defaulted |
   | 13 | Existing fallback: `config_source: "none"` |
   | 14 | **Blocker** — never defaulted |

3. A new section at the end of the file, after "## Questions this script
   deliberately does not contain":

   > ## Auto mode
   >
   > An optional answers doc (flat JSON, keyed by manifest field) may
   > override any Auto-mode value above except Q1/Q2, which are never
   > doc-supplied. `resolve_auto_defaults.resolve_auto_fields` computes
   > the merged result; an unknown doc key is collected, never applied,
   > and reported once in Beat 1. Both hard gates (★ template, ✋ plan)
   > are auto-approved in auto mode — see `SKILL.md`'s "Mode selection"
   > and "Blockers" sections for the trigger phrase and the full blocker
   > list.

- [ ] **Step 2: Verify the content landed correctly**

```bash
grep -n "Auto mode never changes Round 1" plugins/pl-tools/skills/demo-environment/references/intake-script.md
grep -n "resolve_auto_defaults.infer_country" plugins/pl-tools/skills/demo-environment/references/intake-script.md
grep -n "^## Auto mode$" plugins/pl-tools/skills/demo-environment/references/intake-script.md
```

Expected: all three greps find exactly one match each.

- [ ] **Step 3: Run the full script test suite as a regression check**

Run: `cd plugins/pl-tools/scripts && python3 -m unittest discover -s tests -v`
Expected: PASS — a documentation-only change should never affect this,
and a failure here means something else touched these files unexpectedly.

- [ ] **Step 4: Commit**

```bash
git add plugins/pl-tools/skills/demo-environment/references/intake-script.md
git commit -m "docs(demo-environment): add auto-mode resolution column to intake script"
```

---

### Task 4: `SKILL.md` — mode selection, gate auto-approval, blockers, Beat 1 reporting

**Files:**
- Modify: `plugins/pl-tools/skills/demo-environment/SKILL.md`

**Interfaces:**
- Consumes: `resolve_auto_defaults.py`'s CLI (Task 1 Step 13) and
  `resolve_auto_fields`'s return shape (Task 1); `validate_manifest.py`'s
  acceptance of `run.mode`/`run.answers_doc` (Task 2); the Round
  1/2 auto-mode column and the "## Auto mode" section (Task 3).
- Produces: the orchestration behavior this whole plan exists to add —
  no later task consumes this one.

Documentation-only, edited via skill-creator per this repo's `CLAUDE.md`.

- [ ] **Step 1: Invoke skill-creator to add the mode-selection section**

Invoke `/anthropic-skills:skill-creator` to edit `SKILL.md`. Add this
section immediately after the existing "## Paths" section (before
"## Write permissions"):

> ## Mode selection
>
> **Babysit** (default): today's behavior, unchanged — every Round 1/2
> question is asked, both hard gates pause for a human yes.
>
> **Auto**: triggered only by an explicit phrase in the invoking message
> (e.g. "run this in auto mode for Acme", "auto-build the demo for
> Acme") — detect it the same way the prospect URL itself is detected,
> from plain language, never a flag syntax. Record the choice as
> `run.mode: "auto"` in the manifest (absent means babysit, matching
> `run.pace`'s own convention).
>
> In auto mode: Q1 and Q2 are still asked live (see
> `references/intake-script.md`'s "Auto mode never changes Round 1").
> Every other Round 2 question resolves via
> `${CLAUDE_PLUGIN_ROOT}/scripts/resolve_auto_defaults.py`, called once
> the scrape lane's `product-pool.json` exists:
>
> ```bash
> python3 ${CLAUDE_PLUGIN_ROOT}/scripts/resolve_auto_defaults.py \
>   --prospect-url "<url>" \
>   --product-pool-file "<run dir>/scrape/product-pool.json" \
>   --answers-doc-file "<path, if the operator supplied one>"
> ```
>
> Write every resolved field into the manifest exactly where its
> question already writes it (Q4 → `destination_country`, Q6 →
> `run.pace`, Q7 → `gates.order_lifecycle.gate_c`, Q8 →
> `cdc.region`/`cdc.category`, Q11 → the edit-mode fix decision) — Phase
> 1–4 and `validate_manifest.py` do not distinguish an auto-resolved
> field from a human-answered one. If an answers doc was supplied, also
> record `run.answers_doc: "<path>"` in the manifest.
>
> **Both hard gates are auto-approved in auto mode**: at ★ (Phase 0 step
> 8), accept the pre-built template HTML as-is — no screenshot
> round-trip, no chat question. At ✋ (Phase 0 step 9), once
> `validate_manifest.py --pre-gate` passes, treat the plan as approved
> without a chat round-trip. The `mark(d, "gate", ...)` calls still fire
> exactly as documented above, `asked` immediately followed by
> `answered` — telemetry and the run page see no difference from a fast
> human yes. A gate whose underlying artifact failed to render or
> validate is never auto-approved — that becomes a blocker (below), not
> a silent skip.

- [ ] **Step 2: Invoke skill-creator to extend "Failure handling" with blockers**

In the same skill-creator session, extend the existing "## Failure
handling" table (at the end of the file) with this new subsection
directly above it:

> ## Blockers (auto mode)
>
> A blocker is anything auto mode cannot resolve with a default, an
> inference, or the skill's existing retry/fallback rules. On a
> blocker: stop the run, report exactly what is blocked and why (the
> same detail babysit mode's equivalent prompt would give), and wait for
> the operator. This does not change what counts as unrecoverable —
> every case below is already a hard-stop or a reported failure in
> babysit mode; auto mode just reaches it without having asked anything
> else first.
>
> | Blocker | Same as babysit's... |
> |---|---|
> | Q12 — missing write permissions | the existing write-permissions prompt |
> | Q14 — 2+ Shopify stores, no env pin | intake-script Q14 |
> | Missing Shopify CLI | the existing `/pl-setup` pointer |
> | Template publish failure after retry | the publish gate's three-way offer |
> | A lane failure the "Failure handling" table below already reports | that table's own response — reported, run continues past it, never new blocking behavior |
> | A scrape/interview data gap with no resolution rule above | the scrape-failure inline fallback; if that also fails, stop and report |

- [ ] **Step 3: Invoke skill-creator to add the Beat 1 reporting line**

In the same session, add this paragraph to the existing "## Phase 4 —
Report" section, directly after the paragraph beginning "**Beat 1 —
environment built**":

> **In auto mode, Beat 1 also lists every auto-resolved field** — one
> line per field from `resolve_auto_defaults.py`'s output, showing its
> value and source (`default` | `inferred` | `doc`), in the same
> plan-card list style as the rest of Beat 1. Any answers-doc key that
> did not match a known field (`resolve_auto_fields`'s
> `_ignored_doc_keys`) is listed once here as ignored — not an error,
> not a blocker.

- [ ] **Step 4: Update the manifest schema paragraph**

In the same session, update the existing manifest-schema paragraph
(Phase 0 step 9, the long paragraph beginning "**The manifest schema**")
so its `run{…}` field list reads:　`run{…, pace: "standard"|"fast" —
absent means standard, mode: "babysit"|"auto" — absent means babysit,
answers_doc — present only when auto mode used one, page_url — recorded
after the first run-page publish}`. This is a one-line insertion into an
existing sentence, not a new paragraph — do not duplicate the schema
description elsewhere in the file.

- [ ] **Step 5: Verify all the content landed correctly**

```bash
grep -n "^## Mode selection$" plugins/pl-tools/skills/demo-environment/SKILL.md
grep -n "^## Blockers (auto mode)$" plugins/pl-tools/skills/demo-environment/SKILL.md
grep -n "In auto mode, Beat 1 also lists" plugins/pl-tools/skills/demo-environment/SKILL.md
grep -n 'mode: "babysit"|"auto"' plugins/pl-tools/skills/demo-environment/SKILL.md
```

Expected: all four greps find exactly one match each.

- [ ] **Step 6: Confirm the `name:` frontmatter still matches the directory**

```bash
head -5 plugins/pl-tools/skills/demo-environment/SKILL.md
```

Expected: `name: demo-environment` — unchanged. This is the repo's own
documented silent-failure check (a mismatch drops the skill from the
plugin inventory with no error), worth confirming explicitly after any
skill-creator edit.

- [ ] **Step 7: Run the full script test suite as a regression check**

Run: `cd plugins/pl-tools/scripts && python3 -m unittest discover -s tests -v`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add plugins/pl-tools/skills/demo-environment/SKILL.md
git commit -m "feat(demo-environment): add auto mode — mode selection, gate auto-approval, blockers, Beat 1 reporting"
```

---

## Out of scope for this plan (per spec's Non-goals)

- No background-agent/process handoff — auto mode still runs
  synchronously in the current session.
- No changes to Phase 1–4 execution machinery beyond what Task 4 already
  covers (writing the resolved fields into existing manifest slots).
- No new persistent config format beyond the flat-JSON answers doc
  already specified.

## Suggested next step after implementation

A live-run verification in auto mode against a low-risk demo account
(per the spec's Testing section) is manual and should happen after all
four tasks land, not as a task of its own — it exercises the whole
pipeline (scrape → resolve → gates → Beat 1) rather than one component.
