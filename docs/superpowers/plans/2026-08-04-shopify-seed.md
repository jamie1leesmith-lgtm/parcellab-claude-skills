# shopify-seed Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a `pl-tools` skill that takes a prospect URL and loads four of that prospect's real products — four different types, each with real variants — into a Shopify dev store, priced so a size swap, an even cross-product swap, and an uneven swap that takes payment all demo correctly.

**Architecture:** One `SKILL.md` carries the browser-and-CLI workflow as prose; two `references/` files hold the scrape snippets and the GraphQL templates; one pure-logic Python script (`shape_product_mix.py`) owns the price rule and the variant matrix and is unit tested. Image validation reuses `demo-request`'s existing `check_images.mjs`. Products reach Shopify through a single aliased `productSet` call via `shopify store execute --allow-mutations`.

**Tech Stack:** Claude Code skill (markdown), Python 3 stdlib (`unittest`, `decimal`, `itertools`), Shopify CLI 4.6.0, Shopify Admin GraphQL 2026-07, Claude Code Browser pane (`mcp__Claude_Browser__*`).

**Spec:** `docs/superpowers/specs/2026-08-04-shopify-seed-design.md`

## Global Constraints

Every task's requirements implicitly include this section.

- **Skill directory:** `plugins/pl-tools/skills/shopify-seed/`. Frontmatter `name:` **must** equal the directory name `shopify-seed` — a mismatch silently removes the skill from the plugin inventory with no error.
- **No `pl-` prefix** on the skill directory. The `pl-tools:` prefix already namespaces it.
- **`description:` is trigger text, not a label.** Keep the word **parcelLab** spelled out.
- **All internal file references use `${CLAUDE_PLUGIN_ROOT}`.** Never `~/.claude/skills/…`, never a path relative to this repo. Installed users run from `~/.claude/plugins/cache/parcellab-skills/pl-tools/<version>/`.
- **Tests are stdlib `unittest`.** `pytest` is not installed. Never `pip install`. Run with: `cd plugins/pl-tools/scripts && python3 -m unittest discover -s tests -v`
- **Exactly four products** — anything else must raise. `check_images.mjs` also hard-requires exactly 4.
- **Four *different* product types** — a jumper, jeans, shoes, a jacket, not four jumpers. This is strongly preferred but **must not raise**: `product_type` is scraped heuristically from breadcrumbs, so hard-failing a run because two breadcrumbs matched would abort demo prep over unreliable data. Surface it as a warning at the approval gate, where the human can swap a product before anything is written.
- **Every product needs ≥2 variants.** A size swap inside one product is the fastest even-exchange demo and the most common real returns case.
- **One image per product, none per variant.** Every variant of a product shares the product image. Do not use `ProductVariantSetInput.file`.
- **Non-zero stock on every variant in the matrix.** A zero-stock variant is invisible as an exchange target, so the demo silently shows fewer options and looks broken.
- **The uneven demo must be able to go *upward*** — one product priced above the matched pair, so the flow exercises **taking payment**. A merely "different" price is not sufficient; exchanging downward only ever shows a refund.
- **Never fabricate colour values.** Pull real ones or omit the axis.
- **Never document `shopify populate`** — it does not exist, dropped after CLI 2.x.
- **Never document `SHOPIFY_CLI_SKIP_UPDATE_CHECK`** — it is not a real environment variable. The real control is `shopify config autoupgrade off`.
- **`--allow-mutations` is required** on every `shopify store execute` that writes. Reads must omit it.
- **`-s/--store`** is required and takes the `myshopify.com` domain.
- **Dev stores only.** Confirm the destination store by name before the first write. Never a production merchant store.
- **No currency symbols** in any figure the skill reports — dev-store currency varies.
- **Do not modify `plugins/pl-tools/skills/demo-request/`.** It is reused, not changed.
- **Do not add a `version` field to `pl-tools`.** Its version resolves to the git commit SHA deliberately.
- **GitHub: personal account `jamie1leesmith-lgtm` only.** Never the `parcelLab` org. Check `git remote -v` before pushing.
- **Keep the skill terse.** The audience already knows parcelLab; do not explain what a returns portal is.

## The four demos this must produce

Every design decision below traces to one of these. Stated once here so no task loses sight of the point.

| Demo | What makes it possible |
|---|---|
| **Even, inside one product** — swap S for M | ≥2 variants per product |
| **Even, across products** — swap item, nothing to pay | 2 products at the **same** price |
| **Uneven upward** — customer **pays** the balance | ≥1 product priced **above** that pair |
| **Uneven downward** — customer is refunded | a product **below** the pair *(nice to have, never engineered)* |

## File Structure

| Path | Responsibility | Task |
|---|---|---|
| `plugins/pl-tools/scripts/shape_product_mix.py` | Price rule + variant matrix. Pure logic, stdin JSON → stdout JSON. | 1 |
| `plugins/pl-tools/scripts/tests/test_shape_product_mix.py` | `unittest` for the above. | 1 |
| `plugins/pl-tools/skills/shopify-seed/SKILL.md` | The workflow: preflight, store, location, collect, shape, approve, archive, push, verify, report. | 2–5 |
| `plugins/pl-tools/skills/shopify-seed/references/product-scrape.md` | Browser-pane snippets: name, type, price, image, variant axes. | 3 |
| `plugins/pl-tools/skills/shopify-seed/references/mutation-template.md` | `productSet` seed shape, archive mutation, media verification query. | 4 |
| `.claude-plugin/marketplace.json` | Plugin description: five skills → six. | 6 |
| `plugins/pl-tools/.claude-plugin/plugin.json` | Same. | 6 |
| `README.md` | Skill table row + detail section. | 6 |

---

### Task 1: The price rule and the variant matrix

The only real logic in the skill. Pure functions, no I/O beyond stdin/stdout, so it is fully unit testable without Shopify or a browser.

Lives at **plugin** level (`plugins/pl-tools/scripts/`), not skill level, because that is the only location the repo's documented `unittest discover -s tests` command reaches — a skill-level `scripts/tests/` would be silently skipped.

**Files:**
- Create: `plugins/pl-tools/scripts/shape_product_mix.py`
- Test: `plugins/pl-tools/scripts/tests/test_shape_product_mix.py`

**Interfaces:**
- Consumes: nothing (first task).
- Produces, all imported by the test module and invoked by `SKILL.md` Step 4:
  - `normalise_price(value: str | float | int) -> Decimal` — 2dp, `ROUND_HALF_UP`. Raises `ValueError` if unparseable.
  - `shape_prices(prices: list[Decimal]) -> tuple[list[Decimal], list[int], dict]` — returns `(new_prices, adjusted_indices, roles)` where `roles` is `{"pair": [i, j], "higher": k, "lower": m | None}`. Raises `ValueError` unless given exactly 4 prices.
  - `resolve_options(product: dict) -> list[dict]` — returns `[{"name": str, "values": list[str]}]`, always at least one axis with ≥2 values.
  - `build_variants(options: list[dict], price: Decimal, quantity: int, location_id: str) -> list[dict]`
  - `build_mix(payload: dict) -> dict`
  - `main() -> None` — reads stdin JSON, writes stdout JSON, exits 1 on `ValueError`/`KeyError`.
- CLI contract: `python3 shape_product_mix.py < in.json > out.json`

Input payload:

```json
{
  "products": [
    {"name": "Alpine Shell Jacket", "product_type": "Jacket", "price": "129.00",
     "image_url": "https://…/a.jpg", "pdp_url": "https://…",
     "options": [{"name": "Size", "values": ["S", "M", "L"]},
                 {"name": "Colour", "values": ["Black", "Navy"]}]}
  ],
  "location_id": "gid://shopify/Location/123456",
  "prospect_handle": "acme",
  "stock_per_variant": 25
}
```

Output payload:

```json
{
  "products": [
    {"name": "…", "product_type": "Jacket", "original_price": "129.00", "price": "129.00",
     "adjusted": false, "image_url": "…", "pdp_url": "…",
     "options": [{"name": "Size", "values": ["S", "M", "L"]}],
     "variants": [{"option_values": [{"option_name": "Size", "name": "S"}],
                   "price": "129.00", "quantity": 25,
                   "location_id": "gid://shopify/Location/123456"}],
     "variant_count": 3, "tags": ["pl-demo-seed", "pl-prospect-acme"]}
  ],
  "adjustments": [{"name": "…", "from": "…", "to": "…"}],
  "warnings": [],
  "demos": {
    "in_product_even": {"product": "…", "option": "Size", "swap": "S → M"},
    "cross_product_even": ["…", "…"],
    "uneven_upward": {"from": "…", "to": "…", "balance": "35.00"},
    "uneven_downward": {"from": "…", "to": "…", "refund": "20.00"}
  },
  "location_id": "gid://shopify/Location/123456"
}
```

The price rule, and why it is shaped this way:

1. Normalise every price to 2dp.
2. Sort ascending. Consider only the two **adjacent pairs among the three cheapest** — `(0,1)` and `(1,2)`. This deliberately excludes the most expensive product from the pair, which is what guarantees something remains above it for the upward demo.
3. Take whichever pair has the smaller gap; ties go to the cheaper pair. Converge it by lowering the higher price to the lower. **A pair that already matches has a gap of zero, so it wins automatically and nothing is altered.**
4. The most expensive product must now be strictly above the pair price. If it is not — which only happens when every price was identical — nudge it up by `10.00`.
5. The remaining product is left alone. If it happens to sit below the pair price, the downward refund demo is available; report that, never engineer it.

- [ ] **Step 1: Write the failing test**

