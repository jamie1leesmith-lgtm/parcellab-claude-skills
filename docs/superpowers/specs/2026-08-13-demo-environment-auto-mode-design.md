# demo-environment: auto mode vs babysit mode

Status: approved by Jamie 2026-08-13, pending spec review sign-off.

## Problem

Today `pl-tools:demo-environment` always interviews the operator through
14 questions across two rounds, then pauses at two hard gates (★ template
preview, ✋ plan approval) before it sends anything. That is the right
default for a live, watched build — but it means every run needs an
operator present end-to-end, even when the operator would happily accept
sensible defaults for almost everything.

This adds a second mode — **auto** — that answers nearly everything itself
and only interrupts the operator for the two decisions that genuinely
can't be defaulted, or for a blocker it can't resolve on its own. The
existing interactive flow becomes **babysit** mode, unchanged.

## Non-goals

- No literal background process/agent handoff. Auto mode still runs
  synchronously in the current session — it just doesn't pause for input.
- No change to Phase 1–4 execution machinery: agent dispatch, the watch
  loops, Beat 1/Beat 2, telemetry, or the run page. Auto mode only changes
  how Phase 0's intake questions and the two Phase 0 gates get answered.
- No new persistent config format beyond the one answers-doc shape defined
  below.

## Mode selection

- **Babysit** is the default. Nothing about today's behavior changes when
  the skill is invoked without the auto phrase.
- **Auto** is triggered only by an explicit phrase in the request (e.g.
  "run this in auto mode for Acme", "auto-build the demo for Acme").
  Detect it the same way the skill already detects a prospect URL — a
  plain-language cue in the invoking message, not a flag syntax.
- Mode is a run-level choice, recorded in the manifest as `run.mode:
  "babysit" | "auto"` (absent means babysit, matching the existing
  `run.pace` convention).

## Answers doc (optional, auto mode only)

The operator may attach a file (path given in the same message that
triggers auto mode) containing pre-filled answers for any subset of the
auto-resolvable questions below (Q4–Q13; never Q1/Q2 — see next section).
Format: a flat JSON object keyed by the question's manifest field, e.g.:

```json
{
  "destination_country": "DE",
  "run.pace": "fast",
  "gates.order_lifecycle.gate_c": "send-as-is"
}
```

Resolution order per field: **answers doc value, if present → else the
auto-mode default/inference rule below.** A doc is never required; its
absence just means every field falls through to its default. An unknown
key in the doc is reported once in Beat 1 as ignored, not a blocker.

## Q1/Q2 — always asked, even in auto mode

Returns-in-scope (Q1) and Shopify-opp (Q2) decide which of the three
paths (engage / retain / retain-shopify) this run builds. They are never
defaulted and never read from the answers doc — ask them live, exactly as
babysit mode does, before anything else. Every other Round 1/2 question
proceeds unattended in auto mode.

## Q4–Q14 — auto-mode resolution rules

Applies only when auto mode is active. Babysit mode is unaffected and
keeps asking all of these as it does today.

| # | Question | Auto-mode resolution |
|---|---|---|
| 3 | Reuse prior scrape pool? | Reuse when a candidate exists (same as babysit's offer, just accepted automatically) |
| 4 | Destination country | Infer from the scrape: TLD (`.de`→DE, `.co.uk`/`.uk`→UK, `.com`+ no other signal→US), else currency symbol/code or explicit locale/address copy found on the scraped pages. No signal → **US**. |
| 5 | Order count/matrix | The existing documented default matrix (3 orders, standard fraud/scenario spread) |
| 6 | Pace | **Standard** |
| 7 | Extras (Gate C) | **send-as-is** |
| 8 | CDC region/category | Region = Q4's resolved country. Category = best match between the scraped `product_type`s and the CDC's Home/Electronics/Fashion menu; no clear match → **Fashion**. |
| 9 | Target account | User's own demo account (already today's default) |
| 10 | Confirm account name | Auto-confirmed (no ask) |
| 11 | Edit-mode guard fix | **Fix it** |
| 12 | Missing write permissions | **Blocker** — see below, never defaulted |
| 13 | CDC config UUID missing | Existing fallback: `config_source: "none"`, no ask |
| 14 | Shopify store (2+ authed, unpinned) | **Blocker** — see below, never defaulted |

