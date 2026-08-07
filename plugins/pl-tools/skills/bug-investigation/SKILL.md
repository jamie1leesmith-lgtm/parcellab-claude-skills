---
name: bug-investigation
description: Investigate and document a parcelLab product bug — inspect live config via the parcellab CLI, reproduce interactively in Claude-in-Chrome (captures real screenshots/recordings), isolate root cause by comparing against sibling portals/configs, and publish a shareable bug-report artifact before any mitigation is applied. Trigger on phrases like "troubleshoot this portal", "investigate this bug", "reproduce this issue", "something weird is happening on [portal/page]", "document this bug for the team", or any request to debug and write up unexpected behaviour in a live parcelLab account/portal/page.
---

# parcelLab — Bug Investigation & Write-up

## Overview

Investigate → reproduce with real evidence → isolate root cause → **write up the bug report** → only then, if asked, mitigate — and mitigation always needs express, account-number-specific authorisation, separate from "yes go ahead."

The report-before-mitigation ordering is deliberate, not incidental: it guarantees a clean record of the bug *as found* exists before anything in the account changes, and it stops "let's just fix it" from skipping past documentation. If a mitigation is applied, it gets appended to the same report afterward — the original findings are never overwritten by the fix.

This grew out of a real investigation (paula-puma returns portal, account 1625801): a return-reason pick was silently reassigning selection state to a different line item. Config was fine; the bug was in the front end. That session used the built-in Browser pane for the repro (no way to get real screenshots into the write-up — everything had to be prose) and applied the mitigation before the report existed. This version fixes both.

> **Why Claude-in-Chrome, not the built-in Browser pane, for this skill specifically:** the built-in Browser pane (`mcp__Claude_Browser__*`) stays the right default for other browsing/preview skills (brand layouts, demo requests) — fresh context, no login needed, lighter weight. But it has no way to save a screenshot to disk or export a recording, so nothing captured there can survive into a shareable report. Claude-in-Chrome's `computer` tool takes `save_to_disk: true` on the `screenshot` action, and `gif_creator` can record and export an actual GIF of the repro sequence. That's the whole reason to reach for it here — not a general preference change, just this workflow. It also runs in the user's real signed-in Chrome, which is worth knowing before you start clicking around.

---

## Step 0 — Confirm the account, in writing, before doing anything

Never infer, reuse, or carry over an account ID/code from memory, a prior session, or a similar-sounding name. Get it explicitly from the user for *this* investigation and read it back before running a single CLI command:

> "Confirming before I start: account **{ID}** ({name if known}), portal/resource **{code}**. Is that right?"

If the user's message already states the account number plainly, this can be a one-line restatement rather than a full question — but it must still name the number back to them. If it's ambiguous (a name without a number, "the usual account," multiple candidates), stop and ask which account, don't guess from context.

**This skill is deliberately stricter than the repo-wide convention below.** Two
differences, both intentional — do not "simplify" them into the shared rules:

- Confirmation happens **before the first CLI call of any kind**, not just before
  the first write. An investigation run against the wrong account wastes the whole
  effort and reads config that isn't the user's to look at.
- The default account from *Account resolution and confirmation* only supplies the
  account this step **proposes**. It is never used unconfirmed. `$PARCELLAB_ACCOUNT_ID`
  is a starting suggestion here, not an answer.

---

## Account resolution and confirmation

**Resolve the account, in this order:**

1. An account the user named explicitly in this conversation.
2. `$PARCELLAB_ACCOUNT_ID`.
3. `$PARCELLAB_USER_ID` (legacy alias — accept it, never write it).

If none resolve, set the default up now: ask which account they want, find it
with `parcellab account account search --name "<term>"`, and offer to write it
to the `env` block of `~/.claude/settings.json` as `PARCELLAB_ACCOUNT_ID`. Then
tell them to quit and reopen the app — environment variables are only read at
startup.

Point the CLI's write guard at that same account too:
`parcellab settings edit-mode set account-restricted --account <id>`, then confirm
it took with `parcellab settings edit-mode show`. Use their own leaf account — a
parent account does not work. Without this the CLI may permit writes to a
colleague's demo account and block their own, and that stays invisible until a
write fails.

**Confirm before the first write of the conversation.** Resolve the account's
human name with `parcellab account account show <id>` and ask:

> Using **<account name>** (`<id>`) — your default. Correct, or use a different
> account?

A bare account number means nothing to a human reader; a wrong *name* is
obvious. Do not skip the name lookup.

Rules:

- Confirm once per conversation, before the first write — not before every call.
- An account the user names explicitly still gets confirmed, the same way.
- Read-only inspection needs no confirmation. Every write does.
- **Also before the first write:** run `parcellab settings edit-mode show`. It
  must say `account-restricted` scoped to this same account. If it says
  anything else — unrestricted, read-only, or a different account — stop and
  offer to fix it (`parcellab settings edit-mode set account-restricted
  --account <id>`) before writing anything. This guard is the only thing that
  physically stops a write landing in a colleague's account; a write must never
  proceed while it is off or aimed elsewhere.

## Step 1 — Identify the resource and inspect config

**Bugs here are not just returns.** Anything built on the Product API is fair game — returns v1/v2 (Shopify or not), Order Status Page themes, Engage/Journey triggers and placeholders, filters, client/shop setup, carrier connections and checkpoint matching, webhook/OAuth integrations, product feed. Don't default to a returns-shaped investigation just because that's the first one this skill was written from.

1. Get the specific portal/page/journey/theme code or id, and whatever repro details the user already has (order number, email, exact steps, what they expected vs. saw) — account is already confirmed from Step 0.
<!-- Do not rename `parcellab-product-api` / `parcellab-product-configuration`:
     they belong to the org's plugin (parcelLab/parcellab-cli), not to pl-tools. -->
2. Load `parcellab-product-api:parcellab-product-configuration` first — it's the entry point across this whole area and will route you to the specific skill(s) that actually apply, for example:
   - Returns → `returns-v2-entrypoint` (which itself routes to Shopify/non-Shopify/headless/theme variants), or `returns-v1-remediation` for legacy portals
   - Order Status Page → the `track_*` OSP theme/translation tools, or `account-tracking-settings` for account-level tracking visibility
   - Engage/Journey → `engage-outbound-starter-set`, `engage-placeholders-render-context`, `engage-return-email-triggers`, `engage-webhook-triggers` depending on what's misbehaving
   - Filters, client/shop, domains/senders, webhook OAuth → `product-api-filter-builder`, `product-api-filter-fields`, `product-api-client-shop-setup`, `product-api-domains-senders-whitelists`, `product-api-webhook-oauth-integrations`
   - Carrier/checkpoint/product-feed data issues that aren't really "config" → `carrier-checkpoint-debug`, `carrier-connection-setup`, `product-feed-debug`, or `shopify-admin-graphql-debug` for live Shopify order/customer/fulfillment facts
   - If it's genuinely unclear which area owns the symptom, say so and check more than one rather than guessing the wrong owner.
3. Follow `product-api-cli-evidence-loop`'s discipline for the CLI work itself: check Codex-Knowledge for known behaviour first, inspect live config with `parcellab` (draft via `... show <id>`, published via `... lookup <code> --draft false`). **This entire investigation — Steps 1 through 4 — is read-only.** No writes happen before the report exists, regardless of how obvious the fix looks.
4. Note anything config-driven that could plausibly explain the reported behaviour — filters, required-field settings, targeting rules, reason/option hierarchies, checkpoint matching rules. This is what lets you say later whether it's "config is wrong" or "the product has a bug," instead of guessing.

---

## Step 2 — Reproduce live in Claude-in-Chrome

1. Load the Claude-in-Chrome tools if they're deferred (a single batched call, not one at a time):
   ```
   ToolSearch({query: "select:mcp__claude-in-chrome__tabs_context_mcp,mcp__claude-in-chrome__navigate,mcp__claude-in-chrome__computer,mcp__claude-in-chrome__read_page,mcp__claude-in-chrome__tabs_create_mcp,mcp__claude-in-chrome__gif_creator,mcp__claude-in-chrome__find"})
   ```
