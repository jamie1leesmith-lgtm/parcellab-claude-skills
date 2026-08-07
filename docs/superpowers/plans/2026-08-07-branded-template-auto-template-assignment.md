# Auto-Template Assignment in `branded-template` — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** After `branded-template` pushes a new layout, let the user assign it as a store's Auto Template Config — choosing the store by name — and clear the mapping off whichever template previously held it.

**Architecture:** This is a **documentation change to a single prose skill file**, not code. The "implementation" is inserting a new Step 9b into `SKILL.md` and amending Steps 9 and 10. There is no unit-test harness; verification means executing the documented MCP calls against a real ParcelLab account and checking the readback. Task 4 is that verification pass.

**Tech Stack:** Markdown (`SKILL.md`), ParcelLab MCP connector tools (referred to by suffix, e.g. `__config_list_clients`), `parcellab` CLI **for verification only**.

## Global Constraints

- **Spec:** `docs/superpowers/specs/2026-08-07-branded-template-auto-template-assignment-design.md`. Read it before starting.
- **Target file:** `plugins/pl-tools/skills/branded-template/SKILL.md` — the only file this plan modifies.
- **MCP-only at runtime.** The skill must not instruct use of the `parcellab` CLI. This variant exists so colleagues without the CLI can use it. The CLI appears in this plan only in Task 4, where *we* verify behaviour.
- **MCP tools are named by suffix**, never with a hardcoded connector prefix — match the file's existing convention (`the tool ending in __journey_write_layout`).
- **Store names, never client ids**, in every user-facing string.
- **`autoLayout` writes are a full replace.** All documented writes must merge with existing entries.
- **`country` is always `[]` for writes.** Country-specific entries are never created or deleted, only warned about.
- **No version bump.** `pl-tools` has no `version` field and resolves to the git SHA; releasing is commit → push `main` → tell the team to run `/pl-update`. Do not add a `version` field.
- **Never rename `parcellab-brand-layout`** where it appears in this file — it names a different skill in another repo and carries an HTML comment saying so.

---

### Task 1: Amend Step 9 and add store selection (9b.1–9b.3)

**Files:**
- Modify: `plugins/pl-tools/skills/branded-template/SKILL.md` — Step 9 bullet list (~line 351-353), and insert a new section after Step 9 (~line 354)

**Interfaces:**
- Consumes: `{ACCOUNT_ID}` (established in Step 1b), and `{NEW_LAYOUT_ID}` — the `id` returned by the Step 9 push.
- Produces: `{STORE_ID}`, `{STORE_NAME}`, `{OLD_LAYOUT_ID}`, `{OLD_LAYOUT_NAME}` — consumed by Task 2's write steps and Task 3's report line.

- [ ] **Step 1: Soften the `autoLayout` rule in Step 9**

Find this bullet in Step 9:

```markdown
- `"autoLayout"` must be an **empty list** `[]` — not `false` or `true`.
```

Replace with:

```markdown
- `"autoLayout"` must be an **empty list** `[]` on create — not `false` or `true`. Do not try to
  set the store mapping here; that happens in Step 9b, which has to read the account's other
  layouts first.
```

- [ ] **Step 2: Insert the Step 9b heading and store listing**

Immediately after Step 9's final bullet and its `---` separator, insert:

````markdown
## Step 9b — Assign the template to a store (Auto Template Config)

A new layout is inert until a store points at it. That pointer is the **Auto Template Config**,
and it lives on the **layout**, not on the store — each layout carries an `autoLayout` list of
`{client, layout, country}` entries. There is no template field on the client, so there is no
way to look this up from the store side.

**Talk about stores by name, never by client id.** Ids are internal plumbing; the name is what
the user recognises.

### 9b.1 — List the account's stores

Call the tool ending in `__config_list_clients` with `{ "account": [{ACCOUNT_ID}] }`.

Build a name→id map for yourself. For each store, derive a display name with this fallback so
an option is never a blank string:

1. `name` — e.g. `Jamie's Shopify Store`
2. `fullName` — if `name` is empty
3. `key` — e.g. `parcellab-demo-jls.myshopify.com`, if both are empty

Append `(default)` to the store whose `isDefault` is `true`.

If the call returns no stores, skip to Step 10 and report the layout as unassigned, saying why.
````

- [ ] **Step 3: Add the store-choice sub-step**

Continue immediately with:

````markdown
### 9b.2 — Choose the store

- **Exactly one store** → assign it automatically and state what you did. (Same shape as
  Step 1b's single-account handling — don't ask a question with one possible answer.)
