# demo-environment Defect Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix four defects exposed by run `uniqlo-20260811-1913` — a silent HTML-breaking bug in branded-template, an undocumented manifest rule, an unverifiable tracking write, and a comm-wait window that is too short.

**Architecture:** One new validator script turns branded-template's "remember to check" prose into a mechanical gate; the remaining three fixes are targeted edits to skill instructions, each carrying the live evidence that justifies it.

**Tech Stack:** Python 3 (stdlib only), Markdown skill documents.

**Spec:** `docs/superpowers/specs/2026-08-11-demo-environment-live-visibility-and-telemetry-design.md` (Part D, items 2–5)

## Global Constraints

- Tests use **stdlib `unittest` only — never pytest**. The repo has no pytest dependency.
- Scripts live in `plugins/pl-tools/scripts/`; tests in `plugins/pl-tools/scripts/tests/test_<name>.py`.
- Run tests from `plugins/pl-tools/scripts/` as `python3 -m unittest tests.test_<module> < /dev/null`. **Never run bare `python3 -m unittest discover`** — it imports `test_pl_credentials`, which prompts interactively for a token and hangs the run.
- **No version bump on release.** `pl-tools` has no `version` field by design; it is SHA-versioned. Releasing is: commit, push to `main`, tell the team to run `/pl-update`.
- **Never rename any `parcellab-*` string** listed under *"Renaming things — read this first"* in the root README. Several belong to the org's plugin, an external repo, or real files on disk, and renaming them fails silently.
- Work on `main`.
- **The repo owner's standing rule: do not run `git commit` until he has explicitly said he is happy.** Each task's commit step therefore means: `git add` the files, show him `git diff --staged`, and commit only on his go-ahead.

---

### Task 1: Layout HTML validator

The bug this prevents: branded-template Step 7 substituted the scraped
`FONT_STACK` value `"Segoe UI", "Helvetica Neue", Helvetica, Arial, sans-serif`
into `style="…"` attributes. The first `"` **closes the attribute early**, so the
content card, CTA and footer silently lost their styling — the preview rendered a
default-blue link on a black button. Both greps Step 7 already mandates passed.
This task replaces that unreliable prose check with a script.

**Files:**
- Create: `plugins/pl-tools/scripts/check_layout_html.py`
- Test: `plugins/pl-tools/scripts/tests/test_check_layout_html.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: CLI `python3 check_layout_html.py <path-to-html>` → exit `0` when clean, exit `1` with one `PROBLEM: <detail>` line per issue on stdout. Task 2 wires this into the skill.

- [ ] **Step 1: Write the failing test**

Create `plugins/pl-tools/scripts/tests/test_check_layout_html.py`:

```python
"""Unit tests for check_layout_html. Stdlib unittest — no pytest."""
import pathlib
import subprocess
import sys
import tempfile
import unittest

SCRIPT = pathlib.Path(__file__).resolve().parent.parent / "check_layout_html.py"

PL_TOKENS = (
    "{{content}}{{preview}}{{schemaOrgMarkup}}"
    "{{generated/campaignManager/banner}}"
    "{{generated/campaignManager/html}}"
    "{{generated/campaignManager/productRecommendation}}"
)


def build(body):
    """A minimal but structurally valid layout carrying every required token."""
    return (
        "<!doctype html><html><body>"
        + PL_TOKENS
        + body
        + "</body></html>"
    )


def run(html):
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as fh:
        fh.write(html)
        path = fh.name
    return subprocess.run(
        [sys.executable, str(SCRIPT), path],
        capture_output=True, text=True,
    )


