# parcellab-claude-skills

A private Claude Code plugin marketplace distributing internal parcelLab tooling to
Jamie's team. Two plugins: **`pl-tools`** (seven skills + `/pl-setup` + `/pl-update`)
and **`onyx`** (Onyx knowledge bridge, own MCP server).

Full detail is in [README.md](README.md). This file carries the rules whose failure
modes are **silent** — where getting it wrong produces no error, just something
quietly not working.

## Creating or editing a skill

**Use `/anthropic-skills:skill-creator`.** Don't hand-roll a `SKILL.md` and don't
copy an existing skill and edit it — that's how conventions drift. For anything
beyond a trivial fix, plan it first with `superpowers:brainstorming`, then
`superpowers:writing-plans`.

New parcelLab skills go in `plugins/pl-tools/skills/<name>/`. No new plugin, no new
marketplace entry.

### Silent failure modes

- **Frontmatter `name:` must equal the directory name.** A mismatch removes the
  skill from the plugin inventory with no error. First thing to check when a skill
  "didn't install".
- **`description:` is the trigger text, not a label.** Claude matches requests
  against it. **Keep the word "parcelLab" spelled out** — that's what makes
  *"push a parcelLab order"* work. Never edit a description during a rename.
- **Don't prefix skill directories with `pl-`.** The `pl-tools:` prefix already
  namespaces them. Exception: the commands `pl-setup` and `pl-update`, whose bare
  forms would otherwise be generically collidable.
- **Reference files via `${CLAUDE_PLUGIN_ROOT}`.** Never `~/.claude/skills/…`, never
  a path relative to this repo. Installed users run from
  `~/.claude/plugins/cache/parcellab-skills/pl-tools/<version>/`. `demo-request`
  shipped a broken submit step for weeks by pointing at the old hand-copied
  location.

## Releasing

**Commit, push to `main`, tell the team to run `/pl-update`.** That's the whole
process.

**`pl-tools` has no `version` field, deliberately** — its version resolves to the
git commit SHA, so every push is automatically a new version. Consequences, all
intentional: `plugin list` shows a SHA, and `plugin validate` permanently warns
*"No version specified"*. **Do not "fix" that warning by adding a version** —
pinning it means every future release silently reaches nobody unless someone
remembers to bump. That already happened once (`fe9efe6`, fixed in `d0b766c`).

`onyx` **does** pin a version — bump it when changing that plugin.

Nothing updates itself: no notification, no background pull. Teammates run the code
they installed until they run `/pl-update`.

## Never rename these `parcellab-*` strings

A find-and-replace across the repo breaks working behaviour without producing
errors:

| String | Why |
|---|---|
| `parcellab-product-api`, `parcellab-product-configuration` | The **org's** plugin (`parcelLab/parcellab-cli`). `bug-investigation` routes to it. |
| `parcellab-brand-layout` | The **external** Cowork/CLI variant in another repo, referenced for contrast by `branded-template`. Not this skill. |
| `$HOME/parcellab-previews/`, `{brand}-parcellab-layout.html` | A real directory and real output filenames. |
| `~/.claude/parcellab-demo-request.env` | A user config file that exists on disk. |
| `parcellab-demo-request-scripts` | An npm package name. |

The first two have HTML comments in their `SKILL.md` saying so. Renaming a *plugin*
is safe if you add a `renames` entry to `marketplace.json` — treat that map as
append-only.

## Credentials

**Never accept a credential in chat** — chat is stored in the transcript. Route
secrets through `${CLAUDE_PLUGIN_ROOT}/scripts/pl_credentials.py --token`, which
prompts with hidden input, and have the user run it in the app's built-in terminal.
Never pass a secret as a command-line argument (process table, shell history).

`PARCELLAB_ACCOUNT_ID` lives in the `env` block of the user's global
`~/.claude/settings.json`. `PARCELLAB_USER_ID` is a legacy read-only alias — accept
it, never write it. Env vars are read only at app startup, so any change needs a
full quit (⌘Q).

**Any skill writing to a parcelLab account confirms it first by name**, not by
number — resolve with `parcellab account account show <id>` and ask before the first
write. There are 13 demo accounts side by side under *Demo SolCon*.

## Conventions

- **Tests are stdlib `unittest`.** `pytest` is not installed; never `pip install`.
  Run: `cd plugins/pl-tools/scripts && python3 -m unittest discover -s tests -v`.
- The CLI binary is **`parcellab`**; `parcellab-cli` is the repo it ships from.
  `parcellab --version` **does not exist** — use `command -v parcellab`.
- **GitHub: personal account only** (`jamie1leesmith-lgtm`). Never push to the
  `parcelLab` org. Check `git remote -v` before pushing.
- Never commit `node_modules`.
