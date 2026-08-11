# demo-environment Live Run Visibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a demo-environment run visible while it happens — a two-column run page showing the brand deliverable alongside live progress, republished ~12 times per run instead of ~6, with drivers the user can actually see in their task list.

**Architecture:** The conductor stops hand-editing HTML. It maintains `run-state.json`; `render_run_page.py` derives the whole page from state + manifest + inlined assets. Drivers run as visible tracked tasks and append one JSON line per event; a coalescing watcher turns those appends into agent turns, and each turn re-renders and republishes. The page ticks its own clock between republishes but may only ever advance a step to *expected*, never to *confirmed*.

**Tech Stack:** Python 3 (stdlib only), Bash, HTML/CSS/vanilla JS.

**Spec:** `docs/superpowers/specs/2026-08-11-demo-environment-live-visibility-and-telemetry-design.md` (Parts A, B, and Part D items 1 and 6)

## Global Constraints

- Tests use **stdlib `unittest` only — never pytest**.
- Scripts live in `plugins/pl-tools/scripts/`; tests in `plugins/pl-tools/scripts/tests/test_<name>.py`.
- Run tests from `plugins/pl-tools/scripts/` as `python3 -m unittest tests.test_<module> < /dev/null`. **Never run bare `python3 -m unittest discover`** — it imports `test_pl_credentials`, which prompts interactively and hangs.
- **No network calls in tests.** Fetching code must be split so the pure parts (encoding, size guards, URL rewriting) are testable without I/O.
- **The published page must contain no external references.** The artifact CSP blocks them; a remote `<img src>` renders as a broken-image icon. Every test that renders HTML asserts `<img src="http` does not appear.
- **No version bump on release.** `pl-tools` is SHA-versioned: commit, push to `main`, run `/pl-update`.
- **Never rename any `parcellab-*` string** listed under *"Renaming things — read this first"* in the root README — in particular `$HOME/parcellab-previews/` and `{brand}-parcellab-layout.html`, which are real paths.
- Work on `main`.
- **The repo owner's standing rule: do not run `git commit` until he has explicitly said he is happy.** Each commit step means `git add`, show `git diff --staged`, then commit on his go-ahead.

## File Structure

| File | Responsibility |
|---|---|
| `plugins/pl-tools/scripts/run_state.py` | Own `run-state.json`: create, read, amend-and-write. Nothing else reads or writes that file directly. |
| `plugins/pl-tools/scripts/render_run_page.py` | Pure render: state + manifest + assets → complete `run-page.html`. No I/O beyond reading those inputs and writing the page. |
| `plugins/pl-tools/scripts/inline_assets.py` | Fetch images once, base64 them, enforce the size guard, write `scrape/assets.json`. |
| `plugins/pl-tools/skills/order-lifecycle/references/run-lifecycle.sh` | Gains opt-in `STATE_FILE` — one JSON line per event. |
| `plugins/pl-tools/scripts/wait_for_event.sh` | Block until any order's state file advances, settle, exit. |
| `plugins/pl-tools/skills/demo-environment/SKILL.md` | Wire it together: driver launch, republish triggers. |
| `plugins/pl-tools/skills/demo-environment/references/run-page.md` | Replace the milestone *rule* with the state *mechanism*. |

---

### Task 1: `run_state.py` — the single source of run progress

**Files:**
- Create: `plugins/pl-tools/scripts/run_state.py`
- Test: `plugins/pl-tools/scripts/tests/test_run_state.py`

**Interfaces:**
- Consumes: nothing.
- Produces, all taking `run_dir: str | pathlib.Path` as first argument:
  - `init(run_dir, run_id, path, account_name) -> dict`
  - `load(run_dir) -> dict`
  - `set_lane(run_dir, lane, status, **extra) -> dict`
  - `add_order(run_dir, label, order_number, shipments) -> dict` where `shipments` is a list of `{"label", "tracking_number", "courier", "planned": [str]}`
  - `confirm_event(run_dir, tracking_number, status, at, http) -> dict`
  - `set_schedule(run_dir, started_at, gap_seconds) -> dict`
  - `finish(run_dir) -> dict`
  - `add_failure(run_dir, lane, detail) -> dict`
  - Lane names are exactly `scrape`, `template`, `seed`, `orders`, `cdc`. Lane statuses are exactly `pending`, `running`, `ok`, `published`, `skipped`, `failed`.

- [ ] **Step 1: Write the failing test**

Create `plugins/pl-tools/scripts/tests/test_run_state.py`:

