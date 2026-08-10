# Article Categories and Extras Gate — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make both pl-tools order skills ask explicitly about `article_category` (which drives returns-portal reason filters) and treat extra payload info as a blocking gate whose agreed values are itemised in the final pre-send summary.

**Architecture:** Documentation-only change to two `SKILL.md` files plus one README note. No scripts, no new reference files. `create-order` gains a category step and a short extras gate it currently lacks; `order-lifecycle` folds categories into its existing Gate A and tightens Gate C's summary. Spec: `docs/superpowers/specs/2026-08-10-order-skills-category-extras-gate-design.md`.

**Tech Stack:** Markdown skill files (Claude Code plugin skills). Regression check only via stdlib `unittest`.

## Global Constraints

- The API field is **`article_category`**, free-text string, no enum. It exists on both `articles_order[]` and `tracking.articles[]`.
- Standard categories offered (a convention, not an enum): `fashion`, `home`, `electronics`, `beauty`, `sports`, `food`, `toys`, `media`. Any string is valid.
- Category input is **preserved verbatim, case included** — never normalised. Portal reason filters match literally.
- Untracked orders (no `mutations`) carry the category at order level only.
- **Do not touch either skill's frontmatter `name:` or `description:`.** `name:` must keep equalling the directory name; `description:` is trigger text.
- **Never add a `version` field to `pl-tools`.** Its version is the git commit SHA.
- Reference files only via `${CLAUDE_PLUGIN_ROOT}` — not applicable here, but do not introduce repo-relative or `~/.claude/skills/` paths.
- Tests are stdlib `unittest`; never `pip install`, never `pytest`.
- `order-lifecycle` stays a **three-gate** skill: A, B, C.
- Do not use anti-correction phrasing ("do not change this") in skill files; state verifiable facts instead.

---

### Task 1: `create-order` — category step, extras gate, itemised summary

**Files:**
- Modify: `plugins/pl-tools/skills/create-order/SKILL.md` (workflow steps 2a–4, *Payload shape* notes, new *Article categories* and *Extra order information* sections)
- Modify: `plugins/pl-tools/skills/create-order/README.md:63` (confirmation-summary paragraph)

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: the section heading names `## Article categories` and `## Extra order information` and the eight standard category strings. Task 2 cross-references `create-order`'s *Article categories* section by that exact heading, the way it already cross-references *Defaults & dummy data*.

- [ ] **Step 1: Add workflow step 2b for categories**

In `SKILL.md`, immediately after existing step `2a` (carrier confirmation), insert:

```markdown
2b. **Confirm article categories before building the payload.** `article_category`
   is what returns-portal reason filters key on, so never leave it off and never
   pick it silently. Propose a baseline from what the products are, then ask —
   see *Article categories* below.
```

- [ ] **Step 2: Add the `## Article categories` section**

Insert a new section after *Payload shape* and before *Additional recipients (Dynamic Recipients)*:

```markdown
## Article categories

`article_category` is a free-text string on each article. The returns portal's
return-reason filters key on it, so an order built for a returns demo shows the
wrong reasons — or none — when the category is missing or spelled differently
from what the portal expects. Nothing in the API response signals this.

**Propose a baseline, then ask.** Derive one category from what the products
actually are (four clothing items → `fashion` for all four) and put the question
in a single exchange:

> Categories drive which return reasons show in the portal. I'd set **`fashion`**
> for all 4 items. Keep it, set a different one for all, or go per-product?
> Standards: `fashion`, `home`, `electronics`, `beauty`, `sports`, `food`,
> `toys`, `media` — or any string you like.

- Blocking: don't send a payload on an unanswered category prompt. "Keep it"
  answers it in one word.
- A proposal is not a default — show it and get it accepted.
- The eight standards are this skill's convention. The API accepts any string.
- **Use the user's string verbatim, case included.** If the portal filter keys on
  `Fashion`, sending `fashion` matches nothing. Normalising the input breaks the
  match.
- Per-product categories are expected for a mixed order (jacket + kettle).
- **Write it at both levels**: `articles_order[].article_category` *and* every
  `add_tracking.tracking.articles[].article_category`. Returns eligibility is
  derived from `tracking.articles`, so an order-level-only category leaves the
  returns portal filtering on nothing. Untracked orders (no `mutations`) have
  only the order level to write to.
```

- [ ] **Step 3: Add `article_category` to both payload examples**

In *Payload shape*, in the realistic tracked-order example, add the field to the `articles_order` entry (after `article_name`) and to the `tracking.articles` entry (after `article_name`):

```json
"article_category": "fashion",
```

Then add a bullet to the *Notes* list under that example, directly after the existing `tracking.articles` bullet:

```markdown
- **`article_category` belongs on every article at both levels** — see *Article
  categories*. It drives the returns portal's return-reason filters.
```

- [ ] **Step 4: Add the `## Extra order information` section**

Insert after *Article categories*:

