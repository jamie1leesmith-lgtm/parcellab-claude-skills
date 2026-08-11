# Run telemetry

Every run deposits one row in a shared Notion database, so defects are found by
query across users instead of by anecdote.

## One-time setup (the database owner)

Create a Notion **database, table view**, then share it with the team. Columns,
exactly:

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
| Deviations | Multi-select | validator_rejected · api_error · retry_needed · gate_reasked · comm_missing · lane_fallback_inline · manual_intervention · instruction_unfollowable · workaround_invented |
| Error detail | Text | |
| Issue key | Text | |
| Triage status | Select | Untriaged · Reviewed, no action · Fix planned · Fix shipped · Can't reproduce |
| Reviewed at | Date | |
| Reviewed by | Text | |
| Action taken | Text | |
| Fix commit | URL | |
| Verified in run | Text | |

Then give every teammate the database id to set as `PL_RUN_TELEMETRY_DB` during
`/pl-setup`.

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
- **`PL_RUN_TELEMETRY_DB` unset means no telemetry, silently.** Enabling it at
  setup is the opt-in, per person. Never prompt mid-run.
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
