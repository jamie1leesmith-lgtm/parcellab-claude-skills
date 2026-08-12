# demo-environment Intake Standardisation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `pl-tools:demo-environment` ask a fixed, standard set of intake questions, and require zero human input after the ✋ plan gate on a clean run.

**Architecture:** A new `references/intake-script.md` becomes the single source of question wording and order, which `SKILL.md` Phase 0 points at instead of describing questions in prose. order-lifecycle's existing Gate C is hoisted into that script (it was already honoured by the orchestrated contract but never populated), gaining a new article-weight row. Three questions are removed — CDC synthetic generation, the Shopify store, and the Beat 1 edit-mode restore — and `validate_manifest.py` grows checks so the newly-populated manifest fields fail loudly rather than silently.

**Tech Stack:** Markdown skill files, Python 3 stdlib, `unittest`.

## Global Constraints

- **Tests are stdlib `unittest`. `pytest` is NOT installed — never `pip install`.** Run from `plugins/pl-tools/scripts`: `python3 -m unittest discover -s tests -v`
- **Frontmatter `name:` must equal the directory name.** A mismatch silently removes the skill from the plugin inventory. No task in this plan changes any `name:` or `description:` field — leave both alone.
- **Reference files via `${CLAUDE_PLUGIN_ROOT}`** — never `~/.claude/skills/…`, never a repo-relative path.
- **Never rename `parcellab-*` strings** (`parcellab-product-api`, `parcellab-brand-layout`, `$HOME/parcellab-previews/`, `~/.claude/parcellab-demo-request.env`, `parcellab-demo-request-scripts`).
- **`pl-tools` has no `version` field, deliberately.** Do not add one.
- **No anti-correction language in skill files** — state facts verifiably (cite a date, a live run, or a doc URL); never write "do not change this".
- **Do not `git push`.** Commit only. The user pushes when ready.
- Article weight fields, verbatim from `https://product-api.parcellab.com/v4/docs/markdown/order/`: `weight` (number), `weight_unit` (enum `kg` | `g` | `lbs` | `oz`, default `g`).

## Manifest contract (locked here, used by Tasks 1, 3, 4, 5)

`gates.order_lifecycle` carries:

```json
{
  "gate_b_answered": true,
  "gate_c": "send-as-is",
  "extras": {}
}
```

When extras were chosen, `gate_c` is `"extras"` and `extras` is non-empty, e.g.:

```json
{
  "gate_b_answered": true,
  "gate_c": "extras",
  "extras": {
    "announced_delivery_date": "2026-08-15",
    "article_weights": {
      "p1": {"weight": 300, "weight_unit": "g"},
      "p2": {"weight": 900, "weight_unit": "g"}
    }
  }
}
```

`article_weights` is keyed by **product `id`** (the goods code, e.g. `E491096-000`), never by SKU — the same rule the rest of the manifest follows.

## File Structure

| File | Responsibility |
|---|---|
| `plugins/pl-tools/scripts/validate_manifest.py` | Fail-loud manifest checks; gains gate_c / extras / promise-date / weight rules |
| `plugins/pl-tools/scripts/tests/test_validate_manifest.py` | unittest coverage for the above |
| `plugins/pl-tools/skills/order-lifecycle/SKILL.md` | Gate C table gains the article-weight row (standalone runs get it too) |
| `plugins/pl-tools/skills/demo-environment/references/intake-script.md` | **New.** Canonical question wording + order + option sets |
| `plugins/pl-tools/skills/demo-environment/SKILL.md` | Phase 0 points at the script; gate summary; Beat 1/2 automation |

---

### Task 1: Validator rules for gate_c, extras, promise dates and weights

