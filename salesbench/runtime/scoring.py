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


def mutation_matches(entry: dict[str, Any], change: dict[str, Any]) -> bool:
    """Match the authorized business mutation without requiring byte-identical args."""

    if (
        not entry.get("ok")
        or entry.get("server") != change["system"]
        or entry.get("tool") != change["tool"]
    ):
        return False
    actual = entry.get("arguments")
    if not isinstance(actual, dict):
        return False
    expected = change["arguments"]
    body_key = "body" if change["system"] == "salesforce" else "properties"
    if any(
        actual.get(key) != value
        for key, value in expected.items()
        if key != body_key
    ):
        return False
    actual_body = actual.get(body_key)
    expected_body = expected.get(body_key)
    return isinstance(actual_body, dict) and isinstance(expected_body, dict) and all(
        actual_body.get(field) == value for field, value in expected_body.items()
    )


def _postwrite_readback_passed(
    trace: list[dict[str, Any]], change: dict[str, Any]
) -> bool:
    successful = [entry for entry in trace if entry.get("ok")]
    mutation_index = next(
        (
            index
            for index, entry in enumerate(successful)
            if mutation_matches(entry, change)
        ),
        None,
    )
    evidence = change.get("postwrite_evidence") or {}
    if mutation_index is None:
        return False
    for entry in successful[mutation_index + 1 :]:
        if (
            entry.get("server") != evidence.get("server")
            or entry.get("tool") != evidence.get("name")
        ):
            continue
        try:
            observation = json.loads(str(entry.get("observation", "")))
        except json.JSONDecodeError:
            return False
        if change["system"] == "salesforce":
            records = observation.get("records", []) if isinstance(observation, dict) else []
            record = next(
                (
                    row
                    for row in records
                    if str(row.get("Id")) == str(change["record_id"])
                ),
                None,
            )
            value = record.get(change["field"]) if record else None
        else:
            properties = (
                observation.get("properties", {})
                if isinstance(observation, dict)
                else {}
            )
            if str(observation.get("id", change["record_id"])) != str(
                change["record_id"]
            ):
                continue
            value = properties.get(change["field"])
        if value == change["after"]:
            return True
    return False


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
            if mutation_matches(entry, change)
        ]
        called_once = len(matching_calls) == 1
        readback_ok = _postwrite_readback_passed(trace, change)
        for suffix, passed in (
            ("initial_value", before_ok),
            ("target_value", after_ok),
            ("authorized_fields", all_fields_ok),
            ("exactly_one_authorized_call", called_once),
            ("postwrite_readback", readback_ok),
        ):
            criteria[f"{change['id']}.{suffix}"] = bool(passed)
        details.append(
            {
                "id": change["id"],
                "initial_value": _field(initial, change["system"], change["field"]),
                "actual_value": _field(current, change["system"], change["field"]),
                "expected_value": change["after"],
                "matching_calls": len(matching_calls),
                "postwrite_readback": readback_ok,
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
    "value_kind",
    "decision_method",
    "decision_inputs",
    "decision_explanation",
    "selected_option_id",
    "evidence_sources",
)

HOLD_FIELDS = (
    "id",
    "portfolio_key",
    "account_name",
    "blocking_condition",
    "primary_source",
    "corroborating_source",
    "owner",
    "deadline",
    "required_next_step",
)

TOP_LEVEL_FIELDS = ("schema_version", "task_id", "title", "company", "as_of")


def decision_model_leaves(model: Any, prefix: str = "") -> list[tuple[str, Any]]:
    """Flatten the graded decision model into dotted leaf paths.

    Dictionaries recurse; every other value (scalars and lists of scalars)
    is one exact-equality criterion.
    """

    if isinstance(model, dict):
        leaves: list[tuple[str, Any]] = []
        for key, child in model.items():
            leaves.extend(decision_model_leaves(child, f"{prefix}{key}."))
        return leaves
    return [(prefix[:-1], model)]


def _nested_value(value: Any, path: str) -> Any:
    current = value
    for part in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def score_changes(value: Any, spec: dict[str, Any]) -> dict[str, Any]:
    expected = spec["expected_changes"]
    actual = value if isinstance(value, dict) else {}
    rows = actual.get("changes") if isinstance(actual.get("changes"), list) else []
    holds = actual.get("holds") if isinstance(actual.get("holds"), list) else []
    rows_by_id = {
        str(row.get("id")): row
        for row in rows
        if isinstance(row, dict) and isinstance(row.get("id"), str)
    }
    row_ids = [row.get("id") for row in rows if isinstance(row, dict)]
    hold_rows_by_id = {
        str(row.get("id")): row
        for row in holds
        if isinstance(row, dict) and isinstance(row.get("id"), str)
    }
    hold_ids = [row.get("id") for row in holds if isinstance(row, dict)]
    criteria: dict[str, bool] = {
        "changes_is_object": isinstance(value, dict),
        "changes_exact_count": len(rows) == len(expected),
        "change_ids_unique": len(row_ids) == len(set(row_ids)) == len(expected),
        "holds_exact_count": len(holds) == spec["expected_hold_count"],
        "hold_ids_unique": (
            len(hold_ids) == len(set(hold_ids)) == spec["expected_hold_count"]
        ),
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
    decision_summary = (
        actual.get("decision_summary")
        if isinstance(actual.get("decision_summary"), dict)
        else {}
    )
    for key, expected_value in spec["expected_decision_summary"].items():
        criteria[f"decision_summary.{key}"] = (
            decision_summary.get(key) == expected_value
        )
    decision_model = (
        actual.get("decision_model")
        if isinstance(actual.get("decision_model"), dict)
        else {}
    )
    for path, expected_value in decision_model_leaves(
        spec.get("expected_decision_model", {})
    ):
        observed = _nested_value(decision_model, path)
        criteria[f"decision_model.{path}"] = (
            type(observed) is type(expected_value) and observed == expected_value
            if isinstance(expected_value, bool)
            else observed == expected_value
        )
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
    hold_details: list[dict[str, Any]] = []
    for expected_hold in spec["expected_holds"]:
        actual_hold = hold_rows_by_id.get(expected_hold["id"])
        checks = {"present": isinstance(actual_hold, dict)}
        criteria[f"{expected_hold['id']}.present"] = checks["present"]
        for field in HOLD_FIELDS:
            passed = (
                isinstance(actual_hold, dict)
                and actual_hold.get(field) == expected_hold[field]
            )
            checks[field] = bool(passed)
            criteria[f"{expected_hold['id']}.{field}"] = bool(passed)
        hold_details.append({"id": expected_hold["id"], "checks": checks})
    return {
        "criteria": criteria,
        "score": round(mean(criteria), 6),
        "passed": all(criteria.values()),
        "details": details,
        "hold_details": hold_details,
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
            change["decision_method"],
            change["decision_explanation"],
            change["selected_option_id"],
            *change["evidence_sources"],
        ]
        missing = [anchor for anchor in anchors if normalize(anchor) not in normalized]
        criteria[f"change.{change['id']}"] = not missing
        details.append({"id": change["id"], "missing_anchors": missing})
    decision = spec["expected_decision_summary"]
    decision_anchors = [
        decision["selected_option_id"],
        decision["method"],
        *decision["alternatives_considered"],
    ]
    missing_decision = [
        anchor for anchor in decision_anchors if normalize(str(anchor)) not in normalized
    ]
    criteria["decision_and_alternatives"] = not missing_decision
    model = spec.get("expected_decision_model", {})
    model_anchors: list[str] = []
    if model:
        model_anchors.append(str(model["business_need_date"]))
        model_anchors.append(str(model["decision_timing_status"]))
        for option in model.get("options", {}).values():
            model_anchors.extend(
                [
                    str(option["outcome"]),
                    f"USD {int(option['incremental_cost']):,}",
                    str(option["approval"]),
                ]
            )
    missing_model = [
        anchor for anchor in model_anchors if normalize(anchor) not in normalized
    ]
    criteria["alternatives_costed_and_dated"] = bool(model) and not missing_model
    hold_details: list[dict[str, Any]] = []
    for hold in spec["expected_holds"]:
        anchors = [
            hold["id"],
            hold["portfolio_key"],
            hold["account_name"],
            hold["blocking_condition"],
            hold["primary_source"],
            hold["corroborating_source"],
            hold["owner"],
            hold["deadline"],
            hold["required_next_step"],
        ]
        missing = [anchor for anchor in anchors if normalize(str(anchor)) not in normalized]
        criteria[f"hold.{hold['id']}"] = not missing
        hold_details.append({"id": hold["id"], "missing_anchors": missing})
    forbidden = [
        claim for claim in spec["forbidden_claims"] if normalize(claim) in normalized
    ]
    criteria["forbidden_claims_absent"] = not forbidden
    return {
        "criteria": criteria,
        "score": round(mean(criteria), 6),
        "passed": all(criteria.values()),
        "details": details,
        "decision_missing_anchors": missing_decision,
        "hold_details": hold_details,
        "forbidden_claims_present": forbidden,
    }


MILESTONE_IDS = (
    "investigation.scope",
    "investigation.evidence",
    "investigation.identity",
    "investigation.authority",
    "investigation.provider_correlation",
    "decision.portfolio",
    "decision.alternatives",
    "state.primary",
    "verification.readback",
    "containment.scope",
    "deliverable.decision_summary",
    "deliverable.changes",
    "deliverable.holds",
    "deliverable.brief",
    "execution.delivery",
)

PROCEDURE_MILESTONES = {
    "filesystem_discovery_completed": "investigation.scope",
    "custody_metadata_checked": "investigation.scope",
    "salesforce_discovery_completed": "investigation.scope",
    "hubspot_discovery_completed": "investigation.scope",
    "material_evidence_read_in_full": "investigation.evidence",
    "all_required_evidence_precedes_mutation": "investigation.evidence",
    "task_specific_investigation_completed": "investigation.identity",
    "all_salesforce_evidence_queried": "investigation.provider_correlation",
    "all_hubspot_evidence_retrieved": "investigation.provider_correlation",
    "all_gong_evidence_queried": "investigation.provider_correlation",
    "all_provider_evidence_precedes_mutation": "investigation.provider_correlation",
    "all_mutations_verified_by_readback": "verification.readback",
    "exact_deliverable_set": "execution.delivery",
    "deliverables_written_through_mcp": "execution.delivery",
    "no_rejected_mutation": "execution.delivery",
}

STATE_GLOBAL_CRITERIA = (
    "entire_business_state_exact",
    "no_delete_tool_succeeded",
    "gong_remained_read_only",
)

CHANGE_AUTHORITY_FIELDS = {
    "reason",
    "primary_source",
    "corroborating_source",
    "gong_evidence_id",
    "owner",
    "deadline",
    "evidence_sources",
}
CHANGE_DECISION_FIELDS = {
    "decision_method",
    "decision_inputs",
    "decision_explanation",
    "selected_option_id",
}
HOLD_AUTHORITY_FIELDS = {"blocking_condition", "primary_source", "corroborating_source"}


def milestone_for(component: str, criterion_id: str) -> str:
    """Map one atomic verifier criterion to its semantic milestone.

    The same mapping publishes the atomic rubric at build time and rolls the
    executed criteria into weighted milestones at verification time.
    """

    if component == "procedure":
        try:
            return PROCEDURE_MILESTONES[criterion_id]
        except KeyError as exc:
            raise ValueError(f"unmapped procedure criterion: {criterion_id}") from exc
    if component == "state":
        if criterion_id.endswith(".initial_value"):
            return "investigation.provider_correlation"
        if criterion_id.endswith(
            (".target_value", ".authorized_fields", ".exactly_one_authorized_call")
        ):
            return "state.primary"
        if criterion_id.endswith(".postwrite_readback"):
            return "verification.readback"
        if criterion_id in STATE_GLOBAL_CRITERIA:
            return "containment.scope"
        raise ValueError(f"unmapped state criterion: {criterion_id}")
    if component == "changes":
        if criterion_id == "changes_is_object" or criterion_id.startswith("top_level."):
            return "deliverable.decision_summary"
        if criterion_id in {"changes_exact_count", "change_ids_unique"}:
            return "deliverable.changes"
        if criterion_id in {"holds_exact_count", "hold_ids_unique"}:
            return "deliverable.holds"
        if criterion_id.startswith("decision_summary."):
            return "decision.portfolio"
        if criterion_id.startswith("decision_model."):
            return "decision.alternatives"
        if criterion_id.startswith("CHG-"):
            field = criterion_id.rsplit(".", 1)[-1]
            if field in CHANGE_AUTHORITY_FIELDS:
                return "investigation.authority"
            if field in CHANGE_DECISION_FIELDS:
                return "decision.portfolio"
            return "deliverable.changes"
        if criterion_id.startswith("HLD-"):
            field = criterion_id.rsplit(".", 1)[-1]
            return (
                "investigation.authority"
                if field in HOLD_AUTHORITY_FIELDS
                else "deliverable.holds"
            )
        raise ValueError(f"unmapped changes criterion: {criterion_id}")
    if component == "brief":
        if criterion_id == "decision_and_alternatives":
            return "decision.portfolio"
        if criterion_id == "alternatives_costed_and_dated":
            return "decision.alternatives"
        if criterion_id == "forbidden_claims_absent":
            return "containment.scope"
        return "deliverable.brief"
    raise ValueError(f"unknown verifier component: {component}")


def criterion_catalog(spec: dict[str, Any]) -> list[tuple[str, str]]:
    """Enumerate every atomic criterion the verifier produces for a task.

    The order mirrors the verifier components so the published rubric and the
    executed report agree criterion for criterion.
    """

    catalog: list[tuple[str, str]] = [
        ("procedure", criterion_id) for criterion_id in PROCEDURE_MILESTONES
    ]
    for change in spec["expected_changes"]:
        catalog.extend(
            ("state", f"{change['id']}.{suffix}")
            for suffix in (
                "initial_value",
                "target_value",
                "authorized_fields",
                "exactly_one_authorized_call",
                "postwrite_readback",
            )
        )
    catalog.extend(("state", criterion_id) for criterion_id in STATE_GLOBAL_CRITERIA)
    catalog.extend(
        ("changes", criterion_id)
        for criterion_id in (
            "changes_is_object",
            "changes_exact_count",
            "change_ids_unique",
            "holds_exact_count",
            "hold_ids_unique",
        )
    )
    catalog.extend(("changes", f"top_level.{field}") for field in TOP_LEVEL_FIELDS)
    catalog.extend(
        ("changes", f"decision_summary.{key}")
        for key in spec["expected_decision_summary"]
    )
    catalog.extend(
        ("changes", f"decision_model.{path}")
        for path, _ in decision_model_leaves(spec.get("expected_decision_model", {}))
    )
    for change in spec["expected_changes"]:
        catalog.append(("changes", f"{change['id']}.present"))
        catalog.extend(("changes", f"{change['id']}.{field}") for field in CHANGE_FIELDS)
    for hold in spec["expected_holds"]:
        catalog.append(("changes", f"{hold['id']}.present"))
        catalog.extend(("changes", f"{hold['id']}.{field}") for field in HOLD_FIELDS)
    catalog.extend(("brief", f"section.{section}") for section in spec["brief_sections"])
    catalog.extend(("brief", f"change.{change['id']}") for change in spec["expected_changes"])
    catalog.append(("brief", "decision_and_alternatives"))
    catalog.append(("brief", "alternatives_costed_and_dated"))
    catalog.extend(("brief", f"hold.{hold['id']}") for hold in spec["expected_holds"])
    catalog.append(("brief", "forbidden_claims_absent"))
    return catalog


def semantic_checks(
    procedure: dict[str, bool],
    state: dict[str, Any],
    changes: dict[str, Any],
    brief: dict[str, Any],
    spec: dict[str, Any],
) -> list[dict[str, Any]]:
    raw = {
        "procedure": procedure,
        "state": state["criteria"],
        "changes": changes["criteria"],
        "brief": brief["criteria"],
    }
    groups: dict[str, list[tuple[str, str]]] = {
        milestone["id"]: [] for milestone in spec["rubric_milestones"]
    }
    for component, criteria in raw.items():
        for criterion_id in criteria:
            milestone_id = milestone_for(component, criterion_id)
            if milestone_id not in groups:
                raise ValueError(f"unknown semantic milestone: {milestone_id}")
            groups[milestone_id].append((component, criterion_id))

    all_raw = {
        (component, criterion_id)
        for component, criteria in raw.items()
        for criterion_id in criteria
    }
    assigned = [reference for references in groups.values() for reference in references]
    if len(assigned) != len(set(assigned)):
        raise ValueError("one atomic criterion was assigned to multiple semantic milestones")
    unassigned = sorted(all_raw - set(assigned))
    unknown = sorted(set(assigned) - all_raw)
    if unassigned or unknown:
        raise ValueError(
            f"semantic rubric mapping mismatch; unassigned={unassigned}, unknown={unknown}"
        )

    rubric_by_id = {milestone["id"]: milestone for milestone in spec["rubric_milestones"]}
    checks: list[dict[str, Any]] = []
    for milestone_id, references in groups.items():
        if not references:
            raise ValueError(f"semantic milestone has no atomic evidence: {milestone_id}")
        passed_count = sum(raw[component][criterion_id] for component, criterion_id in references)
        fraction = passed_count / len(references)
        milestone = rubric_by_id[milestone_id]
        checks.append(
            {
                "id": milestone_id,
                "category": milestone["category"],
                "description": milestone["description"],
                "weight": float(milestone["weight"]),
                "earned_weight": round(float(milestone["weight"]) * fraction, 6),
                "passed": passed_count == len(references),
                "evidence": {
                    "passed_criteria": passed_count,
                    "total_criteria": len(references),
                    "subchecks": [
                        {
                            "component": component,
                            "id": criterion_id,
                            "passed": bool(raw[component][criterion_id]),
                        }
                        for component, criterion_id in references
                    ],
                },
            }
        )
    if sum(check["weight"] for check in checks) != 100.0:
        raise ValueError("semantic milestone weights must total 100")
    return checks


def aggregate_scores(
    procedure: dict[str, bool],
    state: dict[str, Any],
    changes: dict[str, Any],
    brief: dict[str, Any],
    spec: dict[str, Any],
    *,
    successful_tool_calls: int = -1,
) -> dict[str, Any]:
    scores = {
        "procedure": round(mean(procedure), 6),
        "state": state["score"],
        "changes": changes["score"],
        "brief": brief["score"],
    }
    checks = semantic_checks(procedure, state, changes, brief, spec)
    semantic_weights = {
        check["id"]: round(float(check["weight"]) / 100, 6) for check in checks
    }
    uncapped = sum(float(check["earned_weight"]) for check in checks) / 100
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
    passed = all(check["passed"] for check in checks)
    return {
        "passed": passed,
        "reward": round(reward, 6),
        "uncapped_reward": round(uncapped, 6),
        "cap_reason": cap_reason,
        "category_scores": scores,
        "weights": semantic_weights,
        "semantic_checks": checks,
    }