```markdown
## Extra order information

Ask this once, after categories and before the payload summary. It is an offer
with a fast exit, not a form:

> Anything else to add to this order, or send as-is?

Then show this menu. Don't ask an open "any other fields?" — that's unanswerable
unless the user has the Order API spec memorised.

| Extra | Fields | State this |
|---|---|---|
| Dynamic recipients | `additional_recipients: [{role, email}]` at **both** order and tracking level | Role matches the Journey's `advancedRecipients` literally, case-sensitive. Preserve the user's spelling even if it looks like a typo. See *Additional recipients*. |
| Promise dates | `announced_delivery_date`, `announced_delivery_date_min`, `announced_delivery_date_max` | **`YYYY-MM-DD` only** — a full ISO datetime is rejected. (`order_date` does take full ISO; the fields differ.) |
| Order financials | `order_tax_amount`, `order_net_amount`, `order_discount_amount` | For invoice-style comms |
| Tags / custom fields | `tags`, `additional_attributes` | What filter-driven Journey triggers key on |

Anything the user asks for that isn't listed is still fair game — check the
[full spec](https://docs.parcellab.com/docs/developers/orders/full-order-api-spec)
rather than refusing.
```

- [ ] **Step 5: Make workflow step 4's summary itemise everything agreed**

Replace the body of workflow step 4 with:

```markdown
4. **Show the payload and ask the user to confirm.** Display a summary that
   itemises, field by field:
   - order_number, recipient, destination country, courier, tracking number
   - every article with its `article_category`
   - **every extra agreed at the previous step, with its actual value**

   An extra that was discussed but doesn't appear here is a defect: this summary
   is the last point where a wrong promise date or a mistyped recipient role is
   catchable, and both are invisible in the API's success response. Offer the
   full JSON on request. Then ask "send this to ParcelLab?" and wait for an
   affirmative reply before step 5 — every successful PUT writes a real order to
   their production account.
```

- [ ] **Step 6: Update the README's confirmation paragraph**

In `README.md`, in *Always show the payload before sending*, replace the last sentence ("We show a tight summary table (order number, recipient, country, courier, tracking number, article count) by default with the full JSON on request — the table is what humans actually read.") with:

```markdown
We show a tight summary table by default with the full JSON on request — the table
is what humans actually read. It itemises order number, recipient, country,
courier, tracking number, each article with its `article_category`, and every
extra field agreed during the run. Categories and extras are listed individually
rather than counted, because a wrong `article_category` (which drives the returns
portal's reason filters) or a mistyped promise date both return a clean HTTP 200 —
the summary is the only place they surface.
```

- [ ] **Step 7: Verify the edits**

Run:

```bash
cd /Users/jamie.lee-smith/Documents/Claude/Projects/parcellab-claude-skills && grep -c "article_category" plugins/pl-tools/skills/create-order/SKILL.md && grep -n "^name: create-order$" plugins/pl-tools/skills/create-order/SKILL.md && grep -n "## Article categories\|## Extra order information" plugins/pl-tools/skills/create-order/SKILL.md
```

Expected: the count is at least 6 (two payload examples × 2 levels, plus section prose), `name: create-order` still present on its own line, and both new headings found.

- [ ] **Step 8: Confirm the description line is untouched**

Run:

```bash
cd /Users/jamie.lee-smith/Documents/Claude/Projects/parcellab-claude-skills && git diff -- plugins/pl-tools/skills/create-order/SKILL.md | grep -E "^[-+]description:|^[-+]name:"
```

Expected: **no output.** Any hit means frontmatter changed — revert that line.

- [ ] **Step 9: Commit**

```bash
cd /Users/jamie.lee-smith/Documents/Claude/Projects/parcellab-claude-skills && git add plugins/pl-tools/skills/create-order/SKILL.md plugins/pl-tools/skills/create-order/README.md && git commit -m "feat(create-order): gate article categories and extra order info before send"
```

---

### Task 2: `order-lifecycle` — categories in Gate A, itemised Gate C summary

**Files:**
- Modify: `plugins/pl-tools/skills/order-lifecycle/SKILL.md` (workflow steps 4 and 8, *Order + tracking setup* step 2, *Gate C — order enrichment*, *Confirmation gates*)

**Interfaces:**
- Consumes: the `## Article categories` heading in `create-order/SKILL.md` and the eight standard strings from Task 1. This task cross-references that section by name rather than restating the rules, matching how it already points at `create-order`'s *Defaults & dummy data*.
- Produces: nothing later tasks depend on.

- [ ] **Step 1: Fold categories into workflow step 4**

Replace workflow step 4 with:

```markdown
4. **Gate A — product and category approval.** Show product(s) with a proposed
   `article_category` for each; wait for approval of both. See *Gate A — product
   and category approval*.
```

- [ ] **Step 2: Add the Gate A section**

Insert a new section immediately after *Product sourcing* and before *Order + tracking setup (before the event loop)*:

