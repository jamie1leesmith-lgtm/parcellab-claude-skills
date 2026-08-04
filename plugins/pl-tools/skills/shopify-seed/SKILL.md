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

**Dev stores only.** Never a production merchant store. Say the store name out loud at
the confirmation so a wrong target is caught before any write.

---

## Step 2 — Resolve the location ID

Stock needs a location ID, and it is per-store. Fetch it rather than asking the user to
dig it out of an Admin URL:

```bash
shopify store execute -s "$SHOPIFY_DEMO_STORE" \
  --query '{ locations(first: 5) { nodes { id name isActive } } }'
```

Read-only, so **no `--allow-mutations`** — that flag is only for writes.

Take the first node with `isActive: true`. The `id` comes back as
`gid://shopify/Location/123456`, which is exactly what `ProductSetInventoryInput.locationId`
expects. No numeric-ID conversion needed.

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
`{ name, product_type, price, options, image_url, pdp_url }`.

**Four different product types**, and **a couple of values from each variant axis the site
exposes**. One image per product — variants share it.

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

It expects exactly 4 products, prints a JSON result per image, and **exits non-zero if any
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
shopify store execute -s "$SHOPIFY_DEMO_STORE" \
  --query '{ products(first: 50, query: "tag:pl-demo-seed status:active") { nodes { id title } } }'
```

If any come back, archive them using the aliased `productUpdate` shape in
`${CLAUDE_PLUGIN_ROOT}/skills/shopify-seed/references/mutation-template.md`:

```bash
shopify store execute -s "$SHOPIFY_DEMO_STORE" \
  --query-file /tmp/archive.graphql --variable-file /tmp/archive.json --allow-mutations
```

Archived products leave the storefront and the returns portal but are **not destroyed** —
un-archive in the Admin to recover them. Report what was archived, by name.

If nothing is tagged, say so and move on — a first run against a clean store is normal.

---

## Step 7 — Push the new products

Generate `/tmp/seed.graphql` and `/tmp/seed.json` from
`${CLAUDE_PLUGIN_ROOT}/skills/shopify-seed/references/mutation-template.md`, mapping the
shaped output onto the mutation:

- `name` → `title`
- `options[]` → `productOptions[]`, with 1-based `position`; each `values[]` string becomes
  `{ "name": "<value>" }`
- `variants[].option_values[]` → `optionValues[]` (`option_name` → `optionName`)
- `variants[].quantity` and `location_id` → `inventoryQuantities[]` with `name: "available"`
- `image_url` → a single `files[]` entry with `contentType: IMAGE`
- `product_type` → `productType`, `tags` → `tags`

These files are generated per run, not shipped — the products differ every time.

```bash
shopify store execute -s "$SHOPIFY_DEMO_STORE" \
  --query-file /tmp/seed.graphql --variable-file /tmp/seed.json --allow-mutations
```

`--allow-mutations` is mandatory for writes — without it the mutation is refused. Treat
that as a safety feature, not an annoyance. `--query-file` and `--query` are mutually
exclusive, as are `--variable-file` and `--variables`.

Check `userErrors` on **every alias**, not just the first. Any non-empty `userErrors` →
report it and stop; do not continue to verification with a partial seed.
