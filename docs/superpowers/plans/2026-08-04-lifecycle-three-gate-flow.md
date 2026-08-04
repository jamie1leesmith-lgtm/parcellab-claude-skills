# order-lifecycle Three-Gate Flow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give `order-lifecycle` a three-gate flow where the user always chooses the event/comm scenario, and a custom scenario is derived from the account's real Journey config rather than the user's memory of it.

**Architecture:** This is **skill prose, not code**. All work is editing two Markdown files that Claude reads at runtime: `SKILL.md` (the instructions) and `references/status-codes.md` (the status enum and sequences). The existing Gate B ("plan approval") is renumbered to Gate C, and a new Gate B (journey + scenario) is inserted before payload building — because the journey chosen at B can make order fields mandatory at C. The optional *Journey pre-check* section is absorbed into the custom path, where it becomes the mechanism rather than an optional extra.

**Tech Stack:** Markdown. At runtime the custom path calls two Product-API MCP tools, `journey_list_journey_configurations` and `journey_get_journey_trigger_configuration`. No code, no dependencies, no build.

## Global Constraints

- **No unit tests, and TDD does not apply.** The deliverable is prose Claude follows, not a function. Each prose task ends with `grep` assertions proving the document is internally consistent; correctness is proven by the behavioural runs in Tasks 6 and 7.
- **No version bump.** `pl-tools` deliberately omits `version` from `plugin.json`; its version is the git commit SHA, so every push is a new version. Do not add a `version` field.
- **Do not change the happy path.** `InTransit → OutForDelivery → Delivered` is proven across multiple live runs. Task 6 is a regression check that it still behaves identically.
- **Do not change** `references/run-lifecycle.sh`, the timestamp rule, `GAP_SECONDS` timing, or the `add_tracking`/`tracking.articles` requirements.
- **Only four `event_status` values are proven** to attach and fire comms: `WarehouseDelay`, `InTransit`, `OutForDelivery`, `Delivered`. The other ~42 in the enum are untested and must be labelled as such wherever offered.
- **`eventTypes` is a different vocabulary from `event_status`.** Never present a derived mapping as certain. Every mapping carries **exact**, **inferred**, or **unverified**.
- **Never promise an email.** Report `contacted_with_messages`; a `204` proves ingestion only.
- **This skill reads Journey config and never writes it.** No `journey_write_*` calls.
- **Promise dates are `YYYY-MM-DD`**, not datetimes. `order_date` does accept full ISO.
- All work on `main`, remote `jamie1leesmith-lgtm/parcellab-claude-skills`. Personal account only — check `git remote -v` before pushing.
- Repo lives at `~/Documents/Claude/Projects/parcellab-claude-skills` (moved from `~/` on 2026-08-04).

---

## File Structure

**Modified — `plugins/pl-tools/skills/order-lifecycle/SKILL.md`** (365 lines currently)

| Region | Change |
|---|---|
| Workflow list, lines 17-32 | Renumber for three gates; insert Gate B; drop step 6a |
| Split shipments, line 228 | `Gate B` → `Gate C` in the per-shipment reporting note |
| `## Journey pre-check (optional, Tier 1)`, lines 232-264 | Replaced by the custom-path section |
| `## Confirmation gates`, lines 286-290 | Rewritten for three gates; fixes a stale `00-create.json` reference |
| New sections | *Gate B — scenario selection*, *Custom path*, *Gate C — order enrichment* |

**Modified — `plugins/pl-tools/skills/order-lifecycle/references/status-codes.md`** (134 lines)

| Region | Change |
|---|---|
| `## Sequences`, lines 121-134 | Add the named **unhappy** sequence and record the rejected alternatives with reasons |

**Created — none.** No new files; both targets already exist.

---

## Task 1: Renumber to three gates and fix two stale references

Structural groundwork every later task depends on. Deliberately contains no new
prose sections — only the skeleton — so a reviewer can check the renumbering in
isolation.

**Files:**
- Modify: `plugins/pl-tools/skills/order-lifecycle/SKILL.md` lines 24-32, 228, 286-290

**Interfaces:**
- Consumes: nothing.
- Produces: Workflow steps referencing *Gate B — journey and scenario selection* and *Gate C — order enrichment and send approval*, with section names `## Gate B — scenario selection`, `## Custom path — journey introspection`, and `## Gate C — order enrichment` for Tasks 2-4 to fill.

- [ ] **Step 1: Replace the Workflow list (lines 17-32)**

Replace the numbered list under `## Workflow` in full:

