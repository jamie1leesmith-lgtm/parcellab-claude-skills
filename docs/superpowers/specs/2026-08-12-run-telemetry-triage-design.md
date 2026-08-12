# Run-telemetry triage — design

**Date:** 2026-08-12
**Status:** approved in brainstorming, not yet planned
**Supersedes:** the "v2" placeholder in
[2026-08-11-demo-environment-live-visibility-and-telemetry-design.md](2026-08-11-demo-environment-live-visibility-and-telemetry-design.md),
which shipped the triage *columns* and deferred the flow that reads them back.

## Why

The runs database has rows and nothing reads them. Two rows exist, both
`Untriaged`, and the second one — Kapten & Son, 2026-08-12, a teammate's run —
records a stalled build with 0 of 12 comms fired. Nobody would have found that
by waiting.

Triaging that row by hand produced the design. Two findings shaped it:

**The knowledge existed and did not reach the run.** The row's `Error detail`
proposes `recipientCustomer: false, recipientPlTest: true` as the cause. That
hypothesis had already been disproven once and written down at
`plugins/pl-tools/skills/order-lifecycle/SKILL.md` ("Do not go digging in Journey
config before that window has elapsed"). The run was `demo-environment`, which
orchestrates `order-lifecycle` without necessarily loading that file. So the
defect is placement, not absence — and a skill that only *writes* rules repeats
it.

**The correctness defect and the largest time sink were the same event.** The
run's biggest uncovered gap, 18.5 minutes, is the wait for comms that could
never arrive. Speed and correctness are one lens here, not two.

## What a triage produces

Working the Kapten row yielded eight distinct outputs. The skill is responsible
for all of them, but optimises for the first two:

1. A **generalisable rule**, proven, that lands where the next run will read it.
2. A **fix backlog item**, where action is needed.
3. A verdict on the row's own hypothesis.
4. A root cause with evidence.
5. Confirmation or correction of an existing skill note.
6. Account-level defects owned by someone else.
7. The Notion triage column values.
8. An explicit list of what remains unknown.

## Shape

One skill, one entry point, three phases.

### Phase 1 — Sweep

Query the runs DB for `Triage status = Untriaged`. Score each row on two axes,
both from data already in the schema:

- **Severity** — `Outcome` in (Stalled, Failed) · `Comms fired` < `Comms
  expected` · `Lanes failed` non-empty · deviation count.
- **Time cost** — `Total elapsed` · `Unattributed` · uncovered gaps.

Present a ranked table and stop. This is arithmetic, so it lives in
`scripts/triage_sweep.py` rather than in prose a conductor may interpret
differently each run.

### Phase 2 — Deep-dive the top row

1. **Read the shared diagnosis reference first.** Kill any hypothesis already
   recorded as a proven non-cause before spending an API call. This step is the
   one that would have changed the Kapten run.
2. **Investigate read-only** through `parcellab-cli`, always comparing against a
   known-good control account. The control comparison is what made the Kapten
   diagnosis conclusive rather than plausible: the failing and working accounts
   had byte-identical recipient config, which killed the hypothesis outright.
3. **Stop rule** — **20 `parcellab-cli` calls per row**, then stop and report.
   The Kapten diagnosis took roughly 15, including the control comparison, so
   20 leaves headroom without licensing an open-ended dig. On exhaustion, record
   what is known, mark the rest `unknown`, and write the row. The mandate is to
   record "unknown" rather than reach: that triage left `Delivered` explicitly
   untested on that account instead of inferring it.

Never writes to a parcelLab account. Diagnosis is read-only by construction.

### Phase 3 — Land it

**Writes unattended** — the two records review owns:

- the Notion triage columns
- an append to the shared diagnosis reference

`references/telemetry.md` states that a *run* never writes the triage columns,
because a run that could write them could also silently destroy them. This skill
is the review side of that same rule, so it is the intended writer. A run and a
triage must not share the same credentials path or the separation is nominal.

**Gated on the user each time:**

- any `SKILL.md` edit (per `CLAUDE.md`, skill edits go through
  `/anthropic-skills:skill-creator`)
- opening a GitHub issue
- anything touching a parcelLab account

**Escalation is proportionate to the finding.** Most triages are quick:

| Finding | Route |
|---|---|
| Mechanical — a rule to record, a wrong line, a missing check | Fix in-session |
| A code change across files | GitHub issue; fix inline if small |
| A genuinely new subsystem | `superpowers:brainstorming` → `writing-plans` |

The default is the first row. Full ceremony is the exception, not the path.

## Distribution — private to Jamie

`marketplace.json` lists two plugins. Everything under `plugins/pl-tools/skills/`
reaches every teammate on `/pl-update`; that listing is the only thing making a
skill public.

This skill ships as **`plugins/pl-private/`, absent from `marketplace.json`**,
installed locally by path. Teammates cannot install or trigger it and it never
appears in `/pl-update`. It keeps version control, `${CLAUDE_PLUGIN_ROOT}`
conventions, and co-location with the `pl-tools` files it edits. Because
`pl-tools` carries no `version` field, a sibling plugin does not affect release
mechanics.

This prevents installation, not reading: `MaxSchm1tt` has write access to this
repo and can read any file in it. Anyone who needs true isolation should use a
separate private repo instead, accepting the two-checkout friction.

## Artifacts

| Path | Purpose |
|---|---|
| `plugins/pl-private/.claude-plugin/plugin.json` | The unlisted plugin |
| `plugins/pl-private/skills/run-triage/SKILL.md` | The skill |
| `plugins/pl-private/skills/run-triage/references/comms-diagnosis.md` | Shared ledger of proven causes **and non-causes** |
| `plugins/pl-private/scripts/triage_sweep.py` | Ranking and gap arithmetic |
| `plugins/pl-private/scripts/tests/` | stdlib `unittest` |

Plus pointers into the ledger from `demo-environment`'s Beat 2 and
`order-lifecycle`'s reporting section — placement is what makes a rule reach the
run.

### Ledger seed

Three rules, all proven live on 2026-08-12 and none currently recorded anywhere:

- **Proven cause.** A message whose `hasReleasedVersion` is `false` renders
  nothing. The trigger still matches and the tracking event still names the
  selected message, so the failure is invisible from the event alone. Evidence:
  account 1626102, journey 13736, messageTypes 30889/30890; the `Dispatch` event
  names `shipping_confirmation_9c8f` and no email record exists account-wide.
- **Proven non-cause.** `releaseStatus: draft` does not block sending — a draft
  message serves its last released version. Evidence: account 1626718 message
  75240 sent 51 emails while `draft`.
- **Proven non-cause.** `recipientCustomer: false` with `recipientPlTest: true`
  does not block sending. Evidence: account 1626718 sent 100 emails with config
  byte-identical to the failing account's.

## Fixing the Timeline blind spot

`Timeline` is capped at 1900 chars because an over-length property makes Notion
reject the entire row. The guard is correct and stays. The mistake was making
analysis depend on a field designed to be droppable — so the slowest runs, the
ones most worth optimising, are exactly the ones that lose their timeline.

**Derive at write time, where the full timeline is in the run dir.** Three new
numeric columns:

| Column | Type | Meaning |
|---|---|---|
| `Uncovered gaps` | Number | total minutes not covered by any instrumented span |
| `Largest gap` | Number | minutes |
| `Largest gap after` | Text | the mark it follows, e.g. `orders:end` |

Truncation then costs detail, never signal.

Two payload reductions, roughly halving it so truncation gets rarer anyway:
store **spans** (`name, start, end`) rather than paired start/end events, and
drop the `agent`/`lane` duplicates — they are byte-identical for `scrape` and
`seed` in the Kapten row.

**Add the three columns to the shared database before this code ships.** Notion
rejects an unknown property and takes the whole row with it, and a rejected
telemetry write is non-fatal by design, so the failure appears as absent data
rather than an error. Use the connector's `update_data_source` against data
source `6061c7ca-bbe2-484c-a072-c0a77d9394d3`.

## Error handling

| Condition | Behaviour |
|---|---|
| No Notion connector | Stop with a clear message. The skill is useless without the DB. |
| `Timeline` missing or truncated | Report gap analysis as unavailable for that row; use the derived columns. Never interpolate. |
| Row has no Beat 2 marks | Treat as a stall signal and rank it up, rather than as missing data. |
| Investigation exceeds its budget | Record findings so far, mark the rest `unknown`, write the row. A partial triage beats an abandoned one. |
| `parcellab-cli` unauthenticated | Stop before Phase 2 and say so. Do not fall back to guessing from the row. |

## Testing

stdlib `unittest` (`pytest` is not installed), run with
`cd plugins/pl-private/scripts && python3 -m unittest discover -s tests -v`.

Fixtures from the two real rows, covering: ranking order · gap computation
against the Kapten timeline, whose expected answer is known (42.6 total, 18.5
largest, after `orders:end`) · a truncated timeline · a row with no Beat 2 · a
timeline whose spans never close.

## Deliberately out of scope

- Any write to a parcelLab account, including the 1626102 message publishing
  this triage identified. That is Max's account and his call.
- The `hasReleasedVersion` preflight check in `demo-environment` — a real fix,
  deferred by Jamie on 2026-08-12, and the first backlog item this skill should
  raise.
- Cross-run trend analysis. Two rows do not support it. Revisit at ten.
