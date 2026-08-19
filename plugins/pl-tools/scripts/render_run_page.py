#!/usr/bin/env python3
"""Render the demo-environment run page from run-state.json.

The conductor never writes HTML: it amends state and runs this. A republish is
therefore cheap enough to do a dozen times per run, which is the whole point —
the previous hand-edited page froze for the fifteen minutes that mattered most.
"""
import html as html_mod
import json
import pathlib
import re
import sys

import run_state
import pl_brand

CSS = f"""
:root {{ --fg:{pl_brand.TEXT}; --bg:#fff; --muted:#667; --card:{pl_brand.CARD}; --line:#e2e2e8;
        --ok:#0a7d33; --live:{pl_brand.PRIMARY}; --warn:#b45309; --bad:#b91c1c;
        --brand:{pl_brand.PRIMARY}; --tint:{pl_brand.TINT}; }}
@media (prefers-color-scheme: dark) {{ :root {{ --fg:#eee; --bg:#111; --muted:#99a;
        --card:#1c1c22; --line:#2c2c34; }} }}
:root[data-theme="dark"] {{ --fg:#eee; --bg:#111; --muted:#99a; --card:#1c1c22;
        --line:#2c2c34; }}
:root[data-theme="light"] {{ --fg:{pl_brand.TEXT}; --bg:#fff; --muted:#667; --card:{pl_brand.CARD};
        --line:#e2e2e8; }}
body {{ color:var(--fg); background:var(--bg); font:15px/1.55 {pl_brand.FONT_FAMILY};
       margin:0 auto; padding:24px; max-width:1100px; }}
.pl-header {{ display:flex; align-items:center; gap:10px; margin:0 0 18px; color:var(--brand); }}
.pl-header svg {{ width:100px; height:auto; }}
.layout {{ display:flex; gap:20px; align-items:flex-start; }}
.rail {{ flex:0 0 300px; position:sticky; top:16px; background:var(--card);
        border-radius:12px; padding:16px 18px; }}
.show {{ flex:1; min-width:0; }}
.card {{ background:var(--card); border-radius:12px; padding:16px 20px;
        margin:0 0 14px; }}
.fail {{ border-left:4px solid var(--bad); }}
.pill {{ display:inline-block; border-radius:999px; padding:2px 10px; margin:2px;
        font-size:12px; font-weight:600; }}
.s-confirmed {{ background:var(--ok); color:#fff; }}
.s-live {{ background:var(--live); color:#fff; }}
.s-expected {{ background:transparent; color:var(--muted);
              border:1px dashed var(--muted); }}
.s-failed {{ background:var(--bad); color:#fff; }}
.s-pending {{ background:transparent; color:var(--muted);
             border:1px solid var(--line); }}
.lbl {{ font-size:11px; text-transform:uppercase; letter-spacing:.08em;
       color:var(--muted); margin:14px 0 6px; }}
.overflow {{ overflow-x:auto; }}
table {{ border-collapse:collapse; width:100%; }}
td,th {{ text-align:left; padding:6px 10px; border-bottom:1px solid var(--line); }}
.stamp {{ font-size:12px; color:var(--muted); margin-top:12px; }}
.auto-banner {{ background:linear-gradient(90deg,#ff6b35,#f7931e); color:#111;
        font-size:20px; font-weight:800; text-align:center; padding:14px 20px;
        border-radius:12px; margin:0 0 16px; letter-spacing:.02em; }}
.auto-banner .sub {{ display:block; font-size:13px; font-weight:600;
        margin-top:4px; letter-spacing:normal; }}
@media (max-width: 768px) {{ .layout {{ display:block; }}
  .rail {{ position:static; margin-bottom:16px; }} }}
"""

AUTO_BANNER = (
    '<div class="auto-banner">🤖 AUTO MODE'
    '<span class="sub">Nobody\'s babysitting this one — it drove itself, '
    'and it\'s not even sorry.</span></div>'
)