```python
"""Unit tests for run_state. Stdlib unittest — no pytest."""
import json
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import run_state  # noqa: E402


class TestRunState(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        run_state.init(self.dir, "uniqlo-20260811-1913", "engage", "Demo - JLS")

    def test_init_creates_all_lanes_pending(self):
        state = run_state.load(self.dir)
        self.assertEqual(state["run_id"], "uniqlo-20260811-1913")
        self.assertFalse(state["finished"])
        for lane in ("scrape", "template", "seed", "orders", "cdc"):
            self.assertEqual(state["lanes"][lane]["status"], "pending")

    def test_set_lane_records_status_and_extras(self):
        run_state.set_lane(self.dir, "template", "published", layout_id=20701)
        lane = run_state.load(self.dir)["lanes"]["template"]
        self.assertEqual(lane["status"], "published")
        self.assertEqual(lane["layout_id"], 20701)
        self.assertTrue(lane["at"])

    def test_set_lane_rejects_unknown_lane(self):
        with self.assertRaises(ValueError):
            run_state.set_lane(self.dir, "nonsense", "ok")

    def test_set_lane_rejects_unknown_status(self):
        with self.assertRaises(ValueError):
            run_state.set_lane(self.dir, "orders", "finished-ish")

    def test_confirm_event_appends_to_the_right_shipment(self):
        run_state.add_order(self.dir, "Clean delivery", "UNQ-1", [
            {"label": "A", "tracking_number": "15221962690914",
             "courier": "dpd-uk",
             "planned": ["InTransit", "OutForDelivery", "Delivered"]},
        ])
        run_state.confirm_event(self.dir, "15221962690914", "InTransit",
                                "2026-08-11T18:43:27Z", 204)
        ship = run_state.load(self.dir)["orders"][0]["shipments"][0]
        self.assertEqual(len(ship["confirmed"]), 1)
        self.assertEqual(ship["confirmed"][0]["status"], "InTransit")
        self.assertEqual(ship["confirmed"][0]["http"], 204)

    def test_confirm_event_is_idempotent(self):
        # The watcher may re-read the same line; a replay must not duplicate.
        run_state.add_order(self.dir, "Clean", "UNQ-1", [
            {"label": "A", "tracking_number": "TN1", "courier": "dpd-uk",
             "planned": ["InTransit"]},
        ])
        for _ in range(3):
            run_state.confirm_event(self.dir, "TN1", "InTransit",
                                    "2026-08-11T18:43:27Z", 204)
        ship = run_state.load(self.dir)["orders"][0]["shipments"][0]
        self.assertEqual(len(ship["confirmed"]), 1)

    def test_confirm_event_unknown_tracking_raises(self):
        with self.assertRaises(KeyError):
            run_state.confirm_event(self.dir, "NOPE", "InTransit",
                                    "2026-08-11T18:43:27Z", 204)

    def test_finish_sets_flag(self):
        run_state.finish(self.dir)
        self.assertTrue(run_state.load(self.dir)["finished"])

    def test_add_failure_accumulates(self):
        run_state.add_failure(self.dir, "cdc", "500 from API")
        run_state.add_failure(self.dir, "seed", "no store")
        self.assertEqual(len(run_state.load(self.dir)["failures"]), 2)

    def test_writes_are_valid_json_on_disk(self):
        run_state.set_lane(self.dir, "scrape", "ok")
        raw = (pathlib.Path(self.dir) / "run-state.json").read_text()
        json.loads(raw)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd plugins/pl-tools/scripts && python3 -m unittest tests.test_run_state < /dev/null
```

Expected: `ModuleNotFoundError: No module named 'run_state'`.

- [ ] **Step 3: Write the implementation**

Create `plugins/pl-tools/scripts/run_state.py`:

```python
#!/usr/bin/env python3
"""Own `run-state.json` — the single source of truth for a demo-environment run.

Every write is read-amend-write through this module. Nothing else touches the
file, so the rendered page can never disagree with recorded state.
"""
import datetime
import json
import pathlib

FILENAME = "run-state.json"
LANES = ("scrape", "template", "seed", "orders", "cdc")
STATUSES = ("pending", "running", "ok", "published", "skipped", "failed")


def _path(run_dir):
    return pathlib.Path(run_dir) / FILENAME


def _now():
    return datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


def _write(run_dir, state):
    state["updated_at"] = _now()
    path = _path(run_dir)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2))
    tmp.replace(path)          # atomic: a reader never sees a half-written file
    return state


def _amend(run_dir, fn):
    state = load(run_dir)
    fn(state)
    return _write(run_dir, state)


def init(run_dir, run_id, path, account_name):
    state = {
        "run_id": run_id,
        "path": path,
        "account_name": account_name,
        "updated_at": _now(),
        "finished": False,
        "lanes": {lane: {"status": "pending"} for lane in LANES},
        "orders": [],
        "schedule": {},
        "failures": [],
    }
    return _write(run_dir, state)


def load(run_dir):
    return json.loads(_path(run_dir).read_text())


def set_lane(run_dir, lane, status, **extra):
    if lane not in LANES:
        raise ValueError(f"unknown lane {lane!r}; expected one of {LANES}")
    if status not in STATUSES:
        raise ValueError(f"unknown status {status!r}; expected one of {STATUSES}")

    def apply(state):
        entry = {"status": status, "at": _now()}
        entry.update(extra)
        state["lanes"][lane] = entry

    return _amend(run_dir, apply)


def add_order(run_dir, label, order_number, shipments):
    def apply(state):
        state["orders"].append({
            "label": label,
            "order_number": order_number,
            "status": "ok",
            "shipments": [
                {
                    "label": s["label"],
                    "tracking_number": s["tracking_number"],
                    "courier": s["courier"],
                    "planned": list(s["planned"]),
                    "confirmed": [],
                }
                for s in shipments
            ],
        })

    return _amend(run_dir, apply)


def confirm_event(run_dir, tracking_number, status, at, http):
    def apply(state):
        for order in state["orders"]:
            for ship in order["shipments"]:
                if ship["tracking_number"] != tracking_number:
                    continue
                already = any(c["status"] == status and c["at"] == at
                              for c in ship["confirmed"])
                if not already:
                    ship["confirmed"].append(
                        {"status": status, "at": at, "http": http})
                return
        raise KeyError(f"no shipment with tracking_number {tracking_number!r}")

    return _amend(run_dir, apply)


def set_schedule(run_dir, started_at, gap_seconds):
    def apply(state):
        state["schedule"] = {"started_at": started_at,
                             "gap_seconds": int(gap_seconds)}

    return _amend(run_dir, apply)


def add_failure(run_dir, lane, detail):
    def apply(state):
        state["failures"].append({"lane": lane, "detail": detail,
                                  "at": _now()})

    return _amend(run_dir, apply)


def finish(run_dir):
    def apply(state):
        state["finished"] = True

    return _amend(run_dir, apply)
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd plugins/pl-tools/scripts && python3 -m unittest tests.test_run_state < /dev/null
```

Expected: `Ran 10 tests` … `OK`.

- [ ] **Step 5: Stage and commit** (owner approval required)

```bash
git add plugins/pl-tools/scripts/run_state.py plugins/pl-tools/scripts/tests/test_run_state.py
git commit -m "feat(demo-environment): run-state.json owned by one module"
```

---

### Task 2: `render_run_page.py` — the progress rail

Build the renderer's skeleton and its left rail. The showcase column arrives in
Task 3 and the clock in Task 4.

**Files:**
- Create: `plugins/pl-tools/scripts/render_run_page.py`
- Test: `plugins/pl-tools/scripts/tests/test_render_run_page.py`

**Interfaces:**
- Consumes: state dicts shaped by `run_state.py` (Task 1).
- Produces:
  - `render(state, manifest=None, assets=None, template_html=None) -> str`
  - `state_of(planned_status, confirmed_list) -> str` returning one of `confirmed`, `expected`, `pending`
  - CSS class names `s-confirmed`, `s-live`, `s-expected`, `s-failed` — Tasks 3 and 4 reuse these.
  - CLI: `render_run_page.py <run_dir>` writes `<run_dir>/run-page.html`.