class TestCheckLayoutHtml(unittest.TestCase):
    def test_clean_layout_passes(self):
        r = run(build('<table><tr><td style="color:#000000;">hi</td></tr></table>'))
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_double_quote_inside_style_attribute_fails(self):
        # The live 2026-08-11 bug: a quoted font family closes the attribute.
        bad = ('<table><tr><td style="font-family:"Segoe UI", Arial; '
               'color:#000000;">hi</td></tr></table>')
        r = run(build(bad))
        self.assertEqual(r.returncode, 1)
        self.assertIn("style attribute", r.stdout)

    def test_leftover_brand_token_fails(self):
        r = run(build('<table><tr><td style="color:__BRAND_TEXT_PRIMARY__;">'
                      'hi</td></tr></table>'))
        self.assertEqual(r.returncode, 1)
        self.assertIn("__BRAND_", r.stdout)

    def test_missing_parcellab_token_fails(self):
        html = ("<!doctype html><html><body>{{preview}}"
                "<table><tr><td>hi</td></tr></table></body></html>")
        r = run(html)
        self.assertEqual(r.returncode, 1)
        self.assertIn("{{content}}", r.stdout)

    def test_unbalanced_tags_fail(self):
        r = run(build("<table><tr><td>hi</td></tr>"))
        self.assertEqual(r.returncode, 1)
        self.assertIn("table", r.stdout)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd plugins/pl-tools/scripts && python3 -m unittest tests.test_check_layout_html < /dev/null
```

Expected: errors — `check_layout_html.py` does not exist yet.

- [ ] **Step 3: Write the implementation**

Create `plugins/pl-tools/scripts/check_layout_html.py`:

```python
#!/usr/bin/env python3
"""Validate a built branded-template layout before it is pushed to parcelLab.

Catches the failure modes that browsers silently auto-correct, so the preview
looks perfect while broken markup is what reaches parcelLab.
"""
import pathlib
import re
import sys

REQUIRED_TOKENS = [
    "{{content}}",
    "{{preview}}",
    "{{schemaOrgMarkup}}",
    "{{generated/campaignManager/banner}}",
    "{{generated/campaignManager/html}}",
    "{{generated/campaignManager/productRecommendation}}",
]
BALANCED_TAGS = ["table", "tr", "td"]


def check(html):
    """Return a list of problem strings. Empty list means the layout is clean."""
    problems = []

    for token in REQUIRED_TOKENS:
        if token not in html:
            problems.append(f"required parcelLab token missing: {token}")

    for leftover in sorted(set(re.findall(r"__BRAND_[A-Z_]*__", html))):
        problems.append(f"unsubstituted token left in output: {leftover}")

    # A double quote inside a style="..." value closes the attribute early.
    # In well-formed markup the character after the closing quote is
    # whitespace, '>' or '/'. Anything else means the attribute ended where
    # it should not have.
    for match in re.finditer(r'style="', html):
        end = html.find('"', match.end())
        if end == -1:
            problems.append("style attribute is never closed")
            continue
        following = html[end + 1:end + 2]
        if following and not following.isspace() and following not in ">/":
            snippet = html[match.start():end + 20].replace("\n", " ")
            problems.append(
                "style attribute closed early — a quoted value (usually the "
                f"font stack) terminated it: {snippet!r}"
            )

    for tag in BALANCED_TAGS:
        opens = len(re.findall(rf"<{tag}[ >]", html))
        closes = html.count(f"</{tag}>")
        if opens != closes:
            problems.append(
                f"unbalanced <{tag}>: {opens} opened, {closes} closed"
            )

    return problems