Create `plugins/pl-tools/scripts/tests/test_shape_product_mix.py`:

```python
import json
import subprocess
import sys
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shape_product_mix import (
    build_mix,
    build_variants,
    normalise_price,
    resolve_options,
    shape_prices,
)

SCRIPT = Path(__file__).resolve().parents[1] / "shape_product_mix.py"


def d(value):
    return Decimal(value)


def prices(*values):
    return [d(v) for v in values]


class NormalisePriceTests(unittest.TestCase):
    def test_strips_currency_symbols(self):
        self.assertEqual(normalise_price("£129.99"), d("129.99"))
        self.assertEqual(normalise_price("$28.00"), d("28.00"))

    def test_handles_decimal_comma(self):
        self.assertEqual(normalise_price("€64,50"), d("64.50"))

    def test_handles_thousands_comma(self):
        self.assertEqual(normalise_price("1,299.00"), d("1299.00"))

    def test_pads_to_two_decimal_places(self):
        self.assertEqual(normalise_price("129.9"), d("129.90"))
        self.assertEqual(normalise_price(28), d("28.00"))

    def test_rounds_half_up(self):
        self.assertEqual(normalise_price("10.005"), d("10.01"))

    def test_rejects_unparseable(self):
        with self.assertRaises(ValueError):
            normalise_price("Price on request")

    def test_rejects_empty(self):
        with self.assertRaises(ValueError):
            normalise_price("")


class ShapePricesTests(unittest.TestCase):
    def test_natural_pair_with_dearer_product_is_untouched(self):
        original = prices("28.00", "28.00", "64.00", "90.00")
        new, adjusted, roles = shape_prices(list(original))
        self.assertEqual(new, original)
        self.assertEqual(adjusted, [])
        self.assertEqual(sorted(roles["pair"]), [0, 1])
        self.assertEqual(roles["higher"], 3)

    def test_all_distinct_converges_closest_eligible_pair_downward(self):
        new, adjusted, roles = shape_prices(prices("28.00", "32.00", "64.00", "90.00"))
        self.assertEqual(new, prices("28.00", "28.00", "64.00", "90.00"))
        self.assertEqual(adjusted, [1])
        self.assertEqual(sorted(roles["pair"]), [0, 1])

    def test_pair_can_be_the_middle_two_when_that_gap_is_smallest(self):
        new, adjusted, roles = shape_prices(prices("10.00", "100.00", "105.00", "110.00"))
        self.assertEqual(new, prices("10.00", "100.00", "100.00", "110.00"))
        self.assertEqual(adjusted, [2])
        self.assertEqual(sorted(roles["pair"]), [1, 2])
        self.assertEqual(roles["lower"], 0)

    def test_all_identical_leaves_pair_and_nudges_the_dearest(self):
        new, adjusted, roles = shape_prices(prices("50.00", "50.00", "50.00", "50.00"))
        self.assertEqual(adjusted, [3])
        self.assertEqual(new[3], d("60.00"))
        self.assertEqual(new[:3], prices("50.00", "50.00", "50.00"))

    def test_dearest_tied_with_pair_is_nudged_above_it(self):
        new, _, roles = shape_prices(prices("90.00", "90.00", "90.00", "10.00"))
        self.assertGreater(new[roles["higher"]], new[roles["pair"][0]])
        self.assertEqual(roles["lower"], 3)

    def test_pair_never_includes_the_dearest_product(self):
        for case in (
            prices("28.00", "32.00", "64.00", "90.00"),
            prices("10.00", "100.00", "105.00", "110.00"),
            prices("50.00", "50.00", "50.00", "50.00"),
            prices("5.00", "5.00", "5.00", "900.00"),
        ):
            new, _, roles = shape_prices(list(case))
            self.assertNotIn(roles["higher"], roles["pair"], case)
            self.assertGreater(new[roles["higher"]], new[roles["pair"][0]], case)

    def test_result_always_supports_even_and_upward_uneven(self):
        for case in (
            prices("28.00", "32.00", "64.00", "90.00"),
            prices("50.00", "50.00", "50.00", "50.00"),
            prices("28.00", "28.00", "64.00", "90.00"),
            prices("5.00", "500.00", "501.00", "999.00"),
            prices("90.00", "90.00", "90.00", "10.00"),
        ):
            new, _, roles = shape_prices(list(case))
            i, j = roles["pair"]
            self.assertEqual(new[i], new[j], case)
            self.assertGreater(new[roles["higher"]], new[i], case)

    def test_lower_is_none_when_nothing_sits_below_the_pair(self):
        _, _, roles = shape_prices(prices("28.00", "28.00", "64.00", "90.00"))
        self.assertIsNone(roles["lower"])

    def test_rejects_anything_other_than_four(self):
        with self.assertRaises(ValueError):
            shape_prices(prices("28.00", "28.00", "64.00"))
        with self.assertRaises(ValueError):
            shape_prices(prices("28.00", "28.00", "64.00", "90.00", "99.00"))


class ResolveOptionsTests(unittest.TestCase):
    def test_two_axes_are_both_kept(self):
        product = {"options": [
            {"name": "Size", "values": ["S", "M", "L"]},
            {"name": "Colour", "values": ["Black", "Navy"]},
        ]}
        axes = resolve_options(product)
        self.assertEqual([a["name"] for a in axes], ["Size", "Colour"])

    def test_single_value_axis_is_dropped(self):
        product = {"options": [
            {"name": "Size", "values": ["S", "M"]},
            {"name": "Colour", "values": ["Black"]},
        ]}
        self.assertEqual([a["name"] for a in resolve_options(product)], ["Size"])

    def test_no_usable_axis_falls_back_to_size(self):
        self.assertEqual(resolve_options({}), [{"name": "Size", "values": ["S", "M", "L"]}])
        self.assertEqual(
            resolve_options({"options": [{"name": "Colour", "values": ["Black"]}]}),
            [{"name": "Size", "values": ["S", "M", "L"]}],
        )

    def test_values_are_capped_at_three(self):
        product = {"options": [{"name": "Size", "values": ["XS", "S", "M", "L", "XL"]}]}
        self.assertEqual(resolve_options(product)[0]["values"], ["XS", "S", "M"])

    def test_duplicate_values_are_removed_in_order(self):
        product = {"options": [{"name": "Size", "values": ["S", "S", "M"]}]}
        self.assertEqual(resolve_options(product)[0]["values"], ["S", "M"])

    def test_every_axis_returned_has_at_least_two_values(self):
        for product in ({}, {"options": []}, {"options": [{"name": "X", "values": ["only"]}]}):
            for axis in resolve_options(product):
                self.assertGreaterEqual(len(axis["values"]), 2, product)


class BuildVariantsTests(unittest.TestCase):
    def test_two_axes_produce_the_cartesian_product(self):
        options = [
            {"name": "Size", "values": ["S", "M", "L"]},
            {"name": "Colour", "values": ["Black", "Navy"]},
        ]
        variants = build_variants(options, d("28.00"), 25, "gid://shopify/Location/1")
        self.assertEqual(len(variants), 6)
        self.assertEqual(
            variants[0]["option_values"],
            [{"option_name": "Size", "name": "S"}, {"option_name": "Colour", "name": "Black"}],
        )

    def test_every_variant_carries_price_stock_and_location(self):
        options = [{"name": "Size", "values": ["S", "M"]}]
        variants = build_variants(options, d("28.00"), 25, "gid://shopify/Location/1")
        for variant in variants:
            self.assertEqual(variant["price"], "28.00")
            self.assertEqual(variant["quantity"], 25)
            self.assertEqual(variant["location_id"], "gid://shopify/Location/1")


class BuildMixTests(unittest.TestCase):
    def payload(self, price_values, types=None, options=None):
        types = types or ["Jumper", "Jeans", "Shoes", "Jacket"]
        return {
            "products": [
                {"name": f"Product {i}", "product_type": types[i], "price": p,
                 "image_url": f"https://x/{i}.jpg", "pdp_url": f"https://x/p/{i}",
                 "options": options if options is not None else [
                     {"name": "Size", "values": ["S", "M", "L"]},
                     {"name": "Colour", "values": ["Black", "Navy"]},
                 ]}
                for i, p in enumerate(price_values)
            ],
            "location_id": "gid://shopify/Location/1",
            "prospect_handle": "acme",
            "stock_per_variant": 25,
        }

    def test_every_variant_of_every_product_has_non_zero_stock(self):
        result = build_mix(self.payload(["28.00", "32.00", "64.00", "90.00"]))
        for product in result["products"]:
            self.assertGreaterEqual(product["variant_count"], 2)
            for variant in product["variants"]:
                self.assertGreater(variant["quantity"], 0)

    def test_every_product_has_at_least_two_variants_even_with_no_options(self):
        result = build_mix(self.payload(["28.00", "32.00", "64.00", "90.00"], options=[]))
        for product in result["products"]:
            self.assertGreaterEqual(product["variant_count"], 2)

    def test_tags_include_seed_and_prospect(self):
        result = build_mix(self.payload(["28.00", "28.00", "64.00", "90.00"]))
        for product in result["products"]:
            self.assertIn("pl-demo-seed", product["tags"])
            self.assertIn("pl-prospect-acme", product["tags"])

    def test_natural_pair_produces_no_adjustments(self):
        result = build_mix(self.payload(["28.00", "28.00", "64.00", "90.00"]))
        self.assertEqual(result["adjustments"], [])
        self.assertTrue(all(not p["adjusted"] for p in result["products"]))

    def test_adjustment_reports_from_and_to_and_keeps_original(self):
        result = build_mix(self.payload(["28.00", "32.00", "64.00", "90.00"]))
        self.assertEqual(len(result["adjustments"]), 1)
        self.assertEqual(result["adjustments"][0]["from"], "32.00")
        self.assertEqual(result["adjustments"][0]["to"], "28.00")
        adjusted = [p for p in result["products"] if p["adjusted"]][0]
        self.assertEqual(adjusted["original_price"], "32.00")
        self.assertEqual(adjusted["price"], "28.00")

    def test_reports_all_four_demos(self):
        result = build_mix(self.payload(["10.00", "100.00", "105.00", "110.00"]))
        demos = result["demos"]
        self.assertIn("→", demos["in_product_even"]["swap"])
        self.assertEqual(len(demos["cross_product_even"]), 2)
        self.assertEqual(demos["uneven_upward"]["balance"], "10.00")
        self.assertEqual(demos["uneven_downward"]["refund"], "90.00")

    def test_downward_demo_is_null_when_unavailable(self):
        result = build_mix(self.payload(["28.00", "28.00", "64.00", "90.00"]))
        self.assertIsNone(result["demos"]["uneven_downward"])

    def test_upward_balance_is_always_positive(self):
        for values in (["28.00", "32.00", "64.00", "90.00"],
                       ["50.00", "50.00", "50.00", "50.00"],
                       ["90.00", "90.00", "90.00", "10.00"]):
            result = build_mix(self.payload(values))
            self.assertGreater(Decimal(result["demos"]["uneven_upward"]["balance"]), 0, values)

    def test_duplicate_product_types_warn_but_do_not_fail(self):
        result = build_mix(self.payload(
            ["28.00", "28.00", "64.00", "90.00"],
            types=["Jumper", "Jumper", "Shoes", "Jacket"],
        ))
        self.assertTrue(any("Jumper" in w for w in result["warnings"]))
        self.assertEqual(len(result["products"]), 4)

    def test_distinct_types_produce_no_warnings(self):
        result = build_mix(self.payload(["28.00", "28.00", "64.00", "90.00"]))
        self.assertEqual(result["warnings"], [])

    def test_rejects_wrong_product_count(self):
        payload = self.payload(["28.00", "28.00", "64.00", "90.00"])
        payload["products"] = payload["products"][:3]
        with self.assertRaises(ValueError):
            build_mix(payload)

    def test_rejects_zero_stock(self):
        payload = self.payload(["28.00", "28.00", "64.00", "90.00"])
        payload["stock_per_variant"] = 0
        with self.assertRaises(ValueError):
            build_mix(payload)

    def test_prices_are_serialised_as_strings(self):
        result = build_mix(self.payload(["28.00", "32.00", "64.00", "90.00"]))
        for product in result["products"]:
            self.assertIsInstance(product["price"], str)


class CliTests(unittest.TestCase):
    def run_script(self, payload):
        return subprocess.run(
            [sys.executable, str(SCRIPT)],
            input=json.dumps(payload), capture_output=True, text=True,
        )

    def payload(self, price_values):
        return {
            "products": [
                {"name": f"P{i}", "product_type": f"T{i}", "price": p,
                 "image_url": f"https://x/{i}.jpg", "pdp_url": f"https://x/{i}",
                 "options": [{"name": "Size", "values": ["S", "M"]}]}
                for i, p in enumerate(price_values)
            ],
            "location_id": "gid://shopify/Location/1",
            "prospect_handle": "acme",
        }

    def test_reads_stdin_and_writes_json_to_stdout(self):
        proc = self.run_script(self.payload(["28.00", "32.00", "64.00", "90.00"]))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(len(json.loads(proc.stdout)["products"]), 4)

    def test_defaults_stock_when_omitted(self):
        proc = self.run_script(self.payload(["28.00", "32.00", "64.00", "90.00"]))
        product = json.loads(proc.stdout)["products"][0]
        self.assertGreater(product["variants"][0]["quantity"], 0)

    def test_exits_non_zero_on_unparseable_price(self):
        proc = self.run_script(self.payload(["Price on request", "32.00", "64.00", "90.00"]))
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("shape_product_mix", proc.stderr)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd plugins/pl-tools/scripts && python3 -m unittest discover -s tests -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'shape_product_mix'`.

