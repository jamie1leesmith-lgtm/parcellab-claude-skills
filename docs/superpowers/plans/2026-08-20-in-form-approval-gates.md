# In-Form Approval Gates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the demo-environment run's two hard gates — the ★ template approval and the ✋ plan approval — off chat and onto the run page, with a scaled template preview and a full plan card, each carrying approve / request-changes controls.

**Architecture:** The run page already sends data to the conductor exactly once, at intake: `POST /submit` validates, atomically writes `intake.json`, and the conductor polls for that file. This plan adds two more sentinel files (`template-approval.json`, `plan-approval.json`) through the same handshake, and derives "is this gate open?" from the `gate` marks the conductor already writes into `run-state.json`'s timeline — so no new bookkeeping can be forgotten and there is no second source of truth.

**Tech Stack:** Python 3 stdlib only (`http.server`, `json`, `pathlib`, `unittest`). Vanilla JS + Tailwind utility classes in a single HTML template. No pytest, no new dependencies.

**Spec:** `docs/superpowers/specs/2026-08-20-in-form-approval-gates-design.md`

## Global Constraints

- **Repo:** `~/Documents/Claude/Projects/parcellab-claude-skills`, branch `feat/in-form-approval-gates`. All paths below are relative to `plugins/pl-tools/`.
- **Tests are stdlib `unittest`, never pytest.** Run a module with `python3 -m unittest tests.test_<name> -v` from `plugins/pl-tools/scripts/`. `unittest discover` does **not** work in this repo (the `tests` dir is not an importable package from the repo root) — always name the module.
- **No new dependencies.** Python stdlib only.
- **`decision` is exactly one of `"approved"` or `"changes_requested"`.** These two string literals appear in the schema, the server, the page and `SKILL.md`; they must match verbatim everywhere.
- **`note` max length is 2000 characters.**
- **Sentinel files are written last and only on success**, via a unique temp file named `f"{target.name}.{os.getpid()}.{threading.get_ident()}.tmp"` plus atomic `Path.replace()`. Never a fixed `.tmp` name — the server is threaded and two concurrent posts sharing a temp path can publish a torn document.
- **Gate names are `"template"` and `"plan"`** — the same `name` values already passed to `run_state.mark(d, "gate", <name>, ...)`.
- **`run_state` vocabularies (do not extend):** `KINDS = ("lane", "agent", "gate")`, `PHASES = ("start", "end", "asked", "answered")`. The `asked`/`answered` phases this feature relies on already exist.
- **Nothing in `state_payload.py` may write.** It is read-only by design and every file it reads is read defensively (`_read_json` returns `None` on anything unreadable), because a 2-second poll will inevitably catch a write mid-flight.
- **The page must never depend on a second server.** The template preview is served by `run_server` from inside the run dir, not iframed from the `layout-preview` server on port 8098.

---

### Task 1: `gate_states()` — derive gate status from the timeline

**Files:**
- Modify: `scripts/state_payload.py`
- Test: `scripts/tests/test_state_payload.py`

**Interfaces:**
- Consumes: nothing from earlier tasks. Reads `run_state`-shaped state dicts whose `timeline` entries are `{"kind", "name", "phase", "at"}`.
- Produces: `state_payload.gate_states(state) -> dict[str, str]` — module-level, always returns a key for each of `"template"` and `"plan"`, each valued `"pending" | "open" | "answered"`. Also adds `"gates"` to the `build()` payload with that same dict. Task 2 (server 409 check) and Task 5 (page rendering) both depend on this exact name and shape.

- [ ] **Step 1: Write the failing tests**

Add to `scripts/tests/test_state_payload.py`:

```python
    def test_gate_states_default_to_pending(self):
        gates = state_payload.gate_states(
            json.loads((self.dir / "run-state.json").read_text()))
        self.assertEqual(gates, {"template": "pending", "plan": "pending"})

    def test_asked_without_answered_is_open(self):
        run_state.mark(str(self.dir), "gate", "template", "asked")
        state = json.loads((self.dir / "run-state.json").read_text())
        self.assertEqual(state_payload.gate_states(state)["template"], "open")
        self.assertEqual(state_payload.gate_states(state)["plan"], "pending")

    def test_asked_then_answered_is_answered(self):
        run_state.mark(str(self.dir), "gate", "plan", "asked")
        run_state.mark(str(self.dir), "gate", "plan", "answered")
        state = json.loads((self.dir / "run-state.json").read_text())
        self.assertEqual(state_payload.gate_states(state)["plan"], "answered")

    def test_re_asking_after_an_answer_reopens_the_gate(self):
        """A rejected gate is re-asked: last mark wins, so it is open again."""
        for phase in ("asked", "answered", "asked"):
            run_state.mark(str(self.dir), "gate", "template", phase)
        state = json.loads((self.dir / "run-state.json").read_text())
        self.assertEqual(state_payload.gate_states(state)["template"], "open")

    def test_lane_and_agent_marks_never_affect_gates(self):
        run_state.mark(str(self.dir), "lane", "template", "start")
        run_state.mark(str(self.dir), "agent", "scrape", "start")
        gates = state_payload.gate_states(
            json.loads((self.dir / "run-state.json").read_text()))
        self.assertEqual(gates, {"template": "pending", "plan": "pending"})

    def test_build_payload_carries_gates(self):
        run_state.mark(str(self.dir), "gate", "template", "asked")
        self.assertEqual(state_payload.build(self.dir)["gates"]["template"],
                         "open")

    def test_gate_states_tolerates_a_missing_timeline(self):
        self.assertEqual(state_payload.gate_states({}),
                         {"template": "pending", "plan": "pending"})

    def test_plan_gate_stays_pending_when_only_the_manifest_exists(self):
        """The manifest exists from Phase 0 step 7 — before the plan gate.

        Keying the plan card on the manifest would leak the whole plan while
        the operator is still being asked about the template.
        """
        (self.dir / "demo-manifest.json").write_text(json.dumps(
            {"brand": {"name": "Brand"}}))
        self.assertEqual(state_payload.build(self.dir)["gates"]["plan"],
                         "pending")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run from `plugins/pl-tools/scripts/`:

```bash
python3 -m unittest tests.test_state_payload -v
```

Expected: FAIL — `AttributeError: module 'state_payload' has no attribute 'gate_states'`.

- [ ] **Step 3: Implement `gate_states()`**

Add to `scripts/state_payload.py`, above `build()`:

```python
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
```

Then add the key to the dict `build()` returns, immediately after `"phase": phase,`:

```python
        "gates": gate_states(state),
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python3 -m unittest tests.test_state_payload -v
```

Expected: PASS, all tests in the module.

- [ ] **Step 5: Commit**

```bash
git add plugins/pl-tools/scripts/state_payload.py \
        plugins/pl-tools/scripts/tests/test_state_payload.py
