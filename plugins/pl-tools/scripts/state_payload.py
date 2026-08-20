"""Assemble the GET /state payload the run page renders itself from.

Everything here is derived from files the run already writes — run-state.json
is the source of truth for progress, and the per-lane drill-down detail comes
from the same side files the old run-page renderer read. Nothing writes.

Every file is read defensively — run-state.json included: a half-written or
missing file leaves its detail section None (or, for run-state.json, every
field at its own fallback) rather than failing the whole poll, because the
page polling every two seconds will inevitably catch a write mid-flight.
"""
import json
import pathlib

import run_state


def _read_json(path):
    """None on anything unreadable — a poll must never fail on a side file."""
    try:
        return json.loads(pathlib.Path(path).read_text())
    except (OSError, ValueError):
        return None


def load_state(run_dir):
    """The run state, or an empty dict if it cannot be read.

    `run-state.json` is written by `run_state.init()` before the server
    starts, so a missing file means something unexpected — but a poll is the
    wrong place to find out. Raising here escapes the request handler and the
    page loses its only data source; degrading returns a usable payload with
    every field falling back to its own default, exactly as the side files
    already do.
    """
    try:
        return run_state.load(str(run_dir))
    except (OSError, ValueError):
        return {}


_load_state = load_state          # existing internal callers


def _scrape_detail(run_dir):
    assets = _read_json(run_dir / "scrape" / "assets.json")
    if not assets:
        return None
    tokens = assets.get("tokens") or {}
    swatches = [v for v in tokens.values()
                if isinstance(v, str) and v.startswith("#")]
    products = [
        {
            "sku": sku,
            "name": entry.get("name") or "",
            "product_type": entry.get("product_type") or "",
            "price": entry.get("price") or "",
            "image": entry.get("data_uri"),
        }
        for sku, entry in (assets.get("products") or {}).items()
    ]
    return {
        "swatches": swatches,
        "font": tokens.get("font"),
        "logo": assets.get("logo_data_uri"),
        "logo_svg": assets.get("logo_svg"),
        "products": products,
    }


def _template_detail(state, manifest):
    lane = (state.get("lanes") or {}).get("template") or {}
    if not lane:
        return None
    detail = {
        "status": lane.get("status"),
        "at": lane.get("at"),
        "path": state.get("path"),
    }
    for key in ("layout_id", "store"):
        if key in lane:
            detail[key] = lane[key]
    brand = (manifest or {}).get("brand") or {}
    if brand.get("name"):
        detail["brand"] = brand["name"]
    return detail


def _seed_detail(run_dir):
    result = _read_json(run_dir / "results" / "shopify-seed.json")
    if not result:
        return None
    products = [
        {
            "title": p.get("title") or "",
            "seeded_price": p.get("seeded_price"),
            "adjusted": bool(p.get("adjusted")),
            "variant_count": len(p.get("variants") or []),
            "admin_url": p.get("admin_url"),
        }
        for p in (result.get("products") or [])
    ]
    return {
        "status": result.get("status"),
        "products": products,
        "demos": result.get("demos") or {},
        "warnings": result.get("warnings") or [],
        "error": result.get("error"),
    }


def _cdc_detail(run_dir, state, manifest):
    lane = (state.get("lanes") or {}).get("cdc") or {}
    cdc = (manifest or {}).get("cdc") or {}
    result = _read_json(run_dir / "results" / "demo-request.json")
    return {
        "status": lane.get("status") or "pending",
        "at": lane.get("at"),
        # Surfaced deliberately: a run that silently flipped this to true is
        # what produced the synthetic-order incident this UI now shows plainly.
        "generate_orders": bool(cdc.get("generate_orders")),
        "synthetic_orders": len(cdc.get("orders") or []),
        # results/demo-request.json's documented shape (SKILL.md:300-302) is
        # {"id", "request_status", "request_url", "linked_submitted"} — there
        # is no "url" or "error" key. A failed request (HTTP 500) still gets
        # written with request_status "failed" rather than an error field.
        "id": (result or {}).get("id"),
        "url": (result or {}).get("request_url"),
        "request_status": (result or {}).get("request_status"),
        "linked_count": len((result or {}).get("linked_submitted") or []),
    }


