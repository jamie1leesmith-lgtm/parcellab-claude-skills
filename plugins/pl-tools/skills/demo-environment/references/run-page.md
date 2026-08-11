# The run page

One artifact per run: the conductor maintains `<run dir>/run-page.html` and
republishes it via the Artifact tool at each milestone below — same file
path every time, so the URL stays stable. The page is a VIEW; chat is the
only approval mechanism.

**"Non-fatal" means a failed publish never blocks a phase. It does not mean
the publish is optional.** Skipping it is a defect, not a shortcut. Observed
twice on the 2026-08-11 smoke run: the page sat at the approval gate through
the entire template lane, and again through order creation, ingestion and
enrichment — each time because a live write felt more urgent than a view.
The states worth watching are exactly the ones where the conductor is
busiest, so the pull is toward skipping precisely when it costs the user
most.

**The checkable rule:** the page must never be more than one milestone
behind the run. Before starting any new phase or lane, if the page still
shows the previous milestone, republish first — it is one Write plus one
Artifact call. If the Artifact tool is unavailable or a publish fails, say
so once in chat and continue; that is the only case where the page may lag.

**Treat the republish as a step of the phase, not a note about it.** This
rule was written after two failures on the 2026-08-11 smoke run and then
broken a third time within the same run, by the conductor that had just
written it. The cause is structural: every hook below is a trailing sentence
appended to a paragraph whose subject is some other action, so it reads as an
aside and is dropped precisely when that other action is demanding. Counter
it by treating the hook as its own numbered step — when a phase's steps are
"1. create the order · 2. poll · 3. enrich", the republish is a step in that
list, not a remark after it. A phase is not finished while the page still
shows the previous one.

**The user is the detector of last resort, and that is a failure.** All three
lapses were caught by the user asking why the page had not moved — not by the
conductor noticing. If the user has to ask, the rule has already failed.

Rules baked into every publish: self-contained HTML (no external requests —
the artifact CSP blocks them; product images ARE external, so render each
product card with its name/price/type and link the image URL. **Never use
`<img>` with a remote `src`** — measured on the 2026-08-11 Pets at Home smoke
run, a remote product image renders as a broken-image icon, which reads as a
failed run rather than a styling choice), light/dark via
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
| 5 | Drivers launched | Per order: planned event list with "running since HH:MM"; timestamps filled in from `orders/*/run.log` at each driver-completion notification |
| 6 | Beat 1 | The environment-built summary: layout id/status/store, per-order table, CDC request id + link |
| 7 | Beat 2 | Per-arc verification: checkpoints attached vs planned, comms fired vs promised, ✅/⚠️ per arc; fast-pace ordering caveat when `run.pace` is fast |
| 8 | Any failure | The matching failure-table row, verbatim, in a highlighted card at the top — added to whatever state the page is in, never replacing it |

**Wide tables scroll inside themselves.** Every `<table>` on this page —
state 3's order matrix (the widest content in the run), state 6's per-order
table, state 7's per-arc verification table — is wrapped in
`<div class="overflow">…</div>` so it scrolls horizontally within its own
card. The page body must never scroll sideways.

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
