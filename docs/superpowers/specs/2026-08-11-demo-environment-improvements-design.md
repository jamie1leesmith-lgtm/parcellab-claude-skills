# demo-environment improvements — design (Approach A)

**Date:** 2026-08-11 · **Status:** draft for review · **Owner:** Jamie Lee-Smith
**Base:** the `demo-environment` skill as verified by Task 13's three live runs
(engage 1-order, retain-shopify 1-order, retain 3-order) on `feat/demo-environment`.

## 1. Context and goals

Task 13 proved the pipeline end to end. It also measured it: a retain-shopify
run costs ~45 minutes wall-clock, of which the intake interview + browser pass
run **serially before anything else can start** (~15 minutes on a fresh brand),
while the event drivers (180 s × N events) and the comms lag are physics we
keep. Jamie's improvement asks, in his words:

1. Speed the skill up — run everything concurrently that can be; collect
   products etc. up front and "just wait for approvals before firing the info
   over".
2. Make sure the correct Shopify CLI permissions are obtained at setup.
   *(Already delivered during Task 13 — §3.5 records it.)*
3. A live view of run progress so users know what is going on.
4. Historical per-run documents. *(Deferred to the roadmap by Jamie —
   explicitly out of scope here; §6.)*

Plus his standing feedback from the Run 2 gate: the approval gate is a wall of
text — proposed plans should be *shown*, not only described.

## 2. Scope

**In:** Phase 0 restructure (front-loaded pipeline), the per-run progress
artifact ("run page") that doubles as the visual gate, a driver pace option,
contract hardening for the two hard-4-capped scripts, recording the
already-shipped Shopify scope fix.

**Out:** historical run archive (roadmap), truly-live self-updating artifacts,
Notion integration, any change to the event driver's mechanics, any change to
the CDC call.

## 3. Design

### 3.1 Front-loaded Phase 0 (concurrency)

Today Phase 0 is strictly serial: interview → browser pass → gate. The
restructure runs the read-only work concurrently with the interview and makes
the ✋ gate a **release valve for sends**, not a starting gun for work.

**New sequence:**

1. Conductor takes the prospect URL and the path questions (returns? Shopify?)
   — the minimum needed to know what to collect.
2. **Dispatch the scrape agent** (general-purpose subagent, background): it
   owns the Browser pane and executes the one browser pass — brand tokens
   (branded-template Steps 3–6), product pool (≥8 candidates, superset shape),
   image validation — writing `scrape/brand-tokens.json` and
   `scrape/product-pool.json` into the run dir, then a
   `results/scrape.json` status file. Ground rules mirror the seed agent's:
   never ask the user; a gap is a failure report.
3. **Interview continues in chat concurrently**: destination country, order
   plan, CDC config, account confirmation, preflights. The user watches the
   pane flip through PDPs while answering — incidental but real feedback that
   work is happening.
4. When both interview and scrape are done, the conductor **pre-builds
   everything sendable**: the template HTML (from tokens; no push), each
   order's `create.json`/`track.json`/event files (fraud fragments included;
   no PUTs), and the proposed plan.
5. ✋ gate (now visual — §3.2). One yes releases the sends in the existing
   order: template push → publish → assignment (∥ seed agent on
   retain-shopify), publish gate, order writes, drivers, CDC.

**Browser pane ownership rule** (the one new coordination point): the scrape
agent owns the pane from dispatch until `results/scrape.json` exists. The
conductor must not navigate the pane in that window. The ★ template preview —
the next pane user — can only start after that file exists, which is naturally
true since the preview needs the scraped tokens.

**Failure fallback (Approach B of the run-lane pattern, unchanged):** if the
scrape agent fails or times out, the conductor runs the browser pass inline
after the interview, exactly as today. Nothing about the agent is
load-bearing; it is an accelerator.

