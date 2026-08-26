# SalesBench-100 v1.0.1 — Release Qualification

SalesBench-100 is a deterministic, long-horizon sales-agent benchmark with
100 original revenue-operations tasks across Salesforce, HubSpot, Gong, and a
seeded filesystem evidence room. Task IDs are `sb100-NNN-<slug>` and Harbor
task names are `blobfishai/sb100-NNN-<slug>`.

## Public release

- Source: <https://github.com/blobfishai/sales-agent-simulation>
- Harbor dataset: <https://hub.harborframework.com/datasets/blobfishai/salesbench-100>
- Hugging Face dataset: <https://huggingface.co/datasets/SamuelChien821/salesbench-100>
- Interactive benchmark: <https://blobfish.ai/benchmarks/salesbench-100>

Harbor release `v1.0.1` is dataset revision 2 (`0e615947326d`), with 100
task artifacts at revision 2 and both `v1.0.1` and `latest` tags. A fresh
explicit public download returned all 100 tasks. The representative downloaded
task was rebuilt from scratch and passed with reward `1.000`.

The public Hugging Face repository is ungated and contains 9,833 files at
commit `c8e07c201016fba371b4ff901d0894753a8cd96c`. A fresh Hub download of the
dataset card, qualification and model reports, representative task, and
163-event trajectory parsed successfully; the task and trajectory matched the
local release byte-for-byte.

## Release contents

- `salesbench/catalog.py`: 100 hand-authored business spines, balanced across
  10 workflow families.
- `salesbench/generation.py`: 96 realistic seeded documents per task, 16
  portfolio entities, 48 distractor records, 12 authorized changes, four
  protected control records, a 163-call reference trajectory, and deterministic
  gold deliverables.
- `salesbench/runtime/world.py`: 35 tools on four vendor-separated MCP surfaces
  (filesystem 6, Salesforce 11, HubSpot 15, Gong 3).
- `salesbench/runtime/scoring.py`: pure deterministic scoring over procedure,
  exact final state, change ledger, executive brief, and collateral safety.
  It makes no model, network, random, or wall-clock calls.
- `salesbench/runtime/server.py`: streamable-HTTP MCP endpoints at
  `/mcp/{filesystem,salesforce,hubspot,gong}`, plus `/health` and a verifier-only,
  capability-token-protected `/verify` endpoint. There is no solve endpoint.
- `salesbench/builder.py`: Harbor 1.4 task packs and dataset manifest, plus a
  Hugging Face release with task JSON/JSONL, seeded documents, world source,
  exact oracle trajectories, licenses, and evidence reports.
- `salesbench/run_suite.py`: two complete replays and six adversarial negative
  controls for every task, producing 800 deterministic executions.

The Harbor v1.0.1 images bake the seeded documents into both containers and
make the world copy read-only. That design is required for registry portability;
it replaces the task-relative bind mount used by the superseded v1.0.0 pack.

## Executed qualification

| Check | Result |
|---|---|
| In-process oracle | 100/100 passed, reward 1.0 |
| Exact deterministic replay | 100/100 reports matched |
| Six negative controls | 600/600 correctly rejected; 0 false accepts |
| Pristine no-op | exactly 0.0 on 100/100 tasks |
| Total qualification executions | 800 |
| Local unit tests | 14/14 passed |
| Prompt skeletons | 100/100 unique |
| Maximum pairwise prompt similarity | 0.762931 five-shingle Jaccard |
| Seeded documents | 9,600 total; 9,600 unique SHA-256 digests |
| Document depth | 5,252–6,692 bytes; 5,453-byte median |
| Reference trajectory | 163 successful calls per task; 16,300 total |
| Deterministic verifier criteria | 281 per task |
| Initial full Harbor run | 59 pass, 38 infrastructure exceptions, 3 contention nonpasses |
| Isolated Harbor recovery | all 41 initial nonpasses passed; combined 100/100 |
| Local forced-build packaging smoke | reward 1.0 |
| Fresh public v1.0.1 Harbor download | 100/100 artifacts downloaded |
| Public forced-build representative run | reward 1.0; 0 infrastructure errors |

The initial 100-task concurrent Harbor run deliberately remains in the
evidence. Its 38 exceptions (`RewardFileNotFoundError`, `RuntimeError`, and
`FileNotFoundError`) and three scored nonpasses were runner resource/contention
failures. Every affected task passed in a fresh isolated Harbor job. This is
reported as real infrastructure failure evidence, not hidden or relabeled as a
task failure.

The first public v1.0.0 artifact also remains recorded: it scored `0.165156`
because registry-built containers could not resolve a task-relative document
bind mount. v1.0.1 removed that mount, baked the data into the images, and then
passed both a forced local build and a forced build from a fresh public download.

Evidence:

- `reports/conformance.json`
- `reports/harbor-oracle-qualification.json`
- `reports/harbor-registry-qualification.json`
- `reports/model-evaluation.json`
- generated `reports/build.json` and `reports/qualification.json`

## Real-model evaluation

One authenticated Harbor run used Codex agent `0.150.0`, `gpt-5.6-sol`, and
maximum reasoning on `sb100-001-northwind-q3-commit`:

| Signal | Result |
|---|---|
| Successful calls | 219 (175 unique) |
| Evidence read | 96/96 documents |
| Procedure / state | 100% / 100% |
| Change ledger / brief | 94% / 36.8421% |
| Weighted score | 92.1842% |
| Strict pass | false |
| Cost / duration | $1.7056176 / 569.66 seconds |

The model made every authorized CRM mutation and preserved all protected state,
but selected policy/control records instead of the required source-of-truth
records for all 12 change citations. The deterministic verifier rejected those
12 ledger criteria and the 12 corresponding brief criteria. This is an actual
model failure, not an infrastructure exception. The benchmark page labels the
result as one-task coverage; it is not represented as a 100-task model score.

An earlier adapter attempt received HTTP 401 before task work because an empty
`OPENAI_API_KEY` was supplied. It is retained in `model-evaluation.json` as an
unscored harness-configuration failure.

## Reproduce

```bash
git clone https://github.com/blobfishai/sales-agent-simulation.git
cd sales-agent-simulation
python3 -m unittest discover -s tests -v
python3 -m salesbench.builder
python3 -m salesbench.run_suite
harbor run -d blobfishai/salesbench-100@v1.0.1 -a oracle -n 1
```

The final command exercises the public Harbor release. Each verifier writes
`report.json`, `reward.json`, and `reward.txt` under Harbor's verifier log
directory.

## Contract fidelity and limits

Tool names and request schemas are pinned to immutable real implementations or
official API specifications; see `research/API-CONTRACTS.md`. The conformance
run checked all six filesystem contracts and behavior, matched vendor source
fragments at their recorded commits, and confirmed that the official Salesforce,
HubSpot, and Gong hosted endpoints returned authentication gates.

The release does not claim an authenticated hosted `tools/list` comparison:
`authenticated_hosted_tools_list_compared` is explicitly `false`. Offline
response envelopes mirror the documented surfaces but are not byte-for-byte
copies of tenant-hosted responses. Gong remains strictly read-only.

All 100 reference trajectories use the same auditable macro-procedure—orient,
read 96 evidence documents, inspect metadata and schemas, reconcile 12 changes,
then write two deliverables. Task content, companies, conflicts, authorized
mutations, source records, and prompts are hand-authored per spine; exact
documents and prompt skeletons have no duplicates.
