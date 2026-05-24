# Risk and limitations

This is a pre-production reference implementation. It is honest about what it does not do.

## What is simulated

- **Retailer agent.** The `RetailerAgent` returns offers from a static in-memory catalogue, decides which consumer data it would like, and produces a deterministic confirmation. There is no network call, no inventory check, no real fulfilment commitment.
- **Payment.** The `use_payment_token` action passes an amount and a retailer id. No payment processor is contacted. The payment token is a string.
- **Approval channel.** The `ApprovalService` resolves through a scripted policy in scenarios. In a real deployment this would be an out-of-band, signed, asynchronous channel.
- **Consumer.** The consumer is a static profile and delegation; there is no live human.

Wherever a real integration would be required, the code is structured so that the existing engine boundary still mediates it.

## What is not proven

- **Security.** The repository implements a logical boundary, not a security boundary. It does not address:
  - prompt-injection that steers the agent's reasoning to propose harmful actions (the boundary catches the proposal, but it relies on the action being structured correctly)
  - identity binding between consumer and consumer agent
  - cryptographic separation of the payment token from the agent's process
  - tamper resistance of the trace store at the filesystem level
- **Legal sufficiency.** The trace is structured for human and automated review, but it is not a substitute for a jurisdiction-specific consent and audit framework.
- **Non-repudiation.** The per-scenario hash chain in `TraceStore` is a demo mechanism. It detects ordinary file corruption and accidental editing. It does not prevent an adversary with write access from rewriting the entire chain. Production non-repudiation would need signed records (per-action signature with a key not accessible to the agent), an external timestamp authority, and append-only storage with a third-party witness.
- **Universal coverage.** Governance only applies to action types enumerated in `ActionType`. An action class not in the enum is refused at the boundary (good), but the design relies on enumeration being complete (a maintenance burden).
- **Cross-agent interoperability.** The retailer agent in this demo is co-located. Real agent-to-agent commerce will need a shared action vocabulary and a way to convey delegated authority across organizational boundaries.

## Known blind spots

- **Multi-step compound actions.** The current design treats each consequential step independently. A real mission might require the engine to reason about *plans* (sequence of actions that together exceed an authority), not just individual actions. The current evaluator does not see plans.
- **Latency.** The engine is synchronous and in-process. A real out-of-band approval breaks the assumption that a side effect can be invoked in the same call as PAG. The interface is ready for it (the side effect is a callable), but the orchestration would need refactoring.
- **Concurrency.** The trace store is single-process and not thread-safe.
- **Policy authoring.** Policy packs are YAML and the evaluator is hand-written. A larger deployment would need a policy authoring tool, conflict detection between packs, and dry-run replay over historical traces.
- **Approval UX.** The approval channel is reduced to a callable. A real approval surface has its own threat model (phishing, time pressure, fatigue) that this repository does not address.

## What would need hardening before public production

1. **Signed `DecisionRecord`s** with rotation, and a verifier that reads any trace and asserts integrity.
2. **External approval channel** with out-of-band notification, mutual TLS to the consumer device, and explicit per-action confirmation tokens.
3. **Adversarial test suite** that simulates prompt-injection attempts against the consumer agent and asserts the governance layer still refuses unauthorized actions. Add fuzzing of `ProposedAction.payload` shapes.
4. **Policy authoring system** including conflict detection, replay over a corpus of historical traces, and per-policy SLAs.
5. **Per-tenant isolation** of trace stores, policy packs, and approval channels.
6. **Operational telemetry** distinct from the audit trace (latency, decision throughput, rule hit distribution).
7. **Legal & compliance review** of the trace shape with respect to the jurisdiction's data protection regime; `acting_on_behalf_of` may itself be PII.

## What this repository deliberately does *not* claim

- That governing wrapped action boundaries equals governing the agent.
- That the absence of a `force_execute` API on the engine is, by itself, a defence against a hostile runtime that imports and calls the retailer agent directly. The bypass tests in `tests/test_bypass.py` reduce, but do not eliminate, this risk.
- That the rule kinds shipped here are sufficient for a real consumer mission. They are sufficient for the seven moments in the subscription scenario; the engine itself is action-type agnostic.
- That allow / block / escalate / allow-with-conditions is the only verdict surface that makes sense for delegated commerce. It is *a* surface that handles the actions in the scenario; richer surfaces are plausible.
