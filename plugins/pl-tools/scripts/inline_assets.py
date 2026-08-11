#!/usr/bin/env python3
"""Inline run images as data: URIs for the artifact page.

The artifact CSP blocks external requests, so a remote <img src> renders as a
broken-image icon — which reads as a failed run rather than a styling choice.
Fetch once here; the renderer only ever sees data: URIs.
"""
import base64
import json
import pathlib
import sys
import urllib.request

MAX_ASSET_BYTES = 1_500_000


def to_data_uri(raw, content_type):
    return f"data:{content_type};base64," + base64.b64encode(raw).decode()


def should_skip(size):
    return size > MAX_ASSET_BYTES


def http_fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "pl-tools"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read(), resp.headers.get_content_type()


def _one(url, label, skipped, fetch):
    """Fetch one asset. A failure is recorded and skipped, never raised — a
    missing product shot must not take down a run."""
    try:
        raw, content_type = fetch(url)
    except Exception as exc:                      # network/DNS/timeout/HTTP
        skipped.append({"asset": label, "reason": f"fetch failed: {exc}"})
        return None
    if should_skip(len(raw)):
        skipped.append({"asset": label,
                        "reason": f"{len(raw)} bytes over {MAX_ASSET_BYTES}"})
        return None
    return to_data_uri(raw, content_type)


def build_assets(pool, tokens, fetch=http_fetch):
    skipped = []
    products = {}
    for product in pool:
        products[product["sku"]] = {
            "name": product.get("name"),
            "price": product.get("price"),
            "product_type": product.get("product_type"),
            "pdp_url": product.get("pdp_url"),
            "image_url": product.get("image_url"),
            "data_uri": _one(product["image_url"], product["sku"], skipped,
                             fetch),
        }

    hero_src = (tokens.get("hero") or {}).get("url")
    hero = {"alt": (tokens.get("hero") or {}).get("alt", ""),
            "data_uri": _one(hero_src, "hero", skipped, fetch)
            if hero_src else None}

    logo = tokens.get("logo") or {}
    logo_svg = logo.get("markup") if logo.get("type") == "inline_svg" else None

    return {"products": products, "hero": hero, "logo_svg": logo_svg,
            "tokens": tokens.get("tokens", {}), "skipped": skipped}


def main():
    if len(sys.argv) != 2:
        print("usage: inline_assets.py <run_dir>")
        return 1
    scrape = pathlib.Path(sys.argv[1]) / "scrape"
    pool = json.loads((scrape / "product-pool.json").read_text())
    pool = pool if isinstance(pool, list) else pool["products"]
    tokens = json.loads((scrape / "brand-tokens.json").read_text())

    assets = build_assets(pool, tokens)
    (scrape / "assets.json").write_text(json.dumps(assets, indent=2))
    print(f"inlined {len(assets['products'])} products, "
          f"{len(assets['skipped'])} skipped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
