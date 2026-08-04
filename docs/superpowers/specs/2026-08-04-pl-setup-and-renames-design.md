# pl-setup command and pl-* rename — design

**Date:** 2026-08-04
**Status:** approved, ready for planning
**Repo:** `parcellab-claude-skills` (`jamie1leesmith-lgtm/parcellab-claude-skills`)

## Problem

Two problems, addressed together because they touch the same files.

### 1. Setup depends on a script that only exists on one laptop

Setup currently relies on the user pasting a prose prompt, documented in the
README, which asks Claude to configure the CLI, resolve the demo account, write
`PARCELLAB_ACCOUNT_ID`, and set the CLI edit-mode guard. For the Order API token
it relies on `~/.claude/scripts/set-parcellab-token.py`.

**That script is not in this repo.** It exists only on Jamie's machine. Nothing
in the repo references it. A teammate who installs `parcellab-create-order` and
follows the README reaches a step Claude cannot perform, and Claude will
improvise — most likely by asking for the token in chat, which writes a live
credential into the conversation transcript. That is the specific outcome the
hidden-input script was written to prevent.

A prose prompt is also an unreliable interface. "Set up parcelLab" may configure
only whichever skill was last mentioned, so the README has to specify exact
wording — a sign the interface is wrong, not that the wording needs work.

### 2. The `parcellab-` prefix collides with the org's CLI plugin

`parcellab-product-api` (from `parcelLab/parcellab-cli`) ships 24 skills. Their
skill names do not contain "parcellab" — `returns-v2-entrypoint`,
`product-feed-debug`, `carrier-checkpoint-debug` — so they match a `/parcellab`
search purely through their plugin prefix.

Typing `/parcellab` therefore returns **29 results: 24 the org's, 5 Jamie's**.
The five are 17% of the list and alphabetically interleaved with the rest. The
namespace does not distinguish "tools Jamie built" from "the org's Product API
config knowledge", and both are used regularly.

## Goals

- A teammate can set up every installed pL skill by typing one command, with no
  prose to remember and no missing dependency.
- A credential never enters the conversation transcript, and never enters a
  process argument list or shell history.
- `/pl` returns only Jamie's tools; `/parcellab` returns only the org's.
- Skills still trigger on the word "parcelLab" in ordinary prose.

## Non-goals

- Renaming the marketplace (`parcellab-skills`) or the GitHub repo. Ring 1 only:
  the identifiers typed to invoke a skill.
- Changing what any skill *does*, or the questions it asks.
- Resolving the `create-order` vs `order-lifecycle` naming ambiguity. Noted as a
  real ambiguity no prefix change fixes; deferred deliberately.
- The Cowork skill variants (`parcellab-sc-tools:*`), which live elsewhere.

## Architecture

### New plugin: `pl-setup`

```
plugins/pl-setup/
├── .claude-plugin/plugin.json
├── commands/pl-setup.md
├── scripts/pl-credentials.py
└── README.md
```

No skill. A command and a script.

Every pL plugin declares it as a dependency:

```json
{ "name": "pl-create-order", "dependencies": ["pl-setup"] }
```

Claude Code auto-installs dependencies, enables them transitively, and `plugin
prune` removes them when the last dependent goes. So a teammate installing any
pL plugin gets `pl-setup` without being told it exists, and setup cannot be
skipped by installing the "wrong" plugin.

> **Verify first, before building anything else.** The `dependencies` field is
> confirmed in the plugin reference, and the documented example includes a bare
> string form (`["helper-lib"]`). What is *not* confirmed is that a bare name
> resolves to a plugin in the same marketplace — it may require a
> `name@marketplace` form, or a version constraint. The entire architecture rests
> on this, so the first implementation task is a throwaway test: declare the
> dependency, install a dependent plugin into a scratch scope, and confirm
> `pl-setup` arrives on its own. If bare names do not resolve, the fallbacks in
> preference order are (a) the qualified `pl-setup@parcellab-skills` form, (b) the
> object form with an explicit version, (c) drop the dependency mechanism and
> state in the README that `pl-setup` must be installed alongside — which costs a
> documented manual step but nothing structural.

**Why a dedicated plugin.** The alternatives were rejected:

