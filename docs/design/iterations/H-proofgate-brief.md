# ProofGate — brief (from the product owner, verbatim, 2026-11-22)

Implement ProofGate, a risk-adaptive, claim-level data validation layer in the existing DealProof backend. Do not rewrite the architecture or DecisionFlip.

- Store entity ID, claim type, original value, units, period, source, source field, record date and retrieval time.
- Compute **Evidence Assurance** (a heuristic, not a truth probability) and
  **Verification Priority = 0.45·materiality + 0.30·(100 − evidence assurance) + 0.15·DecisionFlip sensitivity + 0.10·staleness**.
- Trigger validation at priority ≥ 65, or **always** for: uncertain identity, conflicting sources, mandatory criteria, harmful allegations and consequential actions.
- Use claim-specific sources: original funding announcements, Entrackr/Inc42; relevant professional records for people; qualified LinkedIn data for headcount; authorized legal registries for legal identity; official financials for revenue.
- Verify entity, value, unit, period, and claim semantics.
- Do not count syndicated reporting as independent sources, average conflicting values, or auto-verify solely from a score.
- Limit to two targeted parallel lookups with configurable time and credit budgets; retain missing or uncertain results as Cannot verify / Not checked.
- Persist evidence, usage, decisions, policy versions and restart-safe state.
- Connect to DecisionFlip so decision-critical claims are checked first and only affected outcomes are recalculated.
- Tests: mismatch, freshness, wrong entity, different periods, duplicate-source origin, source failure, budget exhaustion and restart.
- UI shows claimed value, evidence, assurance, priority, verdict, cost and latency.
- Preserve current product functionality.

## Related standing rule (owner, same day)
The agent must always search public sources itself for every claim category (financials, customers, partnerships, debt, litigation, compliance, facilities…) — exchange filings, annual reports, press releases, news, registries — regardless of uploads. Private/seller documents are only for what is not public. (Example failure: Mahindra, a listed company — its Q2 FY27 revenue claim came back "Cannot verify" without any search.) ProofGate's source layer is where this rule is implemented.

## Orchestration split
- **PG-A (Opus, backend core):** data model, assurance + priority, triggers, policy versioning, persistence, restart safety, DecisionFlip linkage (sensitivity in, affected-outcome recalculation out). Pushes its public interface first.
- **PG-B (Opus, source layer):** claim-specific targeted lookups (≤ 2 parallel per claim, time/credit budgets), listed-company detection, verification of entity/value/unit/period/semantics, origin de-duplication, never averaging, results feeding PG-A.
- **PG-UI (Fable):** claim row/detail shows claimed value, evidence, assurance, priority, verdict, cost, latency.
