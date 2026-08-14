# Run telemetry

Every run deposits one row in a shared Notion database, so defects are found by
query across users instead of by anecdote.

## The live database

**Created 2026-08-11, shared with the team:**
https://app.notion.com/p/67609211a22643bfaa6bf94ccbd3f391 — id
`67609211a22643bfaa6bf94ccbd3f391`. This is the one shared database; do not
create a second one. `/pl-setup` writes this id into every account's
`PL_RUN_TELEMETRY_DB` automatically, with no question asked and nothing
mentioned in its summary — this is managed centrally, not a per-person choice
presented during setup.

The seven timing columns were added on 2026-08-11 and are already live. A
column must exist before a run can write it: Notion rejects an unknown
property name, and a rejected telemetry write is non-fatal by design, so a
missing column shows up as silently absent data rather than as an error. Add
any future column through the connector's `update_data_source`
(`ADD COLUMN "Name" NUMBER`) against data source
`6061c7ca-bbe2-484c-a072-c0a77d9394d3`, not by hand in the UI — the schema is
shared, and doing it through the connector keeps it reproducible.

Columns, exactly:

| Column | Type | Options |
|---|---|---|
| Run ID | Title | |
| Date | Date | |
| Ran by | Person | |
| Brand | Text | |
| Prospect URL | URL | |
| Path | Select | engage · retain · retain-shopify |
| Account | Number | |
| Skill version | Text | |
| Run page | URL | |
| Outcome | Select | Committed · Built · Verified · Stalled · Failed |
| Reached | Select | Gate · Template · Orders · CDC · Beat 1 · Beat 2 |
| Lanes failed | Multi-select | scrape · template · seed · orders · cdc |
| Orders planned | Number | |
| Orders created | Number | |
| Events planned | Number | |
| Events pushed | Number | |
| Comms expected | Number | |
| Comms fired | Number | |
| Duration to build | Number | minutes, derived: plan gate `answered` → Beat 1 `end`; null if either mark is missing |
| Total elapsed | Number | minutes, derived |
| Measured working time | Number | minutes, union of all measured intervals |
| Waiting on user | Number | minutes, union of gate ask→answer |
| Unattributed | Number | minutes, total minus everything covered |
| Event window | Number | minutes, first driver start → last driver end; null while any driver is unfinished |
| Slowest lane | Text | |
| Timeline | Text | the run's timeline as JSON, capped at 1900 chars (Notion rejects a rich-text value over 2000, and a rejected property rejects the whole row); oldest entries drop first behind a `{"truncated": N}` marker |
| Page publishes | Number | Artifact calls, recorded by the conductor. Healthy run ≈ 8–12 |
| Page renders | Number | renders, recorded by `render_run_page.py` itself. **publishes < renders means a skipped Artifact call** |
| Max page gap | Number | minutes; longest gap between consecutive publishes inside the driver window. Null while any driver is unfinished |
| Page URL changes | Number | distinct published URLs − 1. `0` = stable; ≥1 means readers were left on a URL that stopped updating |
| Page cadence | Text | publish offsets in seconds from the first render, e.g. `0,45,320,610` |
| Largest gap | Number | minutes; the longest stretch covered by no instrumented span. Null when fewer than two stamps |
| Largest gap after | Text | the mark that gap follows, e.g. `orders:end` |
| Deviations | Multi-select | validator_rejected · api_error · retry_needed · gate_reasked · comm_missing · lane_fallback_inline · manual_intervention · instruction_unfollowable · workaround_invented |
| Error detail | Text | |
| Issue key | Text | |
| Triage status | Select | Untriaged · Reviewed - no action · Fix planned · Fix shipped · Can't reproduce |
| Reviewed at | Date | |
| Reviewed by | Text | |
| Action taken | Text | |
| Fix commit | URL | |
| Verified in run | Text | |
| Timing note | Text | a factual, non-causal size-and-location summary from run-triage's Phase 2b (`Largest gap`, `Unattributed`) — never a claim about why. Written by review, like the other triage columns above it. See `pl-private`'s `run-triage` skill if installed. |

### Reading the timing columns

**They are not additive.** A gate can overlap measured work — the scrape agent
runs during the intake interview — so `Total` minus `Measured` minus `Waiting`
double-subtracts. `Unattributed` is computed from a single union across every
interval; `Waiting on user` is an overlapping view of the same timeline.

**`Unattributed` is not user think-time.** It is everything not yet
instrumented. On the run this was designed from it would have been ~37 minutes,
almost all of it the conductor fixing defects rather than the user thinking. It
shrinks as instrumentation improves, so a large value is a signal worth reading.

**`Largest gap` points at one stretch; `Unattributed` totals them all.** They
measure the same uninstrumented time from different ends, so they are not
additive and the largest gap is always the smaller number. On the 2026-08-12
Kapten & Son run the largest gap was 18.5 minutes after `orders:end` — the wait
for comms that could not arrive, which was also that run's correctness defect.
A single large gap points at one event to investigate; a large `Unattributed`
spread thinly across many small gaps points at missing instrumentation instead.

