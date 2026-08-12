# The run page

One artifact per run: the conductor renders `<run dir>/run-page.html` from
`run-state.json` and republishes it via the Artifact tool at each milestone
below — same file path every time, so the URL stays stable. The page is a
VIEW; chat is the only approval mechanism.

**The page is derived, never authored.** The conductor records facts in
`run-state.json` through `scripts/run_state.py` and runs
`scripts/render_run_page.py <run dir>`. Publishing is one Artifact call on the
rendered file. Never hand-edit `run-page.html` — the next render overwrites it.

**Why this replaced a rule.** Earlier versions of this file carried a rule —
*"the page must never be more than one milestone behind"* — plus escalating
warnings about how often it had been broken. It was then broken four more
times, three of them by conductors that had just read it, and every lapse was
caught by the user asking why the page had not moved. The cause was structural,
not moral: updating the page meant hand-editing HTML with string replacements,
which is expensive, so it lost every race against a live write. Making the
update cheap is what fixes it. **If you find yourself about to edit HTML by
hand, that is the bug** — fix the renderer and its tests instead.

**"Non-fatal" still means what it says:** a failed publish never blocks a
phase. Say so once in chat and carry on.

## Cadence — the page should read as live

The states below are the *minimum*, not the budget. Republish whenever the
run's state changes at all: every lane transition, every confirmed event,
every failure. Two renders that would land in the same turn are one render;
otherwise, when in doubt, republish. Recording a fact and re-rendering are
both cheap by design — that is what makes this affordable, and a page that
lags the run is the specific failure this whole mechanism exists to prevent.

The reader cannot tell a fresh page from a frozen one by looking, so the page
carries its own age (`#freshness`, ticking every second) alongside the
countdown to the next expected event. That is what makes a genuine quiet
period legible as quiet rather than broken — but it is not a substitute for
republishing; an honest "updated 9m ago" is still a stale page.

**The staleness floor during Phase 2** is `wait_for_event.sh`'s settle window
(default 5s), plus the conductor's turn. Widen it only if republishing proves
too expensive, and say so when you do — never silently.

Rules baked into every publish: self-contained HTML (no external requests —
the artifact CSP blocks them. **Never use `<img>` with a remote `src`** —
measured on the 2026-08-11 Pets at Home smoke run, a remote product image
renders as a broken-image icon, which reads as a failed run rather than a
styling choice. Product images, the hero and the brand logo are therefore
**inlined as `data:` URIs** by `scripts/inline_assets.py` during the scrape
lane, and the renderer only ever emits those; a product whose asset was
skipped renders as a text card, never as a broken icon), light/dark via
`@media (prefers-color-scheme: dark)` plus `:root[data-theme="…"]`
overrides, favicon `📦` (never changes mid-run), title
`<brand> demo — <run id>`. Keep the URL returned by the first publish and
carry it into the manifest as `run.page_url` when Phase 0 step 9 writes the
manifest (the manifest does not exist yet at the first publish).

**Translate internal labels for the reader.** The manifest's shipment labels
(`A`, `B`) and slot keys (`fraud_low`, `manual_return`) are plumbing. On the
page, a single-shipment order says "single parcel" and a split order says
"parcel 1 of 2 — arrives" / "parcel 2 of 2 — gets stuck"; slots read as their
human labels. A column of bare `A`s under four orders is unreadable, and the
user had to ask what it meant on the 2026-08-11 run.

**Not-yet-known values:** the page is published from step 1, before the
interview has answered everything it displays. Any header or card value the
run dir does not yet carry renders as an em dash `—`; it fills in at the next
republish. Never delay a publish waiting for a value, and never invent one.

## States (each row = one redeploy)

