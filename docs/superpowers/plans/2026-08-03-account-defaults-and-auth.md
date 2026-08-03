# Account Defaults and Auth Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every skill in this marketplace one shared default account that it
confirms before writing, and make the Order API token a one-time setup a
desktop-app user can complete without a terminal.

**Architecture:** Two canonical instruction blocks are defined once in Task 1 and
pasted byte-identically into each skill's `SKILL.md`. The root `README.md` is the
single source of truth for maintainers. No shared plugin, no slash command, no
setup script — the audience uses the desktop app, so Claude performs setup inside
the conversation.

**Tech Stack:** Markdown skill files, `plugin.json` manifests, the `parcellab`
CLI (Product API, OAuth device flow), the ParcelLab Order API (base64
`accountID:token`).

**Spec:** `docs/superpowers/specs/2026-08-03-account-defaults-and-auth-design.md`

## Global Constraints

Every task's requirements implicitly include these. Values are verbatim from the
spec.

- `PARCELLAB_ACCOUNT_ID` is canonical. `PARCELLAB_USER_ID` is accepted as an
  alias at **lower** precedence. Never write the old name.
- `PARCELLAB_TOKEN` is required **only** by `parcellab-create-order` and
  `parcellab-order-lifecycle`.
- Both variables live in the `env` block of the global `~/.claude/settings.json`.
- The CLI binary is **`parcellab`**. `parcellab-cli` is the repo name and must
  never appear as a command.
- Token intake asks for the **base64 blob** (`accountID:token`) in preference to
  the raw token. Raw is a fallback.
- Skills must never echo a token back into the transcript.
- Any credentials-missing message opens with the restart instruction.
- Confirm the account **once per conversation, before the first write**. Read-only
  inspection is ungated.
- `parcellab auth login` must be run in the background — it blocks on browser
  approval.
- Brand-layout's MCP→CLI swap is **last** and is its own task, so it can be
  abandoned without unpicking anything else.

## File Structure

| File | Responsibility |
|---|---|
| `README.md` | Source of truth: the convention, the setup flow, per-skill prerequisites |
| `plugins/parcellab-create-order/skills/parcellab-create-order/SKILL.md` | Order API skill — account resolution, confirm gate, setup on missing creds |
| `plugins/parcellab-create-order/skills/parcellab-create-order/README.md` | Remove stale pre-plugin install instructions |
| `plugins/parcellab-order-lifecycle/skills/parcellab-order-lifecycle/SKILL.md` | Same as create-order; replaces the interim finding-1 stop message |
| `plugins/parcellab-bug-investigation/skills/parcellab-bug-investigation/SKILL.md` | Binary name correction + convention adoption |
| `plugins/parcellab-brand-layout/skills/parcellab-brand-layout-desktop/SKILL.md` | Convention adoption, then the CLI swap |
| `plugins/*/.claude-plugin/plugin.json` | Version bumps so installed users receive updates |

---

### Task 1: Define the canonical blocks and rewrite the root README

Reconciles the interim finding-1 work already uncommitted on this branch. Those
edits used `PARCELLAB_USER_ID` as canonical and told the user to hand-edit
`settings.json` — both wrong under this design. Replace, don't layer.

**Files:**
- Modify: `README.md`

**Interfaces:**
- Produces: **Block A (Account resolution and confirmation)** and **Block B
  (Credentials missing)**, reproduced verbatim below. Tasks 2–5 paste these
  byte-identically. Task 6 relies on Block A already being present in
  brand-layout.

- [ ] **Step 1: Replace the interim credentials section**

Delete the `#### Setting up ParcelLab Order API credentials` section added
earlier on this branch and the modified `parcellab-order-lifecycle` prerequisites
that link to it. They are superseded.

- [ ] **Step 2: Add the convention section to `README.md`**

Insert before the per-skill sections, after the "Available skills" table:

````markdown
## Your default account

Every skill here writes into a parcelLab account. Rather than naming one each
time, they all read a single default and confirm it before writing anything.

`PARCELLAB_ACCOUNT_ID` in the `env` block of your global `~/.claude/settings.json`
holds your demo account:

```json
{ "env": { "PARCELLAB_ACCOUNT_ID": "1626718" } }
```

