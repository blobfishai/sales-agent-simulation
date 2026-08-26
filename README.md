# SalesBench-100

SalesBench-100 is an executable, deterministic benchmark for long-horizon sales
agents working across Salesforce, HubSpot, Gong, and a seeded sales evidence
room. It is the sales-domain counterpart to
[CounselBench-100](https://blobfish.ai/benchmarks/counselbench-100).

The release target is deliberately strict:

- 100 distinct B2B sales and revenue-operations tasks across 10 workflow families.
- At least 100 successful MCP interactions in every accepted reference trajectory.
- 96 task-specific seeded artifacts per task, with linked records and planted conflicts.
- Vendor-separated MCP servers whose schemas and response envelopes are pinned to real implementations or official API specifications.
- Deterministic, criterion-level verification of procedure, CRM state, collateral safety, and deliverables.
- Oracle, negative-control, exact-replay, container, and real-model execution evidence.
- Public GitHub, Harbor, Hugging Face, and Blobfish benchmark-page releases.

## Why a new repository

[`blobfishai/salesforce-grok`](https://github.com/blobfishai/salesforce-grok)
is the broad capability-world predecessor: its live synthetic enterprise world
has 339 tables, 597 tools, 66 tasks and verifiers, eleven vendor endpoints,
deterministic VCode grading, and hundreds of frontier-run traces. SalesBench-100
reuses its strongest methods—vendor isolation, immutable provenance, exact
state diffs, collateral-damage checks, and inspectable trajectories—but focuses
the release on 100 hand-authored Salesforce + HubSpot + Gong workflows with a
uniform 96-document, 163-call evaluation contract. The two repositories are
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
