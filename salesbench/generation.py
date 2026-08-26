"""Deterministic SalesBench-100 task and evidence generation."""

from __future__ import annotations

import csv
import hashlib
import html
import io
import json
import random
import re
from copy import deepcopy
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import PurePosixPath
from typing import Any

from .catalog import FAMILY_SETTINGS, TASK_SPINES, TaskSpine
from .contracts import CONTRACT_PINS


RELEASE_VERSION = "1.0.1"
FIXED_FILE_TIMESTAMP = "2026-08-26T12:00:00.000Z"
DOCUMENT_COUNT = 96
METADATA_CHECK_COUNT = 8
TARGET_CHANGE_COUNT = 12
PORTFOLIO_ENTITY_COUNT = 16
DISTRACTOR_ENTITY_COUNT = 48
MINIMUM_TOOL_CALLS = 163
DELIVERABLES = ("changes.json", "brief.md")

OWNERS = (
    ("005SB000000001", "Maya Chen", "Enterprise AE"),
    ("005SB000000002", "Jon Bell", "Commercial AE"),
    ("005SB000000003", "Priya Raman", "Strategic AE"),
    ("005SB000000004", "Luis Ortega", "Regional AE"),
    ("005SB000000005", "Amina Yusuf", "Account Director"),
    ("005SB000000006", "Theo Martin", "Channel Manager"),
    ("005SB000000007", "Nora Kim", "Renewals Manager"),
    ("005SB000000008", "Elena Rossi", "SDR Manager"),
)

STAGES = (
    "Prospecting",
    "Qualification",
    "Discovery",
    "Technical Validation",
    "Proposal",
    "Negotiation",
)

SIGNALS = (
    "economic buyer confirmed procurement timing",
    "security review remains seller-owned",
    "champion requested a revised mutual action plan",
    "finance validation is complete but legal review is open",
    "buyer explicitly paused the evaluation",
    "implementation capacity moved to the following quarter",
    "competitive evaluation narrowed to two vendors",
    "renewal notice was acknowledged by procurement",
)

RISK_CODES = (
    "procurement_timing",
    "security_review",
    "single_threaded",
    "commercial_terms",
    "support_recovery",
    "consent_conflict",
    "identity_ambiguity",
    "stage_evidence_gap",
)

EXTENSIONS = ("md", "txt", "json", "csv", "eml", "xml", "html", "md")


@dataclass(frozen=True)
class GeneratedTask:
    task_id: str
    spine: TaskSpine
    prompt: str
    documents: dict[str, str]
    spec: dict[str, Any]
    reference: dict[str, Any]
    seed: dict[str, Any]


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def stable_seed(value: str) -> int:
    return int(sha256_text(value)[:16], 16)


def verification_token(task_id: str) -> str:
    return sha256_text(f"SalesBench-100 verifier capability::{task_id}")


def task_id_for(index: int, slug: str) -> str:
    return f"sb100-{index:03d}-{slug}"


def _sf_id(prefix: str, task_number: int, slot: int) -> str:
    return f"{prefix}SB{task_number:03d}{slot:06d}"[:18]


def _hub_id(task_number: int, slot: int, offset: int) -> str:
    return str(8_000_000_000 + task_number * 100_000 + offset + slot)


def _as_of(task_number: int) -> str:
    return (date(2026, 8, 26) + timedelta(days=task_number % 19)).isoformat()


def _money(task_number: int, slot: int) -> int:
    return 180_000 + ((task_number * 83_719 + slot * 137_113) % 4_700_000)


def _entity_name(spine: TaskSpine, slot: int) -> str:
    roots = (
        "Alder", "Beacon", "Cobalt", "Dovetail", "Evergreen", "Foxglove",
        "Granite", "Harbor", "Indigo", "Juniper", "Keystone", "Lantern",
        "Meridian", "Northstar", "Orchard", "Palisade",
    )
    suffixes = (
        "Group", "Holdings", "Systems", "Partners", "Networks", "Labs",
        "Industries", "Collective", "Works", "Technologies", "Services",
        "Ventures", "Enterprises", "Cooperative", "Platform", "Corporation",
    )
    return f"{roots[slot]} {suffixes[(slot + stable_seed(spine.slug)) % len(suffixes)]}"


def build_entities(spine: TaskSpine, task_number: int) -> list[dict[str, Any]]:
    rng = random.Random(stable_seed(spine.slug))
    target_slots = set(rng.sample(range(PORTFOLIO_ENTITY_COUNT), TARGET_CHANGE_COUNT))
    entities: list[dict[str, Any]] = []
    for slot in range(PORTFOLIO_ENTITY_COUNT):
        owner_id, owner_name, owner_role = OWNERS[(task_number + slot) % len(OWNERS)]
        amount = _money(task_number, slot)
        stage = STAGES[(task_number + slot * 3) % len(STAGES)]
        signal = SIGNALS[(task_number * 2 + slot) % len(SIGNALS)]
        risk_code = RISK_CODES[(task_number + slot * 5) % len(RISK_CODES)]
        account_name = _entity_name(spine, slot)
        close_date = (
            date(2026, 8, 30) + timedelta(days=((task_number + slot * 7) % 108))
        ).isoformat()
        entities.append(
            {
                "slot": slot,
                "portfolio_key": f"SBP-{task_number:03d}-{slot + 1:02d}",
                "account_name": account_name,
                "domain": re.sub(r"[^a-z0-9]", "", account_name.lower()) + ".example",
                "sf_account_id": _sf_id("001", task_number, slot),
                "sf_opportunity_id": _sf_id("006", task_number, slot),
                "sf_contact_id": _sf_id("003", task_number, slot),
                "sf_lead_id": _sf_id("00Q", task_number, slot),
                "sf_quote_id": _sf_id("0Q0", task_number, slot),
                "sf_campaign_member_id": _sf_id("00v", task_number, slot),
                "sf_task_id": _sf_id("00T", task_number, slot),
                "hs_company_id": _hub_id(task_number, slot, 10_000),
                "hs_deal_id": _hub_id(task_number, slot, 20_000),
                "hs_contact_id": _hub_id(task_number, slot, 30_000),
                "hs_task_id": _hub_id(task_number, slot, 40_000),
                "gong_account_id": _sf_id("001", task_number, slot),
                "gong_deal_id": _sf_id("006", task_number, slot),
                "owner_id": owner_id,
                "owner_name": owner_name,
                "owner_role": owner_role,
                "amount": amount,
                "stage": stage,
                "close_date": close_date,
                "signal": signal,
                "risk_code": risk_code,
                "target": slot in target_slots,
                "evidence_id": f"GE-{task_number:03d}-{slot + 1:02d}",
                "deadline": (
                    date.fromisoformat(_as_of(task_number))
                    + timedelta(days=3 + (slot % 6))
                ).isoformat(),
            }
        )
    return entities