```markdown
1. **Resolve the account and confirm credentials.** See *Account resolution and
   confirmation* below. If either value is missing, follow *If credentials are
   missing* — don't guess them.

   ```bash
   test -n "${PARCELLAB_ACCOUNT_ID:-$PARCELLAB_USER_ID}" && test -n "$PARCELLAB_TOKEN" && echo ok
   ```
2. **Gather inputs:** brand site URL + a rough product idea (e.g. "coffee machine"), destination country, and any overrides (gap, extra items). **Ask for the destination country if the user hasn't named one — never assume it.** It silently sets the language, currency, timezone, courier and address, so a wrong guess yields an entirely wrong-looking journey. `create-order`'s *Defaults & dummy data* table lists the countries with ready-made defaults.
3. **Source the product** (see *Product sourcing*).
4. **Gate A — product approval.** Show product(s); wait for approval.
5. **Gate B — journey and scenario selection.** Ask one shipment or a split, then which scenario each shipment runs: happy, unhappy, or custom. Show the events and the comm each is expected to fire. See *Gate B — scenario selection*. **Never skip this and never assume a default.**
6. **Confirm the carrier(s).** State the country default courier; let the user confirm/override. For a split shipment, confirm a courier per shipment (they may differ).
7. **Build payloads** (see *Order + tracking setup* and *Event sequence*). Write the untracked order as `create.json` (no `NN-` prefix so the driver skips it), and each event as `NN-<status>.json` in the same run directory. For split shipments, interleave both shipments' events into one numbered sequence — see *Split shipments*.
8. **Gate C — order enrichment and send approval.** Offer the optional extras, apply anything Gate B marked required, then show the final plan and wait for approval. See *Gate C — order enrichment*.
9. **Launch the driver in the background** (see *Timing & background execution*).
10. **Report** progress from the log (see *Reporting*).
```

Note what changed: `scenario` and `split shipment` leave step 2 (they now belong to
Gate B), old step 6a disappears, and the old Gate B becomes Gate C at step 8.

- [ ] **Step 2: Fix the split-shipment gate reference (line 228)**

Change:

```markdown
6. **Gate B and Reporting** should summarise **per shipment** — courier,
```

to:

```markdown
6. **Gate C and Reporting** should summarise **per shipment** — courier,
```

- [ ] **Step 3: Rewrite the Confirmation gates section (lines 286-290)**

Replace:

```markdown
## Confirmation gates

- **Gate A:** product(s) approved before building payloads.
- **Gate B:** full plan approved before `00-create.json` is sent.
After Gate B the sequence runs unattended.
```

with:

```markdown
## Confirmation gates

Three gates. All three are blocking — a run with no user response at any gate
stops and waits. Never infer an answer from earlier context.

- **Gate A:** product(s) approved before anything else.
- **Gate B:** journey and scenario chosen — one shipment or split, and which
  scenario each runs. Asked **every run**; there is no default.
- **Gate C:** optional extras offered, then the final plan approved before
  `create.json` is sent.

After Gate C the sequence runs unattended.
```

This also corrects a stale reference: the file said `00-create.json`, but the
untracked order is written as `create.json` with **no** numeric prefix — that is
precisely how the driver knows to skip it.

- [ ] **Step 4: Verify the renumbering is internally consistent**

```bash
cd ~/Documents/Claude/Projects/parcellab-claude-skills/plugins/pl-tools/skills/order-lifecycle
echo "stale 00-create.json (expect 0):     $(grep -c '00-create.json' SKILL.md)"
echo "Gate A mentions (expect >=2):        $(grep -c 'Gate A' SKILL.md)"
echo "Gate B mentions (expect >=3):        $(grep -c 'Gate B' SKILL.md)"
echo "Gate C mentions (expect >=3):        $(grep -c 'Gate C' SKILL.md)"
echo "old step 6a removed (expect 0):      $(grep -c '^6a\.' SKILL.md)"
echo "workflow ends at step 10 (expect 1): $(grep -c '^10\. \*\*Report\*\*' SKILL.md)"
```

Every count must match. A non-zero `00-create.json` or a surviving `6a.` means the
replacement was partial.

- [ ] **Step 5: Commit**

```bash
cd ~/Documents/Claude/Projects/parcellab-claude-skills
git add plugins/pl-tools/skills/order-lifecycle/SKILL.md
git commit -m "refactor(order-lifecycle): renumber to a three-gate flow

Old Gate B (plan approval) becomes Gate C; a new Gate B for journey and scenario
selection sits before payload building, because the journey chosen there can make
order fields mandatory at C. Scenario and split-shipment choices move out of step 2
into Gate B, and the optional step 6a Journey pre-check is dropped — the custom
path absorbs it.

Also fixes a stale reference to 00-create.json; the untracked order is written as
create.json with no numeric prefix, which is how the driver knows to skip it."
```

---

## Task 2: Write the Gate B scenario-selection section

**Files:**
- Modify: `plugins/pl-tools/skills/order-lifecycle/SKILL.md` — insert a new section immediately before `## Split shipments (multiple trackings per order)`

