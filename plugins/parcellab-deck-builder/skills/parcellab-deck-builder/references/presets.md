# Deck presets

Each preset lists the Master Sales Deck slide types to start from (by their
`data-label` value in `templates/sales-deck/index.html`) and any preset-specific
notes for Phase 2 (Outline) and Phase 3 (Pricing). These are starting points —
Gate 2 always lets the user add, drop, or reorder slides, and any preset may
draft a new slide type (see "New slide types" below).

## 1. Post-discovery recap
No commercials. Sent standalone, not presented live.

Slides: Cover, Big stat, Three pillars, Quote, Next steps.

- **Big stat**: lead with the single most striking Onyx/industry stat matching
  the customer's stated pain (not always the deck's default 68% stat).
- **Three pillars**: map to whichever 3 of parcelLab's 5 capability areas
  (Promise, Deliver, Return, Insights, Integrations) best match the call's
  pains. If more than 3 are relevant, that's a signal to draft a new
  five-capability slide instead of forcing a cut to 3.
- **Quote**: use a matched customer story from Onyx, not the deck's default
  Northbound Retail quote.

## 2. Demo-prep deck
Presented live with narration — built to support a presenter, not to be read
standalone. Only becomes a Demo follow-up if the customer asks to keep it
afterwards.

Slides: Cover, Agenda, Platform showcase, Three pillars, Table · Compare (only
if a competitor was named on the call), Next steps.

- **Agenda**: replace the default 6-topic agenda with the actual demo flow.
- **Table · Compare**: only include if Onyx returned competitive positioning
  for a named competitor; omit the slide entirely otherwise rather than
  filling it with a generic comparison.

## 3. Demo follow-up
Sent after the demo call. Recaps what was shown against what was asked.

Slides: Cover, Agenda (relabelled "What we covered"), Platform showcase, Proof
in numbers, Quote or Spotlight (whichever fits the story better), Table ·
Compare (if raised on the call), Next steps.

## 4. Business case / proposal
The only preset that reaches Phase 3 (Pricing). Sent to the buying committee.

Slides: Cover, Section 01, Big stat, Three pillars, Proof in numbers, Revenue
uplift, 6 Benefits, Rollout, Pricing, Contract summary, Team, Next steps.

- **Revenue uplift**: this slide's own "Assumption inputs" / "parcelLab
  benchmark inputs" panels are structurally what the pricing calculators
  compute — Gate 3's confirmed `rVol` figure feeds this slide's benchmark
  panel, not just the Pricing slide.
- **Pricing**: the only slide using the Gate 3 allowlisted fields (`rTotal`,
  `rRate`, `rTier`). Never built before Gate 3 is confirmed.
- **Contract summary**: only include if commercial terms (term length, start/
  end dates) were actually discussed — drop it rather than fabricate dates.

## 5. Exec summary
Short, senior audience. Sent standalone.

Slides: Cover, Big stat, Proof in numbers, Customers, Next steps.

## 6. Scoping deck
Technical/integration fit. Commonly needs a new slide type this system doesn't
have yet: a requirements-fit matrix (one row per integration requirement from
the call, a `StatusPill` per row showing Supported / Needs custom / Not
supported). Draft this live at Gate 2 using the brand tokens and `StatusPill`
component per the design system README's rules — don't force an existing
table layout to carry per-row status when a purpose-built layout is clearer.

Slides: Cover, Agenda, Platform showcase, Table · Zebra or Tables · Two-up
(carrier/technical coverage data), Table · Compare (if evaluating a named
competitor's tech), [new] Requirements-fit matrix.

## New slide types

When no existing slide type fits, draft one from `colors_and_type.css` and the
`components/core/` primitives (Button, StatusPill, Badge, Card), following the
brand rules in the design system's `README.md`: flat (no shadows), capsule
pills, Poppins only, sentence case, no emoji. Flag any new slide type
explicitly at Gate 2 — reusing the tokens correctly does not mean silent
approval.
