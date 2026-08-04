---
description: Update the parcelLab plugins to the latest version and report what changed
---

Update my parcelLab tooling to the latest version. Work through these steps and
report plainly — including when nothing changed.

## 1. Record what I have now

Run `claude plugin list` and note the current version of `pl-tools@parcellab-skills`
and, if it is installed, `onyx@parcellab-skills`. Keep these to compare against
afterwards.

Note: `pl-tools` has no pinned version string — its version is the git commit SHA
of the marketplace repo, so expect a SHA rather than something like `2.0.1`.

## 2. Refresh the marketplace catalogue

`claude plugin marketplace update parcellab-skills`

This re-clones the marketplace so Claude Code can see what is now available. It
does **not** update any plugin on its own. If it fails, stop and report it — the
usual causes are no network, or my GitHub access to the private repo having lapsed.

## 3. Update pl-tools

`claude plugin update pl-tools@parcellab-skills`

## 4. Update onyx, only if it is installed

If step 1 showed `onyx@parcellab-skills`, run:

`claude plugin update onyx@parcellab-skills`

If it is not installed, skip this and do not offer to install it — not everyone
wants Onyx.

Do **not** touch `parcellab-product-api@parcellab`. That is the org's plugin from
`parcelLab/parcellab-cli`, not ours, and it updates on its own schedule.

## 5. Tell me what actually happened

One line, because "update" reads as success even when nothing moved:

- **Updated** — *"Your parcelLab skills have been updated. You'll need to restart."*
- **Already current** — *"Already up to date — nothing changed, no restart needed."*
  Don't dress this up as success; I need to know whether to restart.
- **Failed** — report the error verbatim. Don't retry silently.

Don't print version numbers or SHAs. They mean nothing to most of the team and
make a working update look like a problem.

## 5a. Show me what changed, as a table

**This is expected, not optional.** Report only **skills that are new or that now
behave differently**. Everything else is noise.

Work out which skills actually changed:

```bash
cd ~/.claude/plugins/marketplaces/parcellab-skills

# Which skills and commands were touched
git diff --name-only <old-version>..<new-version> -- plugins/ \
  | grep -E '/(skills|commands)/' | cut -d/ -f1-4 | sort -u

# Which of them are brand new
git diff --diff-filter=A --name-only <old-version>..<new-version> -- plugins/ \
  | grep -E '/skills/[^/]+/SKILL\.md$'
```

Filter with `grep` rather than a git pathspec like `-- 'plugins/*/skills/'`. That
quoted form matches **nothing** and returns an empty list, so a release that added a
whole new skill reports as "no skills changed" — check it yourself against a known
release if you ever swap it back. Then read each affected skill's own `SKILL.md` to
describe what it does, rather than paraphrasing commit messages.

Report it like this — one row per skill, nothing else:

| Skill | Change | What it means for you |
|---|---|---|
| `shopify-seed` | **New** | Loads a prospect's real products into your Shopify demo store. Ask for *"seed acme.com's products into my Shopify store"*. |
| `create-order` | **Fixed** | Orders to Ireland used to fail. They now work — worth re-testing if you hit that. |
| `demo-request` | **Updated** | Now asks you to approve the product images before submitting. |

Rules for the table:

- **Only new or functionally-changed skills get a row.** A skill nobody touched
  doesn't appear at all — don't add rows saying "unchanged".
- Use **New**, **Updated**, or **Fixed**. Say **Fixed** whenever a skill went from
  broken to working, and lead with those rows — they're the ones worth re-testing.
- If a skill now **asks something new, or needs something installed**, say so in its
  row. That's the change most likely to surprise someone mid-task.
- Write for someone who doesn't know how any of this is built. No jargon.

**Leave all of this out of the report** — it confuses the less technical half of the
team and none of it changes how they use a skill: version numbers and commit SHAs,
commit messages, file paths, line or test counts, internal script names, repo
plumbing (`.gitignore`, CI, bytecode), and anything under `docs/`, `README.md` or a
plan or spec file. A design document changing is not a change to somebody's tooling.

**If no skill changed** — only internals or docs moved — say exactly that in one
line: *"Nothing changed about the skills themselves this time."* Then follow step 6,
because the plugin version still moved.

If the diff is empty or unreadable, say so plainly. Don't invent a summary, and
don't describe changes you haven't read.

## 6. Restart, only if a version actually moved

**If anything updated at all** — even when no skill changed — tell me to **fully quit
Claude Code (⌘Q, not just closing the window) and reopen it.** Skills are loaded when
the app starts, so until I do that I'm still running the old ones no matter what the
update said. This is the step people skip.

**If everything was already current**, say plainly that no restart is needed.

Those are different cases: "no skill changed but the version moved" still needs a
restart. Don't collapse the two.

## 7. If a skill has gone missing after updating

If I say a skill has vanished, check `claude plugin details pl-tools@parcellab-skills`
and compare its skill list against `plugins/pl-tools/skills/` in the marketplace
clone. The usual cause is a `SKILL.md` whose frontmatter `name:` does not match its
directory name — that makes the skill disappear from the inventory with no error.
Report which one, rather than guessing at a fix.