def _auto_banner(manifest):
    """Flash the fact this run is unattended. Absent mode means babysit,
    matching run.pace's own convention, so no manifest or no explicit
    "auto" means no banner."""
    if not manifest:
        return ""
    if (manifest.get("run") or {}).get("mode") != "auto":
        return ""
    return AUTO_BANNER


CLOCK_JS = """
<script>
(() => {
  const S = RUN_SCHEDULE;
  const updated = Date.parse(RUN_UPDATED_AT);
  // How stale the page is, always. This page is a snapshot the conductor
  // republishes, so an unlabelled reading is indistinguishable from a frozen
  // one — the age is what tells the reader which they are looking at.
  const age = () => {
    const el = document.getElementById('freshness');
    if (!el || !updated) return;
    const secs = Math.max(0, Math.round((Date.now() - updated) / 1000));
    el.textContent = secs < 60
      ? 'updated ' + secs + 's ago'
      : 'updated ' + Math.floor(secs / 60) + 'm ' + (secs % 60) + 's ago';
  };
  if (!S || !S.started_at || !S.gap_seconds) {
    age();
    setInterval(age, 1000);
    return;
  }
  const started = Date.parse(S.started_at);
  const tick = () => {
    age();
    const elapsed = (Date.now() - started) / 1000;
    // Events fire after a leading gap, then one per gap.
    const due = Math.floor(elapsed / S.gap_seconds);
    document.querySelectorAll('[data-tracking]').forEach(box => {
      let seen = 0;
      box.querySelectorAll('.pill').forEach(pill => {
        seen += 1;
        // Only ever soften pending -> expected. Confirmation is the server's
        // job; the clock must never claim it.
        if (pill.classList.contains('s-pending') && seen <= due) {
          pill.classList.remove('s-pending');
          pill.classList.add('s-expected');
        }
      });
    });
    const next = S.gap_seconds - (elapsed % S.gap_seconds);
    const el = document.getElementById('countdown');
    if (el) el.textContent = 'next event in ' +
      Math.max(0, Math.floor(next)) + 's';
  };
  tick();
  setInterval(tick, 1000);
})();
</script>
"""


def e(value):
    return html_mod.escape(str(value), quote=True)


def _clock(state):
    """The page's own clock, or nothing.

    Omitted entirely once the run is finished, so opening the page tomorrow
    shows the real end state rather than an animation that ran off the end.
    """
    if state.get("finished"):
        return ""
    # Emitted with or without a schedule: the freshness ticker has to run from
    # the first publish, long before any driver is launched.
    schedule = state.get("schedule") or {}
    return ("<script>const RUN_SCHEDULE = "
            + json.dumps(schedule or None)
            + "; const RUN_UPDATED_AT = "
            + json.dumps(state.get("updated_at")) + ";</script>" + CLOCK_JS)


def state_of(planned_status, confirmed):
    """Where a planned step stands.

    The browser clock may later promote 'pending' to 'expected' — never to
    'confirmed'. Confirmation is only ever recorded server-side, so a driver
    that dies shows a dashed pill that never fills in rather than a fake
    success.
    """
    for entry in confirmed:
        if entry["status"] == planned_status:
            return "confirmed"
    return "pending"


def _lane_pill(name, lane):
    status = lane.get("status", "pending")
    cls = {"ok": "s-confirmed", "published": "s-confirmed",
           "running": "s-live", "failed": "s-failed"}.get(status, "s-pending")
    extra = ""
    if lane.get("layout_id"):
        extra = f" · {e(lane['layout_id'])}"
    if lane.get("store"):
        extra += f" · {e(lane['store'])}"
    return (f'<div><span class="pill {cls}">{e(name)}: {e(status)}</span>'
            f'<span style="color:var(--muted);font-size:12px">{extra}</span>'
            f'</div>')


