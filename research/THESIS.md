# SalesBench-100 thesis

## Evaluation claim

SalesBench-100 measures whether an agent can complete portfolio-scale sales and
revenue-operations work across fragmented systems while preserving policy,
provenance, and neighboring records. It does not grade sales-copy style or use a
model judge.

The unit of difficulty is a connected business workflow, not a single API call.
Each task begins with records distributed across Salesforce, HubSpot, Gong, and
an evidence room. The systems intentionally disagree in realistic ways: stale
stages, duplicate contacts, delayed syncs, outdated next steps, conflicting
owners, unmatched activity, and superseded policies. Source-of-truth rules vary
by field and workflow.

## Ten workflow families

1. Forecast reconciliation and commit inspection.
2. Stalled-pipeline cleanup and next-step recovery.
3. Gong-to-CRM discovery and action-item reconciliation.
4. Duplicate detection, migration, and source-of-truth repair.
5. Lead qualification, enrichment, and territory routing.
6. Renewal, expansion, and customer-success handoff.
7. Discount approval, quote governance, and close readiness.
8. Account planning, stakeholder mapping, and executive preparation.
9. Sequence, consent, deliverability, and activity compliance.
10. Cross-CRM audit, cutover, and post-migration reconciliation.

Each family has ten independently authored company/deal spines. Generation may
fill deterministic records and distractors, but it may not create the hundred
tasks by swapping names in one prompt template.

## World invariants

- Gong is read-only. Its evidence can justify mutations elsewhere, never a Gong mutation.
- Salesforce and HubSpot permissions differ by role and field.
- A field-level source-of-truth map controls conflict resolution.
- Every mutation is attributable to one MCP call and one task-specific reason.
- Unrequested rows, ownership, amounts, stages, consent flags, and close dates remain unchanged.
- Deliverable facts must be recoverable from the task's seeded evidence.
- Verification is pure and deterministic: no model, network, clock, locale, or randomness.

## Long-horizon rule

Every accepted oracle trajectory must contain at least 100 successful,
task-relevant MCP interactions. The builder rejects repeated no-op calls,
duplicate reads of the same asset, and calls unrelated to a scored criterion.
The intended workload is portfolio-scale, so the depth comes from inspecting
many linked accounts, calls, activities, policies, and conflicts rather than
padding a single-record workflow.

