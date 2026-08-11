#!/usr/bin/env python3
"""Fail-loud completeness check for demo-manifest.json, run before Phase 1.

Every rule mirrors the spec's Order model + manifest section. Exit 0 with
"MANIFEST OK", or exit 1 printing one "MANIFEST INVALID: <reason>" per line.
"""

import json
import sys

PROVEN_EVENTS = {"InTransit", "OutForDelivery", "Delivered", "WarehouseDelay"}
CDC_SLOTS = {"fraud_high", "fraud_medium", "fraud_low",
             "manual_return", "return_tracking"}
FRAUD_LEVELS = {"low", "medium", "high"}
PATHS = {"engage", "retain", "retain-shopify"}
BRAND_REGIONS = {"US", "UK", "DE"}
BRAND_CATEGORIES = {"Home", "Electronics", "Fashion"}
PACES = {"standard", "fast"}
PROVEN_SEQUENCES = (
    ("InTransit", "OutForDelivery", "Delivered"),
    ("InTransit", "WarehouseDelay"),
    # recovered — proven live 2026-08-11 (order STU-1786455234, account
    # 1626718); see order-lifecycle/references/status-codes.md
    ("InTransit", "WarehouseDelay", "OutForDelivery", "Delivered"),
)


def validate(m):
    errs = []

    def need(cond, msg):
        if not cond:
            errs.append(msg)

    need(m.get("path") in PATHS, f"path must be one of {sorted(PATHS)}")

    pace = m.get("run", {}).get("pace")
    if pace is not None:
        need(pace in PACES, f"run.pace must be one of {sorted(PACES)}")

    brand = m.get("brand", {})
    need(bool(brand.get("name")), "brand.name must be non-empty")
    need(brand.get("region") in BRAND_REGIONS,
         f"brand.region must be one of {sorted(BRAND_REGIONS)}")
    need(brand.get("category") in BRAND_CATEGORIES,
         f"brand.category must be one of {sorted(BRAND_CATEGORIES)}")

    products = {p.get("id"): p for p in m.get("products", [])}
    core4 = m.get("selection", {}).get("core4", [])
    extra = m.get("selection", {}).get("shopify_extra", [])
    need(len(core4) == 4, "core4 must name exactly 4 products")
    for pid in core4 + extra:
        need(pid in products, f"selection references unknown product {pid}")
    core_products = [products[p] for p in core4 if p in products]
    types = [p.get("product_type") for p in core_products]
    need(len(set(types)) == len(types), "core4 product types must be distinct")
    for pid in core4 + extra:
        if pid in products:
            need(products[pid].get("image_verified") is True,
                 f"image for {pid} not verified")

    shopify = m.get("shopify", {})
    if m.get("path") == "retain-shopify":
        need(shopify.get("enabled") is True,
             "path retain-shopify requires shopify.enabled true")
    if shopify.get("enabled"):
        need(bool(shopify.get("store")), "shopify.store missing")
        need(str(shopify.get("location_id", "")).startswith("gid://shopify/Location/"),
             "shopify.location_id must be a gid://shopify/Location/ id")

    orders = m.get("orders", [])
    need(1 <= len(orders) <= 5, "orders must contain between 1 and 5 entries")
    if len(orders) >= 2:
        need(any(len(o.get("shipments", [])) >= 2 for o in orders),
             "runs of 2+ orders need at least one split-shipment order")

    seen_customers, seen_slots, seen_labels = set(), set(), set()
    any_delivered = False
    for o in orders:
        label = o.get("label", "?")
        need(label not in seen_labels, f"duplicate order label {label}")
        seen_labels.add(label)
        cust = (o.get("customer", {}).get("name"), o.get("customer", {}).get("email"))
        need(all(cust), f"order {label}: customer name and email required")
        need(cust not in seen_customers, f"order {label}: duplicate customer {cust}")
        seen_customers.add(cust)
        need(o.get("fraud_level") in FRAUD_LEVELS,
             f"order {label}: fraud_level required (low|medium|high)")
        slot = o.get("cdc_slot")
        if slot is not None:
            need(slot in CDC_SLOTS, f"order {label}: unknown cdc_slot {slot}")
            need(slot not in seen_slots, f"order {label}: duplicate cdc_slot {slot}")
            seen_slots.add(slot)
        # Product references are product ids, the same style selection uses.
        # Integer indices into products[] also "work" for a careless consumer
        # and silently resolve to the wrong product, so reject them here.
        for pid in o.get("products", []):
            need(not isinstance(pid, bool) and not isinstance(pid, int),
                 f"order {label}: products must reference product ids, not indices "
                 f"(got {pid!r})")
            if isinstance(pid, str):
                need(pid in products,
                     f"order {label}: unknown product {pid}")
        need(bool(o.get("shipments")), f"order {label}: needs at least one shipment")
        for s in o.get("shipments", []):
            events = s.get("events", [])
            need(bool(events), f"order {label}/{s.get('label')}: needs events")
            unproven = set(s.get("unproven_events", []))
            for e in events:
                need(e in PROVEN_EVENTS or e in unproven,
                     f"order {label}/{s.get('label')}: event {e} outside the "
                     f"proven set must be listed in unproven_events")
            # Check if all events are proven but sequence is unproven
            if events and all(e in PROVEN_EVENTS for e in events):
                if tuple(events) not in PROVEN_SEQUENCES and not s.get("unproven_chain"):
                    need(False,
                         f"order {label}/{s.get('label')}: proven events in an unproven sequence — set unproven_chain: true")
            if events and events[-1] == "Delivered":
                any_delivered = True

    if m.get("path") in ("retain", "retain-shopify"):
        need(any_delivered,
             "Retain runs need at least one shipment ending Delivered")

    acct = m.get("account", {})
    need(bool(acct.get("id")) and bool(acct.get("name")),
         "account id and resolved name required")
    need(bool(acct.get("confirmed_at")), "account not confirmed at intake")
    need(acct.get("edit_mode_verified") is True, "edit-mode guard not verified")

    gates = m.get("gates", {}).get("order_lifecycle", {})
    need(gates.get("gate_b_answered") is True, "gate B answer missing")
    approvals = m.get("approvals", {})
    need(bool(approvals.get("products_approved_at")),
         "product approval timestamp missing")
    need(bool(approvals.get("intake_completed_at")),
         "intake approval timestamp missing")

    tokens = m.get("brand_tokens", {})
    need(bool(tokens.get("tokens")), "brand_tokens.tokens missing")
    need(bool(m.get("destination_country")), "destination_country missing")
    return errs


def main():
    if len(sys.argv) != 2:
        sys.exit("usage: validate_manifest.py <manifest-path>")
    manifest = json.loads(open(sys.argv[1]).read())
    errs = validate(manifest)
    if errs:
        for e in errs:
            print(f"MANIFEST INVALID: {e}")
        sys.exit(1)
    print("MANIFEST OK")


if __name__ == "__main__":
    main()
