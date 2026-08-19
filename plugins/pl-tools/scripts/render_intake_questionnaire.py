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
