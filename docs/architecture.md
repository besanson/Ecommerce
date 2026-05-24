# Architecture

This document describes the module responsibilities and the SARC mapping. It is intended for engineers who need to inspect, extend, or audit the governance layer.

## High level

```
Consumer (human)
   │
   ▼
ConsumerAgent  ──── proposes ProposedAction ────►  GovernanceEngine.govern(...)
                                                        │
                                                        ├── PAG (Pre-Action Gate)
                                                        │     evaluates policy packs
                                                        │     emits combined Decision
                                                        │
                                                        ├── (optional) ApprovalService
                                                        │     when Decision == ESCALATE
                                                        │
                                                        ├── ATM (Action-Time Monitor)
                                                        │     verifies approval, conditions, drift
                                                        │     authorizes / aborts the side effect
                                                        │
                                                        ├── side_effect()   ←  only if ATM authorizes
                                                        │
                                                        └── PAA (Post-Action Audit)
                                                              builds DecisionRecord
                                                              hands to TraceStore
TraceStore  (append-only JSONL with prev_hash chain)
   │
   ▼
Forensics view (Streamlit)
```

## Module responsibilities

| Module | Responsibility | Hard rules |
| --- | --- | --- |
| `gacct.domain` | Pydantic models for consumer, delegation, products, actions, decisions, policies, approvals, trace events | Pure data; no I/O |
| `gacct.policy.loader` | Load and validate YAML policy packs | Strict; raises on malformed packs |
| `gacct.policy.evaluator` | Rule-kind handler registry; combine rule verdicts into a Decision | Unknown rule kinds default to BLOCK |
| `gacct.governance.pag` | Run the applicable packs for an action; combine into a single Decision | No side effects; no I/O |
| `gacct.governance.atm` | Validate approval state, conditions, and drift at execute time; authorize or abort | Cannot mutate the Decision; only aborts |
| `gacct.governance.paa` | Construct the canonical `DecisionRecord` and emit it via the recorder callback | Only writer of DecisionRecords |
| `gacct.governance.engine` | Mandatory entry point; orchestrates PAG → approval → ATM → side_effect → PAA | No `force_execute`; refuses unknown action types |
| `gacct.agents.consumer_agent` | Wraps each consequential operation as a `ProposedAction` and calls `engine.govern(...)` | No direct retailer side effects |
| `gacct.agents.retailer_agent` | Simulated retailer surface: catalogue, offers, confirmation | Does not import `gacct.governance` |
| `gacct.approvals.service` | Captures approval requests and resolves them via a pluggable resolver | Resolver is dependency-injected |
| `gacct.trace.store` | Append-only JSONL with per-scenario hash chain | Single sequence per `scenario_id` |
| `gacct.scenarios` | Scripted demo paths + a CLI runner | Generates `examples/traces/*.jsonl` |
| `app/streamlit_app.py` | Operator UI - five sections | Read-only over traces |

## Data curation layer

Before any SARC stage runs, the agent's data foundation must itself be complete and fresh. The data curation layer makes this explicit.

**`ConsumerContext`** (`gacct.domain.context`) is the structured, versioned data foundation an agent depends on. It carries two halves:

- `delegation_parameters` - the bounded authority the consumer has granted (budget ceilings, auto-renew thresholds, approved-service lists with a version timestamp, billing-data whitelists, substitution tolerances).
- `data_baseline` - the agent's last-known facts about the world (e.g. last-confirmed monthly prices, last-confirmed billing periods). These are the facts the agent reasons over when it proposes an action.

`context_version` is a monotone integer that increments whenever any baseline field is updated. Every `ProposedAction` carries `context_id + context_version`, and `PostActionAudit` passes these through to the resulting `DecisionRecord`. The audit trail therefore proves *which* data snapshot was active when each decision was made.

**`DataContextValidator`** (`gacct.domain.context`) is a pre-PAG gate. For every consequential action type it lists the keys the `ConsumerContext` must carry to be governable. If the context is missing required fields - for example a `renew_subscription` proposal whose context omits `approved_services_version` - the validator returns the new verdict `Decision.BLOCK_MISSING_CONTEXT` with the structured list of missing fields. PAG is never engaged for that action; the resulting `DecisionRecord` records `pag_status = "not_reached"`, the missing-fields list, and the context version that failed validation.

