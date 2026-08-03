// extract-pricing-fields.js
// Pure filter: given a map of DOM element id -> its current text/value,
// return ONLY the allowlisted pricing result fields. Never let a caller
// pass through verdictPanel/vFlags/vReason/vTally or any other field —
// unlisted ids are silently dropped, not an error, so a future calculator
// revision can't leak a new internal field just by existing on the page.
//
// Production usage (pasted into execute_javascript against the calculator's
// tab, see references/pricing-fields.md): build `fieldMap` from
// `document.getElementById(id).textContent` for each id in ALLOWLIST, then
// apply this same filter — keeping the ALLOWLIST here and the one in the
// pasted browser snippet identical is the whole point of this being a single
// reviewed source of truth.

const ALLOWLIST = ['rTotal', 'rRate', 'rTier', 'rVol'];

function filterAllowlistedFields(fieldMap) {
  const result = {};
  for (const key of ALLOWLIST) {
    if (Object.prototype.hasOwnProperty.call(fieldMap, key)) {
      result[key] = fieldMap[key];
    }
  }
  return result;
}

module.exports = { ALLOWLIST, filterAllowlistedFields };