git commit -m "feat(state): derive gate open/answered state from the timeline"
```

---

### Task 2: `approval_schema.py` — validate an approval decision

**Files:**
- Create: `scripts/approval_schema.py`
- Create: `scripts/tests/test_approval_schema.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `approval_schema.parse_decision(raw_json) -> dict` with keys `decision` (str), `note` (str or None) and `at` (ISO-8601 UTC str, stamped by the parser). Raises `ValueError` with a human-readable reason on anything invalid. Also exports `DECISIONS = ("approved", "changes_requested")` and `MAX_NOTE = 2000`. Task 3 calls `parse_decision` and turns its `ValueError` into a 400.

- [ ] **Step 1: Write the failing tests**

Create `scripts/tests/test_approval_schema.py`:

```python
"""Unit tests for approval_schema. Stdlib unittest — no pytest."""
import json
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import approval_schema  # noqa: E402


class TestParseDecision(unittest.TestCase):
    def test_approved_needs_no_note(self):
        out = approval_schema.parse_decision(json.dumps(
            {"decision": "approved"}))
        self.assertEqual(out["decision"], "approved")
        self.assertIsNone(out["note"])
        self.assertTrue(out["at"].endswith("Z"))

    def test_approved_keeps_an_optional_note(self):
        out = approval_schema.parse_decision(json.dumps(
            {"decision": "approved", "note": "looks good"}))
        self.assertEqual(out["note"], "looks good")

    def test_changes_requested_keeps_its_note(self):
        out = approval_schema.parse_decision(json.dumps(
            {"decision": "changes_requested",
             "note": "footer address should be the UK entity"}))
        self.assertEqual(out["decision"], "changes_requested")
        self.assertEqual(out["note"],
                         "footer address should be the UK entity")

    def test_changes_requested_without_a_note_is_rejected(self):
        """A rejection with no reason forces the chat round-trip this
        feature exists to avoid."""
        with self.assertRaises(ValueError) as caught:
            approval_schema.parse_decision(json.dumps(
                {"decision": "changes_requested"}))
        self.assertIn("note", str(caught.exception))

    def test_changes_requested_with_a_blank_note_is_rejected(self):
        for blank in ("", "   ", "\n\t "):
            with self.assertRaises(ValueError):
                approval_schema.parse_decision(json.dumps(
                    {"decision": "changes_requested", "note": blank}))

    def test_note_is_stripped(self):
        out = approval_schema.parse_decision(json.dumps(
            {"decision": "changes_requested", "note": "  fix the footer  "}))
        self.assertEqual(out["note"], "fix the footer")

    def test_note_over_the_limit_is_rejected(self):
        with self.assertRaises(ValueError) as caught:
            approval_schema.parse_decision(json.dumps(
                {"decision": "changes_requested",
                 "note": "x" * (approval_schema.MAX_NOTE + 1)}))
        self.assertIn("2000", str(caught.exception))

    def test_note_at_exactly_the_limit_is_allowed(self):
        out = approval_schema.parse_decision(json.dumps(
            {"decision": "changes_requested",
             "note": "x" * approval_schema.MAX_NOTE}))
        self.assertEqual(len(out["note"]), approval_schema.MAX_NOTE)

    def test_unknown_decision_is_rejected(self):
        with self.assertRaises(ValueError) as caught:
            approval_schema.parse_decision(json.dumps({"decision": "maybe"}))
        self.assertIn("approved", str(caught.exception))

    def test_missing_decision_is_rejected(self):
        with self.assertRaises(ValueError):
            approval_schema.parse_decision(json.dumps({"note": "hi"}))

    def test_unknown_top_level_key_is_rejected(self):
        """Stricter than intake_schema on purpose: a typo'd field on a
        two-key schema should fail loudly, not be silently ignored."""
        with self.assertRaises(ValueError) as caught:
            approval_schema.parse_decision(json.dumps(
                {"decision": "approved", "notes": "typo"}))
        self.assertIn("notes", str(caught.exception))

    def test_non_string_note_is_rejected(self):
        with self.assertRaises(ValueError):
            approval_schema.parse_decision(json.dumps(
                {"decision": "approved", "note": 7}))

    def test_non_object_body_is_rejected(self):
        with self.assertRaises(ValueError):
            approval_schema.parse_decision(json.dumps([1, 2]))

    def test_invalid_json_is_rejected(self):
        with self.assertRaises(ValueError):
            approval_schema.parse_decision("{not json")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
python3 -m unittest tests.test_approval_schema -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'approval_schema'`.

- [ ] **Step 3: Implement `approval_schema.py`**

Create `scripts/approval_schema.py`:

