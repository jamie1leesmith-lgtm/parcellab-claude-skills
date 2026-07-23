#!/usr/bin/env node

import fs from 'node:fs';

function readInput() {
  const path = process.argv[2];
  if (path) return fs.readFileSync(path, 'utf8');
  return fs.readFileSync(0, 'utf8');
}

function extractProducts(payload) {
  if (Array.isArray(payload)) return payload;
  if (Array.isArray(payload.products)) return payload.products;
  throw new Error('Input must be an array of products or an object with products.');
}

function getImageUrl(product) {
  return product.image_url ?? product.imageUrl ?? product.image ?? '';
}

function isImageContentType(contentType) {
  return /^image\//i.test(contentType);
}

async function checkImage(product, index) {
  const imageUrl = String(getImageUrl(product)).trim();
  const name = String(product.name ?? `Product ${index + 1}`).trim();

  if (!imageUrl) {
    return { index: index + 1, name, image_url: imageUrl, ok: false, reason: 'missing image_url' };
  }

  let url;
  try {
    url = new URL(imageUrl);
  } catch {
    return { index: index + 1, name, image_url: imageUrl, ok: false, reason: 'invalid URL' };
  }

  if (!['http:', 'https:'].includes(url.protocol)) {
    return { index: index + 1, name, image_url: imageUrl, ok: false, reason: 'not HTTP(S)' };
  }

  try {
    let res = await fetch(imageUrl, {
      method: 'HEAD',
      redirect: 'follow',
      headers: { 'User-Agent': 'Claude Code demo request image checker' },
    });

    if (res.status === 405 || res.status === 403) {
      res = await fetch(imageUrl, {
        method: 'GET',
        redirect: 'follow',
        headers: { Range: 'bytes=0-1023', 'User-Agent': 'Claude Code demo request image checker' },
      });
    }

    const contentType = res.headers.get('content-type') ?? '';
    const ok = res.ok && isImageContentType(contentType);
    return {
      index: index + 1,
      name,
      image_url: imageUrl,
      ok,
      status: res.status,
      content_type: contentType,
      reason: ok ? 'ok' : `HTTP ${res.status}, content-type ${contentType || 'missing'}`,
    };
  } catch (err) {
    return {
      index: index + 1,
      name,
      image_url: imageUrl,
      ok: false,
      reason: err instanceof Error ? err.message : 'fetch failed',
    };
  }
}

async function main() {
  const payload = JSON.parse(readInput());
  const products = extractProducts(payload);

  if (products.length !== 4) {
    throw new Error(`Expected exactly 4 products, received ${products.length}.`);
  }

  const results = await Promise.all(products.map(checkImage));
  console.log(JSON.stringify({ ok: results.every((r) => r.ok), results }, null, 2));

  if (results.some((r) => !r.ok)) process.exit(1);
}

main().catch((err) => {
  console.error(err instanceof Error ? err.message : err);
  process.exit(1);
});
