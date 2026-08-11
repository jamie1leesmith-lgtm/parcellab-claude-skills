# demo-environment Improvements (Approach A) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cut demo-environment's intake-to-first-send time by front-loading all read-only work behind the interview, give every run a progress artifact that doubles as the visual approval gate, add a driver pace option, and lift the two hard-4 script caps that forced improvisation in Task 13.

**Architecture:** The conductor (`plugins/pl-tools/skills/demo-environment/SKILL.md`) gains a background scrape agent and a run-page redeploy loop; two shared scripts gain relaxed input contracts; the manifest gains one optional key (`run.pace`). Chat remains the only approval mechanism — the run page is a view baked from run-dir files at each milestone.

**Tech Stack:** Markdown skill files, stdlib-Python scripts + `unittest`, one Node script, self-contained HTML (no external requests), the Artifact tool.

**Spec:** `docs/superpowers/specs/2026-08-11-demo-environment-improvements-design.md` (approved 2026-08-11).

## Global Constraints

- Tests are stdlib `unittest` only — `pytest` is not installed; never `pip install`. Run: `cd plugins/pl-tools/scripts && python3 -m unittest discover -s tests -v < /dev/null` (the credential test prompts without the redirect).
- Reference bundled files via `${CLAUDE_PLUGIN_ROOT}` in skill text — never repo-relative or `~/.claude/skills/…` paths.
- Never rename the `parcellab-*` strings listed in the repo CLAUDE.md table.
- Frontmatter `name:` must equal the skill directory name; keep the word "parcelLab" in any `description:` you touch.
- Driver pace values are exactly `GAP_SECONDS=180` (standard) and `GAP_SECONDS=60` (fast). Default is standard.
- The Shopify scope string, wherever quoted, is the live-verified seven scopes verbatim: `write_products,write_inventory,read_orders,write_orders,write_fulfillments,write_draft_orders,write_merchant_managed_fulfillment_orders`.
- The run page must be self-contained HTML (a strict CSP blocks all external requests), light/dark aware, favicon `📦`, title `<brand> demo — <run id>`, and is NEVER load-bearing: a failed publish is a one-line chat notice, not a stopped run.
- The Browser pane ownership rule: the scrape agent owns the pane from dispatch until `results/scrape.json` exists; the conductor must not navigate the pane in that window.
- **Execution prerequisite (spec §8):** this plan executes on a fresh branch (`feat/demo-environment-v2`) created AFTER `feat/demo-environment` is finished via superpowers:finishing-a-development-branch. Do not start Task 1 on `feat/demo-environment`.

---

### Task 1: `check_images.mjs` accepts 1–N products

**Files:**
- Modify: `plugins/pl-tools/skills/demo-request/scripts/check_images.mjs` (the count guard in `main()`)
- Create: `plugins/pl-tools/scripts/tests/test_check_images.py`
- Modify: `plugins/pl-tools/skills/demo-environment/SKILL.md` (Phase 0 image-validation bullet — replace "check_images.mjs semantics" wording with a direct script invocation)

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: `check_images.mjs` accepting any product list with ≥1 items (same JSON output shape: `{ok, results:[{index,name,image_url,ok,reason,…}]}`, exit 1 if any image fails or input is invalid). Task 4's conductor text calls it directly.

- [ ] **Step 1: Write the failing tests**