- [ ] **Step 1: Write the failing test**

Create `plugins/pl-tools/scripts/tests/test_render_run_page.py`:

```python
"""Unit tests for render_run_page. Stdlib unittest — no pytest."""
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import render_run_page  # noqa: E402
import run_state  # noqa: E402


def a_state(finished=False):
    d = tempfile.mkdtemp()
    run_state.init(d, "uniqlo-20260811-1913", "engage", "Demo - JLS")
    run_state.set_lane(d, "scrape", "ok")
    run_state.set_lane(d, "template", "published", layout_id=20701,
                       store="JLS Order")
    run_state.set_lane(d, "orders", "running")
    run_state.add_order(d, "Clean delivery", "UNQ-1786473062", [
        {"label": "A", "tracking_number": "15221962690914",
         "courier": "dpd-uk",
         "planned": ["InTransit", "OutForDelivery", "Delivered"]},
    ])
    run_state.confirm_event(d, "15221962690914", "InTransit",
                            "2026-08-11T18:43:27Z", 204)
    run_state.set_schedule(d, "2026-08-11T18:40:27Z", 180)
    if finished:
        run_state.finish(d)
    return run_state.load(d)


class TestRenderRunPage(unittest.TestCase):
    def test_renders_run_id_and_account(self):
        html = render_run_page.render(a_state())
        self.assertIn("uniqlo-20260811-1913", html)
        self.assertIn("Demo - JLS", html)

    def test_no_external_references_anywhere(self):
        # The artifact CSP blocks these; a remote image renders as a broken icon.
        html = render_run_page.render(a_state())
        self.assertNotIn('<img src="http', html)
        self.assertNotIn('<script src="http', html)
        self.assertNotIn('<link rel="stylesheet" href="http', html)

    def test_confirmed_event_renders_confirmed(self):
        html = render_run_page.render(a_state())
        self.assertIn("s-confirmed", html)
        self.assertIn("InTransit", html)

    def test_unconfirmed_planned_event_is_not_marked_confirmed(self):
        html = render_run_page.render(a_state())
        delivered = html[html.index("Delivered"):]
        self.assertNotIn("s-confirmed", delivered[:200])

    def test_lane_status_appears(self):
        html = render_run_page.render(a_state())
        self.assertIn("published", html)
        self.assertIn("20701", html)

    def test_failure_renders_as_failed(self):
        state = a_state()
        state["failures"].append({"lane": "cdc", "detail": "500 from API",
                                  "at": "2026-08-11T19:00:00Z"})
        html = render_run_page.render(state)
        self.assertIn("s-failed", html)
        self.assertIn("500 from API", html)

    def test_state_of_confirmed(self):
        confirmed = [{"status": "InTransit", "at": "x", "http": 204}]
        self.assertEqual(
            render_run_page.state_of("InTransit", confirmed), "confirmed")

    def test_state_of_pending(self):
        self.assertEqual(render_run_page.state_of("Delivered", []), "pending")

    def test_dark_mode_and_theme_overrides_present(self):
        html = render_run_page.render(a_state())
        self.assertIn("prefers-color-scheme: dark", html)
        self.assertIn('data-theme="dark"', html)

    def test_wide_tables_scroll_inside_themselves(self):
        self.assertIn("overflow-x", render_run_page.render(a_state()))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd plugins/pl-tools/scripts && python3 -m unittest tests.test_render_run_page < /dev/null
```

Expected: `ModuleNotFoundError: No module named 'render_run_page'`.

- [ ] **Step 3: Write the implementation**

Create `plugins/pl-tools/scripts/render_run_page.py`:

```python
#!/usr/bin/env python3
"""Render the demo-environment run page from run-state.json.

The conductor never writes HTML: it amends state and runs this. A republish is
therefore cheap enough to do a dozen times per run, which is the whole point —
the previous hand-edited page froze for the 15 minutes that mattered most.
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
    """Where a planned step stands. The clock may later promote 'pending' to
    'expected' in the browser — never to 'confirmed'."""
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
            f'<span style="color:var(--muted);font-size:12px">{extra}</span></div>')


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


def render(state, manifest=None, assets=None, template_html=None):
    """Return the complete run page. Showcase content arrives in Task 3."""
    title = f'{state.get("run_id", "run")}'
    body = [
        f'<h1>{e(state.get("account_name", "—"))} '
        f'<span style="color:var(--muted);font-size:16px">— {e(title)}</span></h1>',
        f'<p style="color:var(--muted)">{e(state.get("path", "—"))} path</p>',
        _failures(state),
        '<div class="layout">',
        _rail(state),
        '<div class="show">',
        _showcase(state, manifest, assets, template_html),
        "</div></div>",
    ]
    return (f"<title>{e(title)}</title><style>{CSS}</style>" + "".join(body))


def _showcase(state, manifest, assets, template_html):
    """Placeholder until Task 3 fills in brand, products and the template."""
    return ""


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
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd plugins/pl-tools/scripts && python3 -m unittest tests.test_render_run_page < /dev/null
```

Expected: `Ran 10 tests` … `OK`.

- [ ] **Step 5: Stage and commit** (owner approval required)

```bash
git add plugins/pl-tools/scripts/render_run_page.py plugins/pl-tools/scripts/tests/test_render_run_page.py
git commit -m "feat(demo-environment): render run page rail from state"
```

---

### Task 3: `inline_assets.py` — images the artifact can actually show

**Files:**
- Create: `plugins/pl-tools/scripts/inline_assets.py`
- Test: `plugins/pl-tools/scripts/tests/test_inline_assets.py`

**Interfaces:**
- Consumes: `product-pool.json` and `brand-tokens.json` shapes from the scrape lane.
- Produces:
  - `to_data_uri(raw: bytes, content_type: str) -> str`
  - `MAX_ASSET_BYTES = 1_500_000`
  - `should_skip(size: int) -> bool`
  - `build_assets(pool, tokens, fetch) -> dict` — `fetch(url) -> (bytes, content_type)` is injected so tests never touch the network. Returns `{"logo_svg", "hero", "products": {sku: {...}}, "skipped": [...]}`.
  - CLI: `inline_assets.py <run_dir>` writes `<run_dir>/scrape/assets.json`.

