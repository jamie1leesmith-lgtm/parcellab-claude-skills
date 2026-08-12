# demo-environment — intake standardisation and unattended completion

**Date:** 2026-08-12
**Skill:** `plugins/pl-tools/skills/demo-environment/`
**Status:** approved, not yet implemented

## Goal

Two things, together:

1. **A standard interview.** The questions demo-environment asks are currently
   described in prose bullets across Phase 0 steps 2 and 4. Prose drifts — the
   wording, the order and the option sets vary run to run. They should be fixed.
2. **Zero manual input after the ✋ plan gate on a clean run.** Today three
   questions can still fire after the gate on a run where nothing went wrong:
   the Shopify store confirmation (before the gate, but avoidable), the Beat 1
   edit-mode restore offer, and the Beat 2 status-codes offer. Only genuine
   failures should require a human.

Net effect: one question added, two removed outright (CDC synthetic generation,
the Beat 1 restore offer), two made automatic or conditional (the Shopify store,
the Beat 2 status-codes offer) — and every surviving question is asked
identically every run.

## Changes

### 1. Canonical intake script

New file `references/intake-script.md` holding every intake question in fixed
order, each with verbatim wording and its fixed option set. Conditional
questions are marked with their condition.

Phase 0 steps 2 and 4 stop describing questions in prose and point at it:

> Ask the questions in `intake-script.md`, in that order, with that wording.
> Conditional questions are marked; skip them when the condition is false,
> never reorder the rest.

SKILL.md is already 601 lines; keeping the script in a reference file keeps
Phase 0 readable and makes wording drift visible in a single diff.

**Order (round 1, before the scrape agent is dispatched):**

| # | Question | Condition |
|---|---|---|
| 1 | Are returns in scope for this demo? | always |
| 2 | Is this a Shopify opp? | Q1 = yes |
| 3 | Reuse the pool scraped for \<brand\> on \<date\>, or scrape fresh? | a prior run dir with the same handle has both scrape files |

**Order (round 2, batched, concurrent with the scrape agent):**

| # | Question | Condition |
|---|---|---|
| 4 | Destination country | always |
| 5 | Order plan — count (1–5, default 3) + per-order fraud level and scenario | always |
| 6 | Pace — standard or fast | always |
| 7 | **Order extras** (see below) | always |
| 8 | CDC region and category | always |
| 9 | Target account — own demo account or parcelfashion | always |
| 10 | Using \<name\> (\<id\>) — correct? | always |
| 11 | Edit-mode fix offer | `edit-mode show` is not `account-restricted` for that account |
| 12 | Write-permission gaps | `permissions.allow` does not cover the run's writes |
| 13 | CDC config UUID | the target's config key is missing |
| 14 | Which Shopify store? | retain-shopify **and** 2+ stores authed |

### 2. New question — order extras (Gate C hoisted into intake)

order-lifecycle already defines **Gate C — order enrichment**
(`skills/order-lifecycle/SKILL.md:495`) as a menu with a fast exit, and its
orchestrated contract already reads `gates.order_lifecycle.gate_c` / `extras`
from the manifest (`skills/order-lifecycle/SKILL.md:646`). demo-environment's
manifest schema already reserves both fields. Nothing has ever populated them,
and `validate_manifest.py:131` only checks `gate_b_answered` — so the schema is
currently dead.

This change wires the existing gate into intake rather than inventing a new
field set. Asked once per run, applying to every order, verbatim:

> Anything else to add to every order, or send as-is?

followed by the Gate C table verbatim: promise dates · order financials ·
delivery detail · tags/custom fields · dynamic recipients · extra articles.
The default is send-as-is and skipping takes one word. Do **not** ask an open
"any other fields?" — that is unanswerable unless the user has the Order API
spec memorised.

Two deltas from standalone Gate C:

- **The `client_key` pre-fill clause is dropped.** It exists because standalone
  Gate B may introspect a journey that requires one. On an orchestrated run
  Gate B is answered by the manifest and no introspection happens, so nothing
  can be pre-filled.
- **Tags merge, they do not replace.** `prepare_fraud_fragment.py` already
  writes each order's top-level `tags` and `additional_attributes`. Extras
  chosen at intake are unioned with the fraud fragment's output per order;
  neither side overwrites the other. Without this rule the extras question
  silently discards the fraud data every order depends on.

**Scope is per-run, not per-order** — one answer merges into every order's
`create.json`. Promise dates are resolved to absolute `YYYY-MM-DD` at
manifest-write time.

Recorded in the manifest as:

```json
"gates": {
  "order_lifecycle": {
    "gate_b_answered": true,
    "gate_c": "send-as-is" | "extras",
    "extras": { }
  }
}
```

### 2a. Article weight — a new Gate C row

Weight is held at **article** level, not order level. Confirmed against the v4
Order API docs (`https://product-api.parcellab.com/v4/docs/markdown/order/`),
whose article schema carries:

| Field | Type | Notes |
|---|---|---|
| `weight` | number | "Weight of the article (in grams, kg, lbs, or oz)" |
| `weight_unit` | enum | `kg` \| `g` \| `lbs` \| `oz`, default `g` |

Because demo-environment reuses the Gate C menu verbatim, the field is added to
**order-lifecycle's Gate C table itself** as a new row, so standalone runs get
it too and there is still one source of truth:

| Extra | Fields | State this |
|---|---|---|
| Article physical data | `weight`, `weight_unit` on each article | Article-level, not order-level. Set at **both** levels — `articles_order` and every `add_tracking`'s `tracking.articles` — like every other article field. |

**Values are auto-derived, not asked.** Turning the row on generates a
plausible weight per article from its `product_type` (fashion ≈ 300 g,
electronics ≈ 1200 g, and so on), consistent with how the run already
synthesises customers and tracking numbers. Every derived value is listed
article-by-article in the ✋ gate summary so it can be objected to before
anything is sent. Unit is `g` unless the user says otherwise.

**snake_case only.** `weight` has no documented legacy camelCase twin, unlike
the `articleNo`/`articleName`/`articleImageUrl`/`articleCategory`/`price`
family that comm templates read. If a template ever renders weight blank, the
dual-family rule is the first thing to check — but do not pre-emptively invent
an `articleWeight` key.

**Dimensions (`width`, `height`, `length`, `length_unit`) are out of scope.**
The docs contradict themselves: `width`, `height` and `length` are all
described as millimetres, but `length_unit` is a `const` of `cm`. Until one
live order settles which is right, shipping them risks rendering a product's
size wrong by a factor of ten. Add them once proven.

### 3. Validator

`scripts/validate_manifest.py` gains, alongside the existing `gate_b_answered`
check:

- `gate_c` present and one of `"send-as-is"` / `"extras"`
- when `"extras"`, `extras` is a non-empty object
- any `announced_delivery_date`, `announced_delivery_date_min` or
  `announced_delivery_date_max` matches `^\d{4}-\d{2}-\d{2}$`
- when article weights are set, every `weight` is a number and every
  `weight_unit` is one of `kg` / `g` / `lbs` / `oz`

The date check catches a failure the Gate C table already documents — a full
ISO datetime is rejected by the API — before any write leaves the machine.

### 4. ✋ gate summary

Two additions to the plan proposed at Phase 0 step 8:

- **Every extra, field by field, with its actual value** — including each
  auto-derived article weight, listed per article. This carries over Gate C's
  own rule: an extra that was discussed but does not appear in the summary is a
  defect. A wrong promise date is invisible in the API's success response, and
  an auto-derived value the user never saw is worse than one they rejected.
- A fixed line `CDC synthetic generation: off`, so the setting stays visible
  and objectable without being a question.

### 5. Dropped questions

**CDC synthetic generation.** Never asked. `cdc.generate_orders` is written as
`false` and `cdc.orders` as `[]`, as constants. Removed from intake and from
Beat 1's report; survives only as the fixed gate line above.

**Shopify dev store.** Resolved without a question: read
`~/.claude/parcellab-shopify-seed.env`, else `shopify store auth list`.

| Stores found | Behaviour |
|---|---|
| exactly 1 | use it silently, state it at the ✋ gate |
| 0 | stop, point at `/pl-setup`'s Shopify CLI section |
| 2+ | ask — the only surviving case (question 14) |

`command -v shopify` and the location-GID resolution (shopify-seed Steps 1–2,
including the fulfils-online-orders preference rules) are unchanged.

### 6. Edit-mode guard — auto-restore

Beat 1's offer to restore the guard is deleted.

The restore happens **after Beat 2**, not at Beat 1. Beat 1 fires immediately
after Phase 3 while the order drivers are still pushing events — Beat 2 waits
≥15 minutes after the final event. Restoring the guard to the user's own
account at Beat 1 would point it away from the account those drivers are
writing to, and every remaining event push would hit the guard.

So: once Beat 2's verification is complete and every driver has exited, if the
guard was repointed for this run, restore it to the user's own account
unconditionally and state it in Beat 2 as a line of fact. **A failed restore is
reported explicitly** — never silently left pointing at the run's account.

### 7. Status codes — auto-record

Beat 2's offer to record newly-proven events and chains in
`skills/order-lifecycle/references/status-codes.md` becomes automatic. Beat 2
writes them and reports what it recorded.

Note this means a demo run edits a skill reference file as a side effect. That
is accepted deliberately: the alternative is that proven status codes keep
being re-labelled unproven because nobody answered a prompt at the end of a
fifteen-minute run.

## Out of scope

- The publish-gate three-way offer and the seed re-run offer stay as they are.
  Both fire only on failure, which is exactly when a human should be asked.
- Article dimensions (`width`, `height`, `length`) — deferred until the
  millimetre/centimetre contradiction is settled live.
- No change to the order engines, the run page, or telemetry.

## Files touched

| File | Change |
|---|---|
| `skills/demo-environment/references/intake-script.md` | new — canonical question script |
| `skills/demo-environment/SKILL.md` | Phase 0 steps 2/4 point at the script; step 4 loses the Shopify-store and CDC-generation questions; step 8 gains the extras (incl. per-article weights) and generation lines; Beat 1 loses the restore offer; Beat 2 gains auto-restore and auto-record |
| `skills/order-lifecycle/SKILL.md` | Gate C table gains the "Article physical data" row |
| `skills/order-lifecycle/references/status-codes.md` | now written to automatically by Beat 2 |
| `scripts/validate_manifest.py` | gate_c, extras, promise-date-format and weight_unit-enum checks |
| `scripts/tests/` | unit tests for the new validator checks |
