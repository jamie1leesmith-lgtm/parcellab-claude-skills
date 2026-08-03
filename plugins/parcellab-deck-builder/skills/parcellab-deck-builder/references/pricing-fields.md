# Pricing extraction

Business-case decks are the only preset that touches the two internal pricing
calculators:

- `~/Documents/Work/Pricing Calcs/parcellab_pricing_model_15_3 1.html` — Retain
  pricing model (13-step wizard; `marketSel`, `gateYes`/`gateNo`).
- `~/Documents/Work/Pricing Calcs/parcellab_engage_pricing_model_19_6_2 1.html`
  — Engage pricing model (8-step wizard).

Both are marked "Internal" in their `<title>`, have no localStorage or export,
and end in a `verdictPanel` (`vFlags`/`vReason`/`vTally`) that is deal-desk
approval logic — **never read that panel or its fields.**

## Procedure

1. The user completes the relevant wizard themselves, in their own browser,
   to the point where the result fields (`rTotal`, `rRate`, `rTier`, `rVol`)
   show real numbers. This skill never drives the wizard.
2. Once the user confirms it's complete, read back **only** the allowlisted
   fields via `execute_javascript` (Control Chrome) or `javascript_tool`
   (Claude-in-Chrome) on that tab:

   ```javascript
   (() => {
     const ALLOWLIST = ['rTotal', 'rRate', 'rTier', 'rVol'];
     const out = {};
     for (const id of ALLOWLIST) {
       const el = document.getElementById(id);
       if (el) out[id] = el.textContent.trim();
     }
     return out;
   })()
   ```

   This is the same `ALLOWLIST` as `extract-pricing-fields.js` — keep them in
   sync; a change to one without the other is a bug, not a style choice.
3. **Gate 3**: show the exact figures read back and wait for explicit
   confirmation before they're placed on the Pricing / Revenue-uplift slides.
   This is separate from Gate 2's approval that a pricing slide will exist at
   all.
