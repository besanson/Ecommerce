# Narrative demo script (3 minutes)

This script is for an executive walkthrough. The audience is mixed business + technical. The tone is sober. Slides are optional; the Streamlit app is the visual aid. The scenario throughout is the same one: Eva's subscription portfolio.

---

## 0:00 - Frame

> "Consumer-facing AI agents are about to act on our behalf - on our payment instruments, against retailers, at machine speed. We do not have a control problem with how these agents *think*. We have a control problem with what they are allowed to *do*. This is a demo of runtime governance over delegated commerce action."

Cue: Mission tab. Read Eva's delegation aloud - auto-renew under €15/month, escalate €15-€30, block above €30 or any unapproved new service, no sharing of payment data beyond token and billing email, cancel on silent billing-period changes.

> "Eva has delegated authority. She has not delegated accountability."

---

## 0:30 - Allowed and conditionally allowed

Open the Ledger. Walk to row 1 (Netflix) and row 2 (Spotify Premium).

> "First, Netflix at €13.99 - fresh baseline, under the auto-renew threshold. ALLOW. The agent did not ask Eva. Second, Spotify Premium has drifted from €9.99 to €10.49 - 5% over baseline, inside Eva's tolerance. The pack returns ALLOW_WITH_CONDITIONS, the condition being that the agent log the new baseline forward. ATM checks the condition at execute time, not earlier. This is what bounded delegation looks like at the cheap end of the portfolio."

Point out:
- `policies_evaluated` - the rule packs that opined.
- `acting_on_behalf_of` - every action is attributed to a delegating human.

---

## 1:00 - Blocked

Walk to row 3 (DAZN Total) and row 5 (BundleSavvy aggregator).

> "DAZN Total has jumped from €19.99 to €34.99 - over Eva's €30 block ceiling. BLOCK. No renewal. No charge. Then BundleSavvy, a billing aggregator, asks for `full_card_number` - outside Eva's whitelist. BLOCK. Eva's identity was never disclosed. The subscription service's `confirm_renewal` tool was never invoked. Evidence exists for every refusal."

Open Forensics, pick the BundleSavvy block, walk through PAG → ATM → PAA and the facts used.

---

## 1:45 - Escalated

Walk to row 4 (Apple TV+) and row 6 (Amazon Prime).

> "This is where governance is most visible. Apple TV+ is new - not on Eva's approved list. The data foundation has a gap. The pack does not block, because the agent's correct move is not to silently refuse - it is to surface a single-action authority extension. ESCALATE. Same for Amazon Prime: the service silently switched from monthly to annual billing. Eva's baseline says monthly. The subscription-terms pack says ESCALATE. In a production system Eva would get a notification with one button each. In the demo, both escalations time out unresolved - the open approval ticket is itself audit evidence."

---

## 2:30 - The data-foundation moment

Walk to row 7 (Disney+ with stale context).

> "The last row is the one most agentic demos elide. The agent attempts to renew Disney+ against a ConsumerContext that is missing `approved_services_version`. The Data Context Validator fires *before* PAG is even consulted. The verdict is BLOCK_MISSING_CONTEXT. The agent does not get to act on a stale data foundation. This is why the demo title says 'Three pillars': agentic action, curated data, and governance are not three independent systems - the data foundation is itself a governance precondition."

---

## 2:45 - Close

> "Three takeaways. One: agentic commerce will scale when delegated action is bounded by policy, intercepted at runtime, escalated when authority is exceeded, and evidenced afterwards. Two: that governance lives at the *action boundary*, not inside the model - we do not need to certify the model to bound its consequences. Three: the artifact we just looked at - the ledger and the forensics view - is what an insurer, a regulator, or a dispute reviewer would actually need. The chat log is not enough."

> "This repository is a pre-production reference implementation. It does not prove security or legal sufficiency. It demonstrates the pattern."
