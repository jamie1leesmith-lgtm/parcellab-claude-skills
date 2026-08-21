---
name: demo-environment
description: Build a complete parcelLab customer demo environment from one intake interview — branded email template, 1–5 realistic orders with fraud-risk data walking through good and bad delivery journeys, optional Shopify dev-store build over the real parcelLab integration, and a CDC demo request linking the real orders. Trigger on phrases like "build a parcelLab demo environment for [brand]", "set up the full demo for [prospect]", "run the whole demo build", "prep the demo environment for [brand]". Orchestrates the branded-template, shopify-seed, order-lifecycle and demo-request skills; requires the parcellab CLI, the Browser pane, and (for Shopify opps) the Shopify CLI.
argument-hint: <prospect-url>
---

# parcelLab — Unified Demo Environment Builder

One interview, a background scrape lane, and at most one template
checkpoint (none when a repeat brand's layout verifies live) → a complete demo:
published branded layout, 1–5 fraud-tagged orders running their journeys,
(if Shopify) a seeded dev store with real orders on the real integration,
and one CDC demo request linking those orders.

Read `${CLAUDE_PLUGIN_ROOT}/skills/demo-environment/references/flows.md` if
you need the phase/gate picture; the four sub-skills' own SKILL.md files are
the single source of truth for their mechanics — this skill only prepares
their answers and sequences them (each has an "Orchestrated runs" section
defining its contract).

## Paths

The questionnaire's first field is **"Is this a Shopify opp?"** — the only
path question, since returns are always in scope for this demo.
- No → **retain** path.
- Yes → **retain-shopify** path.

## Intake questionnaire

**Every question is answered by one up-front form, in both modes.** Phase
0 step 2 starts a local server (`run_server.py`) that serves the intake
form, and waits for `<run dir>/intake.json` to appear on disk before
anything else happens — no chat round-trip per question, no trigger-phrase
mode detection. That file is written only on a submission that passed
validation, so its existence on disk is proof intake is complete; there is
no separate parse/extract step and no polling of the page's DOM. Mode
(**babysit** or **auto**) is one of the form's own fields, not inferred
from the invoking message's wording.

**Mode's only effect is at the two hard gates.** Babysit (the default,
when the field reads that way) pauses at ★ and ✋ for a human yes exactly
as before. Auto auto-approves both — see "Both hard gates are
auto-approved in auto mode" below — and nothing else in the run reads
`run.mode`. There is no other auto-mode behavior left: every question that
used to auto-resolve differently by mode is now simply asked (or silently
resolved) the same way regardless of mode.

When `run.mode` is `"auto"`, the run page itself flashes a large banner at
the top — the run is unattended, and the page should say so before anyone
reads a single lane pill. This is rendered by the page's own poll of
`GET /state`, not by anything the conductor triggers.

**The form asks region and courier, so `infer_country`'s output is a
pre-fill, not the final value.** Phase 0 step 2 calls
`resolve_auto_defaults.py --prospect-url "<url>"` before the server starts,
with `--product-pool-file` omitted since no pool exists yet at this point
— that flag is optional precisely for this call. This pool-less inference
is a weaker signal than the later call below: with no scraped prices it
loses the currency-symbol fallback, falling back to TLD, then URL path
locale, then `US`. That weakness is acceptable only because the result is
a **pre-fill**, not the final value — it passes to `run_server.py --region`
purely as the form's default selection, and the operator can change it
before submitting. Whatever `region` the operator actually submits is what
gets written, to **both** `brand.region` and `destination_country`. The
form offers only `US`, `UK`, `DE`, because `validate_manifest.py` accepts
no other `brand.region` — a fourth option would produce a manifest that
fails validation after the operator has already answered everything.

**This pool-less call never returns `brand.category`.** With no pool,
`infer_category` has nothing to count and would return `DEFAULT_CATEGORY`
("Fashion") for every brand unconditionally — `resolve_auto_defaults.py`
therefore omits the `brand.category` key from its output entirely when
`--product-pool-file` is omitted, rather than emit a fabricated value.
`brand.category` and `run.pace` come from a **second**, later call to
`resolve_auto_defaults.py` — with `--product-pool-file` supplied this
time — exactly as before, once the scrape lane's `product-pool.json`
exists:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/resolve_auto_defaults.py \
  --prospect-url "<url>" \
  --product-pool-file "<run dir>/scrape/product-pool.json"
```

Write `brand.category` and `run.pace` from this second call's output
unconditionally — category is not a form field in any mode; it joins the
fields this script has always resolved without asking.

**`intake.json` carries per-order `split` plus per-parcel `scenario` and
`courier`.** Map each order's parcels onto the manifest's `shipments` for
that order — a non-split order has exactly one shipment, a split order has
exactly two, one per parcel. Each parcel's `courier` (or, when that field
is `null`, the run's default courier from the form) becomes that
shipment's `courier`. `scenario` maps straight across per shipment; nothing
here is inferred.

There is no Artifact anywhere in intake. Do not publish one, and do not
poll a DOM — the handoff is the `intake.json` file appearing on disk, full
stop.

The order matrix, region, courier, and the send-as-is/extras toggle all
come from the form directly (every run, every mode — see "Intake
questionnaire" above). The target account is always the user's own
default demo account (every mode — see Phase 0 step 4), and the CDC
config is always `selected_account_config_id: null`, `config_source:
"none"` (every mode — see Phase 0 step 4). Write every resolved field
into the manifest exactly where its question already writes it — Phase
1–4 and `validate_manifest.py` do not distinguish an auto-resolved field
from a human-answered one.

**Both hard gates are auto-approved in auto mode**: at ★ (Phase 0 step
8), accept the pre-built template HTML as-is — no page gate is opened,
no chat question. At ✋ (Phase 0 step 9), once
`validate_manifest.py --pre-gate` passes, treat the plan as approved
without opening a page gate or a chat round-trip. Write both
`<run dir>/template-approval.json` and `<run dir>/plan-approval.json`
directly (`{"decision": "approved", "note": null, "at": "<ISO8601 UTC>"}`)
rather than waiting on a human to post them, and still call
`mark(d, "gate", "<name>", "asked")` immediately followed by
`mark(d, "gate", "<name>", "answered")` for each — telemetry and the run
page see no difference from a fast human yes. A gate whose underlying
artifact failed to render or validate is never auto-approved — that
becomes a blocker (below), not a silent skip.

## Write permissions — settle these BEFORE the gate

A run is read-only until the ✋ gate, then fires a dense burst of writes. If write
permissions are not settled first, the run stalls at its first write with the
environment half-built and the operator answering prompts one at a time.

**Check during Phase 0 step 4**, in the same round that verifies `edit-mode` —
it is the natural place, and it is still cheap to fix there. Read the user's
`~/.claude/settings.json`; if `permissions.allow` does not cover the writes
below, say so at the gate and let the user add them (they must edit that file
themselves — an agent cannot widen its own permissions, and any attempt is
correctly refused).

| Write | Rule |
|---|---|
| Push the layout | `mcp__<parcellab-mcp-server>__journey_write_layout` |
| Publish the layout | `Bash(parcellab --env prod journey layout publish *)` |
| Shopify seed + orders | `Bash(shopify store execute *)` |

`<parcellab-mcp-server>` is **per-install** — the parcelLab connector registers
under a different id for every user, so these rules cannot be copied between
teammates verbatim. Resolve it by reading the name of any parcelLab MCP tool
available in the session (the segment between `mcp__` and the tool name) and
substitute it before offering the snippet.

Order creation and the CDC submit run through scripts, not these tools, and are
covered by whatever Bash rules the user already has. Do not propose
`Bash(parcellab *)`: `pl-setup` installs a `PreToolUse` hook that auto-approves
read-only `parcellab` commands and refuses every write verb, and a blanket rule
would retire that distinction.

## Timing marks — one line each, and the run is measurable

Durations are only ever the difference between two recorded stamps, so a phase
nobody marked is a phase nobody can measure. Call `run_state.mark()` at each
boundary below; each is one line beside work you are already doing, and each
is named again at the step where it happens.

| Boundary | Call |
|---|---|
| Dispatching an agent (scrape, seed) | `mark(d, "agent", "<name>", "start")` |
| Its results file lands | `mark(d, "agent", "<name>", "end")` |
| Starting a lane's own work | `mark(d, "lane", "<lane>", "start")` |
| That lane finishing | `mark(d, "lane", "<lane>", "end")` |
| Posing the ★ template question or the ✋ plan gate | `mark(d, "gate", "<template\|plan>", "asked")` |
| Recording the answer | `mark(d, "gate", "<template\|plan>", "answered")` |
| Posting Beat 1 | `mark(d, "gate", "beat1", "end")` |

Drivers are **not** marked — they stamp their own `run.log`, and three
concurrent drivers amending `run-state.json` would lose updates.

A missing mark yields a null, never a wrong number. Never reconstruct a mark
after the fact: a stamp written later records when you remembered, not when it
happened.

**A lane mark also moves that lane's status pill** on the run page — `start` →
running, `end` → ok. One call does both. When a lane ends as something richer
than ok, say so explicitly with `set_lane` and the mark will not flatten it:

| Lane outcome | Call |
|---|---|
| template published | `set_lane(d, "template", "published", layout_id=<id>, store="<name>")` |
| seed skipped (non-Shopify path) | `set_lane(d, "seed", "skipped")` |
| any lane failed | `set_lane(d, "<lane>", "failed")` (or `add_failure`) |

These two used to be independent, and only `mark` was documented — so every
run left all five pills on "pending" while the tests, which call `set_lane`
directly, stayed green (found 2026-08-12; Currys and UNIQLO show the mirror
image, correct pills and an empty timeline).

## Deviation logging — the moment you notice, not at Beat 2

A variance that did not stop the run is exactly the kind of fact a conductor
forgets by the time it reaches Beat 2's three questions (below) — it never
caused a visible problem, so there is nothing prompting recall. Call
`run_state.add_deviation(d, "<category>", "<one-line detail>")` **inline, at
the moment you notice the variance**, the same way a timing mark is one line
beside work you are already doing. Beat 2's three questions then become a
final backstop read of what this log already holds, not the sole source of
it — and a run whose log is empty going into Beat 2 has actually had a clean
run, not an unexamined one.

`category` is one of the 9 values the telemetry `Deviations` column already
uses. This table is not exhaustive — log any real variance in its category —
but these are the moments already named elsewhere in this skill that call for
it:

| Category | Log it when |
|---|---|
| `validator_rejected` | `validate_manifest.py` returns `MANIFEST INVALID` and you fix and re-validate (Phase 0 step 7) |
| `gate_reasked` | a hard gate genuinely gets asked again — a second ★ preview round, a plan tweak that loops back to step 9 — never on the first ask |
| `lane_fallback_inline` | the scrape-failure inline fallback or the seed-agent inline re-run fires (Failure handling) |
| `api_error` | a publish failure, a per-order failure (direct or Shopify engine), or a CDC 500 is caught and the run carries on past it |
| `manual_intervention` | in babysit mode, the operator has to step in beyond the normal script (auto mode's blockers stop-and-report instead — that is not this) |
| `instruction_unfollowable` | this skill's own text could not be followed exactly as written and you had to deviate — e.g. a prospect catalog that cannot literally satisfy "four distinct product types" |
| `workaround_invented` | you improvised something this skill does not describe to get past a real-world mismatch, including the fix for an `instruction_unfollowable` case above |
| `comm_missing` | Beat 2's second look still shows a comm missing (Phase 4) |
| `retry_needed` | anything above needed more than one attempt before it succeeded |

## The run page

The run keeps one live page, served by `run_server.py` from Phase 0 step 2
for the whole run. It re-renders itself in the browser from `GET /state`
every two seconds, reading `run-state.json` and the same side files the
old renderer read — so there is nothing for the conductor to send to the
page and no URL to carry between phases. `run.page_url` is simply the
local URL the server prints (`http://127.0.0.1:8097/`), written into the
manifest once at Phase 0 step 7 and never updated again, because it never
changes.