You do not set this up by hand. Ask Claude to set up your parcelLab skills, or
just use a skill — the first run walks you through it, looks your account up by
name, and writes the file for you.

Two skills additionally need an Order API token (`PARCELLAB_TOKEN`):
`parcellab-create-order` and `parcellab-order-lifecycle`. Nothing else does.

> `PARCELLAB_USER_ID` is still accepted as an alias for
> `PARCELLAB_ACCOUNT_ID`, so anyone set up before this convention keeps working.
> New setups use `PARCELLAB_ACCOUNT_ID`.

### One-time setup

You need the parcelLab CLI installed — internal users have this already. Then, in
the Claude Code desktop app:

1. Install the skills you want: **+** → **Plugins** → **Add plugin** →
   marketplace source `jamie1leesmith-lgtm/parcellab-claude-skills`.
2. Start a conversation and say *"set up my parcelLab skills"*.
3. Claude checks the CLI is reachable, logs you in (`parcellab auth login` opens
   your browser), finds your demo account by name, and writes it to
   `settings.json` — you approve the edit when prompted.
4. For the two order skills, Claude asks for your Order API credential. **Paste
   the base64-encoded value from the portal** — it contains both your account ID
   and token, so one paste covers everything. The raw token works too, it just
   takes an extra step.
5. **Quit and reopen the app.** Environment variables are only read at startup,
   so nothing above takes effect until you do.

Everything after that is automatic. Before any skill writes to your account it
confirms which one:

> Using **Acme Demo** (`1626718`) — your default. Correct, or use a different
> account?
````

- [ ] **Step 3: Update the per-skill prerequisites**