- [ ] **Step 1: Write the failing test**

Create `plugins/pl-tools/scripts/tests/test_inline_assets.py`:

```python
"""Unit tests for inline_assets. Stdlib unittest — no pytest, no network."""
import base64
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import inline_assets  # noqa: E402

POOL = [
    {"id": "E491096-000", "sku": "E491096-000-57", "name": "Zip-Up Blouson",
     "price": "49.90", "product_type": "Jackets",
     "image_url": "https://img.example/a.jpg",
     "pdp_url": "https://example/a"},
    {"id": "E481610-000", "sku": "E481610-000-58", "name": "Shoulder Bag",
     "price": "14.90", "product_type": "Bags",
     "image_url": "https://img.example/big.jpg",
     "pdp_url": "https://example/b"},
]
TOKENS = {
    "tokens": {"BRAND_NAME": "UNIQLO"},
    "logo": {"type": "inline_svg", "markup": "<svg><title>U</title></svg>"},
    "hero": {"url": "https://img.example/hero.jpg", "alt": "hero"},
}


def fake_fetch(url):
    if "big" in url:
        return (b"x" * (inline_assets.MAX_ASSET_BYTES + 1), "image/jpeg")
    return (b"\xff\xd8imagedata", "image/jpeg")


class TestInlineAssets(unittest.TestCase):
    def test_to_data_uri_round_trips(self):
        uri = inline_assets.to_data_uri(b"abc", "image/png")
        self.assertTrue(uri.startswith("data:image/png;base64,"))
        self.assertEqual(base64.b64decode(uri.split(",", 1)[1]), b"abc")

    def test_should_skip_at_the_boundary(self):
        self.assertFalse(inline_assets.should_skip(inline_assets.MAX_ASSET_BYTES))
        self.assertTrue(inline_assets.should_skip(
            inline_assets.MAX_ASSET_BYTES + 1))

    def test_products_are_inlined_by_sku(self):
        assets = inline_assets.build_assets(POOL, TOKENS, fake_fetch)
        entry = assets["products"]["E491096-000-57"]
        self.assertTrue(entry["data_uri"].startswith("data:image/jpeg;base64,"))
        self.assertEqual(entry["name"], "Zip-Up Blouson")
        self.assertEqual(entry["price"], "49.90")

    def test_oversized_asset_is_skipped_not_inlined(self):
        assets = inline_assets.build_assets(POOL, TOKENS, fake_fetch)
        self.assertIsNone(assets["products"]["E481610-000-58"]["data_uri"])
        self.assertIn("E481610-000-58", str(assets["skipped"]))

    def test_hero_and_logo_captured(self):
        assets = inline_assets.build_assets(POOL, TOKENS, fake_fetch)
        self.assertTrue(assets["hero"]["data_uri"].startswith("data:"))
        self.assertIn("<svg", assets["logo_svg"])

    def test_fetch_failure_is_recorded_not_raised(self):
        def boom(url):
            raise OSError("connection reset")
        assets = inline_assets.build_assets(POOL, TOKENS, boom)
        self.assertIsNone(assets["products"]["E491096-000-57"]["data_uri"])
        self.assertEqual(len(assets["skipped"]), 3)  # 2 products + hero


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd plugins/pl-tools/scripts && python3 -m unittest tests.test_inline_assets < /dev/null
```

Expected: `ModuleNotFoundError: No module named 'inline_assets'`.

- [ ] **Step 3: Write the implementation**

Create `plugins/pl-tools/scripts/inline_assets.py`:

```python
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
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd plugins/pl-tools/scripts && python3 -m unittest tests.test_inline_assets < /dev/null
```

Expected: `Ran 6 tests` … `OK`.

- [ ] **Step 5: Stage and commit** (owner approval required)

```bash
git add plugins/pl-tools/scripts/inline_assets.py plugins/pl-tools/scripts/tests/test_inline_assets.py
git commit -m "feat(demo-environment): inline run images as data URIs"
```

---

### Task 4: The showcase column — brand, products, and the real email

**Files:**
- Modify: `plugins/pl-tools/scripts/render_run_page.py` (replace the `_showcase` placeholder from Task 2)
- Modify: `plugins/pl-tools/scripts/tests/test_render_run_page.py` (add a test class)

**Interfaces:**
- Consumes: `render()` and `e()` from Task 2; the `assets.json` shape from Task 3.
- Produces: `preview_template(template_html, assets) -> str` — the canonical layout HTML with remote image `src` values swapped for data URIs.

- [ ] **Step 1: Write the failing test**

Append to `plugins/pl-tools/scripts/tests/test_render_run_page.py` (before the `if __name__` block):

```python
ASSETS = {
    "logo_svg": "<svg><title>UNIQLO</title></svg>",
    "hero": {"alt": "hero", "data_uri": "data:image/jpeg;base64,aGVybw=="},
    "tokens": {"BRAND_NAME": "UNIQLO", "CTA_BG": "#000000"},
    "products": {
        "E491096-000-57": {"name": "Zip-Up Blouson", "price": "49.90",
                           "product_type": "Jackets",
                           "pdp_url": "https://example/a",
                           "image_url": "https://img.example/a.jpg",
                           "data_uri": "data:image/jpeg;base64,aW1n"},
        "E481610-000-58": {"name": "Shoulder Bag", "price": "14.90",
                           "product_type": "Bags",
                           "pdp_url": "https://example/b",
                           "image_url": "https://img.example/b.jpg",
                           "data_uri": None},
    },
    "skipped": [{"asset": "E481610-000-58", "reason": "too big"}],
}


class TestShowcase(unittest.TestCase):
    def test_logo_svg_is_inlined(self):
        html = render_run_page.render(a_state(), assets=ASSETS)
        self.assertIn("<svg><title>UNIQLO</title></svg>", html)

    def test_product_with_data_uri_renders_an_image(self):
        html = render_run_page.render(a_state(), assets=ASSETS)
        self.assertIn('src="data:image/jpeg;base64,aW1n"', html)
        self.assertIn("Zip-Up Blouson", html)

    def test_product_without_data_uri_renders_text_card_not_broken_image(self):
        html = render_run_page.render(a_state(), assets=ASSETS)
        self.assertIn("Shoulder Bag", html)
        self.assertNotIn("https://img.example/b.jpg", html)
        self.assertNotIn('<img src="http', html)

    def test_template_is_embedded_as_iframe_srcdoc(self):
        html = render_run_page.render(
            a_state(), assets=ASSETS,
            template_html='<html><body><img src="https://img.example/a.jpg"/>'
                          '</body></html>')
        self.assertIn("<iframe", html)
        self.assertIn("srcdoc=", html)

    def test_preview_template_swaps_remote_images_for_data_uris(self):
        out = render_run_page.preview_template(
            '<img src="https://img.example/a.jpg" width="600"/>', ASSETS)
        self.assertIn('src="data:image/jpeg;base64,aW1n"', out)
        self.assertNotIn("https://img.example/a.jpg", out)

    def test_preview_template_leaves_unknown_images_alone_but_strips_them(self):
        out = render_run_page.preview_template(
            '<img src="https://unknown.example/z.jpg"/>', ASSETS)
        self.assertNotIn("https://unknown.example/z.jpg", out)
```

