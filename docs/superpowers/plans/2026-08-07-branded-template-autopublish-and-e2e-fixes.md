# Auto-Publish + E2E Fixes for `branded-template` — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Auto-publish the layout immediately after Step 9's push, and fix the five inaccuracies found by the live end-to-end run.

**Architecture:** Prose documentation change, continuing the branch `feat/branded-template-auto-template`. Two files: `SKILL.md` (all sections) and `template.html` (one missing token). No test suite; verification is running the documented commands live.

**Tech Stack:** Markdown; ParcelLab MCP connector tools (by suffix); `parcellab` CLI for the publish step only.

## Global Constraints

- Files: `plugins/pl-tools/skills/branded-template/SKILL.md` and `plugins/pl-tools/skills/branded-template/template.html`. Nothing else.
- **The MCP-only rule is now scoped, not absolute.** Everything stays MCP *except* publishing, which the connector cannot do. Do not migrate any other step to the CLI.
- MCP tools by suffix only (e.g. `__journey_write_layout`). Never a hardcoded connector prefix.
- Store NAMES, never client ids, in user-facing text. No real account/client/layout ids in the file.
- Never rename `parcellab-brand-layout`.
- No `version` field in any plugin.json.
- Keep every existing warning intact and forceful — especially 9b.4's full-replace warning.

## Verified facts (established live against account `1626718`, layout `20596`)

- `parcellab journey layout publish <id> --yes` publishes. Response includes `releaseStatus: "published"`, `releasedAt`, `complete: true`, `hasReleasedVersion: true`, **and `autoLayout`**.
- The MCP connector exposes **no** journey-layout publish tool. The route is `POST /v3/journey/layouts/{id}/publish/`.
- `journey_write_layout` responses **omit** `autoLayout` entirely, and **echo the full layout HTML** on every call.
- A layout must be `complete: true` to be usable — it must contain the `{{content}}` placeholder plus `<body>` and `<html>` tags.
- Publishing preserved the existing `autoLayout` mapping.
- `preview_start` returns tab ids like `seed` and `tab-1`. It does **not** return `main`.

---

### Task 1: Add Step 9a — auto-publish

**Files:**
- Modify: `plugins/pl-tools/skills/branded-template/SKILL.md` — insert a new section between Step 9 and Step 9b; amend Step 10's status line.

**Interfaces:**
- Consumes: `{NEW_LAYOUT_ID}` and `{ACCOUNT_ID}`, both bound in Step 9.
- Produces: a published layout, and the `{RELEASE_STATUS}` value Step 10 reports.

- [ ] **Step 1: Insert Step 9a after Step 9, before Step 9b**

