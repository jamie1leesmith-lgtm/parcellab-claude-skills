#!/usr/bin/env node

import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const DEFAULT_BASE_URL = 'http://localhost:3000';
const CONFIG_PATH = path.join(os.homedir(), '.claude', 'parcellab-demo-request.env');
const VALID_REGIONS = new Set(['US', 'UK', 'DE']);
const VALID_CATEGORIES = new Set(['Home', 'Electronics', 'Fashion']);

function readInput() {
  const filePath = process.argv[2];
  if (filePath) return fs.readFileSync(filePath, 'utf8');
  return fs.readFileSync(0, 'utf8');
}

function parseEnvFile(filePath) {
  if (!fs.existsSync(filePath)) return {};

  const values = {};
  const lines = fs.readFileSync(filePath, 'utf8').split(/\r?\n/);

  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) continue;

    const match = trimmed.match(/^([A-Za-z_][A-Za-z0-9_]*)=(.*)$/);
    if (!match) continue;

    let value = match[2].trim();
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }

    values[match[1]] = value;
  }

  return values;
}

function assertUrlOrEmpty(value, field) {
  if (!value) return;
  const url = new URL(value);
  if (!['http:', 'https:'].includes(url.protocol)) {
    throw new Error(`${field} must be an HTTP(S) URL.`);
  }
}

function validatePayload(payload) {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
    throw new Error('Payload must be a JSON object.');
  }

  if (!String(payload.prospect_name ?? '').trim()) {
    throw new Error('prospect_name is required.');
  }

  assertUrlOrEmpty(String(payload.website_url ?? ''), 'website_url');

  if (!VALID_REGIONS.has(payload.region)) {
    throw new Error('region must be US, UK, or DE.');
  }

  if (!VALID_CATEGORIES.has(payload.category)) {
    throw new Error('category must be Home, Electronics, or Fashion.');
  }

  if (payload.selected_account_config_id != null) {
    // Accepts either the config's UUID or its (unique) name (live-verified
    // 2026-08-17; the earlier UUID-only restriction is gone). An
    // unrecognized value is rejected server-side with 403
    // "selected_account_config_id is not available".
    const value = String(payload.selected_account_config_id);
    if (!value.trim()) {
      throw new Error('selected_account_config_id must be a non-empty string (UUID or config name) when provided; omit it to use the caller\'s default CDC config.');
    }
  }

  if (payload.generate_orders != null && typeof payload.generate_orders !== 'boolean') {
    throw new Error('generate_orders must be a boolean when provided.');
  }

  // 2026-08-11 API order-model simplification: the order-type enum is gone.
  // Orders carry a free-form human `name` label; refuse the old field so a
  // stale caller fails loudly here instead of sending a dead field.
  if (payload.order_types != null) {
    throw new Error(
      'order_types was removed from the API (2026-08-11); describe synthetic orders with the orders[] field instead.'
    );
  }

  if (payload.orders != null) {
    if (!Array.isArray(payload.orders)) {
      throw new Error('orders must be an array when provided.');
    }
    payload.orders.forEach((o, i) => {
      if (o == null || typeof o !== 'object' || Array.isArray(o)) {
        throw new Error(`orders[${i}] must be an object.`);
      }
      if (o.items != null) {
        if (!Array.isArray(o.items) || o.items.length === 0) {
          throw new Error(`orders[${i}].items must be a non-empty array when provided.`);
        }
        o.items.forEach((item, j) => {
          if (!Number.isInteger(item?.product_index) || item.product_index < 0) {
            throw new Error(`orders[${i}].items[${j}].product_index must be a non-negative integer.`);
          }
          if (Array.isArray(payload.products) && item.product_index >= payload.products.length) {
            throw new Error(`orders[${i}].items[${j}].product_index is out of range for products.`);
          }
        });
      }
    });
  }

  if (payload.linked_orders != null) {
    if (!Array.isArray(payload.linked_orders)) {
      throw new Error('linked_orders must be an array when provided.');
    }
    payload.linked_orders.forEach((o, i) => {
      if (!String(o?.order_number ?? '').trim()) {
        throw new Error(`linked_orders[${i}].order_number is required.`);
      }
      if (o?.order_type != null) {
        throw new Error(
          `linked_orders[${i}].order_type was removed from the API (2026-08-11); use the optional free-form name instead.`
        );
      }
      if (o?.name != null && !String(o.name).trim()) {
        throw new Error(`linked_orders[${i}].name must be non-empty when provided.`);
      }
    });
  }

  if (!Array.isArray(payload.products) || payload.products.length < 1) {
    throw new Error('products must contain at least 1 item.');
  }

  payload.products.forEach((product, index) => {
    if (!String(product?.name ?? '').trim()) {
      throw new Error(`products[${index}].name is required.`);
    }
    assertUrlOrEmpty(String(product?.image_url ?? ''), `products[${index}].image_url`);
    if (product?.category_override != null
        && !VALID_CATEGORIES.has(product.category_override)) {
      throw new Error(`products[${index}].category_override must be Home, Electronics, or Fashion.`);
    }
  });
}

async function main() {
  const config = parseEnvFile(CONFIG_PATH);
  const baseUrl = (
    process.env.CDC_DEMO_API_BASE_URL ||
    config.CDC_DEMO_API_BASE_URL ||
    DEFAULT_BASE_URL
  ).replace(/\/+$/, '');
  const token = process.env.CDC_DEMO_API_TOKEN || config.CDC_DEMO_API_TOKEN;

  if (!token) {
    throw new Error(
      `CDC_DEMO_API_TOKEN is required. Set it as an environment variable or in ${CONFIG_PATH}.`
    );
  }

  const payload = JSON.parse(readInput());
  validatePayload(payload);

  const res = await fetch(`${baseUrl}/api/automation/demo-requests`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  });

  const text = await res.text();
  let body;
  try {
    body = text ? JSON.parse(text) : {};
  } catch {
    body = { raw: text };
  }

  if (!res.ok) {
    console.error(JSON.stringify({ status: res.status, body }, null, 2));
    process.exit(1);
  }

  console.log(JSON.stringify({
    status: res.status,
    id: body.id,
    request_status: body.status,
    request_url: body.request_url,
  }, null, 2));
}

main().catch((err) => {
  console.error(err instanceof Error ? err.message : err);
  process.exit(1);
});
