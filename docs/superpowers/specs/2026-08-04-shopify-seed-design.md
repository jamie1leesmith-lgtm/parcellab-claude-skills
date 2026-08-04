# Design: `shopify-seed` — seed a prospect's own products into a Shopify dev store

**Date:** 2026-08-04
**Status:** approved, ready for planning
**Source handoff:** `ParcelLab/Shopify Project/HANDOFF-prospect-product-seeding-skill.md`
(in the `parcellab-workspace` repo — not this one)

## Problem

A Solutions Consultant demoing the parcelLab returns and exchanges flow wants to point at
products the prospect actually sells: *"here's the jacket you sell — now imagine your customer
wants to trade it for something else in your range."* Generic placeholder products break that.

An existing three-product generic seed (`Shopify Project/seed/`) proved the `productSet`
mutation works. This skill is a different job: take a prospect URL, get **their** products into
a Shopify dev store, correctly shaped for both exchange flows, in one invocation — repeatably,
for a different prospect every week, against a store that may still hold the last one's
products.

## Identity and location

`plugins/pl-tools/skills/shopify-seed/`

- Frontmatter `name: shopify-seed` — **must equal the directory name**, or the skill silently
  drops out of the plugin inventory.
- No `pl-` directory prefix; the `pl-tools:` prefix already namespaces it.
- `description:` is trigger text, not a label. It spells out **parcelLab** and **Shopify** and
  covers phrasings like *"seed a prospect's products into my Shopify demo store"*,
  *"load [brand]'s products for an exchange demo"*, *"set up the Shopify store for [prospect]"*.
- Built with `anthropic-skills:skill-creator`. Not hand-rolled, not copied from a sibling skill.
- All internal paths use `${CLAUDE_PLUGIN_ROOT}`.

Files:

| Path | Purpose |
|---|---|
| `SKILL.md` | The workflow, terse |
| `references/product-scrape.md` | Browser-pane snippets: name, price, image, sizes |
| `references/mutation-template.md` | The verified `productSet` shape + archive mutation |
The price/size/stock rule goes at the **plugin** level, not the skill level:

| Path | Purpose |
|---|---|
| `plugins/pl-tools/scripts/shape_product_mix.py` | The price/stock/size rule, pure logic |
| `plugins/pl-tools/scripts/tests/test_shape_product_mix.py` | stdlib `unittest` |

That is where `pl_credentials.py` and its tests live, and it is the only location the documented
`python3 -m unittest discover -s tests` command reaches. A skill-level `scripts/tests/` would be
silently skipped by the repo's own test command.

Audience knows parcelLab. The skill does not explain what a returns portal is. **Keep it
terse** — the long-form drafts in the source repo were judged far too verbose.

## Verified facts (established 2026-08-04, do not re-derive)

Confirmed live against Shopify CLI **4.6.0** on macOS, and against the current Admin GraphQL
docs. Some of it contradicts older docs and plausible priors.

### CLI

- **`shopify populate` does not exist.** Dropped after CLI 2.x. Never document it.
- **`SHOPIFY_CLI_SKIP_UPDATE_CHECK` does not exist.** Invented in an earlier session and
  propagated into docs as though mandatory. Setting it does nothing. The real control is
  `shopify config autoupgrade off`.
- Seeding goes through the `store` topic:
  - `shopify store auth -s <store>.myshopify.com --scopes write_products,write_inventory`
  - `shopify store execute -s <store>.myshopify.com --query-file f.graphql --variable-file f.json --allow-mutations`
- `-s/--store` is required and takes the `myshopify.com` domain.
- **`--allow-mutations` is required for any write.** Without it mutations are refused. This is a
  useful safety property and the skill should say so.
- `--query-file`/`--query` are mutually exclusive, as are `--variable-file`/`--variables`.
- `shopify store auth` opens a **browser consent step** — warn the user.
- `shopify store list` covers *organisation* stores and returns "No stores found" for a
  directly-authenticated dev store. **`shopify store auth list`** is the one that lists
  directly-authenticated stores, as a `Subdomain`/`Connected` table.
