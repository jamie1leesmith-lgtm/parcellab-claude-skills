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
