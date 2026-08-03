# Account defaults and auth — design

**Date:** 2026-08-03
**Status:** approved (Jamie, 2026-08-03)
**Scope:** all skills in this marketplace

## Problem

Two problems, found while auditing the repo for missing setup information ahead
of sharing it with the team.

1. **Credential setup is undocumented or unfollowable.** `parcellab-order-lifecycle`
   hard-stops on its first step when `PARCELLAB_USER_ID` / `PARCELLAB_TOKEN`
   are unset, and nothing anywhere tells the user how to set them.
   `parcellab-create-order` documents them, but buried in a per-skill README a
   desktop-app user never opens, and under a heading ("Installation for someone
   new") whose first instruction — copy the folder into `~/.claude/skills/` — is
   stale advice from before these were plugins.

2. **There is no shared notion of "my account".** Each skill resolves an account
   differently: the order skills read an env var, `parcellab-bug-investigation`
   passes one to the CLI, `parcellab-brand-layout` resolves it through the
   ParcelLab MCP connector. Every internal user has a demo account that should
   be their default everywhere, and no skill confirms which account it is about
   to write to.

## Findings that constrain the design

Established by inspection, not assumption. These are the facts the design has to
live with.

- **The CLI binary is `parcellab`, not `parcellab-cli`.** `parcellab-cli` is the
  repo name. `parcellab-bug-investigation` refers to `parcellab-cli` throughout
  and is wrong.
- **The CLI authenticates by OAuth device flow** (`parcellab auth login`,
  `--open-browser` by default). Nothing the CLI covers needs a stored token.
- **The CLI wraps the Product API only — config and reads.** Its full command
  tree (900 lines, `parcellab registry tree`) contains no order-create and no
  checkpoint-push command. `track event` and `track tracking` expose `list` and
  `show` only.
- **`parcellab-create-order` and `parcellab-order-lifecycle` do not use the
  Product API.** They write to the Order API (`api.parcellab.com/v4/orders`,
  `/v4/track/events/`), a separate ingestion API authenticated with a base64
  `accountID:token` pair.

  ⚠️ **The CLI *can* reach the Order API, and the token still stays. Read this
  before "fixing" it.** An earlier version of this spec claimed the CLI could not
  reach the Order API at all. That was wrong — it was inferred from the CLI's
  command tree rather than tested. In fact:

  ```
  parcellab --base-url https://api.parcellab.com api request GET /v4/track/orders/
  ```

  returns real order data, authenticated by the CLI's OAuth session alone
  (verified with `PARCELLAB_TOKEN` unset, and again with the OAuth token
  deliberately invalidated, which fails). The archived `demo-orders` skill said
  as much in its description.

  **The token stays anyway, for a different and better reason.** `--base-url`
  redirects *every* request the CLI makes, including its own internal
  `edit-mode` guard lookup (`GET /v3/account/accounts/?include_children=true`,
  a Product API path). Against the Order API host that 404s, so
  `account-restricted` mode hard-fails and no write can proceed. The only way
  through is `edit-mode set unrestricted` — which removes the guard for every
  account the user can see.

  There are **13 demo accounts under `Demo SolCon` (1621786), one per SC**. Asking
  every teammate to run unrestricted so a skill can create an order would trade a
  credential that is account-bound by construction for one that isn't. Rejected
  on that basis (Jamie, 2026-08-03).

  So: **the Order API token is required, and the CLI route must not be adopted
  even though it demonstrably works.** Re-testing the GET above will succeed and
  prove nothing — the blocker is the guard, not the auth.
- **The Product API does not expose the Order API token.** Checked
  `account account show` (76 fields), `account account info` (51),
  `account user list` and `config client list` against a real account. The only
  match on a token/key/secret/auth pattern was `disableZipAuth`, a tracking-page
  setting. So a skill cannot fetch the token on the user's behalf.
- **`parcellab journey layout` supports `create` / `update` / `delete`**, so
  `parcellab-brand-layout` can be moved off the MCP connector's
  `journey_write_layout` onto the CLI.
- **`parcellab account account search --name` exists**, so a user's demo account
  can be looked up by name — they never need to know its numeric ID. The naming
  convention makes this reliable: every SC's account is `Demo - <Full Name>`
  under `Demo SolCon` (1621786).
- **The CLI has a real, tool-level write guard: `parcellab settings edit-mode`.**
  Set to `account-restricted --account <id>`, it refuses writes to any other
  account *before sending the request*. That is stronger than a prompt-level
  confirmation, which a model can be talked past. It applies to Product API
  writes — so it protects `parcellab-bug-investigation` and (after the swap)
  `parcellab-brand-layout`, but **not** Order API writes, which don't go through
  the CLI at all under the accepted design.
- **Pointing `edit-mode` at a parent account does not work**, even though the
  hierarchy is readable: the guard's child-account lookup fails. Set it to the
  user's own leaf account.
- **Found in passing, worth acting on:** Jamie's `edit-mode` was restricted to
  `1625801` — *Demo - Paula Petersen*, a colleague's account — while his own is
  `1626718`. So his CLI permitted writes to someone else's demo account and
  blocked his own. Almost certainly a setup step with a copied account id. This
  is invisible until a write fails, which is the argument for the setup flow
  setting `edit-mode` per user rather than leaving it to chance.
- **The CLI takes `--account` to scope a command**, and `--yes` to skip an
  interactive confirmation, so it already gates writes by default.

## Audience constraint

**The team uses the Claude Code desktop app, not the CLI.** Nobody types
commands. This is the single most shaping constraint: setup cannot be "run this
command", it has to be Claude performing the steps inside a conversation. It is
why the design puts setup inside the skills rather than in a slash command or a
setup script — a command you paste into Slack has no value to an audience that
never opens a terminal.

## Design

### One variable is "my account"

`PARCELLAB_ACCOUNT_ID` holds the user's default demo account. It lives in the
`env` block of the global `~/.claude/settings.json`.

`PARCELLAB_USER_ID` is accepted as an alias and takes lower precedence. Anyone
already set up (including Jamie) has that name set; a silent rename would break
them. Skills read `PARCELLAB_ACCOUNT_ID` first, fall back to
`PARCELLAB_USER_ID`, and never write the old name.

The same value serves both purposes — it is the account the CLI is scoped to
*and* the `userId` half of the Order API's credential pair. One variable, not
two.

`PARCELLAB_TOKEN` holds the Order API token, and is needed **only** by
`parcellab-create-order` and `parcellab-order-lifecycle`. Anyone installing only
brand-layout or bug-investigation never sets it.

### Token intake: ask for the base64 blob

When a skill needs the Order API credential and it isn't set, it asks for the
**base64-encoded blob** the portal shows, in preference to the raw token.

The blob decodes to `accountID:token`, so one paste yields both values. This
removes the account lookup *and* removes the most common setup error, which is
pasting the whole blob in as the token and getting an unexplained `401`.

The raw token is accepted as a fallback, in which case the account ID is
resolved separately (see below).

Pasting the token into the conversation is acceptable and deliberate: these are
demo accounts holding no sensitive data (Jamie, 2026-08-03). Skills must still
never echo the token back into the transcript once received.

### Setup flow (desktop app, no terminal)

What a new teammate actually does. Steps 2–5 are Claude acting, not the user.

1. **Install** via the app: **+** → **Plugins** → **Add plugin** → marketplace
   source `jamie1leesmith-lgtm/parcellab-claude-skills` → pick skills →
   **Install**.
2. **Check the CLI is reachable.** The skill verifies `parcellab` resolves on
   `PATH`. It usually lives at `~/.local/bin/parcellab`. If it does not resolve,
   stop and say so plainly — every CLI-backed step fails otherwise, and the
   downstream errors are confusing.
3. **Authenticate.** If `parcellab auth show` indicates no valid session, run
   `parcellab auth login`. The browser opens automatically; the user approves
   there. **Run it in the background** — it blocks waiting for approval and will
   otherwise hit the tool timeout.
4. **Resolve the default account.** Either decoded from the pasted blob, or
   looked up with `parcellab account account search --name "<term>"` and
   confirmed from the matches. Written to `settings.json` via a normal file edit,
   which the user approves through the usual permission prompt.
4a. **Point the CLI's write guard at that same account:**

   ```bash
   parcellab settings edit-mode set account-restricted --account <id>
   ```

   This is not optional politeness — it is the only guard that physically prevents
   a CLI-backed skill writing to a colleague's demo account, and it failed open on
   the one machine we checked (see the findings above). Use the user's own leaf
   account; a parent does not work. Confirm the resulting value with
   `parcellab settings edit-mode show` rather than assuming the set succeeded.

5. **Capture the Order API token**, for the two order skills only.
6. **Quit and reopen the app.** Environment variables are read at startup, so
   nothing from steps 4–5 takes effect until then. This is the step users will
   forget, so it is stated loudly and is the *first* line of any
   credentials-missing message.

### Confirm before acting

Every skill, before its first write, resolves the account's human name and
confirms:

> Using **[account name]** (`1626718`) — your default. Correct, or use a
> different account?

The name matters. A wrong account *number* is invisible to a human reader; a
wrong account *name* is not. Resolved via `parcellab account account show <id>`.

Rules:

- The confirmation happens once per conversation, before the first write — not
  before every call.
- An explicit account named by the user overrides the default, and is confirmed
  the same way.
- Read-only inspection does not need the gate. Writes always do.
- If no default is set, the skill runs the setup flow rather than guessing or
  proceeding.

### Per-skill changes

| Skill | Change |
|---|---|
| `parcellab-create-order` | Read `PARCELLAB_ACCOUNT_ID` (alias `PARCELLAB_USER_ID`); actionable setup on missing credentials; confirm-before-write; delete the stale "copy this folder to `~/.claude/skills/`" instruction from its README |
| `parcellab-order-lifecycle` | Same, plus its step-1 hard stop becomes the setup flow |
| `parcellab-brand-layout` | Swap `journey_write_layout` (MCP) for `parcellab journey layout create`; adopt the default account and the confirm gate |
| `parcellab-bug-investigation` | Adopt the default account and confirm gate; correct `parcellab-cli` → `parcellab` throughout |
| `parcellab-demo-request` | Adopt nothing — it has no ParcelLab account concept. Its own setup gaps are tracked separately |
| `onyx` | Unchanged. Already the model this design copies |

Root `README.md` becomes the single source of truth for the convention and the
setup flow. Each `SKILL.md` carries the same short canonical block rather than
its own variant, so the copies cannot drift into disagreement.

### Build order

Order skills first, brand-layout last, and deliberately so. The order skills are
already broken for any teammate, so changing them risks nothing. Brand-layout
**currently works** via the MCP connector — swapping it to the CLI is the one
change here that can break something functional, and `journey layout create` may
want a different payload shape than `journey_write_layout` did. Doing it last
keeps it cheap to abandon.

## In-flight work this supersedes

Branch `fix/skill-setup-docs` already carries a first pass at finding 1: a
shared "Setting up ParcelLab Order API credentials" section in the root README
and an actionable stop message in `parcellab-order-lifecycle`'s `SKILL.md`, both
written against `PARCELLAB_USER_ID` as the canonical name and both instructing
the user to hand-edit `settings.json`.

Those changes are the right shape but the wrong details under this design. They
must be reconciled, not layered on: `PARCELLAB_ACCOUNT_ID` becomes canonical, and
the hand-edit instruction is replaced by Claude performing the setup.

## Out of scope

- The Playwright MCP requirement, `npm install` path and CDC token setup in
  `parcellab-demo-request` (findings 2–4 of the audit).
- The `node_modules`-lost-on-plugin-update problem (finding 3).
- Cross-marketplace dependencies in `parcellab-bug-investigation` (finding 6).
- Any attempt to route order creation or checkpoint pushes through the CLI —
  established above as impossible.

## Risks

- **Brand-layout payload shape.** `journey layout create --json` may not accept
  what the MCP tool did. Verify against a real layout before removing the MCP
  path.
- **CLI not on `PATH` in the app's shell.** The desktop app's shell is
  initialised from the user's profile, so this works where the profile exports
  `~/.local/bin`. It is the most likely per-person setup failure and is why
  step 2 exists.
- **The restart step.** Unavoidable, and the most likely cause of "the skill is
  broken" reports.
- **Alias debt.** Supporting `PARCELLAB_USER_ID` indefinitely is a small ongoing
  cost, accepted to avoid breaking existing users.