- [ ] **Step 2: Run the tests to verify the new ones fail**

```bash
cd plugins/pl-tools/scripts && python3 -m unittest tests.test_render_run_page < /dev/null
```

Expected: the `TestShowcase` tests fail (no `preview_template`, empty showcase); `TestRenderRunPage` still passes.

- [ ] **Step 3: Write the implementation**

In `render_run_page.py`, add `import re` at the top, then replace the `_showcase` placeholder with:

```python
def preview_template(template_html, assets):
    """The artifact copy of the email: identical markup, data: URIs for images.

    The canonical file on disk keeps remote URLs and is what gets pushed to
    parcelLab — pushing this variant would be both wrong and enormous.
    """
    by_url = {}
    for entry in (assets or {}).get("products", {}).values():
        if entry.get("image_url") and entry.get("data_uri"):
            by_url[entry["image_url"]] = entry["data_uri"]
    hero = (assets or {}).get("hero") or {}

    def swap(match):
        url = match.group(1)
        if url in by_url:
            return f'src="{by_url[url]}"'
        if hero.get("data_uri"):
            return f'src="{hero["data_uri"]}"'
        # Nothing to substitute: drop the reference rather than ship a
        # request the CSP will block and render as a broken icon.
        return 'src="" data-stripped="1"'

    return re.sub(r'src="(https?://[^"]+)"', swap, template_html)


def _products(assets):
    products = (assets or {}).get("products") or {}
    if not products:
        return ""
    cards = []
    for sku, p in products.items():
        if p.get("data_uri"):
            visual = (f'<img src="{p["data_uri"]}" alt="{e(p.get("name",""))}" '
                      f'style="width:100%;height:140px;object-fit:cover;'
                      f'border-radius:8px" />')
        else:
            visual = ('<div style="height:140px;border-radius:8px;'
                      'background:var(--line);display:flex;align-items:center;'
                      'justify-content:center;color:var(--muted);'
                      'font-size:12px">image unavailable</div>')
        cards.append(
            f'<div style="flex:1 1 160px;min-width:160px">{visual}'
            f'<div style="font-size:13px;margin-top:6px">{e(p.get("name",""))}</div>'
            f'<div style="font-size:12px;color:var(--muted)">'
            f'{e(p.get("product_type",""))} · {e(p.get("price",""))}</div></div>')
    return ('<div class="card"><h2>Products</h2>'
            '<div style="display:flex;gap:12px;flex-wrap:wrap">'
            + "".join(cards) + "</div></div>")


def _brand_header(assets):
    if not assets:
        return ""
    logo = assets.get("logo_svg") or ""
    swatches = "".join(
        f'<span class="pill" style="background:{e(v)};color:#fff;'
        f'border:1px solid var(--line)">{e(k)}</span>'
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
            + _template_card(template_html, assets)
            + _products(assets))
```

Also update `main()` to load the canonical template when the manifest names the brand:

```python
    template_html = None
    if manifest:
        brand = (manifest.get("brand", {}).get("name") or "").lower()
        candidate = (pathlib.Path.home() / "parcellab-previews"
                     / f"{brand}-parcellab-layout.html")
        if candidate.exists():
            template_html = candidate.read_text()

    (run_dir / "run-page.html").write_text(
        render(state, manifest, assets, template_html))
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd plugins/pl-tools/scripts && python3 -m unittest tests.test_render_run_page < /dev/null
```

Expected: `Ran 16 tests` … `OK`.

- [ ] **Step 5: Stage and commit** (owner approval required)

```bash
git add plugins/pl-tools/scripts/render_run_page.py plugins/pl-tools/scripts/tests/test_render_run_page.py
git commit -m "feat(demo-environment): showcase column with brand, products, embedded email"
```

---

### Task 5: The clock — expected states that never lie

**Files:**
- Modify: `plugins/pl-tools/scripts/render_run_page.py`
- Modify: `plugins/pl-tools/scripts/tests/test_render_run_page.py`

**Interfaces:**
- Consumes: `render()`, `state_of()`, the `.s-expected` class, and the `data-tracking` / `data-step` attributes emitted by Task 2's rail.
- Produces: no new Python API — a `<script>` block whose behaviour is contracted as: it may only ever change a `.s-pending` pill to `.s-expected`, and it is omitted entirely when `state["finished"]` is true.

- [ ] **Step 1: Write the failing test**

Append to `plugins/pl-tools/scripts/tests/test_render_run_page.py`:

```python
class TestClock(unittest.TestCase):
    def test_running_run_embeds_the_schedule_and_clock(self):
        html = render_run_page.render(a_state())
        self.assertIn("RUN_SCHEDULE", html)
        self.assertIn("gap_seconds", html)

    def test_finished_run_has_no_clock(self):
        html = render_run_page.render(a_state(finished=True))
        self.assertNotIn("setInterval", html)

    def test_clock_only_ever_promotes_to_expected(self):
        # Contract guard: the script must not be able to write s-confirmed.
        html = render_run_page.render(a_state())
        script = html[html.index("<script>"):]
        self.assertIn("s-expected", script)
        self.assertNotIn("s-confirmed", script)
```

