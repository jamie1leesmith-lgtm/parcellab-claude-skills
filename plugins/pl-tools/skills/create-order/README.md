# create-order — Skill README

This is a personal Claude Code skill that creates orders in a ParcelLab account via the production Order API (`PUT /v4/track/orders/`). This README explains **why** the skill is shaped the way it is — the design decisions, the gotchas we hit while building it, and the constraints that shaped each choice — so the team can read, reuse, or adapt it without re-deriving the same conclusions.

For the actual instructions Claude follows when the skill runs, read [SKILL.md](./SKILL.md). For the canonical API contract, see <https://docs.parcellab.com/docs/developers/orders/full-order-api-spec>.

---

## What the skill is for

When a Claude Code user says something like *"create a parcellab order for a UK customer with a Father's Day gift card"*, the skill:

1. Reads ParcelLab credentials from environment variables.
2. Builds a plausible order payload — using whatever context the user gave, and filling in realistic dummy data for everything else (recipient, address, courier, tracking number, etc.) adapted to the destination country.
3. Shows the constructed JSON to the user and asks for explicit confirmation.
4. On approval, base64-encodes the auth header and `PUT`s the payload to production.
5. Reports back HTTP status, returned `external_id`, and any warnings.

It exists because hand-crafting realistic test/demo orders against the v4 spec is repetitive — there are four required fields, a long tail of useful-but-optional ones, and country-specific defaults (language, courier, address shape) that should match for the result to look believable.

---

## Design decisions and why

### Trigger on natural phrases, not a slash command
We chose a description-based trigger covering phrasings like *"create a parcellab order"*, *"push a test order to PL"*, *"send an order to parcellab for [country]"*. ParcelLab work is conversational — the user is rarely in a "now I'll run a command" mindset; they're describing a scenario. A slash command would mean breaking that flow. The description is also deliberately a bit pushy ("trigger even when the user has not specified every field") because skills tend to under-trigger by default.

### Production-only, no test environment toggle
The skill always targets `api.parcellab.com`. We considered an `--env=test|prod` flag, but ParcelLab accounts are typically configured for a single environment, and a per-run env switch creates a foot-gun (sending a "test" order to production by mistake). Instead, the workflow forces an explicit confirmation step before every PUT — every send is a deliberate act, not an accidental one.

### Credentials via env vars, not in-conversation
Credentials live in `~/.claude/settings.json` under the `env` block, scoped to Claude only. We rejected pasting them per-run (ends up in transcript) and pulling from a project-specific file (couples credentials to a workspace, which doesn't fit this user's setup).

The skill stores the **raw token** as `PARCELLAB_TOKEN` and the **numeric account ID** as `PARCELLAB_USER_ID`, then constructs the auth header at request time via `base64("$PARCELLAB_USER_ID:$PARCELLAB_TOKEN")`. The ParcelLab portal often exposes the credential as the pre-encoded blob — if you encounter that, decode it once and store the parts separately. This is what the skill expects.

### `curl` via Bash, no SDK or extra dependencies
Personal skills should be portable across machines. Adding a Python or Node dependency means installing things, pinning versions, and dealing with virtualenvs. A single `curl` call backed by `mktemp` + the Write tool for the JSON payload gets the same result with zero install footprint. The `--data-binary @file` pattern avoids shell-quoting issues with UTF-8 characters (e.g. £, ß).

### Plausible dummy data, country-driven
When the user gives partial context (just a country, or just a scenario), the skill fills the rest from a small table — language, currency, timezone, default courier, example address. The defaults match the destination country because mismatched data is the obvious "tell" that an order is fake (a UK recipient with a German DHL tracking number looks wrong in the portal). The defaults are intentionally short (DEU, GBR, USA, FRA, NLD, AUT) rather than exhaustive; for anything else, the skill is told to pick a sensible carrier and use a capital-city address, or ask the user.

Tracking numbers follow each carrier's real format (Royal Mail `XX#########GB`, USPS 22-digit, UPS `1Z…`) so they at least look plausible in the portal, even though they're not live.

### Always show the payload before sending
Every successful PUT writes a real order. The confirmation step exists to give the user a chance to catch (a) Claude misinterpreting their scenario, (b) typos in addresses or tracking numbers, and (c) cases where the user changed their mind about a field. We show a tight summary table (order number, recipient, country, courier, tracking number, article count) by default with the full JSON on request — the table is what humans actually read.

---

## The Dynamic Recipients gotcha

This took the most iteration and is worth documenting in detail because the right answer is genuinely not obvious from the API spec alone.

**The setup:** the user wanted to send an order with an additional recipient — a gift recipient who should also get tracking emails. The Order API has `additional_recipients` at both the order level and inside the `add_tracking` mutation's `tracking` object.

**What we tried (wrong):**

1. First send — `additional_recipients` at order level only. The API returned 200 with the field populated. Portal export showed `additionalRecipients: []`. Looked like a save failure.
2. Second send — `additional_recipients` duplicated into the tracking object. Same result: API confirmed both levels, portal still empty.
3. We thought it was a plumbing gap between the v4 API and the tracking record storage. We even documented it that way in the skill briefly. Wrong.

