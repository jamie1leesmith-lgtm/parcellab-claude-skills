---
name: shopify-seed
description: Seed a prospect's own products into a Shopify dev store so you can demo the parcelLab returns and exchanges flow with products the prospect actually sells. Browses the prospect's site for four products of different types, keeps their real size and colour variants, prices them so both even and uneven exchanges demo correctly, and pushes them with the Shopify CLI. Trigger on phrases like "seed [prospect]'s products into my Shopify store", "load [brand] products for an exchange demo", "set up the Shopify demo store for [prospect]", or any request to put a prospect's products into a Shopify dev store for a parcelLab returns demo.
argument-hint: <prospect-url>
---

# parcelLab — Shopify Prospect Seeding

Load four of a prospect's real products into a Shopify **dev** store, shaped so every
exchange demo works. Run once per prospect, per demo.

Four demos have to be possible when this finishes:

| Demo | Needs |
|---|---|
| Even, inside one product — swap S for M | ≥2 variants per product |
| Even, across products | 2 products at the same price |
| Uneven **upward** — customer pays the balance | 1 product priced above that pair |
| Uneven downward — customer is refunded | a product below the pair *(if the catalogue offers one)* |

Writes to a real store. The destination is confirmed by name before the first write.

---

## Step 0 — Preflight

```bash
command -v shopify && shopify version
```

If missing, install it. `brew install shopify-cli` alone fails — the formula is not in
homebrew-core and Homebrew refuses to load it until the tap is trusted:

```bash
brew tap shopify/shopify
brew trust shopify/shopify
brew install shopify-cli
```

> **`brew trust` is real**, not a typo — added in Homebrew 6 for non-official taps. Verify
> with `brew help trust`. Without it, installing fails with *"Refusing to load formula … from
> untrusted tap"*, and Homebrew's own error text tells you to run it.

Then, **before anything else**:

```bash
shopify config autoupgrade off
```

A self-upgrade firing mid-session uninstalls the CLI, fails to install the replacement,
and leaves a dangling symlink with no working `shopify` command. One command avoids it.

> `shopify populate` does not exist — it was dropped after CLI 2.x.
> `SHOPIFY_CLI_SKIP_UPDATE_CHECK` is not a real environment variable; setting it does
> nothing. `shopify config autoupgrade off` is the real control.

---

## Step 1 — Resolve the destination store

Read the stored store first:

```bash
cat ~/.claude/parcellab-shopify-seed.env 2>/dev/null
```

**If `SHOPIFY_DEMO_STORE` is set and the user has not named a different store:** use it,
state which store you are using in your output, and do not ask again.

**If it is not set,** list the stores the user has actually authenticated:

```bash
shopify store auth list
```

That prints a `Subdomain` / `Connected` table. Note `shopify store list` is a different
command — it covers *organisation* stores and returns "No stores found" for a
directly-authenticated dev store, which is not an error.

- Exactly one store → confirm it **by name** and get an explicit yes.
- Several → ask which one.
- None → authenticate, warning the user that **a browser consent window will open**:

```bash
shopify store auth -s <store>.myshopify.com --scopes write_products,write_inventory
```

`<store>` is a placeholder — substitute the confirmed subdomain, never write the literal
text `<store>`.

Once confirmed, persist it:

```bash
echo 'SHOPIFY_DEMO_STORE=<store>.myshopify.com' > ~/.claude/parcellab-shopify-seed.env
```

Again, substitute the real subdomain here — a literal `<store>` in this file would
silently point every later run at a nonexistent store.

A config file rather than an env var: env vars are read only at app startup, so a value
written here would stay invisible until a full quit (⌘Q).

Every later command that references `$SHOPIFY_DEMO_STORE` sources this file first — each
Bash invocation is its own shell, so nothing set in one command block survives into the
next. Prefix each such block with:

```bash
source ~/.claude/parcellab-shopify-seed.env
```

