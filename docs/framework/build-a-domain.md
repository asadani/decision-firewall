# Build a domain

Run `firewall init my-decision-app`, then `python my-decision-app/run.py`. The generated example runs outside this repository after installation and demonstrates simulated execution, review, replay and receipt verification.

1. Define a Pydantic action model, preferably inheriting `core.Record` to forbid extra fields. Put business parameters here, never actor identity or permissions. Use strict integers for money/counts. Submission persists a normalized copy.
2. Implement `resolve(proposal) -> Evidence`. Read trusted sources, provide material versions and list required unavailable facts in `missing`. The resolver runs again before execution. Model assertions are not evidence.
3. Implement `evaluate(context) -> Decision`. Read action, evidence, assessment signals, review and resource usage. Use `context.now` for deterministic time-sensitive replay. Avoid I/O, wall-clock calls, randomness or mutation in policy code.
4. Check hard constraints before honoring approval. Return `REQUIRE_REVIEW` for discretionary decisions and `REQUIRE_EVIDENCE` for missing facts. Exceptions become evaluation errors, not denials. Unavailable assessments cannot automatically authorize.
5. Return constraints and optional integer resource claims. Executors must advertise and enforce every constraint. Unknown constraints fail closed. Claims use stable domain-local keys; date-qualified keys implement daily budgets.
6. Register a `DomainPack` with explicit implementation/policy versions, configuration and executor. Instantiate `DecisionFirewall(home, domains=[pack])` in trusted startup code. No core changes are required.

The starter has a review rule and a hard destination restriction. Your tests should prove review cannot waive that restriction, stale evidence invalidates permits, repeated dispatch does not duplicate effects and ambiguous failures reconcile safely.

Read `domains/refunds/pack.py` for resource claims and `domains/access/pack.py` for a non-financial schema. These are demonstration policies, not universal business rules.

The CLI accepts `firewall framework --plugin installed_module:create_domain ...`; the factory receives the runtime directory and returns a `DomainPack`. This imports trusted application code. Never construct that option from model output or untrusted requests. Automatic discovery and remote plugin installation are not implemented.