- [ ] **Step 2: Run the tests to verify the new ones fail**

```bash
cd plugins/pl-tools/scripts && python3 -m unittest tests.test_render_run_page < /dev/null
```

Expected: the three `TestClock` tests fail.

- [ ] **Step 3: Write the implementation**

In `render_run_page.py`, add:

```python
CLOCK_JS = """
<script>
(() => {
  const S = RUN_SCHEDULE;
  if (!S || !S.started_at || !S.gap_seconds) return;
  const started = Date.parse(S.started_at);
  const tick = () => {
    const elapsed = (Date.now() - started) / 1000;
    // Events fire after a leading gap, then one per gap.
    const due = Math.floor(elapsed / S.gap_seconds);
    document.querySelectorAll('[data-tracking]').forEach(box => {
      let seen = 0;
      box.querySelectorAll('.pill').forEach(pill => {
        seen += 1;
        // Only ever soften pending -> expected. Confirmation is the
        // server's job; the clock must never claim it.
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


def _clock(state):
    if state.get("finished"):
        return ""                      # frozen: opening this tomorrow shows truth
    schedule = state.get("schedule") or {}
    if not schedule:
        return ""
    return ("<script>const RUN_SCHEDULE = "
            + json.dumps(schedule) + ";</script>" + CLOCK_JS)
```

Add the countdown element to `_rail()` immediately before the `confirmed` stamp:

```python
    parts.append('<div class="stamp" id="countdown"></div>')
```

And append the clock in `render()`, as the last item of `body`:

```python
        _clock(state),
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd plugins/pl-tools/scripts && python3 -m unittest tests.test_render_run_page < /dev/null
```

Expected: `Ran 19 tests` … `OK`.

- [ ] **Step 5: Verify it renders in a browser**

Render the completed UNIQLO run as a fixture and open it in the Browser pane:

```bash
python3 plugins/pl-tools/scripts/render_run_page.py ~/parcellab-demo-runs/uniqlo-20260811-1913
```

(That run predates `run-state.json`, so create one first with `run_state.init` + `set_lane` calls matching its `results/*.json`, or skip this step and rely on the unit tests.) Check: rail sticks on scroll, no broken-image icons, dark and light both legible, body does not scroll sideways at 375px.

- [ ] **Step 6: Stage and commit** (owner approval required)

```bash
git add plugins/pl-tools/scripts/render_run_page.py plugins/pl-tools/scripts/tests/test_render_run_page.py
git commit -m "feat(demo-environment): client clock advances expected states only"
```

---

### Task 6: `run-lifecycle.sh` emits per-event state

**Files:**
- Modify: `plugins/pl-tools/skills/order-lifecycle/references/run-lifecycle.sh`
- Modify: `plugins/pl-tools/skills/order-lifecycle/references/tests/test-run-lifecycle.sh`

**Interfaces:**
- Consumes: nothing.
- Produces: when `STATE_FILE` is set, one JSON object per line appended after each event: `{"status": "...", "tracking_number": "...", "at": "...", "http": "..."}`. When unset, behaviour is byte-identical to today.

- [ ] **Step 1: Write the failing test**

