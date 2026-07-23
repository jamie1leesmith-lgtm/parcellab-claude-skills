# Custom Demo Creator Automation Payload

Endpoint:

```http
POST /api/automation/demo-requests
Authorization: Bearer cdc_live_...
Content-Type: application/json
```

Required JSON shape:

```json
{
  "prospect_name": "Brand Name",
  "website_url": "https://example.com",
  "region": "US",
  "category": "Fashion",
  "notes": "Created via Claude Code skill from prospect URL research.",
  "products": [
    { "name": "Product 1", "image_url": "https://..." },
    { "name": "Product 2", "image_url": "https://..." },
    { "name": "Product 3", "image_url": "https://..." },
    { "name": "Product 4", "image_url": "https://..." }
  ]
}
```

Field rules:

- `prospect_name`: non-empty string.
- `website_url`: valid URL or empty string.
- `region`: one of `US`, `UK`, `DE`.
- `category`: one of `Home`, `Electronics`, `Fashion`.
- `notes`: optional string.
- `selected_account_config_id`: optional UUID or null.
- `products`: exactly four items.
- `products[].name`: non-empty string.
- `products[].image_url`: valid HTTP(S) URL or empty string.

Successful response:

```json
{
  "id": "request-id",
  "status": "queued",
  "request_url": "http://localhost:3000/requests/request-id"
}
```
