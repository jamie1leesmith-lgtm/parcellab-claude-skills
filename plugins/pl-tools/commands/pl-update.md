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

Be specific, because "update" reads as success even when nothing moved:

- **Updated** — say so, and name the old and new versions:
  *"pl-tools updated. You need to restart."*
- **Already current** — say that plainly:
  *"Already up to date — nothing changed, no restart needed."* Do not dress this
  up as success; I need to know whether to restart.
- **Failed** — report the error verbatim. Do not retry silently.

## 5a. Always tell me what actually changed

**This is expected, not optional.** "Updated to `59edc95ed68f`" tells me nothing —
a SHA is not a changelog, and without a summary I have no idea whether the update
matters to me or which skills to re-test.

The marketplace clone was re-cloned at step 2, so it already contains the new
commits. Diff the version I had against the version I now have:

```bash
cd ~/.claude/plugins/marketplaces/parcellab-skills
git log --oneline <old-version-from-step-1>..<new-version-from-step-3>
```

Then summarise it **by skill and by what it means for me**, not as a raw commit
list. Group related commits — five commits touching one skill is one change to me.
Separate user-facing changes from docs and internals, and lead with anything that
alters how a skill behaves or what it asks. Say explicitly when a skill went from
broken to working, or gained a new question, since those are the ones worth
re-testing.

**If the old version was a pinned semver rather than a SHA** (older installs may
show something like `2.0.1`), `git log 2.0.1..<sha>` fails — the tag doesn't exist.
Fall back to `git log --oneline -15` and say the range is approximate rather than
exact.

If the log is genuinely empty or unreadable, say so plainly. Don't invent a summary,
and don't describe changes you haven't read.

## 6. Restart, only if something changed

If anything updated, tell me to **fully quit Claude Code (Cmd-Q, not just closing
the window) and reopen it.** Plugins are loaded at startup, so until I do that I am
still running the old code even though the files on disk are new. This is the step
people skip.

If nothing changed, tell me explicitly that no restart is needed.

## 7. If a skill has gone missing after updating

If I say a skill has vanished, check `claude plugin details pl-tools@parcellab-skills`
and compare its skill list against `plugins/pl-tools/skills/` in the marketplace
clone. The usual cause is a `SKILL.md` whose frontmatter `name:` does not match its
directory name — that makes the skill disappear from the inventory with no error.
Report which one, rather than guessing at a fix.
