# Prospect product scraping

Uses Claude Code's built-in **Browser pane** (`mcp__Claude_Browser__*`) — the same as
`demo-request`, `branded-template` and `order-lifecycle`. Not Claude-in-Chrome, not
Playwright.

`mcp__Claude_Browser__javascript_tool` evaluates an *expression*, so every snippet is
wrapped as an IIFE — `(() => {…})()`. Keep it that way; a bare `() => {…}` returns the
function instead of calling it.

## What to collect

**Four products of four different types** — a jumper, jeans, shoes, a jacket. Not four
jumpers: the cross-product exchange should look like a real decision, not a like-for-like
swap.

**A couple of values from each variant axis the site exposes**, typically Size and Colour,
or shoe size. Every product needs **at least two variants** so a small→medium swap
demonstrates an even exchange inside that one product — the most common real returns case
and the quickest thing to show.

Only **one image per product** is needed. Variants share it, so there is no need to find a
photo per colour.

## Find listing pages, then PDP links

Reuse `demo-request` Steps 2 and 3 verbatim — the listing-link and PDP-link snippets there
already work. Aim for at least 8 PDP candidates across **different categories** before
choosing four.

## Extract name, type, price, image and variant axes from a PDP

```javascript
(() => {
  const clean = (s) => (s || '').trim().replace(/\s+/g, ' ');

  const name = clean(
    document.querySelector('h1')?.innerText ||
    document.querySelector('[class*="product-name"], [class*="product-title"], [itemprop="name"]')?.innerText ||
    document.title
  ).slice(0, 120);

  // Product type: breadcrumb tail is the most reliable signal, then meta.
  const crumbs = Array.from(
    document.querySelectorAll('[class*="breadcrumb"] a, nav[aria-label*="readcrumb"] a')
  ).map(a => clean(a.innerText)).filter(Boolean);
  const productType = clean(
    crumbs[crumbs.length - 1] ||
    document.querySelector('meta[property="product:category"]')?.content ||
    ''
  ).slice(0, 40);

  // Price, most reliable source first. JSON-LD beats reading rendered text.
  let price = null;
  for (const node of document.querySelectorAll('script[type="application/ld+json"]')) {
    try {
      const blocks = [].concat(JSON.parse(node.textContent));
      for (const block of blocks) {
        const offers = [].concat(block.offers || block['@graph'] || []);
        for (const offer of offers) {
          const p = offer?.price ?? offer?.lowPrice ?? offer?.priceSpecification?.price;
          if (p) { price = String(p); break; }
        }
        if (price) break;
      }
    } catch { /* malformed JSON-LD is common; skip it */ }
    if (price) break;
  }
  if (!price) price = document.querySelector('meta[property="product:price:amount"]')?.content || null;
  if (!price) {
    const text = document.querySelector('[class*="price"], [itemprop="price"]')?.innerText || '';
    price = (text.match(/\d[\d.,]*/) || [null])[0];
  }

  // Variant axes. Real values only — never invent a colour.
  const axes = [];
  const seenAxis = new Set();
  const pushAxis = (rawName, rawValues) => {
    const axisName = clean(rawName).replace(/[:*]/g, '').trim();
    if (!axisName || seenAxis.has(axisName.toLowerCase())) return;
    const values = [...new Set(
      rawValues.map(v => clean(String(v)))
        .filter(v => v && v.length <= 20 && !/select|choose|guide|please/i.test(v))
    )];
    if (values.length >= 2) {
      seenAxis.add(axisName.toLowerCase());
      axes.push({ name: axisName, values: values.slice(0, 3) });
    }
  };

  // Shopify storefronts embed product JSON with the real options.
  for (const node of document.querySelectorAll('script[type="application/json"]')) {
    try {
      const data = JSON.parse(node.textContent);
      const product = data?.product || data;
      if (Array.isArray(product?.options)) {
        product.options.forEach((opt, i) => {
          const optName = opt?.name || opt;
          const values = opt?.values
            || (product.variants || []).map(v => v?.[`option${i + 1}`]).filter(Boolean);
          pushAxis(String(optName), values || []);
        });
      }
    } catch { /* not product JSON; skip */ }
  }

  // Fallback: labelled selects and swatch groups in the DOM.
  if (!axes.length) {
    for (const group of document.querySelectorAll(
      'select, fieldset, [data-option-name], [class*="swatch"], [class*="variant-option"]'
    )) {
      const label = group.getAttribute('data-option-name')
        || group.getAttribute('aria-label')
        || group.querySelector('legend, label')?.innerText
        || group.getAttribute('name') || '';
      if (!/size|colour|color/i.test(label)) continue;
      const values = Array.from(
        group.querySelectorAll('option, label, button, [role="radio"]')
      ).map(n => n.value || n.innerText || '');
      pushAxis(label, values);
    }
  }

  // Image scoring — verbatim from demo-request, which is proven.
  const score = (img) => {
    let s = 0;
    const src = (img.currentSrc || img.src || '').toLowerCase();
    const alt = (img.alt || '').toLowerCase();
    const r = img.getBoundingClientRect();
    if (r.width >= 400) s += 10;
    if (r.width >= 600) s += 5;
    if (img.naturalWidth >= 600) s += 8;
    if (img.naturalWidth >= 1000) s += 4;
    if (alt.length > 3) s += 3;
    if (src.includes('product') || src.includes('item') || src.includes('pdp')) s += 6;
    if (src.includes('thumb') || src.includes('icon') || src.includes('logo')) s -= 10;
    if (src.startsWith('data:')) s -= 20;
    if (src.endsWith('.svg')) s -= 10;
    if (src.includes('placeholder') || src.includes('lazy') || src.includes('blank')) s -= 15;
    if (src.includes('tracking') || src.includes('pixel')) s -= 20;
    if (img.closest('[class*="gallery"], [class*="carousel"], [class*="product"]')) s += 5;
    return s;
  };
  const bestImg = Array.from(document.querySelectorAll('img'))
    .filter(img => (img.currentSrc || img.src) && !(img.currentSrc || img.src).startsWith('data:'))
    .sort((a, b) => score(b) - score(a))[0];

  return {
    name,
    product_type: productType,
    price,
    options: axes,
    image_url: bestImg ? (bestImg.currentSrc || bestImg.src) : null,
    pdp_url: location.href,
  };
})()
```

Set `product_type` yourself from the product name if the breadcrumb comes back empty — a
short label like `Jumper`, `Jeans`, `Trainers` is all it needs to be.

## Edge cases

- **Consent modal** — `read_page` with `{ filter: "interactive" }` for `ref_N` handles,
  then click the dismiss control. **Decline non-essential cookies**, never accept all.
- **Lazy-loaded images** — scroll before scoring:
  `(() => { window.scrollTo(0, document.body.scrollHeight / 2); return true; })()`
- **Variant axes come back empty** — fine. The shaping script falls back to a Size axis of
  `S`/`M`/`L`, which still gives the in-product size swap. **Do not invent colour values**
  to fill the gap; a product photographed in red offered as "Navy" looks broken.
- **A variant picker that needs a click to reveal values** — click it, re-run the snippet.
  Not worth more than one attempt per product; the Size fallback is acceptable.
- **Price still null** — ask the user for that product's price rather than inventing one. A
  fabricated price in a demo to that prospect is worse than a question.
- **Bot protection / near-empty page text** — say so and stop. Do not work around a block.
- **Login wall** — out of scope. The pane runs a fresh context with no saved sessions.