def _orders_with_fraud_level(state, manifest):
    """Merge each order's authoritative `fraud_level` in from the manifest.

    `validate_manifest.py` requires `fraud_level` on every manifest order but
    nothing about the run-state label's format, so a page that instead
    guessed the level from the label (e.g. a `NN-fraud-LEVEL` convention)
    would silently show no fraud pill the moment a real run used a
    differently-shaped label. The manifest is the source of truth; this
    just carries it across to the orders the page renders.

    Matched by `label` first — the field both sides actually share — falling
    back to `order_number` only in case a future manifest shape adds that
    key too. An order with no match at all degrades to `fraud_level: None`
    rather than raising, same as every other side-file lookup here.
    """
    manifest_orders = (manifest or {}).get("orders") or []
    by_label = {mo.get("label"): mo for mo in manifest_orders if mo.get("label")}
    by_order_number = {mo.get("order_number"): mo
                       for mo in manifest_orders if mo.get("order_number")}

    result = []
    for order in state.get("orders") or []:
        match = by_label.get(order.get("label"))
        if match is None:
            match = by_order_number.get(order.get("order_number"))
        result.append(dict(order, fraud_level=(match or {}).get("fraud_level")))
    return result


GATE_NAMES = ("template", "plan")


def gate_states(state):
    """Which gates are waiting on the operator, derived from the timeline.

    Derived rather than stored so the `mark(gate, ..., "asked")` calls the
    conductor already makes ARE the trigger — there is no second field to
    forget to set. That failure mode is not hypothetical: SKILL.md documented
    `mark` while the run page's lane pills read `set_lane`, so every real run
    left its pills on "pending" while the tests stayed green.

    Last mark wins, which makes re-asking a rejected gate free: mark `asked`
    again and the gate is open again, no state to reset.
    """
    latest = {}
    for entry in (state.get("timeline") or []):
        if entry.get("kind") != "gate":
            continue
        name = entry.get("name")
        if name in GATE_NAMES and entry.get("phase") in ("asked", "answered"):
            latest[name] = entry["phase"]
    return {name: {"asked": "open", "answered": "answered"}.get(
                latest.get(name), "pending")
            for name in GATE_NAMES}


def gate_marks(state):
    """The `at` timestamp of each gate's latest 'asked' mark.

    Kept separate from `gate_states` so the 409 check in `run_server.py`
    (`states.get(gate) != "open"`) and the payload's `gates` key keep
    reading exactly the status strings they always have — nothing about
    that shape changes here.

    This exists for the page's re-render guard: a rejected gate is re-asked
    under the SAME name (`gate_states` already makes that free — "last mark
    wins"), so a guard keyed only on the name can't tell a fresh ask from a
    repeat poll of one it already rendered. Handing over the latest ask's
    timestamp gives the page a second key to check.
    """
    latest = {}
    for entry in (state.get("timeline") or []):
        if entry.get("kind") == "gate" and entry.get("phase") == "asked":
            name = entry.get("name")
            if name in GATE_NAMES:
                latest[name] = entry.get("at")
    return latest


