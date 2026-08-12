#!/usr/bin/env python3
"""Own `run-state.json` — the single source of truth for a demo-environment run.

Every write is read-amend-write through this module. Nothing else touches the
file, so the rendered run page can never disagree with recorded state.

This exists because the previous approach — a conductor hand-editing
`run-page.html` with string replacements — made every page update expensive, so
updates lost every race against a live write and the page froze for the fifteen
minutes that mattered most. Recording a fact must be cheap.
"""
import datetime
import json
import pathlib

FILENAME = "run-state.json"
LANES = ("scrape", "template", "seed", "orders", "cdc")
STATUSES = ("pending", "running", "ok", "published", "skipped", "failed")
KINDS = ("lane", "agent", "gate")
PHASES = ("start", "end", "asked", "answered")


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
        "timeline": [],
        "orders": [],
        "schedule": {},
        "page": {"renders": [], "publishes": []},
        "failures": [],
    }
    return _write(run_dir, state)


def load(run_dir):
    return json.loads(_path(run_dir).read_text())


def set_meta(run_dir, path=None, account_name=None):
    """Fill in run facts that were unknown at init().

    The path and the account are both settled partway through intake, after
    the run dir already exists — without this they stayed None for the whole
    run and the page titled itself "None".
    """
    def apply(state):
        if path is not None:
            state["path"] = path
        if account_name is not None:
            state["account_name"] = account_name

    return _amend(run_dir, apply)


def mark(run_dir, kind, name, phase):
    """Append one timeline entry. Never replaces an existing one.

    This is the record durations are derived from. `set_lane` keeps only the
    latest transition — correct for the run page's status pills, useless for
    measuring how long anything took.
    """
    if kind not in KINDS:
        raise ValueError(f"unknown kind {kind!r}; expected one of {KINDS}")
    if phase not in PHASES:
        raise ValueError(f"unknown phase {phase!r}; expected one of {PHASES}")

    def apply(state):
        state.setdefault("timeline", []).append(
            {"kind": kind, "name": name, "phase": phase, "at": _now()})

    return _amend(run_dir, apply)


def set_lane(run_dir, lane, status, **extra):
    if lane not in LANES:
        raise ValueError(f"unknown lane {lane!r}; expected one of {LANES}")
    if status not in STATUSES:
        raise ValueError(
            f"unknown status {status!r}; expected one of {STATUSES}")

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


def _page(state):
    return state.setdefault("page", {"renders": [], "publishes": []})


def record_render(run_dir):
    """Stamp a completed render. Called by render_run_page.py itself, so a
    render cannot happen unrecorded — this is the trustworthy half of the
    page telemetry, against which self-reported publishes are compared.
    """
    def apply(state):
        _page(state).setdefault("renders", []).append({"at": _now()})

    return _amend(run_dir, apply)


def record_publish(run_dir, url):
    """Stamp an Artifact call and the URL it returned.

    Self-reported: only the conductor knows a publish happened. A publish
    count below the render count is therefore the signal that the Artifact
    call was skipped.
    """
    def apply(state):
        _page(state).setdefault("publishes", []).append(
            {"at": _now(), "url": url})

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
