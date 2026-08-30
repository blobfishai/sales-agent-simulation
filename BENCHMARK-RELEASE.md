# SalesBench-100 v3.4.0 — Release Qualification

SalesBench-100 v3.4 is a deterministic long-horizon sales-operations benchmark
with 100 synthetic employee requests across Salesforce, HubSpot, Gong, and a
seeded evidence room. Task IDs are `sb100-NNN-<slug>` and Harbor task names are
`blobfishai/sb100-NNN-<slug>`.

## Release status

The source and locally generated v3.4 candidate pass the complete qualification
suite. Public v3.4 publication is recorded only after the merged source is
built, uploaded, and downloaded again. Until that happens, these links may
still show the prior public release:

- Source: <https://github.com/blobfishai/sales-agent-simulation>
- Harbor dataset: <https://hub.harborframework.com/datasets/blobfishai/salesbench-100>
- Hugging Face dataset: <https://huggingface.co/datasets/SamuelChien821/salesbench-100>
- Interactive benchmark: <https://blobfish.ai/benchmarks/salesbench-100>

## What v3.4 changes

v3 gave every task an authored causal rule and task-specific CRM transitions;
v3.3 rolled the atomic criteria into weighted semantic milestones. v3.4 makes
the *decision* itself graded, the way an operating owner would defend it:

- **Costed, dated, authority-tagged alternatives.** Every task grades a
  decision model with three alternatives — the standard operations queue
  (`APPROVED`, recommended), the expedited exception queue
  (`ADDITIONAL_APPROVAL_REQUIRED`: the per-record fee needs Finance Deal Desk
  sign-off), and a full portfolio hold (`AVAILABLE_NOT_RECOMMENDED`: waits for
  the next register refresh and re-reviews every key). Each alternative carries
  an exact outcome date computed across the documented Monday-to-Friday
  calendar with published blackout dates, a whole-USD incremental cost, an
  authority status, a signed variance against the review meeting, and an
  `ON_TIME`/`LATE` status. Outcomes are derived from the supported-record count
  produced by the control join — they appear nowhere in the evidence room.
- **Control-date variance.** The review meeting date (`business_need_date`) is
  documented in two independent sources (the review request email and the
  approval record) and never in the employee prompt. The verifier grades the
  recommended outcome's signed `outcome_vs_control_days`, an honest
  `decision_timing_status` (91 tasks land ON_TIME, 9 honestly LATE), the
  expedite's days saved, and whether escalation to Finance is recommended.
- **Split calendar evidence.** Queue capacity, expedite fee, re-review charge,
  blackout dates, review date, and refresh date are scattered across six
  material sources (collaboration threads, the approval record, the review
  request, the current authority register, and audit evidence), with superseded
  figures planted in the retired register and the former owner's email. No
  single source carries every input; 16–18 records per task are now material.
- **Guaranteed authority and control-window holds.** Every task now holds at
  least one approval-pending record (the scope the current approval excludes)
  and at least one superseded-period record, and grades the approval-pending
  count in the decision summary.
- **Milestones with published atomic evidence.** The 15 weighted semantic
  milestones (including the new `decision.alternatives`) total 100 points, and
  all 338–457 executable atomic criteria per task are published in
  `rubric_criteria`, each tagged with the milestone it rolls into; the released
  rubric and the executed verifier report agree criterion for criterion.
- **Eleventh negative control.** `wrong_alternative` reaches the exact CRM
  state but relabels the hold alternative as on time, reports the expedite fee
  as approved, and flips the timing status; it is rejected on all 100 tasks.

## Release contents

- `salesbench/catalog.py`: 100 hand-authored employee scenarios across 10
  workflow families.
- `salesbench/action_specs.py`: 100 explicit provider object/field transitions.
- `salesbench/decision_specs.py`: 100 distinct causal observation, authority,
  and derivation rules.
- `salesbench/generation.py`: deterministic portfolio data, split evidence,
  natural requests, the graded decision model with costed alternatives,
  exact holds, and reference outputs.
- `salesbench/runtime/world.py`: 35 tools on four vendor-separated MCP surfaces
  with causal trace verification and capability-protected scoring.