- Also available: `shopify store graphiql`, `shopify store bulk`, `shopify store info`.

### Install gotchas

`brew install shopify-cli` alone fails — the formula is not in homebrew-core, and current
Homebrew refuses to load it until the tap is trusted:

```bash
brew tap shopify/shopify
brew trust shopify/shopify
brew install shopify-cli
```

Turn off auto-upgrade **before anything else**. A self-upgrade fired mid-session on 2026-08-04,
uninstalled the CLI, failed to install the replacement, and left a dangling symlink with no
working `shopify` command:

```bash
shopify config autoupgrade off
```

### Mutation shape

`productSet(synchronous: true, input: ProductSetInput!)`, called once per product with GraphQL
aliases so one command creates all of them. Always request `userErrors { field message }` — a
silent partial failure is worse than an error.

Confirmed fields:

- `ProductSetInput` — `title`, `status`, `tags`, `productOptions`, `variants`, `files`
- `OptionSetInput` — `name`, `position`, `values`
- `ProductVariantSetInput` — `price`, `published`, `optionValues`, `inventoryQuantities`, `file`
- `VariantOptionValueInput` — `optionName`, `name`
- `ProductSetInventoryInput` — `locationId`, `name` (use `"available"`), `quantity`
- `FileSetInput` — `originalSource`, `alt`, `filename`, `contentType`, `duplicateResolutionMode`

**Images resolve in the same mutation.** `ProductSetInput.files: [FileSetInput!]`, and
`originalSource` explicitly accepts an external URL. `contentType` is optional — Shopify sniffs
it during processing — but pass `IMAGE` for clarity.