> **On an orchestrated run, pass the store literally instead of sourcing.** A permission
> rule like `Bash(shopify store execute *)` matches on the command's leading text, so a
> `source …env && shopify store execute …` compound starts with `source` and fails to
> match — every Shopify write then prompts, mid-run (hit live 2026-08-11). The conductor
> already knows the store from the manifest, so write
> `shopify store execute -s <store>.myshopify.com …` with the value substituted.

**Dev stores only.** Never a production merchant store. Say the store name out loud at
the confirmation so a wrong target is caught before any write.

---

## Step 2 — Resolve the location ID

Stock needs a location ID, and it is per-store. Fetch it rather than asking the user to
dig it out of an Admin URL:

```bash
source ~/.claude/parcellab-shopify-seed.env
shopify store execute -s "$SHOPIFY_DEMO_STORE" \
  --query '{ locations(first: 20) { nodes { id name isActive fulfillsOnlineOrders shipsInventory } } }'
```

Read-only, so **no `--allow-mutations`** — that flag is only for writes.

**Pick the location the online store actually sells from**, in this order:

1. `isActive` **and** `fulfillsOnlineOrders` **and** `shipsInventory`
2. `isActive` **and** `fulfillsOnlineOrders`
3. any `isActive` — and say so, because stock placed here may not be sellable

Do not just take the first active location. A store can have several, and stock sitting at
one the online store does not fulfil from leaves every variant stocked but **unsellable** —
which looks exactly like the zero-stock failure, with the numbers all appearing correct.
Verify with `availableForSale` on a variant after the push (Step 8 checks this).

Name the chosen location in your output, and if you fell through to case 3, say which
locations were rejected and why.

The `id` comes back as `gid://shopify/Location/123456`, which is exactly what
`ProductSetInventoryInput.locationId` expects. No numeric-ID conversion needed.

If no active location exists, stop and tell the user — stock cannot be set without one.

---

## Step 3 — Collect four of the prospect's products

Open the pane on the prospect URL:

`mcp__Claude_Browser__preview_start` with `{ url: "<prospect URL>" }`.

Use `preview_start` for the *first* page and `mcp__Claude_Browser__navigate` for every page
after — calling `navigate` before a pane exists fails with *"No preview is open"*.

Confirm the page loaded with `mcp__Claude_Browser__get_page_text` (`{ max_chars: 2000 }`)
before scraping — cheaper and more reliable than a screenshot for spotting a consent wall
or a bot block.

Then follow `${CLAUDE_PLUGIN_ROOT}/skills/shopify-seed/references/product-scrape.md` to
collect exactly four products as
`{ name, product_type, price, options, image_url, pdp_url }`. That reference's landing
guard is required before a candidate counts as one of the four — a collection page can
link to a product URL that redirects back to the listing or 404s, which is why more than
four PDP candidates are worth gathering up front.

**Four different product types**, and **up to three values from each variant axis the site
exposes** (`shape_product_mix.py` caps both axes and values-per-axis at 3).

**For clothing, get Size *and* Colour** — three sizes × three colours is nine variants, which
looks like a real product on the variant picker where Size alone looks thin. Footwear is
usually shoe size only, which is fine.

Colour often isn't on the PDP itself: some sites publish each colourway as a separate product
page and put the colour name only in the link between them. The scrape reference harvests
those siblings — check a garment came back with two axes before accepting one, and never
invent colour values to pad it.

One image per product — variants share it, including across colours.

### Assemble the payload

Derive `prospect_handle` from the prospect URL: take the host, drop a leading `www.`, drop
the TLD (and any `.co.uk`-style second-level suffix), lowercase it, and replace any run of
non-alphanumeric characters with a single hyphen — `https://www.acme-store.co.uk/collections/new`
gives `acme-store`, so the seeded products tag as `pl-prospect-acme-store`.

Write `/tmp/seed-products.json` with the full shape `shape_product_mix.py` needs — not just
the products:

```json
{
  "products": [ … the four scraped products … ],
  "location_id": "<the gid:// value from Step 2>",
  "prospect_handle": "<derived above>"
}
```

