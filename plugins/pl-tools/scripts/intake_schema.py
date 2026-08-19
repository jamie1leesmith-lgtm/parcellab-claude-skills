"""What a valid demo-environment intake answer set is.

Pure functions only — no I/O, no HTTP — so the server, the tests and any
future CLI all agree on one definition. Every vocabulary here is pinned to
what `validate_manifest.py` already accepts: widening one of these sets
without widening the validator produces a manifest that fails at Phase 1,
after the operator has already answered everything.
"""
import json
import re

# validate_manifest.BRAND_REGIONS is exactly these three, and
# resolve_auto_defaults.infer_country only ever returns one of them.
REGIONS = ("US", "UK", "DE")

# Couriers from create-order's "Defaults & dummy data" table, which is the
# only place in this repo that documents a real courier code per country.
REGION_COURIERS = {"US": "usps", "UK": "royal-mail", "DE": "dhl-germany"}

FRAUD_LEVELS = frozenset({"low", "medium", "high"})

# FRAUD_LEVELS answers "is this a valid fraud level?" — membership only, so
# a frozenset is the right shape and its iteration order carries no meaning.
# FRAUD_LEVELS_ORDERED answers a different question, "in what order do we
# show these to a human?" — fraud severity has an inherent low-to-high
# order, and `sorted(FRAUD_LEVELS)` alphabetises it into "high, low, medium",
# which reads as meaningless (or worse, backwards) to someone picking a risk
# level. Keep both in sync (see test_fraud_levels_ordered_matches_the_set) —
# a level added to one and not the other silently disappears from either
# validation or the UI.
FRAUD_LEVELS_ORDERED = ("low", "medium", "high")

# `split` is deliberately absent: a split is a per-order boolean that forks
# the order into two parcels, each with its own scenario from this set.
SCENARIOS = frozenset({
    "happy", "stuck-delay", "recovered", "locker",
    "manual_return", "return_tracking", "custom",
})

MODES = frozenset({"babysit", "auto"})
GATE_C_VALUES = frozenset({"send-as-is", "extras"})
WEIGHT_UNITS = frozenset({"kg", "g", "lbs", "oz"})

PROMISE_DATE_FIELDS = ("announced_delivery_date",
                       "announced_delivery_date_min",
                       "announced_delivery_date_max")

# The Gate C menu order-lifecycle documents. Every key here except
# `extra_articles` and `article_weights` IS the literal Order API field
# name that gets written onto the payload (see demo-environment/SKILL.md:675)
# — validate_manifest.py does not check these names, so a wrong one is
# silently dropped by the API and still returns HTTP 201. `extra_articles`
# and `article_weights` are synthetic containers, not literal API fields.
EXTRA_KEYS = frozenset(set(PROMISE_DATE_FIELDS) | {
    "additional_recipients", "order_tax_amount", "order_net_amount",
    "order_discount_amount",
    "extra_articles", "tags", "additional_attributes",
    "delivery_method", "courier_service_level", "requires_signature",
    "article_weights",
})

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

MAX_ORDERS = 5


def default_answers(region="US"):
    """The form's pre-fill: three orders, fraud varied, #2 split.

    Mirrors intake-script.md's documented default matrix, trimmed to three
    rows because the two return-flow rows depend on the retain path being
    chosen, which this form asks about in the same submission.
    """
    if region not in REGIONS:
        region = "US"
    return {
        "shopify_opp": False,
        "reuse_pool": None,
        "region": region,
        "courier": REGION_COURIERS[region],
        "orders": [
            {"label": "#1", "fraud": "low", "split": False,
             "scenario": "happy", "courier": None},
            {"label": "#2", "fraud": "medium", "split": True,
             "parcels": [
                 {"label": "A", "scenario": "happy", "courier": None},
                 {"label": "B", "scenario": "stuck-delay", "courier": None},
             ]},
            {"label": "#3", "fraud": "high", "split": False,
             "scenario": "recovered", "courier": None},
        ],
        "gate_c": "send-as-is",
        "extras": {},
        "mode": "babysit",
    }


def _check_parcel(parcel, where):
    if not isinstance(parcel, dict):
        raise ValueError(f"{where}: parcel must be an object")
    if not parcel.get("label"):
        raise ValueError(f"{where}: parcel is missing a label")
    if parcel.get("scenario") not in SCENARIOS:
        raise ValueError(
            f"{where}: parcel {parcel['label']} has an invalid scenario "
            f"{parcel.get('scenario')!r}; expected one of {sorted(SCENARIOS)}")
    courier = parcel.get("courier")
    if courier is not None and not isinstance(courier, str):
        raise ValueError(f"{where}: parcel courier must be a string or null")


