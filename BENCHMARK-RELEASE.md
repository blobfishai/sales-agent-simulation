# SalesBench-100 — Release Qualification (bench/salesbench-100-release)

SalesBench-100 is a deterministic, long-horizon sales-agent benchmark: 100
original revenue-operations tasks across four vendor-separated MCP surfaces
(Salesforce, HubSpot, Gong, filesystem evidence room), built to
CounselBench-100 release parity. Dataset name: `blobfishai/salesbench-100`;
task ids `sb100-NNN-<slug>`; task names `blobfishai/sb100-NNN-<slug>`.

## What was built

- `salesbench/catalog.py` — 100 hand-authored business spines (10 workflow
  families x 10), import-time validated.
- `salesbench/generation.py` — deterministic expansion: per task 96 seeded
  documents (24 md / 12 each txt, json, csv, eml, xml, html), 16 portfolio
  entities (12 authorized changes + 4 controls), 48 distractor records, a
  163-call reference trajectory, `changes.json` + `brief.md` gold deliverables,
  and a verify-token digest.
- `salesbench/runtime/world.py` — offline multi-server world: 35 tools
  (filesystem 6, Salesforce 11, HubSpot 15, Gong 3 read-only), JSON state,
  `trace.jsonl`, token-gated `verify()`.
- `salesbench/runtime/scoring.py` — pure scoring: reward = 0.20 procedure +
  0.45 state + 0.25 changes + 0.10 brief; caps 0.20 (deliverables missing or
  not written through MCP) and 0.49 (procedure incomplete); floor: zero
  successful MCP calls -> reward exactly 0.0.
- `salesbench/runtime/server.py` — stdlib streamable-HTTP MCP server exposing
  `/mcp/{filesystem,salesforce,hubspot,gong}` (four `[[environment.mcp_servers]]`
  entries per task), `/health`, and token-gated `POST /verify`. No solve endpoint.
- `salesbench/builder.py` — emits `dist/salesbench-100/`:
  - `harbor/tasks/sb100-NNN-<slug>/` — Harbor schema 1.4 packs (task.toml,
    instruction.md, environment with digest-pinned `python:3.12-slim` images
    built from in-pack source, solution/solve.py replaying the exact oracle
    trajectory over live MCP, tests/test.sh POSTing `/verify` and writing
    `$HARBOR_LOGS|$VERIFIER_LOG_DIR/verifier/{report.json,reward.json,reward.txt}`).
  - `harbor/dataset/dataset.toml` — `blobfishai/salesbench-100` with 100
    `[[tasks]]` entries; per-task sha256 content digests replicate the Harbor
    publisher packager algorithm (sorted relpath, `rel\0sha256\n` outer hash).
  - `huggingface/` — `data/tasks.jsonl` (task_id, task_name, world_id, prompt,
    context_files, rubric, gold_output, metadata with `grading:"deterministic"`,
    `llm_judge:false`), per-task JSON, world source, per-task oracle trajectory
    JSONL, reports, LICENSE-CODE (Apache-2.0), LICENSE-DATA (CC BY 4.0), card.
- `salesbench/run_suite.py` — oracle x100, exact replay x100, six negative
  controls x100, `reports/qualification.json`, release-manifest reseal.
- `tests/` — 13 unit tests (`python3 -m unittest discover -s tests`).

Verifier capability token: `verification_token(task_id)` =
sha256("SalesBench-100 verifier capability::" + task_id); the world image holds
only the token's sha256 (`spec.json`), the token appears only in `tests/test.sh`
(verifier side); the agent container never sees it.

## Reproduce

```bash
cd sales-agent-simulation
python3 -m unittest discover -s tests          # 13 tests
python3 -m salesbench.builder                  # rebuild dist/salesbench-100
python3 -m salesbench.run_suite                # 800 executions + qualification.json
# Dockerized probe (run from a $HOME-mounted dir; /private/tmp is empty under Colima):
mkdir -p ~/.cache/bf-audit/salesbench/tasks
cp -R dist/salesbench-100/harbor/tasks/sb100-001-northwind-q3-commit ~/.cache/bf-audit/salesbench/tasks/
cd ~/.cache/bf-audit/salesbench && harbor run -p tasks/sb100-001-northwind-q3-commit -a oracle -o jobs
```