```python
"""Validate one gate approval posted from the run page.

Deliberately tiny — two keys — and deliberately stricter than
`intake_schema`, which rejects unknown keys only inside `extras`. On a
two-key body a typo'd field should fail loudly rather than be dropped on
the floor, because the dropped value would be the operator's reason for
rejecting something.
"""
import datetime
import json

DECISIONS = ("approved", "changes_requested")
MAX_NOTE = 2000
_ALLOWED_KEYS = {"decision", "note"}


def _now():
    return datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


def parse_decision(raw_json):
    """Parse and validate a decision body, or raise ValueError with why.

    Returns `{"decision", "note", "at"}`. `at` is stamped here rather than
    accepted from the client: it records when the server accepted the
    decision, which is the only clock the conductor can trust.
    """
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise ValueError(f"not valid JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError("decision must be a JSON object")

    unknown = sorted(set(data) - _ALLOWED_KEYS)
    if unknown:
        raise ValueError(f"unknown key(s): {unknown}")

    decision = data.get("decision")
    if decision not in DECISIONS:
        raise ValueError(
            f"decision must be one of {list(DECISIONS)} (got {decision!r})")

    note = data.get("note")
    if note is not None:
        if not isinstance(note, str):
            raise ValueError("note must be a string or null")
        if len(note) > MAX_NOTE:
            raise ValueError(f"note must be at most {MAX_NOTE} characters "
                             f"(got {len(note)})")
        note = note.strip() or None

    if decision == "changes_requested" and not note:
        raise ValueError(
            "note is required when requesting changes — a rejection with no "
            "reason cannot be acted on without asking in chat")

    return {"decision": decision, "note": note, "at": _now()}
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python3 -m unittest tests.test_approval_schema -v
```

Expected: PASS, 14 tests.

- [ ] **Step 5: Commit**

```bash
git add plugins/pl-tools/scripts/approval_schema.py \
        plugins/pl-tools/scripts/tests/test_approval_schema.py
git commit -m "feat(approvals): add approval_schema for gate decisions"
```

---

### Task 3: Route table + the three new routes

**Files:**
- Modify: `scripts/run_server.py` — `_get`, `_post`, and a new `_write_sentinel` helper
- Test: `scripts/tests/test_run_server.py`

**Interfaces:**
- Consumes: `state_payload.gate_states` (Task 1); `approval_schema.parse_decision` (Task 2).
- Produces: `POST /approve/template` and `POST /approve/plan` writing `<run dir>/template-approval.json` / `plan-approval.json`; `GET /template.html` serving `<run dir>/template-preview.html`. Task 5's page JS posts to these paths; Task 6's `SKILL.md` polls for those filenames.

**Why the refactor:** `_post` currently hard-codes one `if self.path != "/submit"` comparison. Three routes need dispatch. The intake branch moves into a helper **unchanged** so its existing tested behaviour is untouched.

- [ ] **Step 1: Write the failing tests**

Append to `scripts/tests/test_run_server.py`:

```python
class TestApprovalRoutes(ServerTestCase):
    def open_gate(self, name):
        run_state.mark(str(self.dir), "gate", name, "asked")

    def test_approving_an_open_gate_writes_the_sentinel(self):
        self.open_gate("template")
        status, body = self.post("/approve/template", {"decision": "approved"})
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])
        written = json.loads(
            (self.dir / "template-approval.json").read_text())
        self.assertEqual(written["decision"], "approved")
        self.assertIsNone(written["note"])
        self.assertTrue(written["at"].endswith("Z"))

    def test_requesting_changes_writes_the_note(self):
        self.open_gate("plan")
        status, _ = self.post("/approve/plan", {
            "decision": "changes_requested", "note": "use UK address"})
        self.assertEqual(status, 200)
        written = json.loads((self.dir / "plan-approval.json").read_text())
        self.assertEqual(written["note"], "use UK address")

    def test_each_gate_writes_its_own_file(self):
        self.open_gate("template")
        self.post("/approve/template", {"decision": "approved"})
        self.assertTrue((self.dir / "template-approval.json").exists())
        self.assertFalse((self.dir / "plan-approval.json").exists())

    def test_posting_to_a_gate_that_was_never_asked_is_409(self):
        status, body = self.post("/approve/plan", {"decision": "approved"})
        self.assertEqual(status, 409)
        self.assertFalse(body["ok"])
        self.assertFalse((self.dir / "plan-approval.json").exists())

    def test_posting_to_an_already_answered_gate_is_409(self):
        """A stale browser tab must not answer a resolved gate."""
        self.open_gate("template")
        run_state.mark(str(self.dir), "gate", "template", "answered")
        status, _ = self.post("/approve/template", {"decision": "approved"})
        self.assertEqual(status, 409)

    def test_invalid_decision_is_400_and_writes_nothing(self):
        self.open_gate("template")
        status, body = self.post("/approve/template", {"decision": "maybe"})
        self.assertEqual(status, 400)
        self.assertIn("approved", body["error"])
        self.assertFalse((self.dir / "template-approval.json").exists())

    def test_changes_without_a_note_is_400(self):
        self.open_gate("plan")
        status, body = self.post("/approve/plan",
                                 {"decision": "changes_requested"})
        self.assertEqual(status, 400)
        self.assertIn("note", body["error"])

    def test_unknown_gate_name_is_404(self):
        status, _ = self.post("/approve/nope", {"decision": "approved"})
        self.assertEqual(status, 404)

    def test_submit_still_works_after_the_route_refactor(self):
        status, body = self.post("/submit",
                                 intake_schema.default_answers(region="US"))
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])
        self.assertTrue((self.dir / "intake.json").exists())


class TestTemplatePreviewRoute(ServerTestCase):
    def test_serves_the_preview_file(self):
        (self.dir / "template-preview.html").write_text(
            "<html><body>preview</body></html>")
        status, body = self.get("/template.html")
        self.assertEqual(status, 200)
        self.assertIn(b"preview", body)

    def test_missing_preview_is_404(self):
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.get("/template.html")
        self.assertEqual(caught.exception.code, 404)

    def test_preview_is_served_as_html(self):
        (self.dir / "template-preview.html").write_text("<html></html>")
        with urllib.request.urlopen(
                self.url("/template.html"), timeout=5) as response:
            self.assertIn("text/html",
                          response.headers.get("Content-Type", ""))
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
python3 -m unittest tests.test_run_server -v
```

