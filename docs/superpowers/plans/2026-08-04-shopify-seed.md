# shopify-seed Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a `pl-tools` skill that takes a prospect URL and loads four of that prospect's real products into a Shopify dev store, shaped so both the even and uneven parcelLab exchange demos work.

**Architecture:** One `SKILL.md` carries the browser-and-CLI workflow as prose; two `references/` files hold the scrape snippets and the GraphQL templates; one pure-logic Python script (`shape_product_mix.py`) owns the price/size/stock rule and is unit tested. Image validation reuses `demo-request`'s existing `check_images.mjs` rather than reimplementing it. Products reach Shopify through a single aliased `productSet` call via `shopify store execute --allow-mutations`.

**Tech Stack:** Claude Code skill (markdown), Python 3 stdlib (`unittest`, `decimal`), Shopify CLI 4.6.0, Shopify Admin GraphQL 2026-07, Claude Code Browser pane (`mcp__Claude_Browser__*`).

**Spec:** `docs/superpowers/specs/2026-08-04-shopify-seed-design.md`

## Global Constraints

Every task's requirements implicitly include this section.

- **Skill directory:** `plugins/pl-tools/skills/shopify-seed/`. Frontmatter `name:` **must** equal the directory name `shopify-seed` — a mismatch silently removes the skill from the plugin inventory with no error.
- **No `pl-` prefix** on the skill directory. The `pl-tools:` prefix already namespaces it.
- **`description:` is trigger text, not a label.** Keep the word **parcelLab** spelled out.
- **All internal file references use `${CLAUDE_PLUGIN_ROOT}`.** Never `~/.claude/skills/…`, never a path relative to this repo. Installed users run from `~/.claude/plugins/cache/parcellab-skills/pl-tools/<version>/`.
- **Tests are stdlib `unittest`.** `pytest` is not installed. Never `pip install`. Run with: `cd plugins/pl-tools/scripts && python3 -m unittest discover -s tests -v`
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

## File Structure

| Path | Responsibility | Task |
|---|---|---|
| `plugins/pl-tools/scripts/shape_product_mix.py` | Price/size/stock rule. Pure logic, stdin JSON → stdout JSON. | 1 |
| `plugins/pl-tools/scripts/tests/test_shape_product_mix.py` | `unittest` for the above. | 1 |
| `plugins/pl-tools/skills/shopify-seed/SKILL.md` | The workflow: preflight, store, location, collect, shape, approve, archive, push, verify, report. | 2–5 |
| `plugins/pl-tools/skills/shopify-seed/references/product-scrape.md` | Browser-pane snippets: name, price, image, sizes. | 3 |
| `plugins/pl-tools/skills/shopify-seed/references/mutation-template.md` | `productSet` seed shape, archive query/mutation, media verification query. | 4 |
| `.claude-plugin/marketplace.json` | Plugin description: five skills → six. | 6 |
| `plugins/pl-tools/.claude-plugin/plugin.json` | Same. | 6 |
| `README.md` | Skill table row + detail section. | 6 |

---

### Task 1: The price/size/stock rule

The one piece of real logic. Pure function, no I/O beyond stdin/stdout, so it is fully unit testable without Shopify or a browser.

Lives at **plugin** level (`plugins/pl-tools/scripts/`), not skill level, because that is the only location the repo's documented `unittest discover -s tests` command reaches — a skill-level `scripts/tests/` would be silently skipped.

**Files:**
- Create: `plugins/pl-tools/scripts/shape_product_mix.py`
- Test: `plugins/pl-tools/scripts/tests/test_shape_product_mix.py`

**Interfaces:**
- Consumes: nothing (first task).
- Produces, all imported by the test module and invoked by `SKILL.md` Step 4:
  - `normalise_price(value: str | float | int) -> Decimal` — 2dp, `ROUND_HALF_UP`. Raises `ValueError` if unparseable.
  - `shape_prices(prices: list[Decimal]) -> tuple[list[Decimal], list[int]]` — returns `(new_prices, adjusted_indices)`. Raises `ValueError` if fewer than 3 prices.
  - `resolve_sizes(products: list[dict], default: tuple[str, ...] = ("S", "M", "L")) -> list[str]`
  - `build_mix(payload: dict) -> dict`
  - `main() -> None` — reads stdin JSON, writes stdout JSON.
