# demo-environment — front-loaded intake questionnaire + parcelLab branding

Date: 2026-08-19
Status: approved for planning

> **Superseded** by `2026-08-19-demo-environment-unified-intake-progress-design.md`.
> Its Artifact-based transport (publish the questionnaire, poll the DOM for a
> submitted banner, extract JSON) cannot work: the Browser pane has no
> claude.ai session, so the published page shows a sign-in screen. Kept for
> the reasoning behind front-loading intake and the parcelLab branding, both
> of which the superseding spec carries forward.

## Problem

Today's `pl-tools:demo-environment` intake is a sequential chat interview
spread across two rounds (`references/intake-script.md`): Round 1 (path +
reuse) blocks the scrape agent's dispatch, Round 2 (order matrix, extras,
category, account checks) runs concurrently with the scrape. "Auto mode" is
a scattered set of per-question special cases layered on top — some
questions auto-resolve, some stay live, and which is which is encoded
independently in both `SKILL.md` and `intake-script.md`.

This doesn't scale. As the skill grows to cover more product surfaces
(e.g. returns portal setup), each addition means more questions dropped
into the same sequential chat interview, and more per-question auto/manual
special-casing.

## Goals

- Replace the sequential chat interview with a single up-front
  questionnaire the operator fills out once, before anything else happens.
- Collapse "auto mode" down to one effect: whether the two hard gates (★
  template, ✋ plan) still pause for a chat yes. Every question gets
  answered by the questionnaire regardless of mode.
- Make the questionnaire and the run-page artifact look like a real
  parcelLab internal tool (brand colors, font, logo) rather than
  generic/neutral styling, since this is meant to be adopted broadly.

## Non-goals

- No change to Phase 1–4 (template push, orders, CDC, reporting) beyond
  what falls out of intake changes.
- No change to the underlying manifest schema — the questionnaire answers
  land in exactly the fields Round 1/2 already write today.
- Not building the returns-portal question set itself — this spec only
  makes room for it to be added to the same questionnaire mechanism later.

## Design

### Intake flow

Phase 0 gains a new step between "create the run directory" and "dispatch
the scrape agent": render and publish a single-page questionnaire Artifact,
open it in the Browser pane, wait for the operator to fill it out and
submit, then read the answers back out of the page. Nothing is dispatched —
no scrape, no agent — until the whole questionnaire is submitted.

This trades away today's "scrape runs while Round 2 is still being
answered" overlap in exchange for a simpler mental model (fill in one form,
then it runs) — a deliberate choice, made explicit here because it's a real
regression in wall-clock time for a full interview, not a free win.

**Questionnaire contents**, replacing Round 1 + Round 2 of
`intake-script.md`:

| Field | Source today | Notes |
|---|---|---|
| Shopify opp? (Q1) | Round 1 | Always asked, unconditional |
| Reuse prior scrape pool? (Q2) | Round 1 | Shown only when a candidate pool exists for this handle |
| Order matrix (Q3) | Round 2 | Pre-filled with the existing default matrix, editable |
| Gate C extras (Q4) + article-weight follow-up | Round 2 | Menu + conditional per-article weight fields |
| **Mode: manual / auto** | today's trigger-phrase detection | New — an explicit field, not inferred from the invoking message's wording |

**Dropped as a question, always silently resolved:** category (today's
Q5). It moves into the same "resolved once `scrape/product-pool.json`
exists, in every mode" bucket that destination country, brand region, and
pace already occupy — `resolve_auto_defaults.py`'s existing
`infer_category` output becomes the value in every run, babysit or auto,
with no live question and no form field. This mirrors the exact pattern
`intake-script.md`'s "Questions this script deliberately does not
contain" table already documents for those three fields.

**Stays outside the questionnaire, unchanged in mechanism:** Q6 (edit-mode
guard), Q7 (write permissions), Q8 (Shopify store choice, when 2+ stores).
These are pre-flight state checks and blockers, not creative choices, and
two of them depend on the path answer from the questionnaire — they run
immediately after submission, in the same place Phase 0 step 4 runs them
today, and still hard-stop as blockers exactly as now.

