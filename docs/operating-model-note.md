# Operating model note

## A control plane for delegated commerce

Most agentic commerce demos are built around the data plane: catalogue search, ranking, conversational checkout, dynamic pricing. Those are necessary, but they are not sufficient. The missing piece is a **control plane** that intercepts the moment an agent moves from reasoning to acting.

This repository is one shape of that control plane. The contract it implements is:

> No consequential action on a consumer's behalf executes outside the governance layer, and every governed action produces evidence sufficient to audit it after the fact.

Concretely, the control plane is the `GovernanceEngine`. The data plane is everything else - the consumer agent's reasoning, the retailer agent's catalogue, the offer ranking. The two are coupled only through the engine.

## Why governance sits between intent and execution

A common failure mode in agent design is to bolt governance onto the reasoning layer: prompt-level guardrails, rejection sampling, model-side refusal training. These help, but they are statistical defences against a moving target. They do not produce evidence, they do not bind action to delegated authority, and they cannot tell a dispute reviewer *why* an action did or did not happen.

A second failure mode is to bolt governance onto the execution surface: retailer-side fraud checks, payment-processor risk scoring. These help, but they see only the residue of the agent's reasoning and cannot interpret a consumer's delegation.

The right place is between the two. The agent reasons freely. The moment it proposes a consequential action, that action is structured (`ProposedAction`), evaluated against the consumer's delegation, and either allowed, blocked, escalated, or allowed with conditions. The same code path is the source of evidence and the source of enforcement.

## Why delegated authority needs evidence and escalation

Three properties make delegated commerce different from consented commerce:

1. **Asymmetric speed.** The agent can attempt a hundred consequential actions in the time the consumer needs to look at one. Per-action consent is impossible. Bounded *standing* consent (the delegation) is necessary; runtime enforcement of those bounds is what makes it survive contact with reality.
2. **Asymmetric reversibility.** Some actions (data sharing, identity disclosure, payment) cannot be cleanly reversed even when reversed in the ledger sense. The `reversible_flag` on every `DecisionRecord` is there so that audit and insurance can treat these differently.
3. **Asymmetric blame.** When something goes wrong, three parties will dispute who is accountable: the consumer, the agent vendor, the retailer. A structured trace per action is the only durable answer. A chat transcript is not.

Escalation exists for the actions that sit exactly at the authority boundary - substitutes outside tolerance, totals above the auto-buy threshold, retailers asking for more data than permitted. These are the moments where the *right* answer is not "machine decides" or "human decides" but "machine escalates with full context, human decides quickly, record both halves".

## What the consumer is actually delegating

Under this model, the consumer is delegating three things:

- **Mission execution** - the agent may search, rank, and propose actions.
- **Authority within explicit bounds** - the agent may act on those proposals when they fall within the delegation.
- **Escalation rights** - the agent may interrupt the consumer when an attractive option falls *outside* the delegation, and the consumer can extend authority for that single action.

The consumer is *not* delegating accountability, identity, payment instruments outside their token boundary, or the right to set the delegation's terms. The governance layer is the surface that makes this distinction concrete.

## Reading this as a board-level artifact

If you are evaluating whether to invest in an agentic commerce capability, the questions this repository helps you ask are:

1. Where is your action boundary, and is it a real boundary?
2. Can the agent in your stack reach a retailer side effect without traversing it?
3. For any allowed action in the last 24 hours, can you produce the policy version, the facts used, the approval outcome, and the rationale in under a minute?
4. What is your default behaviour when a required policy input is missing?

If the answers are unclear, the operating model is unclear. This repository proposes a shape for what "clear" looks like.