def _rail(state):
    parts = ['<div class="rail">', '<div class="lbl">Run</div>']
    for name, lane in state["lanes"].items():
        parts.append(_lane_pill(name, lane))

    for order in state.get("orders", []):
        parts.append(f'<div class="lbl">{e(order["label"])}</div>')
        parts.append(f'<div style="font-size:12px;color:var(--muted)">'
                     f'{e(order["order_number"])}</div>')
        for ship in order["shipments"]:
            if len(order["shipments"]) > 1:
                label = ("parcel 1 of 2" if ship["label"] == "A"
                         else "parcel 2 of 2")
            else:
                label = "single parcel"
            parts.append(f'<div style="font-size:12px;margin-top:6px">'
                         f'{e(label)}</div>')
            parts.append(f'<div data-tracking="{e(ship["tracking_number"])}">')
            for planned in ship["planned"]:
                cls = "s-" + state_of(planned, ship["confirmed"])
                parts.append(
                    f'<span class="pill {cls}" data-step="{e(planned)}">'
                    f'{e(planned)}</span>')
            parts.append("</div>")

    parts.append('<div class="stamp" id="countdown"></div>')
    parts.append('<div class="stamp" id="freshness"></div>')
    parts.append(f'<div class="stamp">confirmed '
                 f'{e(state.get("updated_at") or "—")}</div>')
    parts.append("</div>")
    return "".join(parts)


def _failures(state):
    if not state.get("failures"):
        return ""
    rows = "".join(
        f'<div><span class="pill s-failed">{e(f["lane"])}</span> '
        f'{e(f["detail"])}</div>'
        for f in state["failures"])
    return f'<div class="card fail"><h2>Failures</h2>{rows}</div>'


def preview_template(template_html, assets):
    """The artifact copy of the email: identical markup, data: URIs for images.

    The canonical file on disk keeps remote URLs and is what gets pushed to
    parcelLab — pushing this variant would be both wrong and enormous.
    """
    by_url = {}
    for entry in (assets or {}).get("products", {}).values():
        if entry.get("image_url") and entry.get("data_uri"):
            by_url[entry["image_url"]] = entry["data_uri"]
    # The logo is not a product, so the loop above can never supply it. Without
    # this entry it falls through to the strip branch and the preview shows an
    # unbranded email — the one thing the preview exists to confirm.
    if (assets or {}).get("logo_url") and (assets or {}).get("logo_data_uri"):
        by_url[assets["logo_url"]] = assets["logo_data_uri"]
    hero = (assets or {}).get("hero") or {}

    def swap(match):
        url = match.group(1)
        if url in by_url:
            return f'src="{by_url[url]}"'
        if hero.get("data_uri"):
            return f'src="{hero["data_uri"]}"'
        # Nothing to substitute: drop the reference rather than ship a request
        # the CSP will block and render as a broken icon.
        return 'src="" data-stripped="1"'

    return re.sub(r'src="(https?://[^"]+)"', swap, template_html)


def _plan_facts(manifest):
    """The run's own parameters, stated once.

    Everything here was settled at intake and is invisible in the rail, which
    only tracks lane status — so without this the page cannot answer "what is
    this run actually going to do?".
    """
    brand = manifest.get("brand", {})
    shopify = manifest.get("shopify", {})
    cdc = manifest.get("cdc", {})
    account = manifest.get("account", {})
    pace = (manifest.get("run") or {}).get("pace") or "standard"
    facts = [
        ("Path", manifest.get("path")),
        ("Account", f'{account.get("name", "—")} ({account.get("id", "—")})'),
        ("Destination", manifest.get("destination_country")),
        ("Pace", f'{pace} ({200 if pace == "standard" else 60}s between events)'),
        ("Brand", f'{brand.get("name", "—")} · {brand.get("region", "—")} · '
                  f'{brand.get("category", "—")}'),
    ]
    if shopify.get("enabled"):
        facts.append(("Shopify store", shopify.get("store")))
    facts.append(("CDC", f'{brand.get("region", "—")} / '
                         f'{brand.get("category", "—")} · config: '
                         f'{cdc.get("config_source", "none")} · synthetic '
                         f'orders: {"yes" if cdc.get("generate_orders") else "no"}'))
    rows = "".join(
        f'<tr><td style="color:var(--muted);width:150px">{e(k)}</td>'
        f'<td>{e(v if v is not None else "—")}</td></tr>'
        for k, v in facts)
    return f'<div class="overflow"><table>{rows}</table></div>'