**One image per product, and none per variant.** `ProductVariantSetInput.file` exists (and any
variant file must also appear in the product's `files` array), but this skill does not use it:
a single product-level image is enough for the demo, and every variant of a product shares it.
That keeps the mutation to one `files` entry per product and removes the need to source a
matching photo per colour.

## Workflow

### Step 0 — Preflight

`command -v shopify`, then `shopify version`. If missing, the tap/trust/install sequence above.
Then `shopify config autoupgrade off`, unconditionally, before anything else.

### Step 1 — Resolve the destination store: confirm once, then remember

1. Read `~/.claude/parcellab-shopify-seed.env` for `SHOPIFY_DEMO_STORE`.
2. **Stored value present, no override:** use it, state it plainly in output, do not re-ask.
3. **No stored value:** `shopify store auth list`.
   - Exactly one store → confirm it **by name** and get an explicit yes.
   - Several → ask which.
   - None → `shopify store auth -s <store> --scopes write_products,write_inventory`, warning
     that a browser consent window will open.
4. Persist the confirmed store to `~/.claude/parcellab-shopify-seed.env`.
5. Change it only when the user names a different store.

A config file, not an env var: env vars are read only at app startup, so a value the skill
writes there stays invisible until a full ⌘Q restart. This follows the existing
`~/.claude/parcellab-demo-request.env` precedent.

**Dev stores only**, stated at the confirmation. Never a production merchant store.

### Step 2 — Resolve the location ID automatically

```
shopify store execute -s <store> --query '{ locations(first: 5) { nodes { id name isActive } } }'
```

Read-only, so no `--allow-mutations`. This returns the `gid://shopify/Location/…` form, which is
exactly what `ProductSetInventoryInput.locationId` expects — the user never hunts a numeric ID out
of an Admin URL. That manual find-and-replace was the clumsiest part of the original generic seed.

**Choose the location the online store actually sells from**, not simply the first active one:
`isActive` + `fulfillsOnlineOrders` + `shipsInventory`, falling back to `fulfillsOnlineOrders`
alone, then to any active location with that stated. A store can have several — `parcellab-demo-jls`
has *Shop location* and *UK Warehouse* — and stock placed at one the online store does not fulfil
from leaves every variant stocked but **unsellable**. That failure presents identically to the
zero-stock case while every number looks correct, so Step 8 also asserts `availableForSale`.

### Step 3 — Collect the prospect's products

Uses Claude Code's built-in **Browser pane** (`mcp__Claude_Browser__*`), matching
`demo-request`, `branded-template` and `order-lifecycle`. Not Claude-in-Chrome, not Playwright.

`demo-request`'s image-scoring snippet is proven and is reused verbatim. But it collects only
`{name, imageUrl, pdpUrl}`, and this skill also needs **price** and **sizes** — so the extended
snippet lives in this skill's `references/product-scrape.md`. **`demo-request` is not
modified.**

Extraction, in priority order — **revised after the live run, which proved the original order
insufficient**:

1. **Shopify's own product JSON**, fetched same-origin from inside the page:
   `fetch(location.pathname + '.js')`. Gives `type`, `price`, `featured_image`, and crucially
   `options[]` with the option **name** and exact values. `curl` cannot substitute — some
   storefronts return bot-protection noise to it. Prices are in **minor units** (divide by 100)
   and `featured_image` is protocol-relative (prepend `https:`).
2. JSON-LD `application/ld+json` → `offers.price`
3. `meta[property="product:price:amount"]`
4. DOM price text as a last resort

On Allbirds — a Shopify storefront — paths 2–4 found a price but **no variant axes at all**: the
page exposes no product JSON script and no matching option UI, so the skill would have silently
fabricated an `S`/`M`/`L` axis for shoes. Path 1 returned the real sizes. Deriving values by
splitting a variant's `public_title` on `" / "` is also unsafe: a real value was
`"M (W8-10 / M8)"`, which the split corrupts.

**A candidate PDP must be confirmed before its data is used.** A collection page can link to
URLs that redirect back to the listing or 404 — Allbirds' own men's collection did both. Scraping
the redirected page yields a product-shaped `name` with a null price and no axes, which looks like
a sparse product rather than the wrong page.

**Four products of four different types** — a jumper, jeans, shoes, a jacket. Not four
jumpers. The variety is what makes the cross-product exchange look like a real decision.

**For each product, pull a couple of values from each variant axis the site exposes** —
typically Size and Colour, or shoe size. A product needs **at least two variants** so a
small→medium swap demonstrates an even exchange inside that single product, which is the
most common real returns case and the fastest thing to show.

- Take up to 3 values per axis and at most 3 axes, minimum 2 values. A 3×3 Size/Colour
  matrix is 9 variants; 3 axes × 3 values is the 27-variant ceiling.
- **For clothing, get Size *and* Colour.** A Size-only garment looks thin on a variant
  picker; Size × Colour makes it look like a real product. Footwear is usually size alone.
- Drop any axis the site exposes with only one value — a single-value option is noise.
- If no axis can be scraped at all, fall back to one `Size` axis of `S`/`M`/`L`.
- **Never fabricate colour values.** Pull the real ones or omit the axis.

**Colour is frequently not on the PDP being scraped.** Some sites publish each colourway as
its own product page, with the colour name only in the link between them — Nike serves
`/t/<slug>/HV0949-063` and `/t/<slug>/HV0949-451` as one garment in two colours. Harvesting
those sibling links is what recovers the axis; without it, apparel from such a site returns
Size only. Verified against Nike: it recovers *Obsidian*, *Dark Grey Heather* and *Black* for
a jacket whose page exposes no colour picker at all, giving 3 × 3 = 9 variants.

**Product names must not be taken from `h1` alone.** On Nike the `h1` is only the sub-brand —
"Nike Tech", "Nike Form", "Nike Calm 2.0" — so preferring it names products after a range
rather than a product. Take the *most specific* of `h1`, the page `<title>` and JSON-LD
`name`, stripping the site suffix and any trailing size/colour qualifier; the longest
surviving candidate wins, since a sub-brand fragment is always shorter.

Image validation **reuses `demo-request`'s existing script** rather than raw `curl`:

```bash
node ${CLAUDE_PLUGIN_ROOT}/skills/demo-request/scripts/check_images.mjs <payload.json>
```

Cross-skill reuse inside the same plugin, so `${CLAUDE_PLUGIN_ROOT}` resolves correctly and
`demo-request` stays untouched. It is better than a `curl -sIL` check for this skill's purpose
because it **retries HEAD as a ranged GET on 403/405** — which is exactly the hotlink- and
referer-protected CDN case that later breaks Shopify's own server-side fetch in Step 8. It
requires exactly 4 products (matching this design), emits JSON per image, and exits non-zero if
any fails.

Inherit `demo-request`'s other edge cases: consent modals (**decline non-essential**), lazy-loaded
images (scroll first), bot protection (say so and stop, don't work around it), login walls
(out of scope).

### Step 4 — Shape the mix for both exchange flows

Four demos have to be possible when this finishes. Each needs a different thing to be true:

| Demo | Requirement |
|---|---|
| **Even, inside one product** — swap S for M | ≥2 variants on a product (Step 3) |
| **Even, across products** — swap for a different item, nothing to pay | 2 products at the **same** price |
| **Uneven upward** — customer **pays** the balance | ≥1 product priced **above** that pair |
| **Uneven downward** — customer is refunded the difference | a product priced **below** the pair *(nice to have)* |

The upward case is the one with a hard directional requirement: exchanging into something
*more* expensive is what exercises taking payment. A rule that only guaranteed "some other
price" could satisfy itself by exchanging downward and never show the payment step at all.

And underneath all four: **non-zero stock on every variant.** A zero-stock variant is invisible
as an exchange target, so the demo silently shows fewer options than expected and looks broken.

Rule, applied by `shape_product_mix.py` to exactly four products:

1. Normalise all prices to 2dp.
2. Sort by price ascending. Consider only the two *adjacent* pairs among the three cheapest —
   this deliberately excludes the most expensive product from the pair, which is what keeps
   something available above it.
3. Take whichever of those two pairs has the smaller gap; ties go to the cheaper pair. Converge
   it by lowering the higher price to the lower. A pair that already matches has a gap of zero,
   so it wins automatically and **nothing is altered**.
4. The most expensive product must now be strictly above the pair price. If it is not (every
   price was identical), nudge it up by `10.00`.
5. The remaining product is left alone. If it happens to sit below the pair price, the downward
   refund demo is available too — report that, don't engineer it.
6. Stock: a fixed non-zero quantity on every variant in the matrix.

Consequences worth stating: a catalogue that already contains a natural pair and a dearer item
is **not modified at all**, which is the common case. At most two prices ever change, and every
change is reported as `was → now`. Prices are the one place real prospect data may be altered.

### Step 5 — Approval gate

| # | Product | Type | Real price | Seeded price | Adjusted | Variants | Image |
|---|---|---|---|---|---|---|---|

Plus the destination store by name, the four demos the mix now supports, and any duplicate
product types worth swapping out. **No writes before an explicit yes.**

### Step 6 — Archive the previous prospect's products

Every seeded product carries `pl-demo-seed` plus `pl-prospect-<handle>` for traceability.

On re-run, query `products(first: 50, query: "tag:pl-demo-seed status:active")` and set those to
`ARCHIVED`. Archived products disappear from the storefront and the returns portal but nothing
is destroyed — recoverable by un-archiving. Report what was archived, by name.

**Verify before writing:** `productUpdate` changed its argument from `input:` to `product:` in a
recent API version. Confirm the current shape against the live schema — do not guess. Uses
`ProductStatus.ARCHIVED`. Requires `--allow-mutations`.

### Step 7 — Push

Generate the mutation and variable files into the session scratchpad (products differ every
run, so these are not static shipped files — `references/mutation-template.md` holds the shape).
One `shopify store execute … --allow-mutations` creates all four via aliases. Parse `userErrors`
per alias; anything non-empty → report it and stop.

### Step 8 — Verify the images actually landed

**Empty `userErrors` does not mean the images arrived.** Shopify fetches `originalSource`
server-side and media processing is asynchronous even under `synchronous: true`.

So re-query the seeded products' `media { nodes { status, mediaErrors { details } } }`. Retry
once after a short wait on `PROCESSING`; if it is still processing after that, report it
unresolved rather than retrying again or claiming success. Name any product left without an image
and suggest supplying a direct image URL.

**Verify by the product IDs the push returned, not by a tag query.** `products(query: "tag:…")`
is served by a search index that lags writes: in the live run, a tag query immediately after a
clean 4-product push returned only the *previous* run's products, then the full set seconds
later. Verifying by tag right after a write can therefore report a healthy seed as broken.
`nodes(ids: […])` is authoritative and index-independent. The tag query stays correct for the
archive lookup in Step 6, where the previous run is old and lag is harmless.

This step is what catches hotlink- or referer-protected prospect CDNs — the failure mode most
likely to embarrass someone mid-demo, and invisible without it.

### Step 9 — Report

- Each product with its type, seeded price, variant count and Admin link.
- **The four demos now available, named explicitly**, taken from the shaping script's own
  output rather than recomputed:
  - even inside one product — which product, and which size swap
  - even across products — which pair
  - uneven upward — which exchange, and the balance the customer **pays**
  - uneven downward — which exchange and refund, or that it is unavailable
- Any price that was adjusted, as `was → now`, so whoever runs the demo knows which figures
  are not the prospect's real prices.
- **No currency symbols** in any quoted figure. A dev store set to a non-GBP or non-USD
  currency displays different symbols, so demo scripts must not hard-code one.

## Testing

Repo convention is stdlib `unittest`; `pytest` is not installed and nothing is `pip install`ed.

```bash
cd plugins/pl-tools/scripts && python3 -m unittest discover -s tests -v
```

`shape_product_mix.py` is pure logic (stdin JSON → stdout JSON) and carries real edge cases, so
it is unit tested:

- a natural pair with a dearer product → **nothing altered at all**
- all four distinct → the closest of the two eligible pairs converges downward
- all four identical → pair untouched, most expensive nudged up
- the most expensive product tied with the pair → nudged above it
- the pair never includes the most expensive product, so something is always above it
- ties in gap resolve to the cheaper pair
- the downward refund demo is reported when a product sits below the pair, and reported as
  unavailable when none does
- price normalisation: currency symbols, thousands commas, decimal commas, 2dp rounding,
  unparseable input raising
- every variant in the matrix carries non-zero stock
- variant matrix: two axes produce the cartesian product; a single-value axis is dropped; no
  axis at all falls back to `S`/`M`/`L`; every product ends with ≥2 variants
- duplicate product types are surfaced as a warning, not a failure
- anything other than exactly four products raises

Browser and CLI orchestration is prose in `SKILL.md`, not scripted, and is verified by a live
run against `parcellab-demo-jls`.

## Constraints

- **Real writes to a real Shopify store.** Dev stores only, destination confirmed by name
  before mutating, never a production merchant store.
- `--allow-mutations` is a genuine safety gate — call that out rather than hiding it.
- GitHub work goes to the personal account `jamie1leesmith-lgtm` only, never the `parcelLab`
  org. Check `git remote -v` before pushing.
- Release is: commit, push to `main`, tell the team to run `/pl-update`. **Do not add a
  `version` field to `pl-tools`** — its version resolves to the git SHA deliberately.

## Definition of done

One invocation takes a prospect URL and loads four of that prospect's products — four different
types, each with at least two real variants, one image each, and stock on every variant — into a
named Shopify dev store, priced so that all of these work: a size swap inside one product, an
even swap across a matched pair, and an uneven swap upward that makes the customer **pay** a
balance. Location ID resolved automatically, the previous prospect's products archived, and
images verified as actually present rather than assumed.