**Files:**
- Modify: `plugins/pl-tools/scripts/validate_manifest.py:131-132`
- Test: `plugins/pl-tools/scripts/tests/test_validate_manifest.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: the manifest contract above, enforced. Tasks 3–5 write skill prose that must produce manifests passing these rules. Adds module constants `WEIGHT_UNITS = {"kg", "g", "lbs", "oz"}`, `GATE_C_VALUES = {"send-as-is", "extras"}`, `PROMISE_DATE_FIELDS = ("announced_delivery_date", "announced_delivery_date_min", "announced_delivery_date_max")` and `DATE_RE`.

The existing fixture at `tests/test_validate_manifest.py:53-54` already contains `"gate_c": "send-as-is", "extras": {}`, so `test_valid_manifest_passes` should keep passing unchanged.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_validate_manifest.py`, inside `class TestValidateManifest`:

```python
    def test_gate_c_value_must_be_known(self):
        errs = validate(broken(
            lambda m: m["gates"]["order_lifecycle"].update(gate_c="maybe")))
        self.assertTrue(any("gate C" in e for e in errs))

    def test_gate_c_extras_requires_non_empty_extras(self):
        errs = validate(broken(
            lambda m: m["gates"]["order_lifecycle"].update(
                gate_c="extras", extras={})))
        self.assertTrue(any("extras" in e for e in errs))

    def test_send_as_is_rejects_populated_extras(self):
        errs = validate(broken(
            lambda m: m["gates"]["order_lifecycle"].update(
                gate_c="send-as-is",
                extras={"announced_delivery_date": "2026-08-15"})))
        self.assertTrue(any("send-as-is" in e for e in errs))

    def test_promise_date_rejects_full_iso(self):
        errs = validate(broken(
            lambda m: m["gates"]["order_lifecycle"].update(
                gate_c="extras",
                extras={"announced_delivery_date": "2026-08-15T10:00:00Z"})))
        self.assertTrue(any("YYYY-MM-DD" in e for e in errs))

    def test_promise_date_accepts_plain_date(self):
        m = valid_manifest()
        m["gates"]["order_lifecycle"].update(
            gate_c="extras", extras={"announced_delivery_date": "2026-08-15"})
        self.assertEqual(validate(m), [])

    def test_article_weight_unit_enum(self):
        errs = validate(broken(
            lambda m: m["gates"]["order_lifecycle"].update(
                gate_c="extras",
                extras={"article_weights": {
                    "p1": {"weight": 300, "weight_unit": "stone"}}})))
        self.assertTrue(any("weight_unit" in e for e in errs))

    def test_article_weight_must_be_a_positive_number(self):
        errs = validate(broken(
            lambda m: m["gates"]["order_lifecycle"].update(
                gate_c="extras",
                extras={"article_weights": {
                    "p1": {"weight": "300", "weight_unit": "g"}}})))
        self.assertTrue(any("weight" in e for e in errs))

    def test_article_weight_key_must_be_a_known_product_id(self):
        errs = validate(broken(
            lambda m: m["gates"]["order_lifecycle"].update(
                gate_c="extras",
                extras={"article_weights": {
                    "sku1": {"weight": 300, "weight_unit": "g"}}})))
        self.assertTrue(any("unknown product" in e for e in errs))

    def test_article_weights_accepted_when_well_formed(self):
        m = valid_manifest()
        m["gates"]["order_lifecycle"].update(
            gate_c="extras",
            extras={"article_weights": {"p1": {"weight": 300,
                                               "weight_unit": "g"}}})
        self.assertEqual(validate(m), [])
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd plugins/pl-tools/scripts && python3 -m unittest tests.test_validate_manifest -v
```

Expected: the nine new tests FAIL (the validator has no gate_c rules yet, so `validate` returns `[]` and every `assertTrue(any(...))` fails). `test_valid_manifest_passes` still PASSES.

- [ ] **Step 3: Add the module constants**

In `validate_manifest.py`, after `PACES = {"standard", "fast"}` (line 19), add:

```python
GATE_C_VALUES = {"send-as-is", "extras"}
WEIGHT_UNITS = {"kg", "g", "lbs", "oz"}
PROMISE_DATE_FIELDS = ("announced_delivery_date",
                       "announced_delivery_date_min",
                       "announced_delivery_date_max")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
```

and add `import re` beside `import json` at the top.

- [ ] **Step 4: Implement the rules**

Replace line 132 (`need(gates.get("gate_b_answered") is True, "gate B answer missing")`) with:

