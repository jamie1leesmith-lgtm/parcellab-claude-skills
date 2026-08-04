# pl-tools consolidation, pl-setup command, and pl-* rename — design

**Date:** 2026-08-04
**Status:** approved, ready for planning
**Repo:** `parcellab-claude-skills` (`jamie1leesmith-lgtm/parcellab-claude-skills`)

## Problem

Three problems, addressed together because they touch the same files.

### 1. Setup depends on a script that only exists on one laptop

Setup currently relies on the user pasting a prose prompt, documented in the
README, which asks Claude to configure the CLI, resolve the demo account, write
`PARCELLAB_ACCOUNT_ID`, and set the CLI edit-mode guard. For the Order API token
it relies on `~/.claude/scripts/set-parcellab-token.py`.

**That script is not in this repo.** It exists only on Jamie's machine. Nothing
in the repo references it. A teammate who installs the order skill and follows
the README reaches a step Claude cannot perform, and Claude will improvise — most
likely by asking for the token in chat, which writes a live credential into the
conversation transcript. That is the specific outcome the hidden-input script was
written to prevent.

A prose prompt is also an unreliable interface. "Set up parcelLab" may configure
only whichever skill was last mentioned, so the README has to specify exact
wording — a sign the interface is wrong, not that the wording needs work.

### 2. The `parcellab-` prefix collides with the org's CLI plugin

`parcellab-product-api` (from `parcelLab/parcellab-cli`) ships 24 skills. Their
skill names contain no "parcellab" — `returns-v2-entrypoint`,
`product-feed-debug`, `carrier-checkpoint-debug` — so they match a `/parcellab`
search purely through their plugin prefix.

Typing `/parcellab` returns **29 results: 24 the org's, 5 Jamie's**. The five are
17% of the list, alphabetically interleaved. The namespace does not distinguish
"tools Jamie built" from "the org's Product API config knowledge", and both are
used regularly.

Because the collision is entirely in the *plugin* prefix, renaming the plugin is
what fixes it. The skill names underneath are free.

### 3. One plugin per skill is the wrong packaging

Five plugins each wrapping exactly one skill. The plugin groups nothing, so its
name and its skill's name collapse onto the same word
(`parcellab-create-order:parcellab-create-order`). Multi-skill plugins never
stutter — `parcellab-product-api:returns-v2-entrypoint`, `onyx:onyx-setup` —
because there the plugin groups and the skill identifies.

This is the shape you get building plugins one at a time, not the shape you would
choose designing the set as a whole. It also forces five version bumps per
release and, if setup lived in its own plugin, would require the plugin
dependency mechanism purely to hold the set together.

## Goals

- A teammate sets up every pL skill with one typed command — no prose to
  remember, no missing dependency.
- A credential never enters the conversation transcript, a process argument list,
  or shell history.
- `/pl` returns only Jamie's tools; `/parcellab` returns only the org's.
- Skills still trigger on the word "parcelLab" in ordinary prose.
- One version to bump per release.

## Non-goals

- Renaming the marketplace (`parcellab-skills`) or the GitHub repo. Ring 1 only:
  the identifiers typed to invoke a skill.
- Changing what any skill *does*, or the questions it asks.
- Resolving the `create-order` vs `order-lifecycle` ambiguity — real, but no
  rename fixes it. Deferred deliberately.
- The Cowork skill variants (`parcellab-sc-tools:*`), which live elsewhere.
- Merging `onyx` into `pl-tools`. It is a general Onyx bridge, not a parcelLab
  tool, and it carries its own MCP server and commands.

## Architecture

### One plugin: `pl-tools`

```
plugins/pl-tools/
├── .claude-plugin/plugin.json
├── commands/
│   └── pl-setup.md
├── scripts/
│   └── pl-credentials.py
├── README.md
└── skills/
    ├── branded-template/
    ├── bug-investigation/
    ├── create-order/
    ├── demo-request/
    └── order-lifecycle/
```

Five skills and one command in a single plugin. Handles become:

```
pl-tools:create-order       pl-tools:branded-template    pl-tools:demo-request
pl-tools:order-lifecycle    pl-tools:bug-investigation   pl-tools:pl-setup
```

`/pl` matches all six through the plugin prefix, which is the collision fix.

