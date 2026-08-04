#!/usr/bin/env python3
"""Shape scraped prospect products into a mix that supports every exchange demo.

Four demos have to work afterwards:

  * even inside one product   -- swap S for M          -> needs >=2 variants per product
  * even across products      -- swap item, pay nothing -> needs 2 products at one price
  * uneven upward             -- customer PAYS          -> needs a product above that pair
  * uneven downward           -- customer is refunded   -> a product below the pair, if any

The upward case is the one with a direction requirement: exchanging into something more
expensive is what exercises taking payment, so the pair is deliberately chosen from the
three cheapest products, leaving the dearest above it.

Reads a JSON payload on stdin, writes the shaped payload to stdout.
"""

import json
import re
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

TWO_PLACES = Decimal("0.01")
DEFAULT_AXIS = ("S", "M", "L")
DEFAULT_STOCK = 25
MAX_VALUES_PER_AXIS = 3
MAX_AXES = 3
NUDGE = Decimal("10.00")
SEED_TAG = "pl-demo-seed"
PRODUCT_COUNT = 4


def normalise_price(value):
    """Return value as a 2dp Decimal, tolerating currency symbols and separators."""
    text = str(value).strip()
    if not text:
        raise ValueError("empty price")

    text = re.sub(r"[^\d.,]", "", text)
    if not text:
        raise ValueError(f"no digits in price: {value!r}")

    # "64,50" is a decimal comma; "1,299.00" is a thousands comma.
    if "," in text and "." in text:
        text = text.replace(",", "")
    elif "," in text:
        tail = text.split(",")[-1]
        text = text.replace(",", ".") if len(tail) == 2 else text.replace(",", "")

    try:
        return Decimal(text).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
    except InvalidOperation as exc:
        raise ValueError(f"unparseable price: {value!r}") from exc


def shape_prices(prices):
    """Guarantee a matched pair with a dearer product above it.

    Returns (new_prices, adjusted_indices, roles). Only the two adjacent pairs among the
    three cheapest products are eligible, which is what keeps the dearest free to sit
    above the pair and drive the upward (take payment) demo.
    """
    if len(prices) != PRODUCT_COUNT:
        raise ValueError(f"need exactly {PRODUCT_COUNT} products, got {len(prices)}")

    prices = list(prices)
    adjusted = []
    order = sorted(range(PRODUCT_COUNT), key=lambda i: prices[i])

    candidates = [(order[0], order[1]), (order[1], order[2])]
    # min() keeps the first on a tie, which is the cheaper pair.
    low, high = min(candidates, key=lambda pair: abs(prices[pair[0]] - prices[pair[1]]))

    if prices[high] != prices[low]:
        prices[high] = prices[low]
        adjusted.append(high)
    pair_price = prices[low]

    dearest = order[3]
    if prices[dearest] <= pair_price:
        prices[dearest] = pair_price + NUDGE
        adjusted.append(dearest)

    spare = next(i for i in order[:3] if i not in (low, high))
    roles = {
        "pair": [low, high],
        "higher": dearest,
        "lower": spare if prices[spare] < pair_price else None,
    }
    return prices, sorted(adjusted), roles


def resolve_options(product, default_axis=DEFAULT_AXIS):
    """Return the variant axes to build, always with at least one usable axis.

    A single-value axis cannot demo a swap, so it is dropped. If nothing usable survives,
    fall back to a Size axis — colour values are never invented. Axes are capped at
    MAX_AXES (Shopify's own hard limit is 3 options per product), keeping the first three
    in order — exceeding it is not a soft truncation, the push mutation is refused outright.
    """
    axes = []
    for option in product.get("options") or []:
        name = str(option.get("name") or "").strip()
        values = []
        for raw in option.get("values") or []:
            value = str(raw).strip()
            if value and value not in values:
                values.append(value)
        if name and len(values) >= 2:
            axes.append({"name": name, "values": values[:MAX_VALUES_PER_AXIS]})

    axes = axes[:MAX_AXES]

    if not axes:
        axes = [{"name": "Size", "values": list(default_axis)}]
    return axes


