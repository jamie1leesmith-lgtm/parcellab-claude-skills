---
name: demo-request
description: Use this skill when the user wants to create a custom demo request from a prospect website URL. It guides Claude to research the prospect site, collect four representative products from real product detail pages, verify image URLs, ask the user to approve the selected articles and images, then submit the request through the Custom Demo Creator automation API.
argument-hint: <prospect-url>
---

# parcelLab Demo Request

## Overview

Create demo requests from a prospect URL. Research the site using Claude Code's **built-in browser** (the Browser pane, `mcp__Claude_Browser__*`), collect four representative products from real PDPs, validate image URLs, ask the user to approve the product set, then submit through the Custom Demo Creator automation API.

> **Browser pane, not Playwright MCP.** This skill previously required
> `mcp__playwright__*`, which is not installed and is not part of this plugin —
> the skill was unrunnable as a result. It now uses the same built-in Browser pane
> as `branded-template` and `order-lifecycle`. No Chrome extension, no MCP server,
> nothing to install.

## Required Environment

Config file at `~/.claude/parcellab-demo-request.env`:

```bash
CDC_DEMO_API_BASE_URL=https://your-cdc-api-url
CDC_DEMO_API_TOKEN=cdc_live_...
```

Never print the token value.

---

## Step 1 — Open the Browser pane

`mcp__Claude_Browser__preview_start` with `{ url: "<prospect URL>" }`.

That opens the pane and navigates in one call. Use `preview_start` for the *first*
page and `mcp__Claude_Browser__navigate` for every page after — calling `navigate`
before a pane exists fails with *"No preview is open"*.

The Browser pane is loaded by default in Claude Code, so there is nothing to check
and nothing to install. If `preview_start` itself is unavailable, say so and stop;
do not fall back to Claude-in-Chrome, which needs a logged-in Chrome and is not
what this skill is built for.

---

## Step 2 — Research the homepage

The pane is already on the prospect URL from Step 1.

Confirm the page loaded with `mcp__Claude_Browser__get_page_text`
(`{ max_chars: 2000 }`) — cheaper and more reliable than a screenshot for checking
you didn't land on a consent wall or bot block. Then extract brand metadata and
listing links with `mcp__Claude_Browser__javascript_tool`:

**Wrap the snippet as an IIFE.** `javascript_tool` evaluates an *expression*, so a
bare `() => {…}` returns the function rather than calling it. Every snippet below is
already wrapped as `(() => {…})()` — keep it that way.

```javascript
(() => {
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
})()
```

From this, infer:
- `prospect_name` — from `ogSiteName` or cleaned page `title`
- `region` — from TLD (`.co.uk` → UK, `.de` → DE, `.com` → US) or `lang`
- `category` — from listing links and meta description; one of `Home`, `Electronics`, `Fashion`

---

## Step 3 — Find product listing pages and PDP links

Navigate to one of the listing links found in Step 2:

```
mcp__Claude_Browser__navigate → { url: "<listing URL>" }
```

Then scrape PDP links with `mcp__Claude_Browser__javascript_tool`:

```javascript
(() => {
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
})()
```

If fewer than 4 PDP links are found, navigate to another listing page and repeat. Aim to collect at least 8 candidate PDP URLs before selecting.

---

## Step 4 — Extract product data from PDPs

For each of the 4 chosen PDPs, navigate with `mcp__Claude_Browser__navigate` and run
this via `mcp__Claude_Browser__javascript_tool`:

```javascript
(() => {
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
})()
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
node ${CLAUDE_PLUGIN_ROOT}/skills/demo-request/scripts/submit_demo_request.mjs /tmp/cdc-payload.json
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

- **Cookie / consent modal blocking the page** — `mcp__Claude_Browser__read_page`
  with `{ filter: "interactive" }` to get `ref_N` handles, then
  `mcp__Claude_Browser__computer` with `{ action: "left_click", ref: "ref_N" }` on
  the dismiss button. **Choose the most privacy-preserving option** — decline
  non-essential cookies rather than accepting all.
- **Login wall or geofence** — note what's blocked, collect what's accessible, ask the user to supply missing product details manually.
- **Lazy-loaded images** — scroll before running the image scoring snippet:
  `mcp__Claude_Browser__computer` with
  `{ action: "scroll", coordinate: [640, 400], scroll_direction: "down", scroll_amount: 5 }`,
  or `mcp__Claude_Browser__javascript_tool` running
  `(() => { window.scrollTo(0, document.body.scrollHeight / 2); return true; })()`.
- **Fewer than 4 products on one listing page** — navigate to additional listing pages and collect more candidates before finalising the four.
- **Bot protection / empty page text** — `get_page_text` returning a challenge page
  or near-nothing means the site blocked the fresh browser context. Say so and ask
  the user for another site or for product details directly. Do not try to work
  around the block.
- **Site needs a login to browse** — the Browser pane runs a fresh context with no
  saved sessions, which is fine for public storefronts and hopeless behind a login.
  That case is out of scope for this skill; don't switch to Claude-in-Chrome to get
  round it.