**`Event window` is concurrent.** Drivers run in parallel, so the window is the
longest single order, never the sum of every event. The live run's window was
15.2 minutes; multiplying 12 events by the 200 s gap suggests 40 and is wrong.

### Reading the page columns

Added 2026-08-12 because teammates reported the run page "isn't updating" and
the claim could not be checked: before this, a run that never republished and
one that republished twelve times left identical rows.

| Row reads | Diagnosis |
|---|---|
| publishes ≈ renders ≈ 10, max gap ~3.5 min | Working as designed |
| renders 10, publishes 2 | Conductor renders but skips the Artifact call |
| renders 2, publishes 2 | Conductor skips the whole hook |
| publishes 10, max gap 9 min | Publishing too slowly — the watcher loop is not re-triggering |
| URL changes ≥ 1 | Readers were watching a URL that stopped receiving updates |
| publishes ~10, max gap fine, still reported frozen | Viewer-side: an open tab not picking up redeploys |

**`Page publishes` reads one short.** The run's last publish lands either side
of the `beat2` telemetry write, so the final Artifact call is never counted. A
consistent off-by-one is readable; a special case would not be.

**`Page renders` is the trustworthy half.** `render_run_page.py` records its own
render, so it cannot be skipped-but-reported. Publishes are self-reported and
carry the same caveat this file gives for `manual_intervention` below.

**`Max page gap` is scoped to the driver window** — the only stretch with an
expected cadence (one event wave per `GAP_SECONDS`). Across the whole run it
would be dominated by legitimate waiting at the plan gate, which can be ten
minutes and is not a defect.

## The write contract

**Three writes per run**, all through the user's own Notion connector:

| When | Stage | Effect |
|---|---|---|
| Plan gate approved | `committed` | Create the row |
| Beat 1 | `beat1` | Update with build results |
| Beat 2 | `beat2` | Update with verification results |

Build each payload with:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/build_telemetry_row.py <run dir> <stage> \
  --skill-version "$(git -C <plugin repo> rev-parse --short HEAD)"
```

**Send the object this prints straight through to the Notion write, every key,
unmodified.** Never hand-select a subset of its fields — an omitted property
reads back as null forever, indistinguishable from one the script never
computed at all. Live 2026-08-13/14 a conductor did exactly this on both the
`beat1` and `beat2` writes, and `Timeline`, `Lanes failed`, `Error detail`,
`Waiting on user`, and `Page URL changes` were all correctly computed but
never reached the row — the run had to be triaged and backfilled afterward to
recover data the script had already produced.

**Why the row is created at gate approval, not at the end.** If it were written
only on completion, every run that died would never appear, and the table would
systematically over-represent success — hiding exactly the failures it exists to
surface. A stalled run leaves a row with no Beat 2, which is the signal.

**That signal only works if the row is opened on time.** A run that creates its
row late — at Beat 2, say — was never capable of recording its own stall, and a
run that skips creation entirely is invisible rather than merely incomplete.
`results/telemetry.json` is the marker: Beats 1 and 2 branch on it, so its
absence disables telemetry silently for the rest of the run (live 2026-08-12).

**A large `Largest gap` after `cdc:end` means Beat 2's wake-up was not armed.**
Beat 1 launches `scripts/wait_for_beat2.py` as a tracked background task; its
exit is what re-invokes the conductor. Without it the run stops one beat short
with every lane green, which reads as success — the 19.2-minute gap on
`thenorthface-20260812-2328` is that failure's fingerprint.

## Rules

- **Never write the triage columns from a run**, with one exception. They
  belong to review, and a run that could write them could also silently
  destroy them. The exception is `Triage status`, set to `Untriaged` at row
  creation (stage `committed`) only, so unreviewed rows are findable by value
  rather than by querying for empty. `beat1` and `beat2` do not emit it — an
  update that re-sent it would reset whatever the reviewer had chosen.
- **Never write credentials, tokens, or customer data.** Demo customers are
  synthetic; account id and brand URL are internal-only.
- **`/pl-setup` sets `PL_RUN_TELEMETRY_DB` automatically, without asking.**
  This is a managed default, not a per-person opt-in question — do not add one.
  An account with no Notion connector still gets the variable set; its writes
  simply fail at run time (see below).
- **A failed Notion write never fails a run.** Record it in the run dir, mention
  it once in the final report, carry on. Telemetry is an observer, never a
  dependency.
- **Self-reported deviations are the weak link.** `manual_intervention`,
  `instruction_unfollowable` and `workaround_invented` cannot be derived and
  depend on the conductor noticing its own mistakes. Live 2026-08-11 a conductor
  launched drivers with `nohup` against the skill's intent and did not notice
  until the user asked. Ask the closed questions at Beat 2 — "did any instruction
  fail to work as written? which line?" — rather than an open "did anything go
  wrong?", and treat the answers as a bonus signal, never as coverage.
