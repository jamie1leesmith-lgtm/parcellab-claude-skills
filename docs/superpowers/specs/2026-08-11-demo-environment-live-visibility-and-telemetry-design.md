# demo-environment: live run visibility + run telemetry

**Date:** 2026-08-11
**Status:** design approved, not yet planned
**Repo:** `parcellab-claude-skills`
**Affects:** `pl-tools/skills/demo-environment`, `pl-tools/skills/order-lifecycle`,
`pl-tools/skills/branded-template`, `pl-tools/skills/pl-setup`

## Context

A full end-to-end run against `https://www.uniqlo.com/uk/en/` (run
`uniqlo-20260811-1913`, skill version `f0ee309`, engage path, 3 orders) completed
successfully — 12/12 events accepted, every checkpoint attached, every promised
comm fired. But the *experience* of watching it was poor, and the run exposed six
defects. This spec addresses both.

Observed problems, with root causes:

1. **The drivers were invisible.** `SKILL.md:384` says launch `run-lifecycle.sh`
   *"detached (`run_in_background`)"*. These are two different mechanisms. The
   conductor used `nohup` inside a `run_in_background` call, so the tracked task
   was the *launcher* — it exited in ~2s while the three real drivers ran for 15
   minutes with nothing in the user's task list. The user asked "I don't see any
   background tasks running?" and was right to.
2. **The run page froze.** Page states are keyed to *phase boundaries*, and
   Phase 2 is a single boundary spanning ~15 minutes — necessarily the longest,
   most watchable part of the run. `run-page.md` already predicts this failure
   and answers it with a *rule* ("never more than one milestone behind"). That
   rule has now been broken four times, three of them by conductors that had just
   read it. A rule cannot fix a state machine with no state in the middle.
3. **The status chips read badly.** `.chip` and `.done` differ only by border
   colour: no state vocabulary, no timestamps, no grouping — a wall of grey pills.
4. **Manifest product refs** cost a validate → fix → revalidate cycle. Commit
   `dfb14a3` claims "ids everywhere, enforced", but enforcement lives only in
   `validate_manifest.py`; the schema at `SKILL.md:293` says `products[]` and
   never states that `core4` holds ids. Every conductor learns this by failing.
5. **A silent branded-template bug.** The scraped `FONT_STACK` was
   `"Segoe UI", "Helvetica Neue", …`. Substituted into `style="…"` attributes,
   the first double quote *closes the attribute*, breaking the content card, CTA
   and footer. The first preview rendered a default-blue link on a black button.
   Both of Step 7's existing greps passed. This will recur for any brand whose
   font stack contains quoted family names — i.e. most of them.
6. **`add_tracking` cannot be verified from its own response.** The PUT echoes
   the request and carries no `trackings` field. Lacking a documented check, the
   conductor re-sent a payload as a diagnostic — an avoidable duplicate write.
7. **The Beat 2 comm window is too tight.** The skill says treat a missing comm
   as a problem after ≥5 minutes. Measured this run: single-parcel delivered
   comms fired in 3–4 minutes, but the split order's parcel 1 took **over 10**.
   At the 6-minute check it looked like a defect, and a plausible-but-wrong
   hypothesis (split orders hold the delivered comm until all parcels land)
   reached the user before the comm arrived and disproved it.

## Goals

- The user can see, at any moment, what the run is doing — without asking.
- The run page shows the *deliverable* (brand, products, the real email), not
  just a status log.
- Every run deposits structured, honest telemetry that aggregates across users,
  so skill defects are found by query rather than by anecdote.
- Fix the six defects above.

## Non-goals

- Genuinely-live-from-source page updates. Verified this session: available
  artifact capabilities are `downloads` and `mcp`, and `mcp` reaches **claude.ai
  connectors only** — the parcelLab MCP server is locally configured and
  therefore ineligible. A published page cannot read the run directory. (If
  parcelLab is ever added as a claude.ai connector, the page could `watchTool`
  on `public_order_info` and poll real tracking itself. That is a prerequisite
  change, not a design choice here.)
- The triage/review flow that reads telemetry back and proposes fixes — **v2**.
  This spec ships the triage *columns*, written by hand until then.
- Any change to what the demo environment actually builds.

---

## Part A — the run page