```python
# plugins/pl-tools/scripts/tests/test_check_images.py
import json
import subprocess
import unittest
from pathlib import Path

SCRIPT = (Path(__file__).resolve().parent.parent.parent
          / "skills" / "demo-request" / "scripts" / "check_images.mjs")


def run(payload):
    return subprocess.run(
        ["node", str(SCRIPT)],
        input=json.dumps(payload), capture_output=True, text=True,
    )


class TestCheckImages(unittest.TestCase):
    def test_rejects_empty_product_list(self):
        r = run({"products": []})
        self.assertEqual(r.returncode, 1)
        self.assertIn("at least 1", r.stderr)

    def test_accepts_two_products(self):
        # Missing image_url fails fast with no network access.
        r = run({"products": [{"name": "A"}, {"name": "B"}]})
        out = json.loads(r.stdout)
        self.assertEqual(len(out["results"]), 2)
        self.assertFalse(out["ok"])
        self.assertEqual(r.returncode, 1)

    def test_accepts_eleven_products(self):
        r = run({"products": [{"name": f"P{i}"} for i in range(11)]})
        out = json.loads(r.stdout)
        self.assertEqual(len(out["results"]), 11)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd plugins/pl-tools/scripts && python3 -m unittest tests.test_check_images -v < /dev/null`
Expected: `test_rejects_empty_product_list` FAILS (stderr says "Expected exactly 4 products", not "at least 1"); `test_accepts_two_products` and `test_accepts_eleven_products` FAIL (count error instead of results JSON).

- [ ] **Step 3: Relax the count guard**

In `check_images.mjs`, replace:

```javascript
  if (products.length !== 4) {
    throw new Error(`Expected exactly 4 products, received ${products.length}.`);
  }
```

with:

```javascript
  if (products.length < 1) {
    throw new Error(`Expected at least 1 product, received ${products.length}.`);
  }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd plugins/pl-tools/scripts && python3 -m unittest tests.test_check_images -v < /dev/null`
Expected: 3/3 PASS. Also run `node --check plugins/pl-tools/skills/demo-request/scripts/check_images.mjs` → no output.

- [ ] **Step 5: Point the conductor at the script directly**

In `plugins/pl-tools/skills/demo-environment/SKILL.md`, the Phase 0 browser-pass bullet currently reads:

```
   - Validate every candidate image:
     `node ${CLAUDE_PLUGIN_ROOT}/skills/demo-request/scripts/check_images.mjs`
     semantics (200 + image/*; ranged-GET retry). Mark `image_verified`.
```

Replace it with:

```
   - Validate every candidate image by running
     `node ${CLAUDE_PLUGIN_ROOT}/skills/demo-request/scripts/check_images.mjs`
     over the whole pool (accepts 1–N products; 200 + image/*, ranged-GET
     retry). Mark `image_verified` from its per-product `ok` flags.
```

- [ ] **Step 6: Full suite + commit**

Run: `cd plugins/pl-tools/scripts && python3 -m unittest discover -s tests -v < /dev/null` → all pass.

```bash
git add plugins/pl-tools/skills/demo-request/scripts/check_images.mjs plugins/pl-tools/scripts/tests/test_check_images.py plugins/pl-tools/skills/demo-environment/SKILL.md
git commit -m "feat(demo-request): check_images accepts 1-N products; conductor runs it directly"
```

---

### Task 2: `shape_product_mix.py` gains `--extras-file`

**Files:**
- Modify: `plugins/pl-tools/scripts/shape_product_mix.py` (argparse + extras shaping in `build_mix`/`main`)
- Modify: `plugins/pl-tools/scripts/tests/test_shape_product_mix.py` (new tests appended)
- Modify: `plugins/pl-tools/skills/shopify-seed/SKILL.md` ("Orchestrated runs (demo-environment)" section — how the seed agent passes core4 vs extras)

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: `python3 shape_product_mix.py [--extras-file PATH]` — stdin payload unchanged (`{products:[exactly 4], location_id, prospect_handle, stock_per_variant?}`); the extras file holds a JSON **array** of scrape-shaped products (`{name, product_type, price, options, image_url, pdp_url}`). Output shape unchanged except `products` contains 4 + len(extras) entries; extras are shaped at their **own normalised price** (`adjusted: false`, `original_price == price`), with the same `resolve_options`/`build_variants`/tags treatment; `adjustments`, `warnings` (type-repeat check spans all products), and `demos` (computed from the core 4 only) keep their existing shapes.

