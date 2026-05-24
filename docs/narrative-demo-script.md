# Narrative demo script (3 minutes)

This script is for an executive walkthrough. The audience is mixed business + technical. The tone is sober. Slides are optional; the Streamlit app is the visual aid.

---

## 0:00 - Frame

> "Consumer-facing AI agents are about to act on our behalf - on our payment instruments, against retailer agents, at machine speed. We do not have a control problem with how these agents *think*. We have a control problem with what they are allowed to *do*. This is a demo of runtime governance over delegated commerce action."

Cue: Mission tab. Read the delegation aloud - budget, retailers, materials, substitution tolerance, delivery deadline, data sharing limits, auto-buy threshold.

> "Eva has delegated authority. She has not delegated accountability."

---

## 0:30 - Happy path

Switch scenario to `happy_path`. Click through Ledger.

> "The agent searches an approved retailer, shortlists a compliant SKU within budget, shares only whitelisted data fields, places the order, and charges the payment token. Every one of those is a *governed* action - each row in the ledger is a `DecisionRecord` produced by the audit stage. The state of the world only changed because each PAG verdict was ALLOW."

Point out:
- `policies_evaluated` - the rule packs that opined.
- `acting_on_behalf_of` - every action is attributed to a delegating human.

---

## 1:00 - Blocked path

Switch to `blocked_path`. Click through Ledger and Forensics.

> "Three independent failure modes, three blocks. The agent tries to select an unapproved retailer - BLOCK. It tries to share marketing consent and phone number - BLOCK. It tries to accept a 3-day return window when Eva's minimum is 14 days - BLOCK. None of these reached a real consequence. None of them needed Eva's attention. The retailer-side `confirm_order` was never invoked. Evidence exists for every refusal."

Open Forensics, pick the data-sharing block, walk through PAG → ATM → PAA and the facts used.

---

## 1:45 - Escalation path

Switch to `escalation_path`.

> "This is where governance is most visible. The retailer offers a substitute SKU that is 14% more expensive - outside Eva's 10% tolerance. The substitution pack says ESCALATE. The budget pack notices that the substitute's total exceeds the auto-buy threshold and *also* says ESCALATE. The strictest verdict wins. The approval service is invoked. Eva - or her policy proxy - approves. Only then does ATM authorize, and only then does the order proceed. Each ESCALATE is in the ledger with the approval outcome attached."

---

## 2:30 - Allow-with-conditions

Switch to `conditional_path`.

> "A loyalty promotion would reduce the total but requires a marketing consent. The promotions pack returns ALLOW_WITH_CONDITIONS. The condition is `loyalty_enrollment_accepted == true`. ATM requires the condition to be satisfied at execute time, not earlier. If Eva had not flipped that flag, ATM would have aborted - even though PAG already said 'allow'. This is what bounded delegation looks like."

---

## 2:45 - Close

> "Three takeaways. One: agentic commerce will scale when delegated action is bounded by policy, intercepted at runtime, escalated when authority is exceeded, and evidenced afterwards. Two: that governance lives at the *action boundary*, not inside the model - we do not need to certify the model to bound its consequences. Three: the artifact we just looked at - the ledger and the forensics view - is what an insurer, a regulator, or a dispute reviewer would actually need. The chat log is not enough."

> "This repository is a pre-production reference implementation. It does not prove security or legal sufficiency. It demonstrates the pattern."
