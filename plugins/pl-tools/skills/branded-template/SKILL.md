---
name: branded-template
description: Create a branded transactional email layout in the user's ParcelLab account from a brand website URL — built-in-browser version. Browses and previews with Claude Code's built-in browser (the Browser pane, `mcp__Claude_Browser__*`) and pushes via the ParcelLab MCP connector. Trigger on phrases like "create a ParcelLab layout for [brand]", "add a layout for [brand] to ParcelLab", "build a [brand] email layout", "push a [brand] layout to parcellab", or any request to generate a journey layout in ParcelLab from a brand website. Requires Claude Code's built-in browser and the ParcelLab MCP connector.
---

# ParcelLab — Create Branded Journey Layout (Built-in Browser)

Given a brand website URL, scrape the live site with **Claude Code's built-in browser** (the Browser pane, `mcp__Claude_Browser__*`), extract brand styles and logo, generate a branded email layout HTML, preview it **live in the same Browser pane**, and push it to the **user's ParcelLab account** via the **ParcelLab MCP connector**.

> **Why this variant exists:** the original `parcellab-brand-layout` skill is hard-wired to the Playwright MCP and the ParcelLab CLI. This version uses the built-in browser (one tool family for both scraping *and* the live preview) plus the ParcelLab MCP connector — no CLI, no Playwright, and no external Chrome extension required.

> **Built-in browser vs. Claude-in-Chrome:** the built-in Browser pane runs in a fresh context (no logged-in sessions), which is fine for public brand homepages. If you ever need to scrape a site behind a login, that's the one case where Claude-in-Chrome (the user's real Chrome) would be required instead — this skill does not cover it.

> **Browser pane tabs:** `mcp__Claude_Browser__*` tools take a `tabId`; the primary tab is `"main"`. This skill reuses the `"main"` tab throughout — scraping the brand site first, then navigating the same tab to the local preview.

> **MCP tool naming:** ParcelLab MCP tools appear with a per-connector prefix (e.g. `mcp__<connector-id>__journey_write_layout`). This skill refers to them by their **suffix** — match whatever prefix is present in your tool list.

---

## Step 1 — Check prerequisites are connected

Verify both tool families are available before doing anything else:

1. **Built-in browser**: `mcp__Claude_Browser__preview_start` / `mcp__Claude_Browser__navigate` must be in the tool list (they are loaded by default in Claude Code — no ToolSearch needed). If they are genuinely unavailable, stop and tell the user the built-in browser isn't available in this session.
2. **ParcelLab MCP**: a tool ending in `__journey_write_layout` must be available (it may be deferred — search the tool list / ToolSearch for `journey_write_layout`). If not, stop and tell the user:
   > "The ParcelLab MCP connector isn't enabled. Enable it in Settings → Connectors, then try again."

---

## Step 1b — Determine the target ParcelLab account

The layout must be created in **the user's own account** — never assume a hardcoded ID.

1. If the user named an account ID in their request, use it.
2. Otherwise call the ParcelLab MCP tool ending in `__account_get_my_user` and read the `accounts` array:
   - **One account** → use it, and state which account you'll push to.
   - **Multiple accounts** → ask the user which one to use (show the IDs; you can enrich with names via the tool ending `__account_get_account`).
3. Confirm the account ID with the user **before** the push in Step 9. Refer to it as `{ACCOUNT_ID}` throughout.

---

## Step 2 — Navigate to the brand homepage

Open the Browser pane at the brand URL:

```
mcp__Claude_Browser__preview_start → { url: <the URL the user provided> }
```

This opens a browser tab (no dev server needed) — note the `tabId` (the primary tab is `"main"`) and reuse it for every `javascript_tool` / `computer` call below. If the pane is already open, use `mcp__Claude_Browser__navigate → { tabId: "main", url: <URL> }` instead. Wait for the page to fully load. Note the final redirected URL (some brands redirect to a locale, e.g. `zara.com → zara.com/uk/`).

---

