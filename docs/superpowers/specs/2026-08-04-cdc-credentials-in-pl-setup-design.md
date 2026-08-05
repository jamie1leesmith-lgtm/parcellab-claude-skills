# CDC credentials folded into /pl-setup — design

**Date:** 2026-08-04
**Status:** approved, implementing directly (writing-plans skipped — small, well-scoped change)
**Repo:** `parcellab-claude-skills` (`jamie1leesmith-lgtm/parcellab-claude-skills`)

## Problem

`pl-tools:demo-request` needs `CDC_DEMO_API_BASE_URL` and `CDC_DEMO_API_TOKEN` to
submit to the Custom Demo Creator API. These live in a bespoke dotenv file,
`~/.claude/parcellab-demo-request.env`, parsed directly by
`scripts/submit_demo_request.mjs` — not in the `env` block of
`~/.claude/settings.json` that every other credential in this plugin uses.

**Nothing sets this file up.** `/pl-setup` and `pl_credentials.py` only know about
`PARCELLAB_ACCOUNT_ID`, `PARCELLAB_TOKEN`, and (incidentally, since they share the
same settings file) Onyx's keys. A new teammate installing `pl-tools` and running
`demo-request` has no command, no script, and no prompt telling them this file
needs to exist — they would discover the requirement only by reading
`SKILL.md`'s "Required Environment" section and creating the file by hand.

On Jamie's machine the file already exists, dated 2026-06-01 — it predates this
plugin's consolidation entirely, which is exactly why `pl-setup` never learned
about it.

**Secondary defect found while reading the code, fixed as part of this change:**
`SKILL.md` line 229 has the skill run `source ~/.claude/parcellab-demo-request.env`
before submitting. This does nothing useful: `submit_demo_request.mjs` already
reads the file itself via `parseEnvFile(CONFIG_PATH)`, and each Bash tool call is a
separate process, so anything the `source` exported would not survive into the next
call that runs `node` anyway.

## Goals

- `/pl-setup` collects the CDC token through the same mechanism as every other
  secret in this plugin: hidden terminal input, never chat, never a command-line
  argument.
- A teammate who has never heard of the CDC API gets prompted for exactly one
  value — the token — not two.
- `submit_demo_request.mjs` requires **no code change**.
- The dead `source` line is removed.

## Non-goals

- Deleting `~/.claude/parcellab-demo-request.env`. It becomes an unused fallback,
  not a conflict — `process.env` already wins over it in the script's lookup order.
- Changing anything about how `demo-request` researches or submits — this is
  credentials only.
- A full `writing-plans` implementation plan. Jamie asked to skip it for this
  change; design approval here is followed directly by implementation.

## Design

### Storage: `settings.json`'s `env` block, not a new dotenv writer

Considered and rejected: teaching `pl_credentials.py` to also write
`~/.claude/parcellab-demo-request.env`. That would need zero change to
`submit_demo_request.mjs` (it already parses that exact path), but it leaves the
plugin with **two credential storage mechanisms** side by side — one file for four
keys, a second file for two more. A future skill needing a fifth credential would
have no obvious pattern to follow.

Writing to `settings.json`'s `env` block instead means:

- `submit_demo_request.mjs` needs **no change at all**. Its lookup is
  `process.env.CDC_DEMO_API_TOKEN || config.CDC_DEMO_API_TOKEN` — `process.env`
  already wins, so a value in `settings.json` (which Claude Code exposes as an
  environment variable at startup) is picked up automatically.
- One mechanism, one script, one file, for every credential the plugin manages.

### Base URL: hardcoded default, not a second prompt

The script's own fallback (`http://localhost:3000`) is a dev-testing default, not a
real endpoint — using it in practice would just fail with a connection error, which
is at least loud rather than silently wrong.

Jamie's first candidate for the real URL, `https://experience.parcellab.com/requests`,
turned out to be the **portal page** a human visits, not the API base — confirmed
by comparing string length against the value already configured and working in
Jamie's dotenv file (32 characters both). The script appends a fixed path:

```js
fetch(`${baseUrl}/api/automation/demo-requests`)
```