**Repeat-brand shortcut** (proven live in Run 3): at intake, if a layout for
this brand already exists on the target account, the conductor verifies live
(`journey layout show`: `releaseStatus: published` + an `autoLayout` entry for
the store this path's orders will land on) and offers to **skip the template
lane** — no rebuild, no ★ checkpoint, `results/branded-template.json` written
from the verified state with a note. Saves ~4 minutes and one interruption on
every repeat run. Brand-token scraping is also skipped when the pool from a
previous run is reused (existing behaviour, now stated).

**What this does NOT change:** the ✋ gate and ★ checkpoint remain chat
approvals (AskUserQuestion); the publish gate, engines, failure isolation and
report beats are untouched.

### 3.2 The run page (progress artifact + visual gate)

One artifact per run; one stable URL; the conductor **rewrites one HTML file
in the run dir (`run-page.html`) and republishes it at each milestone** —
Jamie chose redeploy-on-phase-change over live self-updating. The page is a
view; chat remains the only approval mechanism.

**States the page moves through** (each is a redeploy):

| # | Milestone | Page shows |
|---|---|---|
| 1 | Run started | Brand, path, account (by name), what's being collected |
| 2 | Scrape done | Product grid **with images**, brand-token swatches |
| 3 | ✋ gate open | **The proposed plan, visually**: core-4 grid, order matrix table (customer / fraud / scenario / products / expected comms with confidence labels), CDC settings — plus a "⏳ approval waiting in chat" banner |
| 4 | Building | Lane cards: template (push → publish → assign), seed (retain-shopify), per-order step chips (create → track → events queued) |
| 5 | Drivers running | Per order: planned event list; sent-at timestamps filled in on each driver-completion notification (not per event — redeploys happen at milestones, so a mid-flight refresh shows "running since HH:MM") |
| 6 | Beat 1 | The environment-built summary (as chat, but scannable) |
| 7 | Beat 2 | Per-arc verification: checkpoints vs planned, comms fired vs promised |
| 8 | Failures (any time) | The failure-table row that applies, verbatim, in a red card |

**Mechanics:** the page reads nothing at runtime — every redeploy bakes in the
current state from the files the conductor already writes (`demo-manifest.json`,
`results/*.json`, `orders/*/run.log`). Self-contained HTML, no external
requests (CSP), light/dark aware, one emoji favicon kept stable per run
(`📦`). Title: `<brand> demo — <run id>`. ~8–10 redeploys per run.

**Degradation:** if the Artifact tool is unavailable in the session, the
conductor says so once and continues chat-only — the page is never
load-bearing, and no phase blocks on a publish succeeding.

**Sharing:** artifacts start private; the runner can share the URL with a
teammate mid-run if they choose. (The roadmap's history feature would build on
these pages; nothing here forecloses that.)

### 3.3 Driver pace option

Intake's order-plan round gains one option, recorded as `run.pace` in the
manifest:

- **standard** (default): `GAP_SECONDS=180` — comm-ordering safe, the
  documented reason the gap exists.
- **fast**: `GAP_SECONDS=60` — run time for a 3-event order drops 9→3 min.
  Offered with the explicit label that comms may arrive out of order, and
  Beat 2 flags it in its report so a weird ordering isn't misread as a bug.

The driver itself is unchanged (`GAP_SECONDS` is already an env knob).

### 3.4 Contract hardening (two scripts)

Both hard-4 caps forced improvisation during Task 13:

- **`check_images.mjs`** (demo-request): accepts exactly 4 products; the
  conductor's "validate every candidate" step (~11 images) couldn't use it.
  Change: accept **1–N** products. The exactly-4 rule belonged to the old CDC
  payload and no longer exists anywhere (§1's API update removed it); the
  standalone demo-request flow still validates its 4 by passing 4.
- **`shape_product_mix.py`** (shopify-seed): hard-requires exactly 4; the seed
  agent had to call its helpers directly for the 3 extras. Change: formalise
  what the agent did — accept an optional `--extras-file` (scrape-shaped
  products built at their own price with the same option/variant logic,
  appended to the shaped output). Core-4 economics logic untouched.

Both changes carry stdlib-`unittest` coverage, run via the existing suite.

### 3.5 Shopify CLI scopes — already delivered

Recorded for completeness: during Task 13, `/pl-setup`'s optional Shopify
section and the order engine's Part 1 were both updated to the live-verified
**seven-scope** string (`… write_draft_orders,
write_merchant_managed_fulfillment_orders`), so a fresh setup consents once.
No further work in this round.

## 4. Interfaces

- Manifest additions: `run.pace` (`"standard" | "fast"`), optional
  `run.page_url` (recorded after first publish). Validator: `pace` optional,
  enum-checked when present.
- New run-dir files: `scrape/brand-tokens.json`, `scrape/product-pool.json`,
  `results/scrape.json` (`{"status": "ok|failed", "error": null|str}`),
  `run-page.html`.
- Scrape agent brief: added to the conductor SKILL.md verbatim, mirroring the
  seed agent's brief structure (contract, ground rules, results file).

## 5. Error handling

- Scrape agent failure → inline fallback (§3.1); the run page shows the lane
  as failed-and-recovered.
- Artifact publish failure → non-fatal, chat notice once, continue.
- Pane contention → prevented by the ownership rule; if the conductor ever
  finds the pane busy it waits for `results/scrape.json` rather than fighting.
- Everything else inherits the existing failure table unchanged.

## 6. Roadmap (explicitly not in this round)

Historical run archive (per-run documents, browsable by the team — likely
Notion), truly-live artifact updates, `is_delayed` flag investigation for
stuck shipments (flag stayed `false` in Run 3 despite the delay comm firing —
cosmetic for demos, worth understanding), order-confirmation comm on the
Shopify path (journey-config question, with Jamie).

## 7. Testing

- Script changes: unit tests (stdlib unittest), existing suite green.
- Conductor/agent/page changes are markdown + one HTML template: verified by
  one live smoke run (any path) — the next real demo Jamie runs, watching the
  page move through its states and timing the intake-to-gate stretch.

## 8. Rollout

Implemented as a follow-on round on the same repo. Recommendation: **finish
`feat/demo-environment` first** (Task 13 is complete; the branch carries all
verified fixes) via `superpowers:finishing-a-development-branch`, then build
this round on a fresh branch (`feat/demo-environment-v2`) so the verified
baseline ships to the team independently of the improvements.