**Why one plugin rather than six.** The alternative — a dedicated `pl-setup`
plugin declared as a `dependencies` entry by five sibling plugins — needed the
plugin dependency mechanism solely to keep the set together. That mechanism is
documented but its bare-name resolution across a marketplace was unverified, so
the design would have rested on an untested assumption. Consolidating removes the
need for it entirely: setup is simply another command in the same plugin. Fewer
moving parts, one version, and the riskiest element of the design deleted rather
than mitigated.

**What consolidation costs.** Granular install goes away — the README's current
first line, *"Install skills individually — take only the ones you need"*, stops
being true. Every skill's description then loads in every session: ~918 measured
tokens always-on for six, against the ~2,529 the org's `parcellab-product-api`
already costs for 24. Accepted as the cheaper side of the trade.

**Command, not skill, for setup.** Setup is deliberate and sequenced. It should
run when typed, and must not trigger because someone said "set up a returns
portal". Consistent with `onyx-setup`.

**The command keeps the `pl-` prefix** — `pl-setup`, giving `pl-tools:pl-setup`.
Slightly redundant, deliberately: the bare form is invocable, and `/setup` is
generic enough to collide with any other plugin that ever ships one. The `onyx`
plugin already does this (`onyx:onyx-setup`) for the same reason.

**A side benefit.** With one plugin, `${CLAUDE_PLUGIN_ROOT}/scripts/` is shared
by every skill. Credential handling becomes one script the skills point at,
instead of the same guidance restated in five `SKILL.md` files.

### Script: `scripts/pl-credentials.py`

A port of the working `~/.claude/scripts/set-parcellab-token.py`, restructured to
match the shape of `setup-onyx.mjs`: small pure functions, importable and
testable, with `main()` behind an entry-point guard.

Python rather than Node, deliberately. Node has no `getpass` equivalent and would
need `/dev/tty` handling; Python's `getpass` is stdlib, macOS ships Python 3, and
this is the version already proven in use. It does mean the repo spans two
languages, since `setup-onyx.mjs` is Node — accepted, because correct secret
handling outweighs language uniformity.

**Two modes:**

| Invocation | Behaviour |
|---|---|
| `pl-credentials.py --account <id>` | Writes `PARCELLAB_ACCOUNT_ID` only. No prompt, no secret. |
| `pl-credentials.py --token` | Hidden prompt via `getpass`, decodes, writes account ID + `PARCELLAB_TOKEN`. |

Account-only mode matters: `branded-template`, `demo-request` and
`bug-investigation` need an account but no token. Nobody should be prompted for a
credential their skills don't use.

**The secret is never passed as an argument.** `--token` is a flag, not a
value — it triggers the hidden prompt. This is a deliberate departure from
`setup-onyx.mjs`, which takes `--token <value>` and thereby exposes a live
credential to the process table and shell history. `setup-onyx.mjs` is not being
changed here; the divergence is noted so a later pass can align it.

**Pure functions to be unit-tested:**

- `decode(value)` → `(account_id, token)` from base64 `accountId:token`, else `None`
- `merge_env(settings, updates)` → new settings dict, other keys untouched
- `read_settings(path)` → dict; raises on invalid JSON without writing
- `write_settings(path, settings)`

**Behaviours carried over from the working script:**

- Accepts the portal's base64 `accountId:token` *or* a raw token. Base64 is
  preferred and prompted for, because it supplies both values in one paste and
  removes the commonest setup error — pasting the base64 blob into a field
  expecting the raw token, which surfaces later as an unexplained `401`.
- Raw token with no `PARCELLAB_ACCOUNT_ID` set → exit saying to re-run with the
  base64 value.
- Credential's account ID differs from an existing `PARCELLAB_ACCOUNT_ID` →
  report both and ask which to keep. Silently overwriting is how someone ends up
  writing into a colleague's demo account.
- Invalid JSON in `settings.json` → refuse, leave the file untouched, say so.
- Never prints the secret. Confirms as `(set, N characters)`.
- Idempotent: updates keys in place, safe to re-run when a token rotates.

**Legacy alias.** `PARCELLAB_USER_ID` is accepted by the skills as a read-only
alias for `PARCELLAB_ACCOUNT_ID`. The script **writes only
`PARCELLAB_ACCOUNT_ID`** and never the alias. If it finds the alias present and
the canonical key absent, it treats the alias's value as the existing account for
mismatch-checking, writes the canonical key, and leaves the alias in place —
removing it is a separate cleanup decision, not something a credential script
should do silently.