def _plan_orders(manifest):
    names = {p.get("id"): p.get("name") for p in manifest.get("products", [])}
    rows = []
    for order in manifest.get("orders", []):
        ships = order.get("shipments", []) or []
        for i, ship in enumerate(ships):
            parcel = ("single" if len(ships) == 1
                      else f'{ship.get("label", "?")} ({i + 1} of {len(ships)})')
            items = ", ".join(names.get(p, p) for p in ship.get("products", []))
            chain = " → ".join(ship.get("events", []))
            if ship.get("unproven_events") or ship.get("unproven_chain"):
                chain += ' <span class="pill s-expected">unproven</span>'
            rows.append(
                f'<tr><td>{e(order.get("label", "—"))}</td>'
                f'<td>{e(order.get("customer", {}).get("name", "—"))}</td>'
                f'<td>{e(order.get("fraud_level", "—"))}</td>'
                f'<td>{e(parcel)}</td><td>{e(items)}</td>'
                f'<td>{e(ship.get("scenario", "—"))}</td>'
                f'<td style="font-size:12px">{chain}</td></tr>')
    if not rows:
        return ""
    head = ("<tr><th>Order</th><th>Customer</th><th>Fraud</th><th>Parcel</th>"
            "<th>Items</th><th>Scenario</th><th>Events</th></tr>")
    return (f'<div class="overflow"><table>{head}{"".join(rows)}</table></div>')


def _plan_products(manifest):
    """The chosen products as a table, read straight from the manifest.

    Deliberately independent of the inlined assets: the plan must be legible
    before — or without — any image fetch, which is precisely the state a
    reader is in while deciding whether to approve the run.
    """
    selection = manifest.get("selection") or {}
    roles = {}
    for role, ids in (("core", selection.get("core4", [])),
                      ("extra", selection.get("shopify_extra", []))):
        for pid in ids:
            roles[pid] = role
    rows = []
    for product in manifest.get("products", []):
        role = roles.get(product.get("id"))
        if selection and role is None:
            continue
        variants = ", ".join(
            f'{o.get("name")}: {"/".join(o.get("values", []))}'
            for o in product.get("options", []) or []) or "—"
        rows.append(
            f'<tr><td>{e(product.get("name", "—"))}</td>'
            f'<td>{e(product.get("product_type", "—"))}</td>'
            f'<td>{e(product.get("price", "—"))}</td>'
            f'<td><span class="pill s-expected">{e(role or "—")}</span></td>'
            f'<td style="font-size:12px">{e(variants)}</td></tr>')
    if not rows:
        return ""
    head = ("<tr><th>Product</th><th>Type</th><th>Price</th><th>Role</th>"
            "<th>Variants</th></tr>")
    return f'<div class="overflow"><table>{head}{"".join(rows)}</table></div>'


def _plan_gate_asked(state):
    """Has the ✋ plan gate been posed yet?

    The manifest is written before both gates so the page can render what it
    asks about, which means its presence no longer marks the plan gate. State
    2b — the ★ template gate — must show the preview and swatches only, so the
    plan waits for its own gate to be asked.
    """
    return any(e.get("kind") == "gate" and e.get("name") == "plan"
               for e in (state or {}).get("timeline", []))


def _plan(manifest, state=None):
    if not manifest or not _plan_gate_asked(state):
        return ""
    return ('<div class="card"><h2>Run plan</h2>'
            + _plan_facts(manifest)
            + '<div class="lbl">Products</div>'
            + _plan_products(manifest)
            + '<div class="lbl">Orders</div>'
            + _plan_orders(manifest) + "</div>")


