# SalesBench-100

SalesBench-100 is an executable, deterministic benchmark for long-horizon sales
agents working across Salesforce, HubSpot, Gong, and a seeded sales evidence
room. It is the sales-domain counterpart to
[CounselBench-100](https://blobfish.ai/benchmarks/counselbench-100).

The release target is deliberately strict:

- 100 distinct B2B sales and revenue-operations tasks across 10 workflow families.
- 100 authored causal decision rules, each with task-specific observations,
  controlling authority, alternatives, and provider state transitions.
- 28 task-specific assets per task (2,800 unique assets total), including 12
  multi-record business exports plus current and superseded PDF controls, real
  XLSX workbooks, email, Slack/Drive-style records, lineage tables, and audit
  evidence. Every portfolio key must be joined across identity, operating facts,
  authority, governed transitions, live-system indexes, and exceptions; no
  business file publishes a precomputed answer.
- Vendor-separated MCP servers whose schemas and response envelopes are pinned to real implementations or official API specifications.
- Deterministic, criterion-level verification of evidence-before-write causality,
  calculation or branch choice, exact CRM state, collateral safety, per-write
  readback, held cases, and human deliverables.
- 68–103 successful MCP calls per accepted trajectory, with 5–12 evidence-derived
  mutations and an exact readback after each mutation.
- 1,200 local qualification executions: oracle, exact replay, and ten adversarial
  controls for every task. Model scores remain withheld until an exact-version run exists.
- Public GitHub, Harbor, Hugging Face, and Blobfish benchmark-page releases.

## Why a new repository

[`blobfishai/salesforce-grok`](https://github.com/blobfishai/salesforce-grok)
is the broad capability-world predecessor: its live synthetic enterprise world
has 339 tables, 597 tools, 66 tasks and verifiers, eleven vendor endpoints,
deterministic VCode grading, and hundreds of frontier-run traces. SalesBench-100
reuses its strongest methods—vendor isolation, immutable provenance, exact
state diffs, collateral-damage checks, and inspectable trajectories—but focuses
the release on 100 hand-authored Salesforce + HubSpot + Gong workflows with
100 distinct semantic action graphs. The two repositories are
complementary: one explores breadth and model frontiers; this one is the compact,
portable public benchmark and dataset.

## Contract targets

| System | Real surface | Benchmark use |
|---|---|---|
| Salesforce | Hosted `platform/sobject-all` MCP | Schema discovery, SOQL/SOSL, related records, CRUD |
| HubSpot | Remote MCP at `https://mcp.hubspot.com` | CRM object search, read/write, associations, activities |
| Gong | Remote MCP at `https://mcp.gong.io/mcp` | Read-only account/deal questions and structured briefs |
| Files | Official MCP filesystem server | Seeded evidence room and final deliverables |

See [`research/API-CONTRACTS.md`](research/API-CONTRACTS.md) for exact pins,
auth probes, schema provenance, and fidelity boundaries.

## Development

```bash
python3 -m unittest discover -s tests -v
python3 -m salesbench.builder
python3 -m salesbench.run_suite
```

Generated release artifacts are written to `dist/salesbench-100` and are not
committed. All benchmark entities and content are synthetic.

## Public release

- Source: <https://github.com/blobfishai/sales-agent-simulation>
- Harbor: <https://hub.harborframework.com/datasets/blobfishai/salesbench-100>
- Hugging Face: <https://huggingface.co/datasets/SamuelChien821/salesbench-100>
- Benchmark explorer: <https://blobfish.ai/benchmarks/salesbench-100>