Append to `plugins/pl-tools/skills/order-lifecycle/references/tests/test-run-lifecycle.sh` (following the file's existing test style):

```bash
# --- STATE_FILE is opt-in and off by default -------------------------------
test_state_file_absent_by_default() {
  local dir; dir="$(mktemp -d)"
  printf '{"event_status":"InTransit","location":"Hub","courier":"dpd-uk","tracking_number":"TN1"}' \
    > "$dir/01-InTransit.json"
  DRYRUN=1 EVENTS_DIR="$dir" GAP_SECONDS=0 LOG_FILE="$dir/run.log" \
    bash "$SCRIPT" >/dev/null 2>&1
  if ls "$dir"/*.jsonl >/dev/null 2>&1; then
    echo "FAIL: state file written when STATE_FILE unset"; return 1
  fi
  echo "PASS: no state file by default"
}

# --- STATE_FILE gets one JSON line per event --------------------------------
test_state_file_one_line_per_event() {
  local dir; dir="$(mktemp -d)"
  printf '{"event_status":"InTransit","location":"Hub","courier":"dpd-uk","tracking_number":"TN1"}' \
    > "$dir/01-InTransit.json"
  printf '{"event_status":"Delivered","location":"Door","courier":"dpd-uk","tracking_number":"TN1"}' \
    > "$dir/02-Delivered.json"
  DRYRUN=1 EVENTS_DIR="$dir" GAP_SECONDS=0 LOG_FILE="$dir/run.log" \
    STATE_FILE="$dir/events.jsonl" bash "$SCRIPT" >/dev/null 2>&1
  local lines; lines="$(wc -l < "$dir/events.jsonl" | tr -d ' ')"
  if [ "$lines" != "2" ]; then
    echo "FAIL: expected 2 state lines, got $lines"; return 1
  fi
  if ! grep -q '"tracking_number":"TN1"' "$dir/events.jsonl"; then
    echo "FAIL: tracking number missing from state line"; return 1
  fi
  echo "PASS: one state line per event"
}

test_state_file_absent_by_default
test_state_file_one_line_per_event
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
bash plugins/pl-tools/skills/order-lifecycle/references/tests/test-run-lifecycle.sh
```

Expected: `FAIL: expected 2 state lines, got 0`.

- [ ] **Step 3: Write the implementation**

In `run-lifecycle.sh`, add to the env documentation block near the top:

```bash
#      STATE_FILE (optional; unset = off). When set, one JSON object per line
#      is appended after each event: {"status","tracking_number","at","http"}.
#      The demo-environment conductor sets this so its watcher can turn event
#      progress into page updates. Standalone runs leave it unset and behave
#      exactly as before.
```

Add after the variable defaults:

```bash
STATE_FILE="${STATE_FILE:-}"
```

Then, immediately after the line that logs the per-event response (the `RESPONSE ...` log call), add:

```bash
  if [ -n "$STATE_FILE" ]; then
    printf '{"status":"%s","tracking_number":"%s","at":"%s","http":"%s"}\n' \
      "$EVENT_STATUS" "$TRACKING_NUMBER" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
      "$RESULT" >> "$STATE_FILE"
  fi
```

Bind `EVENT_STATUS`, `TRACKING_NUMBER` and `RESULT` from the payload alongside the existing parsing — reuse whatever the script already extracts for its log line rather than re-parsing the JSON a second way.

- [ ] **Step 4: Run the test to verify it passes**

```bash
bash plugins/pl-tools/skills/order-lifecycle/references/tests/test-run-lifecycle.sh
```

Expected: all tests pass, including the two new ones.

- [ ] **Step 5: Stage and commit** (owner approval required)

```bash
git add plugins/pl-tools/skills/order-lifecycle/references/run-lifecycle.sh plugins/pl-tools/skills/order-lifecycle/references/tests/test-run-lifecycle.sh
git commit -m "feat(order-lifecycle): opt-in STATE_FILE with one JSON line per event"
```

---

### Task 7: `wait_for_event.sh` — the coalescing watcher

**Files:**
- Create: `plugins/pl-tools/scripts/wait_for_event.sh`
- Test: `plugins/pl-tools/scripts/tests/test_wait_for_event.sh`

**Interfaces:**
- Consumes: the `events.jsonl` files written by Task 6.
- Produces: CLI `wait_for_event.sh <run_dir> [settle_seconds] [timeout_seconds]`. Blocks until the total line count across `<run_dir>/orders/*/events.jsonl` increases, waits `settle_seconds` (default 20) to collapse bursts, prints the new total, exits `0`. Exits `0` with `timeout` printed if `timeout_seconds` (default 1200) passes with no change.

- [ ] **Step 1: Write the failing test**

Create `plugins/pl-tools/scripts/tests/test_wait_for_event.sh`:

```bash
#!/usr/bin/env bash
# Tests for wait_for_event.sh — no network, no sleeping longer than a second.
set -uo pipefail
SCRIPT="$(cd "$(dirname "$0")/.." && pwd)/wait_for_event.sh"
fails=0

test_returns_when_a_line_is_appended() {
  local dir; dir="$(mktemp -d)"; mkdir -p "$dir/orders/01"
  : > "$dir/orders/01/events.jsonl"
  ( sleep 1; echo '{"status":"InTransit"}' >> "$dir/orders/01/events.jsonl" ) &
  local out; out="$(bash "$SCRIPT" "$dir" 0 10)"
  if ! echo "$out" | grep -q "1"; then
    echo "FAIL: expected new total 1, got: $out"; fails=1; return
  fi
  echo "PASS: returns on append"
}

test_times_out_quietly() {
  local dir; dir="$(mktemp -d)"; mkdir -p "$dir/orders/01"
  : > "$dir/orders/01/events.jsonl"
  local out; out="$(bash "$SCRIPT" "$dir" 0 1)"
  if ! echo "$out" | grep -q "timeout"; then
    echo "FAIL: expected timeout, got: $out"; fails=1; return
  fi
  echo "PASS: times out quietly"
}

test_missing_dir_does_not_hang() {
  local out; out="$(bash "$SCRIPT" /nonexistent-run-dir 0 1)"
  if ! echo "$out" | grep -q "timeout"; then
    echo "FAIL: expected timeout for missing dir, got: $out"; fails=1; return
  fi
  echo "PASS: missing dir times out"
}

test_returns_when_a_line_is_appended
test_times_out_quietly
test_missing_dir_does_not_hang
exit $fails
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
bash plugins/pl-tools/scripts/tests/test_wait_for_event.sh
```

Expected: failures — `wait_for_event.sh` does not exist.

- [ ] **Step 3: Write the implementation**

Create `plugins/pl-tools/scripts/wait_for_event.sh`:

```bash
#!/usr/bin/env bash
# Block until any order's event state advances, then exit so the conductor
# gets a turn to re-render and republish the run page.
#
# Usage: wait_for_event.sh <run_dir> [settle_seconds] [timeout_seconds]
#
# Coalescing matters: several orders push events within the same second, and
# one page update covering all of them is worth more than three in a row.
set -uo pipefail

RUN_DIR="${1:?run_dir required}"
SETTLE="${2:-20}"
TIMEOUT="${3:-1200}"

count_lines() {
  local total=0 f
  for f in "$RUN_DIR"/orders/*/events.jsonl; do
    [ -f "$f" ] || continue
    total=$(( total + $(wc -l < "$f") ))
  done
  echo "$total"
}

start_total="$(count_lines)"
elapsed=0
while [ "$elapsed" -lt "$TIMEOUT" ]; do
  sleep 2
  elapsed=$(( elapsed + 2 ))
  now="$(count_lines)"
  if [ "$now" -gt "$start_total" ]; then
    [ "$SETTLE" -gt 0 ] && sleep "$SETTLE"
    count_lines
    exit 0
  fi
done

echo "timeout"
exit 0
```

Make it executable: `chmod +x plugins/pl-tools/scripts/wait_for_event.sh`

- [ ] **Step 4: Run the test to verify it passes**

```bash
bash plugins/pl-tools/scripts/tests/test_wait_for_event.sh
```

Expected: three `PASS` lines, exit 0.

- [ ] **Step 5: Stage and commit** (owner approval required)

```bash
git add plugins/pl-tools/scripts/wait_for_event.sh plugins/pl-tools/scripts/tests/test_wait_for_event.sh
git commit -m "feat(demo-environment): coalescing event watcher"
```

---

### Task 8: Wire it into the conductor

**Files:**
- Modify: `plugins/pl-tools/skills/demo-environment/SKILL.md` (Phase 0 step 1; the run-page hook sentences; Phase 2 step 4 driver launch; Phase 2 Shopify engine driver launch)

**Interfaces:**
- Consumes: every script from Tasks 1–7.
- Produces: nothing consumed by later tasks.

- [ ] **Step 1: Replace the driver-launch instruction (defect fix 1)**

In Phase 2 (direct engine) step 4, replace **"then launch `run-lifecycle.sh` detached (`run_in_background`) — one driver per order, all orders concurrent"** with:

```markdown
   then launch `run-lifecycle.sh` as a **tracked background task — one Bash call per order with
   `run_in_background: true`, and NO `nohup`, `&`, or `disown`.**

   **These are two different mechanisms and mixing them defeats both.** `run_in_background` keeps
   the process attached to a task the user can see and notifies you when it exits. `nohup … &`
   detaches it from that task entirely: live 2026-08-11 a conductor wrapped the launch in `nohup`,
   so the tracked task was the *launcher* — it exited in about two seconds while three drivers ran
   for fifteen minutes with nothing in the user's task list. The user had to ask "I don't see any
   background tasks running?" to discover the run was fine.

   Set `STATE_FILE="orders/<nn>-<label>/events.jsonl"` on every launch so the watcher below can
   see progress.
```

- [ ] **Step 2: Add the watcher loop after the launches**

Immediately after that step, add:

```markdown
5. **Watch and republish.** After launching all drivers, run
   `${CLAUDE_PLUGIN_ROOT}/scripts/wait_for_event.sh <run dir>` as a tracked background task. When
   it returns, ingest every new line of each order's `events.jsonl` with
   `run_state.confirm_event(...)`, re-render, republish, and start the watcher again. Repeat until
   every driver's task has reported completion.

   This is what makes the page live. Expect roughly 8–12 republishes per run; that cost was chosen
   deliberately over a cheaper animation-only page. If it proves too expensive, widen the watcher's
   settle window rather than abandoning the loop.
```

- [ ] **Step 3: Replace every run-page hook sentence with the state+render form**

Every occurrence of the milestone hook currently reads *"Update `run-page.html` (state N per …) and republish — non-fatal."* Replace each with:

```markdown
Record the fact in `run-state.json` via `${CLAUDE_PLUGIN_ROOT}/scripts/run_state.py`, then
`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/render_run_page.py <run dir>` and republish the artifact —
non-fatal. **Never hand-edit `run-page.html`;** it is derived, and an edit will be overwritten by
the next render.
```

- [ ] **Step 4: Add state initialisation and asset inlining to Phase 0**

In Phase 0 step 1, after creating the run directory, add:

```markdown
   Initialise run state:
   `python3 -c "import sys; sys.path.insert(0, '${CLAUDE_PLUGIN_ROOT}/scripts'); import run_state;
   run_state.init('<run dir>', '<run id>', '<path>', '<account name>')"` — then render and publish
   as above. Path and account are still unknown at this point and render as `—`; they fill in at
   the next render.
```

In Phase 0 step 6 (pre-build), add as a new bullet:

```markdown
   - **Inline the run's images** so the page can show them:
     `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/inline_assets.py <run dir>`. The artifact CSP blocks
     external requests, so this is what makes product shots and the hero visible at all.
```

- [ ] **Step 5: Verify every referenced script exists at the documented path**

```bash
cd plugins/pl-tools
for s in scripts/run_state.py scripts/render_run_page.py scripts/inline_assets.py scripts/wait_for_event.sh; do
  [ -f "$s" ] && echo "OK $s" || echo "MISSING $s"
done
grep -c "run-page.html (state" skills/demo-environment/SKILL.md
```

Expected: four `OK` lines, and the grep returns `0` — no old hook sentences survive.

- [ ] **Step 6: Stage and commit** (owner approval required)

```bash
git add plugins/pl-tools/skills/demo-environment/SKILL.md
git commit -m "feat(demo-environment): visible drivers, event watcher, state-derived run page"
```

---

### Task 9: Rewrite `run-page.md` around the mechanism (defect fix 6)

**Files:**
- Modify: `plugins/pl-tools/skills/demo-environment/references/run-page.md`

**Interfaces:**
- Consumes: the renderer and state module.
- Produces: nothing.

- [ ] **Step 1: Replace the doctrine section**

Replace everything from **"**"Non-fatal" means a failed publish never blocks a phase.**"** through **"**The user is the detector of last resort, and that is a failure.**"** with:

```markdown
**The page is derived, never authored.** The conductor records facts in `run-state.json` and runs
`render_run_page.py`. Publishing is one Artifact call on the rendered file. Never hand-edit
`run-page.html` — the next render overwrites it.

**Why this replaced a rule.** Earlier versions of this file carried a rule — *"the page must never
be more than one milestone behind"* — plus escalating warnings about how often it had been broken.
It was then broken four more times, three of them by conductors that had just read it, and every
lapse was caught by the user asking why the page had not moved. The cause was structural, not moral:
updating the page meant hand-editing HTML with string replacements, which is expensive, so it lost
every race against a live write. Making the update cheap is what fixes it. If you find yourself
about to edit HTML by hand, that is the bug — fix the renderer instead.

**"Non-fatal" still means what it says:** a failed publish never blocks a phase. Say so once in
chat and carry on.
```

- [ ] **Step 2: Replace the states table intro and skeleton section**

Replace the `## Skeleton` section (the raw HTML skeleton) with:

```markdown
## Where the markup lives

`plugins/pl-tools/scripts/render_run_page.py` owns all of it — layout, CSS, the four-state
vocabulary, the clock. Change the page by changing the renderer and its tests, never by pasting
HTML into a run.

The four states, used everywhere:

| State | Class | Meaning |
|---|---|---|
| confirmed | `s-confirmed` | A republish confirmed this happened |
| happening now | `s-live` | In progress |
| expected | `s-expected` | The page's own clock believes this happened; unconfirmed |
| failed / stuck | `s-failed` | Failed, or a deliberate terminal state |

The clock may only ever promote a step to **expected**. A driver that dies therefore shows as a
dashed pill that never fills in, next to a stale `confirmed` stamp — visibly wrong rather than
quietly false.
```

- [ ] **Step 3: Verify no stale instructions survive**

```bash
grep -n "one milestone behind\|Skeleton\|<title>{brand}" plugins/pl-tools/skills/demo-environment/references/run-page.md
```

Expected: no matches.

- [ ] **Step 4: Confirm the renderer still passes its tests**

```bash
cd plugins/pl-tools/scripts && python3 -m unittest tests.test_render_run_page < /dev/null
```

Expected: `OK`.

- [ ] **Step 5: Stage and commit** (owner approval required)

```bash
git add plugins/pl-tools/skills/demo-environment/references/run-page.md
git commit -m "docs(demo-environment): run page is derived from state, not authored"
```