- **More than one store** → ask which store should now use this template. Offer the display
  names, plus a final option: `None — leave unassigned`.

If the user picks `None`, skip to Step 10 and report the layout as unassigned.
````

- [ ] **Step 4: Add the discovery sub-step with the country warning**

Continue immediately with:

````markdown
### 9b.3 — Find the template that currently holds that mapping

One call: the tool ending in `__journey_list_journey_layouts` with `{ "account": [{ACCOUNT_ID}] }`.

Scan every result's `autoLayout` array for an entry where `client` equals the chosen store's id:

- **`country` is empty** → this is the current default mapping. Record the holding layout's `id`
  and `prettyName`. There should be at most one.
- **`country` is non-empty** → a country-specific override. **Leave it alone**, but warn:

  > Note: `{STORE_NAME}` also has a country-specific auto-template on `{OTHER_TEMPLATE_NAME}`
  > for `{USA, CAN}`. Orders shipping to those countries will keep using that template, not
  > this one. Change it in the portal if that isn't what you want.

  Without this warning you would tell the user the store now uses the new template while some
  of their orders demonstrably would not.

> **⚠️ This is the most expensive call in the skill.** The response includes the **full HTML
> `content` of every layout on the account**. Read only `id`, `prettyName`, and `autoLayout`
> from it, and never echo `content` back into the conversation. On an account with many
> layouts, tell the user this step is token-heavy before you make the call.
````

- [ ] **Step 5: Verify the file still reads correctly**

Run: `sed -n '/## Step 9b/,/### 9b.4/p' plugins/pl-tools/skills/branded-template/SKILL.md`

Expected: sections 9b.1, 9b.2, and 9b.3 appear in order, with the Step 9 → 9b → (Task 2 will add 9b.4) sequence intact and no duplicated headings.

- [ ] **Step 6: Commit**

```bash
git add plugins/pl-tools/skills/branded-template/SKILL.md
git commit -m "docs(branded-template): add store selection for auto-template assignment"
```

---

### Task 2: Document the writes, merge rule, and verification (9b.4–9b.5)

**Files:**
- Modify: `plugins/pl-tools/skills/branded-template/SKILL.md` — append after the 9b.3 block from Task 1

**Interfaces:**
- Consumes: `{STORE_ID}`, `{STORE_NAME}`, `{OLD_LAYOUT_ID}`, `{OLD_LAYOUT_NAME}` from Task 1; the new layout id from Step 9.
- Produces: the confirmed-assigned state that Task 3's Step 10 report describes.

- [ ] **Step 1: Add the write sub-step, new mapping first**

Append immediately after the 9b.3 warning block:

````markdown
### 9b.4 — Write the mappings: new first, then clear the old

**Order matters.** Clearing the old mapping first leaves a window where the store has no
template at all, which can break outbound emails. Setting the new one first means the worst
case is a brief duplicate between two valid brand templates. **Never leave the store unmapped.**

> **⚠️ `autoLayout` is replaced wholesale on write, not appended to.** Always send the layout's
> existing entries back alongside your change. Writing a bare single-entry list onto a layout
> that serves several stores silently destroys the other stores' mappings. This is the most
> damaging mistake available in this step.

**a. Set the new mapping.** Take the new layout's current `autoLayout` (just created, so
normally `[]`), add your entry, and write the merged list:

```
journey_write_layout → {
  "account": {ACCOUNT_ID},
  "id": {NEW_LAYOUT_ID},
  "data": {
    "autoLayout": [
      ...any entries the new layout already had...,
      { "client": {STORE_ID}, "layout": {NEW_LAYOUT_ID}, "country": [] }
    ]
  }
}
```

The `layout` value inside the entry **must equal the id of the layout you are writing to**.

**b. Clear the stale mapping.** Only if 9b.3 found a holding layout. Send back that layout's
`autoLayout` with **only the chosen store's `country: []` entry removed**, every other entry
preserved verbatim:

```
journey_write_layout → {
  "account": {ACCOUNT_ID},
  "id": {OLD_LAYOUT_ID},
  "data": { "autoLayout": [ ...its other entries, minus the chosen store... ] }
}
```

If 9b.3 found no holding layout, skip 9b.4b entirely — there is nothing to clear.

> **Why 9b.4b is mandatory, not tidy-up:** the API accepts a second mapping for the same store
> at the same `country` without any error or warning. Skip this and the store is mapped to two
> templates at once, with no indication of which one wins.
````