def _update_change(
    *,
    task_number: int,
    sequence: int,
    entity: dict[str, Any],
    system: str,
    object_type: str,
    record_id: str,
    field: str,
    before: Any,
    after: Any,
    tool: str,
    arguments: dict[str, Any],
    reason: str,
) -> dict[str, Any]:
    return {
        "id": f"CHG-{task_number:03d}-{sequence:02d}",
        "system": system,
        "object_type": object_type,
        "record_id": record_id,
        "operation": "update",
        "field": field,
        "before": before,
        "after": after,
        "reason": reason,
        "owner": entity["owner_name"],
        "deadline": entity["deadline"],
        "portfolio_key": entity["portfolio_key"],
        "gong_evidence_id": entity["evidence_id"],
        "tool": tool,
        "arguments": arguments,
    }


def build_changes(
    spine: TaskSpine,
    task_number: int,
    entities: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    targets = [entity for entity in entities if entity["target"]]
    targets.sort(key=lambda entity: entity["portfolio_key"])
    changes: list[dict[str, Any]] = []
    for sequence, entity in enumerate(targets, start=1):
        alternate = sequence % 2 == 0
        reason = (
            f"{entity['portfolio_key']} qualifies for {FAMILY_SETTINGS[spine.family]['mutation']} "
            f"because {entity['signal']}; apply {entity['risk_code']} under the current {spine.period} policy."
        )
        if spine.family == "forecast-reconciliation":
            if alternate:
                field, before, after = "forecast_status", "pipeline", "commit"
                arguments = {
                    "object_type": "deals",
                    "object_id": entity["hs_deal_id"],
                    "properties": {field: after},
                }
                change = _update_change(
                    task_number=task_number, sequence=sequence, entity=entity,
                    system="hubspot", object_type="deals", record_id=entity["hs_deal_id"],
                    field=field, before=before, after=after,
                    tool="hubspot_update_object", arguments=arguments, reason=reason,
                )
            else:
                field, before, after = "ForecastCategoryName", "Pipeline", "Commit"
                arguments = {
                    "sobject-name": "Opportunity",
                    "id": entity["sf_opportunity_id"],
                    "body": {field: after},
                }
                change = _update_change(
                    task_number=task_number, sequence=sequence, entity=entity,
                    system="salesforce", object_type="Opportunity", record_id=entity["sf_opportunity_id"],
                    field=field, before=before, after=after,
                    tool="updateSobjectRecord", arguments=arguments, reason=reason,
                )
        elif spine.family in {"pipeline-recovery", "gong-action-reconciliation"}:
            if alternate:
                field, before, after = "hs_task_status", "DEFERRED", "NOT_STARTED"
                arguments = {
                    "object_type": "tasks",
                    "object_id": entity["hs_task_id"],
                    "properties": {
                        field: after,
                        "hs_task_subject": f"{entity['portfolio_key']} grounded recovery action",
                    },
                }
                change = _update_change(
                    task_number=task_number, sequence=sequence, entity=entity,
                    system="hubspot", object_type="tasks", record_id=entity["hs_task_id"],
                    field=field, before=before, after=after,
                    tool="hubspot_update_object", arguments=arguments, reason=reason,
                )
            else:
                field, before, after = "Status", "Deferred", "Not Started"
                arguments = {
                    "sobject-name": "Task", "id": entity["sf_task_id"],
                    "body": {
                        field: after,
                        "Subject": f"{entity['portfolio_key']} grounded recovery action",
                    },
                }
                change = _update_change(
                    task_number=task_number, sequence=sequence, entity=entity,
                    system="salesforce", object_type="Task", record_id=entity["sf_task_id"],
                    field=field, before=before, after=after,
                    tool="updateSobjectRecord", arguments=arguments, reason=reason,
                )
        elif spine.family == "identity-migration":
            if alternate:
                field, before, after = "salesforce_account_id", "", entity["sf_account_id"]
                arguments = {
                    "object_type": "companies", "object_id": entity["hs_company_id"],
                    "properties": {field: after},
                }
                change = _update_change(
                    task_number=task_number, sequence=sequence, entity=entity,
                    system="hubspot", object_type="companies", record_id=entity["hs_company_id"],
                    field=field, before=before, after=after,
                    tool="hubspot_update_object", arguments=arguments, reason=reason,
                )
            else:
                field, before, after = "HubSpot_Company_ID__c", "", entity["hs_company_id"]
                arguments = {
                    "sobject-name": "Account", "id": entity["sf_account_id"],
                    "body": {field: after},
                }
                change = _update_change(
                    task_number=task_number, sequence=sequence, entity=entity,
                    system="salesforce", object_type="Account", record_id=entity["sf_account_id"],
                    field=field, before=before, after=after,
                    tool="updateSobjectRecord", arguments=arguments, reason=reason,
                )
        elif spine.family == "lead-routing":
            if alternate:
                field, before, after = "hubspot_owner_id", "unassigned", entity["owner_id"]
                arguments = {
                    "object_type": "contacts", "object_id": entity["hs_contact_id"],
                    "properties": {field: after, "lifecyclestage": "salesqualifiedlead"},
                }
                change = _update_change(
                    task_number=task_number, sequence=sequence, entity=entity,
                    system="hubspot", object_type="contacts", record_id=entity["hs_contact_id"],
                    field=field, before=before, after=after,
                    tool="hubspot_update_object", arguments=arguments, reason=reason,
                )
            else:
                field, before, after = "OwnerId", "00GQUEUE", entity["owner_id"]
                arguments = {
                    "sobject-name": "Lead", "id": entity["sf_lead_id"],
                    "body": {field: after, "Status": "Working - Contacted"},
                }
                change = _update_change(
                    task_number=task_number, sequence=sequence, entity=entity,
                    system="salesforce", object_type="Lead", record_id=entity["sf_lead_id"],
                    field=field, before=before, after=after,
                    tool="updateSobjectRecord", arguments=arguments, reason=reason,
                )
        elif spine.family == "renewal-expansion":
            if alternate:
                field, before, after = "renewal_risk", "unreviewed", entity["risk_code"]
                arguments = {
                    "object_type": "deals", "object_id": entity["hs_deal_id"],
                    "properties": {field: after, "next_step": entity["signal"]},
                }
                change = _update_change(
                    task_number=task_number, sequence=sequence, entity=entity,
                    system="hubspot", object_type="deals", record_id=entity["hs_deal_id"],
                    field=field, before=before, after=after,
                    tool="hubspot_update_object", arguments=arguments, reason=reason,
                )
            else:
                field, before, after = "Renewal_Risk__c", "Unreviewed", entity["risk_code"]
                arguments = {
                    "sobject-name": "Opportunity", "id": entity["sf_opportunity_id"],
                    "body": {field: after, "NextStep": entity["signal"]},
                }
                change = _update_change(
                    task_number=task_number, sequence=sequence, entity=entity,
                    system="salesforce", object_type="Opportunity", record_id=entity["sf_opportunity_id"],
                    field=field, before=before, after=after,
                    tool="updateSobjectRecord", arguments=arguments, reason=reason,
                )
        elif spine.family == "quote-governance":
            if alternate:
                field, before, after = "quote_readiness", "unreviewed", "ready_with_conditions"
                arguments = {
                    "object_type": "deals", "object_id": entity["hs_deal_id"],
                    "properties": {field: after, "deal_risk_code": entity["risk_code"]},
                }
                change = _update_change(
                    task_number=task_number, sequence=sequence, entity=entity,
                    system="hubspot", object_type="deals", record_id=entity["hs_deal_id"],
                    field=field, before=before, after=after,
                    tool="hubspot_update_object", arguments=arguments, reason=reason,
                )
            else:
                field, before, after = "Readiness_Status__c", "Unreviewed", "Ready with Conditions"
                arguments = {
                    "sobject-name": "Quote", "id": entity["sf_quote_id"],
                    "body": {field: after, "Risk_Code__c": entity["risk_code"]},
                }
                change = _update_change(
                    task_number=task_number, sequence=sequence, entity=entity,
                    system="salesforce", object_type="Quote", record_id=entity["sf_quote_id"],
                    field=field, before=before, after=after,
                    tool="updateSobjectRecord", arguments=arguments, reason=reason,
                )
        elif spine.family == "account-planning":
            role = ("Economic Buyer", "Champion", "Technical Evaluator", "Procurement")[(sequence - 1) % 4]
            if alternate:
                field, before, after = "buying_role", "Unknown", role
                arguments = {
                    "object_type": "contacts", "object_id": entity["hs_contact_id"],
                    "properties": {field: after},
                }
                change = _update_change(
                    task_number=task_number, sequence=sequence, entity=entity,
                    system="hubspot", object_type="contacts", record_id=entity["hs_contact_id"],
                    field=field, before=before, after=after,
                    tool="hubspot_update_object", arguments=arguments, reason=reason,
                )
            else:
                field, before, after = "Buying_Role__c", "Unknown", role
                arguments = {
                    "sobject-name": "Contact", "id": entity["sf_contact_id"],
                    "body": {field: after},
                }
                change = _update_change(
                    task_number=task_number, sequence=sequence, entity=entity,
                    system="salesforce", object_type="Contact", record_id=entity["sf_contact_id"],
                    field=field, before=before, after=after,
                    tool="updateSobjectRecord", arguments=arguments, reason=reason,
                )
        elif spine.family == "sequence-compliance":
            if alternate:
                field, before, after = "sequence_status", "ACTIVE", "PAUSED_COMPLIANCE"
                arguments = {
                    "object_type": "contacts", "object_id": entity["hs_contact_id"],
                    "properties": {field: after, "compliance_reason": entity["risk_code"]},
                }
                change = _update_change(
                    task_number=task_number, sequence=sequence, entity=entity,
                    system="hubspot", object_type="contacts", record_id=entity["hs_contact_id"],
                    field=field, before=before, after=after,
                    tool="hubspot_update_object", arguments=arguments, reason=reason,
                )
            else:
                field, before, after = "Status", "Sent", "Removed - Compliance"
                arguments = {
                    "sobject-name": "CampaignMember", "id": entity["sf_campaign_member_id"],
                    "body": {field: after, "Compliance_Reason__c": entity["risk_code"]},
                }
                change = _update_change(
                    task_number=task_number, sequence=sequence, entity=entity,
                    system="salesforce", object_type="CampaignMember", record_id=entity["sf_campaign_member_id"],
                    field=field, before=before, after=after,
                    tool="updateSobjectRecord", arguments=arguments, reason=reason,
                )
        else:  # cutover-audit
            if alternate:
                field, before, after = "salesforce_opportunity_id", "", entity["sf_opportunity_id"]
                arguments = {
                    "object_type": "deals", "object_id": entity["hs_deal_id"],
                    "properties": {field: after},
                }
                change = _update_change(
                    task_number=task_number, sequence=sequence, entity=entity,
                    system="hubspot", object_type="deals", record_id=entity["hs_deal_id"],
                    field=field, before=before, after=after,
                    tool="hubspot_update_object", arguments=arguments, reason=reason,
                )
            else:
                field, before, after = "HubSpot_Deal_ID__c", "", entity["hs_deal_id"]
                arguments = {
                    "sobject-name": "Opportunity", "id": entity["sf_opportunity_id"],
                    "body": {field: after},
                }
                change = _update_change(
                    task_number=task_number, sequence=sequence, entity=entity,
                    system="salesforce", object_type="Opportunity", record_id=entity["sf_opportunity_id"],
                    field=field, before=before, after=after,
                    tool="updateSobjectRecord", arguments=arguments, reason=reason,
                )
        changes.append(change)
    if len(changes) != TARGET_CHANGE_COUNT:
        raise ValueError(f"expected {TARGET_CHANGE_COUNT} changes, got {len(changes)}")
    return changes


def _event_lines(entity: dict[str, Any], task_number: int, artifact_number: int) -> list[str]:
    base = date(2026, 5, 1) + timedelta(days=(task_number + artifact_number) % 50)
    return [
        f"{(base + timedelta(days=offset * 5)).isoformat()} | EVT-{task_number:03d}-{artifact_number:03d}-{offset + 1} | "
        f"{('buyer' if offset % 2 == 0 else 'seller')} | {SIGNALS[(entity['slot'] + offset) % len(SIGNALS)]}"
        for offset in range(34)
    ]


def _artifact_payload(
    *,
    spine: TaskSpine,
    task_id: str,
    task_number: int,
    folder: str,
    artifact_number: int,
    entity: dict[str, Any],
    change: dict[str, Any] | None,
) -> dict[str, Any]:
    control = {
        "task_id": task_id,
        "portfolio_key": entity["portfolio_key"],
        "account_name": entity["account_name"],
        "salesforce_account_id": entity["sf_account_id"],
        "salesforce_opportunity_id": entity["sf_opportunity_id"],
        "hubspot_company_id": entity["hs_company_id"],
        "hubspot_deal_id": entity["hs_deal_id"],
        "gong_evidence_id": entity["evidence_id"],
        "period": spine.period,
        "as_of": _as_of(task_number),
        "folder": folder,
        "source_version": f"v{1 + artifact_number % 4}.{artifact_number % 9}",
        "classification": "synthetic-confidential",
    }
    decision = {
        "eligible_for_requested_workflow": bool(change),
        "decision_code": change["id"] if change else f"HOLD-{task_number:03d}-{entity['slot'] + 1:02d}",
        "authorized_system": change["system"] if change else "none",
        "authorized_record_id": change["record_id"] if change else "none",
        "authorized_field": change["field"] if change else "none",
        "current_value": change["before"] if change else "unchanged",
        "required_value": change["after"] if change else "unchanged",
        "reason": change["reason"] if change else (
            f"{entity['portfolio_key']} is a control record. Evidence does not authorize a mutation; "
            "retain current state and include it only in coverage counts."
        ),
        "owner": entity["owner_name"],
        "deadline": entity["deadline"],
    }
    return {
        "record_control": control,
        "business_context": {
            "benchmark_company": spine.company,
            "portfolio_account": entity["account_name"],
            "industry": spine.industry,
            "region": spine.region,
            "requester": spine.requester,
            "amount_usd": entity["amount"],
            "stage": entity["stage"],
            "close_date": entity["close_date"],
            "owner": entity["owner_name"],
            "owner_role": entity["owner_role"],
        },
        "evidence": {
            "signal": entity["signal"],
            "risk_code": entity["risk_code"],
            "gong_summary": (
                f"Permitted Gong insight {entity['evidence_id']} supports {entity['signal']} "
                "without exposing raw or private transcript content."
            ),
            "source_of_truth": (
                f"For {spine.family}, apply the field-specific current-period rule. "
                "A CRM timestamp alone never overrides the evidence register."
            ),
            "events": _event_lines(entity, task_number, artifact_number),
        },
        "decision": decision,
        "controls": {
            "gong_is_read_only": True,
            "deletes_authorized": False,
            "neighboring_records_must_remain_unchanged": True,
            "private_call_content_may_be_copied": False,
            "duplicate_mutations_allowed": False,
        },
    }


def _render_payload(payload: dict[str, Any], extension: str) -> str:
    if extension == "json":
        return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if extension == "csv":
        stream = io.StringIO()
        writer = csv.writer(stream)
        writer.writerow(["section", "field", "value"])
        for section, values in payload.items():
            if isinstance(values, dict):
                for field, value in values.items():
                    writer.writerow([section, field, json.dumps(value, ensure_ascii=False)])
            else:
                writer.writerow(["root", section, json.dumps(values, ensure_ascii=False)])
        return stream.getvalue()
    if extension == "xml":
        sections = []
        for section, values in payload.items():
            sections.append(
                f"  <section name=\"{html.escape(section)}\"><![CDATA[{json.dumps(values, ensure_ascii=False, indent=2)}]]></section>"
            )
        return "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<salesbench-record>\n" + "\n".join(sections) + "\n</salesbench-record>\n"
    if extension == "html":
        rendered = html.escape(json.dumps(payload, ensure_ascii=False, indent=2))
        return f"<!doctype html><html><head><meta charset=\"utf-8\"><title>Sales evidence record</title></head><body><h1>Sales evidence record</h1><pre>{rendered}</pre></body></html>\n"
    if extension == "eml":
        control = payload["record_control"]
        return (
            f"From: revenue-operations@{control['task_id']}.example\n"
            f"To: portfolio-review@{control['task_id']}.example\n"
            f"Date: Wed, 26 Aug 2026 12:00:00 -0700\n"
            f"Subject: Evidence register {control['portfolio_key']} / {control['folder']}\n"
            "MIME-Version: 1.0\nContent-Type: text/plain; charset=UTF-8\n\n"
            + json.dumps(payload, ensure_ascii=False, indent=2)
            + "\n"
        )
    heading = "#" if extension == "md" else ""
    lines = [
        f"{heading} Sales evidence record".strip(),
        "",
        json.dumps(payload, ensure_ascii=False, indent=2),
        "",
        "Certification: synthetic benchmark record; verify identifiers in the live CRM tools before mutation.",
    ]
    return "\n".join(lines) + "\n"


def build_documents(
    spine: TaskSpine,
    task_id: str,
    task_number: int,
    entities: list[dict[str, Any]],
    changes: list[dict[str, Any]],
) -> tuple[dict[str, str], dict[str, list[str]]]:
    changes_by_key = {change["portfolio_key"]: change for change in changes}
    folders = FAMILY_SETTINGS[spine.family]["folders"]
    documents: dict[str, str] = {}
    paths_by_key: dict[str, list[str]] = {entity["portfolio_key"]: [] for entity in entities}
    for folder_index, folder in enumerate(folders):
        for file_index, extension in enumerate(EXTENSIONS):
            artifact_number = folder_index * len(EXTENSIONS) + file_index + 1
            entity = entities[(artifact_number - 1) % len(entities)]
            filename = f"{artifact_number:03d}_{entity['portfolio_key'].lower()}_{folder}.{extension}"
            relative = f"{folder}/{filename}"
            payload = _artifact_payload(
                spine=spine,
                task_id=task_id,
                task_number=task_number,
                folder=folder,
                artifact_number=artifact_number,
                entity=entity,
                change=changes_by_key.get(entity["portfolio_key"]),
            )
            documents[relative] = _render_payload(payload, extension)
            paths_by_key[entity["portfolio_key"]].append(
                str(PurePosixPath("/workspace/documents") / relative)
            )
    if len(documents) != DOCUMENT_COUNT:
        raise ValueError(f"expected {DOCUMENT_COUNT} documents, got {len(documents)}")
    return documents, paths_by_key


def _distractor_name(task_number: int, slot: int) -> str:
    return f"Control Account {task_number:03d}-{slot + 1:03d}"


def build_seed(
    spine: TaskSpine,
    task_number: int,
    entities: list[dict[str, Any]],
) -> dict[str, Any]:
    sf: dict[str, list[dict[str, Any]]] = {
        "Account": [], "Opportunity": [], "Contact": [], "Lead": [],
        "Quote": [], "Task": [], "CampaignMember": [],
    }
    hs: dict[str, list[dict[str, Any]]] = {
        "companies": [], "deals": [], "contacts": [], "tasks": [], "notes": [],
    }
    gong_accounts: dict[str, dict[str, Any]] = {}
    gong_deals: dict[str, dict[str, Any]] = {}
    for entity in entities:
        common = {
            "SalesBenchKey__c": entity["portfolio_key"],
            "LastModifiedDate": f"{_as_of(task_number)}T09:00:00.000Z",
        }
        sf["Account"].append({
            "Id": entity["sf_account_id"], "Name": entity["account_name"],
            "Website": entity["domain"], "OwnerId": entity["owner_id"],
            "HubSpot_Company_ID__c": "", **common,
        })
        sf["Opportunity"].append({
            "Id": entity["sf_opportunity_id"], "Name": f"{entity['account_name']} {spine.period}",
            "AccountId": entity["sf_account_id"], "Amount": entity["amount"],
            "StageName": entity["stage"], "CloseDate": entity["close_date"],
            "ForecastCategoryName": "Pipeline", "NextStep": "", "Renewal_Risk__c": "Unreviewed",
            "HubSpot_Deal_ID__c": "", "OwnerId": entity["owner_id"], **common,
        })
        sf["Contact"].append({
            "Id": entity["sf_contact_id"], "AccountId": entity["sf_account_id"],
            "Name": f"Jordan {entity['account_name'].split()[0]}",
            "Email": f"jordan@{entity['domain']}", "Buying_Role__c": "Unknown", **common,
        })
        sf["Lead"].append({
            "Id": entity["sf_lead_id"], "Company": entity["account_name"],
            "Email": f"inbound@{entity['domain']}", "OwnerId": "00GQUEUE",
            "Status": "Open - Not Contacted", **common,
        })
        sf["Quote"].append({
            "Id": entity["sf_quote_id"], "OpportunityId": entity["sf_opportunity_id"],
            "Name": f"Quote {entity['portfolio_key']}", "Status": "Draft",
            "Readiness_Status__c": "Unreviewed", "Risk_Code__c": "", **common,
        })
        sf["Task"].append({
            "Id": entity["sf_task_id"], "WhatId": entity["sf_opportunity_id"],
            "Subject": f"Deferred review {entity['portfolio_key']}", "Status": "Deferred",
            "OwnerId": entity["owner_id"], "ActivityDate": entity["deadline"], **common,
        })
        sf["CampaignMember"].append({
            "Id": entity["sf_campaign_member_id"], "LeadOrContactId": entity["sf_contact_id"],
            "Status": "Sent", "Compliance_Reason__c": "", **common,
        })

        hs_common = {
            "createdAt": "2026-04-01T12:00:00.000Z",
            "updatedAt": f"{_as_of(task_number)}T09:00:00.000Z",
            "archived": False,
        }
        hs["companies"].append({
            "id": entity["hs_company_id"],
            "properties": {
                "name": entity["account_name"], "domain": entity["domain"],
                "salesforce_account_id": "", "salesbench_key": entity["portfolio_key"],
            }, **hs_common,
        })
        hs["deals"].append({
            "id": entity["hs_deal_id"],
            "properties": {
                "dealname": f"{entity['account_name']} {spine.period}",
                "amount": str(entity["amount"]), "dealstage": entity["stage"],
                "closedate": entity["close_date"], "forecast_status": "pipeline",
                "renewal_risk": "unreviewed", "quote_readiness": "unreviewed",
                "deal_risk_code": "", "next_step": "", "salesforce_opportunity_id": "",
                "salesbench_key": entity["portfolio_key"],
            }, **hs_common,
        })
        hs["contacts"].append({
            "id": entity["hs_contact_id"],
            "properties": {
                "email": f"jordan@{entity['domain']}", "firstname": "Jordan",
                "lastname": entity["account_name"].split()[0],
                "hubspot_owner_id": "unassigned", "lifecyclestage": "lead",
                "buying_role": "Unknown", "sequence_status": "ACTIVE",
                "compliance_reason": "", "salesbench_key": entity["portfolio_key"],
            }, **hs_common,
        })
        hs["tasks"].append({
            "id": entity["hs_task_id"],
            "properties": {
                "hs_task_subject": f"Deferred review {entity['portfolio_key']}",
                "hs_task_status": "DEFERRED", "hs_timestamp": entity["deadline"],
                "hubspot_owner_id": entity["owner_id"], "salesbench_key": entity["portfolio_key"],
            }, **hs_common,
        })
        gong_payload = {
            "workspaceId": f"ws-{task_number:03d}",
            "accountId": entity["gong_account_id"],
            "dealId": entity["gong_deal_id"],
            "timePeriod": "THIS_QUARTER",
            "evidenceId": entity["evidence_id"],
            "answer": entity["signal"],
            "themes": [entity["risk_code"], "next steps", "stakeholder alignment"],
            "stakeholders": [{"name": f"Jordan {entity['account_name'].split()[0]}", "role": "buyer"}],
            "risks": [entity["risk_code"]],
            "nextSteps": [entity["signal"]],
            "privateActivityExcluded": True,
        }
        gong_accounts[entity["gong_account_id"]] = deepcopy(gong_payload)
        gong_deals[entity["gong_deal_id"]] = deepcopy(gong_payload)

    for slot in range(DISTRACTOR_ENTITY_COUNT):
        sf["Account"].append({
            "Id": _sf_id("001", task_number + 500, slot),
            "Name": _distractor_name(task_number, slot),
            "Website": f"control-{task_number:03d}-{slot + 1:03d}.example",
            "OwnerId": OWNERS[slot % len(OWNERS)][0],
            "HubSpot_Company_ID__c": "",
            "SalesBenchKey__c": f"CTRL-{task_number:03d}-{slot + 1:03d}",
            "LastModifiedDate": "2026-05-01T09:00:00.000Z",
        })
        sf["Opportunity"].append({
            "Id": _sf_id("006", task_number + 500, slot),
            "Name": f"{_distractor_name(task_number, slot)} control deal",
            "AccountId": _sf_id("001", task_number + 500, slot),
            "Amount": 25_000 + slot * 1000,
            "StageName": "Prospecting", "CloseDate": "2027-03-31",
            "ForecastCategoryName": "Pipeline", "NextStep": "Routine nurture",
            "Renewal_Risk__c": "Unreviewed", "HubSpot_Deal_ID__c": "",
            "OwnerId": OWNERS[slot % len(OWNERS)][0],
            "SalesBenchKey__c": f"CTRL-{task_number:03d}-{slot + 1:03d}",
            "LastModifiedDate": "2026-05-01T09:00:00.000Z",
        })

    return {
        "schema_version": "salesbench.seed.v1",
        "task_id": task_id_for(task_number, spine.slug),
        "salesforce": {
            "user": {
                "userId": "005SB000000000", "name": spine.requester,
                "email": f"requester-{task_number:03d}@salesbench.example",
                "profile": "SalesBench Revenue Operations", "timezone": "America/Los_Angeles",
            },
            "objects": sf,
        },
        "hubspot": {
            "account_details": {
                "portalId": 900000 + task_number, "timeZone": "America/Los_Angeles",
                "companyCurrency": "USD", "dataHostingLocation": "United_States",
            },
            "objects": hs,
            "associations": [
                {
                    "from": {"type": "deals", "id": entity["hs_deal_id"]},
                    "to": {"type": "companies", "id": entity["hs_company_id"]},
                    "category": "HUBSPOT_DEFINED",
                }
                for entity in entities
            ],
        },
        "gong": {
            "workspace_id": f"ws-{task_number:03d}",
            "accounts": gong_accounts,
            "deals": gong_deals,
            "brief_templates": ["Executive Account Review", "Deal Inspection", "Renewal Handoff"],
        },
    }


def _reference_calls(
    entities: list[dict[str, Any]],
    changes: list[dict[str, Any]],
    document_paths: list[str],
    metadata_paths: list[str],
) -> list[dict[str, Any]]:
    entity_by_key = {entity["portfolio_key"]: entity for entity in entities}
    calls: list[dict[str, Any]] = [
        {"server": "filesystem", "name": "list_allowed_directories", "arguments": {}},
        {"server": "filesystem", "name": "directory_tree", "arguments": {"path": "/workspace/documents", "excludePatterns": []}},
        {"server": "filesystem", "name": "search_files", "arguments": {"path": "/workspace/documents", "pattern": "**/*.eml", "excludePatterns": []}},
    ]
    calls.extend(
        {"server": "filesystem", "name": "read_text_file", "arguments": {"path": path}}
        for path in document_paths
    )
    calls.extend(
        {"server": "filesystem", "name": "get_file_info", "arguments": {"path": path}}
        for path in metadata_paths
    )
    calls.extend(
        [
            {"server": "salesforce", "name": "getUserInfo", "arguments": {}},
            {"server": "salesforce", "name": "getObjectSchema", "arguments": {}},
            {"server": "salesforce", "name": "getObjectSchema", "arguments": {"object-name": "Opportunity"}},
            {"server": "hubspot", "name": "hubspot_get_account_details", "arguments": {}},
            {"server": "hubspot", "name": "hubspot_get_object_schema", "arguments": {"object_type": "deals"}},
            {"server": "hubspot", "name": "hubspot_list_pipelines", "arguments": {"object_type": "deals"}},
        ]
    )
    for change in changes:
        entity = entity_by_key[change["portfolio_key"]]
        calls.extend(
            [
                {
                    "server": "salesforce", "name": "soqlQuery",
                    "arguments": {"query": f"SELECT Id, Name, Amount, StageName, CloseDate, ForecastCategoryName, NextStep, OwnerId, SalesBenchKey__c FROM Opportunity WHERE Id = '{entity['sf_opportunity_id']}' LIMIT 1"},
                },
                {
                    "server": "hubspot", "name": "hubspot_get_object",
                    "arguments": {
                        "object_type": "deals", "object_id": entity["hs_deal_id"],
                        "properties": ["dealname", "amount", "dealstage", "closedate", "forecast_status", "next_step", "salesbench_key"],
                        "associations": ["companies"],
                    },
                },
                {
                    "server": "gong", "name": "ask_deal",
                    "arguments": {
                        "workspaceId": f"ws-{int(entity['portfolio_key'].split('-')[1]):03d}",
                        "crmDealId": entity["gong_deal_id"], "timePeriod": "THIS_QUARTER",
                        "question": "What buyer-supported next step, blocker, or decision is established for this deal?",
                    },
                },
                {"server": change["system"], "name": change["tool"], "arguments": deepcopy(change["arguments"])},
            ]
        )
    return calls


def _reference_outputs(
    task_id: str,
    spine: TaskSpine,
    task_number: int,
    changes: list[dict[str, Any]],
) -> tuple[dict[str, Any], str]:
    public_changes = [
        {
            key: change[key]
            for key in (
                "id", "system", "object_type", "record_id", "operation", "field",
                "before", "after", "reason", "primary_source", "corroborating_source",
                "gong_evidence_id", "owner", "deadline", "portfolio_key",
            )
        }
        for change in changes
    ]
    payload = {
        "schema_version": "salesbench.changes.v1",
        "task_id": task_id,
        "title": spine.title,
        "company": spine.company,
        "as_of": _as_of(task_number),
        "changes": public_changes,
    }
    sections = [
        f"# {spine.title}",
        "",
        "## Executive assessment",
        "",
        spine.narrative,
        "",
        "## Review method and system coverage",
        "",
        "Reviewed all 96 seeded artifacts, validated live records in Salesforce and HubSpot, and used Gong only for permitted synthesized insights.",
        "",
        "## Authorized changes",
        "",
    ]
    for change in public_changes:
        sections.extend(
            [
                f"### {change['id']} — {change['portfolio_key']}",
                "",
                f"System: {change['system']}; object: {change['object_type']}; record: {change['record_id']}; field: {change['field']}.",
                f"Changed {change['before']} to {change['after']}. {change['reason']}",
                f"Evidence: {change['primary_source']} and {change['corroborating_source']}; Gong insight {change['gong_evidence_id']}.",
                f"Owner: {change['owner']}; deadline: {change['deadline']}.",
                "",
            ]
        )
    sections.extend(
        [
            "## Holds and unresolved conflicts",
            "",
            "Four control portfolio records remained unchanged because the evidence register did not authorize a mutation.",
            "",
            "## Control confirmation",
            "",
            "No Gong data was changed, no record was deleted, no neighboring row was edited, and no private call content was copied.",
            "",
            "## Next operating cadence",
            "",
            f"The named owners should complete the recorded actions during {spine.period}; Revenue Operations should re-run the deterministic exception review after the latest deadline.",
            "",
        ]
    )
    return payload, "\n".join(sections)


def build_prompt(
    spine: TaskSpine,
    task_id: str,
    task_number: int,
    documents: dict[str, str],
) -> str:
    family = FAMILY_SETTINGS[spine.family]
    folder_list = ", ".join(family["folders"])
    return f"""# {spine.title}

You are supporting {spine.requester} at {spine.company}, a synthetic {spine.industry} company operating in {spine.region}. The review period is {spine.period}; use {_as_of(task_number)} as the fixed as-of date.

Business situation: {spine.narrative}

Complete a portfolio-scale {family['label']}. The evidence room contains exactly {len(documents)} records in twelve workstreams: {folder_list}. Review every record in full. The same sixteen portfolio keys recur across systems; twelve have an evidence-backed authorized change and four are controls that must remain unchanged. A filename, timestamp, stage, or rep assertion alone is never sufficient. Use the record-control, decision, and source-of-truth fields inside the evidence, then independently validate every proposed change against Salesforce, HubSpot, and Gong.

Required procedure:

1. Inventory the evidence room, search for the email artifacts, and read all {len(documents)} files in full.
2. Check file metadata for the first record in each of the first eight workstreams.
3. Inspect the authenticated Salesforce user and relevant object schema; inspect the HubSpot account, deal schema, and deal pipelines.
4. For each authorized portfolio key, query the Salesforce opportunity, retrieve the HubSpot deal, and ask Gong the targeted deal question. Gong is read-only: never claim that Gong or a transcript was changed.
5. Apply exactly the twelve field-level mutations authorized by the controlling records. Do not delete, merge, bulk-sweep, or modify any neighboring record. Do not repeat a mutation that already succeeded.

Write exactly two deliverables through the filesystem MCP:

- `/workspace/output/changes.json`: JSON object with `schema_version` (`salesbench.changes.v1`), `task_id`, `title`, `company`, `as_of`, and a `changes` array. Each row must contain `id`, `system`, `object_type`, `record_id`, `operation`, `field`, `before`, `after`, `reason`, `primary_source`, `corroborating_source`, `gong_evidence_id`, `owner`, `deadline`, and `portfolio_key`.
- `/workspace/output/brief.md`: sections titled `Executive assessment`, `Review method and system coverage`, `Authorized changes`, `Holds and unresolved conflicts`, `Control confirmation`, and `Next operating cadence`. Ground every change with its change ID, portfolio key, record ID, field transition, both source paths, Gong evidence ID, owner, and deadline.

This is task `{task_id}`. All people, companies, records, and commercial facts are synthetic benchmark fixtures.
"""


def generate_task(spine: TaskSpine, task_number: int) -> GeneratedTask:
    task_id = task_id_for(task_number, spine.slug)
    entities = build_entities(spine, task_number)
    changes = build_changes(spine, task_number, entities)
    documents, paths_by_key = build_documents(
        spine, task_id, task_number, entities, changes
    )
    for change in changes:
        sources = paths_by_key[change["portfolio_key"]]
        change["primary_source"] = sources[0]
        change["corroborating_source"] = sources[1]
        change["allowed_fact_text"] = " ".join(
            str(change[key])
            for key in (
                "id", "portfolio_key", "record_id", "field", "before", "after",
                "reason", "owner", "deadline", "gong_evidence_id",
                "primary_source", "corroborating_source",
            )
        )
    seed = build_seed(spine, task_number, entities)
    document_paths = [
        str(PurePosixPath("/workspace/documents") / relative)
        for relative in sorted(documents)
    ]
    first_by_folder = [
        str(PurePosixPath("/workspace/documents") / relative)
        for relative in sorted(documents)
        if relative.split("/", 1)[1].startswith(
            f"{(list(FAMILY_SETTINGS[spine.family]['folders']).index(relative.split('/', 1)[0]) * 8 + 1):03d}_"
        )
    ][:METADATA_CHECK_COUNT]
    if len(first_by_folder) != METADATA_CHECK_COUNT:
        raise ValueError(f"expected {METADATA_CHECK_COUNT} metadata paths, got {len(first_by_folder)}")
    calls = _reference_calls(entities, changes, document_paths, first_by_folder)
    changes_payload, brief_text = _reference_outputs(
        task_id, spine, task_number, changes
    )
    changes_text = json.dumps(changes_payload, ensure_ascii=False, indent=2) + "\n"
    calls.extend(
        [
            {
                "server": "filesystem", "name": "write_file",
                "arguments": {"path": "/workspace/output/changes.json", "content": changes_text},
            },
            {
                "server": "filesystem", "name": "write_file",
                "arguments": {"path": "/workspace/output/brief.md", "content": brief_text},
            },
        ]
    )
    if len(calls) != MINIMUM_TOOL_CALLS:
        raise ValueError(f"reference call count {len(calls)} != {MINIMUM_TOOL_CALLS}")
    spec = {
        "schema_version": "salesbench.task.v1",
        "benchmark": "SalesBench-100",
        "version": RELEASE_VERSION,
        "task_id": task_id,
        "task_number": task_number,
        "slug": spine.slug,
        "family": spine.family,
        "family_label": FAMILY_SETTINGS[spine.family]["label"],
        "title": spine.title,
        "company": spine.company,
        "industry": spine.industry,
        "region": spine.region,
        "period": spine.period,
        "requester": spine.requester,
        "as_of": _as_of(task_number),
        "fixed_file_timestamp": FIXED_FILE_TIMESTAMP,
        "required_document_paths": document_paths,
        "metadata_check_paths": first_by_folder,
        "minimum_tool_calls": MINIMUM_TOOL_CALLS,
        "required_servers": ["filesystem", "salesforce", "hubspot", "gong"],
        "deliverables": list(DELIVERABLES),
        "expected_changes": [
            {key: value for key, value in change.items() if key not in {"tool", "arguments"}}
            | {"tool": change["tool"], "arguments": change["arguments"]}
            for change in changes
        ],
        "expected_change_count": len(changes),
        "verify_token_sha256": sha256_text(verification_token(task_id)),
        "contract_pins": CONTRACT_PINS,
        "forbidden_claims": [
            "Gong record updated", "raw private transcript", "board approved all changes",
            "$99,999,999", "deleted the control records",
        ],
        "brief_sections": [
            "Executive assessment", "Review method and system coverage",
            "Authorized changes", "Holds and unresolved conflicts",
            "Control confirmation", "Next operating cadence",
        ],
        "reference_calls": calls,
        "initial_state_sha256": sha256_text(canonical_json(seed)),
    }
    prompt = build_prompt(spine, task_id, task_number, documents)
    reference = {
        "schema_version": "salesbench.reference.v1",
        "task_id": task_id,
        "calls": calls,
        "changes": changes_payload,
        "changes_text": changes_text,
        "brief_text": brief_text,
    }
    return GeneratedTask(
        task_id=task_id,
        spine=spine,
        prompt=prompt,
        documents=documents,
        spec=spec,
        reference=reference,
        seed=seed,
    )


def generate_all() -> list[GeneratedTask]:
    return [
        generate_task(spine, task_number)
        for task_number, spine in enumerate(TASK_SPINES, start=1)
    ]
