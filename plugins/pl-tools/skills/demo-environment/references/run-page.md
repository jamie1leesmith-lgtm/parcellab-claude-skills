# The run page

One artifact per run: the conductor maintains `<run dir>/run-page.html` and
republishes it via the Artifact tool at each milestone below — same file
path every time, so the URL stays stable. The page is a VIEW; chat is the
only approval mechanism. Publishing is never load-bearing: if the Artifact
tool is unavailable or a publish fails, say so once in chat and continue —
no phase blocks on it.

Rules baked into every publish: self-contained HTML (no external requests —
the artifact CSP blocks them; product images ARE external, so render each
product card with its name/price/type and link the image URL. **Never use
`<img>` with a remote `src`** — measured on the 2026-08-11 Pets at Home smoke
run, a remote product image renders as a broken-image icon, which reads as a
failed run rather than a styling choice), light/dark via
`@media (prefers-color-scheme: dark)` plus `:root[data-theme="…"]`
overrides, favicon `📦` (never changes mid-run), title
`<brand> demo — <run id>`. Keep the URL returned by the first publish and
carry it into the manifest as `run.page_url` when Phase 0 step 8 writes the
manifest (the manifest does not exist yet at the first publish).

**Not-yet-known values:** the page is published from step 1, before the
interview has answered everything it displays. Any header or card value the
run dir does not yet carry renders as an em dash `—`; it fills in at the next
republish. Never delay a publish waiting for a value, and never invent one.

## States (each row = one redeploy)

| # | When | The page shows |
|---|---|---|
| 1 | Run dir created | Header (brand, path, account by name, run id — path and account are still unanswered at this point, so render them `—`), "collecting products + brand styling", interview underway |
| 2 | `results/scrape.json` ok | Product pool grid (name, type, price, verified badge, PDP link), brand-token swatch strip |
| 3 | ✋ gate opens | The proposed plan: core-4 grid · order matrix table (label, customer, fraud, scenario, products, expected comms with confidence labels) · CDC settings (config source, generate_orders) · pace · a banner: "⏳ Approval waiting in chat" |
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