Every fact the page shows still has to be recorded through `run_state.py`
exactly as before — `mark`, `set_lane`, `confirm_event`, `add_deviation`,
and so on — the page only stopped being something the conductor renders
and pushes out; it did not stop reading `run-state.json`. Wherever this
file used to call for a separate render-and-publish step after a
`run_state.py` call, that call is now the whole instruction: the page
picks up the change on its own next poll, within two seconds.

**The `Page renders` / `Page publishes` / `Page URL changes` telemetry
columns now stay at zero by design.** They existed to catch a conductor
that recorded a fact but skipped sending the page a fresh copy — a
failure mode a self-updating page cannot have, since there is no separate
send step left to skip. `build_telemetry_row.py` already tolerates empty
lists for these, so nothing there needs to change; the columns simply go
quiet rather than needing to be removed.

## Phase 0 — Intake (front-loaded)

1. **Create the run directory** `$HOME/parcellab-demo-runs/<handle>-<ts>/`
   (handle derived from the prospect URL exactly as shopify-seed Step 3
   derives `prospect_handle`; ts = YYYYMMDD-HHMM). Create `results/`,
   `orders/` and `scrape/` inside it. Initialise run state:

   ```bash
   python3 -c "import sys; sys.path.insert(0, '${CLAUDE_PLUGIN_ROOT}/scripts'); \
   import run_state; run_state.init('<run dir>', '<run id>', '<path>', '<account name>')"
   ```

   **There is no render step here.** The run page is a live server (Phase 0
   step 2), not a file this conductor renders — it reads `run-state.json`
   itself on every poll. Path and account are still unanswered here and show
   as `—` on the page until step 2 writes them.

   **Never hand-edit `run-state.json`.** Record facts through `run_state.py`
   only — the page picks up any change on its next poll, within two seconds.
   There is no separate render step and nothing to send to the page by hand.
2. **Start the run server and wait for intake.** Follow this procedure
   exactly:

   1. **Detect a reuse candidate** — scan `$HOME/parcellab-demo-runs/` for a
      directory whose `<handle>-<ts>` handle equals this run's handle and
      which contains both `scrape/brand-tokens.json` and
      `scrape/product-pool.json`; the most recent such run is the candidate.
   2. **Pre-resolve the region** for the form's default:
      `resolve_auto_defaults.py --prospect-url "<url>"`, with
      `--product-pool-file` omitted — that flag is optional, and no product
      pool exists yet this early (the normal case). Omitting it takes the
      TLD/path-locale/`US` inference, weaker than the later call at step 4
      only in that it has no scraped prices to fall back to. This is only a
      **pre-fill** for the form's region field — the operator can change it
      before submitting — which is exactly why the weaker signal is
      acceptable here. The output also carries no `brand.category` at all
      in this pool-less shape (a category guessed with no pool would always
      read "Fashion", so the script omits the key rather than fabricate
      it); category and pace are resolved later, at step 4, once the scrape
      lane has produced a pool and a second call supplies
      `--product-pool-file`.
   3. **Stop any server left running from a previous run before starting
      this one.** Call `preview_list`; if a `demo-run-server` entry is
      running, `preview_stop` it first. Its `runtimeArgs` carry the
      *previous* run's directory, and `preview_start` reuses an
      already-running server rather than starting a fresh one — skipping
      this step serves the last run's state to this run's operator, with no
      error anywhere to catch it. Do this every time, even when this looks
      like the first run of the session.
   4. **Upsert the launch entry.** **Resolve `${CLAUDE_PLUGIN_ROOT}` to its
      real absolute path first and paste that path into the JSON string** —
      the `{PLUGIN_ROOT}` placeholder below is substituted by you, before
      the command runs. This is the one place in this skill that must not
      keep `${CLAUDE_PLUGIN_ROOT}` in the text: the entry is written
      verbatim into `launch.json`, and `preview_start` spawns
      `runtimeExecutable` + `runtimeArgs` directly — no shell, and no
      `CLAUDE_PLUGIN_ROOT` in the child environment — so an unexpanded
      placeholder reaches `python3` as a literal filename and the server
      dies with "can't open file". `preview_start` still reports a started
      server and `run_server`'s own stderr never appears, so the run
      silently falls through to the step-7 chat fallback. Same substitution
      pattern branded-template Step 8 uses for `{HOME}`, and step 3 below
      for the scrape brief.

      Do it in this order:

      1. `echo "${CLAUDE_PLUGIN_ROOT}"` (or `printenv CLAUDE_PLUGIN_ROOT`)
         and read the absolute path back — e.g.
         `/Users/<you>/.claude/plugins/cache/parcellab-skills/pl-tools/<sha>`.
      2. Build the entry JSON with that path in place of `{PLUGIN_ROOT}`.
      3. Before running the command, re-read the JSON you are about to pass
         and confirm it contains no `$`, no `{`, and no `}` inside the
         `runtimeArgs` path. If it does, you have not substituted it.

      ```bash
      python3 ${CLAUDE_PLUGIN_ROOT}/scripts/ensure_launch_config.py \
        "$PWD/.claude/launch.json" \
        '{"name": "demo-run-server", "runtimeExecutable": "python3",
          "runtimeArgs": ["{PLUGIN_ROOT}/scripts/run_server.py",
                          "<run dir>", "--prospect-name", "<brand name>",
                          "--region", "<pre-resolved region>",
                          "--reuse-candidate", "<date, only if found>"],
          "port": 8097}'
      ```

      (`${CLAUDE_PLUGIN_ROOT}` on the *first* line is fine and stays as-is —
      that one is expanded by the shell running the command. Only the path
      inside the single-quoted JSON needs substituting, because single
      quotes stop the shell expanding anything. `<run dir>` is already an
      absolute path for the same reason.)

      Then confirm what landed on disk: `ensure_launch_config.py` prints the
      file it wrote, so read the `demo-run-server` entry back out of
      `.claude/launch.json` and check the `run_server.py` path is absolute
      and exists (`ls <that path>`). A literal `${CLAUDE_PLUGIN_ROOT}` in
      the file means step 5 will start a server that cannot serve anything.

   5. **`preview_start`** → `{name: "demo-run-server"}`, note the returned
      `tabId`, and tell the operator to fill in the form.
   6. **Poll for `<run dir>/intake.json`.** It is written only on a
      submission that passed validation, so its presence means intake is
      complete and there is nothing to parse or extract separately — read
      it directly. A rejected submission never writes the file; the
      operator sees the reason inline on the page and resubmits the same
      form, so there is no chat fallback to reach for on a validation
      error. From the parsed file, write into the manifest: `path`
      (`shopify_opp` → `retain-shopify`, else `retain`), `run.mode`,
      `gates.order_lifecycle.gate_c` and `gates.order_lifecycle.extras`,
      `brand.region` and `destination_country` (both set to the submitted
      `region`), and the per-order matrix and courier defaults (see
      "Intake questionnaire" above for the shipment-mapping rules) — nothing
      past this point is asked again.
   7. **Fallback, if the server cannot start** (`run_server: cannot bind
      port …` on stderr, or `preview_start` itself fails): fall back to a
      plain chat interview, asking in this order — Shopify opp, the reuse
      question (if a candidate exists), region, courier, the order matrix,
      customisation, mode. The UI is never load-bearing; this is the same
      posture the run page has always had.
