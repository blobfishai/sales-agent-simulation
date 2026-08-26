# MCP and API contract audit

## Probe evidence

On 2026-08-26, unauthenticated MCP `initialize` requests were sent to all three
hosted endpoints with protocol version `2025-06-18`:

| Endpoint | Result | What this proves |
|---|---|---|
| `https://api.salesforce.com/platform/mcp/v1/platform/sobject-all` | HTTP 401, `JWT Token is required` | The documented production endpoint is live and auth-gated |
| `https://mcp.hubspot.com/` | HTTP 401 with OAuth protected-resource metadata | The remote Streamable HTTP MCP endpoint is live and OAuth/PKCE-gated |
| `https://mcp.gong.io/mcp` | HTTP 401 with OAuth protected-resource metadata | The Gong MCP endpoint is live and OAuth-gated |

Hosted `tools/list` schemas cannot be obtained without tenant credentials.
SalesBench therefore never claims an unauthenticated live-schema comparison.
It uses three explicit fidelity levels.

## Fidelity levels

### Salesforce: official documented MCP contract

The mock mirrors the documented `platform/sobject-all` tools, camel-case names,
input field names, and structured result semantics:

- `getObjectSchema`
- `soqlQuery`
- `find`
- `getUserInfo`
- `listRecentSobjectRecords`
- `getRelatedRecords`
- `createSobjectRecord`
- `updateSobjectRecord`
- `updateRelatedRecord`
- `deleteSobjectRecord`
- `deleteRelatedRecord`

The benchmark snapshots only the documented subset it exercises. It preserves
MCP annotations such as read-only and destructive hints and rejects operations
the seeded user lacks permission to perform.

### HubSpot: real MCP schemas plus official REST envelopes

HubSpot's hosted MCP documentation publicly names the endpoint, data classes,
permissions, and `get_user_details`, but does not render its full dynamic tool
table without an authenticated account. The benchmark pins the real MIT-licensed
`axonops/hubspot-mcp` schemas for its exercised CRM tools and matches response
objects to HubSpot CRM v3/v4 envelopes:

- `hubspot_list_objects`, `hubspot_get_object`
- `hubspot_search_objects`, `hubspot_batch_read_objects`
- `hubspot_create_object`, `hubspot_update_object`, `hubspot_delete_object`
- `hubspot_list_associations`, `hubspot_associate_default`
- `hubspot_list_owners`, `hubspot_list_pipelines`
- `hubspot_create_note`, `hubspot_create_task`
- `hubspot_get_account_details`, `hubspot_get_object_schema`

HubSpot's public spec repository is used as a non-redistributed validation
source because its own README says the specifications are proprietary and not
intended for external reuse. SalesBench stores derived field mappings and
digests, not copies of those specification files.

### Gong: official hosted behavior plus real open-source schemas

The official Gong MCP has three read-only tools:

- `ask_account`: targeted natural-language account question.
- `ask_deal`: targeted natural-language deal question.
- `generate_brief`: structured account, deal, or contact brief.

The mock preserves the official boundary: results are synthesized structured
insights, raw transcript/message bodies are not returned, private calls are
excluded, and no tool mutates Gong or a CRM. Exact exercised input schemas are
pinned from `gonimbly/gong-mcp`, which maps these tools to Gong's
`/v2/entities/ask-entity` and `/v2/entities/get-brief` APIs.

### Filesystem: live schema conformance

The six-file-tool subset is pinned to
`@modelcontextprotocol/server-filesystem@2026.7.10` at upstream commit
`9a96ea6e5913736f92b88345bf51caeaaa8e719f`. Release qualification launches the
real package and compares `tools/list` plus representative calls against the
offline benchmark implementation.

## Output rule

All mocks return standard MCP tool results:

```json
{
  "content": [{"type": "text", "text": "<vendor JSON or text envelope>"}],
  "isError": false
}
```

The text payload is the same JSON envelope returned by the pinned vendor API or
open-source MCP implementation for the exercised operation. Differences caused
by omitted auth, tenant IDs, rate-limit timing, or unavailable proprietary AI
generation are enumerated in the release conformance report.

