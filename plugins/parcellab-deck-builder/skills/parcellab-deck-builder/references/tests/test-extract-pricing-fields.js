const assert = require('assert');
const { ALLOWLIST, filterAllowlistedFields } = require('../extract-pricing-fields.js');

// Test A: only allowlisted fields pass through, verdict fields are dropped
const input = {
  rTotal: '$4,200/mo',
  rRate: '0.012',
  rTier: 'Tier 3',
  rVol: '250000',
  verdictPanel: 'APPROVED',
  vFlags: 'none',
  vReason: 'within standard discount band',
  vTally: '-12%',
};
const out = filterAllowlistedFields(input);
assert.deepStrictEqual(Object.keys(out).sort(), ['rRate', 'rTier', 'rTotal', 'rVol']);
assert.strictEqual(out.rTotal, '$4,200/mo');
assert.strictEqual(out.rRate, '0.012');
assert.strictEqual(out.rTier, 'Tier 3');
assert.strictEqual(out.rVol, '250000');
assert.strictEqual(out.verdictPanel, undefined);
assert.strictEqual(out.vFlags, undefined);
assert.strictEqual(out.vReason, undefined);
assert.strictEqual(out.vTally, undefined);

// Test B: a missing allowlisted field is simply absent, not an error
const partial = filterAllowlistedFields({ rTotal: '$100' });
assert.deepStrictEqual(Object.keys(partial), ['rTotal']);

// Test C: the allowlist itself is exactly the four approved fields (guards
// against someone silently adding a field to the allowlist unreviewed)
assert.deepStrictEqual(ALLOWLIST.slice().sort(), ['rRate', 'rTier', 'rTotal', 'rVol']);

// Test D: completely empty input -> empty output, no throw
assert.deepStrictEqual(filterAllowlistedFields({}), {});

console.log('ALL TESTS PASSED');