```python
    need(gates.get("gate_b_answered") is True, "gate B answer missing")

    gate_c = gates.get("gate_c")
    extras = gates.get("extras") or {}
    need(gate_c in GATE_C_VALUES,
         f"gate C answer must be one of {sorted(GATE_C_VALUES)} (got {gate_c!r})")
    if gate_c == "extras":
        need(bool(extras), "gate C is 'extras' but extras is empty")
    if gate_c == "send-as-is":
        need(not extras,
             "gate C is 'send-as-is' but extras carries fields")

    for field in PROMISE_DATE_FIELDS:
        value = extras.get(field)
        if value is not None:
            need(isinstance(value, str) and bool(DATE_RE.match(value)),
                 f"extras.{field} must be YYYY-MM-DD, not a full ISO "
                 f"datetime (got {value!r})")

    weights = extras.get("article_weights") or {}
    for pid, entry in weights.items():
        need(pid in products,
             f"extras.article_weights: unknown product {pid} — key by "
             f"product id, not SKU")
        entry = entry or {}
        weight = entry.get("weight")
        need(isinstance(weight, (int, float)) and not isinstance(weight, bool)
             and weight > 0,
             f"extras.article_weights[{pid}].weight must be a positive "
             f"number (got {weight!r})")
        need(entry.get("weight_unit") in WEIGHT_UNITS,
             f"extras.article_weights[{pid}].weight_unit must be one of "
             f"{sorted(WEIGHT_UNITS)} (got {entry.get('weight_unit')!r})")
```

`products` is already in scope — it is built earlier in `validate()` and used at line 102 for the same "unknown product" check.

- [ ] **Step 5: Run the tests to verify they pass**

```bash
cd plugins/pl-tools/scripts && python3 -m unittest tests.test_validate_manifest -v
```

Expected: PASS, all tests including the pre-existing ones.

- [ ] **Step 6: Run the whole suite for regressions**

```bash
cd plugins/pl-tools/scripts && python3 -m unittest discover -s tests -v
```

Expected: PASS. If anything unrelated fails, confirm it fails on a clean checkout before touching it — do not fix pre-existing failures in this plan.

- [ ] **Step 7: Commit**

```bash
git add plugins/pl-tools/scripts/validate_manifest.py plugins/pl-tools/scripts/tests/test_validate_manifest.py
git commit -m "feat(validate): enforce gate C, extras, promise dates and article weights"
```

---

### Task 2: Article-weight row in order-lifecycle's Gate C

**Files:**
- Modify: `plugins/pl-tools/skills/order-lifecycle/SKILL.md:508-516` (the Gate C table)

**Interfaces:**
- Consumes: the field names from Global Constraints.
- Produces: the Gate C menu row that Task 3's intake script reproduces verbatim.

This is the single source of truth for the menu. demo-environment reuses it, so standalone runs gain the row too.

- [ ] **Step 1: Add the table row**

In the Gate C table, after the `Delivery detail` row (line 516), add:

```markdown
| Article physical data | `weight`, `weight_unit` on each article | Article-level, not order-level — set at **both** levels, `articles_order` and every `add_tracking`'s `tracking.articles`, like every other article field. `weight_unit` is one of `kg` / `g` / `lbs` / `oz` and defaults to `g` (v4 Order API docs, `https://product-api.parcellab.com/v4/docs/markdown/order/`). snake_case only: `weight` has no legacy camelCase twin, so if a comm template renders it blank, check the dual-family rule before adding a value. |
```

- [ ] **Step 2: Add the dimensions note under the table**

After the existing "**Split shipments are not offered here**" paragraph (line 518-519), add:

```markdown
**Article dimensions are not offered.** The v4 docs describe `width`, `height`
and `length` as millimetres while `length_unit` is a `const` of `cm`. Until one
live order settles which is right, a size rendered in a demo could be wrong by a
factor of ten. Add them once a run proves the unit.
```

- [ ] **Step 3: Verify the table still renders as a table**

```bash
sed -n '505,530p' plugins/pl-tools/skills/order-lifecycle/SKILL.md
```

Expected: every row starts and ends with `|`, the new row has exactly 3 cells matching the `| Extra | Fields | State this |` header, and no pipe characters appear unescaped inside the cell text.

- [ ] **Step 4: Commit**

```bash
git add plugins/pl-tools/skills/order-lifecycle/SKILL.md
git commit -m "feat(order-lifecycle): offer article weight at Gate C"
```

---

### Task 3: The canonical intake script

**Files:**
- Create: `plugins/pl-tools/skills/demo-environment/references/intake-script.md`

**Interfaces:**
- Consumes: the Gate C row from Task 2; the manifest contract above.
- Produces: the file Task 4's `SKILL.md` Phase 0 points at. Question numbering (1–14) is referenced by Task 5's gate summary.

- [ ] **Step 1: Write the file**

```markdown
# demo-environment — canonical intake script