- [ ] **Step 3: Write the implementation**

Create `plugins/pl-tools/scripts/shape_product_mix.py`:

```python
#!/usr/bin/env python3
"""Shape scraped prospect products into a mix that supports every exchange demo.

Four demos have to work afterwards:

  * even inside one product   -- swap S for M          -> needs >=2 variants per product
  * even across products      -- swap item, pay nothing -> needs 2 products at one price
  * uneven upward             -- customer PAYS          -> needs a product above that pair
  * uneven downward           -- customer is refunded   -> a product below the pair, if any

The upward case is the one with a direction requirement: exchanging into something more
expensive is what exercises taking payment, so the pair is deliberately chosen from the
three cheapest products, leaving the dearest above it.

Reads a JSON payload on stdin, writes the shaped payload to stdout.
"""

import json
import re
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

TWO_PLACES = Decimal("0.01")
DEFAULT_AXIS = ("S", "M", "L")
DEFAULT_STOCK = 25
MAX_VALUES_PER_AXIS = 3
NUDGE = Decimal("10.00")
SEED_TAG = "pl-demo-seed"
PRODUCT_COUNT = 4


def normalise_price(value):
    """Return value as a 2dp Decimal, tolerating currency symbols and separators."""
    text = str(value).strip()
    if not text:
        raise ValueError("empty price")

    text = re.sub(r"[^\d.,]", "", text)
    if not text:
        raise ValueError(f"no digits in price: {value!r}")

    # "64,50" is a decimal comma; "1,299.00" is a thousands comma.
    if "," in text and "." in text:
        text = text.replace(",", "")
    elif "," in text:
        tail = text.split(",")[-1]
        text = text.replace(",", ".") if len(tail) == 2 else text.replace(",", "")

    try:
        return Decimal(text).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
    except InvalidOperation as exc:
        raise ValueError(f"unparseable price: {value!r}") from exc


def shape_prices(prices):
    """Guarantee a matched pair with a dearer product above it.

    Returns (new_prices, adjusted_indices, roles). Only the two adjacent pairs among the
    three cheapest products are eligible, which is what keeps the dearest free to sit
    above the pair and drive the upward (take payment) demo.
    """
    if len(prices) != PRODUCT_COUNT:
        raise ValueError(f"need exactly {PRODUCT_COUNT} products, got {len(prices)}")

    prices = list(prices)
    adjusted = []
    order = sorted(range(PRODUCT_COUNT), key=lambda i: prices[i])

    candidates = [(order[0], order[1]), (order[1], order[2])]
    # min() keeps the first on a tie, which is the cheaper pair.
    low, high = min(candidates, key=lambda pair: abs(prices[pair[0]] - prices[pair[1]]))

    if prices[high] != prices[low]:
        prices[high] = prices[low]
        adjusted.append(high)
    pair_price = prices[low]

    dearest = order[3]
    if prices[dearest] <= pair_price:
        prices[dearest] = pair_price + NUDGE
        adjusted.append(dearest)

    spare = next(i for i in order[:3] if i not in (low, high))
    roles = {
        "pair": [low, high],
        "higher": dearest,
        "lower": spare if prices[spare] < pair_price else None,
    }
    return prices, sorted(adjusted), roles


def resolve_options(product, default_axis=DEFAULT_AXIS):
    """Return the variant axes to build, always with at least one usable axis.

    A single-value axis cannot demo a swap, so it is dropped. If nothing usable survives,
    fall back to a Size axis — colour values are never invented.
    """
    axes = []
    for option in product.get("options") or []:
        name = str(option.get("name") or "").strip()
        values = []
        for raw in option.get("values") or []:
            value = str(raw).strip()
            if value and value not in values:
                values.append(value)
        if name and len(values) >= 2:
            axes.append({"name": name, "values": values[:MAX_VALUES_PER_AXIS]})

    if not axes:
        axes = [{"name": "Size", "values": list(default_axis)}]
    return axes


def build_variants(options, price, quantity, location_id):
    """Cartesian product of the axes, one variant per combination."""
    combos = [[]]
    for option in options:
        combos = [combo + [(option["name"], value)]
                  for combo in combos for value in option["values"]]

    return [
        {
            "option_values": [{"option_name": name, "name": value} for name, value in combo],
            "price": f"{price}",
            "quantity": quantity,
            "location_id": location_id,
        }
        for combo in combos
    ]


def build_mix(payload):
    products = payload["products"]
    if len(products) != PRODUCT_COUNT:
        raise ValueError(f"need exactly {PRODUCT_COUNT} products, got {len(products)}")

    handle = payload.get("prospect_handle") or "prospect"
    location_id = payload.get("location_id")
    # Distinguish "absent" from an explicit 0 -- `or` would silently turn a zero,
    # which breaks every exchange target, into the default.
    raw_stock = payload.get("stock_per_variant")
    stock = DEFAULT_STOCK if raw_stock is None else int(raw_stock)
    if stock <= 0:
        raise ValueError("stock_per_variant must be greater than zero")

    originals = [normalise_price(p["price"]) for p in products]
    shaped, adjusted_indices, roles = shape_prices(originals)
    tags = [SEED_TAG, f"pl-prospect-{handle}"]

    shaped_products = []
    adjustments = []
    for index, product in enumerate(products):
        options = resolve_options(product)
        was_adjusted = index in adjusted_indices
        shaped_products.append({
            "name": product["name"],
            "product_type": str(product.get("product_type") or "").strip(),
            "original_price": f"{originals[index]}",
            "price": f"{shaped[index]}",
            "adjusted": was_adjusted,
            "image_url": product.get("image_url"),
            "pdp_url": product.get("pdp_url"),
            "options": options,
            "variants": build_variants(options, shaped[index], stock, location_id),
            "tags": tags,
        })
        shaped_products[-1]["variant_count"] = len(shaped_products[-1]["variants"])

        if was_adjusted:
            adjustments.append({
                "name": product["name"],
                "from": f"{originals[index]}",
                "to": f"{shaped[index]}",
            })

    warnings = []
    types = [p["product_type"] for p in shaped_products if p["product_type"]]
    repeated = sorted({t for t in types if types.count(t) > 1})
    if repeated:
        warnings.append(
            "repeated product types, so the cross-product exchange looks like a "
            f"like-for-like swap: {', '.join(repeated)}"
        )

    pair_i, pair_j = roles["pair"]
    dearest, spare = roles["higher"], roles["lower"]
    pair_price = shaped[pair_i]

    # Demo the size swap on whichever product has the most variants.
    showcase = max(shaped_products, key=lambda p: p["variant_count"])
    axis = showcase["options"][0]

    demos = {
        "in_product_even": {
            "product": showcase["name"],
            "option": axis["name"],
            "swap": f"{axis['values'][0]} → {axis['values'][1]}",
        },
        "cross_product_even": [products[pair_i]["name"], products[pair_j]["name"]],
        "uneven_upward": {
            "from": products[pair_i]["name"],
            "to": products[dearest]["name"],
            "balance": f"{shaped[dearest] - pair_price}",
        },
        "uneven_downward": None if spare is None else {
            "from": products[pair_i]["name"],
            "to": products[spare]["name"],
            "refund": f"{pair_price - shaped[spare]}",
        },
    }

    return {
        "products": shaped_products,
        "adjustments": adjustments,
        "warnings": warnings,
        "demos": demos,
        "location_id": location_id,
    }


def main():
    try:
        print(json.dumps(build_mix(json.load(sys.stdin)), indent=2))
    except (ValueError, KeyError) as exc:
        print(f"shape_product_mix: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd plugins/pl-tools/scripts && python3 -m unittest discover -s tests -v
```