Expected: FAIL — the approve posts return 404 (no such route), so `test_approving_an_open_gate_writes_the_sentinel` fails on `assertEqual(status, 200)`.

- [ ] **Step 3: Implement the routes**

In `scripts/run_server.py`, add near the other module constants:

```python
APPROVAL_FILES = {"template": "template-approval.json",
                  "plan": "plan-approval.json"}
TEMPLATE_PREVIEW_FILE = "template-preview.html"
```

Add `import approval_schema` and `import state_payload` (the latter is already imported).

Replace the body of `_get` with:

```python
        def _get(self):
            path = self.path.split("?", 1)[0]
            if path == "/":
                self._send(200, render_page(run_dir, context),
                           "text/html; charset=utf-8")
            elif path == "/state":
                self._send_json(200, state_payload.build(run_dir))
            elif path == "/template.html":
                self._serve_template_preview()
            else:
                self._send_json(404, {"ok": False, "error": "not found"})

        def _serve_template_preview(self):
            """The built layout, copied into the run dir by the conductor.

            A fixed filename inside run_dir — no path parameter, so there is
            no traversal surface. Served here rather than iframed from the
            layout-preview server on 8098 because the run page must not
            depend on a second server being alive.
            """
            preview = run_dir / TEMPLATE_PREVIEW_FILE
            try:
                body = preview.read_bytes()
            except OSError:
                self._send_json(404, {"ok": False,
                                      "error": "no template preview yet"})
                return
            self._send(200, body, "text/html; charset=utf-8")
```

Replace `_post` with a dispatching version. The body-reading preamble is unchanged; only the routing and the two handlers are new:

```python
        def _post(self):
            path = self.path.split("?", 1)[0]
            gate = None
            if path.startswith("/approve/"):
                gate = path[len("/approve/"):]
                if gate not in APPROVAL_FILES:
                    self._send_json(404, {"ok": False, "error": "not found"})
                    return
            elif path != "/submit":
                self._send_json(404, {"ok": False, "error": "not found"})
                return

            raw = self._read_body()
            if raw is None:
                return          # _read_body already answered or closed

            if gate is None:
                self._handle_submit(raw)
            else:
                self._handle_approval(gate, raw)

        def _read_body(self):
            """The request body, or None when it has already been answered."""
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except (TypeError, ValueError):
                self._send_json(400, {"ok": False,
                                      "error": "invalid Content-Length"})
                return None
            if length > MAX_BODY_BYTES:
                self._send_json(400, {"ok": False,
                                      "error": "payload too large"})
                return None
            try:
                return self.rfile.read(length).decode("utf-8", "replace")
            except TimeoutError:
                # The client declared more bytes than it ever sent. Close
                # rather than hang this thread on a body that will never
                # arrive.
                self.close_connection = True
                return None

        def _handle_submit(self, raw):
            try:
                answers = intake_schema.parse_answers(raw)
            except ValueError as exc:
                self._send_json(400, {"ok": False, "error": str(exc)})
                return
            self._write_sentinel("intake.json", answers)
            self._send_json(200, {"ok": True})

        def _handle_approval(self, gate, raw):
            # 409 rather than 400: the body may be perfectly valid, it is the
            # gate that is not accepting answers. Stops a stale browser tab
            # answering a gate already resolved in chat via the fallback.
            states = state_payload.gate_states(
                state_payload.load_state(run_dir))
            if states.get(gate) != "open":
                self._send_json(409, {
                    "ok": False,
                    "error": f"gate {gate!r} is not open for approval"})
                return
            try:
                decision = approval_schema.parse_decision(raw)
            except ValueError as exc:
                self._send_json(400, {"ok": False, "error": str(exc)})
                return
            self._write_sentinel(APPROVAL_FILES[gate], decision)
            self._send_json(200, {"ok": True})

        def _write_sentinel(self, name, payload):
            """Atomic publish of a file whose existence is a signal.

            Unique temp name per request (pid + thread id), never a fixed
            ".tmp": the server is threaded, so two concurrent writes sharing
            one temp path could interleave and publish a torn document — the
            rename is atomic, but only over whichever bytes are in the file
            at replace() time.
            """
            target = run_dir / name
            tmp = target.with_name(
                f"{name}.{os.getpid()}.{threading.get_ident()}.tmp")
            try:
                tmp.write_text(json.dumps(payload, indent=2))
                tmp.replace(target)
            except OSError:
                tmp.unlink(missing_ok=True)
                raise
```

Then in `scripts/state_payload.py`, expose the state loader the server now needs — rename `_load_state` to `load_state` and keep a module-level alias so nothing else breaks:

```python
def load_state(run_dir):
    ...  # body unchanged from _load_state


_load_state = load_state          # existing internal callers
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python3 -m unittest tests.test_run_server -v
python3 -m unittest tests.test_state_payload -v
```

Expected: PASS in both, including every pre-existing `TestSubmit` test.

- [ ] **Step 5: Commit**

```bash
git add plugins/pl-tools/scripts/run_server.py \
        plugins/pl-tools/scripts/state_payload.py \
        plugins/pl-tools/scripts/tests/test_run_server.py
git commit -m "feat(server): add approval and template-preview routes"
```

