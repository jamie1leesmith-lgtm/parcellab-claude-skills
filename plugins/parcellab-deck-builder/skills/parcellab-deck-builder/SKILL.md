---
name: parcellab-deck-builder
description: Build a customer-facing, on-brand deck from a Gong call (or direct input if none exists) plus Onyx research, assembled from the Deck Builder design system and pushed to a per-customer Claude Design project. Use for phrases like "build a deck for [customer]", "put together a business case for [customer]", "make me a demo deck for [customer]", "scoping deck for [customer]".
---

# parcelLab — Deck Builder

Turn a customer conversation into a customer-facing, on-brand deck: source
material from Gong (or the user directly) and Onyx, assemble an outline from
the Deck Builder design system, optionally fold in user-confirmed pricing,
and build the result in the customer's own Claude Design project.

Deck Builder (`claude.ai/design` project `12117415-e8b6-4e02-a3ef-f9f3498d65b6`)
is **read-only** — it is the blueprint, never a write target.

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
   `get_file` for `colors_and_type.css`, `_ds_bundle.js`, `fonts/*`,
   `templates/sales-deck/{deck.css,ds-base.js,deck-stage.js}`, and the
   `assets/logo_horizontal*.svg` + only the `assets/customer_logos/*` this
   deck actually uses. Save the fetched path list to
   `deck-builder-cache/.manifest`. If it does exist and a refresh is
   requested, run a fresh `list_files`, save both the old manifest and fresh
   path list to temporary files, then invoke `references/cache-diff.sh
   <old-manifest-path> <fresh-list-path>` (two file-path arguments); re-fetch
   only files marked `ADDED`.
2. **Resolve the customer's Claude Design project.** Call `DesignSync
   list_projects`, format the writable design-system projects as TSV
   (`id<TAB>name`), and invoke `references/match-customer-project.sh
   <customer-name>` with the TSV as stdin:
   - `REUSE <id>` → use that project.
   - `CREATE` → `DesignSync create_project` with the customer name.
   - `AMBIGUOUS <id1>,<id2>,...` → ask the user which project to use.
3. **Assemble the deck locally** in `decks/<customer>/<preset>-<date>/`,
   built from the cached blueprint: copy `deck.css`, `ds-base.js`,
   `deck-stage.js` into that folder, write the outlined slides into
   `index.html` (each a `<section class="slide ...">` per the approved
   Gate 2 outline), reusing the cached tokens/fonts/assets two directories
   up (the `base = '../..'` contract — see Global Constraints in the plan
   this skill was built from).
4. **Push.** `DesignSync finalize_plan` with the customer project id, writes
   covering the project root (tokens/fonts/assets, only if not already
   present) plus `decks/<preset>-<date>/{index.html,deck.css}`; then
   `write_files`.
5. Tell the user the deck is live in their Claude Design project and that
   further edits happen there directly — this skill's job ends at the
   initial build.

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
- **Deck Builder read fails, or a write conflict (409) on the customer's
  project** → re-read and merge; never `force` without asking the user.
- **A new slide type doesn't clearly match the brand rules** → flagged at
  Gate 2 for explicit sign-off, not assumed acceptable.
- **Pricing extraction** must use the allowlist in `references/pricing-fields.md`
  exactly — this is a correctness requirement (the internal/customer
  boundary), not just an implementation detail.