Expected: **40 tests, all passing.** This test module and implementation were run together before this plan was written, so a failure here means a transcription slip rather than a design problem — diff against the plan before debugging the logic.

The pre-existing `test_pl_credentials.py` must also still pass. If it fails, confirm it failed before this change and do not fix it here.

- [ ] **Step 5: Commit**

```bash
git add plugins/pl-tools/scripts/shape_product_mix.py plugins/pl-tools/scripts/tests/test_shape_product_mix.py
git commit -m "feat(shopify-seed): add tested price rule and variant matrix builder"
```

---

### Task 2: Skill scaffold — preflight, store resolution, location ID

Creates the skill and the first three workflow steps: the ones that must be right before anything is written.

**Files:**
- Create: `plugins/pl-tools/skills/shopify-seed/SKILL.md`

**Interfaces:**
- Consumes: nothing from Task 1 yet.
- Produces: the `SKILL.md` file that Tasks 3–5 append sections to, and the config path `~/.claude/parcellab-shopify-seed.env` holding `SHOPIFY_DEMO_STORE=<store>.myshopify.com`.

- [ ] **Step 1: Create the skill with skill-creator**

Invoke `anthropic-skills:skill-creator` to scaffold `plugins/pl-tools/skills/shopify-seed/`. Do not hand-roll the structure and do not copy an existing skill directory — that is how conventions drift.

Frontmatter, exactly:

```markdown
---
name: shopify-seed
description: Seed a prospect's own products into a Shopify dev store so you can demo the parcelLab returns and exchanges flow with products the prospect actually sells. Browses the prospect's site for four products of different types, keeps their real size and colour variants, prices them so both even and uneven exchanges demo correctly, and pushes them with the Shopify CLI. Trigger on phrases like "seed [prospect]'s products into my Shopify store", "load [brand] products for an exchange demo", "set up the Shopify demo store for [prospect]", or any request to put a prospect's products into a Shopify dev store for a parcelLab returns demo.
argument-hint: <prospect-url>
---
```

- [ ] **Step 2: Write the overview and Steps 0–2**

Append to `SKILL.md`:

````markdown
# parcelLab — Shopify Prospect Seeding

Load four of a prospect's real products into a Shopify **dev** store, shaped so every
exchange demo works. Run once per prospect, per demo.

Four demos have to be possible when this finishes:

| Demo | Needs |
|---|---|
| Even, inside one product — swap S for M | ≥2 variants per product |
| Even, across products | 2 products at the same price |
| Uneven **upward** — customer pays the balance | 1 product priced above that pair |
| Uneven downward — customer is refunded | a product below the pair *(if the catalogue offers one)* |

Writes to a real store. The destination is confirmed by name before the first write.

---

## Step 0 — Preflight

```bash
command -v shopify && shopify version
```

If missing, install it. `brew install shopify-cli` alone fails — the formula is not in
homebrew-core and Homebrew refuses to load it until the tap is trusted:

```bash
brew tap shopify/shopify
brew trust shopify/shopify
brew install shopify-cli
```

Then, **before anything else**:

```bash
shopify config autoupgrade off
```

A self-upgrade firing mid-session uninstalls the CLI, fails to install the replacement,
and leaves a dangling symlink with no working `shopify` command. One command avoids it.

> `shopify populate` does not exist — it was dropped after CLI 2.x.
> `SHOPIFY_CLI_SKIP_UPDATE_CHECK` is not a real environment variable; setting it does
> nothing. `shopify config autoupgrade off` is the real control.

---

## Step 1 — Resolve the destination store

Read the stored store first:

```bash
cat ~/.claude/parcellab-shopify-seed.env 2>/dev/null
```

**If `SHOPIFY_DEMO_STORE` is set and the user has not named a different store:** use it,
state which store you are using in your output, and do not ask again.

**If it is not set,** list the stores the user has actually authenticated:

```bash
shopify store auth list
```

That prints a `Subdomain` / `Connected` table. Note `shopify store list` is a different
command — it covers *organisation* stores and returns "No stores found" for a
directly-authenticated dev store, which is not an error.

- Exactly one store → confirm it **by name** and get an explicit yes.
- Several → ask which one.
- None → authenticate, warning the user that **a browser consent window will open**:

```bash
shopify store auth -s <store>.myshopify.com --scopes write_products,write_inventory
```

Once confirmed, persist it:

```bash
echo 'SHOPIFY_DEMO_STORE=<store>.myshopify.com' > ~/.claude/parcellab-shopify-seed.env
```

A config file rather than an env var: env vars are read only at app startup, so a value
written here would stay invisible until a full quit (⌘Q).

**Dev stores only.** Never a production merchant store. Say the store name out loud at
the confirmation so a wrong target is caught before any write.

---

## Step 2 — Resolve the location ID

Stock needs a location ID, and it is per-store. Fetch it rather than asking the user to
dig it out of an Admin URL:

```bash
shopify store execute -s "$SHOPIFY_DEMO_STORE" \
  --query '{ locations(first: 5) { nodes { id name isActive } } }'
```

Read-only, so **no `--allow-mutations`** — that flag is only for writes.

Take the first node with `isActive: true`. The `id` comes back as
`gid://shopify/Location/123456`, which is exactly what `ProductSetInventoryInput.locationId`
expects. No numeric-ID conversion needed.

If no active location exists, stop and tell the user — stock cannot be set without one.
````

- [ ] **Step 3: Verify the silent failure modes**

```bash
cd plugins/pl-tools/skills/shopify-seed
grep -m1 '^name:' SKILL.md
basename "$PWD"
```

Expected: the `name:` value and the directory name are both `shopify-seed`. A mismatch removes the skill from the inventory with no error.

```bash
grep -c 'parcelLab' SKILL.md
grep -rn 'shopify populate\|SHOPIFY_CLI_SKIP_UPDATE_CHECK' . ; echo "forbidden-strings-exit:$?"
```

Expected: at least one `parcelLab` hit in the description; `forbidden-strings-exit:1` (grep found nothing).

- [ ] **Step 4: Verify the skill is actually discoverable**

```bash
cd /Users/jamie.lee-smith/Documents/Claude/Projects/parcellab-claude-skills
claude plugin validate ./plugins/pl-tools 2>&1 | tail -20
```

Expected: `shopify-seed` appears in the inventory. A `"No version specified"` warning is **expected and correct** for `pl-tools` — do not fix it by adding a version.

- [ ] **Step 5: Commit**

```bash
git add plugins/pl-tools/skills/shopify-seed/
git commit -m "feat(shopify-seed): scaffold skill with preflight, store and location resolution"
```

---

### Task 3: Product collection and the approval gate

**Files:**
- Create: `plugins/pl-tools/skills/shopify-seed/references/product-scrape.md`
- Modify: `plugins/pl-tools/skills/shopify-seed/SKILL.md` (append Steps 3–5)

**Interfaces:**
- Consumes: `shape_product_mix.py` from Task 1 (stdin JSON → stdout JSON, contract as defined there); `SHOPIFY_DEMO_STORE` and the location GID from Task 2.
- Produces: an approved shaped-products JSON file in the scratchpad that Task 4 turns into a mutation.

- [ ] **Step 1: Write the scrape reference**

Create `references/product-scrape.md`. The image-scoring function is lifted verbatim from `demo-request`, which is proven; price, type and variant-axis extraction are new.

````markdown
# Prospect product scraping

Uses Claude Code's built-in **Browser pane** (`mcp__Claude_Browser__*`) — the same as
`demo-request`, `branded-template` and `order-lifecycle`. Not Claude-in-Chrome, not
Playwright.