- CLI contract: `python3 shape_product_mix.py < in.json > out.json`

Input payload shape:

```json
{
  "products": [
    {"name": "Alpine Shell Jacket", "price": "129.00", "image_url": "https://…/a.jpg", "pdp_url": "https://…", "sizes": ["S", "M", "L"]}
  ],
  "location_id": "gid://shopify/Location/123456",
  "prospect_handle": "acme",
  "stock_per_variant": 25
}
```

Output payload shape:

```json
{
  "products": [
    {"name": "…", "original_price": "129.00", "price": "129.00", "adjusted": false,
     "image_url": "…", "sizes": ["S","M","L"], "tags": ["pl-demo-seed", "pl-prospect-acme"],
     "stock_per_variant": 25}
  ],
  "adjustments": [{"name": "…", "from": "…", "to": "…"}],
  "even_pair": ["…", "…"],
  "uneven_pair": ["…", "…"],
  "uneven_balance": "35.00",
  "location_id": "gid://shopify/Location/123456"
}
```

The rule:

1. Normalise every price to 2dp.
2. A matching pair already exists **and** some other price differs → change nothing.
3. All prices identical → nudge exactly one (the last) up by `10.00`, so the uneven flow has a target.
4. Otherwise (all distinct) → take the two closest-priced products and lower the higher one to the lower's price. Ties resolve to the lowest-index pair. Never inflate.

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
    normalise_price,
    resolve_sizes,
    shape_prices,
)

SCRIPT = Path(__file__).resolve().parents[1] / "shape_product_mix.py"


def d(value):
    return Decimal(value)


class NormalisePriceTests(unittest.TestCase):
    def test_strips_currency_symbols(self):
        self.assertEqual(normalise_price("£129.99"), d("129.99"))
        self.assertEqual(normalise_price("$28.00"), d("28.00"))
        self.assertEqual(normalise_price("€64,50"), d("64.50"))

    def test_strips_thousands_separator(self):
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
    def test_natural_pair_is_left_untouched(self):
        prices = [d("28.00"), d("28.00"), d("64.00")]
        new, adjusted = shape_prices(prices)
        self.assertEqual(new, prices)
        self.assertEqual(adjusted, [])

    def test_all_distinct_converges_closest_pair_downward(self):
        new, adjusted = shape_prices([d("28.00"), d("32.00"), d("64.00")])
        self.assertEqual(new, [d("28.00"), d("28.00"), d("64.00")])
        self.assertEqual(adjusted, [1])

    def test_tie_resolves_to_lowest_index_pair(self):
        new, adjusted = shape_prices([d("10.00"), d("20.00"), d("30.00")])
        self.assertEqual(new, [d("10.00"), d("10.00"), d("30.00")])
        self.assertEqual(adjusted, [1])

    def test_all_identical_nudges_exactly_one(self):
        new, adjusted = shape_prices([d("28.00"), d("28.00"), d("28.00")])
        self.assertEqual(adjusted, [2])
        self.assertEqual(new[:2], [d("28.00"), d("28.00")])
        self.assertEqual(new[2], d("38.00"))

    def test_result_always_satisfies_both_exchange_flows(self):
        for prices in (
            [d("28.00"), d("32.00"), d("64.00")],
            [d("28.00"), d("28.00"), d("28.00")],
            [d("28.00"), d("28.00"), d("64.00")],
            [d("5.00"), d("500.00"), d("501.00"), d("999.00")],
        ):
            new, _ = shape_prices(list(prices))
            counts = {p: new.count(p) for p in new}
            self.assertTrue(any(c >= 2 for c in counts.values()), new)
            self.assertGreater(len(set(new)), 1, new)

    def test_rejects_fewer_than_three(self):
        with self.assertRaises(ValueError):
            shape_prices([d("28.00"), d("28.00")])


