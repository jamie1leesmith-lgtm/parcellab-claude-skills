---
name: parcellab-deck-builder
description: Build a customer-facing, on-brand deck from a Gong call (or direct input if none exists) plus Onyx research, assembled from the Deck Builder design system and pushed into a shared Claude Design project under a per-customer folder. Use for phrases like "build a deck for [customer]", "put together a business case for [customer]", "make me a demo deck for [customer]", "scoping deck for [customer]".
---

# parcelLab — Deck Builder

Turn a customer conversation into a customer-facing, on-brand deck: source
material from Gong (or the user directly) and Onyx, assemble an outline from
the Deck Builder design system, optionally fold in user-confirmed pricing,
and build the result inside a per-customer folder in the shared Claude
Design project.

Deck Builder (`claude.ai/design` project `12117415-e8b6-4e02-a3ef-f9f3498d65b6`)
is **read-only** — it is the blueprint, never a write target. Decks are pushed
into a separate, shared **Project** (not a design system) — `claude.ai/design`
project `c6f23cde-c20a-4916-a8b3-468df1929762` ("Customer decks project") —
under `decks/<customer>/<preset>-<date>/`. Never call `DesignSync
create_project` for this: it only creates `PROJECT_TYPE_DESIGN_SYSTEM`
objects, a different, wrong entity type. There is no tool that creates a
plain Project — if this shared project is ever lost or invalid, tell the
user; a human must create its replacement via the claude.ai UI and share its
`/p/<uuid>` link back.

## Workflow

1. **Identify the customer/deal** and, if not already stated, ask which
   preset (see `references/presets.md`) — or confirm a blend.
2. **Phase 1 — Sources** (below). **Gate 1.**
3. **Phase 2 — Outline** (below). **Gate 2.**
4. **Phase 3 — Pricing**, only for the business-case preset (below). **Gate 3.**
5. **Phase 4 — Build** (below).

## Phase 1 — Sources

- Run `gong-sync` for the named customer/deal.
- **No call found:** this is a normal path, not an error. Ask the user
  directly for the target pains, what's been discussed, and any quotes or
  requirements they already have. Proceed identically from here regardless
  of which source produced the material.
- For each pain/topic identified, run `onyx-ask` scoped to that specific
  topic (never a generic "tell me about parcelLab" query) across the four
  angles this skill covers: product feature/capability detail, customer
  stories, competitive positioning (only if a competitor was named),
  integration/technical fit.
- **Gate 1:** present the assembled brief — each pain/topic with its matched
  Onyx facts and citations. If Onyx returned nothing relevant for a topic,
  show that gap explicitly rather than omitting it silently. Write the
  approved brief to `decks/<customer>/<preset>-<date>/brief.md`. Wait for
  approval before Phase 2.

## Phase 2 — Outline

- Look up the preset's starting slide list in `references/presets.md`.
- Map brief content onto those slide types. Where nothing fits, draft a new
  slide type per `references/presets.md`'s "New slide types" section.