### A1. Architecture: state, then render

**The load-bearing change.** Today the conductor maintains `run-page.html` by
hand-editing HTML with string replacements. That is expensive and fragile, so it
only happens at big milestones — which is the real cause of problem 2.

Split it:

- **`run-state.json`** (new, in the run dir) — the single source of truth for run
  progress. Updated incrementally: each write reads it, adds or amends one fact,
  and writes it back. Nothing derived from it is ever hand-edited.
- **`render_run_page.py`** (new, in `scripts/`) — reads `run-state.json` +
  `demo-manifest.json` + `scrape/assets.json`, emits the complete
  `run-page.html`.

A republish becomes: append a fact → run the script → call `Artifact`. Cheap
enough to do a dozen times per run, and the page can never drift from state
because it is derived from it.

`run-state.json` shape:

```json
{
  "run_id": "uniqlo-20260811-1913",
  "updated_at": "2026-08-11T18:46:29Z",
  "finished": false,
  "lanes": {
    "scrape":   {"status": "ok",      "at": "..."},
    "template": {"status": "published","at": "...", "layout_id": 20701,
                 "store": "JLS Order", "displaced": "Stubble & Co"},
    "seed":     {"status": "skipped"},
    "orders":   {"status": "running"},
    "cdc":      {"status": "pending"}
  },
  "orders": [
    {"label": "Clean delivery", "order_number": "UNQ-...", "status": "ok",
     "shipments": [
       {"label": "A", "tracking_number": "...", "courier": "dpd-uk",
        "planned": ["InTransit", "OutForDelivery", "Delivered"],
        "confirmed": [{"status": "InTransit", "at": "...", "http": 204}]}
     ]}
  ],
  "schedule": {"started_at": "...", "gap_seconds": 180},
  "failures": []
}
```

### A2. Layout (approved: two-column)

- **Left rail, sticky** — owns run state and nothing else: lane chips, per-order
  event lists with timestamps, countdown to the next expected event, and a
  `confirmed HH:MM:SS` stamp.
- **Right column** — owns the deliverable: brand header (inline SVG logo, token
  swatches), the real email in an `<iframe srcdoc>`, the product grid with
  images, the CDC card.

Responsive: below 768px the rail stacks above the showcase. Wide content keeps
its `overflow-x: auto` wrapper; the body never scrolls sideways.

### A3. State vocabulary

Four states, colour-coded, used everywhere:

| State | Treatment | Meaning |
|---|---|---|
| confirmed | solid green | A republish has confirmed this happened |
| happening now | solid blue | Currently in progress |
| expected | **dashed outline, grey** | The page's clock believes this happened; no republish has confirmed it |
| failed / stuck | solid red | Failed, or a deliberate terminal state (e.g. a parcel that stays delayed) |

The dashed state is what makes the hybrid honest. A driver that dies shows up as
a pill that never fills in, beside a stale `confirmed` stamp — not as a fake
success.

### A4. Confirmed vs expected, and the clock

The page embeds `schedule` and each shipment's planned sequence as JSON, and ticks
its own clock to advance `expected` states between republishes. Rules:

- The clock may only ever move a step to **expected**, never to confirmed.
- When `run-state.json` reports `finished: true`, the rendered page hard-codes
  the clock off. Opening the page tomorrow shows the real end state, not an
  animation that ran off the end.
- The `confirmed at` stamp is always the last republish time, never "now".

### A5. Images and the two template variants

Product images and the hero must be **inlined as `data:` URIs** — the artifact
CSP blocks external requests, and a remote `<img src>` renders as a broken-image
icon (measured on the Pets at Home run). The UNIQLO-style inline SVG logo needs
no treatment.

The scrape agent already validates every image URL, so it gains one step: fetch
each accepted image, base64 it, and write `scrape/assets.json`. Guard: skip any
single asset over 1.5MB and record it as skipped, protecting the 16MB page budget.

**Two variants of the template HTML, never confused:**

| Variant | Images | Destination |
|---|---|---|
| canonical | remote URLs | pushed to parcelLab (correct for email) |
| preview | `data:` URIs | embedded in the artifact iframe |

Pushing the preview variant to parcelLab would be both wrong and enormous. The
renderer derives the preview variant; the canonical file on disk is never
modified.