- *Command inside one existing plugin* — someone who installed only
  `pl-branded-template` would have no setup command, and telling them to install
  the order plugin to configure the layout plugin is incoherent.
- *Command duplicated into all five* — five copies of credential logic is the
  drift problem this marketplace exists to end, plus five competing `/pl-setup`
  entries.

**Why a command, not a skill.** Setup is deliberate and sequenced. It should run
when typed and must not trigger because someone said "set up a returns portal".
Consistent with `onyx-setup`.

### Script: `scripts/pl-credentials.py`

A port of the working `~/.claude/scripts/set-parcellab-token.py`, restructured to
match the shape of `setup-onyx.mjs`: small pure functions, importable and
testable, with `main()` behind an entry-point guard.

Python rather than Node, deliberately. Node has no `getpass` equivalent and would
need `/dev/tty` handling; Python's `getpass` is stdlib, macOS ships Python 3, and
this is the version already proven in use.

**Two modes:**

| Invocation | Behaviour |
|---|---|
| `pl-credentials.py --account <id>` | Writes `PARCELLAB_ACCOUNT_ID` only. No prompt, no secret. |
| `pl-credentials.py --token` | Hidden prompt via `getpass`, decodes, writes account ID + `PARCELLAB_TOKEN`. |

Account-only mode matters: `pl-branded-template`, `pl-demo-request` and
`pl-bug-investigation` need an account but no token. Nobody should be prompted
for a credential their skills don't use.

**The secret is never passed as an argument.** `--token` is a flag, not a
value — it triggers the hidden prompt. This is the one deliberate departure from
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
- Raw token with no `PARCELLAB_ACCOUNT_ID` already set → exit with a message
  saying to re-run with the base64 value.
- Credential's account ID differs from an existing `PARCELLAB_ACCOUNT_ID` →
  report both and ask which to keep. Silently overwriting is how someone ends up
  writing into a colleague's demo account.
- Invalid JSON in `settings.json` → refuse, leave the file untouched, say so.
- Never prints the secret. Confirms as `(set, N characters)`.
- Idempotent: updates keys in place, safe to re-run when a token rotates.

**Legacy alias.** `PARCELLAB_USER_ID` is accepted by the skills as a read-only
alias for `PARCELLAB_ACCOUNT_ID`, for setups predating the convention. The script
**writes only `PARCELLAB_ACCOUNT_ID`** and never writes the alias. If it finds
`PARCELLAB_USER_ID` present and `PARCELLAB_ACCOUNT_ID` absent, it treats the
alias's value as the existing account for mismatch-checking purposes, writes the
canonical key, and leaves the alias in place — removing it is a separate cleanup
decision, not something a credential script should do silently.

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
6. **Order API token, conditionally.** Check whether `pl-create-order` or
   `pl-order-lifecycle` is installed (`claude plugin list`). If neither, skip
   this step and say it was skipped. If either, print the exact command:

   ```
   python3 ${CLAUDE_PLUGIN_ROOT}/scripts/pl-credentials.py --token
   ```

   and tell the user: click the terminal icon at the top right, paste, press
   Enter, then paste the base64 value from the portal. State plainly that
   **nothing appears on screen while pasting the credential, and that is
   correct** — this is the single most common point of failure, because it reads
   as the input being broken.

   Claude must not offer to accept the token in chat, and must not read it from
   any file the user pastes a path to.
7. **Restart** — fully quit (⌘Q) and reopen. Environment variables are read only
   at startup, so nothing above takes effect until then.
8. **Verify** — after restart, ask *"which parcelLab account am I set up
   against?"* Claude should name the account and ID without asking anything.

The command never echoes a token and never writes one into its own output.

## Renames

Identifiers only. Descriptions keep "parcelLab" so prose triggering is unchanged.

| Now | After |
|---|---|
| `parcellab-brand-layout` (skill `…-desktop`) | `pl-branded-template` (plugin and skill) |
| `parcellab-create-order` | `pl-create-order` |
| `parcellab-demo-request` | `pl-demo-request` |
| `parcellab-order-lifecycle` | `pl-order-lifecycle` |
| `parcellab-bug-investigation` | `pl-bug-investigation` |
| — | `pl-setup` (new) |
| `onyx` | unchanged |
| `parcellab-product-api` | **untouched — not ours** |