`mcp__Claude_Browser__javascript_tool` evaluates an *expression*, so every snippet is
wrapped as an IIFE — `(() => {…})()`. Keep it that way; a bare `() => {…}` returns the
function instead of calling it.

## What to collect

**Four products of four different types** — a jumper, jeans, shoes, a jacket. Not four
jumpers: the cross-product exchange should look like a real decision, not a like-for-like
swap.

**A couple of values from each variant axis the site exposes**, typically Size and Colour,
or shoe size. Every product needs **at least two variants** so a small→medium swap
demonstrates an even exchange inside that one product — the most common real returns case
and the quickest thing to show.

Only **one image per product** is needed. Variants share it, so there is no need to find a
photo per colour.

## Find listing pages, then PDP links

Reuse `demo-request` Steps 2 and 3 verbatim — the listing-link and PDP-link snippets there
already work. Aim for at least 8 PDP candidates across **different categories** before
choosing four.

## Extract name, type, price, image and variant axes from a PDP

```javascript
(() => {
  const clean = (s) => (s || '').trim().replace(/\s+/g, ' ');

  const name = clean(
    document.querySelector('h1')?.innerText ||
    document.querySelector('[class*="product-name"], [class*="product-title"], [itemprop="name"]')?.innerText ||
    document.title
  ).slice(0, 120);

  // Product type: breadcrumb tail is the most reliable signal, then meta.
  const crumbs = Array.from(
    document.querySelectorAll('[class*="breadcrumb"] a, nav[aria-label*="readcrumb"] a')
  ).map(a => clean(a.innerText)).filter(Boolean);
  const productType = clean(
    crumbs[crumbs.length - 1] ||
    document.querySelector('meta[property="product:category"]')?.content ||
    ''
  ).slice(0, 40);

  // Price, most reliable source first. JSON-LD beats reading rendered text.
  let price = null;
  for (const node of document.querySelectorAll('script[type="application/ld+json"]')) {
    try {
      const blocks = [].concat(JSON.parse(node.textContent));
      for (const block of blocks) {
        const offers = [].concat(block.offers || block['@graph'] || []);
        for (const offer of offers) {
          const p = offer?.price ?? offer?.lowPrice ?? offer?.priceSpecification?.price;
          if (p) { price = String(p); break; }
        }
        if (price) break;
      }
    } catch { /* malformed JSON-LD is common; skip it */ }
    if (price) break;
  }
  if (!price) price = document.querySelector('meta[property="product:price:amount"]')?.content || null;
  if (!price) {
    const text = document.querySelector('[class*="price"], [itemprop="price"]')?.innerText || '';
    price = (text.match(/\d[\d.,]*/) || [null])[0];
  }

  // Variant axes. Real values only — never invent a colour.
  const axes = [];
  const seenAxis = new Set();
  const pushAxis = (rawName, rawValues) => {
    const axisName = clean(rawName).replace(/[:*]/g, '').trim();
    if (!axisName || seenAxis.has(axisName.toLowerCase())) return;
    const values = [...new Set(
      rawValues.map(v => clean(String(v)))
        .filter(v => v && v.length <= 20 && !/select|choose|guide|please/i.test(v))
    )];
    if (values.length >= 2) {
      seenAxis.add(axisName.toLowerCase());
      axes.push({ name: axisName, values: values.slice(0, 3) });
    }
  };

  // Shopify storefronts embed product JSON with the real options.
  for (const node of document.querySelectorAll('script[type="application/json"]')) {
    try {
      const data = JSON.parse(node.textContent);
      const product = data?.product || data;
      if (Array.isArray(product?.options)) {
        product.options.forEach((opt, i) => {
          const optName = opt?.name || opt;
          const values = opt?.values
            || (product.variants || []).map(v => v?.[`option${i + 1}`]).filter(Boolean);
          pushAxis(String(optName), values || []);
        });
      }
    } catch { /* not product JSON; skip */ }
  }

  // Fallback: labelled selects and swatch groups in the DOM.
  if (!axes.length) {
    for (const group of document.querySelectorAll(
      'select, fieldset, [data-option-name], [class*="swatch"], [class*="variant-option"]'
    )) {
      const label = group.getAttribute('data-option-name')
        || group.getAttribute('aria-label')
        || group.querySelector('legend, label')?.innerText
        || group.getAttribute('name') || '';
      if (!/size|colour|color/i.test(label)) continue;
      const values = Array.from(
        group.querySelectorAll('option, label, button, [role="radio"]')
      ).map(n => n.value || n.innerText || '');
      pushAxis(label, values);
    }
  }

  // Image scoring — verbatim from demo-request, which is proven.
  const score = (img) => {
    let s = 0;
    const src = (img.currentSrc || img.src || '').toLowerCase();
    const alt = (img.alt || '').toLowerCase();
    const r = img.getBoundingClientRect();
    if (r.width >= 400) s += 10;
    if (r.width >= 600) s += 5;
    if (img.naturalWidth >= 600) s += 8;
    if (img.naturalWidth >= 1000) s += 4;
    if (alt.length > 3) s += 3;
    if (src.includes('product') || src.includes('item') || src.includes('pdp')) s += 6;
    if (src.includes('thumb') || src.includes('icon') || src.includes('logo')) s -= 10;
    if (src.startsWith('data:')) s -= 20;
    if (src.endsWith('.svg')) s -= 10;
    if (src.includes('placeholder') || src.includes('lazy') || src.includes('blank')) s -= 15;
    if (src.includes('tracking') || src.includes('pixel')) s -= 20;
    if (img.closest('[class*="gallery"], [class*="carousel"], [class*="product"]')) s += 5;
    return s;
  };
  const bestImg = Array.from(document.querySelectorAll('img'))
    .filter(img => (img.currentSrc || img.src) && !(img.currentSrc || img.src).startsWith('data:'))
    .sort((a, b) => score(b) - score(a))[0];

  return {
    name,
    product_type: productType,
    price,
    options: axes,
    image_url: bestImg ? (bestImg.currentSrc || bestImg.src) : null,
    pdp_url: location.href,
  };
})()
```

Set `product_type` yourself from the product name if the breadcrumb comes back empty — a
short label like `Jumper`, `Jeans`, `Trainers` is all it needs to be.

## Edge cases

- **Consent modal** — `read_page` with `{ filter: "interactive" }` for `ref_N` handles,
  then click the dismiss control. **Decline non-essential cookies**, never accept all.
- **Lazy-loaded images** — scroll before scoring:
  `(() => { window.scrollTo(0, document.body.scrollHeight / 2); return true; })()`
- **Variant axes come back empty** — fine. The shaping script falls back to a Size axis of
  `S`/`M`/`L`, which still gives the in-product size swap. **Do not invent colour values**
  to fill the gap; a product photographed in red offered as "Navy" looks broken.
- **A variant picker that needs a click to reveal values** — click it, re-run the snippet.
  Not worth more than one attempt per product; the Size fallback is acceptable.
- **Price still null** — ask the user for that product's price rather than inventing one. A
  fabricated price in a demo to that prospect is worse than a question.
- **Bot protection / near-empty page text** — say so and stop. Do not work around a block.
- **Login wall** — out of scope. The pane runs a fresh context with no saved sessions.
````

- [ ] **Step 2: Append Steps 3–5 to SKILL.md**

````markdown
---

## Step 3 — Collect four of the prospect's products

Open the pane on the prospect URL:

`mcp__Claude_Browser__preview_start` with `{ url: "<prospect URL>" }`.

Use `preview_start` for the *first* page and `mcp__Claude_Browser__navigate` for every page
after — calling `navigate` before a pane exists fails with *"No preview is open"*.

Confirm the page loaded with `mcp__Claude_Browser__get_page_text` (`{ max_chars: 2000 }`)
before scraping — cheaper and more reliable than a screenshot for spotting a consent wall
or a bot block.

Then follow `${CLAUDE_PLUGIN_ROOT}/skills/shopify-seed/references/product-scrape.md` to
collect exactly four products as
`{ name, product_type, price, options, image_url, pdp_url }`.

**Four different product types**, and **a couple of values from each variant axis the site
exposes**. One image per product — variants share it.

### Validate the images

Write the four products to a scratchpad file, then reuse `demo-request`'s checker:

```bash
node ${CLAUDE_PLUGIN_ROOT}/skills/demo-request/scripts/check_images.mjs /tmp/seed-products.json
```

It expects exactly 4 products, prints a JSON result per image, and **exits non-zero if any
fails**. It retries HEAD as a ranged GET on 403/405, which is the hotlink-protected CDN
case — and that same protection will later defeat Shopify's own server-side fetch, so an
image failing here will not work in Step 8 either. Replace it now.

If an image fails, go back to that PDP and pick the next-best-scoring image. If none work,
ask the user for a direct image URL.

---