### A6. Republish triggers

| Trigger | State |
|---|---|
| run dir created | 1 |
| scrape ok | 2 |
| template built (★ preview) | 2b |
| plan gate opens | 3 |
| gate approved | 4 |
| template pushed / published / assigned | 4 |
| each order created + tracked | 4 |
| drivers launched | 5 |
| **each watcher return (~per event)** | 5 |
| each driver completion | 5 |
| Beat 1 | 6 |
| Beat 2 | 7 |
| any failure | 8 |

---

## Part B — making frequent updates possible

### B1. Drivers become visible

Launch each order's driver with the harness's `run_in_background` and **no
`nohup`**. Three tasks the user can see; each notifies on completion. The
conflated SKILL.md line is rewritten to name one mechanism and explicitly warn
that `nohup` defeats it.

### B2. Per-event state from the driver

`run-lifecycle.sh` gains an optional `STATE_FILE` env var. When set, it appends
one JSON line per event (`{status, tracking_number, at, http}`) alongside its
existing `run.log`. **Opt-in, so standalone `order-lifecycle` runs are
unaffected** — the conductor sets it, nobody else does.

### B3. The coalescing watcher

One tracked background command per run (not per order) that blocks until any
order's state file advances, waits a short settle window (~20s) to collapse
bursts, then exits. Its completion notification gives the conductor a turn to
re-render and republish.

Expected cost: ~8–12 extra agent turns per run. Accepted deliberately — this is
the price of the page being alive, and it was the user's explicit choice
(hybrid) over a cheaper animation-only approach.

---

## Part C — run telemetry to Notion

Because Part A makes the conductor maintain structured state, the telemetry row
is *derived from `run-state.json`* rather than composed by hand.

### C1. The table

One Notion **database, table view**, one row per run, created once and shared
with the team.

**Run identity & context**

| Column | Type |
|---|---|
| Run ID | Title |
| Date | Date |
| Ran by | Person |
| Brand | Text |
| Prospect URL | URL |
| Path | Select — engage · retain · retain-shopify |
| Account | Number |
| Skill version | Text (plugin git sha) |
| Run page | URL |

**Outcome & metrics**

| Column | Type |
|---|---|
| Outcome | Select — Committed · Built · Verified · Stalled · Failed |
| Reached | Select — Gate · Template · Orders · CDC · Beat 1 · Beat 2 |
| Lanes failed | Multi-select (empty = all clean) |
| Orders planned | Number |
| Orders created | Number |
| Events pushed | Number |
| Events attached | Number |
| Comms expected | Number |
| Comms fired | Number |
| Duration to build | Number (minutes) |

**Diagnostics**

| Column | Type |
|---|---|
| Deviations | Multi-select (taxonomy below) |
| Error detail | Text (verbatim errors, no interpretation) |
| Issue key | Text (groups runs sharing a root cause) |

**Triage — written by review, never by a run**

| Column | Type |
|---|---|
| Triage status | Select — Untriaged · Reviewed, no action · Fix planned · Fix shipped · Can't reproduce |
| Reviewed at | Date |
| Reviewed by | Text |
| Action taken | Text |
| Fix commit | URL |
| Verified in run | Text |

Two columns earn their place specifically:

- **Skill version** — without it you cannot tell whether a fix worked. With it,
  "`validator_rejected` stopped appearing after `dfb14a3`" is a query.
- **Comms expected / fired** — the metric that would have surfaced this run's
  late delivered comm mechanically rather than by chance observation.

### C2. Write timing

A run writes its row **three times**:

1. **Plan gate approved** — create the row (`Outcome: Committed`).
2. **Beat 1** — update with build results.
3. **Beat 2** — update with verification results.

This ordering is deliberate. If the row were only written at the end, **every run
that dies would never appear**, and the table would systematically
over-represent success. Writing at gate-approval means an abandoned run leaves a
row with no Beat 2 — the most informative rows become visible instead of absent.

Nothing is written before the plan gate: no outward-facing action precedes user
approval, consistent with existing skill doctrine.

### C3. Write path and consent

- `notion-create-pages` / page update via **each user's own Notion connector**.
  No credentials are distributed, and rows are attributed to the real person.