class ResolveSizesTests(unittest.TestCase):
    def test_consistent_sizes_are_preserved(self):
        products = [{"sizes": ["S", "M", "L"]}, {"sizes": ["S", "M", "L"]}]
        self.assertEqual(resolve_sizes(products), ["S", "M", "L"])

    def test_inconsistent_sizes_fall_back_to_default(self):
        products = [{"sizes": ["S", "M"]}, {"sizes": ["38", "40"]}]
        self.assertEqual(resolve_sizes(products), ["S", "M", "L"])

    def test_missing_sizes_fall_back_to_default(self):
        self.assertEqual(resolve_sizes([{}, {}]), ["S", "M", "L"])


class BuildMixTests(unittest.TestCase):
    def payload(self, prices):
        return {
            "products": [
                {"name": f"Product {i}", "price": p, "image_url": f"https://x/{i}.jpg",
                 "pdp_url": f"https://x/p/{i}", "sizes": ["S", "M", "L"]}
                for i, p in enumerate(prices)
            ],
            "location_id": "gid://shopify/Location/1",
            "prospect_handle": "acme",
            "stock_per_variant": 25,
        }

    def test_every_variant_gets_non_zero_stock(self):
        result = build_mix(self.payload(["28.00", "32.00", "64.00"]))
        for product in result["products"]:
            self.assertGreater(product["stock_per_variant"], 0)

    def test_tags_include_seed_and_prospect(self):
        result = build_mix(self.payload(["28.00", "28.00", "64.00"]))
        for product in result["products"]:
            self.assertIn("pl-demo-seed", product["tags"])
            self.assertIn("pl-prospect-acme", product["tags"])

    def test_adjustments_are_reported_with_from_and_to(self):
        result = build_mix(self.payload(["28.00", "32.00", "64.00"]))
        self.assertEqual(len(result["adjustments"]), 1)
        self.assertEqual(result["adjustments"][0]["from"], "32.00")
        self.assertEqual(result["adjustments"][0]["to"], "28.00")

    def test_no_adjustments_reported_when_pair_is_natural(self):
        result = build_mix(self.payload(["28.00", "28.00", "64.00"]))
        self.assertEqual(result["adjustments"], [])
        self.assertTrue(all(not p["adjusted"] for p in result["products"]))

    def test_original_price_is_retained_after_adjustment(self):
        result = build_mix(self.payload(["28.00", "32.00", "64.00"]))
        adjusted = [p for p in result["products"] if p["adjusted"]][0]
        self.assertEqual(adjusted["original_price"], "32.00")
        self.assertEqual(adjusted["price"], "28.00")

    def test_reports_even_and_uneven_pairs_with_balance(self):
        result = build_mix(self.payload(["28.00", "28.00", "64.00"]))
        self.assertEqual(len(result["even_pair"]), 2)
        self.assertEqual(len(result["uneven_pair"]), 2)
        self.assertEqual(result["uneven_balance"], "36.00")

    def test_prices_are_serialised_as_strings(self):
        result = build_mix(self.payload(["28.00", "32.00", "64.00"]))
        for product in result["products"]:
            self.assertIsInstance(product["price"], str)


