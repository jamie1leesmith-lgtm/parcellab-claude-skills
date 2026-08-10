# Custom Demo Creator Automation Payload

Canonical reference (always check before extending):
https://app.notion.com/p/parcellab/Automation-API-Reference-3b8c37dcb4c481789aa8c5e80fcfc730

Endpoint:

    POST /api/automation/demo-requests
    Authorization: Bearer cdc_live_...   (personal token, scope demo_requests:create)
    Content-Type: application/json

Fields:

- `prospect_name` (required): non-empty string.
- `website_url`: valid URL or empty. Triggers server-side brand/logo enrichment.
- `region` (required): `US` | `UK` | `DE`.
- `category` (required): `Home` | `Electronics` | `Fashion`.
- `notes`: optional string.
- `products` (required): exactly 4 items of
  `{ name (required), image_url?, category_override? }`.
- `selected_account_config_id`: optional UUID. Which parcelLab/Shopify account
  config orders are generated/linked against. **Omitted → the caller's default
  config.** No API exists to list or create configs — UUIDs come from the CDC UI.
- `generate_orders`: optional boolean, default `true`. `false` creates the
  request in `queued` status with no synthetic orders.
- `order_types`: optional array restricting synthetic generation. Enum:
  `fraud_high | fraud_medium | fraud_low | manual_return | return_tracking`.
- `linked_orders`: optional array of `{ order_number, order_type }` attaching
  orders that **already exist** in the target parcelLab account. Additive and
  best-effort: per-item failures land only in the request's activity log
  (`job_logs`) and never fail the HTTP call — verify attachment in-app.
  With token auth this is the ONLY moment linking is possible (the per-order
  endpoints require a session JWT).

Responses:

- `201 { id, status: "ready" | "queued", request_url }`
- `400 { error, details: { fieldErrors } }` — per-field messages.
- `401 / 403` — token missing/invalid or revoked.
- `500 { id, status: "failed", request_url, error }` — **the request still
  exists** and can be retried manually in-app. Report as "created but
  generation failed", never as "nothing happened".