Content to insert (adapt surrounding `---` separators to match the file's existing style):

````markdown
## Step 9a — Publish the layout

A pushed layout is a **draft**. Drafts are not used to send mail, so the layout must be
published before it does anything. Publish it as soon as Step 9 succeeds — the user already
approved the design at the Step 8 preview, so no further confirmation is needed.

> **⚠️ This is the one step that does not use the MCP connector.** The ParcelLab MCP connector
> exposes no journey-layout publish tool, so this step uses the `parcellab` CLI. Every other
> step in this skill stays on MCP — do not migrate anything else to the CLI.

```bash
parcellab --env prod journey layout publish {NEW_LAYOUT_ID} --yes -o json
```

Confirm the response shows:

- `"releaseStatus": "published"`
- `"hasReleasedVersion": true`
- a `releasedAt` timestamp

Record `releaseStatus` as `{RELEASE_STATUS}` for Step 10.

**If the CLI is not installed** (`parcellab: command not found`), do not fail the run. The layout
is already safely in the account. Tell the user:

> The layout was created but not published — the `parcellab` CLI isn't installed, and the MCP
> connector can't publish layouts. Publish it in the ParcelLab portal, or run `/pl-setup` to
> install the CLI.

Then carry on to Step 9b and report `not published` in Step 10.

**If publish returns a 400 about the layout being incomplete**, the HTML is missing something
required: a layout must contain the `{{content}}` placeholder and both `<body>` and `<html>`
tags to be publishable. Check those survived the Step 7 build, fix the file, re-push via Step 9,
and publish again.

Publishing does **not** touch `autoLayout`, so the order of Step 9a and Step 9b does not matter
for correctness. Publishing first simply means the layout is live the moment it is assigned.
````

- [ ] **Step 2: Update Step 10's status line**

Find the Step 10 report bullet:

```markdown
- **Status:** draft
```

Replace with:

```markdown
- **Status:** `{RELEASE_STATUS}` — `published` after a successful Step 9a, or `not published`
  if Step 9a was skipped because the CLI was unavailable (say so plainly, and repeat how to
  publish it).
```

- [ ] **Step 3: Verify the section reads correctly and Step 10 has no stale "draft"**

Run: `grep -n "Status:\|## Step 9a\|releaseStatus" plugins/pl-tools/skills/branded-template/SKILL.md`

Expected: Step 9a exists between Step 9 and Step 9b; Step 10's status bullet references `{RELEASE_STATUS}`; no remaining bare `**Status:** draft`.

- [ ] **Step 4: Commit**

```bash
git add plugins/pl-tools/skills/branded-template/SKILL.md
git commit -m "feat(branded-template): auto-publish the layout after push"
```

---

### Task 2: Fix the five end-to-end findings

**Files:**
- Modify: `plugins/pl-tools/skills/branded-template/SKILL.md`
- Modify: `plugins/pl-tools/skills/branded-template/template.html`

**Interfaces:** None — these are corrections to existing prose and one template token.

- [ ] **Step 1: Fix the `tabId` claim (finding 1)**

The file states the primary tab is `"main"` and hardcodes `tabId: "main"` in its tool calls. That
is wrong: `preview_start` returns generated ids such as `seed` and `tab-1`. Replace the claim
wherever it appears with instruction to **use the `tabId` returned by `preview_start`** and reuse
that value for every later `javascript_tool` / `computer` / `navigate` call. Note that the brand
scrape and the local preview are usually **different tabs** (each `preview_start` opens its own),
so the id from the first call is not necessarily the id for the preview. Use `tabs_context` to
list open tabs if the id is ever unclear. Do not leave any literal `tabId: "main"` behind.

- [ ] **Step 2: Note that the write response can't confirm the mapping (finding 2)**

In Step 9b.5, state that `journey_write_layout` responses **omit `autoLayout` entirely**, so the
write response cannot be used to confirm the mapping — the readback in 9b.5 is the only way to
verify it. This is why 9b.5 exists; make that explicit so nobody optimises it away.

- [ ] **Step 3: Add a cost warning to 9b.4 (finding 3)**

9b.3 already warns that the list call is expensive. Add an equivalent note to 9b.4: every
`journey_write_layout` call **echoes the full layout HTML back** in its response, and 9b.4 makes
at least two writes (one per 9b.4b layout, plus 9b.4a). Tell the agent not to echo that content
into the conversation.

- [ ] **Step 4: Add the missing `{{schemaOrgMarkup}}` token to the template (finding 4)**

`template.html` has no `{{schemaOrgMarkup}}` placeholder, even though Step 7 lists it among the
ParcelLab tokens that must survive verbatim. Add it immediately after the hidden preheader
`<div>` that carries `__BRAND_PREHEADER__`, matching how the account's existing layouts place it.
Change nothing else in the template.

- [ ] **Step 5: Extend Step 4's URL-cleaning rule (finding 5)**

Step 4 says to strip high-DPR multipliers (`dpr_2.0,`) but not the CDN resizing wrapper some
brands put in front of the real asset — e.g. `https://www.lush.com/cdn-cgi/image/width=640,f=auto/https://res.cloudinary.com/...`,
where the real image is the trailing URL and the wrapper caps the width at 640. Add a rule to
strip such a wrapper prefix and request a larger width from the underlying CDN instead.

Also add to Step 4's selection rules: on lazy-loading sites the hero may not be loaded at all on
first scan (`naturalWidth` of `0`, or no matching images). Scroll the page and re-scan, use
`currentSrc` as well as `src`, and verify a candidate by loading it via `new Image()` and
checking its real dimensions before committing to it.

- [ ] **Step 6: Verify all five fixes landed**

Run: `grep -c 'tabId: "main"' plugins/pl-tools/skills/branded-template/SKILL.md; grep -n "schemaOrgMarkup" plugins/pl-tools/skills/branded-template/template.html; grep -n "cdn-cgi\|currentSrc\|omit" plugins/pl-tools/skills/branded-template/SKILL.md`

Expected: zero occurrences of `tabId: "main"`; `{{schemaOrgMarkup}}` present in the template; the CDN-wrapper, `currentSrc`, and write-response-omission notes all present.

- [ ] **Step 7: Commit**

```bash
git add plugins/pl-tools/skills/branded-template/SKILL.md plugins/pl-tools/skills/branded-template/template.html
git commit -m "fix(branded-template): correct tabId, add cost/verification notes, template token, hero URL rules"
```

---

### Task 3: Verify publish behaviour and restore the account

**Files:** No changes unless a documented behaviour proves wrong.

Account `1626718`. Layout `20596` (Lush) is currently **published** and holds the auto-template
for store `16408` (`JLS Order`, the default). Store `18422` (`Jamie's Shopify Store`) maps to
layout `19510` (ParcelLab).

- [ ] **Step 1: Confirm the current state**

```bash
parcellab --env prod journey layout list --account 1626718 --all -o json --jmes 'results[?autoLayout].{id:id,name:prettyName,auto:autoLayout,status:releaseStatus}'
```

Expected: Lush `20596` published and holding `16408`; ParcelLab `19510` holding `18422`.

- [ ] **Step 2: Test that re-publishing is safe**

An agent re-running the skill may publish twice. Confirm it is not destructive:

```bash
parcellab --env prod journey layout publish 20596 --yes -o json --jmes '{status:releaseStatus,released:releasedAt,auto:autoLayout}'
```

Expected: still `published`, `autoLayout` unchanged. If re-publishing errors or drops the
mapping, add that to Step 9a as a failure mode.

- [ ] **Step 3: Report the finding**

State plainly whether re-publishing was safe, quoting the output. If it was not, say so and fix
Step 9a before proceeding.

- [ ] **Step 4: Commit any doc correction**

Only if Step 2 contradicted the documentation:

```bash
git add plugins/pl-tools/skills/branded-template/SKILL.md
git commit -m "docs(branded-template): correct publish behaviour after live check"
```

---

## Notes for the implementer

- Prose quality is the deliverable. These instructions are followed unsupervised against live
  customer accounts; prefer an explicit warning over a terse instruction.
- Do not restore the account in this plan. Whether Lush stays as the default store's template is
  the user's decision, pending separately.
- Task 1 and Task 2 both edit `SKILL.md`. Run them in order and re-read the file before the
  second, so the edits don't collide.