**Interfaces:**
- Consumes: the Workflow step 5 reference to *Gate B — scenario selection* from Task 1.
- Produces: the section heading `## Gate B — scenario selection`, and the option names **happy**, **unhappy**, **custom** used by Task 3 and Task 5.

- [ ] **Step 1: Insert the section**

Insert immediately before the line `## Split shipments (multiple trackings per order)`:

```markdown
## Gate B — scenario selection

**Ask every run. There is no default and no inferring from context.** The point of
this skill is demonstrating post-purchase comms, so the user must see which comms
will fire before any are sent.

Two questions:

1. **One shipment or a split?** A split shipment runs two trackings with
   independent outcomes — see *Split shipments*.
2. **Which scenario per shipment?** Three options:

### 1. Happy path (proven)

```
InTransit → OutForDelivery → Delivered
```

All three statuses are proven to attach and fire. This is the default *offer*, not
a default *choice* — still ask.

### 2. Unhappy path (proven)

```
InTransit → WarehouseDelay      (then stop)
```

Both statuses are proven. The parcel is delayed and never arrives: stop emitting
events and the last one stands as the live state indefinitely, exactly as
*Split shipments* step 5 describes. `is_delayed` becomes `true`.

Do **not** "improve" this to a three-event shape. Two alternatives were considered
and rejected:

- `InTransit → OutForDelivery → WarehouseDelay` is incoherent — a *warehouse* delay
  cannot follow a parcel already out for delivery.
- `InTransit → OutForDelivery → FailedAttempt-NewAttemptNextDay` tells a better
  story, but `FailedAttempt-*` is unverified and may `204` without ever attaching.
  It is reachable through the custom path, where its risk is labelled.

### 3. Custom path

Derived from the account's own Journey configuration — see
*Custom path — journey introspection*.

### What to show the user at this gate

List the events in order, and the comm each is expected to fire. These mappings are
empirically confirmed on account 1626718 with a standard delivery-notification
setup:

| Event | Expected comm | Journey trigger |
|---|---|---|
| *(order creation)* | `order_confirmation_*` | Order Confirmed |
| `InTransit` | `shipping_confirmation_*` | Package dispatched from warehouse |
| `OutForDelivery` | `out_for_delivery_*` | Package out for delivery |
| `Delivered` | `package_delivered_*` | Delivered (parcel delivered to recipient) |
| `WarehouseDelay` | delay comm | Package delayed in transit |

Say plainly that comms depend on the account's Journey config, and that this table
reflects a standard setup rather than a guarantee.

For a split shipment, show this per shipment, labelled A and B.

### Split shipments are chosen here, not at Gate C

A split is a decision about events and comms, so it belongs to Gate B. The
canonical demo is one shipment on the happy path and one stuck at a delay, side by
side — expressible directly as *"A: happy, B: unhappy"*.

**Gate C never offers split shipments.** If it did, a split chosen there would
strand the single scenario chosen here with nothing to say about the second
shipment.
```

- [ ] **Step 2: Verify the section landed and says the right things**

```bash
cd ~/Documents/Claude/Projects/parcellab-claude-skills/plugins/pl-tools/skills/order-lifecycle
echo "section present (expect 1):        $(grep -c '^## Gate B — scenario selection' SKILL.md)"
echo "unhappy sequence (expect 1):       $(grep -c 'InTransit → WarehouseDelay' SKILL.md)"
echo "rejected alt documented (expect 1):$(grep -c 'cannot follow a parcel already out for delivery' SKILL.md)"
echo "comms table present (expect 1):    $(grep -c 'package_delivered_\*' SKILL.md)"
echo "no-default rule (expect 1):        $(grep -c 'no default and no inferring' SKILL.md)"
```

- [ ] **Step 3: Confirm the happy path text is byte-identical to before**

The happy sequence must not have drifted while editing around it:

```bash
cd ~/Documents/Claude/Projects/parcellab-claude-skills
git diff plugins/pl-tools/skills/order-lifecycle/SKILL.md | grep '^-' | grep -i 'InTransit → OutForDelivery → Delivered' || echo "happy path untouched by deletions ✓"
```

Expected: the "untouched" message. Any removed line containing the happy sequence
means the proven path was altered — revert and redo.

- [ ] **Step 4: Commit**

```bash
cd ~/Documents/Claude/Projects/parcellab-claude-skills
git add plugins/pl-tools/skills/order-lifecycle/SKILL.md
git commit -m "feat(order-lifecycle): add the Gate B scenario-selection section

Three options, asked every run: happy (unchanged, proven), unhappy
(InTransit -> WarehouseDelay, both proven, ends stuck and never delivers), or
custom. Shows the events and the comm each is expected to fire, so the user sees
the comms before they send rather than after.

Records why the unhappy path is two events, so nobody re-proposes a WarehouseDelay
after OutForDelivery — that ordering is incoherent — or reaches for the unverified
FailedAttempt-* to pad it out.

Split-shipment selection moves here from Gate C: a split needs a scenario per
shipment, which is this gate's job."
```