## Step 3 — Extract brand styles

Run the extraction via `mcp__Claude_Browser__javascript_tool` with `{ action: "javascript_exec", tabId: "main", text: <snippet> }`.

> **IMPORTANT — REPL semantics:** `javascript_tool` returns the value of the *last expression* (like a console REPL) and serialises it as JSON; it does **not** honour a top-level `return`. Wrap the extraction in an **IIFE** so the last expression is the object you want, i.e. `(() => { ... return {...}; })()`. All snippets below are already wrapped this way.

```javascript
(() => {
  const computed = window.getComputedStyle(document.body);

  const sampleEl = (selector) => {
    const el = document.querySelector(selector);
    if (!el) return null;
    const s = window.getComputedStyle(el);
    return {
      fontFamily: s.fontFamily,
      fontSize: s.fontSize,
      fontWeight: s.fontWeight,
      color: s.color,
      backgroundColor: s.backgroundColor,
      letterSpacing: s.letterSpacing,
      lineHeight: s.lineHeight,
      textTransform: s.textTransform,
      borderRadius: s.borderRadius,
    };
  };

  const header = document.querySelector('header, [class*="header"], [class*="Header"]');
  const footer = document.querySelector('footer, [class*="footer"], [class*="Footer"]');

  const buttons = Array.from(document.querySelectorAll('button, a[class*="btn"], a[class*="button"], [role="button"]'))
    .slice(0, 8)
    .map(el => {
      const s = window.getComputedStyle(el);
      return {
        text: el.innerText?.trim().slice(0, 40),
        bg: s.backgroundColor,
        color: s.color,
        radius: s.borderRadius,
        textTransform: s.textTransform,
        letterSpacing: s.letterSpacing,
      };
    })
    .filter(b => b.bg && b.bg !== 'rgba(0, 0, 0, 0)');

  return {
    readyState: document.readyState,
    finalUrl: location.href,
    pageTitle: document.title,
    bodyBg: computed.backgroundColor,
    bodyColor: computed.color,
    bodyFont: computed.fontFamily,
    bodyFontSize: computed.fontSize,
    bodyFontWeight: computed.fontWeight,
    headerBg: header ? window.getComputedStyle(header).backgroundColor : null,
    headerColor: header ? window.getComputedStyle(header).color : null,
    footerBg: footer ? window.getComputedStyle(footer).backgroundColor : null,
    footerColor: footer ? window.getComputedStyle(footer).color : null,
    buttons,
    heading: sampleEl('h1, h2, h3'),
    nav: sampleEl('nav'),
    link: sampleEl('a'),
  };
})()
```

If the captured buttons are all transparent/grey utility chips, run a second pass over `main a, main button` filtering for solid dark or coloured backgrounds to find the true primary CTA.

To visually confirm the page loaded, take a screenshot with `mcp__Claude_Browser__computer` `{ action: "screenshot", tabId: "main" }`.

---

## Step 4 — Extract the hero image

Run this snippet (IIFE-wrapped for the REPL) via `mcp__Claude_Browser__javascript_tool`:

```javascript
(() => {
  const heroImages = Array.from(document.querySelectorAll(
    'main img, [class*="hero"] img, [class*="banner"] img, section img, [class*="grid"] img, [class*="carousel"] img'
  )).filter(img => {
    const r = img.getBoundingClientRect();
    return r.width > 400 && img.src && !img.src.includes('data:') && img.naturalWidth > 400;
  }).map(img => ({
    src: img.src,
    alt: img.alt,
    naturalW: img.naturalWidth,
    naturalH: img.naturalHeight,
    vw: Math.round(img.getBoundingClientRect().width),
    vh: Math.round(img.getBoundingClientRect().height),
  }));

  return { heroImages: heroImages.slice(0, 5) };
})()
```

**Hero image selection rules:**

