"""Auto-mode resolution: country/category inference for demo-environment.

Pure functions only — no network, no filesystem — so the demo-environment
skill's Phase 0 can call these against data it has already scraped, and so
they stay unit-testable without a live run.
"""

import json
import sys
from pathlib import Path
from urllib.parse import urlparse

DEFAULT_COUNTRY = "US"
DEFAULT_CATEGORY = "Fashion"

_TLD_COUNTRY = {
    "de": "DE",
    "uk": "UK",
}

_PATH_LOCALE_COUNTRY = {
    "gb": "UK",
    "uk": "UK",
    "de": "DE",
    "us": "US",
}

_CURRENCY_COUNTRY = {
    "€": "DE",
    "£": "UK",
}


def infer_country(prospect_url, product_pool):
    """Infer the destination country from the site's TLD, else its URL path
    locale segment, else scraped prices.

    TLD wins outright — a .de site pricing test data in USD is still a DE
    site. Falls next to a locale segment in the path (many sites use a
    ccTLD-less domain with a /gb/en/ or /de/de/-style country code instead,
    live-verified 2026-08-13 against eu.patagonia.com/gb/en/home), then a
    currency symbol found in any scraped price, then to DEFAULT_COUNTRY when
    none of the three gives a signal.
    """
    parsed = urlparse(prospect_url)
    host = (parsed.netloc or prospect_url).lower()
    labels = host.split(".")
    for label in reversed(labels):
        if label in _TLD_COUNTRY:
            return _TLD_COUNTRY[label]

    path_segments = [s for s in parsed.path.lower().split("/") if s]
    for segment in path_segments:
        if segment in _PATH_LOCALE_COUNTRY:
            return _PATH_LOCALE_COUNTRY[segment]

    for product in product_pool or []:
        price = str(product.get("price") or "")
        for symbol, country in _CURRENCY_COUNTRY.items():
            if symbol in price:
                return country

    return DEFAULT_COUNTRY


_CATEGORY_KEYWORDS = {
    "Electronics": ("phone", "laptop", "tablet", "electronic", "device", "audio"),
    "Home": ("home", "kitchen", "decor", "furnish"),
}


def _match_category(product_type):
    text = product_type.lower()
    for category, keywords in _CATEGORY_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            return category
    # Unmatched products default to Fashion
    return DEFAULT_CATEGORY


def infer_category(product_pool):
    """Best match between scraped product_types and the CDC's category menu.

    Counts matches per category across the whole pool and returns whichever
    has the most; ties and no-match both fall back to DEFAULT_CATEGORY,
    since Fashion is the safe default for an unclassifiable or empty pool.
    """
    counts = {}
    for product in product_pool or []:
        category = _match_category(str(product.get("product_type") or ""))
        counts[category] = counts.get(category, 0) + 1

    if not counts:
        return DEFAULT_CATEGORY

    best = max(counts.values())
    winners = [c for c, n in counts.items() if n == best]
    if len(winners) == 1:
        return winners[0]
    return DEFAULT_CATEGORY


# Every field auto-mode can resolve without asking, and its non-doc default.
# Q1 (shopify_opp) is deliberately absent: the spec requires it always be
# asked live, in both modes, via the intake questionnaire. Returns are
# always in scope now (the old Q1/"engage" path was retired), so there is
# no separate returns-in-scope field for this function to guard at all.
_STATIC_DEFAULTS = {
    "run.pace": "standard",
    "gates.order_lifecycle.gate_c": "send-as-is",
    "edit_mode_fix": True,
}


def resolve_auto_fields(prospect_url, product_pool):
    """Values every run resolves without asking, once the scrape's product
    pool exists — category joins country/region/pace here now that it is
    never a live question either, in any mode.
    """
    country = infer_country(prospect_url, product_pool)
    category = infer_category(product_pool)

    fields = {
        "destination_country": {"value": country, "source": "inferred"},
        "brand.region": {"value": country, "source": "inferred"},
        "brand.category": {"value": category, "source": "inferred"},
    }
    for key, value in _STATIC_DEFAULTS.items():
        fields[key] = {"value": value, "source": "default"}

    return fields


def main():
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--prospect-url", required=True)
    ap.add_argument("--product-pool-file", required=True,
                     help="path to scrape/product-pool.json")
    args = ap.parse_args()

    try:
        pool = json.loads(Path(args.product_pool_file).read_text())
        # scrape/product-pool.json may be a bare list or {"products": [...]}
        # — inline_assets.py already accepts both shapes; match that here.
        pool = pool if isinstance(pool, list) else pool["products"]
        print(json.dumps(resolve_auto_fields(args.prospect_url, pool), indent=2))
    except (ValueError, OSError) as exc:
        print(f"resolve_auto_defaults: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