3. **Dispatch the scrape agent immediately** — `mark(d, "agent", "scrape", "start")` and `mark(d, "lane", "scrape", "start")` as you dispatch. Use the Agent tool
   (general-purpose subagent, background) with exactly this brief, filling
   the placeholders. **Resolve `${CLAUDE_PLUGIN_ROOT}` to its absolute path
   and paste the three real file paths into the dispatched brief** — a
   subagent does not reliably inherit that variable, and an unexpanded one
   hands it three unusable paths:

   > Execute the demo-environment scrape pass for the run directory
   > `<run dir>`, prospect `<url>`, path `<retain|retain-shopify>`.
   > Follow `${CLAUDE_PLUGIN_ROOT}/skills/branded-template/SKILL.md` Steps
   > 3–6 for brand tokens (write the full `__BRAND_X__` token map + logo +
   > hero to `<run dir>/scrape/brand-tokens.json`) and
   > `${CLAUDE_PLUGIN_ROOT}/skills/shopify-seed/references/product-scrape.md`
   > for the product pool (**≥8 candidates on retain-shopify, ≥5 on
   > retain** — the 8 exists so shopify-seed can still find four products
   > of four different types, each with variant axes and prices that make
   > both an even and an uneven exchange work, after image validation drops
   > any candidate; the retain path seeds no store and has none of those
   > constraints, needing only the four the CDC demo request submits plus a
   > spare, so scraping eight there is wasted PDP navigation — in the
   > superset shape
   > `{id, name, product_type, price, options, image_url, pdp_url, sku}`;
   > variant axes required only on retain-shopify — elsewhere capture what
   > the PDP shows without extra navigation; write to
   > `<run dir>/scrape/product-pool.json`). Validate every candidate image
   > by running
   > `node ${CLAUDE_PLUGIN_ROOT}/skills/demo-request/scripts/check_images.mjs`
   > over the whole pool (accepts 1–N products; 200 + image/*, ranged-GET
   > retry) and set `image_verified` per product from its per-product `ok`
   > flags. Ground rules, non-negotiable: never ask the user anything — a
   > gap is a failure report; decline non-essential cookies; when done (or
   > failed) write `<run dir>/results/scrape.json` as
   > `{"status": "ok"|"failed", "error": null|"<why>"}` and return a
   > one-paragraph summary.

   **Browser pane ownership:** the agent owns the pane from dispatch until
   `results/scrape.json` exists. Do not navigate the pane in that window —
   the ★ template preview naturally starts after it, since it needs the
   scraped tokens. **This binds more than deliberate navigation:** a
   `PostToolUse` hook can open a file in the pane as a side effect of a plain
   Write (observed 2026-08-11, when writing the old run-page file took the
   pane while the scrape agent held it — the run page is now served live and
   the conductor no longer writes it, but any other Write into the run dir
   can trigger the same hook). Writing run files is unavoidable, so treat pane
   contention as expected rather than forbidden: if the pane is taken from the
   agent, do not also drive it, and re-check `results/scrape.json` rather than
   assuming the agent died. **Reused pool:** when the questionnaire's
   `reuse_pool` answer is true, skip the dispatch entirely — copy the prior
   run's `scrape/brand-tokens.json` and `scrape/product-pool.json` into this
   run's `scrape/`, then write `results/scrape.json` yourself as
   `{"status": "ok", "error": null}`. Without that file the pre-build at
   step 6 waits on a precondition nothing else will ever satisfy. Once
   `results/scrape.json` shows
   `ok`: record the fact via `${CLAUDE_PLUGIN_ROOT}/scripts/run_state.py` —
   `mark(d, "agent", "scrape", "end")` the moment the file lands, plus
   `mark(d, "lane", "scrape", "end")`. The page picks this up on its own
   next poll — there is no separate render or send step.
4. **Resolve the remaining Phase 0 checks**, once the questionnaire has
   answered `path`, `reuse_pool`, the order matrix, and `gate_c`:
   - **Shopify resolution (retain-shopify only):** First `command -v shopify` —
     if the CLI is missing, stop and point the user at `/pl-setup`'s optional
     Shopify CLI section (install + full-scope store auth) rather than
     improvising an install mid-intake; the auth must carry the
     order/fulfilment scopes or the order engine hits a re-consent wall later.
     Then resolve the store **without asking**: read
     `~/.claude/parcellab-shopify-seed.env`, else `shopify store auth list`.
     Exactly one store → use it and state it at the ✋ gate. None → stop and
     point at `/pl-setup`. Two or more → this is the only case that asks.
     Then resolve the location GID immediately — follow
     shopify-seed Steps 1–2 exactly, including the fulfils-online-orders
     preference rules. Record both in the manifest.
   - **Category and pace (every run, resolved silently):** call
     `resolve_auto_defaults.py` once `scrape/product-pool.json` exists (see
     "Intake questionnaire" above for the exact invocation) and write its
     `brand.category` and `run.pace` output straight into the manifest — no
     question, in any mode. `destination_country` and `brand.region` are
     already in the manifest from step 2's form submission — this call does
     not touch them.
   - **Target account (every run, resolved silently):** always the user's
     own default demo account (`${PARCELLAB_ACCOUNT_ID:-$PARCELLAB_USER_ID}`)
     — there is no other account choice to offer here any more; a run that
     needs the shared **parcelfashion** account or another target has to be
     built outside this skill. Resolve the human name with
     `parcellab account account show <id>` and stamp
     `account.confirmed_at` immediately — there is no confirmation question
     left to gate it on, but the resolved name is still stated in Beat 1 so
     it stays visible after the fact. Verify
     `parcellab settings edit-mode show` says `account-restricted` for that
     same account, offering the fix if not (the edit-mode guard check
     above). In the same round, check write permissions per *Write
     permissions* above (the write-permissions check above, if something is
     missing) — a missing rule is cheap to fix here and stalls the run
     mid-build if it surfaces after the gate.
   - **CDC config (every run):** always write
     `selected_account_config_id: null`, `config_source: "none"` — the CDC
     uses the caller's default config. Say so in the final report ("caller's
     default config"). This is safe now that the target account is always
     the fixed default account above and the practical default already
     targets that same account — the earlier per-target key lookup
     (`CDC_ACCOUNT_CONFIG_DEFAULT` / `_PARCELFASHION` / `_SHOPIFY`) no
     longer applies, since there is only one target left.
     `generate_orders` is always `false` and `cdc.orders` always `[]` — the run
     never asks the CDC to generate synthetic orders alongside its real ones,
     and the ✋ gate states this as a fixed line so it stays visible. Linking
     still depends on the caller's default config actually targeting the
     right account: the CDC resolves linked order numbers in the config's
     target account, so a default config pointed elsewhere fails linking with
     "No parcelLab order found" (live-verified 2026-08-11) — worth a one-time
     check outside this run if linking ever fails on the very first run.
5. **Repeat-brand template shortcut:** look for an existing layout for this
   brand on the target account and, if one verifies live, offer to skip the
   template lane.
   - **Find it:**
     `parcellab --env prod journey layout list --account <account.id> --all -o json --jmes 'results[].{id:id,name:prettyName,auto:autoLayout}'`.
     **Match rule:** a layout whose `prettyName`, lowercased with punctuation
     and whitespace stripped, contains the brand name or the run's `<handle>`
     similarly normalised. No match → no shortcut. Several matches → offer the
     most recently created one, or run the template lane normally if the user
     is unsure. Never guess an id.
   - **Verify it:** `parcellab --env prod journey layout show <id> -o json`
     must show `releaseStatus: published` AND an `autoLayout` entry whose
     `client` is the store this path's orders will land on. Anything less →
     no shortcut.
   - **If the user accepts,** write `results/branded-template.json` with
     exactly the four keys branded-template's orchestrated contract defines.
     **The CLI's field names are not those keys — copy the values across, do
     not paste the CLI's shape:**
     `layout_id` ← the response's `id` · `release_status` ← the value of
     `releaseStatus` (the publish gate reads `"release_status": "published"`;
     a verbatim `releaseStatus` key leaves `release_status` absent and stalls
     the gate on every order) · `store_assignment` ← the name of the store
     behind the matching `autoLayout` entry's `client` id (resolve it with
     `parcellab --env prod config client list --account <account.id> -o json`)
     · `account` ← the manifest's `account.id`. Add
     `"note": "template lane skipped — verified live at intake"`. Then skip
     the ★ checkpoint; Phase 1 has no template work.
6. **Pre-build everything sendable**, once the interview and
   `results/scrape.json` (status ok) are both in:
   - **The template HTML** from the tokens — branded-template Step 7, build
     only, no push, written to Step 7's own canonical path
     `$HOME/parcellab-previews/{brand-name-lowercase}-parcellab-layout.html`
     (that path, not the run dir: Step 8's preview server serves from there
     and cannot read `~/Documents`). Skip when the repeat-brand shortcut was
     taken.
   - **The run's images, inlined** so the page can actually show them:
     `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/inline_assets.py <run dir>`. The
     run page's `GET /state` payload reads `data_uri` / `logo_data_uri`
     straight out of `scrape/assets.json` — it never fetches a remote URL
     itself — so without this step there is no image data for the page to
     show at all, not just a broken-image icon. This is what makes product
     shots, the brand logo and the hero visible on the run page.
   - **The fraud fragment** for every order, on every path — it depends on
     nothing the engines produce.
   - **Direct engine only** (the retain path — retain-shopify uses the
     Shopify engine below): every order's
     `create.json` + `track.json` + `NN-<status>.json` event files
     (order-lifecycle's payload rules verbatim, no POSTs and no PUTs).
     **Never pre-build these on retain-shopify.** That path's tracking number
     is assigned by Shopify at `fulfillmentCreate` time and its `courier` must
     be read back out of the live pL order-info response (shopify-order-engine
     Parts 5b and 6b — live run: Shopify company `DPD` → pL courier `dpd`, not
     the `dpd-uk` the direct engine uses). Both values are fields in the event
     files, so anything built now would carry a locally invented tracking
     number and a guessed courier, and every event would push at a tracking
     that does not exist. On retain-shopify these files are built fresh at
     6c, after the read-back.
   - **The proposed plan** itself.
   **Scrape failure fallback:** if `results/scrape.json` says `failed` (or
   the agent dies), run the browser pass inline now — brand tokens, product
   pool, image validation, exactly as the scrape brief specifies — and carry
   on. The agent is an accelerator, never load-bearing.

   **Verify the page is not blank before you show it to anyone.** After
   `inline_assets.py`, `scrape/assets.json` must exist — check for it
   directly; with the run page now serving itself from `GET /state`, there
   is no separate render step left to warn on stderr if it is missing. The
   page's scrape panel renders nothing when assets are absent, so skipping
   the inline step still serves a page that looks fine and shows an empty
   showcase — live 2026-08-12 the user approved a template against a page
   showing nothing at all.
7. **Write and validate the manifest — before either gate.** The manifest is
   the plan, so it has to exist before the page can render the plan. Write it
   per the schema in step 9 below, then validate it **with `--pre-gate`**:

   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/scripts/validate_manifest.py --pre-gate <run>/demo-manifest.json
   ```

   Fix any `MANIFEST INVALID` gaps now, while nothing has been asked or sent.
   Log each one via `add_deviation(d, "validator_rejected", ...)` as you fix
   it (see *Deviation logging* above) — this loop running at all is itself
   the fact worth capturing, whether or not it changed the outcome.

   `--pre-gate` defers exactly one check: `approvals.products_approved_at`,
   which cannot honestly exist until the ✋ gate stamps it. Write that field as
   `null` here — **never back-date it to make a validator pass**. Step 9
   re-validates without the flag once the yes arrives, and Phase 1 still
   demands a fully valid manifest.

   Validating here rather than after the gate means a schema error is caught
   before the user is asked to approve anything, instead of forcing an
   approve → validate → fix → re-approve loop.

   **This does not reveal the plan.** The run page shows the plan card only
   once `mark(d, "gate", "plan", "asked")` is in the timeline, so state 2b
   below still shows the template and swatches alone. Ordering is enforced by
   the timeline, not by which files happen to exist.
8. ★ **Gate the template on the run page — before anything else is
   proposed.** The HTML exists on disk from step 6. Copy it to
   `<run dir>/template-preview.html` — this is what `GET /template.html`
   serves and what the gate card embeds; skipping the copy leaves the card
   pointed at a 404 iframe. Then `mark(d, "gate", "template", "asked")`: the
   page's next poll of `GET /state` sees `gates.template` go from `pending`
   to `open` and renders the gate card from that file. Post **one** chat
   line naming what is waiting (the template) and the link
   (`run.page_url`) — do not paste the template into chat or narrate its
   contents; the page already shows it. Then wait for the answer with a
   tracked background task (`run_in_background: true` — never `nohup`, which
   loses the tracking this relies on) rather than blocking silently:

   ```bash
   until [ -f "<run dir>/template-approval.json" ]; do sleep 5; done
   ```

   Read the file once it appears. `decision: "approved"` →
   `mark(d, "gate", "template", "answered")` and continue to step 9 — mark
   this promptly, since the gate card stays on screen, looking unresolved,
   until the page's next poll sees the answered mark.
   `decision: "changes_requested"` → read `note` (the operator's stated
   reason — the schema requires one, so there is always something to act
   on), iterate on the file in chat, `rm` the approval file so a stale
   `approved` cannot be replayed, re-copy the corrected file, `mark(asked)`
   again, and log the round via `add_deviation(d, "gate_reasked", ...)`.
   This is the run's first deliverable and it gates every comm the
   environment will send, so it is approved on its own, ahead of the plan.

   A page gate answered silently is still a gate the operator has to be
   looking at the page to answer — the chat line is what tells them to
   look. A conductor that only waits on the file, posting nothing, produces
   a run that stalls invisibly: the same failure class as the un-armed Beat
   2 that left a finished environment unverified for 19 minutes live on
   2026-08-12. One short line per gate is not optional politeness — it is
   the only thing that makes the wait visible at all.
   - **Serve the actual file before asking.** The file copied to
     `<run dir>/template-preview.html` must be
     `$HOME/parcellab-previews/{brand}-parcellab-layout.html`, resolved from
     the manifest's brand or the run id's handle, taken fresh — make sure
     that file is current before copying it. Asking for approval against a
     stale file is the defect this ordering exists to prevent.
   - **Hold the run page here.** It shows a template-only state — the
     gate card, and nothing downstream — because the plan card only appears
     once `mark(d, "gate", "plan", "asked")` is in the timeline (below), and
     that has not happened yet at this step. Do not front-run it by writing
     the plan into the manifest early: putting detail on screen that the user
     cannot act on, before the first deliverable is even visible, is what made
     the 2026-08-11 smoke run confusing.
   - **Skip this step entirely when the repeat-brand shortcut was taken** at
     step 5 — the layout is already live and verified, so there is nothing to
     preview and `results/branded-template.json` already exists.
   - **Approval here covers the push.** Phase 1's branded-template run does not
     ask again; its own Step 8 checkpoint is already satisfied.
   - **If the server is not running**, fall back to today's chat-only path:
     follow branded-template Step 8 (launch config → `preview_start` →
     navigate → screenshot) in the Browser pane, ask *"Does this look right
     before I push it to parcelLab?"*, and still mark `asked`/`answered`
     around the exchange. The page has never been load-bearing.
9. **Propose the plan** and gate on approval (✋ — the sends gate;
   one yes releases the sends, and nothing before this step has *sent
   anything to* parcelLab, Shopify or the CDC — the only prior calls are
   read-only lookups plus the edit-mode guard).

   **The plan lives on the run page, not in the question.** `mark(d, "gate",
   "plan", "asked")` is the whole act of posing it: the page's own next poll
   of `GET /state` sees `gates.plan` go to `open` and renders the plan card
   from the manifest written at step 7, with nothing further for the
   conductor to build or send. Never paste the plan into chat, and never put
   it in an `AskUserQuestion` option label — that happened on 2026-08-12
   *because* the page of the time could not show it, was logged as an
   `instruction_unfollowable` deviation, and is exactly the defect this gate
   now exists to remove. Post **one** short chat line naming that the plan is
   waiting for review plus the link (`run.page_url`), then wait for the
   answer with a tracked background task (`run_in_background: true` — never
   `nohup`, which loses the tracking this relies on):

   ```bash
   until [ -f "<run dir>/plan-approval.json" ]; do sleep 5; done
   ```

   The one chat line still matters even though the plan itself is on the
   page: a conductor that only waits on the file, saying nothing, produces a
   run that stalls invisibly while the operator isn't looking — the same
   failure class as the un-armed Beat 2 that left a finished environment
   unverified for 19 minutes live on 2026-08-12.

   The page's plan card covers:
   core 4 (four distinct product types) · per-order product distribution ·
   (retain-shopify) the seed set = core 4 + extras at distinct price points ·
   the order/scenario/fraud matrix with expected comm per event (mark
   unproven items) · CDC region/category/config source ·
   `CDC synthetic generation: off` (a fixed line, never a question) ·
   **every extra agreed on the questionnaire, field by field with its actual value** —
   including each auto-derived article weight listed per article, because an
   auto-derived value the user never saw is worse than one they rejected ·
   the account by name. One explicit yes covers all of it; any tweak loops
   back here: read `note` from `plan-approval.json` on
   `decision: "changes_requested"` (the schema requires a note, so there is
   always a reason to act on), iterate in chat, `rm` the approval file,
   `mark(d, "gate", "plan", "asked")` again, and log the round via
   `add_deviation(d, "gate_reasked", ...)` (per *Deviation logging* above).

   **If the server is not running, the plan still has to be readable** — post
   it in chat as a markdown table then, and say the page is unavailable (the
   same fallback posture as Phase 0 step 2). The page being non-fatal never
   means the user approves something unseen.

   **Once approved** (`decision: "approved"` in `plan-approval.json`), do
   these four things before any build work starts:

   1. `mark(d, "gate", "plan", "answered")` at the moment the yes arrives —
      this is where `Duration to build` starts, and doing it promptly matters:
      the gate card stays on screen until the page's next poll sees this mark,
      so a delay here reads to the operator as an unhandled approval.
   2. Re-validate **without** `--pre-gate` (the approval stamp exists now):
      `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/validate_manifest.py <run>/demo-manifest.json`.
   3. No render step — the page already shows the updated state on its next
      poll.
   4. **Open the telemetry row.** Skip only when `PL_RUN_TELEMETRY_DB` is
      unset — check it, do not assume:

      ```bash
      python3 ${CLAUDE_PLUGIN_ROOT}/scripts/build_telemetry_row.py <run dir> committed \
        --skill-version "$(git -C ${CLAUDE_PLUGIN_ROOT}/../.. rev-parse --short HEAD)"
      ```

      Create the page in the telemetry database via the Notion connector,
      setting `Date` to today and `Ran by` to the current user, then write the
      returned page id to `results/telemetry.json` so Beats 1 and 2 update that
      same row. See
      `${CLAUDE_PLUGIN_ROOT}/skills/demo-environment/references/telemetry.md`.

      **`results/telemetry.json` existing is the proof this happened** — Beats
      1 and 2 both branch on that file, so skipping here silently disables
      telemetry for the whole run. Live 2026-08-12 the row was never opened
      despite `PL_RUN_TELEMETRY_DB` being set, and the omission only surfaced
      at Beat 2, when the row had to be back-filled from the timeline.

   This is the first outward-facing write of the run, and it happens only after
   the gate — never before.
   **The manifest schema** (written at step 7, above — kept here because this
   is where its fields were settled). `demo-manifest.json`:
   `run{…, pace: "standard"|"fast" — absent means standard,
   mode: "babysit"|"auto" — absent means babysit, page_url — the local
   `run_server.py` URL, written once at step 7 and never updated}`, `path`,
   `brand{name,url,handle,region,category}`, `account{id,name,confirmed_at,
   edit_mode_verified}`, `cdc{selected_account_config_id,config_source,
   generate_orders,orders}`, `shopify{enabled,store?,location_id?}`,
   `destination_country`, `products[]` (each in scrape shape, carrying both its
   own `id` and `sku`), `selection{core4,shopify_extra}` — **these hold product
   `id` values, not SKUs, and so do every order's `products` and every
   shipment's `products`.** A product's `id` is its goods code (`E491096-000`);
   its `sku` is the variant (`E491096-000-57`). Payload files use SKUs for
   `line_item_id`; the manifest never does. `validate_manifest.py` rejects SKUs
   with `unknown product <sku>` — live 2026-08-11 that cost a full
   validate-fix-revalidate cycle because the rule existed only in the validator
   and nowhere a conductor would read first,
   `brand_tokens{tokens,logo,hero}`, `orders[]` with per-order
   `{label,dir,cdc_slot,fraud_level,customer{name,email},products,
   shipments[{label,scenario,courier,products,events,unproven_events?,
   unproven_chain?}]}`,
   `gates{order_lifecycle{gate_b_answered, gate_c: "send-as-is"|"extras",
   extras}}` — `extras` is empty when `gate_c` is `send-as-is`, and non-empty
   otherwise. Promise dates in `extras` are `YYYY-MM-DD` (a full ISO datetime
   is rejected by the API). `extras.article_weights` is keyed by product `id`,
   never SKU — the same rule as everywhere else in the manifest —
   `{<product id>: {weight: <number greater than 0>, weight_unit:
   "kg"|"g"|"lbs"|"oz"}}` — `weight_unit` is always written explicitly; a
   missing one is rejected. **`intake.json` does not carry that shape:** the
   form collects one run-wide weight (it has no product ids to key by, since
   the scrape lane runs after intake) and emits it under the sentinel key
   `__run_default__`. Fan that one value out to every product id in the run
   — the `core4` plus any `shopify_extra` — when writing the manifest, and
   never copy the sentinel key across; `validate_manifest.py` rejects it as
   `unknown product __run_default__`. See `references/intake-script.md`,
   "Deriving article weights", for both this fan-out and the `product_type`
   fallback that applies only when the operator gave no weight.
   `validate_manifest.py` enforces all of this,
   `approvals{products_approved_at,intake_completed_at}` — the approval stamps
   are the one part written after their gates, since that is when they happen).
   On retain-shopify also write `seed/seed-products.json`
   (`{products: core4 ∪ shopify_extra in scrape shape, location_id,
   prospect_handle}`). The scrape lane's raw output stays on disk under the
   run dir's `scrape/` (`brand-tokens.json`, `product-pool.json`) with its
   outcome in `results/scrape.json`; the manifest carries the selected
   subset.

   **The validate command** (run at step 7, before the gates):
   `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/validate_manifest.py <run>/demo-manifest.json`
   — on `MANIFEST INVALID`, fix the named gaps (re-asking if needed) and
   re-validate. **Never start Phase 1 on an invalid manifest.**

## Phase 1 — Template ∥ seed

**Dispatch the seed agent first (retain-shopify only)**, so it runs while
you build the template — `mark(d, "agent", "seed", "start")` as you dispatch,
and `mark(d, "agent", "seed", "end")` when `results/shopify-seed.json` lands.
Open each lane's own work with `mark(d, "lane", "<template|seed>", "start")`
and close it with `"end"`. Use the Agent tool (general-purpose subagent,
background) with exactly this brief, filling the placeholders:

> Invoke the pl-tools:shopify-seed skill and execute its "Orchestrated runs
> (demo-environment)" contract for the run directory `<run dir>`. The
> manifest and `seed/seed-products.json` are already there. Ground rules,
> non-negotiable: never open the Browser pane; never ask the user anything —
> a gap is a failure report; write your outcome to
> `<run dir>/results/shopify-seed.json` exactly as the contract specifies,
> and return a one-paragraph summary plus the product/demo tables.

**Store assignment is reassigned, never negotiated.** branded-template Step 9b
asks which store should use the template when an account has several, and 9b.3
treats another layout's `country: []` entry for that store as stale. On an
orchestrated run neither is a question: the path already determines the store
(retain-shopify → the Shopify-integrated client; otherwise the account's
default), and a prior brand's mapping on that store is always cleared in favour
of this run's layout. A store can hold only one default auto-template, so the
two are mutually exclusive and leaving the old one means every comm in this run
goes out under the previous brand. Say in Beat 1 which layout lost the mapping,
so the change is visible and reversible.

**Then run branded-template inline** (main session): invoke the
pl-tools:branded-template skill; its "Orchestrated runs (demo-environment)"
contract consumes the manifest's `brand_tokens` and account, and reuses the
HTML pre-built at Phase 0 step 6 at Step 7's own path
`$HOME/parcellab-previews/{brand-name-lowercase}-parcellab-layout.html`
rather than building it again. **Its Step 8 preview question is already
answered** — the ★ checkpoint ran at Phase 0 step 8, before the plan gate, and
the user approved that exact file. Do not ask again: go straight to Step 9's
push and publish. It finishes by writing `results/branded-template.json`.

**Unless the repeat-brand shortcut was taken** at Phase 0 step 5 — then
`results/branded-template.json` already exists from the live-verified
layout, this lane has no work, and the publish gate below reads that same
file.

## The publish gate

Phase 2 must not start until `results/branded-template.json` shows
`"release_status": "published"` — order creation fires the
order-confirmation comm immediately on every path, and an unpublished
template means that first email goes out unbranded. If it says
`not published`, offer exactly three ways forward and wait:
1. fix and re-publish (follow branded-template Step 9a's failure table);
2. the user publishes manually in the portal, then confirms here;
3. explicitly proceed accepting unbranded comms (record the choice in the
   report).

Whichever path this takes, log it via `add_deviation(d, "api_error", ...)` —
the publish failing at all is the variance, independent of how it was
resolved.

**retain-shopify additionally waits for the seed**: `results/shopify-seed.json`
must show `"status": "ok"` before Shopify orders are created (their line
items reference seeded variants). A failed seed lane stops only the order
stage of the Shopify path: report it, offer to re-run the seed inline from
the same manifest (the fallback), and leave every other lane alone.

## Phase 2 — Orders (direct engine: retain path)

For each manifest order, in its `orders/<nn>-<label>/` directory, follow
order-lifecycle's "Orchestrated runs (demo-environment)" contract. Steps 1–3
were pre-built at Phase 0 step 6 on this engine's paths — reuse those files as
they stand; rebuild only if the approved plan changed at the gate. (The
Shopify engine below shares only steps 3–4's *shape*, never these pre-built
files.)

1. Fraud fragment: run `prepare_fraud_fragment.py` for the order's level and
   merge `tags` + `additional_attributes` into `create.json`.

   **Union, never replace.** When `gates.order_lifecycle.extras` also carries
   `tags` or `additional_attributes`, the order's value is the union of the
   intake's and the fragment's — neither side overwrites the other. Taking the
   intake value alone strips the fraud data from every order, and the
   fraud-driven Journey triggers then never fire; the API's success response
   looks identical either way.
2. Build `create.json` + the single PUT with all `add_tracking` mutations
   (order-lifecycle's payload rules verbatim: randomised format-correct
   tracking numbers, courier per shipment, `tracking.articles` mirrored,
   split rules for 2-shipment orders).

   **`extras.article_weights` is a lookup, not a field to copy.** Every other
   extra's manifest key is already the Order API field name; this one is a
   synthetic container. `extras.article_weights[<product id>]` sets `weight`
   and `weight_unit` on **every article whose product is that id**, at both the
   `articles_order` level and every `add_tracking`'s `tracking.articles` — the
   same dual-level rule as any other article field. The manifest keys by
   product `id` (the goods code) while payload articles key by `line_item_id`,
   which is the SKU, so resolve through the order's product, not the article
   key. No top-level `article_weights` is ever written to a payload.
3. Write the `NN-<status>.json` event files from the shipment's `events`.
4. `DRYRUN=1` pass; then launch `run-lifecycle.sh` as a **tracked background
   task — one Bash call per order with `run_in_background: true`, and NO
   `nohup`, `&`, or `disown`** — all orders concurrent.

   **Those are two different mechanisms and mixing them defeats both.**
   `run_in_background` keeps the process attached to a task the user can see,
   and notifies you when it exits. `nohup … &` detaches it from that task
   entirely: live 2026-08-11 a conductor wrapped the launch in `nohup`, so the
   tracked task was the *launcher* — it exited in about two seconds while three
   drivers ran for fifteen minutes with nothing in the user's task list. The
   user had to ask "I don't see any background tasks running?" to find out the
   run was fine.

   Set `STATE_FILE="<run dir>/orders/<nn>-<label>/events.jsonl"` on every launch
   so the watcher in step 5 can see progress.

   `GAP_SECONDS` comes from the manifest's `run.pace`: 300 for standard (the
   default), 60 for fast. When pace is fast, Beat 2's report must note that
   comm ordering was not guaranteed at this pace. Pass `PARCELLAB_ACCOUNT_ID=<manifest account.id>`
   inline on every launch: `create.json`'s `account` field and the driver's
   account both come from the manifest, never from the ambient
   `$PARCELLAB_ACCOUNT_ID`, which may point at a different account than the
   one confirmed at intake. Once drivers are launched: record it via
   `run_state.py` — `mark(d, "lane", "orders", "start")`, and
   `set_schedule`, which the page's clock needs. No render step follows —
   the page's own poll picks this up.
5. **Watch and record.** After launching every driver, run
   `${CLAUDE_PLUGIN_ROOT}/scripts/wait_for_event.sh <run dir>` as a tracked
   background task. When it returns, ingest each order's new `events.jsonl`
   lines with `run_state.confirm_event(...)` and start the watcher again —
   no render step in between. Repeat until every driver's task has reported
   completion, then `mark(d, "lane", "orders", "end")`.

   This is what makes the page live rather than frozen for the fifteen
   minutes that matter most: the page polls `GET /state` every two seconds on
   its own, so recording each confirmed event is the only thing this loop
   needs to do — there is no separate cost per update to budget for the way
   there was when the conductor had to push each state itself.
6. Write `order.json` per the contract.

When every order's `order.json` exists, build
`results/linked-orders.json`: every order with a non-null `cdc_slot` becomes
`{"order_number": <order.json order_number>, "name": <human label>}` — the
label derived from the slot (`fraud_low` → "Fraud risk: low", `manual_return`
→ "Manual return", `return_tracking` → "Return tracking"); `cdc_slot` itself
never goes to the API (its enum was removed 2026-08-11). This is the base
shape only — no event has fired yet at this point in the run, so there is
nothing to capture. Phase 2.5 below adds a `messages` array to each entry
once real Engage comms have had time to land.
An order whose creation failed is excluded (and reported); one order's
failure never stops another's driver. Log any such failure via
`add_deviation(d, "api_error", ...)`.

## Phase 2 — Orders (Shopify engine: retain-shopify path)

Gate: publish gate passed AND `results/shopify-seed.json` status ok.
For each manifest order, in its `orders/<nn>-<label>/` directory, follow
`${CLAUDE_PLUGIN_ROOT}/skills/demo-environment/references/shopify-order-engine.md`:
create the order in Shopify (line items = the order's `products` mapped to
seeded variant gids) → poll pL ingestion → enrich with the fraud fragment →
fulfil per shipment with tracking → poll the pL tracking → build the
`NN-<status>.json` files and launch the driver, following the same rules as
the direct engine's steps 3–4 — but **the event files are always written
fresh at Part 6c, never reused from Phase 0**: only after 6b has read the
`courier` back out of the live order-info response are the file's `courier`
and `tracking_number` knowable at all. This includes that `GAP_SECONDS` comes from the manifest's
`run.pace`: 300 for standard (the default), 60 for fast. When pace is fast,
Beat 2's report must note that comm ordering was not guaranteed at this
pace. It also includes the launch mechanics in full: a **tracked background task
per order (`run_in_background: true`, never `nohup`)** with `STATE_FILE` set,
followed by the same `wait_for_event.sh` watch-and-record loop as the direct
engine's step 5 — no render step, the page polls itself. Once drivers are
launched: record it via `run_state.py` (`mark(d, "lane", "orders", "start")`
and `set_schedule`, with the matching `"end"` when the watch loop finishes).
Then write `order.json` (order_number = the Shopify
order name, e.g. "#1001") and, once all orders are processed, build
`results/linked-orders.json` the same way as the direct engine — base
shape only, same note about Phase 2.5 applies.

Per-order failure isolation: ingestion timeout, enrichment failure or
fulfilment failure marks THAT order partial in `order.json`
(`"status": "partial", "failed_at": "<step>"`) — its events are not pushed,
other orders continue, and the report says exactly which step failed. Log it
via `add_deviation(d, "api_error", ...)`.

## Phase 2.5 — Wait for comms, then capture real message content

Real parcelLab Engage messages take real time to land after their
triggering event — Beat 2 already knows this (comms landed in 3-4 minutes
on single-parcel orders but took over 10 on a split order's parcel,
measured 2026-08-11). Phase 3 below is the run's **only** chance to attach
message content to a linked order — linking existing orders (and anything
riding on them) is only possible on the creation call, there is no
follow-up endpoint to add data to an order once it is linked. This phase
exists purely so Phase 3 never fires before there is anything real yet to
attach.

`mark(d, "lane", "comms_capture", "start")` as this phase begins, so the
run page shows a pill for this wait instead of looking idle for several
minutes between orders finishing and Phase 3 firing.

1. **Wait for the same floor Beat 2 uses**, from the same last-event
   timestamp:

   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/scripts/wait_for_beat2.py <run dir>
   ```

   Despite the name, this script is a generic "sleep until 5 minutes past
   the newest event across every order's `events.jsonl`" utility — it
   writes nothing and has no side effects, so calling it here and again
   later (Phase 4's own Beat 2 arming) is safe: the floor is anchored to
   the last event's absolute timestamp, not to when the script happens to
   be called, so if this wait already satisfied it, that later call
   returns immediately instead of waiting again. Launch it as a
   **tracked background task** (`run_in_background: true`, never
   `nohup`), exactly as Phase 4 does.

2. **Capture real message content for every linked order**:

   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/scripts/capture_order_messages.py <run dir> \
     --since <this run's own start, ISO8601 UTC>
   ```

   `--since` is required and must be this run's own start — never omit it
   or guess. The target account accumulates history across every run
   anyone has ever pointed at it, and without this floor a bare listing
   could match this run's order numbers against a stale message from a
   different day (there is no order/tracking field on the underlying
   record itself — the script matches by reading each candidate message's
   own rendered content). Derive the timestamp from the run directory's
   own `<handle>-<ts>` name (`ts` is `YYYYMMDD-HHMM`, from Phase 0 step 1
   — the same value the directory was created from).

   This writes a `messages` array onto each entry of
   `results/linked-orders.json` directly. Nothing else needs to change to
   carry it further: demo-request's orchestrated-run contract already
   forwards that file's array **verbatim** as `linked_orders` — `messages`
   included, once it is there — so Phase 3 needs no changes of its own.

3. **The exit code decides what happens next.** `0` — every linked order
   got at least one message; proceed to Phase 3. `2` — one or more orders
   still show zero messages, which is not yet a defect — the same "comm
   missing at 5 minutes" situation Beat 2's own re-check exists for.
   `sleep 300` (or re-run `wait_for_beat2.py --from-now --floor 300`) and
   run the capture script **once more**, then proceed to Phase 3
   regardless of the second attempt's result — never loop indefinitely; a
   message that has still not landed by then is reported missing, not
   chased forever. `1` means it could not run at all (no manifest, or no
   `results/linked-orders.json`) — stop and report, this is not a timing
   issue and a second attempt will not fix it.

   Log the retry via `add_deviation(d, "retry_needed", ...)`. If an order
   still shows zero messages after the second attempt, log that
   separately via `add_deviation(d, "api_error", ...)` — the order still
   links and the run still carries on, exactly the class of degraded-but-
   continuing outcome that category already covers.

`mark(d, "lane", "comms_capture", "end")` once step 3 above lets you move
on, whichever way it resolved.

**This does push Beat 1 later than before.** It now posts only after this
wait, not immediately once orders exist. Say so plainly in auto mode's
opening line alongside the existing unattended-run flag — an operator
watching the run page will see a longer gap before the first report than
earlier runs had.

## Phase 3 — The one CDC call

Exactly one CDC interaction per run, after Phase 2.5 — with a `cdc_live_`
token, linking existing orders (and any `messages` now sitting on them from
Phase 2.5) is only possible on the creation call. Invoke the
pl-tools:demo-request skill's "Orchestrated runs (demo-environment)"
contract against the run dir: it builds the payload from the manifest +
`results/linked-orders.json` and submits once — bracket the invocation
with `mark(d, "lane", "cdc", "start")` and `"end"`. Do not retry a 500 (the
request already exists — the results file records it), but do log it via
`add_deviation(d, "api_error", ...)`.

## Phase 4 — Report

**Beat 1 — environment built** (immediately after Phase 3). **In auto mode,
open with a line flagging that this ran unattended** — the same fact the run
page's banner already flashes, so the chat report doesn't undersell what the
page shouts. Then: layout id +
release status + store assignment (+ any 9b country-override warning,
repeated verbatim) · per order: number, customer, fraud level, slot,
courier(s) + tracking number(s), scenario, and the expected comm per event
with confidence labels · (retain-shopify) the seed table + demos +
adjustments from `results/shopify-seed.json` · CDC request id/URL, which
orders were submitted for linking, and the config source (say "caller's
default config" when `config_source` is `none`). No currency symbols.
**In auto mode, Beat 1 also lists every auto-resolved field** — one
line per field from `resolve_auto_defaults.py`'s output, showing its
value and source (`default` | `inferred`), in the same plan-card list
style as the rest of Beat 1.
Once Beat 1 is posted: record it via `run_state.py` — `mark(d, "gate", "beat1", "end")`, which is where `Duration to build` ends. No render step follows.
Update the telemetry row (stage `beat1`) with the build results, if
`results/telemetry.json` exists.

**Then arm Beat 2's wake-up, in the same turn.** Nothing else will:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/wait_for_beat2.py <run dir>
```

Launch it as a **tracked background task** (`run_in_background: true`, no
`nohup`). It sleeps until 5 minutes past the newest event across every order's
`events.jsonl`, then exits — and that exit notification is what re-invokes you
to run Beat 2.

**A conductor only acts when something invokes it.** By Beat 1 every driver and
watcher has finished, so unless this task is running there is no pending event
left to wake anyone, and the run simply stops one beat short. Live 2026-08-12
that left a completed environment sitting unverified for 19 minutes until the
user asked why Beat 2 had not fired — the run page said `cdc ok` and nothing
further. Arming this is not optional bookkeeping; it is the only thing that
makes Beat 2 happen at all.

If the task is somehow lost, say so plainly and run Beat 2 as soon as you next
act — a late Beat 2 beats a silent one.

**Beat 2 — verified** (after each order's driver finishes AND **≥5 minutes**
after its final event): per order,
order-info lookup; report checkpoints
attached vs planned, and — for *which* comm each tracking selected —
`contacted_with_messages` vs the expected comms, explicitly covering the good
AND bad arcs the run promised.

**Read these from the response's real paths** — none of the three sit where the
obvious name suggests, and guessing produces an empty report that reads as a
failed run:

| What | Path on the order-info response |
|---|---|
| Checkpoint status | `trackings[].checkpoints[].status_code` (not `status`) |
| Which comm a tracking selected | `trackings[].reporting_info.contacted_with_messages` |
| pL courier | `trackings[].courier_info.courier` |

**Never count total sends from `contacted_with_messages`.** It lives per
tracking and is deduplicated within that tracking's own array, so an
order-level comm (`order_confirmation`, `shipping_confirmation`) that fires
once per tracking on a multi-tracking order reads as one accounted-for entry
in each tracking's list — not as the same physical send referenced twice. A
split-shipment order therefore always undercounts by one send per extra
tracking if this field is treated as the count.

**Proven live 2026-08-13**, account 1626718, run `adidas-20260813-1033`: split
order `ADI-1786614815` actually sent `order_confirmation_1093` twice — once
per tracking, at 09:55:16 and 09:55:47, both to the same recipient. Beat 2
reported 15 comms for the run from `contacted_with_messages`; the account had
actually sent 16. Get the real count from raw send records instead:

```bash
parcellab track email list --account <id> --page-size 50 -o json \
  --jmes 'results[?createdAt>=`<run start>`].{mt:messageType,at:createdAt}'
```

Count sends per `messageType` across the run window and report that as
"comms fired" — a split order will legitimately show two sends of the same
order-level `messageType`, and that is the true count, not a bug to explain
away.

Look the order up by **`order_number` + `account`**. The
`courier` + `tracking_number` form this step used to specify returns
`Unauthorized` on a conductor's credentials (live 2026-08-12, same token that
served the `order_number` form seconds earlier).

**A comm still missing at 5 minutes is not yet a defect — re-check before you
call it one.** Wait a further 5 minutes and look again; only report a comm as
missing once a second look agrees. This floor was 15 minutes precisely because
an early report is worse than a late one: measured 2026-08-11, comms landed in
3-4 minutes on single-parcel orders but took over 10 on a split order's parcel,
and reporting at 6 minutes put a wrong defect hypothesis in front of the user.
The floor came down to 5 on 2026-08-12 (verified against the operator's own
inbox), so **the re-check now carries the protection the longer wait used to** —
it is what makes 5 minutes safe, not an optional extra. A run that reports
"comm missing" without a second look has skipped the step, and the split
parcel is where that will bite first.

Once a second look confirms it, log it immediately via
`add_deviation(d, "comm_missing", ...)` — do not wait for the three questions
below; by then it is already known and logging it now is one line.

**Before diagnosing a missing comm, check whether the message can send at all.**
Resolve the journey channel's `messageType` to its message and read
`hasReleasedVersion` — a message that has never been released renders nothing,
while the trigger still matches and the event still names it.

Two things that look like causes and are not, both proven live on 2026-08-12:

- **`releaseStatus: draft` does not block sending.** A draft serves its last
  released version — account 1626718 message 75240 is `draft` and has sent 51
  emails. `hasReleasedVersion` is the gate, not `releaseStatus`.
- **`recipientCustomer: false` with `recipientPlTest: true` does not block
  sending.** That is normal demo-account config. Account 1626718 sent 100 emails
  with channel config byte-identical to a failing account's.

Re-deriving either one costs a run about twenty minutes. The fuller ledger, with
the command for each check, is the run-triage skill's
`references/comms-diagnosis.md` if you have that skill installed.

**Verify the edit-mode guard.** Once every driver has exited and the
verification above is done, confirm the guard is still `account-restricted`
for the user's own account (the only account a run ever targets now, so
nothing should have repointed it — this is a sanity check, not a restore).
Report it in one line. If it is not, say so explicitly with the error; a guard
pointing at another account is exactly the state the next run's Phase 0 check
will trip on.

For every unproven event or chain that fired correctly, record it in
`${CLAUDE_PLUGIN_ROOT}/skills/order-lifecycle/references/status-codes.md` —
automatically, then report what was written. Each entry carries the date, the
order number and the account, so a later reader can check it. A run edits a
skill reference file here on purpose: the alternative is proven status codes
staying labelled unproven because nobody answered a prompt at the end of a
fifteen-minute run.
Once Beat 2 is posted: record it via `run_state.py`. No render step follows.

Update the telemetry row (stage `beat2`), filling `Comms expected` and
`Comms fired` from the verification just performed. `Duration to build` is
derived from the marks — never compute a duration by hand.

**Then append the run detail to the row's own page**, so the run is readable by
anyone on the team:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/build_run_digest.py <run dir>
```

Append the output to the Notion **row page** — the page the `beat2` update just
wrote to — not to the database and not to a new page. The run page is served
from `127.0.0.1` on whoever ran the run's own machine and cannot be reached or
shared from anywhere else, so this digest is the only copy a teammate can
open. A failed append is recorded and mentioned once in the
final report, exactly like a failed row write: telemetry is an observer, never
a dependency.

**Then answer these three questions explicitly before writing the row.** By
now, most of what they ask should already be sitting in `state["deviations"]`
from `add_deviation()` calls made live through the run (*Deviation logging*,
above) — these questions are a final backstop pass, not the only source. Read
the log first, then ask whether anything is still missing from it. An open
"did anything go wrong?" reliably returns "no"; these stay specific on
purpose:

1. Did any instruction fail to work as written? If so, which file and line?
   → `instruction_unfollowable`
2. Did you do anything the skill does not describe, including a workaround for
   a tool that behaved unexpectedly? → `workaround_invented`
3. Did the user have to intervene, correct you, or ask why something had not
   happened? → `manual_intervention`

Answer them from the actual run, not from intent. Live 2026-08-11 all three
would have been answered "no" by a conductor that had in fact wrapped its
drivers in `nohup` against the skill's instruction, leaving the user staring
at an empty task list — question 3 is the one that would have caught it (this
is exactly why the log is now built live rather than relying on this pass
alone). If any answer surfaces something not already in the log, call
`add_deviation()` for it now, before writing the row — the Notion `Deviations`
and `Deviation notes` columns are derived from that log, not typed by hand.

## Blockers (auto mode)

A blocker is anything auto mode cannot resolve with a default, an
inference, or the skill's existing retry/fallback rules. On a
blocker: stop the run, report exactly what is blocked and why (the
same detail babysit mode's equivalent prompt would give), and wait for
the operator. This does not change what counts as unrecoverable —
every case below is already a hard-stop or a reported failure in
babysit mode; auto mode just reaches it without having asked anything
else first.

| Blocker | Same as babysit's... |
|---|---|
| Q7 — missing write permissions | the existing write-permissions prompt |
| Q8 — 2+ Shopify stores, no env pin | the existing Shopify-store prompt |
| Missing Shopify CLI | the existing `/pl-setup` pointer |
| Template publish failure after retry | the publish gate's three-way offer |
| A lane failure the "Failure handling" table below already reports | that table's own response — reported, run continues past it, never new blocking behavior |
| A scrape/interview data gap with no resolution rule above | the scrape-failure inline fallback; if that also fails, stop and report |

## Failure handling

| Lane fails | Blocks | Response |
|---|---|---|
| scrape agent | nothing | run the browser pass inline (Phase 0 step 6's fallback) |
| seed agent | Shopify orders only | report, offer inline re-run from the same manifest |
| template publish | Phase 2 (all orders) | the three-way publish-gate offer |
| one order (any engine) | nothing else | mark partial in its order.json; report the exact step |
| message capture (Phase 2.5) | nothing — orders still link without it | retry once after a further wait, then proceed regardless; report any order still empty |
| CDC call | nothing | report; 500 = request exists, retry manually in-app |

On any failure above: record it via `run_state.py` — no render step follows,
the page picks it up on its own. Also log it via
`add_deviation()` — `lane_fallback_inline` for the scrape/seed rows,
`retry_needed` for a message-capture retry, `api_error` for template
publish, one order, the CDC call, or an order still empty after a
message-capture retry — even though none of these stop the run; that is
precisely what this log exists to catch (*Deviation logging*, above).

Fallback rule (Approach B): any agent lane can be re-run inline in the main
session from the same manifest — the brief and the contract are identical.
Never silently continue past a failed lane; every lane ends in a results
file or a reported failure, and Beat 1 lists any lane still outstanding.