def _selected(manifest):
    """sku -> role, for the products this run actually uses.

    The scrape pool holds every candidate found; showing all of them invites
    the reader to plan around a product the run will never touch.
    """
    if not manifest:
        return None
    selection = manifest.get("selection") or {}
    if not selection:
        return None
    by_id = {p.get("id"): p for p in manifest.get("products", [])}
    roles = {}
    for role, ids in (("core", selection.get("core4", [])),
                      ("extra", selection.get("shopify_extra", []))):
        for pid in ids:
            product = by_id.get(pid)
            if product:
                roles[product.get("sku") or pid] = role
    return roles or None


def _products(assets, manifest=None):
    products = (assets or {}).get("products") or {}
    if not products:
        return ""
    roles = _selected(manifest)
    if roles is not None:
        products = {sku: p for sku, p in products.items() if sku in roles}
    cards = []
    for sku, p in products.items():
        if p.get("data_uri"):
            visual = (f'<img src="{p["data_uri"]}" alt="{e(p.get("name", ""))}" '
                      f'style="width:100%;height:140px;object-fit:cover;'
                      f'border-radius:8px" />')
        else:
            visual = ('<div style="height:140px;border-radius:8px;'
                      'background:var(--line);display:flex;align-items:center;'
                      'justify-content:center;color:var(--muted);'
                      'font-size:12px">image unavailable</div>')
        role = ""
        if roles:
            role = (f'<span class="pill s-expected">{e(roles[sku])}</span>')
        cards.append(
            f'<div style="flex:1 1 160px;min-width:160px">{visual}'
            f'<div style="font-size:13px;margin-top:6px">'
            f'{e(p.get("name", ""))}</div>'
            f'<div style="font-size:12px;color:var(--muted)">'
            f'{e(p.get("product_type", ""))} · {e(p.get("price", ""))}</div>'
            f'{role}</div>')
    return ('<div class="card"><h2>Products</h2>'
            '<div style="display:flex;gap:12px;flex-wrap:wrap">'
            + "".join(cards) + "</div></div>")


def _readable_on(hex_colour):
    """Pick black or white text for a swatch.

    A light swatch with white text is invisible: two of UNIQLO's were, live.
    """
    value = hex_colour.lstrip("#")
    if len(value) == 3:
        value = "".join(c * 2 for c in value)
    try:
        r, g, b = (int(value[i:i + 2], 16) for i in (0, 2, 4))
    except (ValueError, IndexError):
        return "#111"
    # Perceived brightness, ITU-R BT.601.
    return "#111" if (r * 299 + g * 587 + b * 114) / 1000 > 140 else "#fff"


def _brand_header(assets):
    if not assets:
        return ""
    logo = assets.get("logo_svg") or ""
    if not logo and assets.get("logo_data_uri"):
        logo = (f'<img src="{assets["logo_data_uri"]}" alt="brand logo" '
                f'style="max-width:220px;max-height:64px;height:auto" />')
    swatches = "".join(
        f'<span class="pill" style="background:{e(v)};'
        f'color:{_readable_on(v)};border:1px solid var(--line)">'
        f'{e(k)} {e(v)}</span>'
        for k, v in (assets.get("tokens") or {}).items()
        if isinstance(v, str) and v.startswith("#"))
    return (f'<div class="card" style="text-align:center">{logo}'
            f'<div style="margin-top:10px">{swatches}</div></div>')


def _template_card(template_html, assets):
    if not template_html:
        return ""
    srcdoc = e(preview_template(template_html, assets))
    return ('<div class="card"><h2>Email template</h2>'
            f'<iframe srcdoc="{srcdoc}" '
            'style="width:100%;height:520px;border:1px solid var(--line);'
            'border-radius:8px;background:#fff"></iframe></div>')


def _showcase(state, manifest, assets, template_html):
    return (_brand_header(assets)
            + _plan(manifest, state)
            + _template_card(template_html, assets)
            + _products(assets, manifest))