- **Gate 2:** present the slide list — each slide's type, key message, and
  source (which Onyx fact or Gong quote it's drawn from) — and any new slide
  type flagged explicitly. Wait for approval before rendering anything.

## Phase 3 — Pricing (business-case preset only)

- Follow `references/pricing-fields.md` exactly: the user drives the
  relevant calculator themselves; only the allowlisted fields (`rTotal`,
  `rRate`, `rTier`, `rVol`) are ever read back, never the verdict panel.
- **Gate 3:** show the exact figures read back and wait for explicit
  confirmation before placing them on the Pricing / Revenue-uplift slides.
  This gate is separate from Gate 2 — approving that a pricing slide will
  exist is not approving the numbers on it.

## Phase 4 — Build

1. **Resolve the Deck Builder cache.** If `deck-builder-cache/` doesn't
   exist, bootstrap it: `DesignSync list_files` on the Deck Builder project,
   `get_file` for `templates/sales-deck/{deck.css,ds-base.js,deck-stage.js}`
   and the `assets/logo_horizontal*.svg` + only the `assets/customer_logos/*`
   this deck actually uses. **Do not fetch `colors_and_type.css`,
   `_ds_bundle.js`, or `fonts/*`** — the shared project already has these via
   claude.ai's own design-system binding (see step 3). Save the **full**
   `list_files` path list (every path in the project, not just what was just
   fetched) to `deck-builder-cache/.manifest` — `cache-diff.sh` compares this
   manifest against a future fresh `list_files` call, so it must reflect the
   whole project or every refresh will report spurious `ADDED` lines for
   everything this bootstrap didn't fetch. If it does exist and a refresh is
   requested, run a fresh `list_files`, save both the old manifest and fresh
   path list to temporary files, then invoke `references/cache-diff.sh
   <old-manifest-path> <fresh-list-path>` (two file-path arguments); re-fetch
   only files marked `ADDED`.
2. **Check the shared project's `assets/` folder.** `DesignSync list_files`
   on `c6f23cde-c20a-4916-a8b3-468df1929762`. If `assets/logo_horizontal.svg`
   (or `_white`, if this deck needs it on a dark slide) isn't already
   present, it'll be pushed in step 4 — otherwise skip it, it's shared across
   every customer's decks and never needs re-pushing.
3. **Assemble the deck locally** in `decks/<customer>/<preset>-<date>/`,
   built from the cached blueprint: copy `deck.css` and `deck-stage.js` from
   the cache into that folder unchanged. Write `ds-base.js` with its `base`
   line set to exactly `../../../_ds/deck-builder-12117415-e8b6-4e02-a3ef-f9f3498d65b6`
   — three `..` (this deck's folder is 3 levels below the shared project's
   root) then into the platform's own design-system-binding folder, which
   already holds `colors_and_type.css`, `_ds_bundle.js`, and the fonts. Write
   `index.html` with the outlined slides (each a `<section class="slide
   ...">` per the approved Gate 2 outline); any reference to a shared asset
   (e.g. the logo) uses `../../../assets/...` (3 up, same reasoning).
4. **Push.** `DesignSync finalize_plan` against
   `c6f23cde-c20a-4916-a8b3-468df1929762`, writes covering
   `decks/<customer>/<preset>-<date>/{index.html,deck.css,ds-base.js,
   deck-stage.js}` (all four — omitting `ds-base.js`/`deck-stage.js` produces
   a deck with no tokens, no fonts, and no working `<deck-stage>` component)
   plus `assets/logo_horizontal*.svg` only if step 2 found it missing. Then
   `write_files`.
5. Tell the user the deck is live in the shared "Customer decks project",
   under `decks/<customer>/<preset>-<date>/`, and that further edits happen
   there directly — this skill's job ends at the initial build.

## Confirmation gates

- **Gate 1:** the sourced brief (Gong or manual + Onyx), before any slide
  decisions are made.
- **Gate 2:** the slide outline (type, message, source per slide; new slide
  types flagged), before anything renders.
- **Gate 3:** business-case preset only — the exact pricing figures, before
  they're placed on a slide.

## Failure modes

- **No Gong call for the customer** → prompt for manual context (Phase 1);
  never blocks.
- **Onyx returns nothing relevant for a topic** → shown as an explicit gap at
  Gate 1, not papered over.
- **Deck Builder read fails, or a write conflict (409) on the shared
  project** → re-read and merge; never `force` without asking the user.
- **The shared project id (`c6f23cde-c20a-4916-a8b3-468df1929762`) is
  invalid or inaccessible** → stop and tell the user. No tool available to
  this skill can create its replacement (only `PROJECT_TYPE_DESIGN_SYSTEM`
  is creatable, which is the wrong entity type) — a human must create a new
  Project via the claude.ai UI and share its `/p/<uuid>` link back.
- **A new slide type doesn't clearly match the brand rules** → flagged at
  Gate 2 for explicit sign-off, not assumed acceptable.
- **Pricing extraction** must use the allowlist in `references/pricing-fields.md`
  exactly — this is a correctness requirement (the internal/customer
  boundary), not just an implementation detail.