def build_variants(options, price, quantity, location_id):
    """Cartesian product of the axes, one variant per combination."""
    combos = [[]]
    for option in options:
        combos = [combo + [(option["name"], value)]
                  for combo in combos for value in option["values"]]

    return [
        {
            "option_values": [{"option_name": name, "name": value} for name, value in combo],
            "price": f"{price}",
            "quantity": quantity,
            "location_id": location_id,
        }
        for combo in combos
    ]


def build_mix(payload):
    products = payload["products"]
    if len(products) != PRODUCT_COUNT:
        raise ValueError(f"need exactly {PRODUCT_COUNT} products, got {len(products)}")

    handle = payload.get("prospect_handle") or "prospect"
    location_id = payload.get("location_id")
    if location_id is None or not str(location_id).strip():
        raise ValueError(
            "location_id is required — resolve it from the store's locations query"
        )
    # Distinguish "absent" from an explicit 0 -- `or` would silently turn a zero,
    # which breaks every exchange target, into the default.
    raw_stock = payload.get("stock_per_variant")
    stock = DEFAULT_STOCK if raw_stock is None else int(raw_stock)
    if stock <= 0:
        raise ValueError("stock_per_variant must be greater than zero")

    originals = [normalise_price(p["price"]) for p in products]
    shaped, adjusted_indices, roles = shape_prices(originals)

    shaped_products = []
    adjustments = []
    for index, product in enumerate(products):
        options = resolve_options(product)
        was_adjusted = index in adjusted_indices
        shaped_products.append({
            "name": product["name"],
            "product_type": str(product.get("product_type") or "").strip(),
            "original_price": f"{originals[index]}",
            "price": f"{shaped[index]}",
            "adjusted": was_adjusted,
            "image_url": product.get("image_url"),
            "pdp_url": product.get("pdp_url"),
            "options": options,
            "variants": build_variants(options, shaped[index], stock, location_id),
            # Each product gets its own list — sharing one object across all four would
            # let an in-place tag mutation on one product leak into the others.
            "tags": [SEED_TAG, f"pl-prospect-{handle}"],
        })
        shaped_products[-1]["variant_count"] = len(shaped_products[-1]["variants"])

        if was_adjusted:
            adjustments.append({
                "name": product["name"],
                "from": f"{originals[index]}",
                "to": f"{shaped[index]}",
            })

    warnings = []
    types = [p["product_type"] for p in shaped_products if p["product_type"]]
    repeated = sorted({t for t in types if types.count(t) > 1})
    if repeated:
        warnings.append(
            "repeated product types, so the cross-product exchange looks like a "
            f"like-for-like swap: {', '.join(repeated)}"
        )

    pair_i, pair_j = roles["pair"]
    dearest, spare = roles["higher"], roles["lower"]
    pair_price = shaped[pair_i]

    # Demo the size swap on whichever product has the most variants.
    showcase = max(shaped_products, key=lambda p: p["variant_count"])
    axis = showcase["options"][0]

    demos = {
        "in_product_even": {
            "product": showcase["name"],
            "option": axis["name"],
            "swap": f"{axis['values'][0]} → {axis['values'][1]}",
        },
        "cross_product_even": [products[pair_i]["name"], products[pair_j]["name"]],
        "uneven_upward": {
            "from": products[pair_i]["name"],
            "to": products[dearest]["name"],
            "balance": f"{shaped[dearest] - pair_price}",
        },
        "uneven_downward": None if spare is None else {
            "from": products[pair_i]["name"],
            "to": products[spare]["name"],
            "refund": f"{pair_price - shaped[spare]}",
        },
    }

    return {
        "products": shaped_products,
        "adjustments": adjustments,
        "warnings": warnings,
        "demos": demos,
        "location_id": location_id,
    }


def main():
    try:
        print(json.dumps(build_mix(json.load(sys.stdin)), indent=2))
    except (ValueError, KeyError) as exc:
        print(f"shape_product_mix: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