**What we learned (right):**

ParcelLab calls this feature *Dynamic Recipients* in their portal, but the v4 API field is `additional_recipients`. The documentation at <https://docs.parcellab.com/docs/engage/messages-and-journeys/configuration/dynamic-recipients> explains the actual model:

- The API field is just a label. It saves on the record, but does nothing on its own.
- A **Journey** in the parcelLab portal must be configured with `advancedRecipients` listing the same role key. That Journey is what actually fires the notification email — the API field is just data the Journey looks up at trigger time.
- The `role` field is **not free-text**. It must match the Journey's configured role key **exactly** — case-sensitive, no spelling variation. If the Journey expects `giftRecipient` and we send `gift_recipient`, no recipient is selected and nothing happens.

**Why it looked empty in the portal:** unclear without more digging — possibly the tracking-record export view only surfaces recipients that resolved against a Journey, or possibly there's a separate cache. Either way, the user-visible symptom is the same: until a Journey is configured with a matching role key, the additional recipient is inert data.

**What the skill does now:**

- Writes `additional_recipients` to both order and tracking levels (cheap, covers both notification-trigger types).
- Preserves the user's exact spelling and case for `role` — even if it looks misspelled, like `GiftReciever`. The match is literal; "fixing" it would break things if the user's Journey was configured with the same misspelling.
- Before sending, flags the Journey dependency: tells the user the additional recipient won't receive any emails unless their account has a Journey configured with `advancedRecipients: ["<role>"]`.
- Asks for or confirms the role key rather than inventing one. If the user doesn't know, the skill points at the docs and suggests camelCase patterns from the parcelLab examples (`giftRecipient`, `warehouseContact`).

**Takeaway for the team:** any time a parcelLab feature has both an API field and a portal-side configuration, assume the API field is *necessary but not sufficient*. The portal config is what makes the feature actually do something.

---

## Other useful (but optional) order fields

The user can ask for these and the skill will include them. Listed roughly in order of how much value they add to a realistic test order:

| Field | Why it matters |
|---|---|
| `announced_delivery_date` (or min/max) | Drives the "expected delivery" line in notification emails. Without it, the ETA section often renders blank. |
| `billing_address` | For gift orders, the billing party (buyer) differs from the shipping party (recipient). Some templates surface this. |
| `announced_send_date` (inside tracking) | Drives "your order has been dispatched" timing in messaging. |
| `tags` (e.g. `occasion:fathers-day`) | Enables filtering and segmentation in the dashboard and per-tag template A/B testing. |
| `customer_number` | Joins orders to a customer record in your CRM. |
| `payment_method` | Renders in some invoice templates. |
| `additional_attributes` | Free-form key/value bag — useful for gift messages or any custom metadata. Whether it renders depends on the template. |
| `recipient_phone` | Required for SMS notifications if the account has SMS configured. |
| `courier_service_level` | e.g. "Tracked 48" for Royal Mail — adds realism. |
| `shipping_cost_total` | Shown in some confirmation emails. |

The skill doesn't send these by default because they add noise to the confirmation step. The user opts in when they ask.

---

## Courier codes — known unknown

ParcelLab does not publish a clean public list of the courier code strings the API expects. The Supported Carriers page lists carrier *names* but not the API code values. We've documented the codes we know work in the SKILL.md (`dhl-germany`, `royal-mail`, `usps`, `ups`, `fedex`, `dpd-uk`, `parcelforce`, `yodel`, `evri`, `hermes`, `colissimo`, `postnl`, `dhl-austria`), based on common patterns and what's been observed in real integrations.

If a code isn't recognised, the API returns HTTP 200 but `mutations[0].result.success` is `false` with a warning — no order corruption, just a clean failure signal. Recommend looking at an existing order in your account to confirm the canonical code your integration uses; that's the most reliable source of truth.

---

## Installation

Install this as a plugin from the marketplace — see **Install** and **Your
default account** in the [repo README](../../../../README.md#your-default-account).
Setup is a conversation: ask Claude to set up your parcelLab skills and it walks
you through it.

Then try it: *"create a parcellab order for a German customer with two items in
transit"*.

> Earlier versions of this file told you to copy the folder into
> `~/.claude/skills/`. That predates this being a plugin — don't do it, you'll
> end up with the skill installed twice.

---

## Caveats and open questions

- **Production only.** The skill has no concept of staging. Don't install it in an environment where you don't want real orders.
- **Dynamic Recipients require a Journey.** As above — the API field saves, but emails only go out if a Journey is configured with the matching role key.
- **Courier code list is best-effort.** Not authoritative; verify in your account.
- **Default dummy data is intentionally minimal.** Six countries cover most demos. Extend the table in SKILL.md if you regularly demo other markets.
- **No GET helper.** The skill only creates/updates. Reading orders back is a manual `curl` call.