Replace the prerequisites for `parcellab-create-order`, `parcellab-order-lifecycle`,
`parcellab-brand-layout` and `parcellab-bug-investigation` with a pointer to
[Your default account](#your-default-account), noting for the two order skills
that they also need `PARCELLAB_TOKEN`. Leave `parcellab-demo-request` and `onyx`
untouched — they have no ParcelLab account concept and their own setup is tracked
separately.

- [ ] **Step 4: Record Block A verbatim in this plan's terms**

This is the text Tasks 2–5 paste into each `SKILL.md`, unchanged:

````markdown
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
````

- [ ] **Step 5: Record Block B verbatim**

````markdown
### If credentials are missing

Stop. Do not guess values and do not proceed. Say this:

> **If you have just set these up, quit and reopen the app** — environment
> variables are only read at startup.
>
> Otherwise, let's set them up now. I need your parcelLab Order API credential.
> In the portal it's shown as a base64 value — paste that and I'll handle the
> rest. (A raw token works too; I'll just need your account ID as well.)

On receiving a base64 value: decode it, split on the first `:` — the part before
is the account ID, the part after is the token. This is why the base64 form is
preferred: one paste gives both, and it removes the commonest setup error, which
is pasting the whole encoded blob in as the token and getting an unexplained
`401`.

Write both to the `env` block of `~/.claude/settings.json`, merging into any
existing `env` block rather than replacing it. Then tell the user to quit and
reopen the app.

Never print the token back to the user or repeat it anywhere in your reply.
````

- [ ] **Step 6: Verify**

```bash
cd ~/parcellab-claude-skills
grep -c "PARCELLAB_ACCOUNT_ID" README.md          # expect >= 3
grep -c "Setting up ParcelLab Order API" README.md # expect 0 — interim section gone
grep -n "your-default-account" README.md           # anchor link resolves to the new heading
```

- [ ] **Step 7: Commit**

```bash
git add README.md docs/superpowers/
git commit -m "docs: add default-account convention and desktop-app setup flow"
```

---

### Task 2: parcellab-create-order

**Files:**
- Modify: `plugins/parcellab-create-order/skills/parcellab-create-order/SKILL.md`
- Modify: `plugins/parcellab-create-order/skills/parcellab-create-order/README.md`
- Modify: `plugins/parcellab-create-order/.claude-plugin/plugin.json`

**Interfaces:**
- Consumes: Block A and Block B from Task 1, verbatim.

- [ ] **Step 1: Replace step 1 of the workflow in `SKILL.md`**

The current step is `**Confirm credentials are present.** Check PARCELLAB_USER_ID
and PARCELLAB_TOKEN are set…`. Replace with a reference to Block A's resolution
order and Block B on failure, keeping the existing `test -n` check but against
both variable names:

```bash
test -n "${PARCELLAB_ACCOUNT_ID:-$PARCELLAB_USER_ID}" && test -n "$PARCELLAB_TOKEN" && echo ok
```

- [ ] **Step 2: Paste Block A and Block B into `SKILL.md`**

As a new `## Account resolution and confirmation` section immediately after the
workflow list, byte-identical to Task 1.

- [ ] **Step 3: Fix the auth header construction**

The existing `AUTH=$(printf '%s:%s' "$PARCELLAB_USER_ID" "$PARCELLAB_TOKEN" | base64)`
must read the canonical name first:

```bash
AUTH=$(printf '%s:%s' "${PARCELLAB_ACCOUNT_ID:-$PARCELLAB_USER_ID}" "$PARCELLAB_TOKEN" | base64)
```

- [ ] **Step 4: Delete the stale install instructions from `README.md`**

Remove the `## Installation (for someone new)` section's step 1 — *"Copy this
folder to `~/.claude/skills/parcellab-create-order/`"* — which predates these
being plugins and contradicts the plugin install. Replace the whole section with
a pointer to the root README's [Your default account](../../../../README.md#your-default-account).
Keep the "Design decisions and why" and "Courier codes" sections — they are still
accurate and are the only record of that reasoning.

- [ ] **Step 5: Bump the version**

`1.0.0` → `1.1.0` in `plugin.json` (behaviour change, not a fix).

- [ ] **Step 6: Verify**

```bash
cd ~/parcellab-claude-skills
P=plugins/parcellab-create-order
python3 -c "import json;json.load(open('$P/.claude-plugin/plugin.json'));print('json ok')"
grep -c "PARCELLAB_ACCOUNT_ID" $P/skills/parcellab-create-order/SKILL.md   # expect >= 3
grep -rn "~/.claude/skills/parcellab-create-order" $P/ ; echo "exit=$? (1 = stale instruction gone)"
```

- [ ] **Step 7: Commit**

```bash
git add plugins/parcellab-create-order
git commit -m "feat(create-order): adopt default account convention and confirm before writing"
```

---

### Task 3: parcellab-order-lifecycle

**Files:**
- Modify: `plugins/parcellab-order-lifecycle/skills/parcellab-order-lifecycle/SKILL.md`
- Modify: `plugins/parcellab-order-lifecycle/skills/parcellab-order-lifecycle/references/run-lifecycle.sh`
- Modify: `plugins/parcellab-order-lifecycle/.claude-plugin/plugin.json`

**Interfaces:**
- Consumes: Block A and Block B from Task 1, verbatim.

- [ ] **Step 1: Replace the interim stop message in `SKILL.md`**

Workflow step 1 currently carries the long inline setup message added for
finding 1. Delete it. Restore step 1 to a one-line check and point at Block B:

```bash
test -n "${PARCELLAB_ACCOUNT_ID:-$PARCELLAB_USER_ID}" && test -n "$PARCELLAB_TOKEN" && echo ok
```

- [ ] **Step 2: Paste Block A and Block B into `SKILL.md`**

Byte-identical to Task 1. This is why the interim message goes: two different
wordings of the same instruction is exactly the drift the shared block prevents.

- [ ] **Step 3: Update `run-lifecycle.sh`**

Accept the canonical name with the alias as fallback, and update the header
comment (currently `Live mode also needs PARCELLAB_USER_ID and PARCELLAB_TOKEN.`):

```bash
ACCOUNT_ID="${PARCELLAB_ACCOUNT_ID:-${PARCELLAB_USER_ID:-}}"
: "${ACCOUNT_ID:?PARCELLAB_ACCOUNT_ID (or legacy PARCELLAB_USER_ID) required}"
: "${PARCELLAB_TOKEN:?PARCELLAB_TOKEN required}"
AUTH=$(printf '%s:%s' "$ACCOUNT_ID" "$PARCELLAB_TOKEN" | base64 | tr -d '\n')
```

Leave the `DRYRUN` guard around it exactly as it is — dry runs must keep working
with no credentials at all.

- [ ] **Step 4: Confirm the version bump**

`plugin.json` is already at `1.0.1` from the interim work. Move it to `1.1.0` to
match create-order — this is the same behaviour change, not a doc fix.

- [ ] **Step 5: Verify the script still parses and dry-runs without credentials**

```bash
cd ~/parcellab-claude-skills
S=plugins/parcellab-order-lifecycle/skills/parcellab-order-lifecycle/references/run-lifecycle.sh
bash -n $S && echo "syntax ok"
D=$(mktemp -d); printf '{"event_status":"test"}' > $D/01-test.json
env -u PARCELLAB_ACCOUNT_ID -u PARCELLAB_USER_ID -u PARCELLAB_TOKEN \
  DRYRUN=1 EVENTS_DIR=$D GAP_SECONDS=0 bash $S && echo "dry run ok with no creds"
```

- [ ] **Step 6: Commit**

```bash
git add plugins/parcellab-order-lifecycle
git commit -m "feat(order-lifecycle): adopt default account convention and confirm before writing"
```

---

### Task 4: parcellab-bug-investigation

**Files:**
- Modify: `plugins/parcellab-bug-investigation/skills/parcellab-bug-investigation/SKILL.md`
- Modify: `plugins/parcellab-bug-investigation/.claude-plugin/plugin.json`

**Interfaces:**
- Consumes: Block A from Task 1, verbatim. **Not Block B** — this skill needs no
  token, only the account default and the CLI's own OAuth session.

- [ ] **Step 1: Correct the binary name**

Every `parcellab-cli` in this file is a command that does not exist; the binary is
`parcellab`. Replace command occurrences only — a prose reference to the
`parcellab-cli` *repo* stays correct if one exists.

- [ ] **Step 2: Paste Block A into `SKILL.md`**

Byte-identical to Task 1. Place it before the existing Step 1 ("confirms the
exact account up front"), which this block now defines rather than describes.

- [ ] **Step 3: Reconcile with the existing mitigation gate**

This skill already has a stronger, deliberate rule: a mitigation requires
restating the exact account number, and a general "yes" is not enough. Block A's
once-per-conversation confirmation **does not replace or weaken that**. Add one
line saying so explicitly, so a future reader doesn't collapse the two gates into
one:

```markdown
> Block A's confirmation covers reads and the report. It does **not** satisfy the
> mitigation gate below, which requires the exact account number restated at the
> time of the change.
```

- [ ] **Step 4: Bump the version**

`1.0.0` → `1.1.0`.

- [ ] **Step 5: Verify**

```bash
cd ~/parcellab-claude-skills
P=plugins/parcellab-bug-investigation
grep -n "parcellab-cli" $P/skills/parcellab-bug-investigation/SKILL.md
echo "^ any line above must be a repo reference, not a command"
grep -c "PARCELLAB_ACCOUNT_ID" $P/skills/parcellab-bug-investigation/SKILL.md  # expect >= 1
python3 -c "import json;json.load(open('$P/.claude-plugin/plugin.json'));print('json ok')"
```

- [ ] **Step 6: Commit**

```bash
git add plugins/parcellab-bug-investigation
git commit -m "fix(bug-investigation): correct CLI binary name, adopt account convention"
```

---

### Task 5: parcellab-brand-layout — convention only

Deliberately separate from the CLI swap. This task leaves the MCP connector in
place, so it is safe on its own.

**Files:**
- Modify: `plugins/parcellab-brand-layout/skills/parcellab-brand-layout-desktop/SKILL.md`
- Modify: `plugins/parcellab-brand-layout/.claude-plugin/plugin.json`

**Interfaces:**
- Consumes: Block A from Task 1, verbatim. Not Block B.
- Produces: Block A present in this file, which Task 6 depends on.

- [ ] **Step 1: Paste Block A into `SKILL.md`**

The skill currently detects accounts via the MCP connector's
`account_get_my_user` and confirms the target itself. Block A replaces that
resolution order; the MCP connector is still what performs the push in this task.

- [ ] **Step 2: Verify the shared block is byte-identical across all four skills**

This is the check that catches drift, and it is the reason the block is defined
once:

```bash
cd ~/parcellab-claude-skills
for f in plugins/*/skills/*/SKILL.md; do
  awk '/^## Account resolution and confirmation$/,/^## /' "$f" 2>/dev/null \
    | shasum | sed "s|\$|  $f|"
done | grep -v "^$"
```

Expected: the four files carrying Block A produce the **same** hash. A differing
hash means someone reworded a copy.

- [ ] **Step 3: Bump the version**

`1.1.0` → `1.2.0`.

- [ ] **Step 4: Commit**

```bash
git add plugins/parcellab-brand-layout
git commit -m "feat(brand-layout): adopt default account convention"
```

---

### Task 6: parcellab-brand-layout — swap MCP for the CLI

**The only task here that can break something that currently works.** Verify
before removing the MCP path, not after.

**Files:**
- Modify: `plugins/parcellab-brand-layout/skills/parcellab-brand-layout-desktop/SKILL.md`
- Modify: `plugins/parcellab-brand-layout/.claude-plugin/plugin.json`

**Interfaces:**
- Consumes: Block A, already present from Task 5.

- [ ] **Step 1: Establish the payload shape the CLI expects**

Read a real layout back and inspect the fields, before writing anything:

```bash
parcellab journey layout list --account 1626718 -o json --jmes '[0]'
parcellab journey layout create --help
```

The MCP tool `journey_write_layout` took its own argument shape. `create` takes
`--json` (inline, `@file.json`, or `-` for stdin). Record the actual required
fields — do not infer them from the MCP tool's parameters.

- [ ] **Step 2: Stop if the shapes don't reconcile**

If `create` needs fields the skill has no way to supply, **abandon this task**,
leave the MCP path in place, and report what's missing. The spec anticipates
this; it is not a failure. Tasks 1–5 stand on their own.

- [ ] **Step 3: Replace the push step in `SKILL.md`**

Swap the `mcp__…__journey_write_layout` call for `parcellab journey layout create
--json @<file>`, writing the layout HTML to a temp file rather than inlining it —
the HTML contains quotes and `{{…}}` placeholders that will not survive shell
quoting.

Keep the existing approval gate before the push. Keep the layout as a **draft**;
do not add a publish step the skill never had.

- [ ] **Step 4: Update the prerequisites in both READMEs**

The skill no longer needs the ParcelLab MCP connector. Remove it from this
skill's prerequisites in the root `README.md` and from the troubleshooting entry
*"ParcelLab MCP connector isn't enabled"*. Add the CLI and `parcellab auth login`
in its place.

- [ ] **Step 5: Verify end to end against a real account**

```bash
parcellab journey layout list --account 1626718 -o json --jmes 'length(@)'
```

Run the skill against a real brand URL, confirm a draft layout appears, and
confirm the count above increased by one. This needs a real run — a `--help`
check does not prove the payload is accepted.

- [ ] **Step 6: Bump the version and commit**

`1.2.0` → `2.0.0` — the prerequisites changed, which breaks anyone relying on the
connector path.

```bash
git add plugins/parcellab-brand-layout README.md
git commit -m "feat(brand-layout)!: push layouts via parcellab CLI instead of MCP connector"
```

---

## Self-review notes

**Spec coverage.** Every spec section maps to a task: the convention and setup
flow → Task 1; per-skill change table → Tasks 2–6 in the spec's stated build
order; the alias → Global Constraints, applied in Tasks 2 and 3 where the auth
header is built; the confirm gate → Block A, pasted in Tasks 2–5 and hash-checked
in Task 5; the binary-name correction → Task 4; brand-layout last and abandonable
→ Task 6 with an explicit stop step.

**Out of scope, unchanged from the spec:** demo-request's Playwright MCP
requirement, its `npm install` path, the CDC token, the
`node_modules`-lost-on-update problem, and bug-investigation's cross-marketplace
dependency. Those are audit findings 2, 3, 4 and 6 and get their own pass.

**Known gap, deliberate:** nothing here verifies that the desktop app actually
reads `env` from `~/.claude/settings.json`, because every existing skill already
depends on that being true (onyx has shipped on it). If it turns out not to hold,
it invalidates the whole approach rather than one task, and the fastest proof is
Task 1 followed by a real setup run.
