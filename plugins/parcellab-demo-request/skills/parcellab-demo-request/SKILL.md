---
name: parcellab-demo-request
description: Use this skill when the user wants to create a custom demo request from a prospect website URL. It guides Claude to research the prospect site, collect four representative products from real product detail pages, verify image URLs, ask the user to approve the selected articles and images, then submit the request through the Custom Demo Creator automation API.
allowed-tools: mcp__playwright__browser_navigate, mcp__playwright__browser_evaluate, mcp__playwright__browser_snapshot, mcp__playwright__browser_take_screenshot, mcp__playwright__browser_click, Bash(curl:*), Bash(node:*)
argument-hint: <prospect-url>
---

# parcelLab Demo Request

## Overview

Create demo requests from a prospect URL. Research the site using the Playwright MCP browser, collect four representative products from real PDPs, validate image URLs, ask the user to approve the product set, then submit through the Custom Demo Creator automation API.

## Required Environment

Config file at `~/.claude/parcellab-demo-request.env`:

```bash
CDC_DEMO_API_BASE_URL=https://your-cdc-api-url
CDC_DEMO_API_TOKEN=cdc_live_...
```

Never print the token value.

---

## Step 1 — Check Playwright is connected

Verify `mcp__playwright__browser_navigate` is available. If not, stop and tell the user:

> "Playwright MCP isn't connected. Run `claude mcp list` to confirm it's listed, or restart Claude Code and try again."

---

## Step 2 — Research the homepage

Navigate to the prospect URL:

```
mcp__playwright__browser_navigate → prospect URL
```

Take a screenshot to confirm the page loaded. Then run this JS to extract brand metadata and find product listing links:

```javascript
() => {
  const title = document.title;
  const metaDesc = document.querySelector('meta[name="description"]')?.content || '';
  const ogSiteName = document.querySelector('meta[property="og:site_name"]')?.content || '';
  const lang = document.documentElement.lang || '';

  // Find links that look like category/listing pages
  const listingLinks = Array.from(document.querySelectorAll('a[href]'))
    .map(a => ({ href: a.href, text: a.innerText?.trim().slice(0, 60) }))
    .filter(a => {
      const h = a.href.toLowerCase();
      return (
        h.includes('/collection') || h.includes('/category') ||
        h.includes('/products') || h.includes('/shop') ||
        h.includes('/men') || h.includes('/women') ||
        h.includes('/new') || h.includes('/sale') ||
        h.includes('/clothing') || h.includes('/shoes') ||
        h.includes('/accessories') || h.includes('/furniture') ||
        h.includes('/electronics')
      );
    })
    .filter((a, i, arr) => arr.findIndex(b => b.href === a.href) === i)
    .slice(0, 10);

  return { title, metaDesc, ogSiteName, lang, listingLinks };
}
```

From this, infer:
- `prospect_name` — from `ogSiteName` or cleaned page `title`
- `region` — from TLD (`.co.uk` → UK, `.de` → DE, `.com` → US) or `lang`
- `category` — from listing links and meta description; one of `Home`, `Electronics`, `Fashion`

---

## Step 3 — Find product listing pages and PDP links

Navigate to one of the listing links found in Step 2:

```
mcp__playwright__browser_navigate → listing URL
```

Then scrape PDP links:

```javascript
() => {
  // Find product links — look for URL patterns common to PDPs
  const pdpLinks = Array.from(document.querySelectorAll('a[href]'))
    .map(a => ({ href: a.href, text: a.innerText?.trim().slice(0, 80) }))
    .filter(a => {
      const h = a.href.toLowerCase();
      return (
        h.includes('/product') || h.includes('/p/') ||
        h.includes('/item') || h.includes('/dp/') ||
        h.includes('/buy') || h.includes('/pd/') ||
        // fallback: long path with no listing keywords
        (h.split('/').length >= 5 && !h.includes('?') && !h.includes('#'))
      );
    })
    .filter((a, i, arr) => arr.findIndex(b => b.href === a.href) === i)
    .slice(0, 20);

  return { pdpLinks };
}
```