Skill directory name matches its plugin name, as four of the five already do.
`-desktop` is dropped: it distinguished this skill from the Cowork variant, which
now lives in a separate repo, so the suffix marks a distinction that no longer
exists here.

### Files touched

- 5 × `plugin.json` — `name`, `version`, new `dependencies`
- 5 × `SKILL.md` frontmatter `name:`
- 5 × skill directory (`git mv`, to preserve history)
- `.claude-plugin/marketplace.json` — 5 entries plus `pl-setup`
- Root `README.md`
- `plugins/pl-create-order/skills/pl-create-order/README.md`
- 2 cross-references: `order-lifecycle` → `create-order`; brand-layout skill → its plugin

### The one trap

`pl-bug-investigation` references `parcellab-product-api` and
`parcellab-product-configuration`. **Those belong to the org's plugin and must
not be renamed.** A blind `parcellab-` → `pl-` replacement breaks the routing to
that entry point, and it fails as "the bug-investigation skill lost its config
knowledge" rather than as an obvious error. The lines keep `parcellab-` and get a
comment saying why, so a future find-and-replace doesn't reintroduce it.

### Versions

A rename creates a new plugin identity, so version continuity has no mechanical
meaning — but keep the lineage readable: carry the existing version and bump the
minor (`1.1.0` → `1.2.0`; `pl-demo-request` `1.0.0` → `1.1.0`). `pl-setup` starts
at `1.0.0`.

Bumping is mandatory, not cosmetic. Updates are gated on the `version` string,
not on git commits: push without bumping and `plugin update` reports "already at
the latest version" and does nothing, while fresh installs get the change — two
groups on silently different versions. This happened once already (`fe9efe6`,
fixed in `d0b766c`).

## Migration

The rename is breaking: Claude Code keys installs on `name@marketplace`, so the
old IDs go stale rather than following the rename.

Nobody outside Jamie's machine has these installed, so this is the last cheap
moment. Order, on Jamie's machine:

1. Push the release.
2. `claude plugin marketplace update parcellab-skills`
3. **Verify the new entries are present before removing anything** — the
   marketplace listing should show the `pl-*` names.
4. Uninstall the five old plugins.
5. Install the five new ones. `pl-setup` arrives automatically as a dependency.
6. Fully quit (⌘Q) and reopen.
7. Confirm `/pl` lists exactly the pL tools and `/parcellab` lists only the
   org's Product API skills.

Uninstall precedes install so the two never coexist — duplicate skills with
near-identical descriptions would make triggering nondeterministic. Step 3 is
what makes that safe: the new versions are confirmed available before the working
ones are removed.

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

- `decode`: valid base64 pair; base64 with no colon; non-base64; empty; non-numeric account ID; token containing a colon (split on the first only)
- `merge_env`: existing unrelated `env` keys preserved; existing plugin config preserved; missing `env` block created; re-run is idempotent
- `read_settings`: absent file → `{}`; empty file → `{}`; invalid JSON → raises, file unmodified
- `write_settings`: creates the directory; output is valid JSON; trailing newline

**Manual verification** — the parts no unit test covers:

- `/pl-setup` on a machine with no `PARCELLAB_ACCOUNT_ID` set
- `--token` prompt: confirm nothing echoes, and that the value lands correctly
- Confirm the secret appears in neither the transcript nor shell history
- A real order push through `pl-create-order` after restart, proving the token works
- `/pl` and `/parcellab` return disjoint sets
- `claude plugin install pl-branded-template@parcellab-skills` on its own pulls in `pl-setup`

## Documentation

- Root README: replace the "paste this exact prompt" block with `/pl-setup`.
  That block was a workaround for not having a command and becomes obsolete.
- Keep the hidden-input explanation, reframed: it is the designed flow, not an
  apology for a missing tool.
- Update the rename table and the install examples to `pl-*`.
- `pl-setup/README.md`: what it configures, the two script modes, and that it is
  installed automatically as a dependency.

## Open question, deliberately deferred

`pl-create-order` versus `pl-order-lifecycle` is a coin-flip from the names
alone. Renaming does not fix it, and fixing it properly may mean changing what
the skills ask or merging them — which is out of scope here. Revisit alongside
the skill-behaviour session.
