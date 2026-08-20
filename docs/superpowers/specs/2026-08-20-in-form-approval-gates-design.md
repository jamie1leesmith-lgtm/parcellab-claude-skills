# In-form approval gates — design

**Date:** 2026-08-20
**Skill:** `pl-tools/demo-environment`
**Status:** approved design, not yet implemented

## Problem

A `demo-environment` run has two hard gates: ★ (approve the branded template)
and ✋ (approve the plan). Both are answered in chat today, and both are worse
there than they need to be:

- **The template gate asks about something the operator cannot see in chat.**
  The preview lives in a separate Browser pane tab served by a second server on
  port 8098. Approving a design means looking somewhere else and trusting that
  the thing on screen is the thing being approved.
- **The plan gate pastes a wall of detail into chat.** `SKILL.md` already says
  the plan is shown on the run page and chat carries only a short
  approve-or-change question — but the page has **no plan concept at all**.
  `GET /state` returns `phase, run_id, account_name, path, finished,
  updated_at, mode, lanes, orders, schedule, failures, detail` and nothing
  else. Live on 2026-08-19 this forced the documented no-server fallback (a
  markdown table in chat) on a run where the server was healthy, and the
  deviation was logged as `instruction_unfollowable`.

So one gate asks about an artifact it cannot show, and the other documents a UI
that was never built.

## Goal

Move both decisions onto the run page: a scaled template preview and a full plan
card, each with approve / request-changes controls. Chat keeps exactly one line
per gate — what is waiting, and the link.

Non-goal: eliminating chat. See *Rejection* below.

## Approach

Reuse the intake handshake unchanged. It is already the proven, tested contract
for page-to-conductor input: `POST /submit` validates, atomically writes
`intake.json`, and the conductor polls for the file's existence. Approvals become
two more sentinel files.

Two alternatives were considered and rejected:

- **A dedicated "Review" phase** between Building and Live. Visually tidier but
  wrong about the domain: the gates *interleave* with building rather than
  following it — the template gate can open while the scrape lane is still
  finishing, and the plan gate sits before orders start. A separate phase
  implies a sequence that does not exist, and it would hide lane progress at
  the moment the operator is deciding.
- **WebSocket or long-poll** for instant handoff. A whole transport to save
  about two seconds on a click that the existing 2s poll already makes feel
  immediate.

## 1. Data flow

```
conductor                     run_server                    page
    │  mark(gate,template,asked) ──► run-state.json
    │                                     │
    │                          GET /state ◄── poll (2s)
    │                          gates.template = "open" ──►  renders gate card
    │                                                             │
    │                          POST /approve/template ◄───── click
    │                                     │
    │                          writes template-approval.json
    │  ◄── until [ -f … ] sees the file
    │  mark(gate,template,answered)
```

### Gate state is derived, never stored

`state_payload.build()` gains a `gates` key computed by walking the existing
`timeline` for entries with `kind == "gate"`:

| Timeline for that gate name | `gates.<name>` |
|---|---|
| no entries | `"pending"` |
| `asked`, no later `answered` | `"open"` |
| `asked` then `answered` | `"answered"` |
| `asked`, `answered`, `asked` again (re-ask) | `"open"` |

Derivation, not a new stored field, for two reasons. The marks the conductor
already makes become the trigger, so no new bookkeeping can be forgotten — the
exact failure that left every lane pill on "pending" for weeks because
`SKILL.md` documented `mark` but the pills read `set_lane`. And a single source
of truth cannot disagree with itself about whether a gate is open.

Because the derivation is last-mark-wins, re-asking a gate works for free:
delete the approval file, `mark(asked)` again, and the card returns.

This also enforces, for free, the ordering rule `SKILL.md` already depends on:
the plan must not be visible before the plan gate opens. `demo-manifest.json`
exists from Phase 0 step 7 — before the ★ template gate — so a card keyed on
"is the manifest readable" would leak the whole plan while the operator is still
being asked about the template. Keying on `gates.plan === "open"` means the plan
appears when the gate opens and not one poll earlier, which is what the skill
means by "ordering is enforced by the timeline, not by which files happen to
exist".

### The approval files

```json
{"decision": "approved", "note": null, "at": "2026-08-20T08:14:02Z"}
```

```json
{"decision": "changes_requested",
 "note": "footer address should be the UK entity",
 "at": "2026-08-20T08:14:02Z"}
```

Written with the same unique-temp-file (`pid` + thread id) plus atomic
`replace()` as `intake.json`, so a poller can never observe a torn document and
two concurrent posts cannot interleave.

## 2. Server changes — `run_server.py`

| Route | Behaviour |
|---|---|
| `POST /approve/template` | validate → write `template-approval.json` → `{"ok": true}` |
| `POST /approve/plan` | validate → write `plan-approval.json` → `{"ok": true}` |
| `GET /template.html` | serve `<run dir>/template-preview.html`; 404 when absent |

`_post` currently hard-codes one path comparison. It becomes a small route
table with the intake branch moved into it **unchanged**, so its existing tested
behaviour is untouched.

`GET /template.html` reads a fixed filename inside the run dir. It takes no path
parameter of any kind, so there is no traversal surface to defend.

### Validation — `approval_schema.py`

A new module mirroring `intake_schema`, deliberately tiny:

- `decision` must be exactly `"approved"` or `"changes_requested"`
- `note` must be absent, `null`, or a string of at most 2000 characters
- **`note` is required and non-empty when `decision` is `changes_requested`** —
  a rejection with no reason forces the chat round-trip this feature exists to
  avoid
