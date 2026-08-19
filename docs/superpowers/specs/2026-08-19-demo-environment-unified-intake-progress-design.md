# demo-environment — unified intake + progress UI (local server, no Artifact)

Date: 2026-08-19
Status: approved for planning
Supersedes: `2026-08-19-demo-environment-intake-questionnaire-design.md`

## Why this replaces the prior spec

The prior spec's Artifact-based questionnaire shipped and broke on its first
real run: the Browser pane isn't authenticated to claude.ai, so the
"publish, wait, extract" flow that spec describes never completes — every
real build falls back to a plain chat interview, which is the exact
sequential-interview problem the prior spec set out to eliminate. The same
live run (2026-08-19, pccomponentes.com) surfaced two further problems the
prior spec didn't anticipate:

- A separate progress-tracking Artifact alongside the intake Artifact makes
  for a clunky two-artifact experience inside the Claude app.
- The questionnaire's field set was incomplete — customisation extras in
  particular had no real interactive UI, just a placeholder.

This spec keeps the prior spec's branding goal and manifest-field mapping
intact, and replaces its transport mechanism (Artifact publish/poll/extract)
and its scope (one page, not two) entirely. It was developed by mocking up
both phases interactively (7 rounds, in `.superpowers/brainstorm/63507-1787164204/content/`)
before being written up here.

## Problem

Today's `pl-tools:demo-environment` intake, per the prior spec, is meant to
be a single up-front questionnaire but is not one in practice — it degrades
to chat every time because its transport is broken. Progress tracking is a
second, separately-published Artifact. Neither can be fixed by patching the
Artifact approach: `claude.ai` capability testing during this session
confirmed the live-doc capability doesn't notify a Claude Code session of
edits, the clipboard API is CSP-blocked, and the Browser pane cannot
authenticate to claude.ai at all — so no Artifact-based handoff mechanism
can work here, regardless of which capability it tries to use.

## Goals

- One page, two phases (**Intake** → **Building/Live**), switched in place —
  no separate artifacts, no second URL.
- Every question answerable up front with real interactive controls, not
  placeholders: customisation extras (the account's actual Order API extras,
  each revealing its real fields), per-order fraud level, split-shipment
  toggle (forking into independent Parcel A/B controls), per-shipment
  scenario (the real vocabulary: happy · stuck-delay · recovered · locker ·
  manual_return · return_tracking · custom), destination region, and a
  courier default with per-order/per-parcel override.
- Each progress lane (Scrape, Template, Seed, Orders, CDC) is clickable and
  drills into what that stage actually produced — scraped products and
  brand palette, the rendered template preview, the Shopify seed table with
  even/uneven exchange pricing, an order summary, and CDC status.
- Look like a real parcelLab internal tool — brand colors, font, logo —
  reusing the existing `plugins/pl-tools/scripts/pl_brand.py` tokens
  verbatim, not generic Tailwind styling. This carries the prior spec's
  branding goal forward unchanged.
- No new toolchain dependency. Vanilla HTML/CSS/JS with Tailwind via CDN
  (validated across all 7 mockup rounds) — no React, no build step. The
  page is a plain local browser tab, not a claude.ai Artifact, so none of
  the Artifact CSP restrictions that would justify a build step apply here.

## Non-goals

- No change to Phase 1–4 logic itself, beyond what falls out of the new
  intake/progress mechanism replacing Artifact publish calls.
- No change to the manifest schema — same fields the questionnaire already
  writes today.
- **Article category is not made per-product in this build.** A real gap
  was found while brainstorming the order matrix (orchestrated runs collapse
  every product to one `brand.category` via majority vote, which breaks
  demos that need per-product return reasons — e.g. Nespresso coffee
  machines vs. pods). This is parked as its own follow-up, independent of
  this UI rework — see the `article_category is not per-product` memory.
- Not building the returns-portal question set — this spec only continues
  to make room for it in the same mechanism, as the prior spec did.

## Design

### Architecture — local server, not Artifact

A local Python HTTP server (stdlib `http.server`, no new dependency),
per run, started by the conductor at the top of Phase 0 — the same pattern
already proven by `branded-template`'s preview server and by this session's
own POST-handoff/live-poll spikes. It serves:

- The single-page app: one static HTML file containing both the intake form
  and the progress view, phase-switched by JS, sharing one step indicator.
- `POST /submit` — the intake form's answers, written to
  `<run dir>/intake.json`, flips an in-memory "submitted" flag.
- `GET /state` — reads `run_state.py`'s existing JSON output, polled by the
  page every ~2s once the Building phase starts.

This replaces `render_intake_questionnaire.py`, `render_run_page.py`, and
every Artifact publish/poll call in `SKILL.md`'s intake and reporting
sections.

### Data flow