- [ ] **Step 1: Write the failing tests**

Append to `plugins/pl-tools/scripts/tests/test_shape_product_mix.py` (match the file's existing fixture/style — it runs `build_mix` in-process; import `main` pieces the same way the existing tests do). Add:

```python
class TestExtrasFile(unittest.TestCase):
    def payload(self):
        return {
            "products": [
                {"name": "Jumper", "product_type": "Jumper", "price": "50.00",
                 "options": [], "image_url": "https://x/i.jpg", "pdp_url": "https://x/p"},
                {"name": "Jeans", "product_type": "Jeans", "price": "60.00",
                 "options": [], "image_url": "https://x/i.jpg", "pdp_url": "https://x/p"},
                {"name": "Shoes", "product_type": "Shoes", "price": "80.00",
                 "options": [], "image_url": "https://x/i.jpg", "pdp_url": "https://x/p"},
                {"name": "Coat", "product_type": "Coat", "price": "120.00",
                 "options": [], "image_url": "https://x/i.jpg", "pdp_url": "https://x/p"},
            ],
            "location_id": "gid://shopify/Location/1",
            "prospect_handle": "acme",
        }

    def extras(self):
        return [
            {"name": "Scarf", "product_type": "Scarf", "price": "22.50",
             "options": [{"name": "Colour", "values": ["Red", "Blue"]}],
             "image_url": "https://x/s.jpg", "pdp_url": "https://x/s"},
        ]

    def test_extras_appended_at_own_price(self):
        out = shape_product_mix.build_mix(self.payload(), extras=self.extras())
        self.assertEqual(len(out["products"]), 5)
        scarf = out["products"][-1]
        self.assertEqual(scarf["name"], "Scarf")
        self.assertEqual(scarf["price"], "22.50")
        self.assertEqual(scarf["original_price"], "22.50")
        self.assertFalse(scarf["adjusted"])
        self.assertEqual(scarf["options"][0]["name"], "Colour")
        self.assertEqual(scarf["variant_count"], 2)
        self.assertIn("pl-prospect-acme", scarf["tags"])

    def test_demos_ignore_extras(self):
        base = shape_product_mix.build_mix(self.payload())
        with_extras = shape_product_mix.build_mix(self.payload(), extras=self.extras())
        self.assertEqual(base["demos"], with_extras["demos"])
        self.assertEqual(base["adjustments"], with_extras["adjustments"])

    def test_extras_bad_price_fails_loud(self):
        bad = [{"name": "X", "product_type": "X", "price": "??", "options": []}]
        with self.assertRaises(ValueError):
            shape_product_mix.build_mix(self.payload(), extras=bad)
```

(Adjust the import name to whatever the existing test file uses for the module.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd plugins/pl-tools/scripts && python3 -m unittest tests.test_shape_product_mix -v < /dev/null`
Expected: the three new tests FAIL with `TypeError: build_mix() got an unexpected keyword argument 'extras'`. Existing tests still pass.

- [ ] **Step 3: Implement extras shaping**

In `shape_product_mix.py`:

1. Change the signature: `def build_mix(payload, extras=None):`
2. After the existing `shaped_products` loop (and before the `warnings` block), append:

```python
    for product in extras or []:
        price = normalise_price(product["price"])
        options = resolve_options(product)
        shaped_products.append({
            "name": product["name"],
            "product_type": str(product.get("product_type") or "").strip(),
            "original_price": f"{price}",
            "price": f"{price}",
            "adjusted": False,
            "image_url": product.get("image_url"),
            "pdp_url": product.get("pdp_url"),
            "options": options,
            "variants": build_variants(options, price, stock, location_id),
            "tags": [SEED_TAG, f"pl-prospect-{handle}"],
        })
        shaped_products[-1]["variant_count"] = len(shaped_products[-1]["variants"])
```

3. The `warnings`/`demos` blocks already read from `shaped_products`/`products` — confirm `demos` only indexes `products` (the core-4 stdin list) and `shaped` (core-4 prices), which the code above does not touch. The type-repeat warning uses `shaped_products`, so it now spans extras — that is the desired behaviour (a duplicate type anywhere muddies the exchange story).
4. Replace `main()` with an argparse version:

```python
def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--extras-file", default=None,
                    help="JSON array of scrape-shaped products seeded at "
                         "their own price alongside the shaped core 4")
    args = ap.parse_args()
    try:
        extras = None
        if args.extras_file:
            extras = json.loads(Path(args.extras_file).read_text())
            if not isinstance(extras, list):
                raise ValueError("--extras-file must contain a JSON array")
        print(json.dumps(build_mix(json.load(sys.stdin), extras=extras), indent=2))
    except (ValueError, KeyError, OSError) as exc:
        print(f"shape_product_mix: {exc}", file=sys.stderr)
        sys.exit(1)
```

and add `from pathlib import Path` to the imports.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd plugins/pl-tools/scripts && python3 -m unittest tests.test_shape_product_mix -v < /dev/null`
Expected: all pass, including the pre-existing tests (the no-extras path is unchanged).

- [ ] **Step 5: Update the seed contract text**

In `plugins/pl-tools/skills/shopify-seed/SKILL.md`'s "Orchestrated runs (demo-environment)" section, find the sentence describing how `seed/seed-products.json` feeds the shaping step and replace it so the mechanism is explicit:

```
The manifest's `selection.core4` products go to `shape_product_mix.py` on
stdin exactly as the standalone flow does; the `selection.shopify_extra`
products go in a temp JSON array passed via `--extras-file`, which seeds
them at their own real price with the same option/variant logic (no
matched-pair adjustment). One script call shapes the whole seed set — do
not call the script's helpers directly.
```

(Keep the rest of the section verbatim; this replaces only the improvised-helpers behaviour Task 13 observed.)

- [ ] **Step 6: Full suite + commit**

Run: `cd plugins/pl-tools/scripts && python3 -m unittest discover -s tests -v < /dev/null` → all pass.

```bash
git add plugins/pl-tools/scripts/shape_product_mix.py plugins/pl-tools/scripts/tests/test_shape_product_mix.py plugins/pl-tools/skills/shopify-seed/SKILL.md
git commit -m "feat(shopify-seed): shape_product_mix --extras-file seeds extras at their own price"
```

---

### Task 3: `run.pace` in the validator

**Files:**
- Modify: `plugins/pl-tools/scripts/validate_manifest.py` (new optional check)
- Modify: `plugins/pl-tools/scripts/tests/test_validate_manifest.py` (fixture + tests)

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: manifests may carry `run.pace` = `"standard"` | `"fast"`; absent is valid (standard). Task 4's conductor text writes and reads this key. Constant `PACES = {"standard", "fast"}` exported at module level like the existing constant sets.

- [ ] **Step 1: Write the failing tests**

Append to `test_validate_manifest.py`'s test class:

```python
    def test_pace_optional_and_enum(self):
        self.assertEqual(validate(valid_manifest()), [])  # absent is fine
        m = valid_manifest()
        m["run"]["pace"] = "fast"
        self.assertEqual(validate(m), [])
        m["run"]["pace"] = "leisurely"
        self.assertTrue(any("pace" in e for e in validate(m)))
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd plugins/pl-tools/scripts && python3 -m unittest tests.test_validate_manifest -v < /dev/null`
Expected: `test_pace_optional_and_enum` FAILS (no error produced for "leisurely").

- [ ] **Step 3: Implement**

In `validate_manifest.py`, add to the constants block:

```python
PACES = {"standard", "fast"}
```

and inside `validate()` (next to the other top-level checks):

```python
    pace = m.get("run", {}).get("pace")
    if pace is not None:
        need(pace in PACES, f"run.pace must be one of {sorted(PACES)}")
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd plugins/pl-tools/scripts && python3 -m unittest tests.test_validate_manifest -v < /dev/null` → all pass.

- [ ] **Step 5: Commit**

```bash
git add plugins/pl-tools/scripts/validate_manifest.py plugins/pl-tools/scripts/tests/test_validate_manifest.py
git commit -m "feat(demo-environment): optional run.pace (standard|fast) in manifest validator"
```

---

### Task 4: Conductor Phase 0 restructure (scrape agent, pre-builds, pace, repeat-brand skip)

**Files:**
- Modify: `plugins/pl-tools/skills/demo-environment/SKILL.md` (Phase 0 + Phase 1 + Phase 2 driver-launch lines + manifest schema line)
- Modify: `plugins/pl-tools/skills/demo-environment/references/flows.md` (phase-skeleton text)

This task is markdown-only; verification is by grep and by reading the section aloud against the spec's §3.1/§3.3. Keep every existing rule not named below verbatim — this is a restructure, not a rewrite.

**Interfaces:**
- Consumes: Task 1's direct `check_images.mjs` call (the scrape agent brief references it), Task 3's `run.pace` key.
- Produces: the Phase 0 step numbering and the new run-dir files (`scrape/brand-tokens.json`, `scrape/product-pool.json`, `results/scrape.json`) that Task 5's run-page states read; the scrape-agent brief; the pane-ownership rule Task 5 must not contradict.

- [ ] **Step 1: Restructure Phase 0 in SKILL.md**

Replace the current Phase 0 intro and steps 1–6 ordering with this flow (steps 4–5 CDC/account and 7–9 gate/manifest/validate keep their existing text; renumber as needed):

```
## Phase 0 — Intake (front-loaded)

1. **Create the run directory** … (unchanged text) … plus `scrape/` inside it.
2. **Path + brand round:** take the prospect URL and ask ONLY the path
   questions (returns in scope? Shopify opp? per *Paths*) — the minimum
   needed to know what to collect.
3. **Dispatch the scrape agent immediately** (general-purpose subagent,
   background) with exactly this brief, filling the placeholders:

   > Execute the demo-environment scrape pass for the run directory
   > `<run dir>`, prospect `<url>`, path `<engage|retain|retain-shopify>`.
   > Follow `${CLAUDE_PLUGIN_ROOT}/skills/branded-template/SKILL.md` Steps
   > 3–6 for brand tokens (write the full `__BRAND_X__` token map + logo +
   > hero to `<run dir>/scrape/brand-tokens.json`) and
   > `${CLAUDE_PLUGIN_ROOT}/skills/shopify-seed/references/product-scrape.md`
   > for the product pool (≥8 candidates, superset shape; variant axes
   > required only on retain-shopify; write to
   > `<run dir>/scrape/product-pool.json`). Validate every candidate image
   > with `node ${CLAUDE_PLUGIN_ROOT}/skills/demo-request/scripts/check_images.mjs`
   > and set `image_verified` per product. Ground rules, non-negotiable:
   > never ask the user anything — a gap is a failure report; decline
   > non-essential cookies; when done (or failed) write
   > `<run dir>/results/scrape.json` as `{"status": "ok"|"failed",
   > "error": null|"<why>"}` and return a one-paragraph summary.

   **Browser pane ownership:** the agent owns the pane from dispatch until
   `results/scrape.json` exists. Do not navigate the pane in that window —
   the ★ template preview naturally starts after it, since it needs the
   scraped tokens. **Reused pool:** when a prior run's pool for this brand
   is being reused (offer this whenever one exists), skip the dispatch and
   copy the prior `scrape/` files instead.
4. **Interview concurrently, in chat** (batch with AskUserQuestion): the
   remaining rounds — destination country (never assume it) · order plan
   (1–5, default 3, the matrix and scenario vocabulary unchanged, **plus
   pace: standard (180 s gaps, comm-ordering safe — default) or fast (60 s,
   comms may arrive out of order — say so)**) · target account +
   confirmation (unchanged text) · CDC config (unchanged text).
5. **Repeat-brand template shortcut:** if a layout for this brand already
   exists on the target account, verify live —
   `parcellab --env prod journey layout show <id> -o json` must show
   `releaseStatus: published` AND an `autoLayout` entry for the store this
   path's orders will land on — and offer to skip the template lane. If
   accepted, write `results/branded-template.json` from the verified state
   (note "template lane skipped — verified live at intake") and skip the ★
   checkpoint; Phase 1 then has no template work.
6. **Pre-build everything sendable** once the interview and
   `results/scrape.json` (status ok) are both in: the template HTML from
   the tokens (branded-template Step 7, no push), every order's
   `create.json` + `track.json` + `NN-*.json` event files (fraud fragments
   included, payload rules verbatim, no PUTs), and the proposed plan.
   **Scrape failure fallback:** if `results/scrape.json` says failed (or
   the agent dies), run the browser pass inline now, exactly as the
   pre-restructure flow did — the agent is an accelerator, never
   load-bearing.
7. ✋ **Propose the plan and gate** (existing text, unchanged) — one yes
   releases the sends; nothing before this step has touched parcelLab,
   Shopify, or the CDC.
8.–9. Manifest + validate (existing text; the manifest schema line gains
   `run{…, pace}` and the scrape files are recorded under the run dir).
```

- [ ] **Step 2: Wire pace into the driver launches**

In both Phase 2 sections (direct engine step 4 and the Shopify engine's driver reference), change the fixed `GAP_SECONDS` default wording to:

```
GAP_SECONDS comes from the manifest's `run.pace`: 180 for standard (the
default), 60 for fast. When pace is fast, Beat 2's report must note that
comm ordering was not guaranteed at this pace.
```

- [ ] **Step 3: Update flows.md**

In `references/flows.md`, amend the Phase 0 line of the phase skeleton to show the two concurrent lanes (scrape agent ∥ interview → pre-build → ✋ gate releases sends). Keep it to the existing diagram style — this file is prose-sketch, not SVG.

- [ ] **Step 4: Grep verification**

Run and eyeball:
- `grep -n "scrape.json\|scrape/" plugins/pl-tools/skills/demo-environment/SKILL.md` → dispatch step, ownership rule, fallback, pre-build all present.
- `grep -n "run.pace\|GAP_SECONDS" plugins/pl-tools/skills/demo-environment/SKILL.md` → intake option + two driver-launch references.
- `grep -n "journey layout show" plugins/pl-tools/skills/demo-environment/SKILL.md` → repeat-brand shortcut present.
- `grep -c "never ask the user" plugins/pl-tools/skills/demo-environment/SKILL.md` → covers seed AND scrape briefs.

- [ ] **Step 5: Commit**

```bash
git add plugins/pl-tools/skills/demo-environment/SKILL.md plugins/pl-tools/skills/demo-environment/references/flows.md
git commit -m "feat(demo-environment): front-loaded Phase 0 — scrape agent, pre-builds, pace option, repeat-brand skip"
```

---

### Task 5: The run page

**Files:**
- Create: `plugins/pl-tools/skills/demo-environment/references/run-page.md` (structure, states, template skeleton, redeploy points)
- Modify: `plugins/pl-tools/skills/demo-environment/SKILL.md` (one new subsection + one-line hooks at each milestone)

**Interfaces:**
- Consumes: Task 4's Phase 0 numbering and run-dir files; the results files the conductor already writes (`results/*.json`, `orders/*/run.log`, `demo-manifest.json`).
- Produces: `references/run-page.md` — the single source for page structure; the milestone hook sentence used throughout SKILL.md: "Update `run-page.html` (state N per `references/run-page.md`) and republish — non-fatal."

- [ ] **Step 1: Write `references/run-page.md`**

Create the file with exactly these sections:

````markdown
# The run page

One artifact per run: the conductor maintains `<run dir>/run-page.html` and
republishes it via the Artifact tool at each milestone below — same file
path every time, so the URL stays stable. The page is a VIEW; chat is the
only approval mechanism. Publishing is never load-bearing: if the Artifact
tool is unavailable or a publish fails, say so once in chat and continue —
no phase blocks on it.

Rules baked into every publish: self-contained HTML (no external requests —
the artifact CSP blocks them; product images ARE external, so render each
product card with its name/price/type and link the image URL rather than
embedding `<img>` tags that may be blocked — test on the first smoke run
and, if remote images render, switch to `<img>`), light/dark via
`@media (prefers-color-scheme: dark)` plus `:root[data-theme="…"]`
overrides, favicon `📦` (never changes mid-run), title
`<brand> demo — <run id>`. Record the URL in the manifest as
`run.page_url` after the first publish.

## States (each row = one redeploy)

| # | When | The page shows |
|---|---|---|
| 1 | Run dir created | Header (brand, path, account by name, run id), "collecting products + brand styling", interview underway |
| 2 | `results/scrape.json` ok | Product pool grid (name, type, price, verified badge, PDP link), brand-token swatch strip |
| 3 | ✋ gate opens | The proposed plan: core-4 grid · order matrix table (label, customer, fraud, scenario, products, expected comms with confidence labels) · CDC settings (config source, generate_orders) · pace · a banner: "⏳ Approval waiting in chat" |
| 4 | Gate approved / sends firing | Lane cards — template (push → publish → assign), seed (retain-shopify only), per-order chips (created → tracked → events queued); each chip flips as its results land |
| 5 | Drivers launched | Per order: planned event list with "running since HH:MM"; timestamps filled in from `orders/*/run.log` at each driver-completion notification |
| 6 | Beat 1 | The environment-built summary: layout id/status/store, per-order table, CDC request id + link |
| 7 | Beat 2 | Per-arc verification: checkpoints attached vs planned, comms fired vs promised, ✅/⚠️ per arc; fast-pace ordering caveat when `run.pace` is fast |
| 8 | Any failure | The matching failure-table row, verbatim, in a highlighted card at the top — added to whatever state the page is in, never replacing it |

## Skeleton

Every publish rewrites the whole file from current run-dir state (no
incremental patching). Use this skeleton:

```html
<title>{brand} demo — {run_id}</title>
<style>
  :root { --fg:#111; --bg:#fff; --muted:#667; --card:#f5f5f7; --ok:#0a7d33; --warn:#b45309; --bad:#b91c1c; }
  @media (prefers-color-scheme: dark) { :root { --fg:#eee; --bg:#111; --muted:#99a; --card:#1c1c22; } }
  :root[data-theme="dark"] { --fg:#eee; --bg:#111; --muted:#99a; --card:#1c1c22; }
  :root[data-theme="light"] { --fg:#111; --bg:#fff; --muted:#667; --card:#f5f5f7; }
  body { color:var(--fg); background:var(--bg); font:15px/1.5 system-ui, sans-serif; max-width:860px; margin:0 auto; padding:24px; }
  .card { background:var(--card); border-radius:12px; padding:16px 20px; margin:12px 0; }
  .banner { border-left:4px solid var(--warn); font-weight:600; }
  .fail { border-left:4px solid var(--bad); }
  table { border-collapse:collapse; width:100%; } td,th { text-align:left; padding:6px 10px; border-bottom:1px solid var(--muted); }
  .chip { display:inline-block; border-radius:999px; padding:2px 10px; margin:2px; background:var(--card); border:1px solid var(--muted); }
  .done { border-color:var(--ok); } .overflow { overflow-x:auto; }
</style>
<h1>{brand} demo <span style="color:var(--muted)">— {run_id}</span></h1>
<p>{path} path · account {account_name} · {timestamp of this publish}</p>
<!-- state-specific cards go here, newest first; failure cards always at top -->
```

## Milestone hook (the sentence SKILL.md uses)

> Update `run-page.html` (state N per
> `${CLAUDE_PLUGIN_ROOT}/skills/demo-environment/references/run-page.md`)
> and republish — non-fatal.
````

- [ ] **Step 2: Add the hooks to SKILL.md**

Add a short subsection after the *Paths* section:

```
## The run page

Every run keeps one progress artifact — see
`${CLAUDE_PLUGIN_ROOT}/skills/demo-environment/references/run-page.md` for
the states and skeleton. Publish state 1 right after creating the run dir;
republish at each numbered state; record the URL as `run.page_url` in the
manifest after the first publish. Publishing is never load-bearing.
```

Then add the one-line hook (exact sentence from run-page.md) at: run-dir creation (state 1), scrape completion (2), gate opening (3), gate approval (4), driver launches (5), Beat 1 (6), Beat 2 (7), and in the *Failure handling* section (state 8).

- [ ] **Step 3: Grep verification**

- `grep -c "run-page" plugins/pl-tools/skills/demo-environment/SKILL.md` → ≥9 (subsection + 8 hooks).
- `grep -n "page_url" plugins/pl-tools/skills/demo-environment/SKILL.md` → manifest schema line + subsection.
- Open `references/run-page.md` and confirm the skeleton block has no external URLs.

- [ ] **Step 4: Commit**

```bash
git add plugins/pl-tools/skills/demo-environment/references/run-page.md plugins/pl-tools/skills/demo-environment/SKILL.md
git commit -m "feat(demo-environment): per-run progress artifact (run page) with milestone redeploys"
```

---

### Task 6: Live smoke run (interactive — requires Jamie)

**Files:** none created in the repo up front; corrections land wherever reality disagrees with the docs.

**Interfaces:**
- Consumes: everything above, on the new branch, with Jamie at the keyboard.

- [ ] **Step 1: Run one full demo-environment run** (any path; retain 3-order default exercises the most) against account 1626718 with a real brand, following the updated SKILL.md exactly — scrape agent during interview, run page publishing through its states, pace question asked, gate as release valve.

- [ ] **Step 2: Measure and record** — time from prospect URL to ✋ gate, and gate to first send; confirm the pane ownership rule held (no contention); confirm whether remote product images render on the artifact (update `run-page.md`'s image guidance to match reality).

- [ ] **Step 3: Correct any doc that disagreed with reality** (same-day, same-branch commits, one per correction, in the style of Task 13's engine corrections).

- [ ] **Step 4: Commit residuals and hand back** for the final whole-branch review per subagent-driven-development.

---

## Self-review

- **Spec coverage:** §3.1 → Task 4 (+ fallback + shortcut + pane rule); §3.2 → Task 5 (states table matches spec's, degradation + sharing covered); §3.3 → Tasks 3+4 (validator, intake, driver wiring, Beat 2 caveat); §3.4 → Tasks 1+2; §3.5 → no task (already shipped — recorded in spec); §4 manifest keys → Tasks 3 (pace) + 5 (page_url); §5 error handling → Tasks 4 (fallback, pane) + 5 (non-fatal publish); §7 testing → unit tests in 1–3, smoke in 6; §8 rollout → Global Constraints prerequisite note. No gaps.
- **Placeholder scan:** all steps carry real code/text; no TBDs.
- **Type consistency:** `results/scrape.json` shape identical in Tasks 4 and 5; `run.pace` values identical in Tasks 3, 4, 5; `--extras-file` naming consistent between Task 2's script and SKILL.md text; the milestone hook sentence identical in Task 5's two files.