`.../requests` as the base would have produced
`.../requests/api/automation/demo-requests` — a duplicated path segment that would
have 404'd. The correct value, matching what's already deployed and working, is:

```
https://experience.parcellab.com
```

This ships as a hardcoded default in `pl_credentials.py`. `/pl-setup` does **not**
prompt for it — one value to type, not two. If a different CDC environment is ever
needed, the mechanism to override is the same as everywhere else: set the env var
by hand, since `process.env` takes priority over anything the script writes.

### `pl_credentials.py`: a new `--cdc-token` mode

Mirrors `--token`'s shape exactly, with one simplification:

| | `--token` (Order API) | `--cdc-token` (CDC) |
|---|---|---|
| Prompt | hidden, `getpass` | hidden, `getpass` |
| Accepts | base64 `accountId:token` pair, or raw token | a single bearer token — no decode |
| Writes | `PARCELLAB_ACCOUNT_ID` + `PARCELLAB_TOKEN` | `CDC_DEMO_API_TOKEN` + `CDC_DEMO_API_BASE_URL` (the hardcoded default, unless overridden) |
| Merge | `merge_env` (existing, reused as-is) | `merge_env` (same function, no changes needed) |

**No decode/split logic applies.** The Order API's base64 form exists because one
paste needs to yield two independent values (account ID and token) that didn't
otherwise share a source. The CDC token is one value with one destination — added
complexity here would solve a problem this credential doesn't have.

Same non-negotiables as every existing mode, inherited rather than re-specified:

- **Never a command-line argument.** `--cdc-token` is a bare flag that triggers the
  prompt, exactly like `--token` — a secret must never be able to reach argv, the
  process table, or shell history.
- **Never echoed.** Confirmed only as `(set, N characters)`.
- **Idempotent.** Re-running updates in place via `merge_env`.

### `/pl-setup`: a new step, same shape as the Order API token step

Positioned after the existing Order API token step. Logic:

1. **Check first.** If `$CDC_DEMO_API_TOKEN` is already set, say so and skip — do
   not ask for a credential the user already has.
2. **Ask only if unset, and only if relevant.** Ask whether the user will use
   `demo-request`. If not, skip and say so.
3. **If yes:** print the exact command
   (`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/pl_credentials.py --cdc-token`) and the
   same terminal instructions already given for the Order API token — click the
   terminal icon, paste, press Enter, nothing will appear on screen and that is
   correct.

This mirrors the Order API token step closely enough that most of its wording is
reusable rather than newly written.

### `demo-request/SKILL.md`: two edits

1. **`Required Environment` section rewritten.** Replace the manual
   "create this file with these two lines" instructions with a pointer to
   `/pl-setup`, matching how `create-order` and `order-lifecycle` describe their
   credential prerequisites (a see-also, not inline setup steps).
2. **Delete the dead `source ~/.claude/parcellab-demo-request.env` line** (line 229)
   from the submit step. It has never done anything useful.

### What's explicitly not touched

`~/.claude/parcellab-demo-request.env` stays on disk, unreferenced by any new code
path. It is not a conflict: if it ever contained a *different* token than
`settings.json`, `process.env` (populated from `settings.json`) still wins, so
there is exactly one source of truth once this ships. Deleting the old file is a
separate, optional cleanup Jamie can do at his convenience — not part of this
change.

## Testing

Extend `scripts/tests/test_pl_credentials.py` with the same shape of cases
`--token` already has, adapted for the simpler single-value flow:

- `run_cdc_token`: writes `CDC_DEMO_API_TOKEN` and the default
  `CDC_DEMO_API_BASE_URL`; existing unrelated `env` keys and non-`env` settings
  keys survive; idempotent on re-run.
- Empty input → no changes, same as `run_token`'s empty-input case.

**Manual verification** (the parts no unit test covers):

- `/pl-setup` on a machine where `$CDC_DEMO_API_TOKEN` is unset: prompts once,
  hidden input confirmed via terminal (no dots, no asterisks).
- `/pl-setup` re-run with the token already set: skips the step, says so.
- A real `demo-request` submission after this change, proving
  `submit_demo_request.mjs` picks up the `settings.json`-sourced env var with zero
  code change on its side.