class CliTests(unittest.TestCase):
    def test_reads_stdin_and_writes_json_to_stdout(self):
        payload = {
            "products": [
                {"name": "A", "price": "28.00", "image_url": "https://x/a.jpg",
                 "pdp_url": "https://x/a", "sizes": ["S", "M", "L"]},
                {"name": "B", "price": "32.00", "image_url": "https://x/b.jpg",
                 "pdp_url": "https://x/b", "sizes": ["S", "M", "L"]},
                {"name": "C", "price": "64.00", "image_url": "https://x/c.jpg",
                 "pdp_url": "https://x/c", "sizes": ["S", "M", "L"]},
            ],
            "location_id": "gid://shopify/Location/1",
            "prospect_handle": "acme",
        }
        proc = subprocess.run(
            [sys.executable, str(SCRIPT)],
            input=json.dumps(payload), capture_output=True, text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(len(json.loads(proc.stdout)["products"]), 3)

    def test_exits_non_zero_on_unparseable_price(self):
        payload = {
            "products": [
                {"name": "A", "price": "Price on request", "sizes": []},
                {"name": "B", "price": "32.00", "sizes": []},
                {"name": "C", "price": "64.00", "sizes": []},
            ],
            "location_id": "gid://shopify/Location/1",
            "prospect_handle": "acme",
        }
        proc = subprocess.run(
            [sys.executable, str(SCRIPT)],
            input=json.dumps(payload), capture_output=True, text=True,
        )
        self.assertNotEqual(proc.returncode, 0)


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
"""Shape scraped prospect products into a mix valid for both parcelLab exchange demos.

An even exchange needs two products at the same price; an uneven exchange needs a
third at a different price. Real prospect catalogues rarely provide both, so this
module adjusts the minimum number of prices and reports every change.

Reads a JSON payload on stdin, writes the shaped payload to stdout.
"""

import json
import re
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

TWO_PLACES = Decimal("0.01")
DEFAULT_SIZES = ("S", "M", "L")
DEFAULT_STOCK = 25
NUDGE = Decimal("10.00")
SEED_TAG = "pl-demo-seed"


def normalise_price(value):
    """Return value as a 2dp Decimal, tolerating currency symbols and separators."""
    text = str(value).strip()
    if not text:
        raise ValueError("empty price")

    # Drop everything that is not a digit or a separator.
    text = re.sub(r"[^\d.,]", "", text)
    if not text:
        raise ValueError(f"no digits in price: {value!r}")

    # "64,50" is a decimal comma; "1,299.00" is a thousands comma.
    if "," in text and "." in text:
        text = text.replace(",", "")
    elif "," in text:
        text = text.replace(",", ".") if len(text.split(",")[-1]) == 2 else text.replace(",", "")

    try:
        return Decimal(text).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
    except InvalidOperation as exc:
        raise ValueError(f"unparseable price: {value!r}") from exc


def shape_prices(prices):
    """Guarantee at least two equal prices and at least one different one.

    Returns (new_prices, adjusted_indices). Never inflates an existing price
    except in the all-identical case, where one must move for the uneven flow.
    """
    if len(prices) < 3:
        raise ValueError("need at least 3 products: two to match, one to differ")

    prices = list(prices)
    distinct = set(prices)

    # Already valid: a duplicate exists and something else differs.
    if len(distinct) < len(prices) and len(distinct) > 1:
        return prices, []

    # All identical: nudge the last one up so an uneven exchange has a target.
    if len(distinct) == 1:
        prices[-1] = prices[-1] + NUDGE
        return prices, [len(prices) - 1]

    # All distinct: converge the closest pair, lowering the higher price.
    best = None
    for i in range(len(prices)):
        for j in range(i + 1, len(prices)):
            gap = abs(prices[i] - prices[j])
            if best is None or gap < best[0]:
                best = (gap, i, j)

    _, i, j = best
    higher = i if prices[i] > prices[j] else j
    lower = j if higher == i else i
    prices[higher] = prices[lower]
    return prices, [higher]


def resolve_sizes(products, default=DEFAULT_SIZES):
    """Return one shared size axis, or the default when the site's sizes disagree."""
    axes = [tuple(p.get("sizes") or ()) for p in products]
    if axes and all(axis and axis == axes[0] for axis in axes):
        return list(axes[0])
    return list(default)


def build_mix(payload):
    products = payload["products"]
    handle = payload.get("prospect_handle", "prospect")
    stock = int(payload.get("stock_per_variant") or DEFAULT_STOCK)
    if stock <= 0:
        raise ValueError("stock_per_variant must be greater than zero")

    originals = [normalise_price(p["price"]) for p in products]
    shaped, adjusted_indices = shape_prices(originals)
    sizes = resolve_sizes(products)
    tags = [SEED_TAG, f"pl-prospect-{handle}"]

    shaped_products = []
    adjustments = []
    for index, product in enumerate(products):
        was_adjusted = index in adjusted_indices
        shaped_products.append({
            "name": product["name"],
            "original_price": f"{originals[index]}",
            "price": f"{shaped[index]}",
            "adjusted": was_adjusted,
            "image_url": product.get("image_url"),
            "pdp_url": product.get("pdp_url"),
            "sizes": sizes,
            "tags": tags,
            "stock_per_variant": stock,
        })
        if was_adjusted:
            adjustments.append({
                "name": product["name"],
                "from": f"{originals[index]}",
                "to": f"{shaped[index]}",
            })

    # The even pair is the first duplicated price; the uneven partner is any other.
    matched_price = next(p for p in shaped if shaped.count(p) >= 2)
    even_indices = [i for i, p in enumerate(shaped) if p == matched_price][:2]
    other_index = next(i for i, p in enumerate(shaped) if p != matched_price)

    return {
        "products": shaped_products,
        "adjustments": adjustments,
        "even_pair": [products[i]["name"] for i in even_indices],
        "uneven_pair": [products[even_indices[0]]["name"], products[other_index]["name"]],
        "uneven_balance": f"{abs(shaped[other_index] - matched_price)}",
        "location_id": payload.get("location_id"),
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

Expected: PASS, all tests. The pre-existing `test_pl_credentials.py` must also still pass — if it fails, confirm it failed before this change and do not fix it here.

- [ ] **Step 5: Commit**

```bash
git add plugins/pl-tools/scripts/shape_product_mix.py plugins/pl-tools/scripts/tests/test_shape_product_mix.py
git commit -m "feat(shopify-seed): add tested price/size/stock shaping rule"
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
description: Seed a prospect's own products into a Shopify dev store so you can demo the parcelLab returns and exchanges flow with products the prospect actually sells. Browses the prospect's site for four real products with prices and images, shapes them into a price mix that supports both even and uneven exchanges, stocks every variant, and pushes them with the Shopify CLI. Trigger on phrases like "seed [prospect]'s products into my Shopify store", "load [brand] products for an exchange demo", "set up the Shopify demo store for [prospect]", or any request to put a prospect's products into a Shopify dev store for a parcelLab returns demo.
argument-hint: <prospect-url>
---
```

- [ ] **Step 2: Write the overview and Steps 0–2**

Append to `SKILL.md`:

````markdown
# parcelLab — Shopify Prospect Seeding

Load four of a prospect's real products into a Shopify **dev** store, shaped so both the
even and uneven exchange demos work. Run once per prospect, per demo.

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

Create `references/product-scrape.md`. The image-scoring function is lifted verbatim from `demo-request`, which is proven; the price and size extraction is new.

````markdown
# Prospect product scraping

Uses Claude Code's built-in **Browser pane** (`mcp__Claude_Browser__*`) — the same as
`demo-request`, `branded-template` and `order-lifecycle`. Not Claude-in-Chrome, not
Playwright.

`mcp__Claude_Browser__javascript_tool` evaluates an *expression*, so every snippet is
wrapped as an IIFE — `(() => {…})()`. Keep it that way; a bare `() => {…}` returns the
function instead of calling it.

## Find listing pages, then PDP links

Reuse `demo-request` Steps 2 and 3 verbatim for this — the listing-link and PDP-link
snippets there already work. Aim for at least 8 PDP candidates before choosing 4.

## Extract name, price, image and sizes from a PDP

```javascript
(() => {
  const name = (
    document.querySelector('h1')?.innerText ||
    document.querySelector('[class*="product-name"], [class*="product-title"], [itemprop="name"]')?.innerText ||
    document.title
  )?.trim().replace(/\s+/g, ' ').slice(0, 120);

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
  if (!price) {
    price = document.querySelector('meta[property="product:price:amount"]')?.content || null;
  }
  if (!price) {
    const text = document.querySelector('[class*="price"], [itemprop="price"]')?.innerText || '';
    price = (text.match(/\d[\d.,]*/) || [null])[0];
  }

  // Sizes, for the shared variant axis.
  const sizeNodes = document.querySelectorAll(
    '[class*="size"] option, [class*="size"] label, [class*="size"] button, [data-option-name*="ize"] option'
  );
  const sizes = Array.from(sizeNodes)
    .map(n => (n.value || n.innerText || '').trim())
    .filter(s => s && s.length <= 6 && !/select|choose|guide/i.test(s))
    .filter((s, i, arr) => arr.indexOf(s) === i)
    .slice(0, 6);

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
    price,
    sizes,
    image_url: bestImg ? (bestImg.currentSrc || bestImg.src) : null,
    pdp_url: location.href,
  };
})()
```

## Edge cases

- **Consent modal** — `read_page` with `{ filter: "interactive" }` for `ref_N` handles,
  then click the dismiss control. **Decline non-essential cookies**, never accept all.
- **Lazy-loaded images** — scroll before scoring:
  `(() => { window.scrollTo(0, document.body.scrollHeight / 2); return true; })()`
- **Price still null** — ask the user for that product's price rather than inventing one.
  A fabricated price in a demo to that prospect is worse than a question.
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
collect exactly four products as `{ name, price, sizes, image_url, pdp_url }`.

Prefer four products from the **same category** with a shared size axis — a jacket and a
mug make a nonsense exchange.

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

An even exchange needs two products at the same price; an uneven exchange needs a third at
a different price; and **every variant needs non-zero stock** — a zero-stock variant is
invisible as an exchange target, so the demo silently shows fewer options and looks broken.

Feed the collected products through the shaping script:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/shape_product_mix.py < /tmp/seed-products.json > /tmp/seed-shaped.json
```

Input keys: `products[]` (`name`, `price`, `sizes`, `image_url`, `pdp_url`),
`location_id`, `prospect_handle`, optional `stock_per_variant` (defaults to 25).

It keeps real prices whenever the catalogue already contains a matching pair, and
otherwise adjusts the minimum number — reported in `adjustments` as `from`/`to`. It exits
non-zero on an unparseable price.

---

## Step 5 — Approval gate

Show the destination store **by name**, then:

| # | Product | Real price | Seeded price | Adjusted | Sizes | Image |
|---|---|---|---|---|---|---|

Call out the adjustments explicitly — these are the only places real prospect data was
altered. Then state which pair gives the even exchange and which gives the uneven one,
with the balance.

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

- [ ] **Step 5: Commit**

```bash
git add plugins/pl-tools/skills/shopify-seed/
git commit -m "feat(shopify-seed): add product collection, image validation and approval gate"
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

- `ProductSetInput` — `title`, `status`, `tags`, `productOptions`, `variants`, `files`
- `OptionSetInput` — `name`, `position`, `values`
- `ProductVariantSetInput` — `price`, `published`, `optionValues`, `inventoryQuantities`, `file`
- `VariantOptionValueInput` — `optionName`, `name`
- `ProductSetInventoryInput` — `locationId`, `name` (use `"available"`), `quantity`
- `FileSetInput` — `originalSource`, `alt`, `filename`, `contentType`, `duplicateResolutionMode`

**Images ship in this same mutation** via `files`. `originalSource` explicitly accepts an
external URL. `contentType` is optional — Shopify sniffs it — but pass `IMAGE` for clarity.
`ProductVariantSetInput.file` also exists, but any variant file **must also appear in the
product's `files` array**.

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

Variables, per product — prices are unitless strings, `locationId` is the GID from Step 2:

```json
{
  "product1": {
    "title": "Alpine Shell Jacket",
    "status": "ACTIVE",
    "tags": ["pl-demo-seed", "pl-prospect-acme"],
    "files": [
      { "originalSource": "https://cdn.example.com/jacket.jpg", "contentType": "IMAGE", "alt": "Alpine Shell Jacket" }
    ],
    "productOptions": [
      { "name": "Size", "position": 1, "values": [{ "name": "S" }, { "name": "M" }, { "name": "L" }] }
    ],
    "variants": [
      {
        "optionValues": [{ "optionName": "Size", "name": "S" }],
        "price": "129.00",
        "published": true,
        "inventoryQuantities": [
          { "locationId": "gid://shopify/Location/123456", "name": "available", "quantity": 25 }
        ]
      },
      {
        "optionValues": [{ "optionName": "Size", "name": "M" }],
        "price": "129.00",
        "published": true,
        "inventoryQuantities": [
          { "locationId": "gid://shopify/Location/123456", "name": "available", "quantity": 25 }
        ]
      },
      {
        "optionValues": [{ "optionName": "Size", "name": "L" }],
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

One variant per size, every one with non-zero `quantity`.

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
`${CLAUDE_PLUGIN_ROOT}/skills/shopify-seed/references/mutation-template.md`, filling in the
shaped products, the location GID, and the tags. These are generated per run, not shipped —
the products differ every time.

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

- [ ] **Step 3: Verify the deprecated argument is not used**

```bash
cd /Users/jamie.lee-smith/Documents/Claude/Projects/parcellab-claude-skills/plugins/pl-tools/skills/shopify-seed
grep -n 'productUpdate(input:' references/mutation-template.md ; echo "deprecated-arg-exit:$?"
grep -c 'productUpdate(product:' references/mutation-template.md
grep -c 'userErrors' references/mutation-template.md
```

Expected: `deprecated-arg-exit:1` (not found); at least 1 `productUpdate(product:`; at least 4 `userErrors`.

- [ ] **Step 4: Verify the mutation validates against the live schema**

Do not skip this — it is the only check that catches a wrong field name before a live run, and every field in the template was taken from docs rather than from the store's own schema.

The seed files are generated per run and do not exist yet, so build a throwaway sample from the template first. Resolve a real location GID for it:

```bash
STORE=parcellab-demo-jls.myshopify.com
LOC=$(shopify store execute -s "$STORE" \
  --query '{ locations(first: 1) { nodes { id } } }' \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["data"]["locations"]["nodes"][0]["id"])')
echo "$LOC"
```

Write a one-product sample using that GID:

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
import json, sys
print(json.dumps({"product1": {
    "title": "Schema Check Product",
    "status": "ACTIVE",
    "tags": ["pl-demo-seed", "pl-prospect-schemacheck"],
    "files": [{"originalSource": "https://cdn.shopify.com/s/files/1/0533/2089/files/placeholder.jpg",
               "contentType": "IMAGE", "alt": "Schema Check Product"}],
    "productOptions": [{"name": "Size", "position": 1,
                        "values": [{"name": "S"}, {"name": "M"}, {"name": "L"}]}],
    "variants": [
        {"optionValues": [{"optionName": "Size", "name": size}],
         "price": "28.00", "published": True,
         "inventoryQuantities": [{"locationId": sys.argv[1], "name": "available", "quantity": 25}]}
        for size in ("S", "M", "L")
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
- Consumes: the product IDs created in Task 4; the `even_pair`, `uneven_pair` and `uneven_balance` fields produced by `build_mix` in Task 1.
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

This is the failure mode most likely to embarrass someone mid-demo, and it is invisible
without this step.

---

## Step 9 — Report

| # | Product | Seeded price | Sizes | Stock | Image | Admin |
|---|---|---|---|---|---|---|

Admin links are `https://admin.shopify.com/store/<subdomain>/products/<numeric-id>` — the
numeric part of the product GID.

Then state the demos now available, taking `even_pair`, `uneven_pair` and
`uneven_balance` straight from the shaping script's output:

- **Even exchange:** *[product A]* ↔ *[product B]*, same price, no balance.
- **Uneven exchange:** *[product A]* → *[product C]*, balance of *[uneven_balance]*.

Repeat any price adjustments here, so whoever runs the demo knows which figures are not
the prospect's real prices.

**No currency symbols** in any figure — a dev store set to a non-GBP or non-USD currency
displays different symbols, so a demo script must not hard-code one.
````

- [ ] **Step 2: Verify the async-media gap is documented**

```bash
cd /Users/jamie.lee-smith/Documents/Claude/Projects/parcellab-claude-skills/plugins/pl-tools/skills/shopify-seed
grep -c 'asynchronous\|PROCESSING\|FAILED' SKILL.md
grep -c 'uneven_balance' SKILL.md
```

Expected: at least 3 matches for the first; at least 1 for the second — the report must consume the script's own output rather than recomputing the balance.

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
| `pl-tools:shopify-seed` | Loads four of a prospect's real products into a Shopify dev store, priced so both the even and uneven exchange demos work, with stock on every variant | *"Seed [prospect]'s products into my Shopify store"* |
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

Browses the prospect's site for four products, validates the images resolve, then shapes
the prices so both exchange flows have a valid target: two products at one price for an
even exchange, one at another for an uneven one. Real prices are kept whenever the
catalogue already contains a matching pair; any adjustment is reported.

Requires the Shopify CLI. First run confirms which of your authenticated dev stores to
use and remembers it in `~/.claude/parcellab-shopify-seed.env`.

Re-runs **archive** the previous prospect's products — tagged `pl-demo-seed` — rather than
deleting them, so nothing is lost and the store does not accumulate the wrong brand's
items as exchange targets.
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

Ask the user for a prospect URL, then invoke `pl-tools:shopify-seed` with it. Destination store: `parcellab-demo-jls.myshopify.com` (Jamie's authenticated dev store, connected Jul 27 2026 — confirm by name at the Step 1 gate).

Confirm each of these actually happened:

- Store confirmed **by name** before any write, and persisted to `~/.claude/parcellab-shopify-seed.env`.
- Location GID resolved automatically — the user was never asked to paste one.
- Four products collected with real names, prices and images.
- `check_images.mjs` ran and passed on all four.
- The approval table appeared, and **nothing was written before a yes**.
- Any price adjustment was disclosed as `from` → `to`.

- [ ] **Step 3: Verify the result in Shopify**

```bash
shopify store execute -s parcellab-demo-jls.myshopify.com \
  --query '{ products(first: 10, query: "tag:pl-demo-seed") { nodes { id title status tags totalInventory media(first: 1) { nodes { status ... on MediaImage { image { url } } } } variants(first: 5) { nodes { price inventoryQuantity selectedOptions { name value } } } } } }'
```

Confirm, for each product:

- `status: ACTIVE`, tags include `pl-demo-seed` and `pl-prospect-<handle>`.
- Every variant has `inventoryQuantity` **greater than zero** — this is the check that catches the invisible-exchange-target bug.
- Every variant shares the `Size` option name.
- Media `status: READY` with a real `image { url }`.
- Prices satisfy both flows: two equal, at least one different.

- [ ] **Step 4: Verify the re-run archives rather than accumulates**

Run the skill a second time with a **different** prospect URL, then:

```bash
shopify store execute -s parcellab-demo-jls.myshopify.com \
  --query '{ products(first: 20, query: "tag:pl-demo-seed") { nodes { title status tags } } }'
```

Expected: the first prospect's products are `ARCHIVED`, the second prospect's are `ACTIVE`, and only the second prospect's items would appear as exchange targets. Nothing deleted.

- [ ] **Step 5: Fix any defect found, then re-verify**

If any check above fails, fix the skill and repeat the failing step. Do not proceed to Step 6 with a known failure. Do not expand scope to pre-existing unrelated failures — if `test_pl_credentials.py` was already failing, note it plainly and leave it.

- [ ] **Step 6: Commit any fixes and report**

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