### Validate the images

Reuse `demo-request`'s checker against the same file:

```bash
node ${CLAUDE_PLUGIN_ROOT}/skills/demo-request/scripts/check_images.mjs /tmp/seed-products.json
```

It expects at least 1 product, prints a JSON result per image, and **exits non-zero if any
fails**. It retries HEAD as a ranged GET on 403/405, which is the hotlink-protected CDN
case — and that same protection will later defeat Shopify's own server-side fetch, so an
image failing here will not work in Step 8 either. Replace it now.

If an image fails, go back to that PDP and pick the next-best-scoring image. If none work,
ask the user for a direct image URL.

---

## Step 4 — Shape the mix

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/shape_product_mix.py < /tmp/seed-products.json > /tmp/seed-shaped.json
```

Input keys: `products[]` (`name`, `product_type`, `price`, `options`, `image_url`,
`pdp_url`), `location_id`, `prospect_handle`, optional `stock_per_variant` (defaults to 25).

What it does, and why:

- Builds the **variant matrix** — the cartesian product of the axes, so Size×Colour gives 6
  variants — with non-zero stock on every one. A zero-stock variant is invisible as an
  exchange target, so the demo silently shows fewer options and looks broken.
- Drops any single-value axis, and falls back to `S`/`M`/`L` if no axis survives, so every
  product ends with **≥2 variants**.
- Picks a **matched pair from the three cheapest products**, leaving the dearest above it.
  That is what makes the uneven demo go *upward* and exercise taking payment — a merely
  "different" price could be satisfied by exchanging downward and never show that step.
- **Changes nothing at all** when the catalogue already has a natural pair and a dearer
  item, which is the common case. At most two prices ever move.

Read `warnings` from the output — repeated product types are surfaced there. It exits
non-zero on an unparseable price.

---

## Step 5 — Approval gate

Show the destination store **by name**, then:

| # | Product | Type | Real price | Seeded price | Adjusted | Variants | Image |
|---|---|---|---|---|---|---|---|

Then, straight from the script's `demos` output:

- **Even, in-product:** *[product]*, *[option]* *[swap]*
- **Even, cross-product:** *[A]* ↔ *[B]*
- **Uneven upward — customer pays:** *[A]* → *[D]*, balance *[balance]*
- **Uneven downward — refund:** *[A]* → *[C]*, refund *[refund]* — or *not available*

Call out any adjustment as `was → now`; these are the only places real prospect data was
altered. Surface any `warnings` too, and offer to swap a product out.

Quote figures **without currency symbols**; dev-store currency varies.

**No writes before an explicit yes.**

---

## Step 6 — Archive the previous prospect's products

Only after the Step 5 approval.

Every product this skill creates carries the tags `pl-demo-seed` and
`pl-prospect-<handle>`, which is what makes cleanup possible. Find the previous run:

```bash
source ~/.claude/parcellab-shopify-seed.env
shopify store execute -s "$SHOPIFY_DEMO_STORE" \
  --query '{ products(first: 50, query: "tag:pl-demo-seed status:active") { nodes { id title } } }'
```

`first: 50` truncates silently — more than 50 tagged products means archiving in two
passes (page with the query's cursor, or run this step twice).

If any come back, generate `/tmp/archive.graphql` and `/tmp/archive.json` from the
aliased `productUpdate` shape in
`${CLAUDE_PLUGIN_ROOT}/skills/shopify-seed/references/mutation-template.md`, then run:

```bash
source ~/.claude/parcellab-shopify-seed.env
shopify store execute -s "$SHOPIFY_DEMO_STORE" \
  --query-file /tmp/archive.graphql --variable-file /tmp/archive.json --allow-mutations