```markdown
## Gate A — product and category approval

Show each sourced product — name, price, image URL, store URL — with a proposed
`article_category`, and get both approved in one exchange. Categories ride along
here because the products are already on screen; they don't need a gate of their
own.

`article_category` is what the returns portal's return-reason filters key on, so
a run built for a returns demo shows the wrong reasons — or none — when it's
missing or cased differently from what the portal expects. Nothing in the API
response signals this.

Propose one category derived from what the products are (four clothing items →
`fashion` for all four), then ask:

> Categories drive which return reasons show in the portal. I'd set **`fashion`**
> for all 4 items. Keep it, set a different one for all, or go per-product?
> Standards: `fashion`, `home`, `electronics`, `beauty`, `sports`, `food`,
> `toys`, `media` — or any string you like.

- Blocking, like the rest of Gate A. "Keep it" answers it in one word.
- A proposal is not a default — it has to be shown and accepted.
- The eight standards are a convention; the API takes any string.
- **Use the user's string verbatim, case included.** If the portal filter keys on
  `Fashion`, sending `fashion` matches nothing.
- Per-product categories are expected for a mixed order.
- Full rules, including the untracked-order case, are in `create-order`'s
  *Article categories*.
```

- [ ] **Step 3: Add category to the tracking-articles rule**

In *Order + tracking setup (before the event loop)*, step 2, add `"article_category": "fashion",` to the example `tracking.articles` entry (after `"article_name"`), and extend the paragraph that begins "Mirror the same items (with matching `line_item_id`s)" so it reads:

```markdown
   Mirror the same items (with matching `line_item_id`s) from `articles_order`
   into `tracking.articles`, **including `article_category`** — returns
   eligibility is derived from `tracking.articles`, so a category present only at
   order level leaves the returns portal filtering on nothing:
```

- [ ] **Step 4: Make Gate C's final summary itemise everything**

In *Gate C — order enrichment*, replace the closing paragraph ("After the menu, show the final plan — order summary, carrier(s), scenario per shipment, event list with expected comms, and the gap — then wait for approval. This is the last stop before anything reaches production.") with:

```markdown
After the menu, show the final plan and wait for approval. It itemises, field by
field:

- order summary, carrier(s), scenario per shipment, event list with expected
  comms, and the gap
- every article with its `article_category`
- **every extra agreed at this gate, with its actual value**

An extra that was discussed but doesn't appear in the summary is a defect. This
is the last stop before anything reaches production, and a wrong promise date or
a mistyped recipient role is invisible in the API's success response.
```

- [ ] **Step 5: Update the Confirmation gates section**

In *Confirmation gates*, replace the Gate A bullet with:

```markdown
- **Gate A:** product(s) **and their `article_category`** approved before
  anything else.
```

- [ ] **Step 6: Verify the edits**

Run:

```bash
cd /Users/jamie.lee-smith/Documents/Claude/Projects/parcellab-claude-skills && grep -c "article_category" plugins/pl-tools/skills/order-lifecycle/SKILL.md && grep -n "^name: order-lifecycle$\|## Gate A — product and category approval" plugins/pl-tools/skills/order-lifecycle/SKILL.md && grep -c "^## Gate" plugins/pl-tools/skills/order-lifecycle/SKILL.md
```

Expected: `article_category` appears at least 5 times, `name: order-lifecycle` and the new Gate A heading both found, and exactly 3 top-level `## Gate` headings (A, B, C).

- [ ] **Step 7: Confirm frontmatter is untouched and scripts still pass**

Run:

```bash
cd /Users/jamie.lee-smith/Documents/Claude/Projects/parcellab-claude-skills && git diff -- plugins/pl-tools/skills/order-lifecycle/SKILL.md | grep -E "^[-+]description:|^[-+]name:" ; cd plugins/pl-tools/scripts && python3 -m unittest discover -s tests -v 2>&1 | tail -5
```

Expected: no `name:`/`description:` diff lines, and the test suite reports `OK`. The suite covers scripts this change doesn't touch, so a failure here is pre-existing — check `git stash` + rerun before chasing it.

- [ ] **Step 8: Commit**

```bash
cd /Users/jamie.lee-smith/Documents/Claude/Projects/parcellab-claude-skills && git add plugins/pl-tools/skills/order-lifecycle/SKILL.md && git commit -m "feat(order-lifecycle): approve article categories at Gate A, itemise extras at Gate C"
```

---

## Release step (after both tasks)

Push to `main` and tell the team to run `/pl-update`. `pl-tools` has no `version` field — the git SHA is the version, so the push itself is the release.

## Spec coverage

| Spec requirement | Task |
|---|---|
| Baseline proposed, explicit prompt, eight standards, free text | 1 (steps 1–2), 2 (steps 1–2) |
| Blocking with one-word exit | 1 step 2, 2 step 2 |
| Written to both `articles_order` and `tracking.articles` | 1 steps 2–3, 2 step 3 |
| Verbatim/case preservation | 1 step 2, 2 step 2 |
| Per-product override | 1 step 2, 2 step 2 |
| Untracked orders: order level only | 1 step 2 (referenced from 2 step 2) |
| Placement: after carrier / folded into Gate A | 1 step 1, 2 steps 1–2, 5 |
| `create-order` shorter extras menu, four rows, fast exit | 1 step 4 |
| `client_key` and split shipments excluded from `create-order` | 1 step 4 (menu has four rows, neither listed) |
| Final summary itemises articles + extras | 1 steps 5–6, 2 step 4 |
| Gate count stays three | 2 steps 5–6 |