def main():
    if len(sys.argv) != 2:
        print("usage: check_layout_html.py <path-to-html>")
        return 1
    html = pathlib.Path(sys.argv[1]).read_text()
    problems = check(html)
    for problem in problems:
        print(f"PROBLEM: {problem}")
    if problems:
        return 1
    print("OK: layout is clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd plugins/pl-tools/scripts && python3 -m unittest tests.test_check_layout_html < /dev/null
```

Expected: `Ran 5 tests` … `OK`.

- [ ] **Step 5: Verify against the real layout from the live run**

```bash
python3 plugins/pl-tools/scripts/check_layout_html.py ~/parcellab-previews/uniqlo-parcellab-layout.html
```

Expected: `OK: layout is clean` — this is the corrected file. If `~/parcellab-previews/` no longer holds it, skip this step; the unit tests are authoritative.

- [ ] **Step 6: Stage and commit** (owner approval required — see Global Constraints)

```bash
git add plugins/pl-tools/scripts/check_layout_html.py plugins/pl-tools/scripts/tests/test_check_layout_html.py
git commit -m "feat(branded-template): mechanical layout HTML check before push"
```

---

### Task 2: Wire the validator into branded-template, and normalise quotes

**Files:**
- Modify: `plugins/pl-tools/skills/branded-template/SKILL.md` (Step 6 token table; Step 7 build rules)

**Interfaces:**
- Consumes: `check_layout_html.py` CLI from Task 1.
- Produces: nothing consumed by later tasks.

- [ ] **Step 1: Add the quote rule to the Step 6 token table**

In the Step 6 token table, replace the `FONT_STACK` row's rule with:

```markdown
| `FONT_STACK` | `bodyFont` — add `Helvetica, Arial, sans-serif` fallback. **Replace every double quote with a single quote** (`"Segoe UI"` → `'Segoe UI'`). Every token is substituted into `style="…"` attributes, and a double quote inside one closes the attribute early, silently breaking the content card, CTA and footer downstream. Live 2026-08-11: UNIQLO's stack shipped a blue default link on a black button, and both of Step 7's greps passed. |
```

- [ ] **Step 2: Add the general rule to Step 7's build rules**

Add as a new bullet in Step 7's "Key structural rules", immediately after the `{{preview}}` bullet:

```markdown
- **No substituted value may contain a double quote.** Every `__BRAND_*__` token lands inside a
  `style="…"` attribute, so one `"` in a value ends the attribute and everything after it becomes
  stray markup that browsers silently auto-correct in the preview. Normalise quotes to single
  quotes when building the substitution map — do not rely on spotting it in the render.
```

- [ ] **Step 3: Replace the manual check paragraph with the script**

In Step 7, replace the paragraph beginning **"Then check the markup is well-formed — the greps above do not."** with:

```markdown
**Then validate the built file mechanically — the greps above do not catch structural damage.**

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/check_layout_html.py \
  "$HOME/parcellab-previews/{brand-name-lowercase}-parcellab-layout.html"
```

Exit 0 means clean. Any `PROBLEM:` line must be fixed before Step 8 — a layout that fails this
check must never reach Step 9's push. The script checks all six parcelLab tokens are present, no
`__BRAND_` token survived, no `style="…"` attribute was closed early by a quoted value, and that
`<table>`/`<tr>`/`<td>` open and close counts match. Two of these were prose instructions that a
conductor passed while shipping broken markup (live 2026-08-11).
```

- [ ] **Step 4: Verify the instructions are followable as written**

```bash
grep -n "check_layout_html" plugins/pl-tools/skills/branded-template/SKILL.md
ls plugins/pl-tools/scripts/check_layout_html.py
```

Expected: the grep shows the invocation, and the referenced script exists at that path relative to `${CLAUDE_PLUGIN_ROOT}` (i.e. `plugins/pl-tools/scripts/`).

- [ ] **Step 5: Stage and commit** (owner approval required)

```bash
git add plugins/pl-tools/skills/branded-template/SKILL.md
git commit -m "fix(branded-template): normalise quotes in tokens, validate built HTML mechanically"
```

---

### Task 3: order-lifecycle — tracking verification and the comm window

**Files:**
- Modify: `plugins/pl-tools/skills/order-lifecycle/SKILL.md` (*Order + tracking setup* section; *Reporting* section)

**Interfaces:**
- Consumes: nothing.
- Produces: nothing consumed by later tasks.

- [ ] **Step 1: Document how to verify tracking actually attached**

In *Order + tracking setup (before the event loop)*, immediately after item 2 (`add_tracking`), add:

```markdown
   **Verify attachment — the PUT response cannot tell you.** The response echoes the request
   payload and carries no `trackings` field, so a successful write looks identical to a no-op.
   Confirm with a read instead, once per tracking number:

   ```bash
   parcellab track tracking list --account <ACCOUNT_ID> --tracking-number <TN> -o json \
     --jmes 'results[].{tn:trackingNumber,c:courier}'
   ```

   One entry per parcel means attached. **Never re-send the `add_tracking` PUT to find out** —
   live 2026-08-11 a conductor did exactly that as a diagnostic, which is an avoidable duplicate
   write against a live account. (It happened not to duplicate the tracking; that is luck, not a
   guarantee.)
```

- [ ] **Step 2: Correct the comm-wait window**

In *Reporting*, replace the paragraph starting **"Wait at least 5 minutes after the final event…"** with:

```markdown
**Wait at least 15 minutes after the final event before treating a missing comm as a problem.**
Comms do not arrive at a uniform lag. Measured live on account 1626718 (2026-08-11, three orders,
four parcels): order confirmation, dispatch and out-for-delivery comms each landed within ~3–4
minutes of their event; `package_delivered_*` landed in 3–4 minutes on single-parcel orders but
took **over 10 minutes** on one parcel of a split order. At the 6-minute mark that run looked like
a broken delivered trigger and was reported to the user as a possible defect, with a
plausible-but-wrong hypothesis attached (that split orders withhold the delivered comm until every
parcel lands). The comm then arrived and disproved it. Wait the full window before forming — let
alone reporting — a theory.
```

- [ ] **Step 3: Verify both edits landed and nothing else changed**

```bash
git diff --stat plugins/pl-tools/skills/order-lifecycle/SKILL.md
grep -n "15 minutes\|track tracking list" plugins/pl-tools/skills/order-lifecycle/SKILL.md
```

Expected: one file changed; both greps hit.

- [ ] **Step 4: Confirm the existing shell tests still pass**

```bash
bash plugins/pl-tools/skills/order-lifecycle/references/tests/test-run-lifecycle.sh
```

Expected: passes. (This task changes documentation only, so a failure here is pre-existing — record it and carry on rather than fixing unrelated breakage.)

- [ ] **Step 5: Stage and commit** (owner approval required)

```bash
git add plugins/pl-tools/skills/order-lifecycle/SKILL.md
git commit -m "fix(order-lifecycle): verify tracking attachment by read; comm window 5 -> 15 min"
```

---

### Task 4: demo-environment — manifest ids and the Beat 2 window

**Files:**
- Modify: `plugins/pl-tools/skills/demo-environment/SKILL.md` (Phase 0 step 9 manifest schema; Phase 4 Beat 2)

**Interfaces:**
- Consumes: nothing.
- Produces: nothing consumed by later tasks.

- [ ] **Step 1: State the id rule in the manifest schema**

In Phase 0 step 9, replace `` `products[]`, `selection{core4,shopify_extra}` `` with:

```markdown
`products[]` (each entry in scrape shape, carrying its own `id` and `sku`),
`selection{core4,shopify_extra}` — **these hold product `id` values, not SKUs, and so do every
order's `products` and each shipment's `products`.** A product's `id` is its goods code
(`E491096-000`); its `sku` is the variant (`E491096-000-57`). Payload files use SKUs for
`line_item_id`; the manifest never does. `validate_manifest.py` rejects SKUs with
`unknown product <sku>`, which cost a full validate-fix-revalidate cycle live on 2026-08-11
because the rule existed only in the validator,
```

- [ ] **Step 2: Correct the Beat 2 wait in the demo-environment skill**

In Phase 4, replace **"(after each order's driver finishes AND ≥5 minutes after its final event — comms lag, delivered comms the longest)"** with:

```markdown
(after each order's driver finishes AND **≥15 minutes** after its final event — comms lag, and
delivered comms the longest: measured 2026-08-11 at 3–4 minutes on single-parcel orders but over
10 minutes on a split order's parcel. Reporting at 6 minutes produced a wrong defect hypothesis in
front of the user.)
```

- [ ] **Step 3: Verify the manifest rule is now stated where a conductor will read it**

```bash
grep -n "not SKUs" plugins/pl-tools/skills/demo-environment/SKILL.md
grep -n "15 minutes" plugins/pl-tools/skills/demo-environment/SKILL.md
```

Expected: both hit.

- [ ] **Step 4: Confirm the validator still agrees with the documented rule**

```bash
cd plugins/pl-tools/scripts && python3 -m unittest tests.test_validate_manifest < /dev/null
```

Expected: `Ran 21 tests` … `OK`. The documentation now matches what the validator already enforced.

- [ ] **Step 5: Stage and commit** (owner approval required)

```bash
git add plugins/pl-tools/skills/demo-environment/SKILL.md
git commit -m "fix(demo-environment): document product-id rule; Beat 2 window 5 -> 15 min"
```