```

Archived products leave the storefront and the returns portal but are **not destroyed** —
un-archive in the Admin to recover them. Report what was archived, by name.

If nothing is tagged, say so and move on — a first run against a clean store is normal.

**If Step 7's push then fails**, these archived products are the recovery path — see
Step 7's failure branch below.

---

## Step 7 — Push the new products

Generate `/tmp/seed.graphql` and `/tmp/seed.json` from
`${CLAUDE_PLUGIN_ROOT}/skills/shopify-seed/references/mutation-template.md`, mapping
`/tmp/seed-shaped.json` (Step 4's output) onto the mutation:

- `name` → `title`
- `options[]` → `productOptions[]`, with 1-based `position`; each `values[]` string becomes
  `{ "name": "<value>" }`
- `variants[].option_values[]` → `optionValues[]` (`option_name` → `optionName`)
- `variants[].price` → `price`
- `variants[].quantity` and `location_id` → `inventoryQuantities[]` with `name: "available"`
- `image_url` → a single `files[]` entry with `contentType: IMAGE`
- `product_type` → `productType`, `tags` → `tags`
- `status: "ACTIVE"` — the script never emits this field; set it explicitly rather than
  relying on `productSet`'s default, since Step 6's next-run lookup searches
  `status:active`

These files are generated per run, not shipped — the products differ every time.

```bash
source ~/.claude/parcellab-shopify-seed.env
shopify store execute -s "$SHOPIFY_DEMO_STORE" \
  --query-file /tmp/seed.graphql --variable-file /tmp/seed.json --allow-mutations
```

`--allow-mutations` is mandatory for writes — without it the mutation is refused. Treat
that as a safety feature, not an annoyance. `--query-file` and `--query` are mutually
exclusive, as are `--variable-file` and `--variables`.

Check `userErrors` on **every alias**, not just the first. Any non-empty `userErrors` →
report it and stop; do not continue to verification with a partial seed.

**If this fails**, Step 6 already archived the previous seed — the store now has no
active seed at all. That is recoverable, not fatal: name the products archived in Step
6, tell the user they can be restored, and give the re-activation route per product:

```graphql
mutation { productUpdate(product: { id: "<gid>", status: ACTIVE }) { product { id status } userErrors { field message } } }
```

Only after either a clean push or a restored previous seed should you report the
outcome to the user.

---

## Step 8 — Verify the images actually landed

**Empty `userErrors` does not mean the images arrived.** Shopify fetches `originalSource`
server-side, and media processing is asynchronous **even under `synchronous: true`**. A
hotlink- or referer-protected prospect CDN fails at that point, well after the mutation
returned success.

**Verify by the product IDs Step 7's mutation returned** (`p1.product.id` …
`p4.product.id`), not by a fresh tag search. `products(query: "tag:pl-demo-seed")` is
served by a search index that lags writes — verified live, run immediately after a
successful push it returned only the previous run's products and none of the new ones,
then returned all of them correctly a few seconds later. **A tag query returning fewer
products than expected right after a push means index lag, not a failed push** — the IDs
from the mutation response sidestep that entirely, since they are authoritative the
instant the mutation returns.

Write `/tmp/verify-media.graphql` from the ID-based verification query in
`${CLAUDE_PLUGIN_ROOT}/skills/shopify-seed/references/mutation-template.md`, substituting
the four captured IDs, then re-query:

```bash
source ~/.claude/parcellab-shopify-seed.env
shopify store execute -s "$SHOPIFY_DEMO_STORE" \
  --query-file /tmp/verify-media.graphql