Ask these questions in this order, with this wording. Conditional questions are
marked; skip one when its condition is false, never reorder the rest. Batch a
round with AskUserQuestion where the questions are independent.

Standard wording matters because the answers become manifest fields: a question
asked three different ways across three runs produces three differently-shaped
answers, and the run page and telemetry compare runs to each other.

## Round 1 — before the scrape agent is dispatched

Everything that has to be settled before the scrape brief can be written.

| # | Question | Options | Condition |
|---|---|---|---|
| 1 | Are returns in scope for this demo? | No · Yes | always |
| 2 | Is this a Shopify opp? | No · Yes | Q1 = yes |
| 3 | Reuse the pool scraped for **\<brand\>** on \<date\>, or scrape fresh? | Reuse · Scrape fresh | a prior run dir with the same handle holds both `scrape/brand-tokens.json` and `scrape/product-pool.json` |

Q1 no → **engage**. Q1 yes + Q2 no → **retain**. Q1 yes + Q2 yes →
**retain-shopify**. An Engage-only run never asks Q2; Retain covers the Engage
story automatically.

## Round 2 — batched, while the scrape agent runs

| # | Question | Options | Condition |
|---|---|---|---|
| 4 | Which country are these orders delivering to? | US · UK · DE · Other | always — never assume it |
| 5 | How many orders, and which scenario and fraud level for each? | the default matrix below | always |
| 6 | What pace should the journeys run at? | Standard (200 s gaps, comm ordering safe) · Fast (60 s gaps, comms may arrive out of order) | always |
| 7 | Anything else to add to every order, or send as-is? | the Gate C menu below | always |
| 8 | Which region and category should the CDC request use? | US/UK/DE × Home/Electronics/Fashion | always |
| 9 | Which account should this demo build in? | \<user's own demo account\> · parcelfashion | always — parcelfashion is offered only when `CDC_ACCOUNT_CONFIG_PARCELFASHION` is stored, and never on retain-shopify |
| 10 | Using **\<name\>** (\<id\>) — correct? | Yes · Pick another | always |
| 11 | The edit-mode guard is not restricted to this account. Fix it? | Fix it · Leave it | `parcellab settings edit-mode show` is not `account-restricted` for the target |
| 12 | These write permissions are missing — add them to `~/.claude/settings.json`? | (the user edits the file themselves) | `permissions.allow` does not cover the run's writes |
| 13 | What is the CDC account config UUID for this target? | (a UUID, or skip) | the target's config key is missing from the env |
| 14 | Which Shopify store should this seed into? | (the authed stores) | retain-shopify **and** 2+ stores authed |

### Q5 — the default matrix

Offer this first; the user adjusts from it. 1–5 orders, default 3.

| Order | Fraud | Scenario |
|---|---|---|
| #1 | low | happy |
| #2 | medium | split — parcel A happy, parcel B stuck-delay |
| #3 | high | recovered |
| #4 | low | manual_return (retain paths only) |
| #5 | low | return_tracking (retain paths only) |