---

## Task 3: Replace the Journey pre-check with the custom path

**Files:**
- Modify: `plugins/pl-tools/skills/order-lifecycle/SKILL.md` — replace `## Journey pre-check (optional, Tier 1)` and its body (currently lines 232-264) entirely

**Interfaces:**
- Consumes: the option name **custom** from Task 2.
- Produces: the section heading `## Custom path — journey introspection`, and the confidence labels **exact** / **inferred** / **unverified** referenced by Task 5.

- [ ] **Step 1: Delete the old section**

Remove the whole `## Journey pre-check (optional, Tier 1)` section — from its
heading through to the line immediately before `## Timing & background execution`.
It is superseded: what was an optional after-thought becomes the mechanism.

- [ ] **Step 2: Insert the replacement in its place**

```markdown
## Custom path — journey introspection

Builds a sequence from the account's **actual** Journey config, rather than
assuming the user remembers which journeys are live.

**Requires the Product-API MCP journey tools.** If they aren't available in this
session, say so in one line and fall back to asking the user to describe the
sequence in prose, mapping it against *references/status-codes.md*. **Never block a
run on tool availability.**

### 1. List every journey

`journey_list_journey_configurations(account=[<id>])`

**Do not filter by `release_status`** — show drafts too, so the user sees
everything. For each journey give name, `releaseStatus`, and a plain-English
eligibility line derived from `filterExpression`.

### 2. The user picks one by name

### 3. Check the order is actually eligible — do not skip this

Picking a journey by name is **not** sufficient. The order must match that
journey's `filterExpression` or the journey never processes it: no error, just
silence. Three ways a chosen journey fires nothing:

| Condition | Detect | Tell the user |
|---|---|---|
| Draft | `releaseStatus != "published"` | It won't fire until published. Ask whether to continue anyway or pick another. |
| Returns-only | filter requires `isReturnsPortal: true` | A forward shipment is never a returns-portal record. Name the journey that *would* catch this order. |
| Order ineligible | filter needs fields the planned order lacks, e.g. `delivery_info.client: {$in: [...]}` | Name the field and offer to set it at Gate C. |

Where the mismatch is fixable, offer the fix. Where it isn't, say which journey
would catch this order instead. **Never proceed silently past an ineligible pick** —
the whole run would produce checkpoints and no comms, looking like a bug.

### 4. Fetch only that journey's triggers

`journey_get_journey_trigger_configuration(id)` for each trigger on the chosen
journey — roughly 5-12 calls. **Do not introspect every journey**: on a populated
account that is 40+ calls for information the user didn't ask for.

### 5. Present the mapping with a confidence label per row

`eventTypes` in Journey config is a **different vocabulary** from the `event_status`
values the events endpoint accepts. Every proposed mapping is therefore one of:

| Confidence | Meaning | Example |
|---|---|---|
| **exact** | `eventTypes` contains the `event_status` verbatim | `OutForDelivery` → `OutForDelivery`; `WarehouseDelay` → `WarehouseDelay` |
| **inferred** | Clear correspondence, different spelling | `ParcelLocker` → `Delivered-ParcelLocker`; `FailedAttemptFirst` → `FailedAttempt-NewAttemptNextDay` |
| **unverified** | Config genuinely cannot tell us | `eventTypes: ["*"]` on `onDispatch` — a wildcard matches anything on that slot. `InTransit` is known to reach it only because a live run proved it. |

Show **two independent axes**, because they answer different questions:

- **Trigger confidence** — will this event match this trigger? (the table above)
- **Status confidence** — will this `event_status` attach at all? Only
  `WarehouseDelay`, `InTransit`, `OutForDelivery` and `Delivered` are proven; the
  other ~42 enum values are untested.

A mapping can be *exact* on a status that has never been tested, and *unverified*
on a status proven to work. Don't collapse them into one number.

### 6. The user selects which triggers to demonstrate, in order

That selection **is** the sequence. Build `NN-<status>.json` files from it exactly
as *Event sequence* describes — same identifier rule (`courier` +
`tracking_number`), same no-`event_timestamp` rule.

### 7. After the run, report what actually fired

Verify against `contacted_with_messages` and say which *inferred* and *unverified*
mappings actually produced a comm. Offer to record newly confirmed ones in
`references/status-codes.md`, so each custom run shrinks the untested surface
instead of the finding evaporating.

### Known limitation: recipient roles are a second gate

Filter eligibility is necessary but not sufficient. On account 1626718 the
*Gifter Journey* has an empty `filterExpression` — so it matches every order — and
an *Out for Delivery* trigger, yet a live run produced only one
`out_for_delivery_*` comm. It almost certainly requires `additional_recipients`
carrying a role listed in the Journey's `advancedRecipients`, the mechanism
`create-order` documents under *Additional recipients*.

So a journey can be published, eligible, and still mail nobody. State this as a
limitation. Do not try to resolve it from config, and **never promise mail on the
strength of an eligibility check.**
```