- [ ] **Step 2: Add the verification sub-step**

Continue immediately with:

````markdown
### 9b.5 — Verify before claiming success

Call the tool ending in `__journey_get_journey_layout` with `{ "id": {NEW_LAYOUT_ID} }` and
confirm `autoLayout` contains your `{STORE_ID}` entry.

- Entry present → proceed to Step 10.
- Entry missing → **report the failure with the readback.** Do not describe the assignment as
  done.

The mapping needs **no** `layout publish` — `autoLayout` is not part of the layout's publish
diff, so it applies as soon as it is written.
````

- [ ] **Step 3: Add the failure-mode table**

Continue immediately with:

````markdown
### 9b.6 — Failure handling

| Failure | What to do |
|---|---|
| `autoLayout not_a_list` (400) | The value must be a JSON list, not a bool. Fix and retry. |
| The 9b.4a write fails | Report it and make no further writes. The old mapping is untouched, so the store keeps working. |
| The 9b.4b clear fails after 9b.4a landed | Report the duplicate explicitly, naming **both** templates, and tell the user which to clear in the portal. Do not claim success. |
| 9b.5 readback shows no mapping | Report as a failure, including the readback. Not success. |
| `__config_list_clients` returns no stores | Skip assignment, report the layout as unassigned, and say why. |
````

- [ ] **Step 4: Check the constraint appears where it matters**

Run: `grep -n "replaced wholesale\|full replace\|country-specific" plugins/pl-tools/skills/branded-template/SKILL.md`

Expected: the merge warning appears in 9b.4 and the country-specific warning in 9b.3 — both present, neither lost to an editing slip.

- [ ] **Step 5: Commit**

```bash
git add plugins/pl-tools/skills/branded-template/SKILL.md
git commit -m "docs(branded-template): document auto-template writes, merge rule, and verification"
```

---

### Task 3: Update the report and reference sections

**Files:**
- Modify: `plugins/pl-tools/skills/branded-template/SKILL.md` — Step 10 report list (~line 359-365) and the "Useful MCP calls (reference)" list (~line 373-377)

**Interfaces:**
- Consumes: the assigned state confirmed in Task 2's 9b.5.
- Produces: nothing downstream — this is the final user-facing output.

- [ ] **Step 1: Add the auto-template line to the Step 10 success report**

Find this list in Step 10:

```markdown
- Layout **ID** (e.g. `19584`)
- Layout **prettyName**
- **Account:** {ACCOUNT_ID}
- **Status:** draft
- Next step options: assign to a journey in the ParcelLab portal, or publish.
```

Replace with:

```markdown
- Layout **ID** (e.g. `19584`)
- Layout **prettyName**
- **Account:** {ACCOUNT_ID}
- **Status:** draft
- **Auto-template:** one of —
  - `now used by {STORE_NAME} (previously {OLD_LAYOUT_NAME})` — a mapping was moved
  - `now used by {STORE_NAME}` — the store had no previous mapping
  - `not assigned` — the user chose `None`, or the account has no stores
- Any country-specific override warning from 9b.3, repeated here so it isn't lost in scrollback.
- Next step options: assign to a journey in the ParcelLab portal, or publish.
```

- [ ] **Step 2: Add the auto-template calls to the reference list**

Find the "Useful MCP calls (reference)" list and append these three bullets:

```markdown
- List the account's stores (for auto-template selection): tool ending `__config_list_clients` → `{ "account": [{ACCOUNT_ID}] }`
- Set/clear a store→template mapping: tool ending `__journey_write_layout` → `{ "account": {ACCOUNT_ID}, "id": <layout id>, "data": { "autoLayout": [ { "client": <store id>, "layout": <layout id>, "country": [] } ] } }` — remember this **replaces** the whole list
- Read back a mapping: tool ending `__journey_get_journey_layout` → `{ "id": <layout id> }`, then check `autoLayout`
```

- [ ] **Step 3: Confirm no client ids leaked into user-facing copy**

Run: `grep -n "client id\|client_id\|16408\|18422" plugins/pl-tools/skills/branded-template/SKILL.md`

Expected: matches only in explanatory/internal-plumbing context (e.g. "`<store id>`" inside a JSON example, or the "never by client id" instruction). **No** real account's client ids like `16408` or `18422` hardcoded anywhere, and no user-facing string that prints an id instead of a name.

- [ ] **Step 4: Commit**

```bash
git add plugins/pl-tools/skills/branded-template/SKILL.md
git commit -m "docs(branded-template): report auto-template assignment and add reference calls"
```

