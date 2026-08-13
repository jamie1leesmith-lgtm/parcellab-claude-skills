"""Auto-mode resolution: country/category inference and answers-doc merge.

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

_CURRENCY_COUNTRY = {
    "€": "DE",
    "£": "UK",
}


def infer_country(prospect_url, product_pool):
    """Infer the destination country from the site's TLD, else scraped prices.

    TLD wins outright — a .de site pricing test data in USD is still a DE
    site. Falls back to a currency symbol found in any scraped price, then
    to DEFAULT_COUNTRY when neither gives a signal.
    """
    host = (urlparse(prospect_url).netloc or prospect_url).lower()
    labels = host.split(".")
    for label in reversed(labels):
        if label in _TLD_COUNTRY:
            return _TLD_COUNTRY[label]

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
    winners = sorted(c for c, n in counts.items() if n == best)
    return winners[0]


# Every field auto-mode can resolve without asking, and its non-doc default.
# Q1 (returns_in_scope) and Q2 (shopify_opp) are deliberately absent: the
# spec requires those always be asked live, in both modes, never defaulted
# or doc-supplied.
_STATIC_DEFAULTS = {
    "run.pace": "standard",
    "gates.order_lifecycle.gate_c": "send-as-is",
    "edit_mode_fix": True,
}

_NEVER_ASK_FIELDS = frozenset({"returns_in_scope", "shopify_opp"})


def resolve_auto_fields(prospect_url, product_pool, answers_doc=None):
    """Merge inferred/default values with an optional answers doc.

    Precedence per field: answers_doc value, if present and known, else the
    inferred or static default. Unknown doc keys are never applied — they
    are collected in "_ignored_doc_keys" so the caller can report them
    (Beat 1), rather than silently dropped or treated as an error.
    """
    doc = {k: v for k, v in (answers_doc or {}).items() if k not in _NEVER_ASK_FIELDS}

    country = infer_country(prospect_url, product_pool)
    category = infer_category(product_pool)

    fields = {
        "destination_country": {"value": country, "source": "inferred"},
        "cdc.region": {"value": country, "source": "inferred"},
        "cdc.category": {"value": category, "source": "inferred"},
    }
    for key, value in _STATIC_DEFAULTS.items():
        fields[key] = {"value": value, "source": "default"}

    ignored = []
    for key, value in doc.items():
        if key in fields:
            fields[key] = {"value": value, "source": "doc"}
        else:
            ignored.append(key)

    fields["_ignored_doc_keys"] = sorted(ignored)
    return fields


def main():
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--prospect-url", required=True)
    ap.add_argument("--product-pool-file", required=True,
                     help="path to scrape/product-pool.json")
    ap.add_argument("--answers-doc-file", default=None,
                     help="optional path to an auto-mode answers doc")
    args = ap.parse_args()

    try:
        pool = json.loads(Path(args.product_pool_file).read_text())
        answers = None
        if args.answers_doc_file:
            answers = json.loads(Path(args.answers_doc_file).read_text())
        print(json.dumps(resolve_auto_fields(args.prospect_url, pool, answers), indent=2))
    except (ValueError, OSError) as exc:
        print(f"resolve_auto_defaults: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