- [ ] **Step 3: Verify the replacement**

```bash
cd ~/Documents/Claude/Projects/parcellab-claude-skills/plugins/pl-tools/skills/order-lifecycle
echo "old section gone (expect 0):        $(grep -c 'Journey pre-check (optional, Tier 1)' SKILL.md)"
echo "new section present (expect 1):     $(grep -c '^## Custom path — journey introspection' SKILL.md)"
echo "eligibility check (expect 1):       $(grep -c 'Never proceed silently past an ineligible pick' SKILL.md)"
echo "all three labels (expect 1 each):   $(grep -c '\*\*exact\*\*' SKILL.md) $(grep -c '\*\*inferred\*\*' SKILL.md) $(grep -c '\*\*unverified\*\*' SKILL.md)"
echo "two axes stated (expect 1):         $(grep -c 'two independent axes' SKILL.md)"
echo "tool fallback (expect 1):           $(grep -c 'Never block a' SKILL.md)"
echo "gifter limitation (expect 1):       $(grep -c 'still mail nobody' SKILL.md)"
echo "no write tools (expect 0):          $(grep -c 'journey_write' SKILL.md)"
```

`journey_write` must be zero — this skill reads config and never writes it.

- [ ] **Step 4: Commit**

```bash
cd ~/Documents/Claude/Projects/parcellab-claude-skills
git add plugins/pl-tools/skills/order-lifecycle/SKILL.md
git commit -m "feat(order-lifecycle): derive the custom path from Journey config

Replaces the optional Journey pre-check with a custom path that reads the
account's real config: list every journey including drafts, user picks one by
name, check the order is actually eligible for it, then introspect only that
journey's triggers.

The eligibility check is the load-bearing part. A journey can be chosen and still
fire nothing — draft status, a returns-only filter, or a filter requiring fields
the order lacks — and the failure is silent: checkpoints attach, no comms send, and
it looks like a bug in the skill.

Mappings carry exact/inferred/unverified because eventTypes is a different
vocabulary from event_status and wildcards tell you nothing. Trigger confidence and
status confidence are shown as separate axes: a mapping can be exact on an untested
status, or unverified on a proven one.

Records the Gifter Journey limitation: eligible, published, and still mails nobody
without a matching additional_recipients role."
```

---

## Task 4: Write the Gate C enrichment section

**Files:**
- Modify: `plugins/pl-tools/skills/order-lifecycle/SKILL.md` — insert a new section immediately before `## Confirmation gates`

**Interfaces:**
- Consumes: the Workflow step 8 reference to *Gate C — order enrichment* from Task 1, and the "offer to set it at Gate C" promise from Task 3's eligibility table.
- Produces: the section heading `## Gate C — order enrichment`.

- [ ] **Step 1: Insert the section**

```markdown
## Gate C — order enrichment

An offer with a fast exit, not a form. **The default is send-as-is** — skipping
takes one word:

> Anything else to add to this order, or send as-is?

Then list the menu below. Do **not** ask an open "any other fields?" — that is
unanswerable unless the user has the Order API spec memorised.

Anything Gate B flagged as **required** (for example a `client_key` needed to make
the chosen journey eligible) appears here pre-filled and is **not** optional.

| Extra | Fields | State this |
|---|---|---|
| Dynamic recipients | `additional_recipients: [{role, email}]` — write to **both** order and tracking level | Role must match the Journey's `advancedRecipients` **exactly**, case-sensitive. **Preserve the user's spelling even if it looks like a typo** — the match is literal, and "fixing" it breaks a Journey using the same misspelling. Setting the field mails nobody unless the Journey lists that role. |
| Promise dates | `announced_delivery_date`, `announced_delivery_date_min`, `announced_delivery_date_max` | **`YYYY-MM-DD` only.** A full ISO datetime is rejected. (`order_date` *does* take full ISO — the two fields differ.) |
| Client key | `client_key` | Pre-filled when Gate B's journey requires one |
| Order financials | `order_tax_amount`, `order_net_amount`, `order_discount_amount` | For invoice-style comms |
| Extra articles | more `articles_order` entries, each with a unique `line_item_id` | Mirror them into every `add_tracking`'s `tracking.articles` or the shipment comms render an empty article table |
| Tags / custom fields | `tags`, `additional_attributes` | What filter-driven Journey triggers key on |
| Delivery detail | `delivery_method`, `courier_service_level`, `requires_signature` | Mostly cosmetic in comms |

**Split shipments are not offered here** — they are chosen at Gate B, because a
split needs a scenario per shipment.

After the menu, show the final plan — order summary, carrier(s), scenario per
shipment, event list with expected comms, and the gap — then wait for approval.
This is the last stop before anything reaches production.
```