---

### Task 4: Plan-card data in the state payload

**Files:**
- Modify: `scripts/state_payload.py`
- Test: `scripts/tests/test_state_payload.py`

**Interfaces:**
- Consumes: `gate_states` (Task 1).
- Produces: `build()["detail"]["plan"]` — `None` unless the plan gate is `"open"`, otherwise a dict with keys `core4`, `orders`, `cdc`, `extras`, `account`. Task 5 renders exactly these keys.

**Shape produced** (every value read from `demo-manifest.json`):

```python
{
  "core4":   [{"id", "name", "product_type", "price"}],
  "orders":  [{"label", "customer", "fraud_level", "cdc_slot",
               "products": [name, ...],
               "shipments": [{"label", "scenario", "courier", "events"}]}],
  "cdc":     {"region", "category", "config_source",
              "generate_orders": False},
  "extras":  {"gate_c": "send-as-is"|"extras", "fields": [[label, value]]},
  "account": "Demo - Jamie Lee-Smith",
}
```

- [ ] **Step 1: Write the failing tests**

Add to `scripts/tests/test_state_payload.py`:

```python
    MANIFEST = {
        "brand": {"region": "UK", "category": "Electronics"},
        "account": {"id": 1626718, "name": "Demo - JLS"},
        "cdc": {"config_source": "none", "generate_orders": False,
                "orders": []},
        "products": [
            {"id": "h100", "name": "Beoplay H100",
             "product_type": "Over-Ear Headphones", "price": "1500.00"},
            {"id": "a5", "name": "Beosound A5",
             "product_type": "Portable Home Speaker", "price": "1400.00"},
            {"id": "ex", "name": "Beosound Explore",
             "product_type": "Outdoor Speaker", "price": "219.00"},
            {"id": "el", "name": "Beoplay Eleven",
             "product_type": "Wireless Earbuds", "price": "429.00"},
        ],
        "selection": {"core4": ["h100", "a5", "ex", "el"],
                      "shopify_extra": []},
        "orders": [{
            "label": "fraud-low", "fraud_level": "low",
            "cdc_slot": "fraud_low",
            "customer": {"name": "James Wilson",
                         "email": "james@example.com"},
            "products": ["el"],
            "shipments": [{"label": "A", "scenario": "happy",
                           "courier": "dpd-uk",
                           "events": ["InTransit", "Delivered"]}],
        }],
        "gates": {"order_lifecycle": {
            "gate_c": "extras",
            "extras": {"article_weights": {
                "el": {"weight": 0.4, "weight_unit": "kg"}}}}},
    }

    def write_manifest(self):
        (self.dir / "demo-manifest.json").write_text(
            json.dumps(self.MANIFEST))

    def test_plan_detail_is_none_before_the_gate_opens(self):
        self.write_manifest()
        self.assertIsNone(state_payload.build(self.dir)["detail"]["plan"])

    def test_plan_detail_appears_when_the_gate_is_open(self):
        self.write_manifest()
        run_state.mark(str(self.dir), "gate", "plan", "asked")
        plan = state_payload.build(self.dir)["detail"]["plan"]
        self.assertIsNotNone(plan)
        self.assertEqual(plan["account"], "Demo - JLS")

    def test_plan_core4_resolves_ids_to_products(self):
        self.write_manifest()
        run_state.mark(str(self.dir), "gate", "plan", "asked")
        core4 = state_payload.build(self.dir)["detail"]["plan"]["core4"]
        self.assertEqual([p["name"] for p in core4],
                         ["Beoplay H100", "Beosound A5",
                          "Beosound Explore", "Beoplay Eleven"])
        self.assertEqual(core4[0]["product_type"], "Over-Ear Headphones")

    def test_plan_orders_carry_shipments_and_product_names(self):
        self.write_manifest()
        run_state.mark(str(self.dir), "gate", "plan", "asked")
        orders = state_payload.build(self.dir)["detail"]["plan"]["orders"]
        self.assertEqual(orders[0]["products"], ["Beoplay Eleven"])
        self.assertEqual(orders[0]["shipments"][0]["scenario"], "happy")
        self.assertEqual(orders[0]["shipments"][0]["events"],
                         ["InTransit", "Delivered"])

    def test_plan_cdc_block_states_generation_is_off(self):
        self.write_manifest()
        run_state.mark(str(self.dir), "gate", "plan", "asked")
        cdc = state_payload.build(self.dir)["detail"]["plan"]["cdc"]
        self.assertEqual(cdc["region"], "UK")
        self.assertEqual(cdc["category"], "Electronics")
        self.assertEqual(cdc["config_source"], "none")
        self.assertFalse(cdc["generate_orders"])

    def test_plan_extras_are_flattened_field_by_field(self):
        """An auto-derived value the operator never saw is worse than one
        they rejected — so weights are listed per article, not summarised."""
        self.write_manifest()
        run_state.mark(str(self.dir), "gate", "plan", "asked")
        extras = state_payload.build(self.dir)["detail"]["plan"]["extras"]
        self.assertEqual(extras["gate_c"], "extras")
        labels = [row[0] for row in extras["fields"]]
        self.assertIn("Beoplay Eleven weight", labels)
        values = dict(extras["fields"])
        self.assertEqual(values["Beoplay Eleven weight"], "0.4 kg")

    def test_plan_detail_is_none_when_the_manifest_is_unreadable(self):
        run_state.mark(str(self.dir), "gate", "plan", "asked")
        self.assertIsNone(state_payload.build(self.dir)["detail"]["plan"])
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
python3 -m unittest tests.test_state_payload -v
```

Expected: FAIL — `KeyError: 'plan'` on `detail`.

