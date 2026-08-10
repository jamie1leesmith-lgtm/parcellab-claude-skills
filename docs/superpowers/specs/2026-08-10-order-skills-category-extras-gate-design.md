# Article categories and an extras gate for both order skills

**Date:** 2026-08-10
**Skills touched:** `pl-tools:create-order`, `pl-tools:order-lifecycle`

## Problem

Both order skills invent `article_category` silently — in practice they omit it
entirely. That field is what returns-portal reason filters key on, so an order
created for a returns demo can show the wrong return reasons (or none) with
nothing in the payload or the response hinting at why.

Second, extra payload information is handled unevenly. `order-lifecycle` has a
Gate C extras menu; `create-order` has no menu at all — only an
*Additional recipients* section buried below the payload shape, reachable only if
the user thinks to ask. And where extras *are* agreed, neither skill guarantees
they appear in the pre-send summary: `create-order`'s confirm step lists
order_number, recipient, country, courier, tracking number and article count, so
a promise date or a dynamic recipient agreed a minute earlier can be sent without
ever being echoed back.

## API facts this rests on

- The field is **`article_category`**, a free-text string with no enum.
- It exists on **both** `articles_order[]` (`LineItemOrder`) and
  `tracking.articles[]` (`LineItem`).
- Source: <https://docs.parcellab.com/docs/developers/orders/full-order-api-spec>

Not to be confused with `demo-request`'s `category`, which is a hard-validated
`Home` / `Electronics` / `Fashion` trio belonging to the Custom Demo Creator
automation API. Different field, different system, different vocabulary.

## Design

### 1. The category step

Claude proposes a baseline category derived from what the products actually are —
four clothing items get `fashion` for all four — then asks explicitly in one
exchange:

> Categories drive which return reasons show in the portal. I'd set **`fashion`**
> for all 4 items. Keep it, set a different one for all, or go per-product?
> Standards: `fashion`, `home`, `electronics`, `beauty`, `sports`, `food`,
> `toys`, `media` — or any string you like.

Rules:

- **Blocking, with a one-word exit.** The skill does not build a payload on an
  unanswered category prompt. "Keep it" satisfies the gate.
- **Never invented silently.** A baseline proposal is not the same as a default:
  it must be shown and accepted.
- **Standards are a convention, not an enum.** The eight above are ready-made
  picks. Any string is valid to the API.
- **Written to both levels.** `articles_order[].article_category` *and* every
  `add_tracking.tracking.articles[].article_category`. Same mirroring rule that
  already applies to article name, image and price — and the same silent failure
  if missed, since returns eligibility derives from `tracking.articles`.
- **Preserved verbatim, case included.** If the portal's reason filter keys on
  `Fashion`, sending `fashion` matches nothing. Do not normalise the user's
  input. Same literal-match reasoning as the `additional_recipients` `role` key.
- **Per-product override is first-class.** A mixed order (jacket + kettle) is
  expected to carry different categories per line item.
- **Untracked orders still get it**, at order level only — there is no
  `tracking.articles` to mirror into when `mutations` is omitted.

Placement:

- `create-order`: after carrier confirmation, before the extras gate.
- `order-lifecycle`: folded into **Gate A**, which becomes *product and category
  approval*. The products are already on screen there, so this costs no extra
  round trip and stays a three-gate skill.

### 2. The extras gate

`create-order` gains an explicit gate it currently lacks, with a shorter menu
than Gate C's — only extras that make sense for a one-shot order:

| Extra | Fields | Note to state |
|---|---|---|
| Dynamic recipients | `additional_recipients: [{role, email}]`, at order **and** tracking level | Role matches the Journey's `advancedRecipients` literally; preserve spelling |
| Promise dates | `announced_delivery_date`, `_min`, `_max` | `YYYY-MM-DD` only — full ISO is rejected |
| Order financials | `order_tax_amount`, `order_net_amount`, `order_discount_amount` | For invoice-style comms |
| Tags / custom fields | `tags`, `additional_attributes` | What filter-driven Journey triggers key on |

Deliberately excluded from `create-order`: `client_key` and split-shipment
extras, both of which are journey/lifecycle concerns and stay in Gate C.

Framing is an offer with a fast exit, not a form:

> Anything else to add to this order, or send as-is?

Then the menu. Never an open "any other fields?" — unanswerable without the
Order API spec memorised.

`order-lifecycle`'s Gate C keeps its existing structure and fuller table.

### 3. Final summary itemises everything agreed

Both skills' pre-send summary must list, field by field:

- every article with its `article_category`
- every extra agreed at the extras gate, with its actual value

An extra that was discussed but does not appear in the summary is a defect. The
summary is the last point at which a wrong promise date or a mistyped recipient
role is catchable, and both are invisible in the API's success response.

## Non-goals

- No inspection of the account's returns-portal reason filters to discover exact
  category strings. Considered and dropped as too heavy for the payoff; the
  verbatim-preservation rule covers the mismatch risk by keeping the user in
  control of the string.
- No new reference file shared between the two skills. The menus differ by
  design, so a shared table would need per-skill exceptions anyway.
- No change to gate count in `order-lifecycle` — still A, B, C.

## Verification

- `python3 -m unittest discover -s tests -v` from `plugins/pl-tools/scripts`
  (no script changes expected, so this is a regression check only).
- Frontmatter `name:` still equals the directory name for both skills, and
  neither `description:` is touched — descriptions are trigger text.
- Grep both skills for `article_category` and confirm it appears in the payload
  examples at both order and tracking level.
