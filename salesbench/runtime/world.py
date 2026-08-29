"""Offline multi-server MCP world for SalesBench-100."""

from __future__ import annotations

import fnmatch
import hashlib
import json
import re
import stat
from copy import deepcopy
from pathlib import Path, PurePosixPath
from typing import Any

from salesbench.contracts import TOOLS_BY_SERVER, tool_definitions

from .scoring import (
    aggregate_scores,
    canonical_json,
    score_brief,
    score_changes,
    score_state,
)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def tool_result(text: str, *, error: bool = False) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": text}],
        "structuredContent": {"content": text},
        "isError": error,
    }


def json_result(value: Any) -> dict[str, Any]:
    return tool_result(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


class ToolFailure(ValueError):
    """Expected agent-facing tool failure."""


class SalesWorld:
    """One isolated task world with four vendor-separated MCP surfaces."""

    def __init__(
        self,
        documents_root: Path,
        output_root: Path,
        state_root: Path,
        spec_path: Path,
        seed_path: Path,
    ) -> None:
        self.documents_root = documents_root.resolve()
        self.output_root = output_root.resolve()
        self.state_root = state_root.resolve()
        self.spec_path = spec_path.resolve()
        self.seed_path = seed_path.resolve()
        self.output_root.mkdir(parents=True, exist_ok=True)
        self.state_root.mkdir(parents=True, exist_ok=True)
        self.spec = json.loads(self.spec_path.read_text(encoding="utf-8"))
        self.initial_state = json.loads(self.seed_path.read_text(encoding="utf-8"))
        self.state = deepcopy(self.initial_state)
        self.state_path = self.state_root / "state.json"
        self.trace_path = self.state_root / "trace.jsonl"
        self._trace_sequence = 0
        self._save_state()
        self.trace_path.write_text("", encoding="utf-8")

    def list_tools(self, server: str) -> list[dict[str, Any]]:
        return tool_definitions(server)

    def _save_state(self) -> None:
        temporary = self.state_path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(self.state, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.state_path)

    def _trace_entries(self) -> list[dict[str, Any]]:
        if not self.trace_path.exists():
            return []
        entries: list[dict[str, Any]] = []
        for line in self.trace_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                entries.append(json.loads(line))
        return entries

    def _record_trace(
        self,
        *,
        server: str,
        tool: str,
        arguments: dict[str, Any],
        result: dict[str, Any],
        mutation: bool,
    ) -> None:
        text = "\n".join(
            str(block.get("text", ""))
            for block in result.get("content", [])
            if isinstance(block, dict)
        )
        trace_arguments = deepcopy(arguments)
        if server == "filesystem" and tool == "write_file" and isinstance(
            trace_arguments.get("content"), str
        ):
            content = trace_arguments.pop("content")
            trace_arguments["content_sha256"] = sha256_text(content)
            trace_arguments["content_bytes"] = len(content.encode("utf-8"))
        entry = {
            "sequence": self._trace_sequence + 1,
            "server": server,
            "tool": tool,
            "arguments": trace_arguments,
            "ok": not bool(result.get("isError")),
            "mutation": mutation and not bool(result.get("isError")),
            "observation_sha256": sha256_text(text),
            "observation": text,
        }
        with self.trace_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
        self._trace_sequence += 1

    def call_tool(
        self, server: str, name: str, arguments: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        arguments = arguments or {}
        if server not in TOOLS_BY_SERVER or name not in TOOLS_BY_SERVER[server]:
            result = tool_result(f"Unknown tool {server}.{name}", error=True)
            self._record_trace(
                server=server, tool=name, arguments=arguments, result=result, mutation=False
            )
            return result
        annotations = TOOLS_BY_SERVER[server][name].get("annotations", {})
        mutation = not bool(annotations.get("readOnlyHint", False))
        try:
            if server == "filesystem":
                result = self._filesystem(name, arguments)
            elif server == "salesforce":
                result = self._salesforce(name, arguments)
            elif server == "hubspot":
                result = self._hubspot(name, arguments)
            else:
                result = self._gong(name, arguments)
            if mutation and not result.get("isError"):
                self._save_state()
        except (ToolFailure, KeyError, TypeError, ValueError) as exc:
            result = json_result({"error": str(exc), "errorType": type(exc).__name__})
            result["isError"] = True
        self._record_trace(
            server=server,
            tool=name,
            arguments=arguments,
            result=result,
            mutation=mutation,
        )
        return result

    # ---------------------------------------------------------------- files
    def _resolve_path(self, raw: Any, *, write: bool = False) -> Path:
        if not isinstance(raw, str) or not raw:
            raise ToolFailure("path must be a non-empty string")
        pure = PurePosixPath(raw)
        if pure.parts[:2] == ("/", "workspace"):
            pure = PurePosixPath(*pure.parts[2:])
        parts = pure.parts
        if parts and parts[0] == "documents":
            root = self.documents_root
            relative = PurePosixPath(*parts[1:])
        elif parts and parts[0] == "output":
            root = self.output_root
            relative = PurePosixPath(*parts[1:])
        else:
            raise ToolFailure("path must be under /workspace/documents or /workspace/output")
        if write and root != self.output_root:
            raise ToolFailure("the evidence room is immutable")
        resolved = (root / Path(*relative.parts)).resolve()
        if not resolved.is_relative_to(root):
            raise ToolFailure("path escapes the allowed directory")
        return resolved

    def _render_world_path(self, path: Path) -> str:
        if path.resolve().is_relative_to(self.documents_root):
            return str(
                PurePosixPath("/workspace/documents")
                / path.resolve().relative_to(self.documents_root).as_posix()
            )
        return str(
            PurePosixPath("/workspace/output")
            / path.resolve().relative_to(self.output_root).as_posix()
        )

    def _filesystem(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name == "list_allowed_directories":
            return tool_result("Allowed directories:\n/workspace/documents\n/workspace/output")
        if name == "read_text_file":
            path = self._resolve_path(arguments.get("path"))
            if not path.is_file():
                raise ToolFailure(f"ENOENT: no such file: {arguments.get('path')}")
            if "head" in arguments and "tail" in arguments:
                raise ToolFailure("head and tail cannot be used together")
            text = path.read_text(encoding="utf-8")
            lines = text.splitlines(keepends=True)
            if "head" in arguments:
                text = "".join(lines[: int(arguments["head"])])
            elif "tail" in arguments:
                text = "".join(lines[-int(arguments["tail"]):])
            return tool_result(text)
        if name == "write_file":
            path = self._resolve_path(arguments.get("path"), write=True)
            content = arguments.get("content")
            if not isinstance(content, str):
                raise ToolFailure("content must be a string")
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_name(f".{path.name}.salesbench.tmp")
            temporary.write_text(content, encoding="utf-8")
            temporary.replace(path)
            return tool_result(f"Successfully wrote to {arguments.get('path')}")
        if name == "directory_tree":
            root = self._resolve_path(arguments.get("path"))
            patterns = arguments.get("excludePatterns", [])
            if not isinstance(patterns, list):
                raise ToolFailure("excludePatterns must be an array")

            def tree(directory: Path, base: Path) -> list[dict[str, Any]]:
                values: list[dict[str, Any]] = []
                for child in sorted(directory.iterdir(), key=lambda item: item.name):
                    relative = child.relative_to(base).as_posix()
                    if any(fnmatch.fnmatch(relative, pattern) for pattern in patterns):
                        continue
                    item: dict[str, Any] = {
                        "name": child.name,
                        "type": "directory" if child.is_dir() else "file",
                    }
                    if child.is_dir():
                        item["children"] = tree(child, base)
                    values.append(item)
                return values

            return tool_result(json.dumps(tree(root, root), indent=2))
        if name == "search_files":
            root = self._resolve_path(arguments.get("path"))
            pattern = arguments.get("pattern")
            excludes = arguments.get("excludePatterns", [])
            if not isinstance(pattern, str) or not pattern:
                raise ToolFailure("pattern must be a non-empty string")
            if not isinstance(excludes, list):
                raise ToolFailure("excludePatterns must be an array")
            matches: list[str] = []
            for child in root.rglob("*"):
                relative = child.relative_to(root).as_posix()
                matched = (
                    fnmatch.fnmatch(relative, pattern)
                    or ("/" not in pattern and fnmatch.fnmatch(child.name, pattern))
                    or (pattern.startswith("**/") and fnmatch.fnmatch(relative, pattern[3:]))
                )
                if matched and not any(fnmatch.fnmatch(relative, item) for item in excludes):
                    matches.append(self._render_world_path(child))
            return tool_result("\n".join(sorted(matches)) if matches else "No matches found")
        if name == "get_file_info":
            path = self._resolve_path(arguments.get("path"))
            if not path.exists():
                raise ToolFailure(f"ENOENT: no such path: {arguments.get('path')}")
            info = path.stat()
            timestamp = self.spec["fixed_file_timestamp"]
            return tool_result(
                "\n".join(
                    [
                        f"size: {info.st_size}",
                        f"created: {timestamp}",
                        f"modified: {timestamp}",
                        f"accessed: {timestamp}",
                        f"isDirectory: {'true' if path.is_dir() else 'false'}",
                        f"isFile: {'true' if path.is_file() else 'false'}",
                        f"permissions: {stat.S_IMODE(info.st_mode):03o}",
                    ]
                )
            )
        raise ToolFailure(f"unsupported filesystem tool: {name}")

    # ------------------------------------------------------------- state helpers
    def _sf_rows(self, object_type: str) -> list[dict[str, Any]]:
        rows = self.state["salesforce"]["objects"].get(object_type)
        if rows is None:
            raise ToolFailure(f"unknown Salesforce object: {object_type}")
        return rows

    def _hs_rows(self, object_type: str) -> list[dict[str, Any]]:
        rows = self.state["hubspot"]["objects"].get(object_type)
        if rows is None:
            raise ToolFailure(f"unknown HubSpot object: {object_type}")
        return rows

    @staticmethod
    def _by_id(rows: list[dict[str, Any]], record_id: Any, key: str) -> dict[str, Any]:
        for row in rows:
            if str(row.get(key)) == str(record_id):
                return row
        raise ToolFailure(f"record not found: {record_id}")

    @staticmethod
    def _schema_for_rows(name: str, rows: list[dict[str, Any]], *, hubspot: bool = False) -> dict[str, Any]:
        sample = rows[0] if rows else {}
        fields = sample.get("properties", {}) if hubspot else sample
        return {
            "name": name,
            "label": name.replace("_", " ").title(),
            "fields": [
                {
                    "name": field,
                    "type": (
                        "boolean" if isinstance(value, bool)
                        else "double" if isinstance(value, (int, float))
                        else "string"
                    ),
                    "nillable": True,
                    "updateable": field not in {"Id", "id", "createdAt"},
                }
                for field, value in fields.items()
            ],
        }

    # ------------------------------------------------------------- salesforce
    def _soql(self, query: str) -> dict[str, Any]:
        normalized = re.sub(r"\s+", " ", query).strip()
        match = re.match(
            r"(?is)^SELECT (.+?) FROM ([A-Za-z0-9_]+)(?: WHERE (.+?))?(?: ORDER BY .+?)?(?: LIMIT (\d+))?$",
            normalized,
        )
        if not match:
            raise ToolFailure("unsupported SOQL; expected SELECT fields FROM Object [WHERE field = value] [LIMIT n]")
        fields_text, object_type, where_text, limit_text = match.groups()
        rows = list(self._sf_rows(object_type))
        if where_text:
            where_text = re.split(r"(?i) ORDER BY | LIMIT ", where_text)[0]
            conditions = re.split(r"(?i)\s+AND\s+", where_text)
            for condition in conditions:
                eq = re.match(r"(?is)^([A-Za-z0-9_]+)\s*=\s*'([^']*)'$", condition.strip())
                neq = re.match(r"(?is)^([A-Za-z0-9_]+)\s*!=\s*'([^']*)'$", condition.strip())
                like = re.match(r"(?is)^([A-Za-z0-9_]+)\s+LIKE\s+'([^']*)'$", condition.strip())
                if eq:
                    field, value = eq.groups()
                    rows = [row for row in rows if str(row.get(field, "")) == value]
                elif neq:
                    field, value = neq.groups()
                    rows = [row for row in rows if str(row.get(field, "")) != value]
                elif like:
                    field, value = like.groups()
                    regex = "^" + re.escape(value).replace("%", ".*") + "$"
                    rows = [row for row in rows if re.match(regex, str(row.get(field, "")), re.I)]
                else:
                    raise ToolFailure(f"unsupported SOQL condition: {condition}")
        limit = int(limit_text or 200)
        requested = [field.strip() for field in fields_text.split(",")]
        projected = []
        for row in rows[:limit]:
            item = {
                "attributes": {
                    "type": object_type,
                    "url": f"/services/data/v67.0/sobjects/{object_type}/{row.get('Id', '')}",
                }
            }
            if requested == ["*"]:
                item.update(deepcopy(row))
            else:
                item.update({field: deepcopy(row.get(field)) for field in requested})
            projected.append(item)
        return {"totalSize": len(projected), "done": True, "records": projected}

    def _salesforce(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name == "getUserInfo":
            return json_result(self.state["salesforce"]["user"])
        if name == "getObjectSchema":
            object_type = arguments.get("object-name")
            objects = self.state["salesforce"]["objects"]
            if object_type:
                return json_result(self._schema_for_rows(object_type, self._sf_rows(object_type)))
            return json_result(
                {
                    "objects": [
                        {
                            "name": key,
                            "label": key,
                            "queryable": True,
                            "createable": True,
                            "updateable": True,
                        }
                        for key in sorted(objects)
                    ]
                }
            )
        if name == "soqlQuery":
            query = arguments.get("query")
            if not isinstance(query, str):
                raise ToolFailure("query is required")
            return json_result(self._soql(query))
        if name == "find":
            search = arguments.get("search")
            if not isinstance(search, str):
                raise ToolFailure("search is required")
            match = re.search(r"\{([^}]+)\}", search)
            term = (match.group(1) if match else search).casefold()
            found = []
            for object_type, rows in self.state["salesforce"]["objects"].items():
                for row in rows:
                    if term in canonical_json(row).casefold():
                        found.append({"attributes": {"type": object_type}, **deepcopy(row)})
                    if len(found) >= 2000:
                        break
            return json_result({"searchRecords": found})
        if name == "listRecentSobjectRecords":
            object_type = arguments.get("sobject-name")
            return json_result(deepcopy(self._sf_rows(str(object_type))[:20]))
        if name == "getRelatedRecords":
            object_type = str(arguments.get("sobject-name"))
            record_id = str(arguments.get("id"))
            relationship = str(arguments.get("relationship-path"))
            mapping = {
                ("Account", "Contacts"): ("Contact", "AccountId"),
                ("Account", "Opportunities"): ("Opportunity", "AccountId"),
                ("Opportunity", "Tasks"): ("Task", "WhatId"),
                ("Opportunity", "Quotes"): ("Quote", "OpportunityId"),
            }
            child = mapping.get((object_type, relationship))
            if not child:
                raise ToolFailure(f"unknown relationship {object_type}.{relationship}")
            child_type, foreign_key = child
            return json_result(
                [row for row in self._sf_rows(child_type) if str(row.get(foreign_key)) == record_id]
            )
        if name == "createSobjectRecord":
            object_type = str(arguments.get("sobject-name"))
            body = arguments.get("body")
            if not isinstance(body, dict):
                raise ToolFailure("body must be an object")
            rows = self._sf_rows(object_type)
            prefix = {"Account": "001", "Contact": "003", "Opportunity": "006", "Lead": "00Q", "Task": "00T", "Quote": "0Q0"}.get(object_type, "a00")
            record_id = f"{prefix}NEW{self.spec['task_number']:03d}{len(rows) + 1:06d}"[:18]
            rows.append({"Id": record_id, **deepcopy(body)})
            return json_result({"id": record_id, "success": True, "errors": []})
        if name == "updateSobjectRecord":
            object_type = str(arguments.get("sobject-name"))
            record = self._by_id(self._sf_rows(object_type), arguments.get("id"), "Id")
            body = arguments.get("body")
            if not isinstance(body, dict):
                raise ToolFailure("body must be an object")
            if "Id" in body:
                raise ToolFailure("Id is not updateable")
            record.update(deepcopy(body))
            return json_result({"id": record["Id"], "success": True, "errors": []})
        if name == "updateRelatedRecord":
            object_type = str(arguments.get("sobject-name"))
            parent_id = str(arguments.get("id"))
            relationship = str(arguments.get("relationship-path"))
            body = deepcopy(arguments.get("body"))
            child_id = body.pop("Id", None) if isinstance(body, dict) else None
            related_result = self._salesforce(
                "getRelatedRecords",
                {"sobject-name": object_type, "id": parent_id, "relationship-path": relationship},
            )
            related = json.loads(related_result["content"][0]["text"])
            if not related:
                raise ToolFailure("related record not found")
            target_id = child_id or related[0]["Id"]
            child_type = {"Contacts": "Contact", "Opportunities": "Opportunity", "Tasks": "Task", "Quotes": "Quote"}[relationship]
            return self._salesforce(
                "updateSobjectRecord",
                {"sobject-name": child_type, "id": target_id, "body": body or {}},
            )
        if name == "deleteSobjectRecord":
            object_type = str(arguments.get("sobject-name"))
            rows = self._sf_rows(object_type)
            record = self._by_id(rows, arguments.get("id"), "Id")
            rows.remove(record)
            return json_result({"id": arguments.get("id"), "success": True, "errors": []})
        if name == "deleteRelatedRecord":
            relationship = str(arguments.get("relationship-path"))
            related = json.loads(
                self._salesforce("getRelatedRecords", arguments)["content"][0]["text"]
            )
            if not related:
                raise ToolFailure("related record not found")
            child_type = {"Contacts": "Contact", "Opportunities": "Opportunity", "Tasks": "Task", "Quotes": "Quote"}[relationship]
            return self._salesforce(
                "deleteSobjectRecord",
                {"sobject-name": child_type, "id": related[0]["Id"]},
            )
        raise ToolFailure(f"unsupported Salesforce tool: {name}")

    # ---------------------------------------------------------------- hubspot
    @staticmethod
    def _hs_projection(row: dict[str, Any], properties: Any) -> dict[str, Any]:
        projected = deepcopy(row)
        if isinstance(properties, list):
            projected["properties"] = {
                key: deepcopy(row.get("properties", {}).get(key)) for key in properties
            }
        return projected

    @staticmethod
    def _matches_filter(row: dict[str, Any], item: dict[str, Any]) -> bool:
        props = row.get("properties", {})
        field = item.get("propertyName")
        operator = str(item.get("operator", "EQ"))
        actual = props.get(field)
        expected = item.get("value")
        if operator == "EQ":
            return str(actual) == str(expected)
        if operator == "NEQ":
            return str(actual) != str(expected)
        if operator == "HAS_PROPERTY":
            return actual not in (None, "")
        if operator == "NOT_HAS_PROPERTY":
            return actual in (None, "")
        if operator == "CONTAINS_TOKEN":
            return str(expected).casefold() in str(actual).casefold()
        if operator == "NOT_CONTAINS_TOKEN":
            return str(expected).casefold() not in str(actual).casefold()
        if operator in {"GT", "GTE", "LT", "LTE"}:
            try:
                left, right = float(actual), float(expected)
            except (TypeError, ValueError):
                return False
            return {"GT": left > right, "GTE": left >= right, "LT": left < right, "LTE": left <= right}[operator]
        if operator in {"IN", "NOT_IN"}:
            values = item.get("values", [])
            included = str(actual) in {str(value) for value in values}
            return included if operator == "IN" else not included
        return False

    def _hubspot(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name == "hubspot_get_account_details":
            return json_result(self.state["hubspot"]["account_details"])
        if name == "hubspot_get_object_schema":
            object_type = str(arguments.get("object_type"))
            return json_result(self._schema_for_rows(object_type, self._hs_rows(object_type), hubspot=True))
        if name == "hubspot_list_pipelines":
            object_type = str(arguments.get("object_type"))
            return json_result(
                {
                    "results": [
                        {
                            "id": f"salesbench-{object_type}",
                            "label": f"SalesBench {object_type.title()} Pipeline",
                            "stages": [
                                {"id": stage.lower().replace(" ", "_"), "label": stage, "displayOrder": index}
                                for index, stage in enumerate(("Prospecting", "Qualification", "Discovery", "Technical Validation", "Proposal", "Negotiation", "Closed Won", "Closed Lost"))
                            ],
                        }
                    ]
                }
            )
        if name == "hubspot_list_owners":
            rows = [
                {"id": owner_id, "firstName": name.split()[0], "lastName": name.split()[-1], "email": f"{name.lower().replace(' ', '.')}@salesbench.example", "archived": False}
                for owner_id, name, _ in (
                    (row[0], row[1], row[2])
                    for row in (
                        ("005SB000000001", "Maya Chen", "Enterprise AE"),
                        ("005SB000000002", "Jon Bell", "Commercial AE"),
                        ("005SB000000003", "Priya Raman", "Strategic AE"),
                        ("005SB000000004", "Luis Ortega", "Regional AE"),
                    )
                )
            ]
            return json_result({"results": rows})
        if name == "hubspot_list_objects":
            object_type = str(arguments.get("object_type"))
            rows = [row for row in self._hs_rows(object_type) if bool(row.get("archived")) == bool(arguments.get("archived", False))]
            after = int(arguments.get("after") or 0)
            limit = max(1, min(int(arguments.get("limit", 50)), 100))
            page = rows[after: after + limit]
            response: dict[str, Any] = {
                "results": [self._hs_projection(row, arguments.get("properties")) for row in page]
            }
            if after + limit < len(rows):
                response["paging"] = {"next": {"after": str(after + limit), "link": f"/crm/v3/objects/{object_type}?after={after + limit}"}}
            return json_result(response)
        if name == "hubspot_get_object":
            object_type = str(arguments.get("object_type"))
            record = self._by_id(self._hs_rows(object_type), arguments.get("object_id"), "id")
            result = self._hs_projection(record, arguments.get("properties"))
            requested_assoc = arguments.get("associations")
            if isinstance(requested_assoc, list):
                result["associations"] = {}
                for target_type in requested_assoc:
                    associated = [
                        link["to"]["id"]
                        for link in self.state["hubspot"].get("associations", [])
                        if link["from"] == {"type": object_type, "id": record["id"]}
                        and link["to"]["type"] == target_type
                    ]
                    result["associations"][target_type] = {"results": [{"id": value, "type": f"{object_type}_to_{target_type}"} for value in associated]}
            return json_result(result)
        if name == "hubspot_search_objects":
            object_type = str(arguments.get("object_type"))
            rows = list(self._hs_rows(object_type))
            query = arguments.get("query")
            if isinstance(query, str) and query:
                rows = [row for row in rows if query.casefold() in canonical_json(row.get("properties", {})).casefold()]
            groups = arguments.get("filter_groups")
            if isinstance(groups, list) and groups:
                rows = [
                    row for row in rows
                    if any(
                        all(self._matches_filter(row, item) for item in group.get("filters", []))
                        for group in groups
                    )
                ]
            limit = max(1, min(int(arguments.get("limit", 25)), 200))
            return json_result(
                {
                    "total": len(rows),
                    "results": [self._hs_projection(row, arguments.get("properties")) for row in rows[:limit]],
                }
            )
        if name == "hubspot_batch_read_objects":
            object_type = str(arguments.get("object_type"))
            ids = {str(value) for value in arguments.get("ids", [])}
            rows = [row for row in self._hs_rows(object_type) if str(row.get("id")) in ids]
            return json_result(
                {"status": "COMPLETE", "results": [self._hs_projection(row, arguments.get("properties")) for row in rows], "numErrors": 0}
            )
        if name == "hubspot_create_object":
            object_type = str(arguments.get("object_type"))
            properties = arguments.get("properties")
            if not isinstance(properties, dict):
                raise ToolFailure("properties must be an object")
            rows = self._hs_rows(object_type)
            record_id = str(9_900_000_000 + self.spec["task_number"] * 10_000 + len(rows) + 1)
            record = {"id": record_id, "properties": deepcopy(properties), "createdAt": self.spec["as_of"] + "T12:00:00.000Z", "updatedAt": self.spec["as_of"] + "T12:00:00.000Z", "archived": False}
            rows.append(record)
            return json_result(record)
        if name == "hubspot_update_object":
            object_type = str(arguments.get("object_type"))
            record = self._by_id(self._hs_rows(object_type), arguments.get("object_id"), "id")
            properties = arguments.get("properties")
            if not isinstance(properties, dict):
                raise ToolFailure("properties must be an object")
            record.setdefault("properties", {}).update(deepcopy(properties))
            return json_result(record)
        if name == "hubspot_delete_object":
            object_type = str(arguments.get("object_type"))
            record = self._by_id(self._hs_rows(object_type), arguments.get("object_id"), "id")
            record["archived"] = True
            return json_result({"archived": True, "object_type": object_type, "id": record["id"]})
        if name == "hubspot_list_associations":
            source = {"type": str(arguments.get("object_type")), "id": str(arguments.get("object_id"))}
            target_type = str(arguments.get("to_object_type"))
            rows = [link for link in self.state["hubspot"].get("associations", []) if link["from"] == source and link["to"]["type"] == target_type]
            return json_result({"results": [{"toObjectId": link["to"]["id"], "associationTypes": [{"category": link["category"]}]} for link in rows]})
        if name == "hubspot_associate_default":
            link = {
                "from": {"type": str(arguments.get("from_object_type")), "id": str(arguments.get("from_object_id"))},
                "to": {"type": str(arguments.get("to_object_type")), "id": str(arguments.get("to_object_id"))},
                "category": "HUBSPOT_DEFINED",
            }
            links = self.state["hubspot"].setdefault("associations", [])
            if link not in links:
                links.append(link)
            return json_result({"fromObjectTypeId": link["from"]["type"], "fromObjectId": link["from"]["id"], "toObjectTypeId": link["to"]["type"], "toObjectId": link["to"]["id"]})
        if name == "hubspot_create_note":
            record = self._hubspot(
                "hubspot_create_object",
                {"object_type": "notes", "properties": {"hs_note_body": arguments.get("body"), "hs_timestamp": arguments.get("timestamp") or self.spec["as_of"] + "T12:00:00.000Z", "hubspot_owner_id": arguments.get("owner_id")}},
            )
            note = json.loads(record["content"][0]["text"])
            linked = []
            for association in arguments.get("associations", []) or []:
                self._hubspot(
                    "hubspot_associate_default",
                    {"from_object_type": "notes", "from_object_id": note["id"], "to_object_type": association["to_object_type"], "to_object_id": association["to_object_id"]},
                )
                linked.append(association)
            return json_result({"note": note, "associations": linked})
        if name == "hubspot_create_task":
            properties = {
                "hs_task_subject": arguments.get("subject"),
                "hs_task_body": arguments.get("body"),
                "hs_task_status": arguments.get("status", "NOT_STARTED"),
                "hs_task_priority": arguments.get("priority"),
                "hs_timestamp": arguments.get("due_date") or self.spec["as_of"] + "T12:00:00.000Z",
                "hubspot_owner_id": arguments.get("owner_id"),
            }
            record = self._hubspot("hubspot_create_object", {"object_type": "tasks", "properties": properties})
            task = json.loads(record["content"][0]["text"])
            linked = []
            for association in arguments.get("associations", []) or []:
                self._hubspot(
                    "hubspot_associate_default",
                    {"from_object_type": "tasks", "from_object_id": task["id"], "to_object_type": association["to_object_type"], "to_object_id": association["to_object_id"]},
                )
                linked.append(association)
            return json_result({"task": task, "associations": linked})
        raise ToolFailure(f"unsupported HubSpot tool: {name}")

    # ------------------------------------------------------------------- gong
    def _gong(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name == "ask_account":
            record_id = str(arguments.get("crmAccountId"))
            payload = self.state["gong"]["accounts"].get(record_id)
            if payload is None:
                raise ToolFailure(f"Gong account not found: {record_id}")
            response = deepcopy(payload)
            response["question"] = arguments.get("question")
            response["timePeriod"] = arguments.get("timePeriod", "THIS_MONTH")
            return json_result(response)
        if name == "ask_deal":
            record_id = str(arguments.get("crmDealId"))
            payload = self.state["gong"]["deals"].get(record_id)
            if payload is None:
                raise ToolFailure(f"Gong deal not found: {record_id}")
            response = deepcopy(payload)
            response["question"] = arguments.get("question")
            response["timePeriod"] = arguments.get("timePeriod", "THIS_MONTH")
            return json_result(response)
        if name == "generate_brief":
            template = arguments.get("briefName")
            if template not in self.state["gong"]["brief_templates"]:
                raise ToolFailure(f"published Gong brief not found: {template}")
            entity_type = str(arguments.get("crmEntityType"))
            record_id = str(arguments.get("crmEntityId"))
            source = self.state["gong"]["accounts"] if entity_type == "ACCOUNT" else self.state["gong"]["deals"]
            payload = source.get(record_id)
            if payload is None:
                raise ToolFailure(f"Gong {entity_type.lower()} not found: {record_id}")
            return json_result({"briefName": template, "entityType": entity_type, "entityId": record_id, "timePeriod": arguments.get("timePeriod", "THIS_MONTH"), "brief": deepcopy(payload), "privateActivityExcluded": True})
        raise ToolFailure(f"unsupported Gong tool: {name}")

    # ---------------------------------------------------------------- verify
    @staticmethod
    def _signature(entry: dict[str, Any]) -> str:
        return canonical_json(
            {
                "server": entry.get("server"),
                "tool": entry.get("tool"),
                "arguments": entry.get("arguments"),
            }
        )

    def verify(self, token: str | None) -> dict[str, Any]:
        if not token or sha256_text(token) != self.spec["verify_token_sha256"]:
            raise PermissionError("not found")
        trace = self._trace_entries()
        successful = [entry for entry in trace if entry.get("ok")]
        unique_successful = {self._signature(entry) for entry in successful}
        full_reads = {
            str(entry.get("arguments", {}).get("path"))
            for entry in successful
            if entry.get("server") == "filesystem"
            and entry.get("tool") == "read_text_file"
            and "head" not in entry.get("arguments", {})
            and "tail" not in entry.get("arguments", {})
        }
        info_paths = {
            str(entry.get("arguments", {}).get("path"))
            for entry in successful
            if entry.get("server") == "filesystem" and entry.get("tool") == "get_file_info"
        }
        called = {(entry.get("server"), entry.get("tool")) for entry in successful}
        sf_query_ids = {
            match
            for entry in successful
            if entry.get("server") == "salesforce" and entry.get("tool") == "soqlQuery"
            for match in re.findall(
                r"(?:001|006|003|00Q|0Q0|00v|00T)SB[A-Za-z0-9]+",
                str(entry.get("arguments", {}).get("query", "")),
            )
        }
        hs_object_ids = {
            str(entry.get("arguments", {}).get("object_id"))
            for entry in successful
            if entry.get("server") == "hubspot"
            and entry.get("tool") == "hubspot_get_object"
        }
        def gong_record_id(entry: dict[str, Any]) -> str:
            arguments = entry.get("arguments", {})
            return str(
                arguments.get("crmDealId")
                or arguments.get("crmAccountId")
                or arguments.get("crmEntityId")
                or ""
            )

        gong_record_ids = {
            gong_record_id(entry)
            for entry in successful
            if entry.get("server") == "gong"
            and entry.get("tool") in {"ask_deal", "ask_account", "generate_brief"}
        } - {""}
        required_salesforce_ids = {
            str(change.get("prewrite_evidence", {}).get("salesforce_record_id") or "")
            for change in self.spec["expected_changes"]
        } - {""}
        required_hs_ids = {
            str(change.get("prewrite_evidence", {}).get("hubspot_record_id") or "")
            for change in self.spec["expected_changes"]
        } - {""}
        required_gong_ids = {
            str(change.get("prewrite_evidence", {}).get("gong_record_id") or "")
            for change in self.spec["expected_changes"]
        } - {""}

        def first_index(predicate) -> int | None:
            return next(
                (index for index, entry in enumerate(successful) if predicate(entry)),
                None,
            )

        crm_mutation_indexes = [
            index
            for index, entry in enumerate(successful)
            if entry.get("server") in {"salesforce", "hubspot"}
            and entry.get("mutation")
        ]
        first_crm_mutation = min(crm_mutation_indexes) if crm_mutation_indexes else None
        all_required_evidence_precedes_mutation = first_crm_mutation is not None and all(
            (
                index := first_index(
                    lambda entry, required_path=required_path: entry.get("server") == "filesystem"
                    and entry.get("tool") == "read_text_file"
                    and entry.get("arguments", {}).get("path") == required_path
                    and "head" not in entry.get("arguments", {})
                    and "tail" not in entry.get("arguments", {})
                )
            )
            is not None
            and index < first_crm_mutation
            for required_path in self.spec["required_document_paths"]
        )
        provider_evidence_precedes_mutation = True
        for change in self.spec["expected_changes"]:
            mutation_index = first_index(
                lambda entry, change=change: entry.get("server") == change["system"]
                and entry.get("tool") == change["tool"]
                and entry.get("arguments") == change["arguments"]
            )
            evidence = change.get("prewrite_evidence") or {}
            required_paths = set(evidence.get("document_paths") or [])
            path_indexes = [
                first_index(
                    lambda entry, required_path=required_path: entry.get("server") == "filesystem"
                    and entry.get("tool") == "read_text_file"
                    and entry.get("arguments", {}).get("path") == required_path
                    and "head" not in entry.get("arguments", {})
                    and "tail" not in entry.get("arguments", {})
                )
                for required_path in required_paths
            ]
            sf_id = str(evidence.get("salesforce_record_id") or "")
            hs_id = str(evidence.get("hubspot_record_id") or "")
            hs_object = str(evidence.get("hubspot_object") or "")
            gong_id = str(evidence.get("gong_record_id") or "")
            gong_tool = str(evidence.get("gong_tool") or "")
            sf_index = first_index(
                lambda entry, sf_id=sf_id: entry.get("server") == "salesforce"
                and entry.get("tool") == "soqlQuery"
                and sf_id in str(entry.get("arguments", {}).get("query", ""))
            )
            hs_index = first_index(
                lambda entry, hs_id=hs_id, hs_object=hs_object: entry.get("server") == "hubspot"
                and entry.get("tool") == "hubspot_get_object"
                and str(entry.get("arguments", {}).get("object_id")) == hs_id
                and str(entry.get("arguments", {}).get("object_type")) == hs_object
            )
            gong_index = first_index(
                lambda entry, gong_id=gong_id, gong_tool=gong_tool: entry.get("server") == "gong"
                and entry.get("tool") == gong_tool
                and gong_record_id(entry) == gong_id
            )
            required_indexes = [*path_indexes, sf_index, hs_index, gong_index]
            if (
                mutation_index is None
                or not required_paths
                or any(index is None or index >= mutation_index for index in required_indexes)
            ):
                provider_evidence_precedes_mutation = False
                break
        procedure = {
            "all_evidence_read_in_full": set(self.spec["required_document_paths"]) <= full_reads,
            "custody_metadata_checked": set(self.spec["metadata_check_paths"]) <= info_paths,
            "filesystem_discovery_completed": {
                ("filesystem", "list_allowed_directories"),
                ("filesystem", "directory_tree"),
                ("filesystem", "search_files"),
            } <= called,
            "salesforce_discovery_completed": {
                ("salesforce", "getUserInfo"), ("salesforce", "getObjectSchema")
            } <= called,
            "hubspot_discovery_completed": {
                ("hubspot", "hubspot_get_account_details"),
                ("hubspot", "hubspot_get_object_schema"),
            }
            <= called
            and bool(
                {
                    ("hubspot", "hubspot_list_pipelines"),
                    ("hubspot", "hubspot_list_objects"),
                }
                & called
            ),
            "all_salesforce_evidence_queried": required_salesforce_ids <= sf_query_ids,
            "all_hubspot_evidence_retrieved": required_hs_ids <= hs_object_ids,
            "all_gong_evidence_queried": required_gong_ids <= gong_record_ids,
            "all_required_evidence_precedes_mutation": all_required_evidence_precedes_mutation,
            "all_provider_evidence_precedes_mutation": provider_evidence_precedes_mutation,
        }
        output_files = sorted(
            path.relative_to(self.output_root).as_posix()
            for path in self.output_root.rglob("*")
            if path.is_file()
        )
        procedure["exact_deliverable_set"] = output_files == sorted(self.spec["deliverables"])
        current_digests = {
            name: sha256_text((self.output_root / name).read_text(encoding="utf-8"))
            for name in self.spec["deliverables"]
            if (self.output_root / name).is_file()
        }
        write_digests = {
            Path(str(entry.get("arguments", {}).get("path"))).name: entry.get("arguments", {}).get("content_sha256")
            for entry in successful
            if entry.get("server") == "filesystem" and entry.get("tool") == "write_file"
        }
        procedure["deliverables_written_through_mcp"] = all(
            write_digests.get(Path(name).name) == current_digests.get(name)
            for name in self.spec["deliverables"]
        )

        changes_value: Any = None
        try:
            changes_value = json.loads((self.output_root / "changes.json").read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            pass
        brief = (
            (self.output_root / "brief.md").read_text(encoding="utf-8")
            if (self.output_root / "brief.md").is_file()
            else ""
        )
        state_scoring = score_state(self.state, self.initial_state, trace, self.spec)
        procedure["all_mutations_verified_by_readback"] = all(
            state_scoring["criteria"].get(
                f"{change['id']}.postwrite_readback", False
            )
            for change in self.spec["expected_changes"]
        )
        changes_scoring = score_changes(changes_value, self.spec)
        brief_scoring = score_brief(brief, self.spec)
        aggregate = aggregate_scores(
            procedure,
            state_scoring,
            changes_scoring,
            brief_scoring,
            successful_tool_calls=len(successful),
        )
        report = {
            "schema_version": "salesbench.verifier.v1",
            "task_id": self.spec["task_id"],
            "passed": aggregate["passed"],
            "reward": aggregate["reward"],
            "uncapped_reward": aggregate["uncapped_reward"],
            "reward_cap_reason": aggregate["cap_reason"],
            "category_scores": aggregate["category_scores"],
            "score_weights": aggregate["weights"],
            "criteria": {
                "procedure": procedure,
                "state": state_scoring,
                "changes": changes_scoring,
                "brief": brief_scoring,
            },
            "successful_tool_calls": len(successful),
            "unique_successful_tool_calls": len(unique_successful),
            "reference_tool_calls": self.spec["reference_tool_calls"],
            "documents_read": len(set(self.spec["required_document_paths"]) & full_reads),
            "required_documents": len(self.spec["required_document_paths"]),
            "output_sha256": current_digests,
            "diagnostics": {
                "deterministic": True,
                "model_calls": 0,
                "network_calls": 0,
                "clock_calls": 0,
                "random_calls": 0,
                "state_sha256": sha256_text(canonical_json(self.state)),
                "initial_state_sha256": sha256_text(canonical_json(self.initial_state)),
            },
        }
        report["report_sha256"] = sha256_text(canonical_json(report))
        return report