Scenario vocabulary: `happy` · `stuck-delay` · `recovered`
(`InTransit → WarehouseDelay → OutForDelivery → Delivered`, proven live
2026-08-11) · `locker` (`… → Delivered-ParcelLocker`, status unproven) ·
`custom` (user-specified sequence, labelled per order-lifecycle's confidence
rules). Runs of 2+ orders need at least one split-shipment order. Every order
gets a distinct synthetic customer (region-appropriate name + email) —
generate them and show them.

### Q7 — the Gate C menu

The default is send-as-is, and skipping takes one word. Offer the menu from
order-lifecycle's Gate C table verbatim: promise dates · order financials ·
article physical data · delivery detail · tags/custom fields · dynamic
recipients · extra articles.

Do **not** ask an open "any other fields?" — that is unanswerable unless the
user has the Order API spec memorised.

Three rules specific to an orchestrated run:

- **One answer covers every order.** Extras are per-run, not per-order.
- **Tags merge, they do not replace.** `prepare_fraud_fragment.py` already
  writes each order's top-level `tags` and `additional_attributes`. Union the
  intake's tags with the fraud fragment's output per order; neither side
  overwrites the other. Overwriting discards the fraud data the whole run is
  built to demonstrate.
- **The `client_key` pre-fill does not apply.** Standalone Gate C pre-fills a
  `client_key` when Gate B introspected a journey needing one. Here Gate B is
  answered by the manifest and no introspection runs, so nothing is pre-filled.

Record the answer as `gates.order_lifecycle.gate_c` (`"send-as-is"` or
`"extras"`) plus `extras`. Promise dates are resolved to absolute `YYYY-MM-DD`
at manifest-write time — a full ISO datetime is rejected by the API.

### Q7 — deriving article weights

When the user turns on article physical data, do not ask for a value per
product. Derive one per article from its `product_type` and show every derived
value at the ✋ gate, article by article, so it can be corrected before anything
is sent.

Match case-insensitively on the `product_type` string; first match wins.

| `product_type` contains | Weight |
|---|---|
| shoe, boot, sneaker, trainer | 900 g |
| coat, jacket, knit, jumper, hoodie | 700 g |
| shirt, tee, top, dress, trouser, sock, apparel | 300 g |
| bag, hat, belt, scarf, accessor | 500 g |
| phone, laptop, tablet, electronic, device, audio | 1200 g |
| home, kitchen, decor, furnish | 800 g |
| (no match) | 500 g |

Unit is `g` unless the user says otherwise. Write them to
`extras.article_weights`, keyed by product **`id`** (the goods code) and never
by SKU — `validate_manifest.py` rejects SKU keys.

## Questions this script deliberately does not contain

Each of these was a question once. Removing them is what makes a clean run
unattended after the ✋ gate.

| Not asked | Instead |
|---|---|
| Should the CDC also generate synthetic orders? | `generate_orders` is always `false` and `cdc.orders` always `[]`. The ✋ gate states `CDC synthetic generation: off` so it stays visible. |
| Which Shopify store? (when only one) | Resolved from `~/.claude/parcellab-shopify-seed.env`, else `shopify store auth list`. Exactly one → use it and state it at the gate. Zero → stop and point at `/pl-setup`. 2+ → Q14. |
| Restore the edit-mode guard? | Restored automatically after Beat 2, once every driver has exited. |
| Record this proven event in `status-codes.md`? | Recorded automatically by Beat 2, which reports what it wrote. |
```

- [ ] **Step 2: Verify the file is reachable and well-formed**

```bash
python3 -c "import pathlib,sys; p=pathlib.Path('plugins/pl-tools/skills/demo-environment/references/intake-script.md'); t=p.read_text(); print('lines:',len(t.splitlines())); print('q14 present:', 'Which Shopify store' in t); print('unbalanced tables:', [l for l in t.splitlines() if l.startswith('|') and not l.rstrip().endswith('|')])"
```

Expected: the file reads, `q14 present: True`, and `unbalanced tables: []`.

- [ ] **Step 3: Commit**

```bash
git add plugins/pl-tools/skills/demo-environment/references/intake-script.md
git commit -m "feat(demo-environment): add the canonical intake script"
```

---

### Task 4: Point Phase 0 at the script and drop the removed questions

**Files:**
- Modify: `plugins/pl-tools/skills/demo-environment/SKILL.md:114-124` (step 2), `:170-234` (step 4)

**Interfaces:**
- Consumes: `references/intake-script.md` from Task 3.
- Produces: a Phase 0 that populates `gates.order_lifecycle.gate_c`/`extras` and writes `cdc.generate_orders: false` as a constant — which Task 1's validator now enforces.

The prose bullets currently in steps 2 and 4 are replaced by a pointer plus the
mechanics that are *not* questions (env lookups, CLI verification). Keep every
non-question mechanic — this task moves questions out, it does not delete
behaviour.

- [ ] **Step 1: Replace step 2's question prose with a pointer**

In step 2, replace the sentence beginning "take the prospect URL and ask ONLY the path questions" with:

```markdown
   take the prospect URL and ask **Round 1** of
   `${CLAUDE_PLUGIN_ROOT}/skills/demo-environment/references/intake-script.md`
   — the path questions plus, when one applies, the reuse offer. Ask them in
   that file's order, with that file's wording. That is the minimum needed to
   know what to collect, and everything that has to be settled before the
   scrape agent is dispatched.