2. `tabs_context_mcp {createIfEmpty: true}`, then `tabs_create_mcp` for a fresh tab — don't reuse a tab that might hold the user's own in-progress work.
3. `navigate` to the right URL for the resource under test, on the account confirmed in Step 0:
   - Returns v2 draft: `https://returns-app.parcellab.com/{account.name}/{portal.code}/?draft=true`
   - Returns v2 published: same host, without `?draft=true`, or the portal's `productionUrl`
   - Other surfaces (OSP, Journey previews) — check the matching `parcellab-product-api` skill for its preview URL convention before guessing one.
4. Drive the repro with `computer` (`left_click`, `type`, etc.), confirming coordinates against a fresh screenshot each time the layout might have reflowed — don't chain clicks from stale coordinates. Prefer `find`/`read_page` refs over guessed coordinates when the DOM is stable enough to give them.
5. **Capture real evidence as you go, not just at the end:**
   - Key-state screenshots: `computer {action: "screenshot", tabId, save_to_disk: true}` — before the repro and at the moment the bug fires. (An "after" capture only happens later, in Step 5, if a mitigation is applied.)
   - A recording of the exact sequence, when a single screenshot won't show the problem (state carrying across steps, a race, a reflow):
     ```
     gif_creator {action: "start_recording", tabId}
     computer {action: "screenshot", tabId}        // first frame
     ...perform the repro steps...
     computer {action: "screenshot", tabId}        // last frame
     gif_creator {action: "stop_recording", tabId}
     gif_creator {action: "export", tabId, download: true, filename: "<bug-name>.gif"}
     ```
6. Confirm you actually reproduced the reported symptom before moving on. If it doesn't reproduce, that's a finding — say so plainly, describe what you tried, and don't manufacture a root cause from config alone.

---

## Step 3 — Isolate root cause (still read-only)