## Step 4 — Shape the mix

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/shape_product_mix.py < /tmp/seed-products.json > /tmp/seed-shaped.json
```

Input keys: `products[]` (`name`, `product_type`, `price`, `options`, `image_url`,
`pdp_url`), `location_id`, `prospect_handle`, optional `stock_per_variant` (defaults to 25).

What it does, and why:

- Builds the **variant matrix** — the cartesian product of the axes, so Size×Colour gives 6
  variants — with non-zero stock on every one. A zero-stock variant is invisible as an
  exchange target, so the demo silently shows fewer options and looks broken.
- Drops any single-value axis, and falls back to `S`/`M`/`L` if no axis survives, so every
  product ends with **≥2 variants**.
- Picks a **matched pair from the three cheapest products**, leaving the dearest above it.
  That is what makes the uneven demo go *upward* and exercise taking payment — a merely
  "different" price could be satisfied by exchanging downward and never show that step.
- **Changes nothing at all** when the catalogue already has a natural pair and a dearer
  item, which is the common case. At most two prices ever move.

Read `warnings` from the output — repeated product types are surfaced there. It exits
non-zero on an unparseable price.

---

## Step 5 — Approval gate

Show the destination store **by name**, then:

| # | Product | Type | Real price | Seeded price | Adjusted | Variants | Image |
|---|---|---|---|---|---|---|---|

Then, straight from the script's `demos` output:

- **Even, in-product:** *[product]*, *[option]* *[swap]*
- **Even, cross-product:** *[A]* ↔ *[B]*
- **Uneven upward — customer pays:** *[A]* → *[D]*, balance *[balance]*
- **Uneven downward — refund:** *[A]* → *[C]*, refund *[refund]* — or *not available*

Call out any adjustment as `was → now`; these are the only places real prospect data was
altered. Surface any `warnings` too, and offer to swap a product out.

Quote figures **without currency symbols**; dev-store currency varies.

**No writes before an explicit yes.**
````

- [ ] **Step 3: Verify the reference is reachable and the reuse path is real**

```bash
cd /Users/jamie.lee-smith/Documents/Claude/Projects/parcellab-claude-skills/plugins/pl-tools
test -f skills/demo-request/scripts/check_images.mjs && echo "reuse target exists"
grep -c 'CLAUDE_PLUGIN_ROOT' skills/shopify-seed/SKILL.md
grep -rn '~/.claude/skills' skills/shopify-seed/ ; echo "bad-path-exit:$?"
git status --porcelain skills/demo-request/
```

Expected: `reuse target exists`; at least 3 `${CLAUDE_PLUGIN_ROOT}` uses; `bad-path-exit:1`; and **empty** `git status` for `demo-request` — it must not be modified.

- [ ] **Step 4: Verify the script path in SKILL.md resolves as written**

```bash
CLAUDE_PLUGIN_ROOT=/Users/jamie.lee-smith/Documents/Claude/Projects/parcellab-claude-skills/plugins/pl-tools
test -f "$CLAUDE_PLUGIN_ROOT/scripts/shape_product_mix.py" && echo "script path correct"
```

Expected: `script path correct`. This catches a skill-level vs plugin-level path mistake before a live run.

- [ ] **Step 5: Verify the documented input contract matches the script**

Feed the script exactly the shape `SKILL.md` promises, and confirm it is accepted:

```bash
cd /Users/jamie.lee-smith/Documents/Claude/Projects/parcellab-claude-skills
python3 - <<'EOF' > /tmp/contract-check.json
import json
print(json.dumps({
    "products": [
        {"name": f"P{i}", "product_type": t, "price": p,
         "image_url": f"https://x/{i}.jpg", "pdp_url": f"https://x/{i}",
         "options": [{"name": "Size", "values": ["S", "M", "L"]},
                     {"name": "Colour", "values": ["Black", "Navy"]}]}
        for i, (t, p) in enumerate([("Jumper", "28.00"), ("Jeans", "28.00"),
                                    ("Trainers", "64.00"), ("Jacket", "90.00")])
    ],
    "location_id": "gid://shopify/Location/1",
    "prospect_handle": "acme",
}))
EOF
python3 plugins/pl-tools/scripts/shape_product_mix.py < /tmp/contract-check.json \
  | python3 -c 'import json,sys; r=json.load(sys.stdin); print("variants:", [p["variant_count"] for p in r["products"]]); print("adjustments:", r["adjustments"]); print("upward:", r["demos"]["uneven_upward"])'
```

Expected exactly this — these figures were confirmed by running the finished script:

```
variants: [6, 6, 6, 6]
adjustments: []
upward: {'from': 'P0', 'to': 'P3', 'balance': '62.00'}
```

`adjustments: []` is the important one: the natural pair at 28.00 with a dearer product above it means **no real price was altered**. If the key names differ from what `SKILL.md` documents, fix `SKILL.md` — the script is the contract.

- [ ] **Step 6: Commit**

```bash
git add plugins/pl-tools/skills/shopify-seed/
git commit -m "feat(shopify-seed): add product collection, variant scraping and approval gate"
```

---

### Task 4: Archive the previous prospect, then push

**Files:**
- Create: `plugins/pl-tools/skills/shopify-seed/references/mutation-template.md`
- Modify: `plugins/pl-tools/skills/shopify-seed/SKILL.md` (append Steps 6–7)

**Interfaces:**
- Consumes: the approved `/tmp/seed-shaped.json` from Task 3; `SHOPIFY_DEMO_STORE`; the location GID.
- Produces: created product IDs, which Task 5 re-queries to verify media.

- [ ] **Step 1: Write the mutation reference**

Create `references/mutation-template.md`. Every field below was verified against the 2026-07 Admin GraphQL schema — reuse these shapes rather than composing new ones.

````markdown
# Verified GraphQL shapes

Verified against Shopify Admin GraphQL **2026-07**. Always request
`userErrors { field message }` — a silent partial failure is worse than an error.

## Find the previous seed

Read-only, so **no `--allow-mutations`**:

```graphql
{
  products(first: 50, query: "tag:pl-demo-seed status:active") {
    nodes { id title }
  }
}
```

## Archive it

`productUpdate` takes **`product: ProductUpdateInput`**. The older `input: ProductInput`
argument is **deprecated** — do not use it. `ProductStatus` valid values are `ACTIVE`,
`ARCHIVED`, `DRAFT` and `UNLISTED`.

One aliased call per product found above:

```graphql
mutation ArchivePreviousSeed($p0: ProductUpdateInput!, $p1: ProductUpdateInput!) {
  a0: productUpdate(product: $p0) {
    product { id title status }
    userErrors { field message }
  }
  a1: productUpdate(product: $p1) {
    product { id title status }
    userErrors { field message }
  }
}
```

Variables:

```json
{
  "p0": { "id": "gid://shopify/Product/111", "status": "ARCHIVED" },
  "p1": { "id": "gid://shopify/Product/222", "status": "ARCHIVED" }
}
```

Archiving is reversible — the products leave the storefront and the returns portal but
nothing is destroyed.

## Create the new seed

`productSet(synchronous: true, input: ProductSetInput!)`, one aliased call per product so
a single command creates all four.

Confirmed input fields:

- `ProductSetInput` — `title`, `productType`, `status`, `tags`, `productOptions`, `variants`, `files`
- `OptionSetInput` — `name`, `position`, `values`
- `ProductVariantSetInput` — `price`, `published`, `optionValues`, `inventoryQuantities`
- `VariantOptionValueInput` — `optionName`, `name`
- `ProductSetInventoryInput` — `locationId`, `name` (use `"available"`), `quantity`
- `FileSetInput` — `originalSource`, `alt`, `filename`, `contentType`, `duplicateResolutionMode`

**Images ship in this same mutation** via `files`. `originalSource` explicitly accepts an
external URL. `contentType` is optional — Shopify sniffs it — but pass `IMAGE` for clarity.

**One image per product, none per variant.** `ProductVariantSetInput.file` exists, and any
variant file must also appear in the product's `files` array — but this skill does not use
it. Every variant of a product shares the single product image, which is all the demo
needs and removes the job of sourcing a photo per colour.

```graphql
mutation SeedProspectProducts(
  $product1: ProductSetInput!
  $product2: ProductSetInput!
  $product3: ProductSetInput!
  $product4: ProductSetInput!
) {
  p1: productSet(synchronous: true, input: $product1) {
    product { id title handle }
    userErrors { field message }
  }
  p2: productSet(synchronous: true, input: $product2) {
    product { id title handle }
    userErrors { field message }
  }
  p3: productSet(synchronous: true, input: $product3) {
    product { id title handle }
    userErrors { field message }
  }
  p4: productSet(synchronous: true, input: $product4) {
    product { id title handle }
    userErrors { field message }
  }
}
```

Variables, per product. Prices are unitless strings; `locationId` is the GID from Step 2.
`productOptions` mirrors the axes, and `variants` is the full cartesian product — every
combination present, every one stocked:

```json
{
  "product1": {
    "title": "Alpine Shell Jacket",
    "productType": "Jacket",
    "status": "ACTIVE",
    "tags": ["pl-demo-seed", "pl-prospect-acme"],
    "files": [
      { "originalSource": "https://cdn.example.com/jacket.jpg", "contentType": "IMAGE", "alt": "Alpine Shell Jacket" }
    ],
    "productOptions": [
      { "name": "Size", "position": 1, "values": [{ "name": "S" }, { "name": "M" }] },
      { "name": "Colour", "position": 2, "values": [{ "name": "Black" }, { "name": "Navy" }] }
    ],
    "variants": [
      {
        "optionValues": [{ "optionName": "Size", "name": "S" }, { "optionName": "Colour", "name": "Black" }],
        "price": "129.00",
        "published": true,
        "inventoryQuantities": [
          { "locationId": "gid://shopify/Location/123456", "name": "available", "quantity": 25 }
        ]
      },
      {
        "optionValues": [{ "optionName": "Size", "name": "S" }, { "optionName": "Colour", "name": "Navy" }],
        "price": "129.00",
        "published": true,
        "inventoryQuantities": [
          { "locationId": "gid://shopify/Location/123456", "name": "available", "quantity": 25 }
        ]
      },
      {
        "optionValues": [{ "optionName": "Size", "name": "M" }, { "optionName": "Colour", "name": "Black" }],
        "price": "129.00",
        "published": true,
        "inventoryQuantities": [
          { "locationId": "gid://shopify/Location/123456", "name": "available", "quantity": 25 }
        ]
      },
      {
        "optionValues": [{ "optionName": "Size", "name": "M" }, { "optionName": "Colour", "name": "Navy" }],
        "price": "129.00",
        "published": true,
        "inventoryQuantities": [
          { "locationId": "gid://shopify/Location/123456", "name": "available", "quantity": 25 }
        ]
      }
    ]
  }
}
```

Every variant of a product carries the same price — that is what makes the in-product size
swap an *even* exchange.

`productOptions[].position` is 1-based and must match the order the axes appear in
`optionValues`.

## Verify the media actually landed

```graphql
{
  products(first: 4, query: "tag:pl-demo-seed status:active") {
    nodes {
      id
      title
      media(first: 1) {
        nodes {
          status
          mediaErrors { code details }
          ... on MediaImage { image { url } }
        }
      }
    }
  }
}
```
````

- [ ] **Step 2: Append Steps 6–7 to SKILL.md**

````markdown
---

## Step 6 — Archive the previous prospect's products

Only after the Step 5 approval.

Every product this skill creates carries the tags `pl-demo-seed` and
`pl-prospect-<handle>`, which is what makes cleanup possible. Find the previous run:

```bash
shopify store execute -s "$SHOPIFY_DEMO_STORE" \
  --query '{ products(first: 50, query: "tag:pl-demo-seed status:active") { nodes { id title } } }'