- [ ] **Step 2: Verify**

```bash
cd ~/Documents/Claude/Projects/parcellab-claude-skills/plugins/pl-tools/skills/order-lifecycle
echo "section present (expect 1):       $(grep -c '^## Gate C — order enrichment' SKILL.md)"
echo "send-as-is default (expect 1):    $(grep -c 'default is send-as-is' SKILL.md)"
echo "promise date rule (expect 1):     $(grep -c 'YYYY-MM-DD\`\*\* only' SKILL.md)"
echo "role literal-match (expect 1):    $(grep -c 'Preserve the user' SKILL.md)"
echo "split excluded here (expect 1):   $(grep -c 'Split shipments are not offered here' SKILL.md)"
```

- [ ] **Step 3: Commit**

```bash
cd ~/Documents/Claude/Projects/parcellab-claude-skills
git add plugins/pl-tools/skills/order-lifecycle/SKILL.md
git commit -m "feat(order-lifecycle): add the Gate C order-enrichment section

Offers dynamic recipients, promise dates, client key, financials, extra articles,
tags and delivery detail as a concrete menu, defaulting to send-as-is so skipping
costs one word. An open 'any other fields?' would be unanswerable without the API
spec to hand.

Bakes in two constraints that have each cost time before: announced_delivery_date
is YYYY-MM-DD and rejects a datetime, and a dynamic-recipient role matches
literally, so the user's spelling is preserved even when it looks wrong."
```

---

## Task 5: Add the unhappy sequence to the status reference

**Files:**
- Modify: `plugins/pl-tools/skills/order-lifecycle/references/status-codes.md` — the `## Sequences` list, currently lines 121-134

**Interfaces:**
- Consumes: the scenario names **happy** / **unhappy** / **custom** from Task 2.
- Produces: a named `unhappy` sequence the Gate B section refers to.

- [ ] **Step 1: Replace the Sequences list**

Replace the entire `## Sequences` list with:

```markdown
## Sequences

The three the skill offers at **Gate B**:

- **happy** (proven, no delay): `InTransit`, `OutForDelivery`, `Delivered`
- **unhappy** (proven, ends stuck): `InTransit`, `WarehouseDelay` — then stop.
  The parcel is delayed and never arrives; the last event stands as the live state
  indefinitely and `is_delayed` becomes `true`.
- **custom**: derived from the account's Journey config — see *Custom path —
  journey introspection* in `SKILL.md`.

**Why `unhappy` is two events, not three.** Two alternatives were considered and
rejected, recorded so they are not re-proposed:

- `InTransit`, `OutForDelivery`, `WarehouseDelay` — incoherent. A *warehouse* delay
  cannot follow a parcel already out for delivery.
- `InTransit`, `OutForDelivery`, `FailedAttempt-NewAttemptNextDay` — a better story
  and it matches the happy path's three-event shape, but `FailedAttempt-*` is
  unverified and may `204` without attaching. Reachable via the custom path, where
  the risk is labelled.

Other sequences, available through the custom path — **all untested**, so verify
attachment with a lookup before trusting any of them:

- **happy-with-delay**: `WarehouseDelay`, `InTransit`, `OutForDelivery`, `Delivered`
  — all four statuses are individually proven, but this ends *delivered*, so it
  demonstrates recovery rather than failure.
- **failed-attempt**: `InTransit`, `OutForDelivery`, `FailedAttempt-NewAttemptNextDay`, `OutForDelivery`, `Delivered`
- **exception**: `InTransit`, `Exception-Notified`, `InTransit`, `OutForDelivery`, `Delivered`
- **return**: `InTransit`, `OutForDelivery`, `FailedAttempt-NewAttemptNextDay`, `ReturnToSender-NotCollected`, `ReturnDelivered`
- **locker collection**: `InTransit`, `OutForDelivery`, `Delivered-ParcelLocker` —
  maps to a *Collected from Locker or Shop* trigger listening on
  `eventTypes: ["ParcelLocker"]`, so the correspondence is *inferred*, not proven.

- **partial-delay** (for the "stuck" shipment in a split-shipment demo): send only
  the first 1-2 stages, then stop emitting events for that tracking.
  - Single-stage (proven): `WarehouseDelay` only. This is what **unhappy** uses.
  - Two-stage (partly untested): `WarehouseDelay` (proven), then
    `Exception-Notified` (untested — verify via lookup after running).
```

- [ ] **Step 2: Verify**

