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
| Path | Select | retain · retain-shopify (`engage` retired 2026-08-18 — the Notion column may still list it as a legacy option; new runs never write it) |
| Account | Number | |
| Skill version | Text | |
| Run page | URL | |
| Mode | Select | babysit · auto — read straight from the manifest's `run.mode` (absent means babysit) |
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
| Page publishes | Number | stays `0` by design — see "Reading the page columns" below |
| Page renders | Number | stays `0` by design — see "Reading the page columns" below |
| Max page gap | Number | stays null by design — no publish events exist to measure a gap between |
| Page URL changes | Number | stays `0` by design — see "Reading the page columns" below |
| Page cadence | Text | stays empty by design — no publish events exist to record an offset for |
| Largest gap | Number | minutes; the longest stretch covered by no instrumented span. Null when fewer than two stamps |
| Largest gap after | Text | the mark that gap follows, e.g. `orders:end` |
| Deviations | Multi-select | validator_rejected · api_error · retry_needed · gate_reasked · comm_missing · lane_fallback_inline · manual_intervention · instruction_unfollowable · workaround_invented — derived from `run_state.add_deviation()` calls logged live through the run (see SKILL.md's *Deviation logging*), unioned with a few mechanical signals (failed lanes, inline fallbacks) |
| Deviation notes | Text | one line per logged deviation, `<at> <category>: <detail>`, same 1900-char cap and oldest-drop convention as `Timeline` — the free-text detail behind each `Deviations` entry |
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
one that republished twelve times left identical rows. That was a real gap
when the run page was a conductor-rendered, conductor-published Artifact —
`Page publishes`, `Page renders`, `Page URL changes`, `Max page gap`, and
`Page cadence` all existed to catch a conductor that recorded a fact in
`run-state.json` and then skipped the separate render-and-publish step that
used to be required to show it.

**The run page is now served live by `run_server.py`** (see SKILL.md's "The
run page"): it polls `GET /state` itself every two seconds and there is no
render call, no publish call, and no second URL to drift to — `run.page_url`
is written once and never changes. Nothing in SKILL.md calls
`run_state.record_publish()` or `record_render()` any more, so these five
columns stay at their empty defaults (`0` or null) on every run from here
forward. A nonzero value in one of them would mean some code path is still
calling one of those two functions, which is a fact worth checking in the
code that produced the row, not a sign of a more current page — the run
page's freshness is no longer something these columns measure at all.

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
- **Deviations are logged live now, not reconstructed at Beat 2.**
  `manual_intervention`, `instruction_unfollowable`, `workaround_invented`, and
  every other category still depend on the conductor noticing its own
  variances — that has not changed — but noticing no longer has to survive
  until the end of a fifteen-minute run. SKILL.md's *Deviation logging*
  section calls for `add_deviation()` the moment a variance is noticed, at
  each of the specific points already named in this skill (a validator
  retry, a re-asked gate, an inline fallback, a caught API error, a comm
  still missing after the second look). Beat 2's three closed questions —
  "did any instruction fail to work as written? which line?" rather than an
  open "did anything go wrong?" — are now a backstop review of that log, not
  its only source. Live 2026-08-11 a conductor launched drivers with `nohup`
  against the skill's intent and did not notice until the user asked; that
  case is exactly what logging inline, rather than waiting for Beat 2's
  memory to hold it, is meant to catch.
