# SalesBench-100 v3.0.0 — Release Qualification

SalesBench-100 v3 is a deterministic long-horizon sales-operations benchmark
with 100 synthetic employee requests across Salesforce, HubSpot, Gong, and a
seeded evidence room. Task IDs are `sb100-NNN-<slug>` and Harbor task names are
`blobfishai/sb100-NNN-<slug>`.

## Release status

The source and locally generated v3 candidate pass the complete qualification
suite. Public v3 publication is recorded only after the merged source is built,
uploaded, and downloaded again. Until that happens, these links may still show
the prior public release:

- Source: <https://github.com/blobfishai/sales-agent-simulation>
- Harbor dataset: <https://hub.harborframework.com/datasets/blobfishai/salesbench-100>
- Hugging Face dataset: <https://huggingface.co/datasets/SamuelChien821/salesbench-100>
- Interactive benchmark: <https://blobfish.ai/benchmarks/salesbench-100>

## What v3 changes

Earlier releases exposed complete machine-readable decisions and reused one
semantic procedure. v3 replaces that shortcut with 100 authored causal rules
and 100 task-specific CRM transitions.

Each task starts with a high-level employee request. For every one of 16
portfolio records, the agent must correlate six independently mounted evidence
roles:

1. identity crosswalk,
2. operating observation,
3. controlling authority,
4. governed transition,
5. live-system corroboration, and
6. exception record.

The 12 assets in each task are multi-row source exports, not 96 tiny pseudo-files.
They use text-native Markdown, CSV, JSON, EML, HTML, XML, and text formats and
range from 5,467 to 39,650 bytes. The release does not rename text as PDF or
XLSX and makes no binary-document claim.

No mounted business file identifies the selected option or contains a complete
record/field/value/approval transition. Calculated amounts are absent from the
evidence room. The agent must derive them from inputs split across observations,
authority, policy, identity, provider state, and exception evidence.

Supported work varies from 5 to 12 changes per task. The remaining portfolio
records must be reported as exact held cases with their blocking condition,
sources, owner, deadline, and next step. The verifier rejects an answer-only
shortcut, a state-only shortcut, a correct write before investigation, and a
successful mutation acknowledgement that is never read back.

## Release contents

- `salesbench/catalog.py`: 100 hand-authored employee scenarios across 10
  workflow families.
- `salesbench/action_specs.py`: 100 explicit provider object/field transitions.
- `salesbench/decision_specs.py`: 100 distinct causal observation, authority,
  and derivation rules.
- `salesbench/generation.py`: deterministic portfolio data, split evidence,
  natural requests, decision alternatives, exact holds, and reference outputs.
- `salesbench/runtime/world.py`: 35 tools on four vendor-separated MCP surfaces
  with causal trace verification and capability-protected scoring.
- `salesbench/runtime/scoring.py`: exact state, decision, held-case, readback,
  collateral-safety, and human-handoff scoring.
- `salesbench/builder.py`: Harbor 1.4 packs, Hugging Face output, and
  release-blocking leakage, diversity, partition, and trajectory audits.
- `salesbench/run_suite.py`: oracle, deterministic replay, and ten adversarial
  controls for every task.

## Executed v3 qualification

| Check | Result |
|---|---:|
| Oracle trajectories | 100/100 passed |
| Exact deterministic replays | 100/100 reports matched |
| Ten negative controls | 1,000/1,000 correctly rejected |
| Total qualification executions | 1,200 |
| Unit tests | 28 tests plus 35 subtests passed |
| Workflow families | 10, with 10 tasks each |
| Prompt duplicates | 0 |
| Maximum prompt similarity | 0.272727 five-shingle Jaccard |
| Multi-record evidence assets | 1,200 total; 1,200 unique SHA-256 digests |
| Evidence bytes | 20,266,114 total; 14,255-byte median |
| Precomputed answer findings | 0 |
| Single-file complete-transition findings | 0 |
| Selected-option leaks | 0 |
| Calculated-amount leaks | 0 |
| Authored causal rule signatures | 100/100 unique |
| Ordered tool-name sequences | 100/100 unique |
| Semantic action graphs | 100/100 unique |
| Maximum semantic sequence match | 0.885246 |
| Reference trajectory | 56–91 calls; 7,205 total |
| Deterministic verifier criteria | 301–420 per task |
| Missing-readback false accepts | 0/100 |
| No-op nonzero rewards | 0/100 |

The ten adversarial controls are answer-only, state-only, incomplete evidence,
write-before-read, missing readback, unauthorized write, unauthorized delete,
wrong derived value, wrong decision option, and pristine no-op. Each control is
executed independently for all 100 tasks.

Machine-readable evidence is generated at:

- `dist/salesbench-100/reports/build.json`
- `dist/salesbench-100/reports/qualification.json`

## Real-model results

No v3 model score is claimed. Historical runs from prior releases are not
comparable and must not appear as v3 leaderboard rows. A row may be published
only after the model is run against the exact v3 artifact with coverage, harness,
and artifact-digest provenance.

## Reproduce

```bash
git clone https://github.com/blobfishai/sales-agent-simulation.git
cd sales-agent-simulation
uv run --python 3.12 --with pytest python -m pytest -q
uv run --python 3.12 python -m salesbench.builder
uv run --python 3.12 python -m salesbench.run_suite
```

After v3 is published, the exact Harbor artifact can be exercised with:

```bash
harbor run -d blobfishai/salesbench-100@v3.0.0 -a oracle -n 1
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