```

If any come back, archive them using the aliased `productUpdate` shape in
`${CLAUDE_PLUGIN_ROOT}/skills/shopify-seed/references/mutation-template.md`:

```bash
shopify store execute -s "$SHOPIFY_DEMO_STORE" \
  --query-file /tmp/archive.graphql --variable-file /tmp/archive.json --allow-mutations
```

Archived products leave the storefront and the returns portal but are **not destroyed** —
un-archive in the Admin to recover them. Report what was archived, by name.

If nothing is tagged, say so and move on — a first run against a clean store is normal.

---

## Step 7 — Push the new products

Generate `/tmp/seed.graphql` and `/tmp/seed.json` from
`${CLAUDE_PLUGIN_ROOT}/skills/shopify-seed/references/mutation-template.md`, mapping the
shaped output onto the mutation:

- `options[]` → `productOptions[]`, with 1-based `position`
- `variants[].option_values[]` → `optionValues[]` (`option_name` → `optionName`)
- `variants[].quantity` and `location_id` → `inventoryQuantities[]` with `name: "available"`
- `image_url` → a single `files[]` entry with `contentType: IMAGE`
- `product_type` → `productType`, `tags` → `tags`

These files are generated per run, not shipped — the products differ every time.

```bash
shopify store execute -s "$SHOPIFY_DEMO_STORE" \
  --query-file /tmp/seed.graphql --variable-file /tmp/seed.json --allow-mutations