Every resolved value is still written to the manifest exactly as babysit
mode would write an answered question, so Phase 1–4 and validation see no
difference between an auto-resolved field and a human-answered one.

## Gates — auto-approved

Both Phase 0 hard gates are approved automatically in auto mode, using
whatever the pre-build already produced:

- **★ Template preview** — the rendered HTML from Phase 0 step 6 is
  accepted as-is; no screenshot round-trip, no "does this look right?"
  question. Still skipped entirely on the repeat-brand shortcut, same as
  today.
- **✋ Plan approval** — the manifest produced by Phase 0 step 7, once it
  passes `validate_manifest.py --pre-gate`, is accepted as-is. The `mark`
  calls for `asked`/`answered` still fire (telemetry and the run page keep
  working identically), just with no chat round-trip between them.

A gate is **not** auto-approved if the thing it gates failed validation or
rendering — that becomes a blocker (see below), not a silent skip.

## Blockers

A blocker is anything auto mode cannot resolve with a default, an
inference, or a safe retry. When one occurs:

1. Try to resolve it first, if there is a reasonable resolution path
   (e.g. a transient scrape failure retried once per the skill's existing
   fallback rules).
2. If still unresolved, **stop the run**, report exactly what is blocked
   and why (same detail level as babysit mode's equivalent prompt), and
   wait for the operator. This matches babysit mode's existing behavior
   for the same situations — auto mode does not change what counts as
   unrecoverable, only how much gets asked before one is hit.

Confirmed blocker cases (all already hard-stops in babysit mode, unchanged
here):

- Q12 — missing write permissions (the operator must edit
  `~/.claude/settings.json` themselves; no agent workaround exists)
- Q14 — 2+ Shopify stores authed with no
  `~/.claude/parcellab-shopify-seed.env` pin (ambiguous, ask same as
  babysit's Q14)
- Missing Shopify CLI (point at `/pl-setup`, same as babysit)
- Template publish failure after the existing retry path (offer babysit's
  three-way choice)
- A lane failure the skill's existing "Failure handling" table already
  can't self-heal (seed, one order, CDC) — reported per that table, run
  continues past it exactly as babysit mode does; this is not new
  blocking behavior, just unattended reporting of it
- Any scrape/interview data gap with no rule above to resolve it (e.g. the
  scrape agent fails outright and the inline fallback also fails)

## Manifest / reporting changes

- `run.mode: "babysit" | "auto"` — new field, absent means babysit.
- Any answers-doc path used, recorded as `run.answers_doc: "<path>"` for
  traceability (absent when none supplied).
- Beat 1 gains one line when in auto mode: which of Q4–Q14 were
  auto-resolved vs. read from the answers doc, so the operator can see
  what was decided without having watched the run. Format: reuse the
  existing plan-card style list, one line per field, value + source
  (`default` | `inferred` | `doc`).
- Any answers-doc key that didn't match a known field is listed once in
  Beat 1 as ignored (not an error, not a blocker).

## Testing

- Unit-test the country/region-category inference rules against a small
  fixture set of scraped-token shapes (TLD variants, currency signals, no
  signal → US fallback) — pure functions, no live calls needed.
- Unit-test answers-doc merge precedence (doc value wins, missing key
  falls through to default, unknown key collected for reporting).
- One live-run verification in auto mode against a low-risk demo account,
  covering: Q1/Q2 still asked, every other field auto-resolved and visible
  in Beat 1's new reporting line, both gates passed with no chat
  round-trip, and one deliberately triggered blocker (e.g. temporarily
  unpin a multi-store Shopify env) actually stops the run and reports
  correctly.
