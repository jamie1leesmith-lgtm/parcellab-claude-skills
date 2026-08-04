# Verified GraphQL shapes

Verified against Shopify Admin GraphQL **2026-07**. Always request
`userErrors { field message }` — a silent partial failure is worse than an error.

## Find the previous seed

Read-only, so **no `--allow-mutations`**:

```graphql
{
  products(first: 50, query: "tag:pl-demo-seed status:active") {
    nodes { id title }
  }
}
```

This tag query is served by a search index that lags writes — verified live, immediately
after a successful 4-product push it returned only products from an older run, then
returned everything correctly a few seconds later. That lag is harmless here, because
what this query is looking for is the *previous* run, which is old enough that the index
has long since caught up. Do not reuse this query to verify the run that was just
pushed — see the ID-based verification below instead.

## Archive it

`productUpdate` takes **`product: ProductUpdateInput`**. The older `input: ProductInput`
argument is **deprecated** — do not use it. `ProductStatus` valid values are `ACTIVE`,
`ARCHIVED`, `DRAFT` and `UNLISTED`.

One aliased call per product found above:

```graphql
mutation ArchivePreviousSeed($p0: ProductUpdateInput!, $p1: ProductUpdateInput!) {
  a0: productUpdate(product: $p0) {
    product { id title status }
    userErrors { field message }
  }
  a1: productUpdate(product: $p1) {
    product { id title status }
    userErrors { field message }
  }
}
```

Variables:

```json
{
  "p0": { "id": "gid://shopify/Product/111", "status": "ARCHIVED" },
  "p1": { "id": "gid://shopify/Product/222", "status": "ARCHIVED" }
}
```

Archiving is reversible — the products leave the storefront and the returns portal but
nothing is destroyed.

## Create the new seed

`productSet(synchronous: true, input: ProductSetInput!)`, one aliased call per product so
a single command creates all four.

Confirmed input fields:

- `ProductSetInput` — `title`, `productType`, `status`, `tags`, `productOptions`, `variants`, `files`
- `OptionSetInput` — `name`, `position`, `values`
- `ProductVariantSetInput` — `price`, `published`, `optionValues`, `inventoryQuantities`
- `VariantOptionValueInput` — `optionName`, `name`
- `ProductSetInventoryInput` — `locationId`, `name` (use `"available"`), `quantity`
- `FileSetInput` — `originalSource`, `alt`, `filename`, `contentType`, `duplicateResolutionMode`

**Images ship in this same mutation** via `files`. `originalSource` explicitly accepts an
external URL. `contentType` is optional — Shopify sniffs it — but pass `IMAGE` for clarity.

**One image per product, none per variant.** `ProductVariantSetInput.file` exists, and any
variant file must also appear in the product's `files` array — but this skill does not use
it. Every variant of a product shares the single product image, which is all the demo
needs and removes the job of sourcing a photo per colour.

```graphql
mutation SeedProspectProducts(
  $product1: ProductSetInput!
  $product2: ProductSetInput!
  $product3: ProductSetInput!
  $product4: ProductSetInput!
) {
  p1: productSet(synchronous: true, input: $product1) {
    product { id title handle }
    userErrors { field message }
  }
  p2: productSet(synchronous: true, input: $product2) {
    product { id title handle }
    userErrors { field message }
  }
  p3: productSet(synchronous: true, input: $product3) {
    product { id title handle }
    userErrors { field message }
  }
  p4: productSet(synchronous: true, input: $product4) {
    product { id title handle }
    userErrors { field message }
  }
}
```

Variables, per product. Prices are unitless strings; `locationId` is the GID from Step 2.
`productOptions` mirrors the axes, and `variants` is the full cartesian product — every
combination present, every one stocked:

```json
{
  "product1": {
    "title": "Alpine Shell Jacket",
    "productType": "Jacket",
    "status": "ACTIVE",
    "tags": ["pl-demo-seed", "pl-prospect-acme"],
    "files": [
      { "originalSource": "https://cdn.example.com/jacket.jpg", "contentType": "IMAGE", "alt": "Alpine Shell Jacket" }
    ],
    "productOptions": [
      { "name": "Size", "position": 1, "values": [{ "name": "S" }, { "name": "M" }] },
      { "name": "Colour", "position": 2, "values": [{ "name": "Black" }, { "name": "Navy" }] }
    ],
    "variants": [
      {
        "optionValues": [{ "optionName": "Size", "name": "S" }, { "optionName": "Colour", "name": "Black" }],
        "price": "129.00",
        "published": true,
        "inventoryQuantities": [
          { "locationId": "gid://shopify/Location/123456", "name": "available", "quantity": 25 }
        ]
      },
      {
        "optionValues": [{ "optionName": "Size", "name": "S" }, { "optionName": "Colour", "name": "Navy" }],
        "price": "129.00",
        "published": true,
        "inventoryQuantities": [
          { "locationId": "gid://shopify/Location/123456", "name": "available", "quantity": 25 }
        ]
      },
      {
        "optionValues": [{ "optionName": "Size", "name": "M" }, { "optionName": "Colour", "name": "Black" }],
        "price": "129.00",
        "published": true,
        "inventoryQuantities": [
          { "locationId": "gid://shopify/Location/123456", "name": "available", "quantity": 25 }
        ]
      },
      {
        "optionValues": [{ "optionName": "Size", "name": "M" }, { "optionName": "Colour", "name": "Navy" }],
        "price": "129.00",
        "published": true,
        "inventoryQuantities": [
          { "locationId": "gid://shopify/Location/123456", "name": "available", "quantity": 25 }
        ]
      }
    ]
  }
}
```

Every variant of a product carries the same price — that is what makes the in-product size
swap an *even* exchange.

`productOptions[].position` is 1-based and must match the order the axes appear in
`optionValues`.

## Verify the media actually landed — by ID, not tag

Verify against the exact product IDs the push mutation just returned (`p1.product.id`
… `p4.product.id`), not a fresh tag search. The tag query above is index-backed and
lags writes — verified live, a tag query run immediately after a successful push (0
`userErrors`) returned only the previous run's products and none of the new ones,
then returned all 8 correctly a few seconds later. A tag query returning fewer
products than expected right after a push means index lag, not a failed push — but
the safer fix is to skip the index entirely and verify by ID, which is authoritative
the instant the mutation returns:

```graphql
{
  nodes(ids: ["gid://shopify/Product/111", "gid://shopify/Product/222", "gid://shopify/Product/333", "gid://shopify/Product/444"]) {
    ... on Product {
      id
      title
      media(first: 1) {
        nodes {
          status
          mediaErrors { code details }
          ... on MediaImage { image { url } }
        }
      }
      variants(first: 20) {
        nodes { inventoryQuantity selectedOptions { name value } }
      }
    }
  }
}
```

Same fields as the tag-based query, plus `variants` folded in so one query covers both
checks Step 8 needs (media status and stocked variants).