- `salesbench/runtime/scoring.py`: exact state, decision, alternative, held-case,
  readback, collateral-safety, and human-handoff scoring with the published
  criterion-to-milestone mapping.
- `salesbench/builder.py`: Harbor 1.4 packs, Hugging Face output, and
  release-blocking leakage, diversity, partition, decision-model, and
  trajectory audits.
- `salesbench/run_suite.py`: oracle, deterministic replay, and eleven
  adversarial controls for every task.

## Executed v3.4 qualification

| Check | Result |
|---|---:|
| Oracle trajectories | 100/100 passed |
| Exact deterministic replays | 100/100 reports matched |
| Eleven negative controls | 1,100/1,100 correctly rejected |
| Total qualification executions | 1,300 |
| Unit tests | 39 passed |
| Workflow families | 10, with 10 tasks each |
| Prompt duplicates | 0 |
| Maximum prompt similarity | 0.272727 five-shingle Jaccard |
| Agent-visible evidence assets | 2,800 total; 2,800 unique SHA-256 digests |
| Evidence bytes | 26,572,432 total; 4,508-byte median |
| Native formats | 11; PDF and XLSX structures parse successfully |
| Costed, dated, authority-tagged alternatives | 300/300 (3 per task) |
| Unauthorized + inferior alternative per task | 100/100 |
| Business-need date in two sources / in a prompt | 100/100 / 0 |
| Approval-pending and superseded-period holds | 100/100 each |
| Option-outcome or option-cost leaks | 0 |
| Precomputed answer findings | 0 |
| Single-file complete-transition findings | 0 |
| Selected-option leaks | 0 |
| Calculated-amount leaks | 0 |
| Authored causal rule signatures | 100/100 unique |
| Ordered tool-name sequences | 100/100 unique |
| Semantic action graphs | 100/100 unique |
| Maximum semantic sequence match | 0.773006 |
| Reference trajectory | 75–114 calls; 9,250 total |
| Semantic milestones per task | 15, totaling 100 points |
| Deterministic atomic criteria per task | 338–457, each published with its milestone |
| Missing-readback false accepts | 0/100 |
| No-op nonzero rewards | 0/100 |

The eleven adversarial controls are answer-only, state-only, incomplete
evidence, write-before-read, missing readback, unauthorized write, unauthorized
delete, wrong derived value, wrong decision option, misreported alternatives
(`wrong_alternative`), and pristine no-op. Each control is executed
independently for all 100 tasks.

Machine-readable evidence is generated at:

- `dist/salesbench-100/reports/build.json`
- `dist/salesbench-100/reports/qualification.json`

## Real-model results

No v3.4 model score is claimed. Historical runs from prior releases are not
comparable and must not appear as v3.4 leaderboard rows. A row may be published
only after the model is run against the exact v3.4 artifact with coverage,
harness, and artifact-digest provenance.

## Reproduce

```bash
git clone https://github.com/blobfishai/sales-agent-simulation.git
cd sales-agent-simulation
uv run --python 3.12 --with pytest python -m pytest -q
uv run --python 3.12 python -m salesbench.builder
uv run --python 3.12 python -m salesbench.run_suite
```

After v3.4 is published, the exact Harbor artifact can be exercised with:

```bash
harbor run -d blobfishai/salesbench-100@v3.4.0 -a oracle -n 1
```

## Contract fidelity and limits

Tool names and request schemas are pinned to immutable real implementations or
official API specifications; see `research/API-CONTRACTS.md`. Salesforce,
HubSpot, Gong, and filesystem remain separate MCP endpoints. Gong is read-only.

The release does not claim an authenticated hosted `tools/list` comparison:
`authenticated_hosted_tools_list_compared` remains `false`. Offline response
envelopes mirror documented shapes but are not byte-for-byte tenant responses.
All benchmark people, companies, records, and commercial facts are synthetic.

Public gold, verifier metadata, and oracle traces are inspection artifacts; they
are never mounted into the agent-visible task workspace. Open-book scores must
be labeled separately from sealed leaderboard evaluations.