---

### Task 4: Verify the documented flow against a live account

**Files:**
- No file changes unless a defect is found. If one is, fix `plugins/pl-tools/skills/branded-template/SKILL.md` and note it.

**Interfaces:**
- Consumes: the complete Step 9b from Tasks 1–3.
- Produces: evidence that the documented calls behave as written, plus a restored account.

**Account:** `1626718`. Two stores — `_default` (`16408`) and `Jamie's Shopify Store` (`18422`). Eight layouts.

**Starting state, and the state to restore at the end:**

| Layout | Mapped store |
|---|---|
| `19585` Nike | `16408` |
| `19510` ParcelLab | `18422` |
| all others | none |

Use the **CLI** for verification readbacks — it can trim output with `--jmes`, where the MCP list call returns every layout's full HTML. The skill itself still documents MCP-only; this is our test instrumentation, not runtime behaviour.

- [ ] **Step 1: Capture the starting state**

```bash
parcellab --env prod journey layout list --account 1626718 --all -o json --jmes 'results[].{id:id,name:prettyName,auto:autoLayout}'
```

Expected: matches the table above. If it does not, record what is actually there — that is now the state to restore.

- [ ] **Step 2: Confirm store names resolve without ids**

```bash
parcellab --env prod config client list --account 1626718 --all -o json --jmes 'results[].{id:id,name:name,fullName:fullName,key:key,isDefault:isDefault}'
```

Expected: both stores have a non-empty `name`, so the 9b.1 fallback chain is not needed here. Confirm the display names a user would see are `_default`-ish and `Jamie's Shopify Store` — recognisable without ids.

- [ ] **Step 3: Test the move case (spec test 2)**

Follow 9b.4 by hand for store `18422`, moving it from ParcelLab (`19510`) onto Goddiva (`20102`) — new first, then clear:

```bash
parcellab --env prod journey layout update 20102 --json '{"autoLayout":[{"client":18422,"layout":20102,"country":[]}]}' --yes -o json --jmes 'autoLayout'
parcellab --env prod journey layout update 19510 --json '{"autoLayout":[]}' --yes -o json --jmes 'autoLayout'
```

Expected: Goddiva holds `18422`; ParcelLab holds nothing. Exactly one entry for `18422` across the account.

- [ ] **Step 4: Confirm exactly one mapping survived**

```bash
parcellab --env prod journey layout list --account 1626718 --all -o json --jmes 'results[?autoLayout].{id:id,name:prettyName,auto:autoLayout}'
```

Expected: two layouts listed — Nike with `16408`, Goddiva with `18422`. If `18422` appears twice, 9b.4b's wording is wrong; fix it.

- [ ] **Step 4b: Test the no-prior-mapping case (spec test 3)**

Clear store `18422` entirely, then assign it fresh, and confirm nothing else changed:

```bash
parcellab --env prod journey layout update 20102 --json '{"autoLayout":[]}' --yes -o json --jmes 'autoLayout'
parcellab --env prod journey layout update 20200 --json '{"autoLayout":[{"client":18422,"layout":20200,"country":[]}]}' --yes -o json --jmes 'autoLayout'
parcellab --env prod journey layout list --account 1626718 --all -o json --jmes 'results[?autoLayout].{id:id,name:prettyName,auto:autoLayout}'
```

Expected: Wonderbly (`20200`) holds `18422`, Nike still holds `16408`, and nothing was cleared
that did not need clearing — 9b.3 finds no holding layout, so 9b.4b is skipped.

Then reset to the post-Step-4 state, so Steps 5 and 6 start from a known point:

```bash
parcellab --env prod journey layout update 20200 --json '{"autoLayout":[]}' --yes -o json --jmes 'autoLayout'
parcellab --env prod journey layout update 20102 --json '{"autoLayout":[{"client":18422,"layout":20102,"country":[]}]}' --yes -o json --jmes 'autoLayout'
```

Expected: Goddiva (`20102`) holds `18422`, Wonderbly (`20200`) empty, Nike (`19585`) holds `16408`.

- [ ] **Step 4c: Read-through check of the `None` path (spec test 5)**

No API calls — this branch is conversational. Re-read 9b.2 and confirm that choosing
`None — leave unassigned` routes straight to Step 10 with **no** `journey_write_layout` call
documented anywhere on that path, and that Step 10's `not assigned` wording covers it.

Expected: no write is reachable from the `None` branch. If one is, the wording is wrong.

- [ ] **Step 5: Test the merge rule (spec test 4) — the one that can cause real damage**