| # | When | The page shows |
|---|---|---|
| 1 | Run dir created | Header (brand, path, account by name, run id — path and account are still unanswered at this point, so render them `—`), "collecting products + brand styling", interview underway |
| 2 | `results/scrape.json` ok | Product pool grid (name, type, price, verified badge, PDP link), brand-token swatch strip |
| 2b | ★ template preview (step 7) | The template preview and brand-token swatches ONLY — no plan, no order matrix, no seed set. The first deliverable is approved on its own; showing downstream detail the user cannot act on yet is what made the first smoke run confusing. Skipped when the repeat-brand shortcut was taken. |
| 3 | ✋ plan gate opens | The proposed plan: core-4 grid · order matrix table (label, customer, fraud, scenario, products, expected comms with confidence labels) · CDC settings (config source, generate_orders) · pace · a banner: "⏳ Approval waiting in chat" |
| 4 | Gate approved / sends firing | Lane cards — template (push → publish → assign), seed (retain-shopify only), per-order chips (created → tracked → events queued); each chip flips as its results land |
| 5 | Drivers launched, then on **every watcher return** | Per order: the planned event list, each step confirmed / expected / pending, with a countdown to the next event. Confirmations come from `orders/*/events.jsonl` via `run_state.confirm_event`, ingested each time `wait_for_event.sh` returns — roughly 8–12 republishes per run, not one |
| 6 | Beat 1 | The environment-built summary: layout id/status/store, per-order table, CDC request id + link |
| 7 | Beat 2 | Per-arc verification: checkpoints attached vs planned, comms fired vs promised, ✅/⚠️ per arc; fast-pace ordering caveat when `run.pace` is fast |
| 8 | Any failure | The matching failure-table row, verbatim, in a highlighted card at the top — added to whatever state the page is in, never replacing it |

**Wide tables scroll inside themselves.** Every `<table>` on this page —
state 3's order matrix (the widest content in the run), state 6's per-order
table, state 7's per-arc verification table — is wrapped in
`<div class="overflow">…</div>` so it scrolls horizontally within its own
card. The page body must never scroll sideways.

## Where the markup lives

`plugins/pl-tools/scripts/render_run_page.py` owns all of it — layout, CSS, the
four-state vocabulary, the clock. Change the page by changing the renderer and
its tests, never by pasting HTML into a run.

The four states, used everywhere:

| State | Class | Meaning |
|---|---|---|
| confirmed | `s-confirmed` | A republish confirmed this happened |
| happening now | `s-live` | In progress |
| expected | `s-expected` | The page's own clock believes this happened; unconfirmed |
| failed / stuck | `s-failed` | Failed, or a deliberate terminal state |

The clock may only ever promote a step to **expected** — never to confirmed. A
driver that dies therefore shows as a dashed pill that never fills in, next to
a stale `confirmed` stamp: visibly wrong rather than quietly false. When the run
finishes the clock is omitted entirely, so opening the page tomorrow shows the
real end state rather than an animation that ran off the end.

## Roadmap — a genuinely live view

The artifact is not what limits freshness: **only the conductor can republish,
and the conductor only acts in turns.** Phase 2's drivers run in the background
for fifteen minutes, which is precisely when the conductor is least able to
update anything. Any design where the background process updates the view
directly beats any amount of tuning on the republish cadence.

Verified 2026-08-11: a page served from the `preview_start` server polls a local
JSON file every second and tracks changes written by another process, with no
conductor turn at all. The artifact CSP forbids this; localhost does not.

The intended shape, when it is worth building:

- **During the run** — a local polling page in the Browser pane, reading the
  `events.jsonl` files the drivers already write. Roughly one second of lag,
  zero conductor turns. Cheapest real win available.
- **After the run** — one artifact publish as the permanent, shareable record,
  which is what artifacts are actually good at.

`preview_start` is session-scoped, so the local page is a during-the-run tool
only — it cannot be the durable artefact.

A third option exists and is a real project rather than an afternoon: have
`run-lifecycle.sh` post state to Notion (the telemetry database is already
there), and give the artifact the `mcp` capability so it polls Notion via
`watchTool`. That is live *and* shareable, with the driver — not the conductor —
doing the updating. It inherits one constraint: a page declaring `mcp` can
never be shared publicly.

## Milestone hook (the sentence SKILL.md uses)

> record it via `run_state.py`, re-render with `render_run_page.py <run dir>`,
> republish, then record the publish with
> `run_state.record_publish(<run dir>, <the URL the Artifact call returned>)`
> — non-fatal.