- [ ] **Step 3: Implement the plan detail builder**

Add to `scripts/state_payload.py`:

```python
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
                       "events": s.get("events") or []}
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
```

In `build()`, compute the gates once and add the detail key. Replace `"gates": gate_states(state),` with a precomputed local, and add `"plan"` to the `detail` dict:

```python
    gates = gate_states(state)
```

then `"gates": gates,` in the returned dict, and inside the existing `"detail"` dict add:

```python
            "plan": _plan_detail(manifest, gates),
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python3 -m unittest tests.test_state_payload -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add plugins/pl-tools/scripts/state_payload.py \
        plugins/pl-tools/scripts/tests/test_state_payload.py
git commit -m "feat(state): expose plan-card detail once the plan gate opens"
```

---

### Task 5: The gate card UI

**Files:**
- Modify: `scripts/run_app_template.html`
- Test: `scripts/tests/test_run_server.py` (markup presence only — the behaviour is verified live in Step 6)

**Interfaces:**
- Consumes: `payload.gates` (Task 1), `payload.detail.plan` (Task 4), `POST /approve/<gate>` and `GET /template.html` (Task 3).
- Produces: no interface later tasks depend on.

- [ ] **Step 1: Write the failing test**

Add to `scripts/tests/test_run_server.py`, inside `TestRenderPage`:

```python
    def test_page_has_a_gate_card_container(self):
        html = run_server.render_page(self.dir, {"prospect_name": "Brand"})
        self.assertIn('id="gate-card"', html)
        self.assertIn("renderGate", html)
        self.assertIn("/approve/", html)
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
python3 -m unittest tests.test_run_server -v
```

Expected: FAIL — `'id="gate-card"' not found in html`.

- [ ] **Step 3: Add the container, then the renderer**

In `run_app_template.html`, immediately after the opening of `<section id="phase-building" hidden>`, insert the container so the gate sits above the lane pills:

```html
    <div id="gate-card" class="mb-6 hidden"></div>
```

Add this JS before `function renderBuilding(payload) {`:

```javascript
  // ---- Approval gates ----
  let gateSubmitting = false;

  const GATE_COPY = {
    template: {
      title: 'Template ready for review',
      blurb: 'This is the branded layout that every comm in this run will '
           + 'use. Approve it and it gets pushed and published.',
    },
    plan: {
      title: 'Plan ready for review',
      blurb: 'One yes covers all of it. Nothing has been sent to parcelLab '
           + 'yet.',
    },
  };

  function planTable(plan) {
    if (!plan) return '<p class="text-sm text-gray-400">Plan unavailable.</p>';
    const core = (plan.core4 || []).map((p) =>
      `<tr><td class="py-1 pr-4">${escapeHtml(p.name || '')}</td>
           <td class="py-1 pr-4 text-gray-500">${escapeHtml(p.product_type || '')}</td>
           <td class="py-1 text-gray-500">${escapeHtml(p.price || '')}</td></tr>`).join('');
    const orders = (plan.orders || []).map((o) => (o.shipments || []).map((s, i) =>
      `<tr><td class="py-1 pr-4">${i === 0 ? escapeHtml(o.label || '') : ''}</td>
           <td class="py-1 pr-4">${i === 0 ? escapeHtml((o.customer || {}).name || '') : ''}</td>
           <td class="py-1 pr-4">${i === 0 ? escapeHtml(o.fraud_level || '') : ''}</td>
           <td class="py-1 pr-4">${escapeHtml(s.label || '')}</td>
           <td class="py-1 pr-4">${escapeHtml(s.scenario || '')}</td>
           <td class="py-1 pr-4">${escapeHtml(s.courier || '')}</td>
           <td class="py-1 text-gray-500">${(s.events || []).map(escapeHtml).join(' → ')}</td>
       </tr>`).join('')).join('');
    const cdc = plan.cdc || {};
    const extras = plan.extras || {};
    const extraRows = (extras.fields || []).map(([label, value]) =>
      `<li>${escapeHtml(String(label))}: <span class="text-gray-500">${escapeHtml(String(value))}</span></li>`).join('');
    return `
      <div class="space-y-4 text-sm">
        <div>
          <p class="mb-1 text-xs font-semibold uppercase text-gray-400">Core 4</p>
          <table class="w-full text-left"><tbody>${core}</tbody></table>
        </div>
        <div>
          <p class="mb-1 text-xs font-semibold uppercase text-gray-400">Orders</p>
          <table class="w-full text-left"><tbody>${orders}</tbody></table>
        </div>
        <div>
          <p class="mb-1 text-xs font-semibold uppercase text-gray-400">CDC</p>
          <p class="text-gray-600">region ${escapeHtml(cdc.region || '')}
             · category ${escapeHtml(cdc.category || '')}
             · config ${escapeHtml(cdc.config_source === 'none' ? "caller's default" : (cdc.config_source || ''))}
             · synthetic generation: ${cdc.generate_orders ? 'ON' : 'off'}</p>
        </div>
        <div>
          <p class="mb-1 text-xs font-semibold uppercase text-gray-400">Enrichment (${escapeHtml(extras.gate_c || '')})</p>
          <ul class="list-disc pl-5 text-gray-600">${extraRows || '<li class="list-none text-gray-400">none</li>'}</ul>
        </div>
        <p class="text-xs text-gray-400">Account: ${escapeHtml(plan.account || '')}</p>
      </div>`;
  }

  function templatePreview() {
    return `
      <div class="mb-3">
        <div class="overflow-hidden rounded-md border border-gray-200 bg-white"
             style="height: 300px;">
          <iframe src="/template.html" title="Template preview"
                  style="width: 600px; height: 600px; border: 0;
                         transform: scale(0.5); transform-origin: top left;">
          </iframe>
        </div>
        <a href="/template.html" target="_blank" rel="noopener"
           class="mt-1.5 inline-block text-xs underline" style="color: var(--brand)">
          open full size ↗</a>
      </div>`;
  }

  function renderGate(payload) {
    const card = document.getElementById('gate-card');
    if (!card) return;
    const gates = payload.gates || {};
    const name = gates.template === 'open' ? 'template'
               : gates.plan === 'open' ? 'plan' : null;
    if (!name) {
      card.classList.add('hidden');
      card.innerHTML = '';
      gateSubmitting = false;
      return;
    }
    // Re-rendering while the operator is mid-note would wipe what they typed.
    if (card.dataset.gate === name && card.innerHTML) return;
    card.dataset.gate = name;
    const copy = GATE_COPY[name];
    card.innerHTML = `
      <div class="rounded-lg border-2 bg-white p-5 shadow-sm" style="border-color: var(--brand)">
        <p class="text-sm font-semibold text-gray-900">${escapeHtml(copy.title)}</p>
        <p class="mb-3 mt-0.5 text-xs text-gray-500">${escapeHtml(copy.blurb)}</p>
        ${name === 'template' ? templatePreview() : planTable((payload.detail || {}).plan)}
        <div id="gate-error" class="mb-2 hidden rounded-md bg-red-50 px-3 py-2 text-xs text-red-700"></div>
        <div class="flex items-center gap-2">
          <button type="button" id="gate-approve"
                  class="rounded-md px-4 py-2 text-sm font-semibold text-white shadow-sm submit-btn">Approve &amp; continue</button>
          <button type="button" id="gate-reject"
                  class="rounded-md border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700">Request changes</button>
        </div>
        <div id="gate-note-wrap" class="mt-3 hidden">
          <textarea id="gate-note" rows="3" placeholder="What needs changing?"
                    class="block w-full rounded-md border-0 px-3 py-1.5 text-sm text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 focus:ring-2"></textarea>
          <button type="button" id="gate-send"
                  class="mt-2 rounded-md border border-gray-300 px-3 py-1.5 text-sm font-medium text-gray-700">Send</button>
        </div>
      </div>`;
    document.getElementById('gate-approve').onclick =
      () => sendDecision(name, 'approved', null);
    document.getElementById('gate-reject').onclick = () => {
      document.getElementById('gate-note-wrap').classList.remove('hidden');
      document.getElementById('gate-note').focus();
    };
    document.getElementById('gate-send').onclick = () => {
      const note = document.getElementById('gate-note').value.trim();
      if (!note) {
        gateError('Say what needs changing so it can be acted on.');
        return;
      }
      sendDecision(name, 'changes_requested', note);
    };
  }

  function gateError(message) {
    const box = document.getElementById('gate-error');
    if (!box) return;
    box.textContent = message;
    box.classList.remove('hidden');
  }

  function sendDecision(gate, decision, note) {
    if (gateSubmitting) return;
    gateSubmitting = true;
    ['gate-approve', 'gate-reject', 'gate-send'].forEach((id) => {
      const el = document.getElementById(id);
      if (el) el.disabled = true;
    });
    const body = note === null ? {decision} : {decision, note};
    fetch('/approve/' + gate, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(body),
    }).then((r) => r.json().then((j) => ({ok: r.ok, j}))).then(({ok, j}) => {
      if (ok) return;                    // next poll clears the card
      throw new Error(j.error || 'could not send');
    }).catch((err) => {
      gateSubmitting = false;
      ['gate-approve', 'gate-reject', 'gate-send'].forEach((id) => {
        const el = document.getElementById(id);
        if (el) el.disabled = false;
      });
      gateError(String(err.message || err));
    });
  }
```