Put both stores on Goddiva, then clear only `18422`, and confirm `16408` survives:

```bash
parcellab --env prod journey layout update 20102 --json '{"autoLayout":[{"client":18422,"layout":20102,"country":[]},{"client":16408,"layout":20102,"country":[]}]}' --yes -o json --jmes 'autoLayout'
parcellab --env prod journey layout update 20102 --json '{"autoLayout":[{"client":16408,"layout":20102,"country":[]}]}' --yes -o json --jmes 'autoLayout'
```

Expected: the final readback shows **only** the `16408` entry, proving a merge-and-remove write preserves siblings. If a naive `[]` write had been documented instead, `16408` would have been destroyed — this is the case 9b.4's warning exists for.

- [ ] **Step 6: Test the country-specific warning path (spec test 6)**

```bash
parcellab --env prod journey layout update 20200 --json '{"autoLayout":[{"client":16408,"layout":20200,"country":["USA"]}]}' --yes -o json --jmes 'autoLayout'
parcellab --env prod journey layout list --account 1626718 --all -o json --jmes 'results[?autoLayout].{id:id,name:prettyName,auto:autoLayout}'
```

Expected: Wonderbly (`20200`) holds a `country: ["USA"]` entry for `16408` **alongside** Goddiva's `country: []` entry for the same store — both coexist. This is exactly the situation 9b.3's warning must fire on. Confirm the warning wording in the file would correctly name Wonderbly and `USA`.

- [ ] **Step 7: Restore the account to its starting state**

```bash
parcellab --env prod journey layout update 20200 --json '{"autoLayout":[]}' --yes -o json --jmes 'autoLayout'
parcellab --env prod journey layout update 20102 --json '{"autoLayout":[]}' --yes -o json --jmes 'autoLayout'
parcellab --env prod journey layout update 19585 --json '{"autoLayout":[{"client":16408,"layout":19585,"country":[]}]}' --yes -o json --jmes 'autoLayout'
parcellab --env prod journey layout update 19510 --json '{"autoLayout":[{"client":18422,"layout":19510,"country":[]}]}' --yes -o json --jmes 'autoLayout'
```

- [ ] **Step 8: Confirm the restore**

```bash
parcellab --env prod journey layout list --account 1626718 --all -o json --jmes 'results[?autoLayout].{id:id,name:prettyName,auto:autoLayout}'
```

Expected: exactly Nike→`16408` and ParcelLab→`18422`, matching Step 1. **Report the actual output** — do not assert the restore worked without showing it.

- [ ] **Step 9: Commit any fixes**

Only if Steps 3–6 exposed wording that does not match real API behaviour:

```bash
git add plugins/pl-tools/skills/branded-template/SKILL.md
git commit -m "docs(branded-template): correct auto-template wording after live verification"
```

---

### Task 5: Release

**Files:**
- No file changes. Do **not** add a `version` field to `plugins/pl-tools/.claude-plugin/plugin.json`.

- [ ] **Step 1: Confirm the remote is the personal account**

```bash
git remote -v
```

Expected: `github.com/jamie1leesmith-lgtm/parcellab-claude-skills`. **If this shows a `parcelLab` org repo, stop and ask** — org pushes need per-action approval.

- [ ] **Step 2: Review the full diff before pushing**

```bash
git log --oneline main..HEAD && git diff main...HEAD -- plugins/pl-tools/skills/branded-template/SKILL.md
```

Expected: only `SKILL.md` changes, plus the spec and this plan under `docs/superpowers/`. No stray edits to other skills.

- [ ] **Step 3: Push, then tell the team**

```bash
git push -u origin HEAD
```

`pl-tools` has no `version` field, so its version resolves to the git commit SHA and this push is automatically a new version. Nothing needs bumping.

Then state plainly: teammates receive nothing until they run `/pl-update`. There is no notification and no background pull. "Message the team" is part of releasing.

---

## Notes for the implementer

- **This is a prose file.** The measure of a good edit is that someone following Step 9b cold gets it right — particularly the merge rule. Prefer explicit warnings over terse instructions.
- **Do not add CLI instructions to the skill.** The CLI in Task 4 is test instrumentation only.
- **Do not rename `parcellab-brand-layout`** where it appears near the end of the file; it names a different skill in another repo and has an HTML comment saying so.
- The spec's claim that `autoLayout` needs no publish is well-supported but not conclusively proven. If Task 4 turns up any evidence to the contrary, say so rather than smoothing it over.
