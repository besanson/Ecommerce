# Self-review (hostile)

Written after implementation, on purpose, in the voice of an engineer who has been asked to find problems. The intent is to surface what was deliberately simplified, what was elided, and what would not survive an independent code review on its own.

---

## Overclaiming risks

1. **"Mandatory governance path" is a structural claim, not a runtime claim.** Nothing prevents another process — or another module loaded into the same Python process — from instantiating `RetailerAgent` and calling `confirm_order()` directly. The boundary is one of *agent design*, not one of *enforcement*. The README softens this; the architecture doc spells it out; the bypass test asserts only that the canonical agent does not do it. A genuinely hostile co-resident module is not in scope. This should not be sold as a sandbox.
2. **"Default deny on missing inputs" is true for the rule kinds implemented.** The evaluator returns `passed=False` when a fact is missing, and the rule's `on_violation` decides the verdict. But if a rule's `on_violation` is `escalate` and no approval resolver is configured, the ATM aborts the action — *but the engine still records that as "not executed", not as a fresh BLOCK*. This is correct behaviour, but a hurried reader could confuse "aborted by ATM" with "verdict was BLOCK". The DecisionRecord carries both `pag_status` and `atm_status` to make this distinguishable; the UI relies on the reader noticing.
3. **The trace's "hash chain" is at most tamper-evident, and only against accidental edits.** The hash is computed over a JSON-serialised view of the event and embedded in the *next* event. A determined editor with write access can recompute the entire chain. The `risk-and-limitations.md` doc says this explicitly; the README references it. The word "tamper-evident" appears nowhere in the README — that was intentional.

## Weak architectural spots

1. **`GovernanceEngine.govern(...)` has too many parameters.** Eight keyword arguments. Most are optional and most are mutually exclusive depending on the action type. The signature is honest (it admits the complexity rather than hiding it in subclasses), but it would benefit from per-action helper builders. The consumer agent partially does this; promoting that pattern to first-class would help.
2. **Rule kinds are global.** The handler registry in `evaluator.py` is module-level. Multiple packs that wanted different semantics for the same kind name would collide silently. A pack-scoped registry would be more correct.
3. **`combine_verdicts` ignores `ALLOW_WITH_CONDITIONS` interactions with `ESCALATE`.** Currently any ESCALATE outranks any ALLOW_WITH_CONDITIONS, which is the right default for safety but loses information: the consumer might want to approve the escalation *with* a condition. The DecisionRecord captures conditions, so a real implementation could reconstruct this, but `combine_verdicts` does not.
4. **The PAA's `policy_version` was originally hardcoded.** That was a real defect. It has been fixed: the PAA now receives the loaded `packs` registry and looks up the actual YAML version. A test (`test_decision_record_carries_audit_fields`) now asserts the recorded version matches the loaded pack. This is the one item flagged in an earlier draft of this review that was actually patched, rather than just documented — the rest remain accurate as known issues.

## Bypass risks

1. **`ProposedAction.model_construct`** lets a caller skip pydantic validation. The bypass test demonstrates that the engine catches this via `_validate_action`, but the catch is `isinstance(action.action_type, ActionType)` — a sufficiently determined caller can construct an `ActionType` member that happens to match an enum name but with mutated payload. The evaluator would then run normally. The catch is shallow.
2. **Scenarios may write directly to the trace store** via `store.record_event(...)`. This is intentional (non-decision context events use it), but a scenario could in principle write a `decision` event with a fabricated `DecisionRecord` payload. The store does not validate that decision events originate from the PAA. A signed record would close this; the demo does not.
3. **Approval resolver is fully trusted.** The engine asks the resolver and accepts the answer. The resolver could be malicious or buggy. A real system would need an out-of-band acknowledgement.

## Missing tests

1. No test for **trace hash integrity over a tampered file**. A test that loads a tampered JSONL and asserts the chain breaks would tighten the demo claim.
3. No test for **concurrent scenarios** writing to the same `TraceStore`. The store is not thread-safe and there is no test that catches this regression.
4. No fuzz testing on `ProposedAction.payload` shapes. The evaluator handlers assume types; a malformed payload would raise rather than return a default-deny verdict in some cases. (Verified by reading the code; not exercised by a test.)
5. No test for **a policy pack that opts into an action with zero rules**. The current loader would accept it; the PAG would return ALLOW because there are no verdicts to combine. This contradicts the default-deny stance — `combine_verdicts` returns BLOCK only on empty verdicts at the *combined* level, but a single empty pack would contribute no verdicts and a second non-empty pack would carry the decision. This is plausibly correct but unspecified.

## What would need hardening before public release

In addition to the items in `risk-and-limitations.md`:

- A property-based test pass over `combine_verdicts` for every (decision1, decision2) combination.
- A README "Threat model" subsection that distinguishes "control plane for delegated commerce" from "secure sandbox for untrusted agents". The repo currently leans on the operating-model doc; a one-paragraph caveat in the README would be safer.
- An explicit `THIRD_PARTY_NOTICES.md` if dependencies change.
- A pinned `requirements.lock` or `uv.lock` for reproducible scenario traces.

## Which README claims were deliberately softened

- The README does not say "production-ready" or "enterprise-grade" anywhere. The hype-word ban was followed.
- The README does not claim the trace chain is non-repudiation. It says "demo mechanism" in the risk doc and the trace store source.
- The README does not claim cross-framework portability. It limits scope to the action types and the scripted scenarios.
- The README does not claim that bypass is impossible. It says the engine has no public bypass API. The bypass tests assert structural properties; they do not assert sandbox-grade isolation.

## What is simulated versus real

| Element | State |
| --- | --- |
| Consumer reasoning | Static profile + delegation |
| Consumer agent | Real Python class with governed wrappers |
| Retailer catalogue | Static in-memory list |
| Retailer confirm_order | Returns a dict |
| Payment | Action recorded; no processor |
| Approval channel | Scripted resolver in scenarios |
| Trace store | Real append-only JSONL with demo hash chain |
| Policy packs | Real YAML, parsed and validated |
| PAG / ATM / PAA | Real, exercised end-to-end by tests |
| Engine boundary | Real, asserted by bypass tests |

The engine, evaluator, trace store, and PAG/ATM/PAA stages are the parts a hostile reviewer should focus on. Everything else is intentionally scenery.