```

`--allow-mutations` is mandatory for writes — without it the mutation is refused. Treat
that as a safety feature, not an annoyance. `--query-file` and `--query` are mutually
exclusive, as are `--variable-file` and `--variables`.

Check `userErrors` on **every alias**, not just the first. Any non-empty `userErrors` →
report it and stop; do not continue to verification with a partial seed.
````

- [ ] **Step 3: Verify the deprecated argument is not used and variant files are absent**

```bash
cd /Users/jamie.lee-smith/Documents/Claude/Projects/parcellab-claude-skills/plugins/pl-tools/skills/shopify-seed
grep -n 'productUpdate(input:' references/mutation-template.md ; echo "deprecated-arg-exit:$?"
grep -c 'productUpdate(product:' references/mutation-template.md
grep -c 'userErrors' references/mutation-template.md
grep -n '"file":' references/mutation-template.md ; echo "variant-file-exit:$?"
```

Expected: `deprecated-arg-exit:1`; at least 1 `productUpdate(product:`; at least 4 `userErrors`; `variant-file-exit:1` — no per-variant image.

- [ ] **Step 4: Verify the mutation validates against the live schema**

Do not skip this — it is the only check that catches a wrong field name before a live run, and every field in the template came from docs rather than from the store's own schema.

The seed files are generated per run and do not exist yet, so build a throwaway sample from the template first. Resolve a real location GID for it:

```bash
STORE=parcellab-demo-jls.myshopify.com
LOC=$(shopify store execute -s "$STORE" \
  --query '{ locations(first: 1) { nodes { id } } }' \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["data"]["locations"]["nodes"][0]["id"])')
echo "$LOC"
```

Write a one-product, two-axis sample using that GID — the two-axis case is the one that exercises `productOptions[].position` and multi-entry `optionValues`:

```bash
cat > /tmp/schema-check.graphql <<'EOF'
mutation SchemaCheck($product1: ProductSetInput!) {
  p1: productSet(synchronous: true, input: $product1) {
    product { id title handle }
    userErrors { field message }
  }
}
EOF

python3 - "$LOC" > /tmp/schema-check.json <<'EOF'
import itertools, json, sys
loc = sys.argv[1]
sizes, colours = ["S", "M"], ["Black", "Navy"]
print(json.dumps({"product1": {
    "title": "Schema Check Product",
    "productType": "Jacket",
    "status": "ACTIVE",
    "tags": ["pl-demo-seed", "pl-prospect-schemacheck"],
    "files": [{"originalSource": "https://cdn.shopify.com/s/files/1/0533/2089/files/placeholder.jpg",
               "contentType": "IMAGE", "alt": "Schema Check Product"}],
    "productOptions": [
        {"name": "Size", "position": 1, "values": [{"name": s} for s in sizes]},
        {"name": "Colour", "position": 2, "values": [{"name": c} for c in colours]},
    ],
    "variants": [
        {"optionValues": [{"optionName": "Size", "name": s},
                          {"optionName": "Colour", "name": c}],
         "price": "28.00", "published": True,
         "inventoryQuantities": [{"locationId": loc, "name": "available", "quantity": 25}]}
        for s, c in itertools.product(sizes, colours)
    ],
}}, indent=2))
EOF
```

Now run it **without `--allow-mutations`**. That makes the CLI refuse the *mutation* while still validating the document against the schema:

```bash
shopify store execute -s "$STORE" \
  --query-file /tmp/schema-check.graphql --variable-file /tmp/schema-check.json 2>&1 | head -20
```

Expected: a refusal about mutations not being allowed. That is **success** — it means every field, argument and input type resolved.

A failure mentioning an **unknown field, unknown argument, or unknown input type** means the template is wrong. Fix `references/mutation-template.md` before Task 5, and re-run this check.

No product is created by this step. Run the same check on the archive document during Task 7, once a live run has produced a real product ID to reference.

- [ ] **Step 5: Commit**

```bash
git add plugins/pl-tools/skills/shopify-seed/
git commit -m "feat(shopify-seed): add archive-previous and productSet push steps"
```

---

### Task 5: Verify images landed, then report

The step that stops a demo failing silently.

**Files:**
- Modify: `plugins/pl-tools/skills/shopify-seed/SKILL.md` (append Steps 8–9)

**Interfaces:**
- Consumes: the product IDs created in Task 4; the `demos`, `adjustments` and `warnings` fields produced by `build_mix` in Task 1.
- Produces: the final user-facing report. Nothing downstream.

- [ ] **Step 1: Append Steps 8–9 to SKILL.md**

````markdown
---

## Step 8 — Verify the images actually landed

**Empty `userErrors` does not mean the images arrived.** Shopify fetches `originalSource`
server-side, and media processing is asynchronous **even under `synchronous: true`**. A
hotlink- or referer-protected prospect CDN fails at that point, well after the mutation
returned success.

So re-query, using the media verification shape in
`${CLAUDE_PLUGIN_ROOT}/skills/shopify-seed/references/mutation-template.md`:

```bash
shopify store execute -s "$SHOPIFY_DEMO_STORE" \
  --query-file /tmp/verify-media.graphql
```

Read-only — no `--allow-mutations`.

- `status: READY` and an `image { url }` → good.
- `status: PROCESSING` → wait a few seconds and re-run **once**.
- `status: FAILED`, or `mediaErrors` populated, or no media node at all → that product has
  no image. Name it, quote the `mediaErrors.details`, and offer to re-push that product
  with a different image URL. Do not report success.

Also confirm the variants actually exist with stock, since a silently dropped variant
removes an exchange target:

```bash
shopify store execute -s "$SHOPIFY_DEMO_STORE" \
  --query '{ products(first: 4, query: "tag:pl-demo-seed status:active") { nodes { title variants(first: 20) { nodes { inventoryQuantity selectedOptions { name value } } } } } }'
```

Every product needs **≥2 variants**, and every variant needs `inventoryQuantity` above
zero. A zero-stock variant is invisible as an exchange target — the demo would show fewer
options than expected and look broken.

---

## Step 9 — Report

| # | Product | Type | Seeded price | Variants | Stock | Image | Admin |
|---|---|---|---|---|---|---|---|

Admin links are `https://admin.shopify.com/store/<subdomain>/products/<numeric-id>` — the
numeric part of the product GID.

Then the demos now available, taken **straight from the shaping script's `demos` output**
rather than recomputed:

- **Even, in-product:** *[product]* — swap *[swap]*, nothing to pay.
- **Even, across products:** *[A]* ↔ *[B]*, same price, nothing to pay.
- **Uneven upward:** *[A]* → *[D]*, customer **pays** *[balance]*.
- **Uneven downward:** *[A]* → *[C]*, customer is refunded *[refund]* — or say it is not
  available for this product set.

Repeat any price adjustments as `was → now`, so whoever runs the demo knows which figures
are not the prospect's real prices. Surface any `warnings` from the script.

**No currency symbols** in any figure — a dev store set to a non-GBP or non-USD currency
displays different symbols, so a demo script must not hard-code one.
````

- [ ] **Step 2: Verify the async-media gap and demo reporting are documented**

```bash
cd /Users/jamie.lee-smith/Documents/Claude/Projects/parcellab-claude-skills/plugins/pl-tools/skills/shopify-seed
grep -c 'asynchronous\|PROCESSING\|FAILED' SKILL.md
grep -c 'pays' SKILL.md
grep -c 'inventoryQuantity' SKILL.md
```

Expected: at least 3 for the first; at least 2 for `pays` — the upward demo must be named as taking payment; at least 1 for `inventoryQuantity`.

- [ ] **Step 3: Verify the full step sequence is present and ordered**

```bash
grep -n '^## Step' SKILL.md
```

Expected: Steps 0 through 9, in order, no gaps.

- [ ] **Step 4: Commit**

```bash
git add plugins/pl-tools/skills/shopify-seed/SKILL.md
git commit -m "feat(shopify-seed): add async media verification and final report"
```

---

### Task 6: Update the plugin inventory and docs

Three strings currently say **"Five skills"**. A sixth skill makes them wrong. This is documentation-only but it is how teammates discover the skill exists.

**Files:**
- Modify: `.claude-plugin/marketplace.json`
- Modify: `plugins/pl-tools/.claude-plugin/plugin.json`
- Modify: `README.md`

**Interfaces:**
- Consumes: the finished skill from Tasks 2–5.
- Produces: nothing consumed by other tasks.

- [ ] **Step 1: Update marketplace.json**

In the `pl-tools` entry, replace the `description` with:

```
"parcelLab internal tooling: create orders, simulate post-purchase journeys, build branded email layouts, raise demo requests, investigate bugs, and seed a prospect's products into a Shopify dev store. Six skills plus /pl-setup, which configures your account and credentials in one pass."
```

Leave the `renames` map alone — it is append-only, and this is a new skill, not a rename.

- [ ] **Step 2: Update plugin.json**

Replace the `description` with:

```
"parcelLab internal tooling: create orders, simulate post-purchase journeys, build branded email layouts, raise demo requests, investigate bugs, and seed prospect products into Shopify. Run /pl-setup once after installing."
```

Add `"shopify"` to the `keywords` array.

- [ ] **Step 3: Add the README skill-table row**

In the skill table (around `README.md:58`), after the `order-lifecycle` row:

```markdown
| `pl-tools:shopify-seed` | Loads four of a prospect's real products — with their size and colour variants — into a Shopify dev store, priced so a size swap, an even cross-product swap, and an uneven swap that takes payment all demo correctly | *"Seed [prospect]'s products into my Shopify store"* |
```

- [ ] **Step 4: Add the README detail section**

After the `### pl-tools:order-lifecycle` section (around `README.md:218`), add:

````markdown
### pl-tools:shopify-seed

Puts a prospect's own products into a Shopify **dev** store so an exchange demo uses
products they actually sell.

```
seed acme.com's products into my Shopify store
```

Browses the prospect's site for four products of different types, keeps a couple of values
from each variant axis the site exposes, and validates the images resolve. Then it prices
them so every exchange demo works:

- **a size swap inside one product** — the quickest even exchange, and the most common real
  returns case
- **an even swap across a matched pair** — different item, nothing to pay
- **an uneven swap upward** — into something dearer, so the flow takes payment
- **an uneven swap downward** where the catalogue allows one, for the refund case

Real prices are kept whenever the catalogue already has a matching pair and a dearer item,
which is the common case. Any adjustment is reported as `was → now`.

Requires the Shopify CLI. First run confirms which of your authenticated dev stores to use
and remembers it in `~/.claude/parcellab-shopify-seed.env`.

Re-runs **archive** the previous prospect's products — tagged `pl-demo-seed` — rather than
deleting them, so nothing is lost and the store does not accumulate the wrong brand's items
as exchange targets.
````

- [ ] **Step 5: Verify the JSON is still valid and no stale count remains**

```bash
cd /Users/jamie.lee-smith/Documents/Claude/Projects/parcellab-claude-skills
python3 -m json.tool .claude-plugin/marketplace.json > /dev/null && echo "marketplace.json valid"
python3 -m json.tool plugins/pl-tools/.claude-plugin/plugin.json > /dev/null && echo "plugin.json valid"
grep -rn 'Five skills\|five skills' . --include=*.json --include=*.md ; echo "stale-count-exit:$?"
grep -c 'version' plugins/pl-tools/.claude-plugin/plugin.json
```

Expected: both `valid`; `stale-count-exit:1`; and **0** occurrences of `version` in `plugin.json` — `pl-tools` must stay unversioned.

- [ ] **Step 6: Commit**

```bash
git add .claude-plugin/marketplace.json plugins/pl-tools/.claude-plugin/plugin.json README.md
git commit -m "docs(shopify-seed): add skill to plugin inventory and README"
```

---

### Task 7: Live end-to-end verification

Prose workflows cannot be unit tested. This task is the real test, and it must run before anything is called done.

**Files:** none modified unless a defect is found.

**Interfaces:**
- Consumes: everything from Tasks 1–6.
- Produces: a verified working skill.

- [ ] **Step 1: Confirm the tests and inventory still pass**

```bash
cd /Users/jamie.lee-smith/Documents/Claude/Projects/parcellab-claude-skills/plugins/pl-tools/scripts
python3 -m unittest discover -s tests -v
```

Expected: PASS.

```bash
cd /Users/jamie.lee-smith/Documents/Claude/Projects/parcellab-claude-skills
claude plugin validate ./plugins/pl-tools 2>&1 | tail -20
```

Expected: `shopify-seed` listed; the `"No version specified"` warning present and **left alone**.

- [ ] **Step 2: Run the skill against a real prospect site**

Ask the user for a prospect URL — ideally a fashion retailer, since real Size and Colour axes are what this exercises. Destination store: `parcellab-demo-jls.myshopify.com` (Jamie's authenticated dev store, connected Jul 27 2026 — confirm by name at the Step 1 gate).

Confirm each of these actually happened:

- Store confirmed **by name** before any write, and persisted to `~/.claude/parcellab-shopify-seed.env`.
- Location GID resolved automatically — the user was never asked to paste one.
- Four products of **four different types**, with real names, prices and images.
- Real variant axes were picked up where the site exposes them, and no colour was invented.
- `check_images.mjs` ran and passed on all four.
- The approval table appeared with all four demos named, and **nothing was written before a yes**.
- Any price adjustment was disclosed as `from` → `to`.

- [ ] **Step 3: Verify the result in Shopify**

```bash
shopify store execute -s parcellab-demo-jls.myshopify.com \
  --query '{ products(first: 10, query: "tag:pl-demo-seed") { nodes { id title status productType tags totalInventory options { name values } media(first: 1) { nodes { status ... on MediaImage { image { url } } } } variants(first: 20) { nodes { price inventoryQuantity selectedOptions { name value } } } } } }'
```

Confirm, for each product:

- `status: ACTIVE`, tags include `pl-demo-seed` and `pl-prospect-<handle>`.
- **≥2 variants**, and every variant's `inventoryQuantity` **greater than zero** — this is the check that catches the invisible-exchange-target bug.
- Every variant of a product shares the **same price** — that is what makes the in-product size swap an even exchange.
- `options` matches the axes scraped, and the variant count equals the product of the axis lengths (nothing silently dropped).
- Media `status: READY` with a real `image { url }`.
- Four distinct `productType` values.

Then confirm the price shape across the four products:

- exactly two share a price (the matched pair);
- at least one is priced **above** that pair — without this the upward payment demo does not exist.

- [ ] **Step 4: Walk one exchange in the returns portal**

The Shopify data being right does not prove the demo works. In the parcelLab returns portal against this store, start a return on a seeded product and confirm:

- the same product's other size appears as an exchange target, with no balance to pay;
- the dearer product appears as a target and shows a **balance to pay**.

If exchange targets are missing, check variant stock first — that is the usual cause.

- [ ] **Step 5: Verify the re-run archives rather than accumulates**

Run the skill a second time with a **different** prospect URL, then:

```bash
shopify store execute -s parcellab-demo-jls.myshopify.com \
  --query '{ products(first: 20, query: "tag:pl-demo-seed") { nodes { title status tags } } }'
```

Expected: the first prospect's products are `ARCHIVED`, the second prospect's are `ACTIVE`, and only the second prospect's items would appear as exchange targets. Nothing deleted.

- [ ] **Step 6: Fix any defect found, then re-verify**

If any check above fails, fix the skill and repeat the failing step. Do not proceed to Step 7 with a known failure. Do not expand scope to pre-existing unrelated failures — if `test_pl_credentials.py` was already failing, note it plainly and leave it.

- [ ] **Step 7: Commit any fixes and report**

```bash
git add -A
git commit -m "fix(shopify-seed): corrections from live verification"
```

Then report to the user what was verified, with the actual command output — not a claim of success. **Do not push and do not tell the team to run `/pl-update` until the user says they are happy.**

---

## Release

Only after the user approves:

```bash
git remote -v   # must be jamie1leesmith-lgtm, never the parcelLab org
git push origin main
```

Then tell the team to run `/pl-update`. Nothing updates itself — no notification, no background pull. `pl-tools` stays unversioned; its version resolves to the commit SHA, so the push itself is the release.