def _plan_detail(manifest, gates):
    """The plan card's contents, or None until the plan gate opens.

    Gated on the gate rather than on the manifest existing: the manifest is
    written at Phase 0 step 7, BEFORE the template gate, so keying on the
    file would show the whole plan while the operator is still being asked
    about the template. SKILL.md's rule is that ordering comes from the
    timeline, not from which files happen to exist.
    """
    if gates.get("plan") != "open" or not manifest:
        return None

    products = {p.get("id"): p for p in (manifest.get("products") or [])}

    def named(pid):
        return (products.get(pid) or {}).get("name") or pid

    selection = manifest.get("selection") or {}
    core4 = [{"id": pid,
              "name": named(pid),
              "product_type": (products.get(pid) or {}).get("product_type"),
              "price": (products.get(pid) or {}).get("price")}
             for pid in (selection.get("core4") or [])]

    orders = [{
        "label": o.get("label"),
        "customer": o.get("customer") or {},
        "fraud_level": o.get("fraud_level"),
        "cdc_slot": o.get("cdc_slot"),
        "products": [named(p) for p in (o.get("products") or [])],
        "shipments": [{"label": s.get("label"),
                       "scenario": s.get("scenario"),
                       "courier": s.get("courier"),
                       "events": s.get("events") or [],
                       # validate_manifest.py's confidence labelling
                       # (unproven_events/unproven_chain) — carried through
                       # so the plan card can mark them, not just the
                       # events themselves.
                       "unproven_events": s.get("unproven_events") or [],
                       "unproven_chain": bool(s.get("unproven_chain"))}
                      for s in (o.get("shipments") or [])],
    } for o in (manifest.get("orders") or [])]

    brand = manifest.get("brand") or {}
    cdc = manifest.get("cdc") or {}
    gate_block = ((manifest.get("gates") or {}).get("order_lifecycle") or {})
    extras = gate_block.get("extras") or {}

    fields = []
    for key, value in sorted(extras.items()):
        if key == "article_weights":
            # Listed per article, never summarised: the operator has to see
            # each auto-derived weight to be able to reject it.
            for pid, entry in sorted((value or {}).items()):
                entry = entry or {}
                fields.append((f"{named(pid)} weight",
                               f"{entry.get('weight')} "
                               f"{entry.get('weight_unit')}"))
        else:
            fields.append((key, value))

    return {
        "core4": core4,
        "orders": orders,
        "cdc": {"region": brand.get("region"),
                "category": brand.get("category"),
                "config_source": cdc.get("config_source"),
                "generate_orders": bool(cdc.get("generate_orders"))},
        "extras": {"gate_c": gate_block.get("gate_c"), "fields": fields},
        "account": (manifest.get("account") or {}).get("name"),
    }


def build(run_dir):
    """Return the page's whole data contract for one poll."""
    run_dir = pathlib.Path(run_dir)
    state = load_state(run_dir)
    manifest = _read_json(run_dir / "demo-manifest.json")

    # The file is the flag: the conductor writes intake.json on a valid
    # submission, so its existence is what moves the page past intake.
    # "live" is the third and final step — run_state.finish() sets `finished`
    # at the end of Beat 2, and without emitting it here the page's step 3
    # could never light and a completed run sat on "Building" forever.
    if not (run_dir / "intake.json").exists():
        phase = "intake"
    elif state.get("finished"):
        phase = "live"
    else:
        phase = "building"

    gates = gate_states(state)

    return {
        "phase": phase,
        "gates": gates,
        # The latest 'asked' timestamp per gate — lets the page tell a fresh
        # re-ask of the same gate apart from a repeat poll of one already
        # rendered. Never consumed for the open/closed decision itself;
        # `gates` above remains the single source of truth for that.
        "gates_at": gate_marks(state),
        "run_id": state.get("run_id"),
        "account_name": state.get("account_name"),
        "path": state.get("path"),
        "finished": bool(state.get("finished")),
        "updated_at": state.get("updated_at"),
        "mode": ((manifest or {}).get("run") or {}).get("mode"),
        "lanes": state.get("lanes") or {},
        "orders": _orders_with_fraud_level(state, manifest),
        "schedule": state.get("schedule") or {},
        "failures": state.get("failures") or [],
        "detail": {
            "scrape": _scrape_detail(run_dir),
            "template": _template_detail(state, manifest),
            "seed": _seed_detail(run_dir),
            "cdc": _cdc_detail(run_dir, state, manifest),
            "plan": _plan_detail(manifest, gates),
        },
    }
