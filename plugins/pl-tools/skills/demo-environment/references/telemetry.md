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
| Duration to build | Number | |
| Total elapsed | Number | minutes, derived |
| Measured working time | Number | minutes, union of all measured intervals |
| Waiting on user | Number | minutes, union of gate ask→answer |
| Unattributed | Number | minutes, total minus everything covered |
| Event window | Number | minutes, first driver start → last driver end |
| Slowest lane | Text | |
| Timeline | Text | the run's timeline as JSON |
| Deviations | Multi-select | validator_rejected · api_error · retry_needed · gate_reasked · comm_missing · lane_fallback_inline · manual_intervention · instruction_unfollowable · workaround_invented |
| Error detail | Text | |
| Issue key | Text | |
| Triage status | Select | Untriaged · Reviewed - no action · Fix planned · Fix shipped · Can't reproduce |
| Reviewed at | Date | |
| Reviewed by | Text | |
| Action taken | Text | |
| Fix commit | URL | |
| Verified in run | Text | |

### Reading the timing columns

**They are not additive.** A gate can overlap measured work — the scrape agent
runs during the intake interview — so `Total` minus `Measured` minus `Waiting`
double-subtracts. `Unattributed` is computed from a single union across every
interval; `Waiting on user` is an overlapping view of the same timeline.

**`Unattributed` is not user think-time.** It is everything not yet
instrumented. On the run this was designed from it would have been ~37 minutes,
almost all of it the conductor fixing defects rather than the user thinking. It
shrinks as instrumentation improves, so a large value is a signal worth reading.

**`Event window` is concurrent.** Drivers run in parallel, so the window is the
longest single order, never the sum of every event. The live run's window was
15.2 minutes; multiplying 12 events by the 200 s gap suggests 40 and is wrong.

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

**Why the row is created at gate approval, not at the end.** If it were written
only on completion, every run that died would never appear, and the table would
systematically over-represent success — hiding exactly the failures it exists to
surface. A stalled run leaves a row with no Beat 2, which is the signal.

## Rules

- **Never write the triage columns from a run.** They belong to review. A run
  that could write them could also silently destroy them.
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
