"""Pinned MCP contracts for the SalesBench-100 offline world.

The release stores only the exercised subset.  Contract provenance and known
fidelity limits are documented in ``research/API-CONTRACTS.md``.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


CONTRACT_PINS = {
    "protocol_version": "2025-06-18",
    "filesystem": {
        "repository": "https://github.com/modelcontextprotocol/servers",
        "commit": "9a96ea6e5913736f92b88345bf51caeaaa8e719f",
        "package": "@modelcontextprotocol/server-filesystem",
        "version": "2026.7.10",
    },
    "salesforce": {
        "repository": "https://github.com/forcedotcom/mcp-hosted",
        "commit": "7c962c7c2f5451105157a4b0ab8d070bc6400f3a",
        "endpoint": "https://api.salesforce.com/platform/mcp/v1/platform/sobject-all",
        "reference": "https://developer.salesforce.com/docs/platform/hosted-mcp-servers/guide/sobject-all.html",
    },
    "hubspot": {
        "repository": "https://github.com/axonops/hubspot-mcp",
        "commit": "af798766ccd3385e4a9616a106f580b9f3a0f976",
        "official_endpoint": "https://mcp.hubspot.com/",
        "api_spec_commit": "54f440ca65a4b7fb14063fd6a538e9db4c590f22",
    },
    "gong": {
        "repository": "https://github.com/gonimbly/gong-mcp",
        "commit": "bcbb289e96bf1ff8b0d9637d8dc0d4ce11891998",
        "official_endpoint": "https://mcp.gong.io/mcp",
        "reference": "https://help.gong.io/docs/about-gong-mcp-server",
    },
}


def obj(
    properties: dict[str, Any] | None = None,
    required: list[str] | None = None,
    *,
    additional: bool | None = None,
) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "object", "properties": properties or {}}
    if required:
        schema["required"] = required
    if additional is not None:
        schema["additionalProperties"] = additional
    return schema


def arr(items: dict[str, Any]) -> dict[str, Any]:
    return {"type": "array", "items": items}


STR = {"type": "string"}
BOOL = {"type": "boolean"}
INT = {"type": "integer"}
ANY_OBJECT = {"type": "object", "additionalProperties": True}
STRINGS = arr(STR)
TEXT_OUTPUT = obj({"content": STR}, ["content"], additional=False)


FILESYSTEM_TOOLS = [
    {
        "name": "read_text_file",
        "title": "Read Text File",
        "description": "Read the complete contents of one allowed file as text.",
        "inputSchema": obj(
            {
                "path": STR,
                "tail": {"type": "number"},
                "head": {"type": "number"},
            },
            ["path"],
        ),
        "outputSchema": TEXT_OUTPUT,
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
    },
    {
        "name": "write_file",
        "title": "Write File",
        "description": "Create or completely overwrite an allowed text file.",
        "inputSchema": obj({"path": STR, "content": STR}, ["path", "content"]),
        "outputSchema": TEXT_OUTPUT,
        "annotations": {
            "readOnlyHint": False,
            "idempotentHint": True,
            "destructiveHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "directory_tree",
        "title": "Directory Tree",
        "description": "Return the recursive JSON tree under an allowed directory.",
        "inputSchema": obj(
            {
                "path": STR,
                "excludePatterns": {**STRINGS, "default": []},
            },
            ["path"],
        ),
        "outputSchema": TEXT_OUTPUT,
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
    },
    {
        "name": "search_files",
        "title": "Search Files",
        "description": "Recursively search allowed paths with a glob-style pattern.",
        "inputSchema": obj(
            {
                "path": STR,
                "pattern": STR,
                "excludePatterns": {**STRINGS, "default": []},
            },
            ["path", "pattern"],
        ),
        "outputSchema": TEXT_OUTPUT,
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
    },
    {
        "name": "get_file_info",
        "title": "Get File Info",
        "description": "Return size, timestamps, type, and permissions for an allowed path.",
        "inputSchema": obj({"path": STR}, ["path"]),
        "outputSchema": TEXT_OUTPUT,
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
    },
    {
        "name": "list_allowed_directories",
        "title": "List Allowed Directories",
        "description": "Return the filesystem roots available to this server.",
        "inputSchema": obj(),
        "outputSchema": TEXT_OUTPUT,
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
    },
]


def sf_tool(
    name: str,
    description: str,
    schema: dict[str, Any],
    *,
    read_only: bool,
    destructive: bool = False,
) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "inputSchema": schema,
        "annotations": {
            "readOnlyHint": read_only,
            "destructiveHint": destructive,
            "idempotentHint": read_only,
            "openWorldHint": False,
        },
    }


SALESFORCE_TOOLS = [
    sf_tool(
        "getObjectSchema",
        "Return a compact Salesforce object index or field-level schema.",
        obj({"object-name": STR}),
        read_only=True,
    ),
    sf_tool(
        "soqlQuery",
        "Execute a SOQL query and return the requested Salesforce records.",
        obj({"query": STR}, ["query"]),
        read_only=True,
    ),
    sf_tool(
        "find",
        "Execute a SOSL search across Salesforce objects.",
        obj({"search": STR}, ["search"]),
        read_only=True,
    ),
    sf_tool(
        "getUserInfo",
        "Return the authenticated Salesforce user's identity and context.",
        obj(),
        read_only=True,
    ),
    sf_tool(
        "listRecentSobjectRecords",
        "Return recently viewed records of one Salesforce object type.",
        obj({"sobject-name": STR}, ["sobject-name"]),
        read_only=True,
    ),
    sf_tool(
        "getRelatedRecords",
        "Traverse a Salesforce relationship and return related records.",
        obj(
            {"sobject-name": STR, "id": STR, "relationship-path": STR},
            ["sobject-name", "id", "relationship-path"],
        ),
        read_only=True,
    ),
    sf_tool(
        "createSobjectRecord",
        "Create a Salesforce record and return its ID and success indicator.",
        obj({"sobject-name": STR, "body": ANY_OBJECT}, ["sobject-name", "body"]),
        read_only=False,
    ),
    sf_tool(
        "updateSobjectRecord",
        "Update fields on a Salesforce record by ID.",
        obj(
            {"sobject-name": STR, "id": STR, "body": ANY_OBJECT},
            ["sobject-name", "id", "body"],
        ),
        read_only=False,
    ),
    sf_tool(
        "updateRelatedRecord",
        "Update a child record through a parent Salesforce relationship.",
        obj(
            {
                "sobject-name": STR,
                "id": STR,
                "relationship-path": STR,
                "body": ANY_OBJECT,
            },
            ["sobject-name", "id", "relationship-path", "body"],
        ),
        read_only=False,
    ),
    sf_tool(
        "deleteSobjectRecord",
        "Delete a Salesforce record by ID.",
        obj({"sobject-name": STR, "id": STR}, ["sobject-name", "id"]),
        read_only=False,
        destructive=True,
    ),
    sf_tool(
        "deleteRelatedRecord",
        "Delete a child record through a parent Salesforce relationship.",
        obj(
            {"sobject-name": STR, "id": STR, "relationship-path": STR},
            ["sobject-name", "id", "relationship-path"],
        ),
        read_only=False,
        destructive=True,
    ),
]


def hs_tool(
    name: str,
    description: str,
    schema: dict[str, Any],
    *,
    read_only: bool,
    destructive: bool = False,
) -> dict[str, Any]:
    return sf_tool(
        name,
        description,
        schema,
        read_only=read_only,
        destructive=destructive,
    )


HS_ASSOC = arr(
    obj(
        {"to_object_type": STR, "to_object_id": STR},
        ["to_object_type", "to_object_id"],
    )
)

HUBSPOT_TOOLS = [
    hs_tool(
        "hubspot_list_objects",
        "List HubSpot CRM records of a given type with paging.",
        obj(
            {
                "object_type": STR,
                "limit": {**INT, "default": 50},
                "after": STR,
                "properties": STRINGS,
                "associations": STRINGS,
                "archived": {**BOOL, "default": False},
            },
            ["object_type"],
        ),
        read_only=True,
    ),
    hs_tool(
        "hubspot_get_object",
        "Fetch one HubSpot CRM record by ID or unique property.",
        obj(
            {
                "object_type": STR,
                "object_id": STR,
                "properties": STRINGS,
                "associations": STRINGS,
                "id_property": STR,
                "archived": {**BOOL, "default": False},
            },
            ["object_type", "object_id"],
        ),
        read_only=True,
    ),
    hs_tool(
        "hubspot_search_objects",
        "Search HubSpot CRM records with text and filter groups.",
        obj(
            {
                "object_type": STR,
                "query": STR,
                "filter_groups": arr(ANY_OBJECT),
                "properties": STRINGS,
                "sorts": arr(ANY_OBJECT),
                "limit": {**INT, "default": 25},
                "after": STR,
            },
            ["object_type"],
        ),
        read_only=True,
    ),
    hs_tool(
        "hubspot_batch_read_objects",
        "Read up to 100 HubSpot records by ID or unique property.",
        obj(
            {
                "object_type": STR,
                "ids": STRINGS,
                "properties": STRINGS,
                "id_property": STR,
            },
            ["object_type", "ids"],
        ),
        read_only=True,
    ),
    hs_tool(
        "hubspot_create_object",
        "Create a HubSpot CRM record.",
        obj(
            {
                "object_type": STR,
                "properties": ANY_OBJECT,
                "associations": arr(ANY_OBJECT),
            },
            ["object_type", "properties"],
        ),
        read_only=False,
    ),
    hs_tool(
        "hubspot_update_object",
        "Update properties on a HubSpot CRM record.",
        obj(
            {
                "object_type": STR,
                "object_id": STR,
                "properties": ANY_OBJECT,
                "id_property": STR,
            },
            ["object_type", "object_id", "properties"],
        ),
        read_only=False,
    ),
    hs_tool(
        "hubspot_delete_object",
        "Archive a HubSpot CRM record.",
        obj({"object_type": STR, "object_id": STR}, ["object_type", "object_id"]),
        read_only=False,
        destructive=True,
    ),
    hs_tool(
        "hubspot_list_associations",
        "List HubSpot records associated with a source record.",
        obj(
            {
                "object_type": STR,
                "object_id": STR,
                "to_object_type": STR,
                "limit": {**INT, "default": 100},
                "after": STR,
            },
            ["object_type", "object_id", "to_object_type"],
        ),
        read_only=True,
    ),
    hs_tool(
        "hubspot_associate_default",
        "Create the default association between two HubSpot records.",
        obj(
            {
                "from_object_type": STR,
                "from_object_id": STR,
                "to_object_type": STR,
                "to_object_id": STR,
            },
            [
                "from_object_type",
                "from_object_id",
                "to_object_type",
                "to_object_id",
            ],
        ),
        read_only=False,
    ),
    hs_tool(
        "hubspot_list_owners",
        "List HubSpot owners with paging and archived filtering.",
        obj({"limit": INT, "after": STR, "archived": BOOL}),
        read_only=True,
    ),
    hs_tool(
        "hubspot_list_pipelines",
        "List HubSpot pipelines for an object type.",
        obj({"object_type": STR}, ["object_type"]),
        read_only=True,
    ),
    hs_tool(
        "hubspot_create_note",
        "Create a HubSpot note and optionally associate it to CRM records.",
        obj(
            {
                "body": STR,
                "associations": HS_ASSOC,
                "owner_id": STR,
                "timestamp": STR,
            },
            ["body"],
        ),
        read_only=False,
    ),
    hs_tool(
        "hubspot_create_task",
        "Create a HubSpot task and optionally associate it to CRM records.",
        obj(
            {
                "subject": STR,
                "body": STR,
                "status": {**STR, "default": "NOT_STARTED"},
                "priority": STR,
                "due_date": STR,
                "associations": HS_ASSOC,
                "owner_id": STR,
            },
            ["subject"],
        ),
        read_only=False,
    ),
    hs_tool(
        "hubspot_get_account_details",
        "Return portal, time zone, currency, and hosting-region details.",
        obj(),
        read_only=True,
    ),
    hs_tool(
        "hubspot_get_object_schema",
        "Return the full schema for a HubSpot object type.",
        obj({"object_type": STR}, ["object_type"]),
        read_only=True,
    ),
]


TIME_PERIOD = {
    "type": "string",
    "enum": ["THIS_WEEK", "THIS_MONTH", "THIS_QUARTER", "THIS_YEAR"],
    "default": "THIS_MONTH",
}

GONG_TOOLS = [
    sf_tool(
        "ask_account",
        "Answer a targeted question about one CRM account from permitted Gong activity.",
        obj(
            {
                "workspaceId": STR,
                "crmAccountId": STR,
                "timePeriod": TIME_PERIOD,
                "question": STR,
            },
            ["crmAccountId", "question"],
        ),
        read_only=True,
    ),
    sf_tool(
        "ask_deal",
        "Answer a targeted question about one CRM deal from permitted Gong activity.",
        obj(
            {
                "workspaceId": STR,
                "crmDealId": STR,
                "timePeriod": TIME_PERIOD,
                "question": STR,
            },
            ["crmDealId", "question"],
        ),
        read_only=True,
    ),
    sf_tool(
        "generate_brief",
        "Generate a structured Gong brief for one CRM account, deal, contact, or lead.",
        obj(
            {
                "workspaceId": STR,
                "briefName": STR,
                "crmEntityType": {
                    "type": "string",
                    "enum": ["ACCOUNT", "DEAL", "CONTACT", "LEAD"],
                },
                "crmEntityId": STR,
                "timePeriod": TIME_PERIOD,
            },
            ["briefName", "crmEntityType", "crmEntityId"],
        ),
        read_only=True,
    ),
]


TOOLSETS = {
    "filesystem": FILESYSTEM_TOOLS,
    "salesforce": SALESFORCE_TOOLS,
    "hubspot": HUBSPOT_TOOLS,
    "gong": GONG_TOOLS,
}


def tool_definitions(server: str) -> list[dict[str, Any]]:
    """Return an isolated contract copy for one MCP server."""

    if server not in TOOLSETS:
        raise KeyError(f"unknown MCP server: {server}")
    return deepcopy(TOOLSETS[server])


TOOLS_BY_SERVER = {
    server: {tool["name"]: tool for tool in tools}
    for server, tools in TOOLSETS.items()
}