def _check_order(order, where):
    if not isinstance(order, dict):
        raise ValueError(f"{where}: order must be an object")
    if not order.get("label"):
        raise ValueError(f"{where}: order is missing a label")
    if order.get("fraud") not in FRAUD_LEVELS:
        raise ValueError(
            f"{where}: invalid fraud level {order.get('fraud')!r}; "
            f"expected one of {sorted(FRAUD_LEVELS)}")
    if not isinstance(order.get("split"), bool):
        raise ValueError(f"{where}: split must be true or false")

    if order["split"]:
        parcels = order.get("parcels")
        if not isinstance(parcels, list) or len(parcels) != 2:
            raise ValueError(
                f"{where}: a split order needs exactly two parcels")
        for parcel in parcels:
            _check_parcel(parcel, where)
    else:
        if order.get("scenario") not in SCENARIOS:
            raise ValueError(
                f"{where}: invalid scenario {order.get('scenario')!r}; "
                f"expected one of {sorted(SCENARIOS)}")
        courier = order.get("courier")
        if courier is not None and not isinstance(courier, str):
            raise ValueError(f"{where}: courier must be a string or null")


def _check_extras(extras, gate_c):
    if not isinstance(extras, dict):
        raise ValueError("extras must be an object")

    if gate_c == "send-as-is" and extras:
        raise ValueError("gate_c is 'send-as-is' but extras carries fields")
    if gate_c == "extras" and not extras:
        raise ValueError("gate_c is 'extras' but extras is empty")

    unknown = sorted(set(extras) - EXTRA_KEYS)
    if unknown:
        raise ValueError(f"unknown extras key(s): {unknown}")

    for field in PROMISE_DATE_FIELDS:
        value = extras.get(field)
        if value is not None and not _DATE_RE.match(str(value)):
            raise ValueError(
                f"extras.{field} must be YYYY-MM-DD, not a full ISO "
                f"datetime (got {value!r})")

    weights = extras.get("article_weights") or {}
    if not isinstance(weights, dict):
        raise ValueError("extras.article_weights must be an object keyed by "
                         "product id")
    for pid, entry in weights.items():
        if not isinstance(entry, dict):
            raise ValueError(
                f"extras.article_weights[{pid}] must be an object")
        weight = entry.get("weight")
        if not isinstance(weight, (int, float)) or isinstance(weight, bool) \
                or weight <= 0:
            raise ValueError(
                f"extras.article_weights[{pid}].weight must be a positive "
                f"number (got {weight!r})")
        if entry.get("weight_unit") not in WEIGHT_UNITS:
            raise ValueError(
                f"extras.article_weights[{pid}].weight_unit must be one of "
                f"{sorted(WEIGHT_UNITS)} (got {entry.get('weight_unit')!r})")


def parse_answers(raw_json):
    """Validate and normalise a submitted answer set.

    Raises ValueError with one specific reason. The server turns that reason
    into a 400 the page shows inline, so the operator fixes it on the same
    form rather than falling through to a chat interview.
    """
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise ValueError(f"not valid JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError("answers must be a JSON object")

    required = {"shopify_opp", "reuse_pool", "region", "courier",
                "orders", "gate_c", "extras", "mode"}
    missing = sorted(required - set(data))
    if missing:
        raise ValueError(f"missing field(s): {missing}")

    if not isinstance(data["shopify_opp"], bool):
        raise ValueError("shopify_opp must be true or false")

    if data["reuse_pool"] is not None \
            and not isinstance(data["reuse_pool"], bool):
        raise ValueError("reuse_pool must be true, false, or null")

    if data["region"] not in REGIONS:
        raise ValueError(
            f"region must be one of {list(REGIONS)} (got {data['region']!r}) "
            f"— validate_manifest.py accepts no others")

    if not data["courier"] or not isinstance(data["courier"], str):
        raise ValueError("courier must be a non-empty string")

    if data["mode"] not in MODES:
        raise ValueError(
            f"mode must be one of {sorted(MODES)} (got {data['mode']!r})")

    if data["gate_c"] not in GATE_C_VALUES:
        raise ValueError(
            f"gate_c must be one of {sorted(GATE_C_VALUES)} "
            f"(got {data['gate_c']!r})")

    orders = data["orders"]
    if not isinstance(orders, list) or not 1 <= len(orders) <= MAX_ORDERS:
        raise ValueError(
            f"orders must contain between 1 and {MAX_ORDERS} entries")

    seen = set()
    for index, order in enumerate(orders):
        where = f"order {index + 1}"
        _check_order(order, where)
        if order["label"] in seen:
            raise ValueError(f"{where}: duplicate order label "
                             f"{order['label']!r}")
        seen.add(order["label"])

    # Same rule validate_manifest.py enforces on the manifest, checked here
    # so the operator hears it on the form instead of at Phase 1.
    if len(orders) >= 2 and not any(o["split"] for o in orders):
        raise ValueError("runs of 2+ orders need at least one split order")

    _check_extras(data["extras"], data["gate_c"])

    return {
        "shopify_opp": data["shopify_opp"],
        "reuse_pool": data["reuse_pool"],
        "region": data["region"],
        "courier": data["courier"],
        "orders": orders,
        "gate_c": data["gate_c"],
        "extras": data["extras"],
        "mode": data["mode"],
    }