Call it from `renderBuilding(payload)` — add as the first line after the existing `document.title` block:

```javascript
    renderGate(payload);
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
python3 -m unittest tests.test_run_server -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add plugins/pl-tools/scripts/run_app_template.html \
        plugins/pl-tools/scripts/tests/test_run_server.py
git commit -m "feat(page): render approval gate cards with preview and plan"
```

---

### Task 6: Verify both gates live, end to end

**Files:**
- Create: throwaway fixture run dir under `/tmp` (not committed)
- Modify: nothing unless a defect is found

**Interfaces:**
- Consumes: everything from Tasks 1–5.
- Produces: nothing. This task's deliverable is evidence.

The page JS has no Python test hook, so it is verified by driving a real server — the same way the title/fraud/Live fixes were verified.

- [ ] **Step 1: Build a fixture run dir with the template gate open**

```bash
cd ~/Documents/Claude/Projects/parcellab-claude-skills/plugins/pl-tools/scripts
D=/tmp/gate-fixture && rm -rf "$D" && mkdir -p "$D/results" "$D/scrape" "$D/orders"
python3 -c "
import sys; sys.path.insert(0, '.')
import run_state
run_state.init('$D', 'brand-20260820-0900', 'retain', 'Demo - JLS')
open('$D/intake.json', 'w').write('{}')
run_state.mark('$D', 'gate', 'template', 'asked')
"
cp ~/parcellab-previews/bang-olufsen-parcellab-layout.html "$D/template-preview.html"
```

- [ ] **Step 2: Serve it and confirm the gate card and preview render**

Add a `gate-fixture` entry to `.claude/launch.json` via `ensure_launch_config.py` pointing `run_server.py` at `/tmp/gate-fixture` on a free port, `preview_start` it, then screenshot. Confirm: the gate card is above the lane pills, the scaled iframe shows the whole B&O email, and "open full size" opens it.

- [ ] **Step 3: Confirm approve writes the sentinel and the card clears**

Click **Approve & continue**, then:

```bash
cat /tmp/gate-fixture/template-approval.json
```