```

Read-only — no `--allow-mutations`.

- `status: READY` and an `image { url }` → good.
- `status: PROCESSING` → wait a few seconds and re-run **once**; if it is still
  `PROCESSING` after that retry, treat it the same as a failure for reporting — name the
  product, say its image is unresolved rather than broken, and do not report success.
- `status: FAILED`, `mediaErrors` populated, no media node at all, or a `null` entry in the
  `nodes(ids: …)` result (an ID that resolved to nothing) — any of these means that product
  has no image. Name it, quote `mediaErrors.details` where present, and offer to re-push
  that product with a different image URL. Do not report success.

The same by-ID query returns `variants` too, so confirm stock from that one response
rather than a second tag-based call — a silently dropped variant removes an exchange
target. Every product needs **≥2 variants**, every variant needs `inventoryQuantity` above
zero, and every variant needs **`availableForSale: true`**. A zero-stock variant is invisible
as an exchange target — the demo would show fewer options than expected and look broken.

`availableForSale: false` while `inventoryQuantity` is above zero means the stock went to a
location the online store does not sell from. The numbers all look right and nothing is
purchasable. Re-check the Step 2 location choice: prefer one with `fulfillsOnlineOrders`.

**If any of the three checks fails** — fewer than 2 variants, a variant at zero stock, or a
variant not available for sale — name the product and the offending variant, say it will be
invisible as an exchange target, and do not report success.

---

## Step 9 — Report

| # | Product | Type | Seeded price | Variants | Stock | Image | Admin |
|---|---|---|---|---|---|---|---|

Admin links are `https://admin.shopify.com/store/<subdomain>/products/<numeric-id>` — the
numeric part of the product GID.

Then the demos now available, taken **straight from the shaping script's `demos` output**
rather than recomputed:

- **Even, in-product:** *[product]* — *[option]*: *[swap]*, nothing to pay.
- **Even, across products:** *[A]* ↔ *[B]*, same price, nothing to pay.
- **Uneven upward:** *[A]* → *[D]*, customer **pays** *[balance]*.
- **Uneven downward:** *[A]* → *[C]*, customer is refunded *[refund]* — or say it is not
  available for this product set.

Repeat any price adjustments as `was → now`, so whoever runs the demo knows which figures
are not the prospect's real prices. Surface any `warnings` from the script.

**No currency symbols** in any figure — a dev store set to a non-GBP or non-USD currency
displays different symbols, so a demo script must not hard-code one.

---

## Orchestrated runs (demo-environment)

When invoked as a background agent by the `demo-environment` conductor, the
brief names a run directory; `demo-manifest.json` and `seed/seed-products.json`
inside it replace Steps 1, 2, 3 and 5:

- **Store and location come from the manifest** (`shopify.store`,
  `shopify.location_id`) — both were confirmed/resolved at intake. State the
  store name in output; do not re-ask, do not run `store auth list`.
- **Products come from `seed/seed-products.json`** — already in Step 3's
  input shape with images verified at intake. Skip all browsing. The
  manifest's `selection.core4` products go to `shape_product_mix.py` on
  stdin exactly as the standalone flow does; the `selection.shopify_extra`
  products go in a temp JSON array passed via `--extras-file`, which seeds
  them at their own real price with the same option/variant logic (no
  matched-pair adjustment). One script call shapes the whole seed set — do
  not call the script's helpers directly.
- **The Step 5 approval is already given** (`approvals.products_approved_at`
  in the manifest). Do not wait for a yes.
- **Agent ground rules:** never open the Browser pane; never ask the user
  anything. A gap (missing file, image Shopify won't fetch, push failure) is
  a failure report, not a question: write it to the results file and stop.
- **Steps 0, 4, 6, 7, 8 run unchanged** (preflight, shaping via
  `shape_product_mix.py`, archive, push, verify by returned IDs).
- **Instead of the Step 9 prose-only report**, write
  `results/shopify-seed.json` in the run dir:
  `{"status": "ok"|"failed", "products": [{"title", "id", "admin_url",
  "seeded_price", "variants", "adjusted"}], "demos": <the shape script's
  demos output verbatim>, "warnings": [...], "error": null|"<message>"}` —
  then give the usual Step 9 tables as the agent's returned summary.
  Pin `"variants"`'s shape: `[{"id", "selectedOptions", "inventoryQuantity",
  "availableForSale"}]` — the variant `id` (a Shopify gid) is required, not
  optional, because the Shopify order engine builds each order's `lineItems`
  by looking up these gids; without them it has nothing to put in
  `lineItems[].variantId`.

Standalone behaviour (no brief/manifest): everything above this section,
unchanged.
