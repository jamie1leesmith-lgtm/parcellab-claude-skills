#!/usr/bin/env node
/**
 * fetch_page.mjs
 *
 * Uses a locally installed Playwright + Chromium to load a product detail page
 * as a real browser would, then extracts:
 *   - The page title (product name fallback)
 *   - The largest visible product image URL
 *
 * Usage:
 *   node fetch_page.mjs <url>
 *   node fetch_page.mjs <url> --json   (outputs JSON instead of plain text)
 *
 * Output (JSON):
 *   { "url": "...", "title": "...", "image_url": "..." }
 *
 * Exit codes:
 *   0  success
 *   1  error (message printed to stderr)
 */

import { chromium } from 'playwright';

const url = process.argv[2];
const jsonMode = process.argv.includes('--json');

if (!url) {
  console.error('Usage: node fetch_page.mjs <url> [--json]');
  process.exit(1);
}

/**
 * Score candidate image URLs — higher is better.
 * Penalises tracking pixels, icons, SVGs, lazy-load placeholders, and data URIs.
 */
function scoreImage(src = '', naturalWidth = 0, naturalHeight = 0) {
  if (!src || src.startsWith('data:')) return -1;
  if (/\.(svg|gif)(\?|$)/i.test(src)) return -1;
  if (/placeholder|spacer|blank|pixel|tracking|logo|icon|spinner/i.test(src)) return -1;

  const area = naturalWidth * naturalHeight;
  if (area < 5000) return -1; // too small (e.g. 100×50 or less)

  return area;
}

async function main() {
  const browser = await chromium.launch({
    headless: true,
    args: [
      '--no-sandbox',
      '--disable-blink-features=AutomationControlled', // reduces bot-detection signals
    ],
  });

  const context = await browser.newContext({
    userAgent:
      'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) ' +
      'AppleWebKit/537.36 (KHTML, like Gecko) ' +
      'Chrome/124.0.0.0 Safari/537.36',
    viewport: { width: 1440, height: 900 },
    locale: 'en-GB',
    extraHTTPHeaders: {
      'Accept-Language': 'en-GB,en;q=0.9',
    },
  });

  const page = await context.newPage();

  try {
    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 30000 });

    // Wait a moment for lazy-loaded images to settle
    await page.waitForTimeout(2000);

    const title = await page.title();

    // Evaluate all <img> elements and pick the best candidate
    const imageUrl = await page.evaluate(() => {
      function scoreImage(src = '', naturalWidth = 0, naturalHeight = 0) {
        if (!src || src.startsWith('data:')) return -1;
        if (/\.(svg|gif)(\?|$)/i.test(src)) return -1;
        if (/placeholder|spacer|blank|pixel|tracking|logo|icon|spinner/i.test(src)) return -1;
        const area = naturalWidth * naturalHeight;
        if (area < 5000) return -1;
        return area;
      }

      const imgs = Array.from(document.querySelectorAll('img'));
      let best = { score: -1, src: '' };

      for (const img of imgs) {
        const src = img.currentSrc || img.src || '';
        const score = scoreImage(src, img.naturalWidth, img.naturalHeight);
        if (score > best.score) {
          best = { score, src };
        }
      }

      return best.src || '';
    });

    const result = { url, title, image_url: imageUrl };

    if (jsonMode) {
      console.log(JSON.stringify(result, null, 2));
    } else {
      console.log(`Title:     ${title}`);
      console.log(`Image URL: ${imageUrl}`);
    }
  } finally {
    await browser.close();
  }
}

main().catch((err) => {
  console.error(err instanceof Error ? err.message : String(err));
  process.exit(1);
});