### Command: `commands/pl-setup.md`

Instructions for Claude, following the `onyx-setup.md` pattern. Sequence:

1. **CLI present** — `parcellab --version`. Missing → say how to install, stop.
   Do not continue and do not guess.
2. **Authenticated** — `parcellab auth show`. Not authenticated → run
   `parcellab auth login`, which opens the browser.
3. **Resolve the account.**
   - `$PARCELLAB_ACCOUNT_ID` set → resolve its name with
     `parcellab account account show <id>` and confirm:
     *"Using **<name>** (`<id>`) — your default. Correct?"*
   - Not set → ask for the account name, find it with
     `parcellab account account search --name "<term>"`, confirm the match by
     name. Never present a bare number for confirmation: a wrong number looks
     fine, a wrong name is obvious.
4. **Write it** — `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/pl-credentials.py --account <id>`.
5. **Set the write guard** —
   `parcellab settings edit-mode set account-restricted --account <id>`, then
   verify with `parcellab settings edit-mode show`. Must be the user's own leaf
   account; a parent does not work. Without this the CLI can permit writes to a
   colleague's demo account and block the user's own, invisibly until a write
   fails. There are 13 demo accounts side by side under *Demo SolCon*.
6. **Order API token, conditionally.** Ask whether the user will use the order
   skills (`create-order`, `order-lifecycle`); only those two need a token. If
   not, skip and say it was skipped. If yes, print the exact command:

   ```
   python3 ${CLAUDE_PLUGIN_ROOT}/scripts/pl-credentials.py --token
   ```

   and tell the user: click the terminal icon at the top right, paste, press
   Enter, then paste the base64 value from the portal. State plainly that
   **nothing appears on screen while pasting the credential, and that is
   correct** — the single most common point of failure, because it reads as the
   input being broken.

   Claude must not offer to accept the token in chat, and must not read it from a
   file path the user pastes.

   > Conditional on a question rather than on detecting installed plugins:
   > consolidation means the order skills are always installed, so their presence
   > no longer indicates whether the user needs a token.

7. **Restart** — fully quit (⌘Q) and reopen. Environment variables are read only
   at startup, so nothing above takes effect until then.
8. **Verify** — after restart, ask *"which parcelLab account am I set up
   against?"* Claude should name the account and ID without asking anything.

The command never echoes a token and never writes one into its own output.

## Renames

Identifiers only. Descriptions keep "parcelLab" so prose triggering is unchanged.

| Now (plugin / skill) | After (plugin / skill) |
|---|---|
| `parcellab-brand-layout` / `parcellab-brand-layout-desktop` | `pl-tools` / `branded-template` |
| `parcellab-create-order` / `parcellab-create-order` | `pl-tools` / `create-order` |
| `parcellab-demo-request` / `parcellab-demo-request` | `pl-tools` / `demo-request` |
| `parcellab-order-lifecycle` / `parcellab-order-lifecycle` | `pl-tools` / `order-lifecycle` |
| `parcellab-bug-investigation` / `parcellab-bug-investigation` | `pl-tools` / `bug-investigation` |
| — | `pl-tools` / command `pl-setup` |
| `onyx` | unchanged |
| `parcellab-product-api` | **untouched — not ours** |

`-desktop` is dropped: it distinguished this skill from the Cowork variant, which
now lives in a separate repo, so the suffix marks a distinction that no longer
exists here.

### Files touched

- 5 × skill directory moved under `plugins/pl-tools/skills/` (`git mv`, to
  preserve history), each renamed
- 5 × `SKILL.md` frontmatter `name:` → unprefixed name
- 5 × old `plugin.json` deleted; 1 × new `pl-tools` manifest
- `.claude-plugin/marketplace.json` — six entries become two (`onyx`, `pl-tools`)
- Root `README.md` — install instructions, skill table, setup section, and the
  removal of the "install individually" premise
- `plugins/pl-tools/skills/create-order/README.md`
- 2 cross-references: `order-lifecycle` → `create-order`; the brand-layout skill
  → its own former plugin name

### The one trap

`bug-investigation` references `parcellab-product-api` and
`parcellab-product-configuration`. **Those belong to the org's plugin and must not
be renamed.** A blind `parcellab-` → `pl-` replacement breaks routing to that
entry point, and it fails as "the bug-investigation skill lost its config
knowledge" rather than as an obvious error. Those lines keep `parcellab-` and get
a comment saying why, so a future find-and-replace cannot reintroduce it.