Expected: `{"decision": "approved", "note": null, "at": "..."}`. The card should disappear within one poll (2s) only after the conductor marks `answered` — so also confirm it *stays* until then, which is the correct behaviour.

- [ ] **Step 4: Confirm the plan gate renders and rejection carries a note**

```bash
D=/tmp/gate-fixture
python3 -c "
import sys; sys.path.insert(0, '.')
import run_state
run_state.mark('$D', 'gate', 'template', 'answered')
run_state.mark('$D', 'gate', 'plan', 'asked')
"
cp ~/parcellab-demo-runs/bang-olufsen-*/demo-manifest.json "$D/demo-manifest.json"
```

Reload. Confirm the plan card lists the core 4, the order/shipment matrix, the CDC block reading `synthetic generation: off`, and the account name. Click **Request changes**, type a note, send, then:

```bash
cat /tmp/gate-fixture/plan-approval.json
```

Expected `decision: "changes_requested"` with the typed note. Also confirm **Send** with an empty note shows the inline error and posts nothing.

- [ ] **Step 5: Confirm the 409 guard**

```bash
D=/tmp/gate-fixture
rm "$D/plan-approval.json"
python3 -c "
import sys; sys.path.insert(0, '.')
import run_state
run_state.mark('$D', 'gate', 'plan', 'answered')
"
curl -s -o /dev/null -w '%{http_code}\n' -X POST \
  -H 'Content-Type: application/json' -d '{"decision":"approved"}' \
  http://127.0.0.1:<port>/approve/plan
```

Expected: `409`, and no `plan-approval.json` recreated.

- [ ] **Step 6: Tear down and commit any fixes**

`preview_stop` the fixture server, `rm -rf /tmp/gate-fixture`, remove the `gate-fixture` launch entry. If Steps 2–5 found defects, fix them and commit:

```bash
git add plugins/pl-tools/scripts/
git commit -m "fix(page): address defects found verifying the gate cards live"
```

---

### Task 7: Rewire the conductor — `SKILL.md`

**Files:**
- Modify: `plugins/pl-tools/skills/demo-environment/SKILL.md` — Phase 0 step 8 (★), step 9 (✋), the auto-mode section, and the *Deviation logging* table row for `gate_reasked`
- Test: none (prose). Correctness is checked by the next real run.

**Interfaces:**
- Consumes: the routes and filenames from Task 3, the gate marks from Task 1.
- Produces: nothing further.

- [ ] **Step 1: Rewrite step 8 (★) to gate on the page**

Replace the "Show the template and get it approved" body so that it: copies the built HTML from `$HOME/parcellab-previews/{brand}-parcellab-layout.html` to `<run dir>/template-preview.html`; calls `mark(d, "gate", "template", "asked")`; posts **one** chat line naming what is waiting plus `run.page_url`; then waits for `<run dir>/template-approval.json` with a tracked background task:

```bash
until [ -f "<run dir>/template-approval.json" ]; do sleep 5; done
```

On `approved` → `mark(d, "gate", "template", "answered")` and continue to step 9. On `changes_requested` → read `note`, iterate on the file in chat, `rm` the approval file, `mark(asked)` again, and `add_deviation(d, "gate_reasked", ...)`.

Keep the existing rules verbatim: serve the actual current file before asking; skip the step entirely when the repeat-brand shortcut was taken; approval here covers the push.

- [ ] **Step 2: Rewrite step 9 (✋) the same way**

Replace "The plan is shown on the run page" with the accurate mechanism: `mark(d, "gate", "plan", "asked")` makes the page render the plan card from the manifest on its next poll; post one short chat line with the link; wait for `plan-approval.json`. Delete the sentence claiming the page already renders a plan card — it did not, which is why the 2026-08-19 run fell back to a chat table.

Keep the four post-approval actions unchanged: `mark(answered)`, re-validate without `--pre-gate`, no render step, open the telemetry row.

- [ ] **Step 3: Update the auto-mode section**

State that auto mode writes both approval files directly and never opens a page gate, with `asked`/`answered` still marked in immediate succession so telemetry is indistinguishable from a fast human yes.

- [ ] **Step 4: Update the fallback wording**

Both gates fall back to chat when the server is not running — the template as a Browser-pane preview, the plan as a markdown table — unchanged from today's posture.

- [ ] **Step 5: Commit**

```bash
git add plugins/pl-tools/skills/demo-environment/SKILL.md
git commit -m "docs(demo-environment): move both hard gates onto the run page"
```

---

## Self-Review

**Spec coverage:** §1 data flow → Tasks 1, 3. §1 gate derivation → Task 1. §1 approval files → Tasks 2, 3. §2 server routes + route table → Task 3. §2 `approval_schema` → Task 2. §2 409 + shared derivation → Task 3 (`load_state` rename is what lets the server reuse it). §3 page/gate card/preview/interaction → Task 5. §4 plan card contents → Task 4 (data) + Task 5 (rendering). §5 conductor + auto mode + fallback → Task 7. §6 testing → Tasks 1–5 unit tests + Task 6 live pass. §7 out of scope → nothing to build.

**Placeholder scan:** no TBDs. The one deliberate `<port>` in Task 6 Step 5 is a value only known at runtime, and Step 2 says where it comes from.

**Type consistency:** `gate_states(state) -> dict` used identically in Tasks 1, 3, 4. `parse_decision(raw_json) -> dict` defined in Task 2, called in Task 3. `APPROVAL_FILES` keys (`template`, `plan`) match `GATE_NAMES` in Task 1 and `GATE_COPY` in Task 5. `detail.plan` keys produced in Task 4 (`core4`, `orders`, `cdc`, `extras`, `account`) are exactly the keys read by `planTable` in Task 5. `load_state` is renamed in Task 3 and used there only.
