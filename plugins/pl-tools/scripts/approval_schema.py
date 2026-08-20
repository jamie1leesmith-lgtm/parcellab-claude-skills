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