## Qualification numbers (all executed in this session, 2026-08-26)

| Check | Result |
|---|---|
| Oracle replay (in-process, 163 calls each) | 100/100 tasks, reward 1.0 |
| Determinism (second full replay) | 100/100 byte-identical verifier reports |
| Negative controls (6 kinds x 100 tasks) | 600 executions, 0 false accepts |
| Pristine no-op control | reward exactly 0.0 on 100/100 |
| Total executions in `reports/qualification.json` | 800 |
| Unit tests | 13/13 OK |
| Dockerized Harbor oracle probe (job `sb100-probe-3`) | 2/2 trials, reward 1.0, 0 errors |
| Docker-vs-in-process verifier reports (2 probed tasks) | identical `report_sha256` |
| Prompt-skeleton uniqueness (litbench `skel()` normalization) | 100/100 unique |
| Max pairwise prompt similarity (5-shingle Jaccard) | 0.762931 |
| Seeded documents | 9,600 total, 9,600 unique sha256, 5,252–6,692 bytes |
| Deterministic criteria per task | 281 (11 procedure + 51 state + 200 changes + 19 brief) |

Negative controls: `shortcut` (last 2 calls only; reward 0.49),
`incomplete_read` (one required document skipped; 0.49), `unauthorized_write`
(one off-scope field injected into an authorized mutation; ~0.982),
`unauthorized_delete` (full oracle work plus one control-record delete; ~0.982,
`no_delete_tool_succeeded` and `entire_business_state_exact` fail),
`wrong_value` (fabricated `after` value + forbidden claim in brief; ~0.993),
`noop` (pristine world; exactly 0.0). All 600 scored `passed: false`.

Evidence files: `reports/harbor-probe/sb100-probe-3/` (also mirrored into
`dist/salesbench-100/reports/` and `dist/salesbench-100/huggingface/reports/`),
`dist/salesbench-100/reports/{build,qualification}.json`.

## Honest caveats

- `reports/conformance.json` (live 401 probes of the hosted Salesforce, HubSpot,
  and Gong MCP endpoints plus behavior checks against the pinned npm filesystem
  server) is committed evidence from an earlier run on 2026-08-26; it was NOT
  re-executed in this session (it requires network and npx). Its
  `authenticated_hosted_tools_list_compared` claim is `false` — hosted vendor
  tool lists were verified against pinned source/docs, not an authenticated
  live session.
- The dockerized Harbor probe covered 2 of 100 packs (sb100-001, sb100-051);
  the remaining 98 are proven by the in-process oracle + verifier only. All
  packs share the same generated environment/server/test templates.
- No real-model (non-oracle) run was executed in this session; the repo README
  lists model-run evidence as a release target, and that evidence does not yet
  exist for the sb100-* packs.
- All 100 reference trajectories share one macro-structure (3 discovery +
  96 reads + 8 metadata + 6 schema/account calls + 12 x (SOQL + HubSpot get +
  Gong ask + mutation) + 2 deliverable writes = 163 calls). Diversity comes
  from the hand-authored spines, prompts, entity data, and family-specific
  mutation surfaces — prompt skeletons are 100/100 unique — but the procedure
  shape is intentionally uniform.
- `LICENSE` / `LICENSE-CODE` are short Apache-2.0 pointer texts (the
  CounselBench pattern), not the full license text.
- MCP output envelopes are offline simplifications documented in
  `research/API-CONTRACTS.md`; tool names and input schemas are pinned to real
  implementations at immutable commits, response payloads mirror but do not
  replicate hosted behavior.
- Nothing was published: no `harbor publish`, no `hf upload`, no pushes.
  Docker note: a full local Docker network pool ("all predefined address pools
  have been fully subnetted") bricks `harbor run`; `docker network prune -f`
  cleared it.