Why this is a governance moment and not a developer error:

- **Stale or incomplete context is itself a governance failure mode.** A capable agent operating against a partial baseline will produce confident but wrong actions. The control plane must refuse rather than silently allow.
- **It makes the data dependency auditable.** When a BLOCK_MISSING_CONTEXT decision is written into the trace, a reviewer can see exactly which fields were missing, on which context version, for which proposed action.
- **It keeps the agentic and governance pillars honest about pillar 2.** Without the validator, the demo would let agentic capability + runtime governance claim the win whenever the data happens to be fresh; with the validator, the data foundation is forced into the same audit surface.

The architecture flow including this stage:

```
ProposedAction
   │
   ▼
DataContextValidator                 ← pre-PAG gate (pillar 2)
   ├─ context complete & fresh  → continue to PAG
   └─ context missing fields    → BLOCK_MISSING_CONTEXT, record, stop
   │
   ▼
PAG → ATM → PAA                      ← SARC governance (pillar 3)
```

## SARC mapping

| SARC stage | Implementation | Output |
| --- | --- | --- |
| Pre-Action Gate | `gacct/governance/pag.py` | `PAGOutcome` with combined Decision, per-rule verdicts, packs evaluated, facts used |
| Action-Time Monitor | `gacct/governance/atm.py` | `ATMState` with `aborted`, `abort_reason`, `approval_outcome`, `conditions_satisfied` |
| Post-Action Audit | `gacct/governance/paa.py` | `DecisionRecord` (persisted to trace store; includes `context_id` and `context_version`) |

The engine wires these together. The flow is fixed; agents and scenarios cannot reorder it.

## Where enforcement is mandatory

Every method on `ConsumerAgent` that touches retailer state, payment state, or consumer data is wrapped in `engine.govern(...)`. The retailer-side `confirm_order` side effect is passed as a callable into the engine - the engine decides whether to invoke it. There is no API in `ConsumerAgent` that takes a retailer object and bypasses the engine.

The `tests/test_bypass.py` suite asserts these structural properties:

- `GovernanceEngine` has no `force_execute` / `skip_governance` / `bypass` attribute.
- `ConsumerAgent` does not call `retailer.confirm_order` outside a side_effect lambda passed to the engine.
- `RetailerAgent` does not import `gacct.governance`.
- The only public action method on the engine is `govern`.

These tests catch refactors that would silently undo the boundary.

## Where orchestration ends and governance begins

| Orchestration (scenario code) | Governance (engine) |
| --- | --- |
| Chooses which retailer to query | Decides whether an action against that retailer may execute |
| Builds the shortlist of offers | Decides whether an order against the chosen offer may execute |
| Schedules approval prompts in demo mode | Refuses to execute escalated actions without an `APPROVED` outcome |
| Records non-decision context (mission opened, offer received) | Writes the canonical `DecisionRecord` |

Orchestration freely walks the agent through the mission. The engine binds the mission's consequences to the delegated authority.

## Adding a new policy

1. Add a YAML file to `policies/`. It must declare `pack_id`, `version`, `applies_to_actions`, and one or more `rules`.
2. Each rule's `kind` must have a registered handler in `gacct/policy/evaluator.py`. Add one if needed.
3. Add tests in `tests/test_pag.py` that exercise the allow and the violation paths.

Unknown `kind` values default to BLOCK; this is intentional so that an incomplete deployment cannot silently allow.

## Adding a new action type

1. Add a member to `ActionType` in `gacct/domain/actions.py`.
2. Add a method on `ConsumerAgent` that constructs the `ProposedAction` and calls `engine.govern(...)`.
3. Decide which policy packs should opt in to the new action type (`applies_to_actions` in YAML).
4. Add tests.

The engine refuses unknown action types at the boundary (`GovernanceBypassError`), so omitting step 2 is detectable.
