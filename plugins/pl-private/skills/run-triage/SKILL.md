---
name: run-triage
description: Triage parcelLab demo-environment run telemetry — sweep the shared Notion runs database for untriaged runs, rank them by severity and time cost, investigate the worst one read-only through parcellab-cli, and record the proven cause as a durable rule. Trigger on "triage the runs", "what broke in the last demo runs", "why did that run stall", "review the run telemetry".
---

# Run triage

Every `demo-environment` run deposits one row in a shared Notion database. This
skill reads those rows back and turns them into two things: **a proven rule that
lands where the next run will read it**, and **a fix-backlog item** where action
is needed.

## Why the order of Phase 2 matters

The 2026-08-12 Kapten & Son run stalled with 0 of 12 comms fired. Its row
proposed a cause — a recipient-config setting — that had **already been
disproven and written down** weeks earlier. The note existed; it lived in a file
that run never loaded. Roughly 20 minutes went into re-deriving a dead
hypothesis.

That is the failure this skill attacks. Reading the ledger before spending an
API call is not a formality; it is the step that pays for the skill.

## Phase 1 — Sweep

Query the runs database for rows where `Triage status` is `Untriaged`.

- Database: `67609211a22643bfaa6bf94ccbd3f391`
- Data source: `6061c7ca-bbe2-484c-a072-c0a77d9394d3`

Query with the connector's SQL mode, which returns one flat object per row —
`{"Run ID": …, "Outcome": …, "Largest gap": …}` — the shape the script reads.
Write that array to a file, then pipe it in:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/triage_sweep.py < rows.json
```

The script reads a JSON array on stdin, so it needs a redirect or a pipe. Run
bare it exits with a `JSONDecodeError` on empty input.

It scores on these keys, using the Notion column names verbatim: `Run ID`,
`Outcome`, `Reached`, `Comms expected`, `Comms fired`, `Lanes failed`,
`Deviations`, `Largest gap`, `Total elapsed`. A row whose keys arrive under other
names scores as though every field were absent — every row comes back with the
same low score and the ranking is quietly uniform rather than wrong-looking. If
the table looks suspiciously flat, check the keys before trusting the order.

It scores each row on severity (stalled or failed · comms fired short of comms
expected · failed lanes · deviations · never reached Beat 2) and breaks ties on
`Largest gap`, the longest stretch of the run covered by no instrumented span.

Present the ranked table, then **stop**. Ranking is cheap; investigation is not.
Let the reader choose whether the top row is the one they care about.

The scoring lives in a script rather than in this file because a conductor asked
to weigh severity in prose weighs it differently every run — and the point of a
shared database is that defects are found by query rather than by anecdote.

## Phase 2 — Deep-dive the top row

Work in this order.

### 1. Read the ledger first

Read `references/comms-diagnosis.md`.

If the row's stated hypothesis appears there as a proven non-cause, say so,
cite the entry, and go straight to the alternatives it lists. Spend no calls
re-testing it.

### 2. Investigate read-only, against a control

Use `parcellab` (`list` and `show` only — this skill never writes to a parcelLab
account). For every object you inspect on the failing account, **fetch the same
object from a known-good account and compare.**

State which control account you used.

The comparison is what turns a plausible story into a conclusion. The Kapten
diagnosis only became certain when the failing and working accounts turned out
to carry byte-identical recipient config — which killed the leading hypothesis
outright and redirected the search to message release state, the actual cause.

### 3. Read the row's page body, not the `Run page` URL

Run-page artifacts are private to whoever published them, and there is no
publish-time setting or default that changes it. A teammate's link will not
open for you.

The spans and full timeline are written into the row's own page body for exactly
this reason. Rows written before that landed have only their columns — say so in
the triage rather than working around it.

### 4. Budget: 20 `parcellab` calls

The Kapten diagnosis took about 15, including the control comparison. On
exhaustion, stop, record what is known, mark the rest `unknown`, and write the
row.

**Write `unknown` rather than reaching.** That triage left `Delivered`
explicitly untested on the account instead of inferring it from the two events
that had run — and the honest gap is more useful to the next reader than a
confident guess would have been.

## Phase 3 — Land it

### Write without asking

- The Notion triage columns: `Triage status`, `Reviewed at`, `Reviewed by`,
  `Action taken`, plus `Issue key` and `Fix commit` when they exist.
- An append to `references/comms-diagnosis.md`.

Both are review's own records. `references/telemetry.md` in `demo-environment`
states that a *run* never writes the triage columns, because a run that could
write them could also silently destroy them — with one exception: a run sets
`Triage status` to `Untriaged` at row creation, so unreviewed rows are findable
by value rather than by querying for empty. This skill is the review side of
that rule, so it is the intended writer of the rest.

### Ask first

- Any `SKILL.md` edit — per `CLAUDE.md`, skill edits go through
  `/anthropic-skills:skill-creator`.
- Any GitHub issue. Personal account `jamie1leesmith-lgtm` only, never the
  `parcelLab` org.
- Anything touching a parcelLab account, including publishing a message that
  this triage found unpublished. Accounts often belong to someone else.

### Escalate proportionately

Most triages are quick. Full planning ceremony is the exception:

| Finding | Route |
|---|---|
| Mechanical — a rule to record, a wrong line, a missing check | Fix in-session |
| A code change across files | GitHub issue; fix inline if small |
| A genuinely new subsystem | `superpowers:brainstorming` → `writing-plans` |

## When something is missing

Decided once here, so they are not improvised per run:

| Condition | Behaviour |
|---|---|
| No Notion connector | Stop and say so. The skill has nothing to read without it. |
| `parcellab` unauthenticated | Stop before Phase 2. Do not fall back to guessing from the row. |
| `Timeline` missing or truncated | Use `Largest gap` and `Largest gap after`; report per-span detail as unavailable. Never interpolate the missing entries. |
| Call budget exhausted | Record findings, mark the rest `unknown`, write the row. A partial triage beats an abandoned one. |
| Row's hypothesis already a proven non-cause | Say so, cite the ledger entry, and move to the alternatives without spending calls. |

## What a good triage produces

Working one row well yields more than a status change. Aim for:

- a verdict on the row's own hypothesis, including "it was wrong"
- a root cause with evidence someone else can re-check
- a generalisable rule, appended to the ledger
- an explicit list of what remains unknown

The rule is the durable part. A status change helps the table; a rule recorded
where the next run will read it stops the same twenty minutes being spent again.

## Reference

- `references/comms-diagnosis.md` — proven causes and proven non-causes for
  comms that did not fire, each with the account and object it was proven
  against. Read before Phase 2; append after Phase 3.