def _pl_header():
    return f'<div class="pl-header">{pl_brand.LOGO_SVG}</div>'


def render(state, manifest=None, assets=None, template_html=None):
    """Return the complete run page as a self-contained HTML string."""
    title = f'{state.get("run_id", "run")}'
    # `or` rather than a .get default: these keys are present-but-None until
    # intake resolves them, which a default never catches.
    body = [
        _pl_header(),
        _auto_banner(manifest),
        f'<h1>{e(state.get("account_name") or "—")} '
        f'<span style="color:var(--muted);font-size:16px">— {e(title)}</span>'
        f'</h1>',
        f'<p style="color:var(--muted)">{e(state.get("path") or "—")} path</p>',
        _failures(state),
        '<div class="layout">',
        _rail(state),
        '<div class="show">',
        _showcase(state, manifest, assets, template_html),
        "</div></div>",
        _clock(state),
    ]
    return (f'<meta charset="utf-8">'
            f"{pl_brand.GOOGLE_FONTS_LINK}"
            f"<title>{e(title)}</title><style>{CSS}</style>" + "".join(body))


def template_basenames(state, manifest):
    """Candidate `{brand}` prefixes for a `{brand}-parcellab-layout.html` file.

    The ★ template gate runs before the plan gate, so the template must be
    findable without a manifest — the run id's handle (`thenorthface` from
    `thenorthface-20260812-2243`) is the same string branded-template's Step 7
    names the file with. The manifest's brand is preferred when present, since
    a brand whose handle differs from its lowercased name (Pets at Home →
    petsathome) resolves either way.
    """
    names = []
    brand = ((manifest or {}).get("brand", {}).get("name") or "").lower()
    brand = re.sub(r"[^a-z0-9]", "", brand)
    if brand:
        names.append(brand)
    run_id = (state or {}).get("run_id") or ""
    handle = run_id.rsplit("-", 2)[0] if "-" in run_id else run_id
    if handle and handle not in names:
        names.append(handle)
    return names


def _find_template(state, manifest):
    previews = pathlib.Path.home() / "parcellab-previews"
    for name in template_basenames(state, manifest):
        candidate = previews / f"{name}-parcellab-layout.html"
        if candidate.exists():
            return candidate.read_text()
    return None


def _warn_missing_assets(run_dir, assets):
    """A finished scrape with no inlined assets renders an empty page.

    Silent by construction: `_brand_header` and `_products` both return "" when
    assets are absent, so the render succeeds and the conductor republishes a
    blank page. Only the reader finds out.
    """
    if assets is not None:
        return
    scrape_result = run_dir / "results" / "scrape.json"
    if not scrape_result.exists():
        return
    try:
        status = json.loads(scrape_result.read_text()).get("status")
    except (ValueError, OSError):
        return
    if status != "ok":
        return
    print(f"WARNING: {run_dir / 'scrape' / 'assets.json'} is missing while "
          f"results/scrape.json says ok — the brand header and product grid "
          f"will render empty. Run: python3 inline_assets.py {run_dir}",
          file=sys.stderr)


def main():
    if len(sys.argv) != 2:
        print("usage: render_run_page.py <run_dir>")
        return 1
    run_dir = pathlib.Path(sys.argv[1])
    state = json.loads((run_dir / "run-state.json").read_text())

    manifest = None
    manifest_path = run_dir / "demo-manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())

    assets = None
    assets_path = run_dir / "scrape" / "assets.json"
    if assets_path.exists():
        assets = json.loads(assets_path.read_text())
    _warn_missing_assets(run_dir, assets)

    template_html = _find_template(state, manifest)

    (run_dir / "run-page.html").write_text(
        render(state, manifest, assets, template_html))
    # Recorded after the write, so a render that died mid-write is not
    # counted. This is the half of page telemetry that cannot be skipped.
    run_state.record_render(run_dir)
    print(f"rendered {run_dir / 'run-page.html'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