```

Leave the **Prior-pool detection** paragraph exactly as it is — it describes how
to detect the candidate, which is not a question.

- [ ] **Step 2: Replace step 4's bullet list with a pointer plus the non-question mechanics**

Replace step 4's opening line and the bullets for destination country, order plan, pace and CDC region (lines 170-188) with:

```markdown
4. **Interview concurrently, in chat** — ask **Round 2** of
   `${CLAUDE_PLUGIN_ROOT}/skills/demo-environment/references/intake-script.md`
   while the scrape agent runs, batching with AskUserQuestion where the
   questions are independent. Ask them in that file's order, with that file's
   wording; it also carries the default order matrix, the Gate C menu rules and
   the article-weight derivation table. The mechanics below are not questions —
   they are the lookups and verifications those answers depend on.
```

- [ ] **Step 3: Rewrite the Shopify resolution bullet so it does not ask**

Replace the **Shopify resolution (retain-shopify only)** bullet (lines 189-193) with:

```markdown
   - **Shopify resolution (retain-shopify only):** First `command -v shopify` —
     if the CLI is missing, stop and point the user at `/pl-setup`'s optional
     Shopify CLI section (install + full-scope store auth) rather than
     improvising an install mid-intake; the auth must carry the
     order/fulfilment scopes or the order engine hits a re-consent wall later.
     Then resolve the store **without asking**: read
     `~/.claude/parcellab-shopify-seed.env`, else `shopify store auth list`.
     Exactly one store → use it and state it at the ✋ gate. None → stop and
     point at `/pl-setup`. Two or more → this is the only case that asks
     (intake-script Q14). Then resolve the location GID immediately — follow
     shopify-seed Steps 1–2 exactly, including the fulfils-online-orders
     preference rules. Record both in the manifest.
```

- [ ] **Step 4: Make CDC generation a constant**

In the **CDC config** bullet, replace the sentence beginning "`generate_orders` is **false** unless the user asks" and its `cdc.orders` composition guidance (lines 227-231) with:

```markdown
     `generate_orders` is always `false` and `cdc.orders` always `[]` — the run
     never asks the CDC to generate synthetic orders alongside its real ones,
     and the ✋ gate states this as a fixed line so it stays visible. The
     config still matters for linking: the CDC resolves linked order numbers in
     the config's target account, so a mismatched config fails linking with
     "No parcelLab order found" (live-verified 2026-08-11).