Operator fills the form → JS `fetch`es `POST /submit` → server writes
`intake.json` and sets the submitted flag → the conductor, waiting on that
flag in a poll loop (not scanning a DOM), reads it and builds the manifest →
Phases 0–2 proceed exactly as today → every `run_state.py` write is
immediately visible to `GET /state` → the same page, now showing the
Building phase, polls and re-renders the lane row, drill-down panels, and
order feed from that JSON. A page reload at any point re-fetches current
phase + state from the server, so nothing is lost if the tab closes.

### Page content — Intake phase

(Fields as validated in mockup v5, `intake-mockup-v5.html`.)

- **Prospect**: website URL; destination region (pre-filled from
  `resolve_auto_defaults.infer_country`, editable — this is only possible
  now because intake runs entirely up front, so editing it costs nothing
  mid-run); default courier (pre-filled from the region's default,
  overridable); Shopify opportunity yes/no toggle.
- **Order matrix**: order count (1–5, segmented picker); a single
  "customise each order individually?" toggle — off by default (auto-varied
  fraud/scenario, no clutter); on reveals per-order cards: fraud-level
  pills, a split-shipment checkbox that forks the card into Parcel A/B (each
  with its own scenario dropdown and courier override), scenario dropdown
  using the real vocabulary above.
- **Customisation**: a single toggle reveals the account's actual Gate C
  extras menu (dynamic recipients, promise dates, order financials, extra
  articles, tags/custom fields, delivery detail, article physical data),
  each item revealing its own real fields on selection — not a placeholder
  field pair.
- **Mode**: babysit / auto, unchanged from the prior spec.

Category stays out of this form, per Non-goals above and the prior spec's
own reasoning — it still can't be known before the scrape runs.

### Page content — Building/Live phase

(As validated in `progress-mockup-v3.html`.)

- Step indicator (Intake ✓ → Building → Live), an indeterminate top
  progress bar, and a pulsing "live" indicator — signals the page is
  actively polling, not static.
- A 5-lane status row (Scrape, Template, Seed, Orders, CDC), each a button.
  Clicking one expands an inline drill-down panel (accordion, one open at a
  time): Scrape shows brand palette swatches and the scraped product grid;
  Template shows a preview thumbnail, resolved path, approval time, and a
  link to the full-size preview; Seed shows the seeded-product table (real
  vs. seeded price, variants, stock) plus the four exchange-demo scenarios
  (even in-product, even cross-product, uneven upward, uneven downward)
  with their actual prices; Orders shows a one-line summary pointing at the
  order feed below; CDC shows pending/sent status including a reminder that
  `generate_orders` stays `false`.
- The order feed itself: one changelog-style card per order, with a
  breathing glow on whichever order is actively running, split shipments
  shown as two side-by-side parcel columns.

### Branding

Reuse `plugins/pl-tools/scripts/pl_brand.py` verbatim — it already exists
on this branch from the prior spec's implementation and needs no rework:
`PRIMARY` (`#3E39D3`) replaces every indigo-600 accent used in the mockups
across both phases, `FONT_FAMILY`/`GOOGLE_FONTS_LINK` (Poppins) replaces the
mockups' default sans-serif, and `LOGO_SVG` appears in the page header on
both phases. `TINT`/`CARD` replace the mockups' generic gray-50/gray-100
backgrounds. This is a restyle of already-validated layouts, not a new
design pass.

### Error handling

- Port conflicts: handled the same way `ensure_launch_config.py` already
  handles them elsewhere in the repo.
- Client-side validation mirrors `validate_manifest.py`'s rules so obviously
  bad input (e.g. 0 orders) is caught before submit, but this is a UX
  nicety — the server still runs the real `--pre-gate` validation before
  Phase 1 regardless of what the form allowed through.
- If the local server fails to start at all, fall back to today's plain
  chat interview — matching the run page's existing "publishing is never
  load-bearing" posture. A UI failure degrades to something plainer, never
  blocks the run.

### Testing

- `server.py`'s two endpoints (`/submit`, `/state`) get stdlib `unittest`
  coverage — no `pytest`, per repo convention.
- The JSON-answers → manifest-fields mapping stays pure and unit-testable,
  same as the prior spec intended.
- The page itself gets manual verification against a real skill run (split
  toggle, region/courier defaults, drill-down panels, live poll cadence) —
  it's browser-rendered HTML/JS, not something a unit test meaningfully
  covers, consistent with how the ★ template preview is already verified
  today.

## Open items for the implementation plan

- Exact polling interval and whether plain `setInterval` fetch is
  sufficient or long-polling is worth it — implementation detail.
- Whether `render_intake_questionnaire.py` / `render_run_page.py` are
  deleted outright or left with a pointer comment to the new server —
  planning decision.
- How much of the mockups' HTML/CSS/JS is reused near-verbatim vs.
  rewritten against real data — the mockups were built to prove the UX, not
  as production code, so some cleanup is expected regardless.