```bash
cd ~/Documents/Claude/Projects/parcellab-claude-skills/plugins/pl-tools/skills/order-lifecycle
echo "unhappy named (expect 1):        $(grep -c '\*\*unhappy\*\*' references/status-codes.md)"
echo "rejected alts recorded (expect 1):$(grep -c 'not re-proposed' references/status-codes.md)"
echo "locker sequence added (expect 1): $(grep -c 'locker collection' references/status-codes.md)"
echo "happy unchanged (expect 1):      $(grep -c '\*\*happy\*\* (proven, no delay)' references/status-codes.md)"
```

- [ ] **Step 3: Commit**

```bash
cd ~/Documents/Claude/Projects/parcellab-claude-skills
git add plugins/pl-tools/skills/order-lifecycle/references/status-codes.md
git commit -m "docs(order-lifecycle): name the unhappy sequence in the status reference

Adds unhappy (InTransit, WarehouseDelay, stop) alongside happy and custom, records
why it is two events rather than three, and adds a locker-collection sequence for
the Delivered-ParcelLocker mapping the custom path can now surface.

Re-labels the remaining sequences as custom-path-only and untested, so nobody
reads happy-with-delay as an offered option."
```

---

## Task 6: Regression-verify the happy path

The most important task in the plan. The happy path is the one proven flow, and
everything above edited the file around it.

**Files:** none — behavioural verification.

**Interfaces:**
- Consumes: Tasks 1-5.
- Produces: confidence that the proven path is unchanged.

- [ ] **Step 1: Ship the changes and pick them up**

```bash
cd ~/Documents/Claude/Projects/parcellab-claude-skills
git remote -v   # must be jamie1leesmith-lgtm
git push origin main
claude plugin marketplace update parcellab-skills
claude plugin update pl-tools@parcellab-skills
```

Expected: *"updated from &lt;old SHA&gt; to &lt;new SHA&gt;"*. Then **fully quit and
reopen the app (⌘Q)** — plugins load at startup.

- [ ] **Step 2: Run the happy path**

In a new conversation: `/pl-tools:order-lifecycle`, then a brand URL, a product
idea, and a destination country.

Confirm the flow now stops at **three** gates, and that Gate B **asks** rather than
assuming: it must offer one-shipment-or-split and the three scenarios, and show the
events with their expected comms.

- [ ] **Step 3: Verify the run matches the 2026-08-04 baseline**

The reference run was `NIK-1785849524`, tracking `RM144237600GB`, on account
1626718. Compare against it:

| Expected | Baseline value |
|---|---|
| Events pushed | 3, each `204` |
| Checkpoints | 4: `OrderProcessed`, `InboundScan`, `OutForDelivery`, `Delivered` |
| Comms | 4: `order_confirmation_*`, `shipping_confirmation_*`, `out_for_delivery_*`, `package_delivered_*` |
| `is_delayed` | `false` |
| `tracking.articles` | present, with image and store URL |

**Wait at least 5 minutes after the final event before judging the comms** — the
delivered comm lags the others. Checking early shows 4 checkpoints and 3 comms,
which looks like a broken trigger and isn't.

Any difference from this table means an edit above changed the proven path. Stop and
fix rather than accepting it.

- [ ] **Step 4: Commit nothing, report the comparison**

This task produces no code change. Report the checkpoint and comm lists against the
baseline table explicitly — do not summarise as "worked".

---

## Task 7: Verify the unhappy and custom paths

**Files:** none — behavioural verification.

**Interfaces:**
- Consumes: Task 6's confirmation that the happy path is intact.
- Produces: verified behaviour for the two new scenarios, and any findings worth recording in `references/status-codes.md`.

- [ ] **Step 1: Run the unhappy path**

`/pl-tools:order-lifecycle`, choose **unhappy** at Gate B.

Expected: 2 events, both `204`; checkpoints `OrderProcessed`, `InboundScan`, plus a
delay checkpoint; `is_delayed: true`; **no** `Delivered` and **no**
`package_delivered_*`; the tracking stays delayed indefinitely.

Record which comm slug the delay produces — the Gate B table currently says only
"delay comm" because the slug has never been observed. Note it for a follow-up edit.

- [ ] **Step 2: Run the custom path with introspection available**

Choose **custom** at Gate B. Verify in order:

1. The journey list appears with **6** journeys on account 1626718, including the
   **draft** `{{CUSTOMERNAME}} Returns Portal Journey`.
2. Picking `Shopify Comms` for a normal order is **caught** — it requires
   `delivery_info.client: parcellab-demo-jls.myshopify.com`, which the order lacks.
   The skill must say so and offer to set `client_key` at Gate C.
3. Picking `Standard Return Notifications` is **caught** as returns-only.
4. Picking `Standard Delivery Notifications` proceeds, and its ~12 triggers are
   fetched — **only** that journey's, not all 40+.