```

- [ ] **Step 5: Verify no orphaned question text remains**

```bash
grep -n "generate_orders\|Shopify opp\|returns in scope\|which store" plugins/pl-tools/skills/demo-environment/SKILL.md
```

Expected: `generate_orders` appears only as the constant above and in the manifest schema; no line still poses the Shopify-store or CDC-generation question. The Paths section near line 23 still names the returns/Shopify questions — that is the routing summary and stays.

- [ ] **Step 6: Commit**

```bash
git add plugins/pl-tools/skills/demo-environment/SKILL.md
git commit -m "refactor(demo-environment): ask Phase 0's questions from the intake script"
```

---

### Task 5: Gate summary and manifest schema

**Files:**
- Modify: `plugins/pl-tools/skills/demo-environment/SKILL.md:312-324` (step 8 gate), `:341-366` (step 9 manifest schema)

**Interfaces:**
- Consumes: the manifest contract; Task 3's derivation table.
- Produces: a ✋ gate whose summary itemises every extra, satisfying Gate C's "an extra that was discussed but does not appear in the summary is a defect" rule.

- [ ] **Step 1: Extend the gate summary list**

In step 8, in the list beginning "core 4 (four distinct product types)", after the CDC region/category/config source item, replace the "CDC synthetic generation on/off (+ which slots)" item with:

```markdown
   `CDC synthetic generation: off` (a fixed line, never a question) ·
   **every extra agreed at Q7, field by field with its actual value** —
   including each auto-derived article weight listed per article, because an
   auto-derived value the user never saw is worse than one they rejected ·
```

- [ ] **Step 2: Record the extras in the manifest schema**

In step 9's schema, replace `gates{order_lifecycle{gate_b_answered,gate_c, extras}}` with:

```markdown
   `gates{order_lifecycle{gate_b_answered, gate_c: "send-as-is"|"extras",
   extras}}` — `extras` is empty when `gate_c` is `send-as-is`, and non-empty
   otherwise. Promise dates in `extras` are `YYYY-MM-DD` (a full ISO datetime
   is rejected by the API). `extras.article_weights` is keyed by product `id`,
   never SKU — the same rule as everywhere else in the manifest —
   `{<product id>: {weight: <number>, weight_unit: "kg"|"g"|"lbs"|"oz"}}`.
   `validate_manifest.py` enforces all of this,
```

- [ ] **Step 3: Verify the gate summary and schema agree with the validator**

Build a throwaway manifest carrying extras and run the real validator against it:

```bash
cd plugins/pl-tools/scripts && python3 -c "
import json, sys
sys.path.insert(0, 'tests')
from test_validate_manifest import valid_manifest
from validate_manifest import validate
m = valid_manifest()
m['gates']['order_lifecycle'].update(
    gate_c='extras',
    extras={'announced_delivery_date': '2026-08-15',
            'article_weights': {'p1': {'weight': 300, 'weight_unit': 'g'}}})