If fewer than 4 PDP links are found, navigate to another listing page and repeat. Aim to collect at least 8 candidate PDP URLs before selecting.

---

## Step 4 — Extract product data from PDPs

For each of the 4 chosen PDPs, navigate to the page and run:

```javascript
() => {
  // Product name
  const name = (
    document.querySelector('h1')?.innerText ||
    document.querySelector('[class*="product-name"], [class*="product-title"], [itemprop="name"]')?.innerText ||
    document.title
  )?.trim().replace(/\s+/g, ' ').slice(0, 120);

  // Score candidate images — prefer large, product-focused images
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

  const imageUrl = bestImg ? (bestImg.currentSrc || bestImg.src) : null;

  return { name, imageUrl, pdpUrl: location.href };
}
```

Run this for each of the 4 PDPs and collect `{ name, imageUrl, pdpUrl }` for each.

---

## Step 5 — Validate image URLs

For each of the 4 image URLs, check it resolves to a real image:

```bash
curl -sIL --max-time 8 "{imageUrl}" | grep -iE '^(HTTP|content-type)'
```

An image is valid if:
- HTTP status is `200`
- `Content-Type` starts with `image/`

If an image fails:
1. Go back to that PDP in the browser and look for an alternative image URL by running the scoring snippet again with the failed URL excluded.
2. If still no valid image, ask the user to provide one before proceeding.

---

## Step 6 — User approval gate

Show the user a summary table before submitting anything:

| Field | Value |
|---|---|
| Prospect | inferred prospect name |
| Website | prospect URL |
| Region | US, UK, or DE |
| Category | Home, Electronics, or Fashion |

Then the four products:

| # | Product | PDP URL | Image URL | Image Check |
|---|---|---|---|---|
| 1 | … | … | … | ✅ / ❌ |
| 2 | … | … | … | ✅ / ❌ |
| 3 | … | … | … | ✅ / ❌ |
| 4 | … | … | … | ✅ / ❌ |

**Do not submit until the user explicitly approves.** If they want to swap a product or image, go back to the browser and find a replacement.

---

## Step 7 — Submit

Load config:

```bash
source ~/.claude/parcellab-demo-request.env
```

Write the payload to `/tmp/cdc-payload.json`:

```json
{
  "prospect_name": "...",
  "website_url": "...",
  "region": "US|UK|DE",
  "category": "Home|Electronics|Fashion",
  "notes": "Created via Claude Code skill from prospect URL research.",
  "products": [
    { "name": "...", "image_url": "..." },
    { "name": "...", "image_url": "..." },
    { "name": "...", "image_url": "..." },
    { "name": "...", "image_url": "..." }
  ]
}
```

Submit:

```bash
node ~/.claude/skills/parcellab-demo-request/scripts/submit_demo_request.mjs /tmp/cdc-payload.json
```

---

## Step 8 — Report back

Tell the user:
- Returned request ID and URL
- Status

On error:
- `401` — token missing or expired; ask user to update `~/.claude/parcellab-demo-request.env`
- `400` — payload validation failed; fix the fields in the API error and resubmit
- Image failures at submission — go back to Step 5 and replace the failing URL

---

## Edge cases

- **Cookie / consent modal blocking the page** — use `mcp__playwright__browser_snapshot` to find the dismiss button reference, then `mcp__playwright__browser_click` to close it before scraping.
- **Login wall or geofence** — note what's blocked, collect what's accessible, ask the user to supply missing product details manually.
- **Lazy-loaded images** — scroll the page before running the image scoring snippet: `window.scrollTo(0, document.body.scrollHeight / 2)` in a `mcp__playwright__browser_evaluate` call.
- **Fewer than 4 products on one listing page** — navigate to additional listing pages and collect more candidates before finalising the four.