That skill's dependency on the org plugin stays a **documented prerequisite**, as
it is today. Declaring it as a cross-marketplace `dependencies` entry was
available only under the multi-plugin design and is not adopted here.

### Version

`pl-tools` starts at **`2.0.0`**. It supersedes plugins that were at `1.1.0`, so
starting at `1.0.0` would read as a regression in the changelog.

Bumping on every release is mandatory, not cosmetic. Updates are gated on the
`version` string, not on git commits: push without bumping and `plugin update`
reports "already at the latest version" and does nothing, while fresh installs
get the change — two groups on silently different versions. This happened once
already (`fe9efe6`, fixed in `d0b766c`). Consolidation makes it much harder to
repeat, since there is now one number rather than five.

## Migration

Breaking: Claude Code keys installs on `name@marketplace`, so the old IDs go
stale rather than following the rename.

Nobody outside Jamie's machine has these installed, so this is the last cheap
moment. Order, on Jamie's machine:

1. Push the release.
2. `claude plugin marketplace update parcellab-skills`
3. **Verify `pl-tools` is listed before removing anything.**
4. Uninstall the five old plugins.
5. `claude plugin install pl-tools@parcellab-skills`
6. Fully quit (⌘Q) and reopen.
7. Confirm `/pl` lists the six pL handles and `/parcellab` lists only the org's
   Product API skills.

Uninstall precedes install so the two never coexist — duplicate skills with
near-identical descriptions would make triggering nondeterministic. Step 3 is what
makes that safe: the replacement is confirmed available before the working
versions are removed.

If a teammate has installed in the meantime, they follow the same sequence.

## Error handling

Every failure stops and reports. Nothing is guessed, nothing partially applied.

| Failure | Behaviour |
|---|---|
| CLI missing | Stop at step 1, say how to install |
| Not authenticated | Run `auth login`; if it fails, stop and report |
| Account name matches nothing | Report it, ask again — never pick a "closest" match |
| Account name matches several | List them with names and IDs, ask which |
| `settings.json` invalid JSON | Refuse, leave untouched, name the file and the parse error |
| Empty credential entered | Exit without changes |
| Raw token, no account ID set | Exit, say to re-run with the base64 value |
| Credential account ≠ existing account ID | Report both, ask which to keep |
| `edit-mode set` fails | Report; setup is incomplete, do not claim success |

## Testing

Per the project workflow, TDD: tests before implementation.

**Unit tests** on the pure functions, against a temp settings file:

- `decode`: valid base64 pair; base64 with no colon; non-base64; empty;
  non-numeric account ID; token containing a colon (split on the first only)
- `merge_env`: existing unrelated `env` keys preserved; existing plugin config
  preserved; missing `env` block created; re-run is idempotent
- `read_settings`: absent file → `{}`; empty file → `{}`; invalid JSON → raises,
  file unmodified
- `write_settings`: creates the directory; output is valid JSON; trailing newline

**Manual verification** — the parts no unit test covers:

- `/pl-setup` with no `PARCELLAB_ACCOUNT_ID` set
- `--token` prompt: nothing echoes, and the value lands correctly
- The secret appears in neither the transcript nor shell history
- A real order push through `create-order` after restart, proving the token works
- `/pl` and `/parcellab` return disjoint sets
- All five skills still trigger on prose containing "parcelLab", confirming the
  description-side wording was left intact
- `git log --follow` on a moved skill still shows its history

## Documentation

- Root README: replace the "paste this exact prompt" block with `/pl-setup`. That
  block was a workaround for not having a command and becomes obsolete.
- Remove the "install skills individually" premise; install is now one plugin.
- Keep the hidden-input explanation, reframed: it is the designed flow, not an
  apology for a missing tool.
- Update the skill table and install examples to the `pl-tools:*` handles.
- `plugins/pl-tools/README.md`: what the plugin contains, what `/pl-setup`
  configures, the two script modes, and which skills need a token.

## Open question, deliberately deferred

`create-order` versus `order-lifecycle` is a coin-flip from the names alone.
Renaming does not fix it, and fixing it properly may mean changing what the
skills ask or merging them — out of scope here. Revisit alongside the
skill-behaviour session.