1. Pick the **first landscape image** (`naturalW > naturalH`) with `naturalW ≥ 800` — this is almost always the primary campaign image.
2. **Clean the URL for email**: strip high-DPR multipliers (`dpr_2.0,`) but keep the full width (`w_1200`) — email clients scale via `width="600"` on the `<img>`, so the image stays crisp on retina.
3. If no large landscape image is found, fall back to a large square campaign image, then the OG image (`meta[property="og:image"]`). **Verify OG images before using them** (load via `new Image()` in `javascript_tool` and check dimensions; some brands' OG image is just a logo card, which duplicates the header logo and looks wrong).
4. If still nothing, skip the hero block entirely — don't use a placeholder.

**Hero block HTML** (goes between the header and the campaign block):

```html
<!-- Hero image -->
<tr>
  <td style="padding:0; line-height:0; font-size:0;">
    <img
      src="{HERO_IMAGE_URL}"
      alt="{HERO_IMAGE_ALT}"
      width="600"
      class="hero-img img-fluid"
      style="display:block; width:600px; max-width:100%; height:auto; border:0; outline:none; text-decoration:none;"
    />
  </td>
</tr>
```

Also add `.hero-img` to the mobile media query: `width: 100% !important; height: auto !important;`

---

## Step 5 — Extract the logo

Run this snippet (IIFE-wrapped) via `mcp__Claude_Browser__javascript_tool`:

```javascript
(() => {
  // Prefer <img> in header/logo container
  const logoImg = document.querySelector(
    'img[class*="logo"], img[alt*="logo" i], [class*="logo"] img, [class*="brand"] img, header img, a[aria-label*="home" i] img'
  );

  // Detect inline SVG logo (common in modern brands like ZARA)
  const logoSvgEl = document.querySelector(
    '[class*="logo"] svg, [class*="brand"] svg, header svg, a[aria-label*="home" i] svg, a[href="/"] svg'
  );

  // Get full SVG markup if found
  const logoSvgMarkup = logoSvgEl ? logoSvgEl.outerHTML : null;

  // OG image as last resort
  const ogImage = document.querySelector('meta[property="og:image"]')?.content;

  const header = document.querySelector('header, [class*="header"]');
  const headerImgs = Array.from(header?.querySelectorAll('img') || []).map(img => ({
    src: img.src, alt: img.alt, w: img.naturalWidth, h: img.naturalHeight
  }));

  return {
    logoImgSrc: logoImg?.src || null,
    logoSvgMarkup,
    ogImage,
    headerImgs,
  };
})()
```

**Watch out for multi-brand headers** (e.g. Nike's header contains Jordan and Converse SVGs too). If several SVGs are found, list them all with their parent link's `aria-label`/`href` and pick the one whose parent links to the homepage (`/`) or whose aria-label matches the brand name.

**Logo decision tree:**

1. If `logoImgSrc` is a valid image URL → use it for `__BRAND_HEADER_LOGO_URL__` and `__BRAND_FOOTER_LOGO_URL__`.
2. If the logo is an inline SVG (`logoSvgMarkup` is set, `logoImgSrc` is null):
   - Extract the full SVG `outerHTML`.
   - In the template, **replace** the `<img>` logo tags with the inline SVG directly.
   - For the **header** (dark bg): set `fill="#ffffff"` on the SVG path.
   - For the **footer** (dark bg): set `fill="#ffffff"` on the SVG path.
   - For a **light bg** variant: set `fill="#000000"`.
   - If the icon sits inside a mostly-empty square viewBox, **crop the viewBox to the path bounds** so the logo isn't rendered tiny inside whitespace.
   - Wrap in a non-MSO conditional: `<!--[if !mso]><!--> … SVG … <!--<![endif]-->` with an MSO fallback of plain uppercase text styled with letter-spacing.
3. If neither → use `ogImage` as a fallback, or leave a `[LOGO NOT FOUND]` placeholder and tell the user.

---

## Step 6 — Map brand tokens

From the extracted data, derive these values:

| Token | Source / Rule |
|---|---|
| `BRAND_NAME` | Brand display name (infer from domain or page title) |
| `FONT_STACK` | `bodyFont` — strip quotes if needed, add `Helvetica, Arial, sans-serif` fallback |
| `BODY_BG` | Usually `#f2f2f2` (light grey canvas) regardless of site body bg; use `#f5f5f5` minimum |
| `HEADER_BG` | If site header is dark → `#000000`. If coloured → that colour. If transparent/white → use the brand's primary CTA colour or `#000000` |
| `CARD_BG` | Always `#ffffff` |
| `CARD_BORDER` | `#e0e0e0` default; lighten brand primary if they have one |
| `CARD_ACCENT_STRIPE` | Brand's primary CTA button bg colour; default `#000000` |
| `TEXT_PRIMARY` | `bodyColor` if dark; else `#000000` |
| `SOFT_BG` | `#ffffff` (white, same as card) or very light grey |
| `CTA_BG` | Primary CTA button bg from `buttons[]` |
| `CTA_TEXT` | Primary CTA button color from `buttons[]`; usually `#ffffff` |
| `CTA_TEXT_TRANSFORM` | `uppercase` or `none` from `buttons[].textTransform` |
| `CTA_LETTER_SPACING` | From `buttons[].letterSpacing`; use `0.1em` if `normal` |
| `FOOTER_BG` | Dark colour — use `#000000` unless site footer is distinctly different |
| `FOOTER_TEXT` | `#ffffff` |
| `FOOTER_TEXT_MUTED` | `#888888` |
| `FOOTER_DIVIDER` | `#555555` |
| `RADIUS_LG` | `0px` if brand is sharp (buttons radius=0); `8px` medium; `18px` round |
| `RADIUS_SM` | Match CTA button radius from `buttons[]` |
| `FONT_WEIGHT_BODY` | `bodyFontWeight`; use `300` if the brand is light-weight (e.g. Zara) |
| `ADDRESS` | Infer from `footer` text or `/about`/`/contact` page; use `[ADDRESS — not found]` if missing |

**Colour normalisation:** convert all `rgb(r, g, b)` values to `#RRGGBB` hex before writing into the HTML.

```javascript
// Helper (run in javascript_tool if needed)
const rgbToHex = (rgb) => {
  const [r, g, b] = rgb.match(/\d+/g).map(Number);
  return '#' + [r, g, b].map(c => c.toString(16).padStart(2, '0')).join('').toUpperCase();
};
```

---

## Step 7 — Build the HTML

Read the base template **bundled with this skill**:

```
Read: <this skill's directory>/template.html
```

Substitute all `__BRAND_X__` tokens. Key structural rules for the final HTML:

- **Width:** 600px fixed, 100% on mobile.
- **Header:** black (or brand colour) background. Logo centred, padding `28px 32px 26px`.
- **Remove the soft transition band** (the `__BRAND_HEADER_BG_SOFT__` row) — replace it with a simple `24px` padding spacer above the campaign block.
- **Hero image block:** insert between the header row and the main canvas `<td>`, using the HTML from Step 4. Zero padding, zero line-height on the containing `<td>` so it sits flush against the header.
- **Campaign block:** `{{generated/campaignManager/banner}}{{generated/campaignManager/html}}{{generated/campaignManager/productRecommendation}}` — must pass through untouched in their own `<td>` with top padding.
- **Content card:** white, `border:1px solid #e0e0e0`, `border-radius:RADIUS_LG`, 4px black top-stripe, `padding:36px 36px 32px`. Contains `{{content}}` token.
- **Help block:** below the card, same border style. "NEED HELP?" in uppercase bold, body text, CTA button right-aligned.
- **Footer:** black background. Logo (white variant) centred, footer links row, received copy, address. All text muted white.
- **ParcelLab tokens** that must survive verbatim: `{{content}}`, `{{preview}}`, `{{schemaOrgMarkup}}`, `{{generated/campaignManager/banner}}`, `{{generated/campaignManager/html}}`, `{{generated/campaignManager/productRecommendation}}`.

Write to: `$HOME/parcellab-previews/{brand-name-lowercase}-parcellab-layout.html` — where `$HOME` is the current user's home directory. Create the folder if missing. **Do NOT write under `~/Documents`** — the preview server cannot read it (macOS TCC protection).

---

## Step 8 — Preview in the Browser pane (live-editable)

Serve the HTML file from disk and open it in the built-in Browser pane. This keeps follow-up edits a simple loop: edit the file → reload the pane → the user watches the change land. (Do NOT use `show_widget` — it bakes a static snapshot into the chat and cannot reflect later edits. Do NOT run `python3 -m http.server` via Bash — always go through `preview_start`.)

**Serving directory — TCC warning:** the preview server's spawned process **cannot read `~/Documents`** (macOS TCC protection → 404 "No permission to list directory"). Always serve from `$HOME/parcellab-previews/`.

1. Ensure the launch config exists at `{project}/.claude/launch.json`, substituting the current user's real home path for `{HOME}`:

```json
{
  "version": "0.0.1",
  "configurations": [
    {
      "name": "layout-preview",
      "runtimeExecutable": "python3",
      "runtimeArgs": [
        "-c",
        "import sys; sys.path = [p for p in sys.path if p]; import http.server, socketserver, functools; H = functools.partial(http.server.SimpleHTTPRequestHandler, directory='{HOME}/parcellab-previews'); socketserver.TCPServer(('127.0.0.1', 8098), H).serve_forever()"
      ],
      "port": 8098
    }
  ]
}
```

(The `sys.path` cleanup works around the Python 3.14 empty-path issue; the inline `-c` server avoids `--directory` cwd quirks.)

2. `mcp__Claude_Browser__preview_start` → `{ name: "layout-preview" }` (starts the python server from launch.json, reusing it if already running).
3. Point the pane at the file: `mcp__Claude_Browser__navigate` → `{ tabId: "main", url: "http://127.0.0.1:8098/{brand}-parcellab-layout.html" }`.
4. Confirm with `mcp__Claude_Browser__computer` `{ action: "screenshot", tabId: "main" }` (or `mcp__Claude_Browser__read_page` to verify structure/text).

**Iteration loop** (when the user asks for changes): edit `$HOME/parcellab-previews/{brand}-parcellab-layout.html` directly (it is the canonical working copy), then reload with `mcp__Claude_Browser__navigate` → `{ tabId: "main", url: <same URL> }` (or `javascript_tool` → `window.location.reload()`), then screenshot to confirm.

> **Note:** ParcelLab tokens (`{{content}}`, `{{generated/...}}`, `{{schemaOrgMarkup}}`) render as literal text in the preview — that is expected. The preview is for confirming branding, logo, hero image, colours and structure, not the injected order content.

Ask the user: *"Does this look right before I push to ParcelLab?"*

---

## Step 9 — Push to ParcelLab via the MCP connector

Once the user approves, read the final HTML from `$HOME/parcellab-previews/` and call the ParcelLab MCP tool ending in `__journey_write_layout`:

```
journey_write_layout → {
  "account": {ACCOUNT_ID},
  "data": {
    "name": "{BRAND_NAME}",
    "prettyName": "{BRAND_NAME}",
    "content": "<the full layout HTML as a string>",
    "language": "en",
    "autoLayout": []
  }
}
```

- Omit `id` to **create** a new layout; pass `id` to **update** an existing one (PATCH semantics).
- `"autoLayout"` must be an **empty list** `[]` on create — not `false` or `true`. Do not try to
  set the store mapping here; that happens in Step 9b, which has to read the account's other
  layouts first.
- To check existing layouts first, call the tool ending in `__journey_list_journey_layouts` with `{ "account": [{ACCOUNT_ID}] }` (optionally `search: "{BRAND_NAME}"` to avoid duplicates).

---

## Step 9b — Assign the template to a store (Auto Template Config)

A new layout is inert until a store points at it. That pointer is the **Auto Template Config**,
and it lives on the **layout**, not on the store — each layout carries an `autoLayout` list of
`{client, layout, country}` entries. There is no template field on the client, so there is no
way to look this up from the store side.

**Talk about stores by name, never by client id.** Ids are internal plumbing; the name is what
the user recognises.

### 9b.1 — List the account's stores

Call the tool ending in `__config_list_clients` with `{ "account": [{ACCOUNT_ID}] }`.

Build a name→id map for yourself. For each store, derive a display name with this fallback so
an option is never a blank string:

1. `name` — e.g. `Jamie's Shopify Store`
2. `fullName` — if `name` is empty
3. `key` — e.g. `parcellab-demo-jls.myshopify.com`, if both are empty

Append `(default)` to the store whose `isDefault` is `true`.

If the call returns no stores, skip to Step 10 and report the layout as unassigned, saying why.

### 9b.2 — Choose the store

- **Exactly one store** → assign it automatically and state what you did. (Same shape as
  Step 1b's single-account handling — don't ask a question with one possible answer.)
- **More than one store** → ask which store should now use this template. Offer the display
  names, plus a final option: `None — leave unassigned`.

If the user picks `None`, skip to Step 10 and report the layout as unassigned.

### 9b.3 — Find the template that currently holds that mapping

One call: the tool ending in `__journey_list_journey_layouts` with `{ "account": [{ACCOUNT_ID}] }`.

Scan every result's `autoLayout` array for an entry where `client` equals the chosen store's id:

- **`country` is empty** → this is the current default mapping. Record the holding layout's `id`
  and `prettyName`. There should be at most one.
- **`country` is non-empty** → a country-specific override. **Leave it alone**, but warn:

  > Note: `{STORE_NAME}` also has a country-specific auto-template on `{OTHER_TEMPLATE_NAME}`
  > for `{USA, CAN}`. Orders shipping to those countries will keep using that template, not
  > this one. Change it in the portal if that isn't what you want.

  Without this warning you would tell the user the store now uses the new template while some
  of their orders demonstrably would not.

> **⚠️ This is the most expensive call in the skill.** The response includes the **full HTML
> `content` of every layout on the account**. Read only `id`, `prettyName`, and `autoLayout`
> from it, and never echo `content` back into the conversation. On an account with many
> layouts, tell the user this step is token-heavy before you make the call.

### 9b.4 — Write the mappings: new first, then clear the old

**This is the only step that writes anything.** Whether the store reached here via 9b.2's
single-store path or its multi-store path, no write has happened yet — it happens here.

**Order matters.** Clearing the old mapping first leaves a window where the store has no
template at all, which can break outbound emails. Setting the new one first means the worst
case is a brief duplicate between two valid brand templates. **Never leave the store unmapped.**

> **⚠️ `autoLayout` is replaced wholesale on write, not appended to.** Always send the layout's
> existing entries back alongside your change. Writing a bare single-entry list onto a layout
> that serves several stores silently destroys the other stores' mappings. This is the most
> damaging mistake available in this step.

**a. Set the new mapping.** Take the new layout's current `autoLayout` (just created, so
normally `[]`), add your entry, and write the merged list:

```
journey_write_layout → {
  "account": {ACCOUNT_ID},
  "id": {NEW_LAYOUT_ID},
  "data": {
    "autoLayout": [
      ...any entries the new layout already had...,
      { "client": {STORE_ID}, "layout": {NEW_LAYOUT_ID}, "country": [] }
    ]
  }
}
```

The `layout` value inside the entry **must equal the id of the layout you are writing to**.

**b. Clear the stale mapping.** Only if 9b.3 found a holding layout. Send back that layout's
`autoLayout` with **only the chosen store's `country: []` entry removed**, every other entry
preserved verbatim:

```
journey_write_layout → {
  "account": {ACCOUNT_ID},
  "id": {OLD_LAYOUT_ID},
  "data": { "autoLayout": [ ...its other entries, minus the chosen store... ] }
}
```

If 9b.3 found no holding layout, skip 9b.4b entirely — there is nothing to clear.

> **Why 9b.4b is mandatory, not tidy-up:** the API accepts a second mapping for the same store
> at the same `country` without any error or warning. Skip this and the store is mapped to two
> templates at once, with no indication of which one wins.

### 9b.5 — Verify before claiming success

Call the tool ending in `__journey_get_journey_layout` with `{ "id": {NEW_LAYOUT_ID} }` and
confirm `autoLayout` contains your `{STORE_ID}` entry.

- Entry present → proceed to Step 10.
- Entry missing → **report the failure with the readback.** Do not describe the assignment as
  done.

The mapping needs **no** `layout publish` — `autoLayout` is not part of the layout's publish
diff, so it applies as soon as it is written.

### 9b.6 — Failure handling

| Failure | What to do |
|---|---|
| `autoLayout not_a_list` (400) | The value must be a JSON list, not a bool. Fix and retry. |
| The 9b.4a write fails | Report it and make no further writes. The old mapping is untouched, so the store keeps working. |
| The 9b.4b clear fails after 9b.4a landed | Report the duplicate explicitly, naming **both** templates, and tell the user which to clear in the portal. Do not claim success. |
| 9b.5 readback shows no mapping | Report as a failure, including the readback. Not success. |
| `__config_list_clients` returns no stores | Skip assignment, report the layout as unassigned, and say why. |

---

## Step 10 — Report back

On success, tell the user:

- Layout **ID** (e.g. `19584`)
- Layout **prettyName**
- **Account:** {ACCOUNT_ID}
- **Status:** draft
- Next step options: assign to a journey in the ParcelLab portal, or publish.

On failure:
- Validation error (400) → read the error details, fix the field, retry. `autoLayout not_a_list` → ensure `autoLayout` is `[]` not a bool.
- Auth/permission error → the ParcelLab MCP connector needs re-authentication; tell the user to reconnect it in Settings → Connectors.

---

## Useful MCP calls (reference)

- List layouts on the account: tool ending `__journey_list_journey_layouts` → `{ "account": [{ACCOUNT_ID}], "ordering": "-created_at" }`
- Inspect one layout: tool ending `__journey_get_journey_layout` → `{ "id": <layout id> }`
- Update a layout: tool ending `__journey_write_layout` → `{ "account": {ACCOUNT_ID}, "id": <layout id>, "data": { ...changed fields... } }`

---

<!-- Do not rename `parcellab-brand-layout` below: it names the separate
     Cowork/CLI variant in another repo, not this skill. -->

## Differences from `parcellab-brand-layout` (CLI/Playwright version)

| Concern | CLI skill | This built-in-browser skill |
|---|---|---|
| Browser | `mcp__playwright__browser_navigate` / `browser_evaluate` | `mcp__Claude_Browser__navigate` / `javascript_tool` (built-in Browser pane, tab `"main"`) |
| JS return | arrow fn with `return` | IIFE `(() => {...})()` (REPL last-expression) |
| Page screenshot | `browser_take_screenshot` | `mcp__Claude_Browser__computer` `{action:"screenshot"}` |
| Preview | `python3 -m http.server` + Playwright screenshot | `mcp__Claude_Browser__preview_start {name}` server + same Browser pane (live-editable; serves `$HOME/parcellab-previews/`) |
| Push to ParcelLab | `parcellab` CLI (`api request POST`) | ParcelLab MCP connector (`journey_write_layout`) |
| Template | read from sibling `brand-style-guide` skill | bundled `template.html` in this skill's folder |

> **Prior variant:** an earlier version of this skill used the Claude-in-Chrome extension (`mcp__Claude_in_Chrome__*`) plus a separate `mcp__Claude_Preview__*` panel. Both are now replaced by the single built-in Browser pane. Only revert to Claude-in-Chrome if you must scrape a login-gated site.
