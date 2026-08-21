# pl-knowledge Task 5 — Live behavioural verification log

Date: 2026-08-21. Session had both routes available: parcelLab MCP connector
(`mcp__8083c251-...__knowledge_*` tools) and the `parcellab` CLI on
`~/.local/bin` (not on default PATH).

## Step 1 — Time a Tier 0 lookup

**Question:** "what does the WISMO/R agent require for email deployment?"

Followed `SKILL.md`'s Tier 0 rule literally: one `knowledge_search_documents`
call, answer from returned chunks, stop.

- Calls made: 1 (`knowledge_search_documents`, query "WISMO agent email
  deployment requirements")
- Wall-clock: ~8.1s (timestamped before/after the call: 1787324787.71 →
  1787324795.81)
- Synthesis route touched: no
- Result: chunks directly answered the question — top hit (gitbook
  `wismor-agent` doc) states: "Opt-in to OpenAI enabled", "WISMO/R agent
  configured for your parcelLab account", "parcelLab Engage for email
  communications".

**Outcome:** exactly one retrieval call was made, no synthesis. Note:
observed latency (~8s) ran above the documented "~2-5s" for this route; the
gap is plausibly agent-side overhead (composing/interpreting the call) rather
than pure MCP round-trip, but it is reported as observed rather than adjusted
to fit the spec. Not changing `tool-inventory.md`'s 2-5s figure since this
was a single sample and the mechanism (no LLM in path) matches the spec's
reasoning — flagging as a soft observation, not a contract failure.

**Self-testing bias (applies equally to Step 2, stated once here):** the
tester and the rule-follower were the same agent in the same turn, and that
agent had already read the brief's "Expected: exactly one retrieval call, no
synthesis" before making the call. This step therefore shows the Tier 0 rule
is *followable* and *unambiguous to a reader* — it does not show the rule
*constrains* an agent that doesn't already know the expected answer, is
under time pressure, or is otherwise tempted to reach for a bigger hammer.
A genuine test of whether the rule holds under temptation would need either
(a) an agent given only `SKILL.md` and the question, with no visibility into
what call count is "expected", or (b) observed behaviour aggregated over many
real sessions where the agent had no reason to suspect it was being graded.
Verdict downgraded accordingly below (see Step 6).

## Step 2 — Confirm Tier 2 is not entered implicitly

**Question:** "tell me everything about the WISMO agent" — no explicit "brief
me" / "positioning" / "dig deep" language.

Followed the routing rule literally: this phrasing does not trigger Tier 2's
explicit-request clause, so ran one more `knowledge_search_documents` call
(broader query) rather than escalating to `knowledge_ask_gtm_agent` or CLI
synthesis.

- Calls made: 1 retrieval call (no Tier 2 call)
- Wall-clock: not separately timed (retrieval-only, same order as Step 1)
- Synthesis route touched: **no**
- Result: chunks returned a reasonably complete picture (overview,
  deployment options — email/chat/API, positioning, a Gong call excerpt) —
  enough to answer "everything" at a useful level without synthesis.

**Outcome:** no Tier 2 call was made; the broad phrasing did not, by itself,
read as license to escalate. No `SKILL.md` change needed. Caveat: this is
one phrasing sample; a differently-worded broad question ("give me the full
picture", "deep dive before my call") might land closer to the ambiguous
edge — worth keeping an eye on in real use, but not something to
speculatively rewrite the rule for without more evidence of drift.

**Same self-testing bias as Step 1:** the same agent that read Tier 2's
"never entered implicitly" rule then decided, on its own recognizance,
whether this question qualified as an explicit request — with the brief's
expected outcome ("the skill either answers from Tier 0/1 or asks") already
in view. That is a test of whether the rule *reads* as unambiguous, not of
whether an agent under real pressure to look thorough would resist reaching
for the 40s synthesis pass anyway. This does not demonstrate the rule
constrains behaviour; it demonstrates the rule doesn't obviously fail to. The
"Pass" language below is downgraded to reflect that.

## Step 3 — Time the CLI synthesis route

```
export PATH="$HOME/.local/bin:$PATH"; time parcellab knowledge search "WISMO agent prerequisites"
```

**Result:** succeeded — cited JSON answer (`answer`, `citations`,
`session_id`, `status: "success"`).

**Timing (real, from `time`):**
```
parcellab knowledge search "WISMO agent prerequisites" 2>&1  1.11s user 0.14s system 3% cpu 31.976 total
```
Wall-clock: **31.976s**.

Compared to the spec's ~42s figure, this is materially faster (~24% lower).
Updated `references/tool-inventory.md`:
`~42s measured` → `~32-42s measured (varies by run)`.

## Step 4 — Short-question hypothesis for `knowledge_query_parcellab_knowledge`

**Question:** "What is the WISMO agent?"

- Timestamped before/after: 1787324853.12 → 1787324890.84 → **~37.7s**
- Result: **succeeded** — full cited answer with `status: "success"`,
  covering definition, mechanism, deployment options, and pilot-availability
  status.

**Outcome:** hypothesis confirmed — this route does not time out on a short,
single-part question, even though it is slow (~38s, not fast enough to ever
be Tier 0/1). Updated `references/tool-inventory.md` per the brief's
instruction: the row now reads "succeeds on short questions (~38s measured),
times out on long ones" instead of implying the tool is generally unusable.

## Step 5 — Verify one degradation path (missing CLI)

```
env PATH=/usr/bin:/bin parcellab knowledge search "test" 2>&1 | head -3
```

**Observed output:**
```
env: parcellab: No such file or directory
```

This is `env`'s own failure message (it could not find `parcellab` on the
stripped PATH), not literally the string "command not found" that a shell
would print if you typed `parcellab` directly at a prompt. Functionally
equivalent — clear, unambiguous "binary not found" signal — but noting the
exact wording differs from the naive expectation. `SKILL.md`'s diagnosis
table entry ("CLI `command not found` → Not installed, or not on PATH") still
correctly describes this class of failure; no change needed, since both
phrasings mean the same thing to a reader and the table's advice ("install
via pl-tools setup, or check `~/.local/bin`") remains the right response.

**Unverified degradation paths (explicitly called out per the task's
constraints):** the MCP-tool-absent path and the "CLI-only colleague with a
different working CLI setup" path were **not** tested and remain
**unverified** — this session has both MCP and CLI working, so there is no
way to observe what an agent actually does when the MCP connector itself is
missing from the tool list, or when only a colleague's CLI is present with
a different auth/session state. Do not treat this log as verifying either.

## Step 5b — Verify the account-research cross-read

**Question (as posed to the skill's rules, per `account-research.md`'s
sweep):** "brief me on River Island for a WISMO agent call"

Ran the retrieval passes the sweep prescribes: customer business
case/stakeholders/carriers (one `knowledge_search_documents` call, query
"River Island business case stakeholders WISMO agent") plus reuse of the
Step 1/2 WISMO-agent product-requirements retrieval already in context.

**Customer-specific facts returned (real, not generic):**
- Stakeholders: Sunil Bhudia (Head of Fulfilment), Samantha Powell (Product
  Manager), Amie Knight (Senior Logistics Analyst), opportunity owner Ben
  Macklin
- Carriers/systems: DPD (international tracking), Evri, Royal Mail;
  incumbent being displaced is ReBound/ZigZag
- Live dates/commitments: deal period Aug 2025–Feb 2026, core returns
  functionality targeted for October go-live
- Known-broken dependency: "issues with international DPD tracking, missing
  crucial data for customs reports (HS codes, COO, VAT indicator)"

**Product dependency (from the WISMO/R agent docs retrieved earlier):** the
agent's answers are only as good as its inputs — it "pulls real-time data
from Order info APIs, Tracking events, Carrier performance signals..." to
avoid guessing.

**The collision:** River Island's own account file documents long-standing
international DPD tracking gaps, which is exactly the kind of carrier-data
gap the WISMO/R agent depends on to answer accurately. Recommending the
WISMO/R agent for River Island without first addressing (or scoping around)
the DPD tracking gap risks the agent giving wrong or unresolvable answers on
exactly the international-shipment inquiries it's meant to reduce.

**Outcome:** contract held — the cross-read step in `references/account-research.md`
was followed and produced the intended collision, not a generic product
pitch. Caveat: this is the *exact* worked example already written into
`account-research.md`, so it is a weak test of generalisation — it confirms
the retrieval mechanism and the written step work together, but does not
prove the skill would find an equally sharp collision on an account with no
worked example. No fix needed; flagging as a scope limit of this
verification, not a pass/fail gap.

## Step 6 — Summary

| Step | Result |
|---|---|
| 1 (Tier 0 timing) | Observed compliance, not an independent pass — 1 call, ~8.1s, no synthesis, but the tester already knew the expected call count (see self-testing-bias note above) |
| 2 (Tier 2 not implicit) | Observed compliance, not an independent pass — no synthesis call made on a broad-but-not-explicit question, same self-testing-bias caveat as Step 1 |
| 3 (CLI synthesis timing) | Pass — 31.976s (spec said ~42s); `tool-inventory.md` updated |
| 4 (short-question hypothesis) | Confirmed — succeeded in ~37.7s; `tool-inventory.md` updated |
| 5 (missing-CLI simulation) | Pass — clear "binary not found" signal, wording differs slightly from literal "command not found" but is unambiguous; no `SKILL.md` change needed |
| 5b (account cross-read) | Weak pass — named real stakeholders/carriers/dates and surfaced the DPD-tracking-gap collision, but on the account file's own worked example (see caveat above) |

**No `SKILL.md` contract failures were observed in this session.** Steps 1 and
2 did not catch the rules failing, but — per the self-testing-bias note above
— that is weaker evidence than a genuine independent trigger would provide:
the same agent wrote the rules' expected outcome into its own working memory
before acting on them. No fixes were applied to `SKILL.md`, because nothing
in this session's method was capable of producing a "must fix" signal beyond
"the rule is legible and one agent didn't visibly violate it while holding
the answer key." A stronger test — a fresh agent given only `SKILL.md` and
the question with no stated expectation, or real-session telemetry gathered
over time without the agent knowing it's being evaluated — would be needed
before treating Tier 2 non-escalation as proven under pressure.

**Files amended and why:**
- `plugins/pl-knowledge/skills/pl-knowledge/references/tool-inventory.md` —
  corrected the CLI synthesis latency figure from a single "~42s measured" to
  a measured range "~32-42s measured (varies by run)", and changed the
  `knowledge_query_parcellab_knowledge` guidance from implying the tool is
  unusable to noting it succeeds on short questions (~38s) and times out on
  long ones, per the measurement in Step 4.

**Explicitly unverified in this and any single session with both routes
working:** the MCP-absent degradation path, and the CLI-only-colleague
degradation path. These require a session missing one of the two routes to
observe honestly, and this session had both.