5. Mappings show confidence labels, with `OutForDelivery` as *exact* and the
   dispatch trigger's `["*"]` as *unverified*.

- [ ] **Step 3: Test the locker mapping end to end**

Select the *Collected from Locker or Shop* trigger, which listens on
`eventTypes: ["ParcelLocker"]`. The skill should propose `Delivered-ParcelLocker`
as **inferred**.

Run it, then after 5+ minutes check whether a comm fired. Either outcome is a
result worth having:

- **Fired** → promote `Delivered-ParcelLocker` from untested to proven in
  `references/status-codes.md`.
- **Didn't** → record it as attempted-and-failed, with whatever the lookup showed,
  so nobody retries it blind.

- [ ] **Step 4: Verify the no-tools fallback**

Confirm that when the journey MCP tools are unavailable, the custom path says so in
one line and falls back to a prose description instead of stalling. If that state
can't be produced on demand, re-read the section and confirm the instruction is
unambiguous — the failure mode is a run that blocks forever waiting for a tool that
will never appear.

- [ ] **Step 5: Verify Gate C**

Run once more and at Gate C:

1. Confirm skipping takes one word and the payload is unchanged by it.
2. Add a promise date as `YYYY-MM-DD` → accepted.
3. Offer a datetime (`2026-08-10T12:00:00Z`) → must be rejected **before** sending,
   with the `YYYY-MM-DD` rule explained, not passed to the API to fail.
4. Add a dynamic recipient and confirm the reply says the field is set **and** that
   mail depends on the Journey listing that role — not that an email will arrive.

- [ ] **Step 6: Record findings and commit**

Apply any confirmed mappings and the observed delay-comm slug to
`references/status-codes.md` and the Gate B table.

```bash
cd ~/Documents/Claude/Projects/parcellab-claude-skills
git add plugins/pl-tools/skills/order-lifecycle
git commit -m "docs(order-lifecycle): record findings from scenario verification"
git push origin main
```

---

## Self-Review

**Spec coverage:**

| Spec requirement | Task |
|---|---|
| Three gates, A/B/C | 1 |
| Gate B always asked, no default | 1 (step 1), 2 |
| Happy path unchanged | 2 (step 3), 6 |
| Unhappy = `InTransit → WarehouseDelay` | 2, 5 |
| Rejected alternatives recorded | 2, 5 |
| Custom path: list all journeys incl. drafts | 3 |
| User picks by name | 3 |
| Eligibility check (draft / returns-only / ineligible) | 3, 7 (step 2) |
| Scope introspection to one journey | 3, 7 (step 2.4) |
| exact / inferred / unverified labels | 3, 7 (step 2.5) |
| Two confidence axes | 3 |
| Post-run verification, record findings | 3 (step 7), 7 (step 3) |
| Recipient-role limitation | 3 |
| Tool-unavailable fallback | 3, 7 (step 4) |
| Gate C menu, send-as-is default | 4, 7 (step 5) |
| Promise dates `YYYY-MM-DD` | 4, 7 (step 5.3) |
| Dynamic recipients caveat | 4, 7 (step 5.4) |
| Split shipments at Gate B not C | 2, 4 |
| Never promise mail | 3, 4 |
| Never write Journey config | 3 (step 3 assertion) |
| No version bump | Global Constraints |
| Gates cannot be bypassed | 1 (step 3) |
| 5-minute comm wait | 6 (step 3), 7 (steps 1, 3) |

No gaps.

**Placeholder scan:** none. Every prose step contains the literal text to insert;
every verification step contains a runnable command with an expected count.

**Consistency check:** section headings are byte-identical wherever
cross-referenced — `## Gate B — scenario selection`, `## Custom path — journey
introspection`, `## Gate C — order enrichment` (all using an em dash) match between
Task 1's Workflow references, the inserting task, and each verification `grep`.
Scenario names are lowercase **happy** / **unhappy** / **custom** throughout Tasks
2, 5 and 7. `create.json` (no prefix) is used consistently, replacing the stale
`00-create.json`.

**Two things this plan fixes that the spec didn't mention**, both found while
mapping line numbers:

1. **The existing Gate B is "plan approval"**, so the spec's three-gate scheme is a
   renumbering, not just an insertion. It touches four places: the Workflow list,
   the split-shipment note at line 228, the Confirmation gates section, and the
   dropped step 6a.
2. **`## Confirmation gates` referenced `00-create.json`**, which does not exist —
   the untracked order is `create.json` with no numeric prefix, precisely so the
   driver skips it. A reader following the old text would look for a file that was
   never written.

**One deliberate scope call:** Task 7 step 1 records the delay comm's slug rather
than guessing it. The Gate B table says "delay comm" because no live run has
observed the actual `*_slug`, and inventing a plausible one would be worse than
admitting the gap.