- unknown top-level keys rejected. Note this is *stricter* than
  `intake_schema`, which rejects unknown keys only inside `extras` and merely
  checks for required keys at the top level. Cheap to be strict on a two-key
  schema, and it means a typo'd field fails loudly instead of being ignored.

A post to a gate that is not currently `open` returns **409**, so a stale
browser tab cannot approve something twice or answer a gate that was already
resolved in chat via the fallback.

The 409 check means the POST handler needs to know whether the gate is open, so
the derivation in §1 must live in **one** function that both `state_payload.build()`
and the handler call — not two implementations of the same table. It goes in
`state_payload` as a module-level helper (`gate_states(state)`), since that is
where the timeline is already interpreted, and `run_server` imports it. Two
copies of this logic drifting apart would let the page show a gate as open that
the server would then reject.

## 3. Page changes — `run_app_template.html`

One shared gate-card component renders at the top of the building section —
above the lane pills, so it is the first thing on screen — whenever
`gates.<name> === "open"`. Only the body differs between the two gates.

**Template gate.** The `GET /template.html` iframe at `transform: scale(0.5)`
with `transform-origin: top left` inside a clipped, fixed-height container, so
the whole email is visible at a glance; an "open full size ↗" link opens the
same URL in a new tab for true fidelity. Then `[ Approve & continue ]` and
`[ Request changes ]`.

The preview is a **copy inside the run dir**, not an iframe pointed at the
`layout-preview` server on port 8098. The run page must not depend on a second
server being alive: port 8098 collided with another session's server during
development of this very change, and `run_server` otherwise serves nothing
outside the run dir.

**Plan gate.** The plan card, §4.

**Interaction.** `[ Request changes ]` reveals a note textarea and a send
button; send is disabled until the note is non-empty, matching the schema rule.
On submit both buttons disable and the card shows "sent"; the next poll flips
the gate to `answered` and the card disappears. A non-2xx re-enables the buttons
and shows the error inline, exactly as the intake form does on a 400.

## 4. The plan card's contents

Rendered from `demo-manifest.json`, which `state_payload` already loads. Contents
are taken from the `SKILL.md` plan-gate spec verbatim:

- the core 4, each with product type and price
- per-order product distribution
- the order / scenario / fraud matrix, one row per shipment, with the expected
  comm per event and a confidence label (unproven items marked)
- CDC region, category and config source, plus the fixed line
  `CDC synthetic generation: off`
- every extra agreed at intake, **field by field with its actual value**,
  including each auto-derived article weight listed per article
- the account by name

The field-by-field rule is why this card cannot be a summary. `SKILL.md`'s own
reasoning is that an auto-derived value the operator never saw is worse than one
they rejected, and the B&O run of 2026-08-19 is the live example: `brand.category`
resolved to `Fashion` for a premium audio brand (`infer_category` has no keyword
for "Speaker", so five speaker products outvoted four headphone matches) and was
corrected to `Electronics` only because it was on screen to be read.

## 5. Conductor changes — `SKILL.md`

Phase 0 step 8 (★) and step 9 (✋) change from "ask in chat" to:

1. copy the built template to `<run dir>/template-preview.html` (★ only)
2. `mark(d, "gate", "<name>", "asked")`
3. post **one** chat line: what is waiting, plus `run.page_url`
4. wait for `<run dir>/<name>-approval.json` with an `until [ -f … ]` tracked
   background task — the same mechanism already used for `intake.json`
5. read the decision:
   - `approved` → `mark(…, "answered")`, stamp the approval, continue
   - `changes_requested` → pick the note up in chat, iterate, delete the
     approval file, re-`mark(asked)`, and log `add_deviation(gate_reasked)`

Step 3 is why this is not zero-chat. A conductor that goes silent while waiting
on a page the operator is not looking at produces a run that stalls invisibly —
the same class of failure as the un-armed Beat 2 that left a finished
environment unverified for 19 minutes on 2026-08-12.

`validate_manifest.py --pre-gate` stays exactly where it is, before the gate, so
a schema error still surfaces before the operator is asked anything.

**Auto mode** writes both approval files itself and never opens a page gate. The
`asked`/`answered` marks still fire in immediate succession, so the timeline and
all derived telemetry are indistinguishable from a fast human yes.

**Fallback.** If the server is not running, both gates fall back to chat exactly
as today, including the plan-as-markdown-table. The page has never been
load-bearing and this change does not make it so.

## 6. Testing

| Unit | Cases |
|---|---|
| `approval_schema` | both decisions; missing/empty note on `changes_requested`; note over 2000 chars; bad decision literal; unknown key |
| `run_server` | all three routes; 409 posting to a gate that is not open; 404 for a missing preview file; intake route still behaves identically after the route-table refactor |
| `state_payload` | `gate_states` for pending / open / answered, and asked-answered-asked → open; plan gate still `pending` when the manifest exists but the gate has not been asked |
| page JS | driven against a real run dir with a gate marked open, as items 1–4 were verified |

The `run_server` tests follow `test_run_server.py`'s existing in-process pattern
(`make_server` on port 0), so no test binds a fixed port.

## 7. Out of scope

- **No auth.** Localhost only, same as the intake form today.
- **No per-order approval.** One decision covers the whole plan, per
  `SKILL.md`'s existing "one explicit yes covers all of it".
- **The rejection loop iterates in chat**, not on the page. Describing a design
  change is conversational by nature; forcing it through a textarea would take
  more rounds, not fewer.
- **No change to the `--pre-gate` validation split**, the telemetry schema, or
  any lane.
