"""Pure deterministic scoring for SalesBench-100."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from typing import Any


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def normalize(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return re.sub(r"\s+", " ", value).strip().casefold()


def mean(criteria: dict[str, bool]) -> float:
    if not criteria:
        return 1.0
    return sum(bool(value) for value in criteria.values()) / len(criteria)


def _objects(state: dict[str, Any], system: str, object_type: str) -> list[dict[str, Any]]:
    if system == "salesforce":
        return state.get("salesforce", {}).get("objects", {}).get(object_type, [])
    if system == "hubspot":
        return state.get("hubspot", {}).get("objects", {}).get(object_type, [])
    return []


def _record(
    state: dict[str, Any], system: str, object_type: str, record_id: str
) -> dict[str, Any] | None:
    for row in _objects(state, system, object_type):
        if str(row.get("Id" if system == "salesforce" else "id")) == str(record_id):
            return row
    return None


def _field(row: dict[str, Any] | None, system: str, field: str) -> Any:
    if not row:
        return None
    if system == "hubspot":
        return row.get("properties", {}).get(field)
    return row.get(field)


def expected_state(initial_state: dict[str, Any], changes: list[dict[str, Any]]) -> dict[str, Any]:
    state = deepcopy(initial_state)
    for change in changes:
        row = _record(
            state,
            str(change["system"]),
            str(change["object_type"]),
            str(change["record_id"]),
        )
        if row is None:
            raise ValueError(f"expected target record missing: {change['id']}")
        args = change["arguments"]
        body = args.get("body") if change["system"] == "salesforce" else args.get("properties")
        if not isinstance(body, dict):
            raise ValueError(f"expected update body missing: {change['id']}")
        target = row if change["system"] == "salesforce" else row.setdefault("properties", {})
        target.update(deepcopy(body))
    return state


def score_state(
    current_state: dict[str, Any],
    initial_state: dict[str, Any],
    trace: list[dict[str, Any]],
    spec: dict[str, Any],
) -> dict[str, Any]:
    criteria: dict[str, bool] = {}
    details: list[dict[str, Any]] = []
    successful = [entry for entry in trace if entry.get("ok")]
    for change in spec["expected_changes"]:
        initial = _record(
            initial_state, change["system"], change["object_type"], change["record_id"]
        )
        current = _record(
            current_state, change["system"], change["object_type"], change["record_id"]
        )
        before_ok = _field(initial, change["system"], change["field"]) == change["before"]
        after_ok = _field(current, change["system"], change["field"]) == change["after"]
        expected_body = (
            change["arguments"].get("body", {})
            if change["system"] == "salesforce"
            else change["arguments"].get("properties", {})
        )
        all_fields_ok = all(
            _field(current, change["system"], field) == value
            for field, value in expected_body.items()
        )
        matching_calls = [
            entry
            for entry in successful
            if entry.get("server") == change["system"]
            and entry.get("tool") == change["tool"]
            and entry.get("arguments") == change["arguments"]
        ]
        called_once = len(matching_calls) == 1
        for suffix, passed in (
            ("initial_value", before_ok),
            ("target_value", after_ok),
            ("authorized_fields", all_fields_ok),
            ("exactly_one_authorized_call", called_once),
        ):
            criteria[f"{change['id']}.{suffix}"] = bool(passed)
        details.append(
            {
                "id": change["id"],
                "initial_value": _field(initial, change["system"], change["field"]),
                "actual_value": _field(current, change["system"], change["field"]),
                "expected_value": change["after"],
                "matching_calls": len(matching_calls),
            }
        )
    expected = expected_state(initial_state, spec["expected_changes"])
    criteria["entire_business_state_exact"] = current_state == expected
    criteria["no_delete_tool_succeeded"] = not any(
        entry.get("ok") and "delete" in str(entry.get("tool", "")).casefold()
        for entry in trace
    )
    criteria["gong_remained_read_only"] = not any(
        entry.get("server") == "gong" and entry.get("mutation")
        for entry in trace
    )
    return {
        "criteria": criteria,
        "score": round(mean(criteria), 6),
        "passed": all(criteria.values()),
        "details": details,
        "expected_state_matches": current_state == expected,
    }


CHANGE_FIELDS = (
    "id",
    "system",
    "object_type",
    "record_id",
    "operation",
    "field",
    "before",
    "after",
    "reason",
    "primary_source",
    "corroborating_source",
    "gong_evidence_id",
    "owner",
    "deadline",
    "portfolio_key",
)


def score_changes(value: Any, spec: dict[str, Any]) -> dict[str, Any]:
    expected = spec["expected_changes"]
    actual = value if isinstance(value, dict) else {}
    rows = actual.get("changes") if isinstance(actual.get("changes"), list) else []
    rows_by_id = {
        str(row.get("id")): row
        for row in rows
        if isinstance(row, dict) and isinstance(row.get("id"), str)
    }
    row_ids = [row.get("id") for row in rows if isinstance(row, dict)]
    criteria: dict[str, bool] = {
        "changes_is_object": isinstance(value, dict),
        "changes_exact_count": len(rows) == len(expected),
        "change_ids_unique": len(row_ids) == len(set(row_ids)) == len(expected),
    }
    expected_top = {
        "schema_version": "salesbench.changes.v1",
        "task_id": spec["task_id"],
        "title": spec["title"],
        "company": spec["company"],
        "as_of": spec["as_of"],
    }
    for key, expected_value in expected_top.items():
        criteria[f"top_level.{key}"] = actual.get(key) == expected_value
    details: list[dict[str, Any]] = []
    for expected_row in expected:
        actual_row = rows_by_id.get(expected_row["id"])
        checks: dict[str, bool] = {"present": isinstance(actual_row, dict)}
        criteria[f"{expected_row['id']}.present"] = checks["present"]
        for field in CHANGE_FIELDS:
            passed = isinstance(actual_row, dict) and actual_row.get(field) == expected_row[field]
            checks[field] = bool(passed)
            criteria[f"{expected_row['id']}.{field}"] = bool(passed)
        details.append({"id": expected_row["id"], "checks": checks})
    return {
        "criteria": criteria,
        "score": round(mean(criteria), 6),
        "passed": all(criteria.values()),
        "details": details,
    }


def score_brief(value: Any, spec: dict[str, Any]) -> dict[str, Any]:
    brief = value if isinstance(value, str) else ""
    normalized = normalize(brief)
    criteria: dict[str, bool] = {}
    for section in spec["brief_sections"]:
        criteria[f"section.{section}"] = normalize(section) in normalized
    details: list[dict[str, Any]] = []
    for change in spec["expected_changes"]:
        anchors = [
            change["id"],
            change["portfolio_key"],
            change["record_id"],
            change["field"],
            str(change["before"]),
            str(change["after"]),
            change["primary_source"],
            change["corroborating_source"],
            change["gong_evidence_id"],
            change["owner"],
            change["deadline"],
        ]
        missing = [anchor for anchor in anchors if normalize(anchor) not in normalized]
        criteria[f"change.{change['id']}"] = not missing
        details.append({"id": change["id"], "missing_anchors": missing})
    forbidden = [
        claim for claim in spec["forbidden_claims"] if normalize(claim) in normalized
    ]
    criteria["forbidden_claims_absent"] = not forbidden
    return {
        "criteria": criteria,
        "score": round(mean(criteria), 6),
        "passed": all(criteria.values()),
        "details": details,
        "forbidden_claims_present": forbidden,
    }


def aggregate_scores(
    procedure: dict[str, bool],
    state: dict[str, Any],
    changes: dict[str, Any],
    brief: dict[str, Any],
    *,
    successful_tool_calls: int = -1,
) -> dict[str, Any]:
    scores = {
        "procedure": round(mean(procedure), 6),
        "state": state["score"],
        "changes": changes["score"],
        "brief": brief["score"],
    }
    weights = {"procedure": 0.20, "state": 0.45, "changes": 0.25, "brief": 0.10}
    uncapped = sum(scores[key] * weights[key] for key in scores)
    reward = uncapped
    cap_reason = None
    if successful_tool_calls == 0:
        # A pristine world with zero successful MCP interactions earns nothing:
        # untouched seed state and absent deliverables must not collect the
        # partial credit that vacuously-true criteria would otherwise supply.
        reward = 0.0
        cap_reason = "no_mcp_interaction"
    elif not procedure.get("exact_deliverable_set") or not procedure.get(
        "deliverables_written_through_mcp"
    ):
        reward = min(reward, 0.20)
        cap_reason = "deliverables_missing_or_not_written_through_mcp"
    elif not all(procedure.values()):
        reward = min(reward, 0.49)
        cap_reason = "required_workflow_procedure_incomplete"
    passed = all(procedure.values()) and state["passed"] and changes["passed"] and brief["passed"]
    return {
        "passed": passed,
        "reward": round(reward, 6),
        "uncapped_reward": round(uncapped, 6),
        "cap_reason": cap_reason,
        "category_scores": scores,
        "weights": weights,
    }

