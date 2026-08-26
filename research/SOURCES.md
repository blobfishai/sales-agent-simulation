# Primary-source register

Research was refreshed on 2026-08-26. Commit pins are immutable inputs to the
contract audit; vendor documentation URLs remain the authority for hosted
services.

## Open benchmarks

| Source | Pin | What SalesBench uses |
|---|---|---|
| [CRMArena / CRMArena-Pro](https://github.com/SalesforceAIResearch/CRMArena) | `a37d882c3a947f0330a907f513b90a7f08b9c532` | Salesforce object/task taxonomy, B2B/B2C CRM baselines, interactive scenarios |
| [SCUBA](https://github.com/SalesforceAIResearch/SCUBA) | `b893e2239b035f93d5753a32557346d15935d596` | Browser/computer-use trajectories and state-reset evidence |
| [AutomationBench](https://github.com/zapier/AutomationBench) | `4a8e1061254004d9dac807054eed33fad7d1ff14` | 100-task sales-domain scope, cross-app initial state, programmatic end-state assertions |
| [Archipelago](https://github.com/Mercor-Intelligence/archipelago) | live public repository | Environment/agent/grader separation and trajectory presentation |
| [salesforce-grok](https://github.com/blobfishai/salesforce-grok) | local audit at `b8a4246` | Sales census, CRMArena reproduction, collateral assertions, multi-server session design |

## Vendor and protocol sources

| Source | Pin | Status |
|---|---|---|
| [Salesforce Hosted MCP Servers](https://github.com/forcedotcom/mcp-hosted) | `7c962c7c2f5451105157a4b0ab8d070bc6400f3a` | Official, Apache-2.0 |
| [Salesforce SObject All reference](https://developer.salesforce.com/docs/platform/hosted-mcp-servers/guide/sobject-all.html) | retrieved 2026-08-26 | Official hosted MCP tool reference |
| [HubSpot remote MCP](https://developers.hubspot.com/docs/apps/developer-platform/build-apps/integrate-with-the-remote-hubspot-mcp-server) | retrieved 2026-08-26 | Official hosted MCP endpoint and capability reference |
| [HubSpot public API specifications](https://github.com/HubSpot/HubSpot-public-api-spec-collection) | `54f440ca65a4b7fb14063fd6a538e9db4c590f22` | Official OpenAPI 3.0 snapshots; repository warns they are not licensed for redistribution |
| [axonops/hubspot-mcp](https://github.com/axonops/hubspot-mcp) | `af798766ccd3385e4a9616a106f580b9f3a0f976` | Real open-source MCP schema reference, MIT |
| [Gong MCP documentation](https://help.gong.io/docs/about-gong-mcp-server) | updated 2026-08-24 | Official hosted tool behavior and read-only boundary |
| [gonimbly/gong-mcp](https://github.com/gonimbly/gong-mcp) | `bcbb289e96bf1ff8b0d9637d8dc0d4ce11891998` | Real open-source Gong REST/MCP implementation |
| [MCP specification](https://modelcontextprotocol.io/specification/2025-06-18) | `2025-06-18` | JSON-RPC, Streamable HTTP, tool result contract |
| [MCP filesystem server](https://github.com/modelcontextprotocol/servers) | `9a96ea6e5913736f92b88345bf51caeaaa8e719f` | Official seeded-file surface used by CounselBench |

## Questions the release must answer

1. Can the agent reconcile the same account and deal across two CRMs without
   treating either system as universally authoritative?
2. Can it turn Gong evidence into authorized CRM changes without fabricating
   transcript facts or attempting a Gong write?
3. Can it follow territory, discount, consent, forecast, and source-of-truth
   policies while operating on a large portfolio?
4. Can the verifier distinguish a correct headline outcome from collateral
   edits, duplicate activities, unsafe deletes, and unsupported narrative?
5. Does every accepted task still require more than 100 successful interactions
   after obvious no-op calls are removed?

