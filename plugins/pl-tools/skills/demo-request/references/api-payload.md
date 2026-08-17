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
- `products` (required): at least 1 item (no upper cap since the 2026-08-11
  order-model simplification) of `{ name (required), image_url?,
  category_override? }`.
- `selected_account_config_id`: optional **UUID or config name** — accepts
  either form (live-verified 2026-08-17; the earlier UUID-only restriction,
  and its 400 "invalid input syntax for type uuid" on a bare id, are gone).
  An unrecognized value is rejected with 403 "selected_account_config_id is
  not available". Which parcelLab/Shopify account config orders are
  generated/linked against; **omitted → the caller's default config**.
  No API exists to list configs. **Linking looks orders up in this config's
  target account** (live-verified): the practical setup is to point your CDC
  default config at your own demo account in the CDC UI and omit this field —
  that combination linked successfully on multiple live runs. Pass a UUID or
  name only when a run must target a config other than your default.
- `generate_orders`: optional boolean, default `true`. `false` creates the
  request in `queued` status with no synthetic orders.
- `orders`: optional array describing synthetic order composition when
  `generate_orders` is `true`: `{ name?, items?: [{ product_index (0-based
  into products), quantity? }] }`. Omit `items` → every product; omit `orders`
  entirely → one order named "Demo order" with every product. **There is no
  order-type enum any more** — `fraud_high | … | return_tracking` was removed
  2026-08-11; orders carry free-form human `name` labels only.
- `linked_orders`: optional array of `{ order_number, name? }` attaching
  orders that **already exist** in the target parcelLab account. Additive and
  best-effort: per-item failures land only in the request's activity log
  (`job_logs`) and never fail the HTTP call — verify attachment in-app.
  Regenerate/retry never touches linked orders. With token auth this is the
  ONLY moment linking is possible (the per-order endpoints require a session
  JWT).

Responses:

- `201 { id, status: "ready" | "queued", request_url }`
- `400 { error, details: { fieldErrors } }` — per-field messages.
- `401 / 403` — token missing/invalid or revoked.
- `500 { id, status: "failed", request_url, error }` — **the request still
  exists** and can be retried manually in-app. Report as "created but
  generation failed", never as "nothing happened".
