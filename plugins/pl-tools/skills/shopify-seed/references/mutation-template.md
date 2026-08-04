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

## Verify the media actually landed

```graphql
{
  products(first: 4, query: "tag:pl-demo-seed status:active") {
    nodes {
      id
      title
      media(first: 1) {
        nodes {
          status
          mediaErrors { code details }
          ... on MediaImage { image { url } }
        }
      }
    }
  }
}
```
