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
contains valuable CRM world research, CRMArena reproduction work, deterministic
state verifiers, and historical frontier runs. It also contains 7.8 GB of
experimental worlds and traces, only 20 suite-of-record sales tasks, and no Gong
or HubSpot MCP contract. SalesBench-100 reuses the validated methodology while
shipping a clean, reproducible multi-vendor benchmark.

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