- Database id in env as `PL_RUN_TELEMETRY_DB`, set during `/pl-setup`.
- **Unset means no telemetry, silently.** Enabling it at setup *is* the opt-in,
  per person. Teammates who have not opted in are unaffected.
- Never write tokens or credentials. Customer names/emails in runs are synthetic;
  brand URL and account id are internal-only.

### C4. Deviation taxonomy

`validator_rejected` · `api_error` · `retry_needed` · `gate_reasked` ·
`comm_missing` · `lane_fallback_inline` · `manual_intervention` ·
`instruction_unfollowable` · `workaround_invented`

**The first six are mechanical** — derived from exit codes, HTTP statuses and
state transitions — so they do not depend on the conductor's honesty.

**The last three are self-report, and are the weakest link in this design.** The
evidence is this run: the conductor used `nohup` against the skill's intent and
did not notice until the user asked. An agent reporting on its own deviations
will under-report exactly the cases most worth catching. Mitigation: prompt for
them with specific closed questions at Beat 2 ("did any instruction fail to work
as written? which line?") rather than an open "did anything go wrong?". Treat
self-reported deviations as a bonus signal, never as coverage.

---

## Part D — defect fixes

| # | Fix | File |
|---|---|---|
| 1 | Driver launch: one mechanism, warn that `nohup` defeats `run_in_background` | `demo-environment/SKILL.md` |
| 2 | Manifest schema states `core4` and order `products` hold product **ids**, not SKUs | `demo-environment/SKILL.md` |
| 3 | Step 7 normalises quotes in `FONT_STACK` (and any token substituted into a `style="…"` attribute); add a check that no substituted value contains `"` | `branded-template/SKILL.md` |
| 4 | Document `parcellab track tracking list --tracking-number <n>` as the attachment check; state plainly that the PUT response proves nothing | `order-lifecycle/SKILL.md` |
| 5 | Beat 2 comm window 5 → 15 minutes for delivered comms, citing the 2026-08-11 measurement (3–4 min single parcel, >10 min split) | `demo-environment/SKILL.md`, `order-lifecycle/SKILL.md` |
| 6 | Replace the "never more than one milestone behind" rule with the state-file mechanism | `demo-environment/references/run-page.md` |

Fix 6 deserves a note in the file itself: the rule was broken four times,
including by conductors that had just written it. That is evidence of a design
problem, not a discipline problem, and the replacement should say so.

---

## Error handling

- **Render failure** — `render_run_page.py` must never abort a run. On exception,
  log it, leave the previous `run-page.html` in place, and report once in chat.
- **Publish failure** — unchanged: non-fatal, said once, run continues.
- **Watcher dies** — the run continues; drivers are independent. The page shows
  `expected` states that stop being confirmed, which is the honest rendering.
- **Notion write fails** — never fails a run. Record the error in the run dir,
  report it once at the end. Telemetry is an observer, never a dependency.
- **Asset fetch fails** — that product renders as a text card without an image.

## Testing

- `render_run_page.py` gets unit tests over fixture `run-state.json` files:
  empty, mid-run, failed lane, finished. Assert the four states render, the
  clock is disabled when `finished`, and no `<img src="http` survives.
- A fixture-driven render of a completed run (this UNIQLO run's real state makes
  a good fixture) verified in the browser pane at desktop and mobile widths, in
  both colour schemes.
- `run-lifecycle.sh` `STATE_FILE` behaviour covered by the skill's existing
  `references/tests`, including the default-off case.
- Telemetry: a dry-run mode that prints the row payload without writing to
  Notion, so the schema can be validated without polluting the table.

## Risks and open questions

- **Turn cost.** ~8–12 extra turns per run is the accepted price. If it proves
  too expensive in practice, the coalescing window is the dial to turn — widen it
  before abandoning the approach.
- **Self-reported deviations are unreliable** (see C4). Known and accepted; the
  mechanical six carry the design.
- **Page size.** Ten inlined product images plus a hero should sit far inside
  16MB, but the 1.5MB per-asset guard exists because no one has measured a
  worst-case brand yet.
- **One table vs two.** A run is an event; a fix spans many runs, which argues
  for a separate Issues database with a relation. Shipping one table plus
  `Issue key` as a text grouper — migratable later without data loss — because
  volume is low and setup cost is real.