**Mode's only effect**: unchanged from today's "Both hard gates are
auto-approved in auto mode" behavior at ★ and ✋. Nothing else in the run
reads `run.mode`. All of today's per-question auto-resolution logic for Q2
and Q5 in `SKILL.md` and `intake-script.md` is deleted — there is nothing
left for it to do once every question is answered by the questionnaire in
both modes.

### Data flow

The questionnaire is a self-contained Artifact (own palette, no external
requests except the Google Fonts exception below). On submit, the page
renders the collected answers as JSON into a hidden element (or exposes
them as a global) and shows a visible "submitted" state. Claude polls the
page after asking the operator to fill it in, extracts the JSON via
`read_page` / `javascript_tool` once present, and writes the values
straight into the manifest fields Round 1/2 already write today — no new
manifest shape.

A malformed or incomplete submission (a required field missing) re-prompts
on the same page; it never silently falls through.

### Fallback

If the Artifact fails to publish, or the Browser pane can't open it, fall
back to today's plain chat Round 1/2 questions (mode is then asked as a
plain question too, since there's no form to carry it). This matches the
run page's own "publishing is never load-bearing" posture — a UI failure
degrades to something plainer, never blocks the run.

### parcelLab branding

A new static reference, `plugins/pl-tools/skills/demo-environment/references/pl_brand.py`
(or `.json`), holds parcelLab's own brand tokens — unlike a customer's
brand tokens (scraped fresh per run because the customer's site changes),
parcelLab's identity doesn't change per-run, so this is authored once
rather than scraped:

- Primary/accent: `#3E39D3`
- Text: `#1A1A1A`
- Light tint: `#F1F1FC`
- Card background: `#F5F5F5`
- Font: Poppins (via Google Fonts — the one external host an Artifact's
  CSP allows)
- Logo: the parcelLab wordmark SVG, single-color, with its `fill="black"`
  swapped to `fill="currentColor"` so it follows the page's theme instead
  of needing separate light/dark asset variants

Both the questionnaire Artifact and `render_run_page.py` import from this
one file, so a future re-brand touches one place, not two.

- **Questionnaire**: built with these tokens from scratch — Poppins,
  `#3E39D3` for primary actions/focus states, the logo in the header,
  light/dark handled the normal Artifact way (tokens on `:root`, dark
  overrides guarded per the usual pattern).
- **Run page**: `render_run_page.py`'s existing `CSS` constant (currently
  generic system-ui, black-on-white) gets its color and font tokens
  replaced with `pl_brand`'s values, and the header gains the logo. Same
  states, same structure, same tests — a restyle, not a rebuild.
- **Exception, by design**: the auto-mode banner keeps its current orange
  gradient (`#ff6b35`→`#f7931e`) rather than moving to the brand palette.
  It's a deliberate off-brand choice — the banner exists specifically to
  visually jump out as "this ran unattended," and warm/urgent colors serve
  that better than the brand indigo would.

## Testing

- The JSON-answers → manifest-fields mapping is pure and unit-testable
  the same way the rest of `validate_manifest.py`'s inputs are.
- `render_run_page.py`'s restyle is covered by its existing test suite
  (`test_render_run_page.py`) — states and structure are unchanged, only
  CSS values move, so no new test states are needed, just a check that the
  brand tokens actually appear in rendered output.
- The questionnaire Artifact itself gets a manual smoke test (open it,
  fill it out, confirm the extracted JSON matches expectations) rather
  than an automated one — consistent with how the ★ template preview is
  already verified today.

## Open items for the implementation plan

- Exact JSON extraction mechanism (hidden `<pre>` element vs. a
  `window.__answers` global) — an implementation detail, not a design
  decision, left to planning.
- Whether the questionnaire's default order matrix and Gate C menu are
  rendered as real interactive form controls or a simpler
  accept-defaults-or-type-overrides layout — a UI detail for the
  implementation plan, not this spec.