1. Compare the broken resource against siblings on the same account (other portals, other clients, other layouts) — pull each one's relevant config via `parcellab` and diff the fields that plausibly matter to the symptom.
2. State plainly whether the defect is **config-specific** (fixable by editing this account's config) or **systemic** (a product/front-end bug that would reproduce anywhere the same conditions are met, even if this account is the only place it currently fires).
3. If you can already see what a config mitigation would look like, note it for the report — but do not propose it as an action yet, and absolutely do not write anything. That gate is Step 5, after the report is published.

---

## Step 4 — Write up the bug report (before any mitigation)

The report documents the bug **as found** — this step happens whether or not a mitigation is ever applied, and it happens *before* one is.

1. Read the bundled `report-template.html` in this skill's folder — it's the same design system used for the first paula-puma write-up (utilitarian report layout, light/dark aware, semantic severity chips, a before/after comparison block, a config comparison table, code blocks for CLI/JSON evidence, an evidence section for real captures).
2. Fill in every `[BRACKETED PLACEHOLDER]` with this investigation's specifics, including the confirmed account number/code from Step 0 in the meta block. Keep the numbered repro-steps list only if the steps are genuinely sequential. Leave the "Mitigation applied" section either deleted or explicitly marked "Not yet applied" — never pre-fill it before it's real.
3. **Embed the real captures, not prose descriptions of them.** A `file://` path won't survive publishing. Instead:
   - Read the saved screenshot/GIF file and base64-encode it, then inline it as `<img src="data:image/png;base64,{data}">` (or `data:image/gif;base64,...` for the recording).
   - Caption each image with what it's showing and at which repro step.
4. Publish with the `Artifact` tool — HTML, favicon `🐛`, a title naming the bug, a one-line `description`. Tell the user it's private until they share it from the artifact's own share menu; don't imply it's already been sent anywhere.
5. **Always also hand over a standalone HTML file and a PDF**, without being asked — the claude.ai artifact link needs a Claude account to view, and the people a bug report gets shared with (engineering, account owners, the client) often don't have one:
   - The filled-in HTML file used to publish the artifact is already self-contained (no CDN fonts, no external assets — everything inlined per the artifact design rules) and already sits on disk at whatever path you wrote it to. That file *is* the shareable HTML deliverable, no extra step needed.
   - Render the same file to PDF with headless Chrome so there's a static, universally-openable copy too:
     ```bash
     "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
       --headless --disable-gpu --no-pdf-header-footer --print-to-pdf-no-header \
       --print-to-pdf="<same-dir>/<bug-name>.pdf" \
       "file://<path-to-the-report-html>"
     ```
     If Chrome isn't at that path on this machine, check `/Applications/Chromium.app/...` or `google-chrome`/`chromium` on `PATH` before giving up — don't skip the PDF silently, say plainly if no renderer is available.
   - Deliver both files with `SendUserFile` (`display: "attach"`, since they're for download/forwarding, not inline viewing) in the same turn as the artifact link.
6. Report the findings to the user now, before asking anything about mitigation: what was reproduced, root cause (config vs. product bug), the artifact link, and the attached HTML/PDF. Let this land as its own moment — don't immediately roll into a mitigation pitch in the same breath.

---

## Step 5 — Mitigation gate (only if the user asks, after the report exists)

Do not raise mitigation unprompted immediately after the report — if the user wants one, they'll ask, same as happened in the session this skill was built from. If they do ask:

1. State the trade-off plainly: what changes for real customers, not just what stops the bug's symptom from firing (a `keep_article`-style removal is a policy change, not a neutral bugfix — say so explicitly if that's the shape of it).
2. Ask for **express, account-number-specific authorisation** — a general "yes" is not enough. The confirmation question itself must restate the exact account number and resource code, so the user is approving a specific, named target, not a vague intent:
   > "This will edit and publish account **{ID}**, portal **{code}** — removing/changing {specific config}. Confirm this is the correct account and you want it applied?"
   Use `AskUserQuestion` with the account number and code written into the question text itself, not just implied by prior conversation context. If the user has been discussing multiple accounts in the same session, this restatement is what prevents a mitigation landing on the wrong one.
3. Only after that express confirmation: edit the draft via `parcellab ... update` **on the confirmed account**, publish, read back the published config to confirm it landed on the account/resource you intended.
4. Replay the exact repro in Claude-in-Chrome to confirm the fix — capture that too (a genuine "after" screenshot, not assumed).
5. Update the **same** published artifact (redeploy the same file path) to add the mitigation section and the before/after evidence — don't leave the report saying "not yet applied" once it has been.
6. **Regenerate and redeliver the HTML and PDF exports from Step 4.5** against the updated file, and send them again. The first round you handed over is now stale (still says "not yet applied") — don't leave whoever received it holding an out-of-date copy while only the live artifact link gets the update. Say plainly that this replaces the earlier files, since the two exports don't auto-update the way the artifact link's URL does.

---

## Step 6 — Final report back

State plainly: what was reproduced, root cause (config vs. product bug), whether a mitigation was applied and what trade-off it carries, the artifact link (same URL throughout, updated in place if a mitigation landed), and the attached HTML/PDF (regenerated if a mitigation landed after the first delivery). If the defect is systemic, say so explicitly so it gets raised with engineering rather than left as tribal knowledge sitting in one account's report.

---

## Edge cases

- **Account number never stated plainly** — stop at Step 0 and ask; don't infer from a portal code, a brand name, or what account came up earlier in the conversation.
- **User asks to "just fix it" before a report exists** — still do Steps 1-4 first. Say plainly that the report comes before any change, and why (it's the record of the bug as found, and the account-number confirmation gate needs something concrete to confirm against).
- **Can't reproduce at all** — say so, share exactly what you tried, and stop. Don't infer a root cause from config alone when you haven't seen the behaviour.
- **Bug is published-only** — draft preview URLs (`?draft=true`) only reflect draft config; if the reported behaviour depends on what's actually live, test the production/lookup URL instead and say which one you used.
- **Screenshot/recording capture fails** — Claude-in-Chrome runs the user's real Chrome; if a tab or profile issue blocks capture, fall back to the built-in Browser pane for the repro itself and tell the user plainly that the report will use prose descriptions instead of real images, rather than silently dropping the evidence.
- **Multiple accounts/portals affected** — repeat Step 3's comparison across accounts too, not just within one, before calling something "isolated" to a single portal. Each account that ends up mitigated needs its own Step 5 authorisation — approval for one account's fix is never approval for another's, even if they look identical.
- **The mitigation is itself a policy change** (not just a bug workaround) — say so in both the Step 5 confirmation and the final report, the same way removing `keep_article` changed Puma's actual refund policy, not just its bug exposure.
- **No headless-Chrome/Chromium available for the PDF export** — say so plainly rather than silently only delivering the HTML file; the artifact link and the HTML file still work as fallbacks for sharing.
