# demo-environment Intake Questionnaire + parcelLab Branding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `pl-tools:demo-environment`'s sequential chat intake with a
single up-front Browser-pane questionnaire, collapse "auto mode" down to
"gates auto-approve," and give the questionnaire and run-page artifact real
parcelLab branding.

**Architecture:** Two new pure-function/CLI Python modules
(`pl_brand.py` for static brand tokens, `render_intake_questionnaire.py`
for the questionnaire's HTML render + answer parsing) alongside the
existing `render_run_page.py`/`run_state.py`/`validate_manifest.py`
scripts in `plugins/pl-tools/scripts/`, following that directory's existing
conventions exactly (stdlib `unittest`, plain sibling-module imports, a
CLI `main()` per script). `render_run_page.py` gets restyled in place using
the new brand tokens. `resolve_auto_defaults.py` and `validate_manifest.py`
lose their now-dead answers-doc support. `SKILL.md` and
`intake-script.md` get rewritten to describe the new flow.

**Tech Stack:** Python 3 stdlib only (`json`, `argparse`, `pathlib`, `html`,
`re`), stdlib `unittest` for tests, no new dependencies.

**Spec:** [docs/superpowers/specs/2026-08-19-demo-environment-intake-questionnaire-design.md](../specs/2026-08-19-demo-environment-intake-questionnaire-design.md)

## Global Constraints

- Tests are stdlib `unittest` only — `pytest` is not installed, never `pip install` it.
- Test invocation: `cd plugins/pl-tools/scripts && python3 -m unittest discover -s tests -v`.
- Every script lives in `plugins/pl-tools/scripts/`; cross-script imports use the plain sibling-module convention (`import run_state`, `import pl_brand`) — never reference `${CLAUDE_PLUGIN_ROOT}` from inside a `.py` file, that variable only matters in SKILL.md's bash snippets.
- Every test file inserts the scripts directory onto `sys.path` before importing the module under test: `sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))`.
- HTML-escape all interpolated text through `render_run_page.e()` (or an equivalent local helper) — never interpolate raw strings into HTML.
- No manifest schema change: questionnaire answers land in exactly the fields Round 1/2 already write today (`path`, `brand.category` [now always-silent], `run.mode`, `gates.order_lifecycle.gate_c`).
- The answers-doc mechanism (`run.answers_doc`, `resolve_auto_defaults.py --answers-doc-file`) is removed entirely — confirmed with the user 2026-08-19: every run now requires a human to fill the questionnaire and pick a mode; there is no fully-doc-driven unattended path.
- Gate C's per-field extras detail (promise dates, order financials, article physical data values, delivery detail, tags/custom fields, dynamic recipients, extra articles) stays a **live chat interaction** when `gate_c == "extras"`, exactly as order-lifecycle's Gate C works today — the questionnaire only captures the `send-as-is` vs `extras` toggle. This is a deliberate scope line: those per-field values depend on schema owned by `order-lifecycle`, which this plan does not touch (spec non-goal).

---

## File Structure

| File | Responsibility |
|---|---|
| `plugins/pl-tools/scripts/pl_brand.py` (new) | Static parcelLab brand tokens: colors, font, Google Fonts link, logo SVG. |
| `plugins/pl-tools/scripts/tests/test_pl_brand.py` (new) | Sanity-checks the tokens (format, logo recoloring). |
| `plugins/pl-tools/scripts/render_intake_questionnaire.py` (new) | Renders the questionnaire HTML; parses the submitted answers JSON; CLI (`render` / `parse` subcommands). |
| `plugins/pl-tools/scripts/tests/test_render_intake_questionnaire.py` (new) | Tests for both the render and parse halves, plus the CLI. |
| `plugins/pl-tools/scripts/render_run_page.py` (modify) | Import `pl_brand`, restyle `CSS`, add a parcelLab header to `render()`. |
| `plugins/pl-tools/scripts/tests/test_render_run_page.py` (modify) | Add brand-token assertions; fix any assertions pinned to the old hardcoded hex values. |
| `plugins/pl-tools/scripts/resolve_auto_defaults.py` (modify) | Remove answers-doc merge support (`answers_doc` param, `--answers-doc-file`, `_ignored_doc_keys`, `_NEVER_ASK_FIELDS`). |
| `plugins/pl-tools/scripts/tests/test_resolve_auto_defaults.py` (modify) | Remove doc-override tests; update call sites to the new 2-arg signature. |
| `plugins/pl-tools/scripts/validate_manifest.py` (modify) | Remove the `run.answers_doc` validation block. |
| `plugins/pl-tools/scripts/tests/test_validate_manifest.py` (modify) | Remove the `run.answers_doc` test case(s). |
| `plugins/pl-tools/skills/demo-environment/SKILL.md` (modify) | Replace "Mode selection" + Phase 0 steps 2–4 with the questionnaire flow; drop Q5's live-question carve-out (two spots); drop the answers-doc manifest field. |
| `plugins/pl-tools/skills/demo-environment/references/intake-script.md` (modify) | Restructure away from Round 1/Round 2 chat framing into questionnaire fields / always-silent fields / pre-flight checks; category joins the always-silent table. |

---

### Task 1: `pl_brand.py` — static brand tokens

**Files:**
- Create: `plugins/pl-tools/scripts/pl_brand.py`
- Test: `plugins/pl-tools/scripts/tests/test_pl_brand.py`

**Interfaces:**
- Produces: `pl_brand.PRIMARY` (str, `#RRGGBB`), `pl_brand.TEXT` (str), `pl_brand.TINT` (str), `pl_brand.CARD` (str), `pl_brand.FONT_FAMILY` (str, CSS `font-family` value), `pl_brand.GOOGLE_FONTS_LINK` (str, HTML `<link>` tags), `pl_brand.LOGO_SVG` (str, a complete `<svg>...</svg>` markup using `fill="currentColor"`). Tasks 2 and 4 consume all of these.

- [ ] **Step 1: Write the failing test**

```python
# plugins/pl-tools/scripts/tests/test_pl_brand.py
"""Stdlib unittest — no pytest."""
import pathlib
import re
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import pl_brand

HEX_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


class BrandTokenTests(unittest.TestCase):
    def test_colors_are_hex(self):
        for token in (pl_brand.PRIMARY, pl_brand.TEXT, pl_brand.TINT, pl_brand.CARD):
            self.assertRegex(token, HEX_RE)

    def test_primary_is_the_parcellab_indigo(self):
        self.assertEqual(pl_brand.PRIMARY, "#3E39D3")

    def test_font_family_names_poppins(self):
        self.assertIn("Poppins", pl_brand.FONT_FAMILY)

    def test_google_fonts_link_loads_poppins(self):
        self.assertIn("fonts.googleapis.com", pl_brand.GOOGLE_FONTS_LINK)
        self.assertIn("Poppins", pl_brand.GOOGLE_FONTS_LINK)

    def test_logo_svg_is_recolorable(self):
        self.assertTrue(pl_brand.LOGO_SVG.strip().startswith("<svg"))
        self.assertIn("currentColor", pl_brand.LOGO_SVG)
        self.assertNotIn('fill="black"', pl_brand.LOGO_SVG)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd plugins/pl-tools/scripts && python3 -m unittest tests.test_pl_brand -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pl_brand'`

- [ ] **Step 3: Write the module**

```python
# plugins/pl-tools/scripts/pl_brand.py
"""parcelLab's own brand tokens.

Static, not scraped: unlike a customer's brand (fetched fresh per run by
branded-template because the customer's site changes), parcelLab's own
identity doesn't change per run, so it's authored once here instead.
Values pulled live from parcellab.com 2026-08-19.
"""

PRIMARY = "#3E39D3"
TEXT = "#1A1A1A"
TINT = "#F1F1FC"
CARD = "#F5F5F5"

FONT_FAMILY = "'Poppins', system-ui, sans-serif"

GOOGLE_FONTS_LINK = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
    'family=Poppins:wght@400;500;600;700&display=swap">'
)

# The parcelLab wordmark, single-color in the source (fill="black"),
# recolored to currentColor so it follows whatever text color the page
# gives it instead of needing separate light/dark asset variants.
LOGO_SVG = """<svg width="144" height="48" viewBox="0 0 144 48" fill="none" xmlns="http://www.w3.org/2000/svg">
<path d="M9.63664 34.4114V16.6758L4.68066 19.5503V37.1774L16.2446 43.9029V38.2351L9.63664 34.4114Z" fill="currentColor"/>
<path fill-rule="evenodd" clip-rule="evenodd" d="M23.4037 8.67578L11.2891 15.7266V33.4623L16.2451 36.3368V19.3877L22.5777 23.0758V30.1809L17.8971 27.4419V33.1096L23.4037 36.3097L35.5183 29.2588V15.6995L23.4037 8.67578ZM17.1261 18.0046L23.4037 14.3436L29.6812 18.0046L23.4037 21.6656L17.1261 18.0046ZM30.5623 26.4928L24.2297 30.1809V23.0758L30.5623 19.3877V26.4928Z" fill="currentColor"/>
<path d="M101.35 14.6445V29.2886H98.9814V14.6445H101.35Z" fill="currentColor"/>
<path d="M75.083 24.2455C75.083 21.3166 77.2857 18.9844 80.452 18.9844C82.9851 18.9844 85.3253 20.7742 85.6007 23.3505H83.2879C82.9851 22.0488 81.8012 21.1539 80.452 21.1539C78.6348 21.1539 77.4509 22.5098 77.4509 24.2455C77.4509 25.981 78.6073 27.3098 80.452 27.3098C81.8012 27.337 82.9851 26.4149 83.2879 25.1132H85.6007C85.3253 27.7166 82.9851 29.4793 80.452 29.4793C77.2857 29.4793 75.083 27.1472 75.083 24.2455Z" fill="currentColor"/>
<path fill-rule="evenodd" clip-rule="evenodd" d="M65.3082 19.1985V29.2867H62.9404V27.9308C62.0869 28.9342 60.8478 29.5037 59.4987 29.5037C56.6903 29.5037 54.5703 27.3612 54.5703 24.2697C54.5703 21.1782 56.6903 19.0087 59.4987 19.0087C60.8204 18.9816 62.0869 19.551 62.9404 20.5816V19.2257L65.3082 19.1985ZM62.9404 24.2426C62.9404 22.507 61.6739 21.124 59.9393 21.124C58.2047 21.124 57.0208 22.507 57.0208 24.2426C57.0208 25.9782 58.2322 27.3342 59.9393 27.3342C61.6463 27.3342 62.9404 25.9782 62.9404 24.2426Z" fill="currentColor"/>
<path fill-rule="evenodd" clip-rule="evenodd" d="M53.4146 24.2455C53.4146 27.3371 51.2944 29.5066 48.4861 29.5066C47.1645 29.5337 45.898 28.9642 45.072 27.9608V34.1982H42.7041V19.2287H45.072V20.5846C45.9255 19.5812 47.1645 19.0117 48.5136 19.0117C51.322 19.0117 53.4146 21.1541 53.4146 24.2455ZM50.9917 24.2455C50.9917 22.5371 49.7802 21.1541 48.0456 21.1541C46.311 21.1541 45.072 22.51 45.072 24.2455C45.072 25.9812 46.3386 27.3642 48.0732 27.3642C49.8077 27.3642 50.9917 25.9812 50.9917 24.2455Z" fill="currentColor"/>
<path d="M74.6151 21.5066V19.0117C72.8255 19.0117 71.2561 19.6354 70.1823 20.9371V19.2015H67.8145V29.2897H70.1823V25.1676C70.1823 22.5914 71.7517 21.2355 74.6151 21.5066Z" fill="currentColor"/>
<path fill-rule="evenodd" clip-rule="evenodd" d="M89.0147 25.059H96.9722C97.4395 21.4251 95.072 19.0115 91.8782 18.9844C88.8771 18.9844 86.7295 21.3438 86.7295 24.2455C86.7295 27.1472 88.7669 29.4793 92.1535 29.4793C94.3011 29.4793 96.2008 28.1234 96.8619 26.1166H94.5488C94.0532 27.0387 93.1447 27.4725 92.0433 27.4725C90.5565 27.5267 89.2625 26.4963 89.0147 25.059ZM94.6865 23.3234H89.0698C89.3451 21.9403 90.5841 20.9641 91.9883 21.0183C93.3649 20.9912 94.5214 21.9946 94.6865 23.3234Z" fill="currentColor"/>
<path d="M112.527 29.2886V27.1191H106.526V14.6445H104.158V29.2886H112.527Z" fill="currentColor"/>
<path fill-rule="evenodd" clip-rule="evenodd" d="M123.596 19.1985V29.2867H121.228V27.9308C120.375 28.9342 119.136 29.5037 117.786 29.5037C114.978 29.5037 112.858 27.3612 112.858 24.2697C112.858 21.1782 114.978 19.0087 117.786 19.0087C119.109 18.9816 120.375 19.551 121.228 20.5816V19.2257L123.596 19.1985ZM121.201 24.2426C121.201 22.507 119.934 21.124 118.199 21.124C116.465 21.124 115.281 22.507 115.281 24.2426C115.281 25.9782 116.493 27.3342 118.227 27.3342C119.962 27.3342 121.201 25.9782 121.201 24.2426Z" fill="currentColor"/>
<path fill-rule="evenodd" clip-rule="evenodd" d="M131.911 29.5058C134.719 29.5058 136.84 27.3363 136.84 24.2447C136.84 21.1532 134.719 19.0109 131.911 19.038C130.59 19.0109 129.323 19.5804 128.47 20.6108V14.6719H126.102V29.3159H128.47V27.9329C129.295 28.9363 130.563 29.5329 131.911 29.5058ZM131.471 21.1532C133.206 21.1532 134.417 22.5363 134.417 24.2447C134.417 25.9804 133.233 27.3634 131.498 27.3634C129.764 27.3634 128.497 25.9804 128.497 24.2447C128.497 22.5091 129.737 21.1532 131.471 21.1532Z" fill="currentColor"/>
<path fill-rule="evenodd" clip-rule="evenodd" d="M137.804 16.9791H138.162V16.3554H138.327C138.52 16.3554 138.602 16.4368 138.63 16.5995C138.657 16.7893 138.685 16.9249 138.74 16.9791H139.125C139.098 16.9249 139.07 16.8436 139.015 16.5995C138.96 16.3826 138.878 16.2741 138.74 16.2198V16.1927C138.905 16.1384 139.043 16.0029 139.043 15.8402C139.043 15.7045 138.988 15.569 138.905 15.5147C138.795 15.4605 138.657 15.4062 138.382 15.4062C138.135 15.4062 137.941 15.4334 137.804 15.4605V16.9791ZM138.354 16.1114H138.189V15.6774C138.217 15.6503 138.299 15.6504 138.382 15.6504C138.602 15.6504 138.712 15.7588 138.712 15.8944C138.712 16.0571 138.547 16.1114 138.354 16.1114Z" fill="currentColor"/>
<path fill-rule="evenodd" clip-rule="evenodd" d="M138.409 17.7089C139.29 17.7089 139.978 17.0309 139.978 16.1632C139.978 15.3225 139.29 14.6445 138.409 14.6445C137.528 14.6445 136.84 15.3225 136.84 16.1632C136.84 17.0309 137.528 17.7089 138.409 17.7089ZM138.409 17.3835C137.721 17.3835 137.225 16.8411 137.225 16.1632C137.225 15.5123 137.748 14.9428 138.409 14.9428C139.07 14.9428 139.566 15.4852 139.566 16.1632C139.566 16.8411 139.07 17.3835 138.409 17.3835Z" fill="currentColor"/>
</svg>"""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd plugins/pl-tools/scripts && python3 -m unittest tests.test_pl_brand -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add plugins/pl-tools/scripts/pl_brand.py plugins/pl-tools/scripts/tests/test_pl_brand.py
git commit -m "feat(demo-environment): add static parcelLab brand tokens"
```

---

### Task 2: `render_intake_questionnaire.py` — render half

**Files:**
- Create: `plugins/pl-tools/scripts/render_intake_questionnaire.py`
- Test: `plugins/pl-tools/scripts/tests/test_render_intake_questionnaire.py`

**Interfaces:**
- Consumes: `pl_brand.PRIMARY`, `pl_brand.FONT_FAMILY`, `pl_brand.GOOGLE_FONTS_LINK`, `pl_brand.LOGO_SVG`, `pl_brand.TINT`, `pl_brand.CARD` (Task 1).
- Produces: `render_intake_questionnaire.DEFAULT_MATRIX` (list of `{"label": str, "fraud": str, "scenario": str}`, 5 entries), `render_intake_questionnaire.FRAUD_LEVELS` (`{"low","medium","high"}`), `render_intake_questionnaire.SCENARIOS` (`{"happy","split","recovered","manual_return","return_tracking","stuck-delay","locker","custom"}`), `render_intake_questionnaire.render(prospect_name, reuse_candidate=None)` → `str` (complete self-contained HTML). Task 3 consumes `DEFAULT_MATRIX`, `FRAUD_LEVELS`, `SCENARIOS` for `parse_answers`. Task 6 (SKILL.md) documents calling `render()` via this file's CLI.

- [ ] **Step 1: Write the failing tests**

```python
# plugins/pl-tools/scripts/tests/test_render_intake_questionnaire.py
"""Stdlib unittest — no pytest."""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import pl_brand
import render_intake_questionnaire as riq


class RenderTests(unittest.TestCase):
    def test_includes_shopify_question(self):
        html = riq.render("Acme")
        self.assertIn('name="shopify_opp"', html)
        self.assertIn('value="yes"', html)
        self.assertIn('value="no"', html)

    def test_omits_reuse_question_without_a_candidate(self):
        html = riq.render("Acme")
        self.assertNotIn('name="reuse_pool"', html)

    def test_includes_reuse_question_with_a_candidate(self):
        html = riq.render("Acme", reuse_candidate="2026-08-10")
        self.assertIn('name="reuse_pool"', html)
        self.assertIn("2026-08-10", html)

    def test_includes_every_default_matrix_row(self):
        html = riq.render("Acme")
        for row in riq.DEFAULT_MATRIX:
            self.assertIn(row["label"], html)

    def test_includes_gate_c_toggle(self):
        html = riq.render("Acme")
        self.assertIn('name="gate_c"', html)
        self.assertIn('value="send-as-is"', html)
        self.assertIn('value="extras"', html)

    def test_includes_mode_selector(self):
        html = riq.render("Acme")
        self.assertIn('name="mode"', html)
        self.assertIn('value="babysit"', html)
        self.assertIn('value="auto"', html)

    def test_escapes_the_prospect_name(self):
        html = riq.render('<script>alert(1)</script>')
        self.assertNotIn('<script>alert(1)</script>', html)

    def test_includes_brand_tokens(self):
        html = riq.render("Acme")
        self.assertIn(pl_brand.PRIMARY, html)
        self.assertIn("Poppins", html)
        self.assertIn("<svg", html)

    def test_has_a_submit_answers_json_target(self):
        html = riq.render("Acme")
        self.assertIn('id="answers-json"', html)
        self.assertIn('id="submitted-banner"', html)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd plugins/pl-tools/scripts && python3 -m unittest tests.test_render_intake_questionnaire -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'render_intake_questionnaire'`

- [ ] **Step 3: Write the render implementation**

```python
# plugins/pl-tools/scripts/render_intake_questionnaire.py
"""Render the demo-environment intake questionnaire and parse its answers.

Replaces the sequential Round 1/2 chat interview with a single up-front
form: the conductor publishes render()'s output as an Artifact, opens it
in the Browser pane, waits for submission, then extracts the JSON blob
the page writes into #answers-json and runs it through parse_answers().
"""
import argparse
import html as html_mod
import json
import pathlib
import sys

import pl_brand

DEFAULT_MATRIX = [
    {"label": "#1", "fraud": "low", "scenario": "happy"},
    {"label": "#2", "fraud": "medium", "scenario": "split"},
    {"label": "#3", "fraud": "high", "scenario": "recovered"},
    {"label": "#4", "fraud": "low", "scenario": "manual_return"},
    {"label": "#5", "fraud": "low", "scenario": "return_tracking"},
]

FRAUD_LEVELS = {"low", "medium", "high"}
SCENARIOS = {
    "happy", "split", "recovered", "manual_return", "return_tracking",
    "stuck-delay", "locker", "custom",
}
MODES = {"babysit", "auto"}
GATE_C_VALUES = {"send-as-is", "extras"}


def e(value):
    return html_mod.escape(str(value), quote=True)


def _matrix_rows():
    rows = []
    for row in DEFAULT_MATRIX:
        fraud_options = "".join(
            f'<option value="{e(level)}"{" selected" if level == row["fraud"] else ""}>{e(level)}</option>'
            for level in sorted(FRAUD_LEVELS)
        )
        scenario_options = "".join(
            f'<option value="{e(s)}"{" selected" if s == row["scenario"] else ""}>{e(s)}</option>'
            for s in sorted(SCENARIOS)
        )
        rows.append(
            f'<tr data-row="{e(row["label"])}">'
            f'<td><label><input type="checkbox" class="row-enabled" checked> {e(row["label"])}</label></td>'
            f'<td><select class="row-fraud">{fraud_options}</select></td>'
            f'<td><select class="row-scenario">{scenario_options}</select></td>'
            f"</tr>"
        )
    return "".join(rows)


def _reuse_question(reuse_candidate):
    if reuse_candidate is None:
        return ""
    return f"""
    <fieldset>
      <legend>Reuse the pool scraped on {e(reuse_candidate)}, or scrape fresh?</legend>
      <label><input type="radio" name="reuse_pool" value="reuse" checked> Reuse</label>
      <label><input type="radio" name="reuse_pool" value="fresh"> Scrape fresh</label>
    </fieldset>
    """


def render(prospect_name, reuse_candidate=None):
    """Return the complete questionnaire page as a self-contained HTML string."""
    return f"""<meta charset="utf-8">
{pl_brand.GOOGLE_FONTS_LINK}
<title>Demo intake — {e(prospect_name)}</title>
<style>
:root {{ --brand:{pl_brand.PRIMARY}; --fg:{pl_brand.TEXT}; --bg:#fff;
        --card:{pl_brand.CARD}; --tint:{pl_brand.TINT}; --line:#e2e2e8; }}
@media (prefers-color-scheme: dark) {{ :root {{ --fg:#eee; --bg:#111;
        --card:#1c1c22; --tint:#242235; --line:#2c2c34; }} }}
:root[data-theme="dark"] {{ --fg:#eee; --bg:#111; --card:#1c1c22;
        --tint:#242235; --line:#2c2c34; }}
:root[data-theme="light"] {{ --fg:{pl_brand.TEXT}; --bg:#fff; --card:{pl_brand.CARD};
        --tint:{pl_brand.TINT}; --line:#e2e2e8; }}
body {{ font:15px/1.6 {pl_brand.FONT_FAMILY}; color:var(--fg); background:var(--bg);
       max-width:760px; margin:0 auto; padding:32px 24px; }}
.pl-header {{ display:flex; align-items:center; gap:10px; color:var(--brand);
             margin-bottom:24px; }}
.pl-header svg {{ width:110px; height:auto; }}
h1 {{ font-size:20px; font-weight:600; }}
fieldset {{ border:1px solid var(--line); border-radius:10px; background:var(--card);
           padding:14px 18px; margin:0 0 18px; }}
legend {{ font-weight:600; padding:0 6px; }}
label {{ display:block; margin:6px 0; }}
table {{ border-collapse:collapse; width:100%; }}
td,th {{ text-align:left; padding:6px 8px; }}
button {{ background:var(--brand); color:#fff; border:none; border-radius:8px;
         padding:10px 22px; font:600 15px {pl_brand.FONT_FAMILY}; cursor:pointer; }}
#submitted-banner {{ display:none; background:var(--tint); color:var(--brand);
                     border-radius:10px; padding:14px 18px; font-weight:600; }}
#answers-json {{ display:none; }}
</style>
<div class="pl-header">{pl_brand.LOGO_SVG}<h1>Demo intake — {e(prospect_name)}</h1></div>
<form id="intake-form">
  <fieldset>
    <legend>Is this a Shopify opp?</legend>
    <label><input type="radio" name="shopify_opp" value="no" checked> No</label>
    <label><input type="radio" name="shopify_opp" value="yes"> Yes</label>
  </fieldset>
  {_reuse_question(reuse_candidate)}
  <fieldset>
    <legend>Order matrix</legend>
    <table>
      <tr><th>Order</th><th>Fraud</th><th>Scenario</th></tr>
      {_matrix_rows()}
    </table>
  </fieldset>
  <fieldset>
    <legend>Anything else to add to every order, or send as-is?</legend>
    <label><input type="radio" name="gate_c" value="send-as-is" checked> Send as-is</label>
    <label><input type="radio" name="gate_c" value="extras"> Add extras (asked in chat after this form)</label>
  </fieldset>
  <fieldset>
    <legend>Mode</legend>
    <label><input type="radio" name="mode" value="babysit" checked> Babysit — pause for approval at both gates</label>
    <label><input type="radio" name="mode" value="auto"> Auto — auto-approve both gates</label>
  </fieldset>
  <button type="submit">Submit</button>
</form>
<div id="submitted-banner">Submitted — you can return to the chat now.</div>
<pre id="answers-json"></pre>
<script>
document.getElementById('intake-form').addEventListener('submit', function (ev) {{
  ev.preventDefault();
  var form = ev.target;
  var rows = Array.from(form.querySelectorAll('tr[data-row]')).filter(function (tr) {{
    return tr.querySelector('.row-enabled').checked;
  }}).map(function (tr) {{
    return {{
      label: tr.getAttribute('data-row'),
      fraud: tr.querySelector('.row-fraud').value,
      scenario: tr.querySelector('.row-scenario').value
    }};
  }});
  var reuseInput = form.querySelector('input[name="reuse_pool"]:checked');
  var answers = {{
    shopify_opp: form.querySelector('input[name="shopify_opp"]:checked').value === 'yes',
    reuse_pool: reuseInput ? reuseInput.value === 'reuse' : null,
    order_matrix: rows,
    gate_c: form.querySelector('input[name="gate_c"]:checked').value,
    mode: form.querySelector('input[name="mode"]:checked').value
  }};
  document.getElementById('answers-json').textContent = JSON.stringify(answers);
  form.style.display = 'none';
  document.getElementById('submitted-banner').style.display = 'block';
}});
</script>"""


if __name__ == "__main__":
    pass  # main() is added in Task 3, once parsing exists too.
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd plugins/pl-tools/scripts && python3 -m unittest tests.test_render_intake_questionnaire -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add plugins/pl-tools/scripts/render_intake_questionnaire.py plugins/pl-tools/scripts/tests/test_render_intake_questionnaire.py
git commit -m "feat(demo-environment): render the intake questionnaire page"
```

---

### Task 3: `render_intake_questionnaire.py` — parse half + CLI

**Files:**
- Modify: `plugins/pl-tools/scripts/render_intake_questionnaire.py` (append `parse_answers` and `main`)
- Modify: `plugins/pl-tools/scripts/tests/test_render_intake_questionnaire.py` (append parse/CLI tests)

**Interfaces:**
- Consumes: `DEFAULT_MATRIX`, `FRAUD_LEVELS`, `SCENARIOS`, `MODES`, `GATE_C_VALUES` (this file, Task 2), `render()` (Task 2).
- Produces: `render_intake_questionnaire.parse_answers(raw_json: str) -> dict` — raises `ValueError` on any invalid/missing field, else returns `{"shopify_opp": bool, "reuse_pool": bool | None, "order_matrix": [{"label": str, "fraud": str, "scenario": str}, ...], "gate_c": str, "mode": str}`. `main(argv=None) -> int` — CLI with `render` and `parse` subcommands. Task 6 (SKILL.md) documents invoking both subcommands.

- [ ] **Step 1: Write the failing tests**

Append to `plugins/pl-tools/scripts/tests/test_render_intake_questionnaire.py`:

```python
import json
import subprocess
import tempfile


def _valid_answers(**overrides):
    base = {
        "shopify_opp": False,
        "reuse_pool": None,
        "order_matrix": [{"label": "#1", "fraud": "low", "scenario": "happy"}],
        "gate_c": "send-as-is",
        "mode": "babysit",
    }
    base.update(overrides)
    return json.dumps(base)


class ParseAnswersTests(unittest.TestCase):
    def test_valid_answers_round_trip(self):
        answers = riq.parse_answers(_valid_answers())
        self.assertEqual(answers["mode"], "babysit")
        self.assertEqual(answers["order_matrix"][0]["label"], "#1")

    def test_rejects_malformed_json(self):
        with self.assertRaises(ValueError):
            riq.parse_answers("not json")

    def test_rejects_missing_field(self):
        raw = json.loads(_valid_answers())
        del raw["mode"]
        with self.assertRaises(ValueError):
            riq.parse_answers(json.dumps(raw))

    def test_rejects_unknown_mode(self):
        with self.assertRaises(ValueError):
            riq.parse_answers(_valid_answers(mode="turbo"))

    def test_rejects_unknown_gate_c(self):
        with self.assertRaises(ValueError):
            riq.parse_answers(_valid_answers(gate_c="something-else"))

    def test_rejects_empty_order_matrix(self):
        with self.assertRaises(ValueError):
            riq.parse_answers(_valid_answers(order_matrix=[]))

    def test_rejects_unknown_fraud_level(self):
        with self.assertRaises(ValueError):
            riq.parse_answers(_valid_answers(
                order_matrix=[{"label": "#1", "fraud": "extreme", "scenario": "happy"}]))

    def test_rejects_unknown_scenario(self):
        with self.assertRaises(ValueError):
            riq.parse_answers(_valid_answers(
                order_matrix=[{"label": "#1", "fraud": "low", "scenario": "nonsense"}]))


class CliTests(unittest.TestCase):
    def _script_path(self):
        return str(pathlib.Path(__file__).resolve().parents[1] / "render_intake_questionnaire.py")

    def test_render_subcommand_writes_a_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = str(pathlib.Path(tmp) / "questionnaire.html")
            result = subprocess.run(
                [sys.executable, self._script_path(), "render",
                 "--prospect-name", "Acme", "-o", out],
                capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("shopify_opp", pathlib.Path(out).read_text())

    def test_parse_subcommand_prints_normalized_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            answers_file = pathlib.Path(tmp) / "answers.json"
            answers_file.write_text(_valid_answers())
            result = subprocess.run(
                [sys.executable, self._script_path(), "parse", str(answers_file)],
                capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["mode"], "babysit")

    def test_parse_subcommand_fails_loud_on_invalid_answers(self):
        with tempfile.TemporaryDirectory() as tmp:
            answers_file = pathlib.Path(tmp) / "answers.json"
            answers_file.write_text(_valid_answers(mode="turbo"))
            result = subprocess.run(
                [sys.executable, self._script_path(), "parse", str(answers_file)],
                capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn("ANSWERS INVALID", result.stderr)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd plugins/pl-tools/scripts && python3 -m unittest tests.test_render_intake_questionnaire -v`
Expected: FAIL — `AttributeError: module 'render_intake_questionnaire' has no attribute 'parse_answers'`

- [ ] **Step 3: Implement `parse_answers` and `main`**

Replace the `if __name__ == "__main__": pass` line at the end of
`plugins/pl-tools/scripts/render_intake_questionnaire.py` with:

```python
def parse_answers(raw_json):
    """Validate and normalize the questionnaire's submitted JSON.

    Raises ValueError with a specific reason on any problem — this is the
    function that decides whether the conductor writes the manifest fields
    or re-prompts on the same page.
    """
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise ValueError(f"not valid JSON: {exc}") from exc

    required = {"shopify_opp", "reuse_pool", "order_matrix", "gate_c", "mode"}
    missing = required - set(data)
    if missing:
        raise ValueError(f"missing field(s): {sorted(missing)}")

    if not isinstance(data["shopify_opp"], bool):
        raise ValueError("shopify_opp must be true or false")

    if data["reuse_pool"] is not None and not isinstance(data["reuse_pool"], bool):
        raise ValueError("reuse_pool must be true, false, or null")

    if data["mode"] not in MODES:
        raise ValueError(f"mode must be one of {sorted(MODES)}")

    if data["gate_c"] not in GATE_C_VALUES:
        raise ValueError(f"gate_c must be one of {sorted(GATE_C_VALUES)}")

    matrix = data["order_matrix"]
    if not isinstance(matrix, list) or not matrix:
        raise ValueError("order_matrix must be a non-empty list")
    for row in matrix:
        if row.get("fraud") not in FRAUD_LEVELS:
            raise ValueError(f"order_matrix row {row!r} has an invalid fraud level")
        if row.get("scenario") not in SCENARIOS:
            raise ValueError(f"order_matrix row {row!r} has an invalid scenario")
        if not row.get("label"):
            raise ValueError(f"order_matrix row {row!r} is missing a label")

    return {
        "shopify_opp": data["shopify_opp"],
        "reuse_pool": data["reuse_pool"],
        "order_matrix": matrix,
        "gate_c": data["gate_c"],
        "mode": data["mode"],
    }


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="command", required=True)

    render_p = sub.add_parser("render", help="write the questionnaire HTML")
    render_p.add_argument("--prospect-name", required=True)
    render_p.add_argument("--reuse-candidate-date", default=None)
    render_p.add_argument("-o", "--output", required=True)

    parse_p = sub.add_parser("parse", help="validate a submitted answers JSON file")
    parse_p.add_argument("answers_file")

    args = ap.parse_args(argv)

    if args.command == "render":
        html = render(args.prospect_name, reuse_candidate=args.reuse_candidate_date)
        pathlib.Path(args.output).write_text(html)
        print(f"wrote {args.output}")
        return 0

    try:
        raw = pathlib.Path(args.answers_file).read_text()
        answers = parse_answers(raw)
    except (ValueError, OSError) as exc:
        print(f"ANSWERS INVALID: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(answers, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd plugins/pl-tools/scripts && python3 -m unittest tests.test_render_intake_questionnaire -v`
Expected: PASS (19 tests total in this file)

- [ ] **Step 5: Commit**

```bash
git add plugins/pl-tools/scripts/render_intake_questionnaire.py plugins/pl-tools/scripts/tests/test_render_intake_questionnaire.py
git commit -m "feat(demo-environment): parse and validate questionnaire answers"
```

---

### Task 4: Restyle `render_run_page.py` with parcelLab branding

**Files:**
- Modify: `plugins/pl-tools/scripts/render_run_page.py:1-56` (imports + `CSS`), `:470-490` (`render()`)
- Modify: `plugins/pl-tools/scripts/tests/test_render_run_page.py`

**Interfaces:**
- Consumes: `pl_brand.PRIMARY`, `pl_brand.TEXT`, `pl_brand.CARD`, `pl_brand.FONT_FAMILY`, `pl_brand.GOOGLE_FONTS_LINK`, `pl_brand.LOGO_SVG` (Task 1).
- No change to `render_run_page.render()`'s signature or return contract (still `render(state, manifest=None, assets=None, template_html=None) -> str`) — existing callers (`main()`, tests) are unaffected beyond the new HTML content.

- [ ] **Step 1: Read the existing test file in full**

Run: `cat plugins/pl-tools/scripts/tests/test_render_run_page.py`

Note any assertion that pins a literal old color value (e.g. `"#111"`,
`"#1d4ed8"`, `"system-ui"`) — these will need updating in Step 5 below to
reference `pl_brand`'s constants instead, since this task changes those
literal values. Do not change any assertion about page *structure*
(states, pill classes, plan-card gating, product filtering) — none of
that changes in this task.

- [ ] **Step 2: Write the failing tests**

Append to `plugins/pl-tools/scripts/tests/test_render_run_page.py` (add
`import pl_brand` alongside its existing `import render_run_page` /
`import run_state` lines at the top):

```python
class BrandingTests(unittest.TestCase):
    def test_page_uses_the_brand_primary_color(self):
        html = render_run_page.render(a_state())
        self.assertIn(pl_brand.PRIMARY, html)

    def test_page_loads_poppins(self):
        html = render_run_page.render(a_state())
        self.assertIn("Poppins", html)
        self.assertIn("fonts.googleapis.com", html)

    def test_page_shows_the_parcellab_logo(self):
        html = render_run_page.render(a_state())
        self.assertIn(pl_brand.LOGO_SVG.strip()[:40], html)

    def test_auto_banner_keeps_its_orange_on_purpose(self):
        state = a_state()
        manifest = {"run": {"mode": "auto"}}
        html = render_run_page.render(state, manifest)
        self.assertIn("#ff6b35", html)
        self.assertIn(pl_brand.PRIMARY, html)  # brand color is used elsewhere on the page
        banner_start = html.index('class="auto-banner"')
        banner_end = html.index("</div>", banner_start)
        banner_markup = html[banner_start:banner_end]
        self.assertNotIn(pl_brand.PRIMARY, banner_markup)
```

(Use whatever fixture helper the existing file already provides for a
minimal state — the research pass found it's called `a_state()`; if the
actual name differs, use the file's real helper instead — this is the one
spot in this task where you must match the existing file's own
convention rather than the name written here.)

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd plugins/pl-tools/scripts && python3 -m unittest tests.test_render_run_page -v`
Expected: FAIL — the new `BrandingTests` fail (brand tokens not yet present); all pre-existing tests still pass at this point.

- [ ] **Step 4: Restyle the renderer**

In `plugins/pl-tools/scripts/render_run_page.py`, add the import right
after the existing `import run_state` (currently line 14):

```python
import run_state
import pl_brand
```

Replace the `CSS` constant (currently lines 16–56) with:

```python
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
```

(Note the doubled `{{`/`}}` throughout — this constant is now an
f-string, so every literal brace from the original CSS must be escaped.
The `.auto-banner` rules are copied verbatim, unchanged — the orange stays
on purpose, per the design decision.)

Then replace `render()` (currently lines 470–490):

```python
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
```

- [ ] **Step 5: Fix any pre-existing assertions pinned to old literal values**

If Step 1 found assertions like `self.assertIn("#111", html)` or
`self.assertIn("system-ui", html)`, update them to assert
`pl_brand.TEXT`/`pl_brand.FONT_FAMILY` (or the specific new value)
instead. If none were found, skip this step.

- [ ] **Step 6: Run the full test file to verify everything passes**

Run: `cd plugins/pl-tools/scripts && python3 -m unittest tests.test_render_run_page -v`
Expected: PASS, including every pre-existing test — page structure, pill
classes, plan-card gating, and product filtering are all unchanged.

- [ ] **Step 7: Commit**

```bash
git add plugins/pl-tools/scripts/render_run_page.py plugins/pl-tools/scripts/tests/test_render_run_page.py
git commit -m "style(demo-environment): brand the run page with parcelLab tokens"
```

---

### Task 5: Remove the answers-doc mechanism

**Files:**
- Modify: `plugins/pl-tools/scripts/resolve_auto_defaults.py`
- Modify: `plugins/pl-tools/scripts/tests/test_resolve_auto_defaults.py`
- Modify: `plugins/pl-tools/scripts/validate_manifest.py:63-68`
- Modify: `plugins/pl-tools/scripts/tests/test_validate_manifest.py`

**Interfaces:**
- Produces: `resolve_auto_defaults.resolve_auto_fields(prospect_url, product_pool) -> dict` (drops the `answers_doc` parameter and the `_ignored_doc_keys` output key). Task 6 (SKILL.md) documents calling this 2-arg form.

- [ ] **Step 1: Update `resolve_auto_defaults.py`'s docstring and drop `_NEVER_ASK_FIELDS`**

Replace line 1:

```python
"""Auto-mode resolution: country/category inference for demo-environment.
```

(drops "and answers-doc merge" — there is no doc anymore, confirmed with
the user 2026-08-19: every run now requires a human to fill the
questionnaire.)

Replace the comment + constant at lines 103–114:

```python
# Every field auto-mode can resolve without asking, and its non-doc default.
# Q1 (shopify_opp) is deliberately absent: the spec requires it always be
# asked live, in both modes, via the intake questionnaire. Returns are
# always in scope now (the old Q1/"engage" path was retired), so there is
# no separate returns-in-scope field for this function to guard at all.
_STATIC_DEFAULTS = {
    "run.pace": "standard",
    "gates.order_lifecycle.gate_c": "send-as-is",
    "edit_mode_fix": True,
}
```

(This drops `_NEVER_ASK_FIELDS` entirely — it existed only to keep an
answers doc from overriding `shopify_opp`, and there is no doc left to
guard against.)

- [ ] **Step 2: Update `resolve_auto_fields` and `main`**

Replace lines 117–146:

```python
def resolve_auto_fields(prospect_url, product_pool):
    """Values every run resolves without asking, once the scrape's product
    pool exists — category joins country/region/pace here now that it is
    never a live question either, in any mode.
    """
    country = infer_country(prospect_url, product_pool)
    category = infer_category(product_pool)

    fields = {
        "destination_country": {"value": country, "source": "inferred"},
        "brand.region": {"value": country, "source": "inferred"},
        "brand.category": {"value": category, "source": "inferred"},
    }
    for key, value in _STATIC_DEFAULTS.items():
        fields[key] = {"value": value, "source": "default"}

    return fields
```

Replace lines 149–171 (`main()`):

```python
def main():
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--prospect-url", required=True)
    ap.add_argument("--product-pool-file", required=True,
                     help="path to scrape/product-pool.json")
    args = ap.parse_args()

    try:
        pool = json.loads(Path(args.product_pool_file).read_text())
        # scrape/product-pool.json may be a bare list or {"products": [...]}
        # — inline_assets.py already accepts both shapes; match that here.
        pool = pool if isinstance(pool, list) else pool["products"]
        print(json.dumps(resolve_auto_fields(args.prospect_url, pool), indent=2))
    except (ValueError, OSError) as exc:
        print(f"resolve_auto_defaults: {exc}", file=sys.stderr)
        sys.exit(1)
```

- [ ] **Step 3: Update `test_resolve_auto_defaults.py`**

Read the file in full: `cat plugins/pl-tools/scripts/tests/test_resolve_auto_defaults.py`.

Remove any test method referencing `answers_doc`, `_ignored_doc_keys`, or
`--answers-doc-file` (the research pass identified these live in the
`ResolveAutoFieldsTests` class — doc-override precedence and unknown-key
reporting — and possibly a CLI test for the flag). Update every remaining
call to `resolve_auto_fields(...)` to drop its third argument, and every
assertion on the returned dict to not expect an `"_ignored_doc_keys"` key.

- [ ] **Step 4: Run the test file to verify it passes**

Run: `cd plugins/pl-tools/scripts && python3 -m unittest tests.test_resolve_auto_defaults -v`
Expected: PASS, with the removed doc-related tests gone (test count lower than before) and every remaining test green.

- [ ] **Step 5: Remove `run.answers_doc` from `validate_manifest.py`**

Delete lines 63–68:

```python
    answers_doc = m.get("run", {}).get("answers_doc")
    if answers_doc is not None:
        need(
            isinstance(answers_doc, str) and answers_doc.strip(),
            "run.answers_doc must be a non-empty string when present",
        )
```

- [ ] **Step 6: Update `test_validate_manifest.py`**

Read the file in full: `cat plugins/pl-tools/scripts/tests/test_validate_manifest.py`.
Remove any test case asserting on `run.answers_doc` validation (e.g. a
test that sets `manifest["run"]["answers_doc"] = ""` and expects a
`MANIFEST INVALID` error mentioning it, or one setting a valid
non-empty string and expecting no error from that check specifically).

- [ ] **Step 7: Run both affected test files to verify everything passes**

Run: `cd plugins/pl-tools/scripts && python3 -m unittest tests.test_resolve_auto_defaults tests.test_validate_manifest -v`
Expected: PASS.

- [ ] **Step 8: Run the full test suite**

Run: `cd plugins/pl-tools/scripts && python3 -m unittest discover -s tests -v < /dev/null`
Expected: PASS, same total test count as before this task minus the removed doc-related tests.

- [ ] **Step 9: Commit**

```bash
git add plugins/pl-tools/scripts/resolve_auto_defaults.py plugins/pl-tools/scripts/tests/test_resolve_auto_defaults.py plugins/pl-tools/scripts/validate_manifest.py plugins/pl-tools/scripts/tests/test_validate_manifest.py
git commit -m "refactor(demo-environment): remove the answers-doc mechanism"
```

---

### Task 6: Rewrite `SKILL.md`'s intake flow

**Files:**
- Modify: `plugins/pl-tools/skills/demo-environment/SKILL.md:28-99` ("Mode selection" section)
- Modify: `plugins/pl-tools/skills/demo-environment/SKILL.md:238-343` (Phase 0 steps 2–4)
- Modify: `plugins/pl-tools/skills/demo-environment/SKILL.md:536-539` (manifest schema's `run{...}` line)

This task is prose-only — no automated test exists for a skill's
instructions, so its "test" is the self-consistency grep check in Step 4.

- [ ] **Step 1: Replace the "Mode selection" section**

Replace SKILL.md's current lines 28–49 (from `## Mode selection` through
the end of the "In auto mode: only Q1 is asked live..." paragraph) with:

```markdown
## Intake questionnaire

**Every question is answered by one up-front form, in both modes.** Phase
0 step 2 publishes a single questionnaire (built by
`render_intake_questionnaire.py`) as an Artifact, opens it in the Browser
pane, and waits for the operator to submit it before anything else
happens — no chat round-trip per question, no trigger-phrase mode
detection. Mode (**babysit** or **auto**) is one of the form's own
fields, not inferred from the invoking message's wording.

**Mode's only effect is at the two hard gates.** Babysit (the default,
when the field reads that way) pauses at ★ and ✋ for a human yes exactly
as before. Auto auto-approves both — see "Both hard gates are
auto-approved in auto mode" below — and nothing else in the run reads
`run.mode`. There is no other auto-mode behavior left: every question that
used to auto-resolve differently by mode is now simply asked (or silently
resolved) the same way regardless of mode.

When `run.mode` is `"auto"`, `render_run_page.py` flashes a large banner at
the top of the run page — the run is unattended, and the page should say so
before anyone reads a single lane pill.
```

- [ ] **Step 2: Replace lines 51-67 (the destination country/category block)**

Replace SKILL.md's current lines 51–67 with:

```markdown
**Destination country, brand region, category, and pace are all resolved
silently, in every mode** — call
`${CLAUDE_PLUGIN_ROOT}/scripts/resolve_auto_defaults.py` once the scrape
lane's `product-pool.json` exists:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/resolve_auto_defaults.py \
  --prospect-url "<url>" \
  --product-pool-file "<run dir>/scrape/product-pool.json"
```

Write `destination_country`, `brand.region` (the same value as
`destination_country`), `brand.category`, and `run.pace` from its output
unconditionally — category is no longer a live question in any mode; it
joins the fields this script has always resolved without asking.
```

- [ ] **Step 3: Replace lines 69–78 (rest of Round 2 auto-resolution) and the answers-doc sentence**

Replace SKILL.md's current lines 69–78 with:

```markdown
The order matrix and the send-as-is/extras toggle come from the
questionnaire directly (every run, every mode — see "Intake
questionnaire" above). The target account is always the user's own
default demo account (every mode — see Phase 0 step 4), and the CDC
config is always `selected_account_config_id: null`, `config_source:
"none"` (every mode — see Phase 0 step 4). Write every resolved field
into the manifest exactly where its question already writes it — Phase
1–4 and `validate_manifest.py` do not distinguish an auto-resolved field
from a human-answered one.
```

- [ ] **Step 4: Replace Phase 0 steps 2–4**

Replace SKILL.md's current step 2 ("Path + brand round...") and step 4
("Interview concurrently, in chat...") — step 3 (dispatch the scrape
agent) stays where it is, but now runs after the questionnaire instead of
after a chat Round 1 — with:

```markdown
2. **Publish the intake questionnaire and wait for it.** Detect a reuse
   candidate first — scan `$HOME/parcellab-demo-runs/` for a directory
   whose `<handle>-<ts>` handle equals this run's handle and which
   contains both `scrape/brand-tokens.json` and `scrape/product-pool.json`;
   the most recent such run is the candidate.

   Render the page:

   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/scripts/render_intake_questionnaire.py render \
     --prospect-name "<brand name>" \
     --reuse-candidate-date "<date, only if a candidate was found>" \
     -o "<run dir>/intake-questionnaire.html"
   ```

   Publish it via the Artifact tool, open it in the Browser pane
   (`preview_start` → `navigate`), and tell the operator to fill it in.
   Poll with `read_page` until `#submitted-banner` is visible, then pull
   the JSON out of `#answers-json` with `javascript_tool`
   (`document.getElementById('answers-json').textContent`) and write it
   to `<run dir>/results/questionnaire-answers.json`. Validate it:

   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/scripts/render_intake_questionnaire.py parse \
     "<run dir>/results/questionnaire-answers.json"
   ```

   On `ANSWERS INVALID`, tell the operator what was wrong and have them
   resubmit the same page — never fall through to chat for a fixable
   validation error. Once it parses, write `path` (`shopify_opp` →
   `retain-shopify`, else `retain`), `run.mode`, and
   `gates.order_lifecycle.gate_c` into the manifest immediately — nothing
   past this point is asked again.

   **Fallback, if the Artifact fails to publish or the Browser pane can't
   open it:** fall back to a plain chat interview — ask "Is this a Shopify
   opp?", the reuse question (if a candidate exists), the order matrix, the
   send-as-is/extras toggle, and "babysit or auto?" as ordinary chat
   questions, in that order. Publishing is never load-bearing, the same
   posture as the run page itself.
3. **Dispatch the scrape agent immediately** — `mark(d, "agent", "scrape", "start")` and `mark(d, "lane", "scrape", "start")` as you dispatch. Use the Agent tool
   (general-purpose subagent, background) with exactly this brief, filling
   the placeholders. **Resolve `${CLAUDE_PLUGIN_ROOT}` to its absolute path
   and paste the three real file paths into the dispatched brief** — a
   subagent does not reliably inherit that variable, and an unexpanded one
   hands it three unusable paths:

   > Execute the demo-environment scrape pass for the run directory
   > `<run dir>`, prospect `<url>`, path `<retain|retain-shopify>`.
   > Follow `${CLAUDE_PLUGIN_ROOT}/skills/branded-template/SKILL.md` Steps
   > 3–6 for brand tokens (write the full `__BRAND_X__` token map + logo +
   > hero to `<run dir>/scrape/brand-tokens.json`) and
   > `${CLAUDE_PLUGIN_ROOT}/skills/shopify-seed/references/product-scrape.md`
   > for the product pool (≥8 candidates in the superset shape
   > `{id, name, product_type, price, options, image_url, pdp_url, sku}`;
   > variant axes required only on retain-shopify — elsewhere capture what
   > the PDP shows without extra navigation; write to
   > `<run dir>/scrape/product-pool.json`). Validate every candidate image
   > by running
   > `node ${CLAUDE_PLUGIN_ROOT}/skills/demo-request/scripts/check_images.mjs`
   > over the whole pool (accepts 1–N products; 200 + image/*, ranged-GET
   > retry) and set `image_verified` per product from its per-product `ok`
   > flags. Ground rules, non-negotiable: never ask the user anything — a
   > gap is a failure report; decline non-essential cookies; when done (or
   > failed) write `<run dir>/results/scrape.json` as
   > `{"status": "ok"|"failed", "error": null|"<why>"}` and return a
   > one-paragraph summary.

   **Browser pane ownership:** the agent owns the pane from dispatch until
   `results/scrape.json` exists. Do not navigate the pane in that window —
   the ★ template preview naturally starts after it, since it needs the
   scraped tokens. **This binds more than deliberate navigation:** a
   `PostToolUse` hook can open a file in the pane as a side effect of a plain
   Write (observed 2026-08-11 — writing `run-page.html` took the pane while the
   scrape agent held it). Writing run files is unavoidable, so treat pane
   contention as expected rather than forbidden: if the pane is taken from the
   agent, do not also drive it, and re-check `results/scrape.json` rather than
   assuming the agent died. **Reused pool:** when the questionnaire's
   `reuse_pool` answer is true, skip the dispatch entirely — copy the prior
   run's `scrape/brand-tokens.json` and `scrape/product-pool.json` into this
   run's `scrape/`, then write `results/scrape.json` yourself as
   `{"status": "ok", "error": null}`. Without that file the pre-build at
   step 6 waits on a precondition nothing else will ever satisfy. Once
   `results/scrape.json` shows
   `ok`: record the fact via `${CLAUDE_PLUGIN_ROOT}/scripts/run_state.py` — `mark(d, "agent", "scrape", "end")` the moment the file lands, plus `mark(d, "lane", "scrape", "end")` — then `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/render_run_page.py <run dir>` and republish the artifact — non-fatal. **Never hand-edit `run-page.html`;** it is derived, and the next render overwrites it.
4. **Resolve the remaining Phase 0 checks**, once the questionnaire has
   answered `path`, `reuse_pool`, the order matrix, and `gate_c`:
   - **Shopify resolution (retain-shopify only):** First `command -v shopify` —
     if the CLI is missing, stop and point the user at `/pl-setup`'s optional
     Shopify CLI section (install + full-scope store auth) rather than
     improvising an install mid-intake; the auth must carry the
     order/fulfilment scopes or the order engine hits a re-consent wall later.
     Then resolve the store **without asking**: read
     `~/.claude/parcellab-shopify-seed.env`, else `shopify store auth list`.
     Exactly one store → use it and state it at the ✋ gate. None → stop and
     point at `/pl-setup`. Two or more → this is the only case that asks
     (intake-script Q8). Then resolve the location GID immediately — follow
     shopify-seed Steps 1–2 exactly, including the fulfils-online-orders
     preference rules. Record both in the manifest.
   - **Destination country, brand region, category, and pace (every run,
     resolved silently):** call `resolve_auto_defaults.py` once
     `scrape/product-pool.json` exists (see "Intake questionnaire" above for the
     exact invocation) and write its `destination_country`, `brand.region`
     (the same value as `destination_country`), `brand.category`, and
     `run.pace` output straight into the manifest — no question, in any mode.
   - **Target account (every run, resolved silently):** always the user's
     own default demo account (`${PARCELLAB_ACCOUNT_ID:-$PARCELLAB_USER_ID}`)
     — there is no other account choice to offer here any more; a run that
     needs the shared **parcelfashion** account or another target has to be
     built outside this skill. Resolve the human name with
     `parcellab account account show <id>` and stamp
     `account.confirmed_at` immediately — there is no confirmation question
     left to gate it on, but the resolved name is still stated in Beat 1 so
     it stays visible after the fact. Verify
     `parcellab settings edit-mode show` says `account-restricted` for that
     same account, offering the fix if not (Q6). In the same round, check
     write permissions per *Write permissions* above (Q7 if something is
     missing) — a missing rule is cheap to fix here and stalls the run
     mid-build if it surfaces after the gate.
   - **CDC config (every run):** always write
     `selected_account_config_id: null`, `config_source: "none"` — the CDC
     uses the caller's default config. Say so in the final report ("caller's
     default config"). This is safe now that the target account is always
     the fixed default account above and the practical default already
     targets that same account — the earlier per-target key lookup
     (`CDC_ACCOUNT_CONFIG_DEFAULT` / `_PARCELFASHION` / `_SHOPIFY`) no
     longer applies, since there is only one target left.
     `generate_orders` is always `false` and `cdc.orders` always `[]` — the run
     never asks the CDC to generate synthetic orders alongside its real ones,
     and the ✋ gate states this as a fixed line so it stays visible. Linking
     still depends on the caller's default config actually targeting the
     right account: the CDC resolves linked order numbers in the config's
     target account, so a default config pointed elsewhere fails linking with
     "No parcelLab order found" (live-verified 2026-08-11) — worth a one-time
     check outside this run if linking ever fails on the very first run.
```

(This preserves every bullet from the old step 4 verbatim except the two
"Destination country..." and lead-in sentences, which now say "category"
too, matching Step 2 above.)

- [ ] **Step 5: Update the manifest schema line**

Replace SKILL.md's current lines 536–539:

```markdown
`demo-manifest.json`:
`run{…, pace: "standard"|"fast" — absent means standard,
mode: "babysit"|"auto" — absent means babysit, page_url —
```

(drops `, answers_doc — present only when auto mode used one` — there is
no answers doc anymore.)

- [ ] **Step 6: Self-consistency grep check**

Run:

```bash
grep -n "trigger phrase\|answers_doc\|answers doc\|Round 1\|Round 2\|only Q1 is asked live" plugins/pl-tools/skills/demo-environment/SKILL.md
```

Expected: no matches. If any remain, they are leftover references this
task missed — fix them before committing.

- [ ] **Step 7: Commit**

```bash
git add plugins/pl-tools/skills/demo-environment/SKILL.md
git commit -m "docs(demo-environment): describe the questionnaire-driven intake flow"
```

---

### Task 7: Rewrite `intake-script.md`

**Files:**
- Modify: `plugins/pl-tools/skills/demo-environment/references/intake-script.md`

Prose-only, same self-consistency-grep verification approach as Task 6.

- [ ] **Step 1: Replace the whole file**

Replace the entire contents of
`plugins/pl-tools/skills/demo-environment/references/intake-script.md`
with:

```markdown
# demo-environment — canonical intake fields

Every field below is answered once, by the intake questionnaire
(`render_intake_questionnaire.py`), before the scrape agent is dispatched
— see `SKILL.md`'s "Intake questionnaire" section for the publish/wait/
extract mechanics. This file documents *what* the questionnaire asks and
what it deliberately doesn't; it no longer describes a sequential chat
round structure, since there isn't one.

## Fields the questionnaire asks

| Field | Options | Condition |
|---|---|---|
| Shopify opp? | No · Yes | always |
| Reuse the pool scraped for **\<brand\>** on \<date\>, or scrape fresh? | Reuse · Scrape fresh | a prior run dir with the same handle holds both `scrape/brand-tokens.json` and `scrape/product-pool.json` |
| Order matrix | see below | always |
| Anything else to add to every order, or send as-is? | Send as-is · Extras (detail asked in chat after the form) | always |
| Mode | Babysit · Auto | always |

`shopify_opp` → `path` (No → **retain**, Yes → **retain-shopify**).
Returns are always in scope for this demo — there is no separate question
about that; every run is either **retain** or **retain-shopify**.

### The default order matrix

The questionnaire pre-fills this; the operator edits from it. 1–5 orders,
default 3.

| Order | Fraud | Scenario |
|---|---|---|
| #1 | low | happy |
| #2 | medium | split — parcel A happy, parcel B stuck-delay |
| #3 | high | recovered |
| #4 | low | manual_return (retain paths only) |
| #5 | low | return_tracking (retain paths only) |

Scenario vocabulary: `happy` · `stuck-delay` · `recovered`
(`InTransit → WarehouseDelay → OutForDelivery → Delivered`, proven live
2026-08-11) · `locker` (`… → Delivered-ParcelLocker`, status unproven) ·
`custom` (user-specified sequence, labelled per order-lifecycle's confidence
rules). Runs of 2+ orders need at least one split-shipment order. Every order
gets a distinct synthetic customer (region-appropriate name + email) —
generate them and show them.

### The send-as-is / extras toggle

The default is send-as-is, and picking it takes one click. When the
operator picks **extras**, the field-by-field detail — promise dates,
order financials, article physical data, delivery detail, tags/custom
fields, dynamic recipients, extra articles — is collected in **chat, after
the questionnaire**, from order-lifecycle's own Gate C menu. The
questionnaire only ever asks the toggle: those per-field values depend on
schema owned by order-lifecycle, not this skill.

Three rules specific to an orchestrated run, unchanged from before:

- **One answer covers every order.** Extras are per-run, not per-order.
- **Tags merge, they do not replace.** `prepare_fraud_fragment.py` already
  writes each order's top-level `tags` and `additional_attributes`. Union the
  intake's tags with the fraud fragment's output per order; neither side
  overwrites the other. Overwriting discards the fraud data the whole run is
  built to demonstrate.
- **The `client_key` pre-fill does not apply.** Standalone Gate C pre-fills a
  `client_key` when Gate B introspected a journey needing one. Here Gate B is
  answered by the manifest and no introspection runs, so nothing is pre-filled.

Record the answer as `gates.order_lifecycle.gate_c` (`"send-as-is"` or
`"extras"`) plus `extras`. Promise dates are resolved to absolute `YYYY-MM-DD`
at manifest-write time — a full ISO datetime is rejected by the API.

### Deriving article weights

When the chat follow-up turns on article physical data, do not ask for a
value per product. Derive one per article from its `product_type` and show
every derived value at the ✋ gate, article by article, so it can be
corrected before anything is sent.

Match case-insensitively on the `product_type` string; first match wins.

| `product_type` contains | Weight |
|---|---|
| shoe, boot, sneaker, trainer | 900 g |
| coat, jacket, knit, jumper, hoodie | 700 g |
| shirt, tee, top, dress, trouser, sock, apparel | 300 g |
| bag, hat, belt, scarf, accessor | 500 g |
| phone, laptop, tablet, electronic, device, audio | 1200 g |
| home, kitchen, decor, furnish | 800 g |
| (no match) | 500 g |

**`weight_unit` is always written, never left out** — `validate_manifest.py`
rejects a missing one (`{weight: 300}` → "must be one of [...] (got None)").
Write `g` unless the user says otherwise, in which case it must be one of
`kg`, `g`, `lbs`, `oz`; any other value is rejected too. Weights are numbers
greater than zero. Write them to
`extras.article_weights`, keyed by product **`id`** (the goods code) and never
by SKU — `validate_manifest.py` rejects SKU keys.

## Fields the questionnaire deliberately does not ask

Each of these was a live question once. Resolving them silently is what
makes a clean run unattended after the ✋ gate, and what makes mode
irrelevant to every question except the two hard gates.

| Not asked | Instead |
|---|---|
| Are returns in scope for this demo? | Always yes. The old "engage" (no-returns) path is retired; every run is `retain` or `retain-shopify`. |
| Which country are these orders delivering to? | Always inferred via `resolve_auto_defaults.infer_country` (TLD, else path locale segment, else scraped currency symbol, else `US`) — in every mode. Written to `destination_country`. |
| Which region should the CDC request use? | Always set equal to the resolved `destination_country` above, written to `brand.region`. |
| Which category should the CDC request use? | Always inferred via `resolve_auto_defaults.infer_category` from the scraped product pool, once it exists — in every mode. Written to `brand.category`. |
| What pace should the journeys run at? | Always `"standard"` (200 s gaps). `GAP_SECONDS=60` ("fast") is no longer offered as a live choice. |
| Which account should this demo build in? | Always the user's own default demo account (`${PARCELLAB_ACCOUNT_ID:-$PARCELLAB_USER_ID}`) — the shared **parcelfashion** account is no longer offered as a choice here. |
| Using **\<name\>** (\<id\>) — correct? | No longer asked — the account above is resolved and used silently. Its name is still looked up (`parcellab account account show <id>`) and stated in Beat 1, so it stays visible after the fact even though nothing gates on it beforehand. |
| What is the CDC account config name (or UUID) for this target? | Always `selected_account_config_id: null`, `config_source: "none"` — the CDC uses the caller's default config. |
| Should the CDC also generate synthetic orders? | `generate_orders` is always `false` and `cdc.orders` always `[]`. The ✋ gate states `CDC synthetic generation: off` so it stays visible. |
| Which Shopify store? (when only one) | Resolved from `~/.claude/parcellab-shopify-seed.env`, else `shopify store auth list`. Exactly one → use it and state it at the gate. Zero → stop and point at `/pl-setup`. 2+ → asked (SKILL.md Phase 0 step 4's Shopify resolution bullet). |
| Restore the edit-mode guard? | Restored automatically after Beat 2, once every driver has exited. |
| Record this proven event in `status-codes.md`? | Recorded automatically by Beat 2, which reports what it wrote. |

## Mode

**Babysit** and **auto** answer every field above identically — mode is
purely a questionnaire field now, not inferred from wording, and it
changes exactly one thing downstream: whether the ★ template preview and
✋ plan approval pause for a chat yes or auto-approve. See `SKILL.md`'s
"Intake questionnaire" and "Both hard gates are auto-approved in auto
mode" sections.
```

- [ ] **Step 2: Self-consistency grep check**

Run:

```bash
grep -n "Round 1\|Round 2\|Auto mode never changes\|answers_doc\|answers doc\|trigger phrase\|Q[1-8]\b" plugins/pl-tools/skills/demo-environment/references/intake-script.md
```

Expected: no matches — this file no longer numbers questions or refers to
rounds, docs, or trigger phrases.

- [ ] **Step 3: Cross-check against SKILL.md**

Run:

```bash
grep -n "intake-script" plugins/pl-tools/skills/demo-environment/SKILL.md
```

For each match, confirm the surrounding SKILL.md sentence still makes
sense given intake-script.md's new structure (no more "Round 1"/"Q1-Q8"
references pointing at a numbering scheme this file no longer has).

- [ ] **Step 4: Commit**

```bash
git add plugins/pl-tools/skills/demo-environment/references/intake-script.md
git commit -m "docs(demo-environment): rewrite intake-script for the questionnaire flow"
```

---

## Final verification

- [ ] Run the entire suite once more from a clean state:

```bash
cd plugins/pl-tools/scripts && python3 -m unittest discover -s tests -v < /dev/null
```

Expected: PASS, all tests green.

- [ ] Grep the whole `demo-environment` skill directory for any leftover
  reference to the removed mechanisms:

```bash
grep -rn "answers_doc\|answers doc\|trigger phrase\|Round 1\|Round 2" plugins/pl-tools/skills/demo-environment/
```

Expected: no matches.
