# Moving to the parcelLab skills marketplace

If you're running any parcelLab Claude skill that you got by having a
`SKILL.md` file copied to you directly — rather than installed from a
marketplace — this is for you.

## Why move

Claude picks which skill to run for a request by matching your words against
each skill's **description**, not its filename. A hand-copied skill and the
marketplace's version of it can carry near-identical descriptions, so both
match the same request — and you have no control over which one wins. The
hand-copied one is frozen at whatever day it was copied. It never gets fixes.

That's not theoretical. While building this out, real bugs were found and
fixed that a hand-copied skill would never receive:

- **`create-order` silently defaulted to a German address** whenever no country
  was specified, instead of asking. Fixed to always ask.
- **`demo-request` was completely broken** — it required a browser tool that
  isn't installed, so it couldn't run at all. Fixed to use the browser tool
  Claude Code actually ships with.
- **The account write-guard wasn't set** on at least one working setup, meaning
  a skill could have written into a colleague's demo account with no warning.

If you're on a hand-copied version of any of these, you're running code from
before all three of those fixes — and won't get the next ones either.

## What to do

**1. Install from the marketplace**, if you haven't already:

- Desktop app: **+** → **Plugins** → **Add plugin** → source
  `jamie1leesmith-lgtm/parcellab-claude-skills` → install **`pl-tools`**
- CLI:
  ```
  /plugin marketplace add jamie1leesmith-lgtm/parcellab-claude-skills
  /plugin install pl-tools@parcellab-skills
  ```

**2. In a new conversation, run `/pl-setup`.**

It now checks for hand-copied skills automatically and will tell you — by
name — if it finds one in `~/.claude/skills/`. Follow what it says: it moves
the old copy aside (not deletes it) so you can get it back if something's
missing, and then asks you to restart.

If you'd rather check yourself first:

```bash
ls ~/.claude/skills/
```

Anything parcelLab- or pl-tools-named in that list is a hand-copied copy —
skills installed as a plugin never live there.

**3. Fully quit and reopen the app (⌘Q)** — plugins and any change to
`~/.claude/skills/` are only picked up at startup.

## Questions

Ask Jamie (`jamie1leesmith-lgtm`). This is his repo — private, invite-only —
so he can also add you as a collaborator if you don't have access yet.
