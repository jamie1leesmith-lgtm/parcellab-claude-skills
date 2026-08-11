#!/usr/bin/env python3
"""Render the demo-environment run page from run-state.json.

The conductor never writes HTML: it amends state and runs this. A republish is
therefore cheap enough to do a dozen times per run, which is the whole point —
the previous hand-edited page froze for the fifteen minutes that mattered most.
"""
import html as html_mod
import json
import pathlib
import sys

CSS = """
:root { --fg:#111; --bg:#fff; --muted:#667; --card:#f5f5f7; --line:#e2e2e8;
        --ok:#0a7d33; --live:#1d4ed8; --warn:#b45309; --bad:#b91c1c; }
@media (prefers-color-scheme: dark) { :root { --fg:#eee; --bg:#111; --muted:#99a;
        --card:#1c1c22; --line:#2c2c34; } }
:root[data-theme="dark"] { --fg:#eee; --bg:#111; --muted:#99a; --card:#1c1c22;
        --line:#2c2c34; }
:root[data-theme="light"] { --fg:#111; --bg:#fff; --muted:#667; --card:#f5f5f7;
        --line:#e2e2e8; }
body { color:var(--fg); background:var(--bg); font:15px/1.55 system-ui,sans-serif;
       margin:0 auto; padding:24px; max-width:1100px; }
.layout { display:flex; gap:20px; align-items:flex-start; }
.rail { flex:0 0 300px; position:sticky; top:16px; background:var(--card);
        border-radius:12px; padding:16px 18px; }
.show { flex:1; min-width:0; }
.card { background:var(--card); border-radius:12px; padding:16px 20px;
        margin:0 0 14px; }
.fail { border-left:4px solid var(--bad); }
.pill { display:inline-block; border-radius:999px; padding:2px 10px; margin:2px;
        font-size:12px; font-weight:600; }
.s-confirmed { background:var(--ok); color:#fff; }
.s-live { background:var(--live); color:#fff; }
.s-expected { background:transparent; color:var(--muted);
              border:1px dashed var(--muted); }
.s-failed { background:var(--bad); color:#fff; }
.s-pending { background:transparent; color:var(--muted);
             border:1px solid var(--line); }
.lbl { font-size:11px; text-transform:uppercase; letter-spacing:.08em;
       color:var(--muted); margin:14px 0 6px; }
.overflow { overflow-x:auto; }
table { border-collapse:collapse; width:100%; }
td,th { text-align:left; padding:6px 10px; border-bottom:1px solid var(--line); }
.stamp { font-size:12px; color:var(--muted); margin-top:12px; }
@media (max-width: 768px) { .layout { display:block; }
  .rail { position:static; margin-bottom:16px; } }
"""


def e(value):
    return html_mod.escape(str(value), quote=True)


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
    parts.append(f'<div class="stamp">confirmed '
                 f'{e(state.get("updated_at", "—"))}</div>')
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


def _showcase(state, manifest, assets, template_html):
    """Placeholder — brand, products and the template arrive in LV4."""
    return ""


def render(state, manifest=None, assets=None, template_html=None):
    """Return the complete run page as a self-contained HTML string."""
    title = f'{state.get("run_id", "run")}'
    body = [
        f'<h1>{e(state.get("account_name", "—"))} '
        f'<span style="color:var(--muted);font-size:16px">— {e(title)}</span>'
        f'</h1>',
        f'<p style="color:var(--muted)">{e(state.get("path", "—"))} path</p>',
        _failures(state),
        '<div class="layout">',
        _rail(state),
        '<div class="show">',
        _showcase(state, manifest, assets, template_html),
        "</div></div>",
    ]
    return (f"<title>{e(title)}</title><style>{CSS}</style>" + "".join(body))


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

    (run_dir / "run-page.html").write_text(render(state, manifest, assets))
    print(f"rendered {run_dir / 'run-page.html'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