print('errors:', validate(m))
"
```

Expected: `errors: []`.

- [ ] **Step 4: Commit**

```bash
git add plugins/pl-tools/skills/demo-environment/SKILL.md
git commit -m "feat(demo-environment): itemise extras and article weights at the plan gate"
```

---

### Task 6: Automate the Beat 1 restore offer and the Beat 2 status-codes offer

**Files:**
- Modify: `plugins/pl-tools/skills/demo-environment/SKILL.md:539-568` (Beat 1 and Beat 2)

**Interfaces:**
- Consumes: the "repointed for this run" note recorded at Phase 0 step 4.
- Produces: no manifest change. This task removes two user-facing questions.

The restore moves to **after Beat 2**, not Beat 1. Beat 1 fires right after
Phase 3 while the order drivers are still pushing events — Beat 2 waits ≥15
minutes after the final event. Restoring the guard at Beat 1 would point it away
from the account those drivers write to, and their remaining pushes would hit
the guard.

- [ ] **Step 1: Delete Beat 1's restore offer**

In Beat 1, remove the sentence: "**If the edit-mode guard was repointed for this run** (per Phase 0 step 4's note), offer here to restore it to the user's own account." Replace it with:

```markdown
**If the edit-mode guard was repointed for this run** (per Phase 0 step 4's
note), say so here as a line of fact and state that it is restored after Beat 2
— not now. The drivers are still pushing events against that account.
```

- [ ] **Step 2: Add the auto-restore to Beat 2**

In Beat 2, after the sentence ending "explicitly covering the good AND bad arcs the run promised.", add:

```markdown
**Restore the edit-mode guard.** Once every driver has exited and the
verification above is done, if the guard was repointed for this run, restore it
to the user's own account — no question, and report it in one line. If the
restore fails, say so explicitly with the error; a guard left pointing at
another account is exactly the state the next run's Phase 0 check will trip on.
```

- [ ] **Step 3: Replace the status-codes offer with automatic recording**

Replace "For every unproven event or chain that fired correctly, offer to record it in `${CLAUDE_PLUGIN_ROOT}/skills/order-lifecycle/references/status-codes.md`." with:

```markdown
For every unproven event or chain that fired correctly, record it in
`${CLAUDE_PLUGIN_ROOT}/skills/order-lifecycle/references/status-codes.md` —
automatically, then report what was written. Each entry carries the date, the
order number and the account, so a later reader can check it. A run edits a
skill reference file here on purpose: the alternative is proven status codes
staying labelled unproven because nobody answered a prompt at the end of a
fifteen-minute run.
```

- [ ] **Step 4: Verify no post-gate question survives on the clean path**

```bash
sed -n '535,575p' plugins/pl-tools/skills/demo-environment/SKILL.md | grep -niE "offer|ask|confirm"
```

Expected: no hit that poses a question to the user on a successful run. Hits describing failure handling are fine and should stay.

- [ ] **Step 5: Commit**

```bash
git add plugins/pl-tools/skills/demo-environment/SKILL.md
git commit -m "feat(demo-environment): restore the guard and record status codes without asking"
```

---

### Task 7: Whole-repo verification

**Files:**
- Modify: none (fix-forward only if something fails)

**Interfaces:**
- Consumes: every prior task.
- Produces: evidence the plugin still loads and the suite is green.

- [ ] **Step 1: Run the full test suite**

```bash
cd plugins/pl-tools/scripts && python3 -m unittest discover -s tests -v
```

Expected: PASS. A failure unrelated to this plan must be confirmed pre-existing (`git stash` and re-run) before being left alone — and then reported plainly, not fixed here.

- [ ] **Step 2: Confirm the skills still load**

```bash
python3 - <<'PY'
import pathlib, re
root = pathlib.Path("plugins/pl-tools/skills")
for skill in sorted(root.iterdir()):
    f = skill / "SKILL.md"
    if not f.exists():
        continue
    head = f.read_text().split("---")[1]
    name = re.search(r"^name:\s*(\S+)", head, re.M).group(1)
    status = "OK" if name == skill.name else "MISMATCH"
    print(f"{status}: dir={skill.name} name={name}")
PY
```

Expected: `OK` for every skill. A `MISMATCH` silently removes that skill from the plugin inventory.

- [ ] **Step 3: Confirm every referenced file exists**

```bash
grep -ohE '\$\{CLAUDE_PLUGIN_ROOT\}/[A-Za-z0-9_./-]+' -r plugins/pl-tools/skills | sort -u | while read -r ref; do
  p="plugins/pl-tools/${ref#\$\{CLAUDE_PLUGIN_ROOT\}/}"
  [ -e "$p" ] && echo "OK   $ref" || echo "MISS $ref"
done
```

Expected: no `MISS` lines for anything this plan created or referenced — in particular `references/intake-script.md` resolves. Pre-existing `MISS` lines outside this plan's scope get reported, not fixed.

- [ ] **Step 4: Report**

State plainly: suite result, skill-name check result, reference check result, and anything confirmed pre-existing. Do not claim completion without pasting the actual command output.

---

## Notes for the implementer

- **Do not change any `name:` or `description:` frontmatter.** `description:` is trigger text; the word "parcelLab" must stay spelled out in it.
- **Do not add a `version:` to `pl-tools`.** Its version is the git SHA on purpose; `plugin validate` warning about a missing version is expected and correct.
- **Article weight is per-article; extras are otherwise per-run.** That asymmetry is deliberate — weight is derived per product, everything else is one value for the run.
- **Nothing here is a live parcelLab write.** No task in this plan calls the Order API, the CDC, or Shopify. If a step seems to require one, stop and ask.
