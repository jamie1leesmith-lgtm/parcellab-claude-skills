# Auto-template assignment in `branded-template`

**Date:** 2026-08-07
**Skill:** `plugins/pl-tools/skills/branded-template/SKILL.md`
**Status:** approved design, not yet implemented

## Problem

`branded-template` creates a branded journey layout and stops. The layout is left as an
orphan: nothing in ParcelLab uses it until someone opens the portal and wires it up by
hand. Meanwhile the store carries on sending the *old* template.

The wiring in question is the **Auto Template Config** — the store → template mapping. Two
facts about it drive this design, both established by testing against account `1626718`:

1. **It lives on the layout, not on the client.** Each layout carries an `autoLayout` list of
   `{client, layout, country}` entries. There is no template field on `config/client`, so
   there is no cheap reverse lookup from the store side.
2. **The API permits duplicate mappings and never warns.** Adding client `16408` to the Nike
   layout while it was still mapped to the Nespresso layout left the client mapped to *both*
   at `country: []`, with no error. Clearing the previous mapping is therefore a required
   step, not a tidy-up.

A third fact removes a step: `autoLayout` does not appear in the layout publish diff
(`journey layout diff` returns only `name`, `prettyName`, `language`, `content`, `liquid`,
`partials`), so the mapping is a live relational record and needs no `layout publish`. This
is well-supported rather than conclusively proven — the definitive check would be firing a
message for the store and observing which template wraps it.

## Scope

Add a store-assignment step to `branded-template`. Present stores by **name**, never by
client id — the name is what people recognise.

Out of scope: country-specific mappings (`country` is always `[]`), multi-store assignment
in one run, and any change to how the layout HTML is built.

## Constraints

- **MCP-only.** This skill variant deliberately avoids the `parcellab` CLI so it works for
  colleagues who have not installed it. Discovery and writes both go through the ParcelLab
  MCP connector. MCP tools are referred to by suffix (e.g. `__config_list_clients`), matching
  the skill's existing convention.
- **No new dependencies** beyond MCP tools the skill already relies on.

## Design

A new **Step 9b — Assign the template to a store**, between the push (Step 9) and the report
(Step 10).

Step 9's current hard rule — `"autoLayout" must be an empty list [] — not false or true` —
becomes: create the layout with `[]`, then set the mapping in Step 9b. Creation stays a
single concern; assignment is separable and skippable.

### 9b.1 List the stores

`__config_list_clients { account: [ACCOUNT_ID] }`.

Build a name→id map internally. **Only names are ever shown to the user.**

Display-name fallback, so an option is never a blank string:

1. `name` (e.g. `Jamie's Shopify Store`)
2. `fullName`
3. `key` (e.g. `parcellab-demo-jls.myshopify.com`)

Annotate the store with `isDefault: true` as `(default)`.

### 9b.2 Choose the store

- **Exactly one store** → assign it automatically and state what happened. This mirrors how
  Step 1b already handles single-account cases.
- **Multiple stores** → ask which store should now use this template. Offer the display names
  plus `None — leave unassigned`.
- **`None`** → skip to Step 10 and report the layout as unassigned.

### 9b.3 Find the current holder of that mapping

One call: `__journey_list_journey_layouts { account: [ACCOUNT_ID] }`.

Scan every result's `autoLayout` for an entry where `client` equals the chosen store id and
`country` is empty. Record the holding layout's `id` and `prettyName`.

**Also record country-specific entries.** While scanning, collect any entry for the chosen
store where `country` is *non-empty*. These are left untouched (country variants are out of
scope), but they override the default mapping for those countries — so the skill must warn:

> Note: `<Store Name>` also has a country-specific auto-template on `<Template prettyName>`
> for `<USA, CAN>`. Orders shipping to those countries will keep using that template, not
> this one. Change it in the portal if that isn't what you want.

Without this warning the skill would claim the store now uses the new template while some of
its orders demonstrably would not.

**This response includes the full HTML `content` of every layout and is the expensive step in
the skill.** Read only `id`, `prettyName`, and `autoLayout`; never echo `content` back into
the conversation. On an account with many layouts, warn the user that this step is costly
before making the call.

### 9b.4 Write the mappings — new first, then clear the old

Order matters. Clearing first leaves a window in which the store has no template at all,
which could break outbound emails; setting first means the worst case is a transient
duplicate between two valid brand templates. **Never leave the store unmapped.**

**a. Set the new mapping.** Take the new layout's existing `autoLayout`, append
`{client: <store id>, layout: <new layout id>, country: []}`, and write the merged list:

```
__journey_write_layout → {
  "account": {ACCOUNT_ID},
  "id": <new layout id>,
  "data": { "autoLayout": [ ...existing entries..., {"client": <store id>, "layout": <new layout id>, "country": []} ] }
}
```

**b. Clear the stale mapping.** For the holding layout found in 9b.3, write back its
`autoLayout` with *only* the matching entry removed:

```
__journey_write_layout → {
  "account": {ACCOUNT_ID},
  "id": <old layout id>,
  "data": { "autoLayout": [ ...its other entries, minus the chosen store... ] }
}
```

If no holding layout was found, skip this step.

### 9b.5 Verify

`__journey_get_journey_layout { id: <new layout id> }` and confirm the expected entry is
present in `autoLayout`. If it is missing, report the failure rather than claiming success.

### Step 10 — report

Add one line to the existing report:

```
Auto-template: now used by <Store Name> (previously <Old Template prettyName>)
```

Variants: `now used by <Store Name>` when there was no previous holder;
`Auto-template: not assigned` when the user chose `None`.

## Rules the skill must state explicitly

- **`autoLayout` writes are a full replace, not an append.** Always merge with the layout's
  existing entries. Writing a bare single-entry list onto a layout that serves several stores
  silently destroys the other stores' mappings — the most damaging mistake available here.
- The API permits duplicate mappings for the same client and never warns, so clearing the
  previous mapping is mandatory.
- The `layout` value inside each mapping must equal the id of the layout being written.
- `country` is always `[]` for writes. Country-specific entries are never created or removed,
  but they must be **warned about** when found for the chosen store (see 9b.3).
- The mapping needs no `layout publish`.
- Show store names, never client ids. Ids are internal plumbing.

## Failure modes

| Failure | Handling |
|---|---|
| `autoLayout not_a_list` (400) | The value must be a JSON list, not a bool. Fix and retry. |
| New mapping write fails | Report it; make no further writes. The old mapping is still intact, so the store keeps working. |
| Stale clear fails after the new mapping landed | Report the duplicate explicitly, naming both templates, and tell the user which one to clear in the portal. Do not claim success. |
| Verification (9b.5) shows no mapping | Report as a failure with the readback, not as success. |
| No stores returned by `config_list_clients` | Skip assignment, report the layout as unassigned, and say why. |

## Testing

Verify against account `1626718`, which has two stores (`_default` `16408`, and
`Jamie's Shopify Store` `18422`) and eight layouts:

1. Multi-store account prompts by name, with no client ids shown.
2. Assigning a store that already has a mapping moves it, leaving exactly one entry for that
   store across all layouts.
3. Assigning a store with no existing mapping adds one and clears nothing.
4. A layout holding mappings for two stores keeps the other store's entry when one is cleared
   (the merge rule).
5. `None` leaves every mapping untouched.
6. A store with a country-specific mapping on another layout triggers the 9b.3 warning, and
   that country entry survives the swap untouched.

Test state to restore afterwards: layout `19585` (Nike) → client `16408`; layout `19510`
(ParcelLab) → client `18422`; all other layouts unmapped.
