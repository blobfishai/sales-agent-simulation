"""Deterministic SalesBench-100 task and evidence generation."""

from __future__ import annotations

import csv
import hashlib
import html
import io
import json
import random
import re
import zipfile
from copy import deepcopy
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import PurePosixPath
from typing import Any

from .action_specs import ACTION_SPECS, ActionSpec, validate_action_specs
from .catalog import FAMILY_SETTINGS, TASK_SPINES, TaskSpine
from .contracts import CONTRACT_PINS
from .decision_specs import DECISION_RULES, validate_decision_rules


RELEASE_VERSION = "3.2.0"
FIXED_FILE_TIMESTAMP = "2026-08-26T12:00:00.000Z"
FIXED_XLSX_ZIP_TIMESTAMP = (2026, 8, 26, 12, 0, 0)
DOCUMENT_COUNT = 28
REQUIRED_TEXT_DOCUMENT_COUNT = 24
METADATA_CHECK_COUNT = 8
PORTFOLIO_ENTITY_COUNT = 16
MIN_TARGET_CHANGE_COUNT = 5
MAX_TARGET_CHANGE_COUNT = 12
DISTRACTOR_ENTITY_COUNT = 48
MIN_REFERENCE_TOOL_CALLS = 68
MAX_REFERENCE_TOOL_CALLS = 114
DELIVERABLES = ("changes.json", "brief.md")

validate_action_specs({spine.slug for spine in TASK_SPINES})
validate_decision_rules({spine.slug for spine in TASK_SPINES})

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

EXTENSIONS = (
    "md",
    "csv",
    "json",
    "eml",
    "csv",
    "html",
    "xml",
    "txt",
    "csv",
    "md",
    "json",
    "md",
)

# Every portfolio key appears once in each role. No single released record
# contains the complete answer: identity, operating fact, authority, governed
# transition, live-system corroboration, and exception evidence have to agree.
EVIDENCE_ROLES = (
    "identity_crosswalk",
    "operating_observation",
    "authority_record",
    "governed_transition",
    "live_system_corroboration",
    "exception_record",
)

# Folder meaning differs by workflow.  Each role still appears exactly twice so
# every portfolio key receives one independently authored row for each causal
# role, but a finance input no longer lands in a Gong folder merely because of
# its ordinal position.
EVIDENCE_ROLE_FOLDERS: dict[str, dict[str, str]] = {
    "forecast-reconciliation": {
        "01_salesforce_pipeline": "identity_crosswalk",
        "02_hubspot_deals": "identity_crosswalk",
        "03_gong_briefs": "operating_observation",
        "04_call_evidence": "operating_observation",
        "05_forecast_snapshots": "authority_record",
        "06_rep_commits": "authority_record",
        "07_stage_policy": "governed_transition",
        "08_close_plans": "live_system_corroboration",
        "09_finance_actuals": "live_system_corroboration",
        "10_territories": "governed_transition",
        "11_exceptions": "exception_record",
        "12_deliverables": "exception_record",
    },
    "pipeline-recovery": {
        "01_open_opportunities": "identity_crosswalk",
        "02_stage_history": "identity_crosswalk",
        "03_hubspot_activity": "operating_observation",
        "04_gong_deal_questions": "operating_observation",
        "05_next_steps": "authority_record",
        "06_calendar": "governed_transition",
        "07_owner_roster": "authority_record",
        "08_slippage": "live_system_corroboration",
        "09_support_risks": "live_system_corroboration",
        "10_playbooks": "governed_transition",
        "11_exclusions": "exception_record",
        "12_deliverables": "exception_record",
    },
    "gong-action-reconciliation": {
        "01_gong_calls": "operating_observation",
        "02_gong_briefs": "operating_observation",
        "03_salesforce_activities": "identity_crosswalk",
        "04_hubspot_engagements": "identity_crosswalk",
        "05_commitments": "authority_record",
        "06_stakeholders": "authority_record",
        "07_objections": "live_system_corroboration",
        "08_competitors": "live_system_corroboration",
        "09_followups": "governed_transition",
        "10_evidence_policy": "governed_transition",
        "11_private_calls": "exception_record",
        "12_deliverables": "exception_record",
    },
    "identity-migration": {
        "01_salesforce_accounts": "identity_crosswalk",
        "02_hubspot_companies": "identity_crosswalk",
        "03_contacts": "operating_observation",
        "04_domains": "live_system_corroboration",
        "05_external_ids": "authority_record",
        "06_associations": "authority_record",
        "07_merge_history": "live_system_corroboration",
        "08_sync_failures": "operating_observation",
        "09_source_rules": "governed_transition",
        "10_consent": "governed_transition",
        "11_do_not_merge": "exception_record",
        "12_deliverables": "exception_record",
    },
    "lead-routing": {
        "01_inbound_leads": "identity_crosswalk",
        "02_hubspot_contacts": "identity_crosswalk",
        "03_salesforce_leads": "operating_observation",
        "04_gong_history": "operating_observation",
        "05_account_matches": "live_system_corroboration",
        "06_territories": "authority_record",
        "07_scoring_policy": "governed_transition",
        "08_consent": "governed_transition",
        "09_owner_capacity": "authority_record",
        "10_disqualifiers": "live_system_corroboration",
        "11_routing_audit": "exception_record",
        "12_deliverables": "exception_record",
    },
    "renewal-expansion": {
        "01_contracts": "identity_crosswalk",
        "02_subscriptions": "identity_crosswalk",
        "03_salesforce_renewals": "live_system_corroboration",
        "04_hubspot_health": "live_system_corroboration",
        "05_gong_account_voice": "operating_observation",
        "06_support": "governed_transition",
        "07_usage": "operating_observation",
        "08_notice_windows": "authority_record",
        "09_expansion_signals": "authority_record",
        "10_handoff_policy": "governed_transition",
        "11_risks": "exception_record",
        "12_deliverables": "exception_record",
    },
    "quote-governance": {
        "01_opportunities": "identity_crosswalk",
        "02_quotes": "identity_crosswalk",
        "03_line_items": "operating_observation",
        "04_discount_matrix": "governed_transition",
        "05_approvals": "authority_record",
        "06_gong_commercials": "operating_observation",
        "07_hubspot_deals": "live_system_corroboration",
        "08_legal_status": "live_system_corroboration",
        "09_finance_checks": "authority_record",
        "10_close_plan": "governed_transition",
        "11_exceptions": "exception_record",
        "12_deliverables": "exception_record",
    },
    "account-planning": {
        "01_accounts": "identity_crosswalk",
        "02_opportunities": "live_system_corroboration",
        "03_contacts": "identity_crosswalk",
        "04_gong_briefs": "operating_observation",
        "05_org_charts": "authority_record",
        "06_engagement": "operating_observation",
        "07_products": "governed_transition",
        "08_competition": "exception_record",
        "09_support": "live_system_corroboration",
        "10_white_space": "authority_record",
        "11_account_plan_policy": "governed_transition",
        "12_deliverables": "exception_record",
    },
    "sequence-compliance": {
        "01_sequences": "operating_observation",
        "02_enrollments": "live_system_corroboration",
        "03_contacts": "identity_crosswalk",
        "04_consent": "authority_record",
        "05_suppressions": "authority_record",
        "06_email_events": "operating_observation",
        "07_domains": "governed_transition",
        "08_salesforce_campaigns": "identity_crosswalk",
        "09_hubspot_workflows": "live_system_corroboration",
        "10_regional_policy": "governed_transition",
        "11_exceptions": "exception_record",
        "12_deliverables": "exception_record",
    },
    "cutover-audit": {
        "01_cutover_plan": "authority_record",
        "02_salesforce_extract": "identity_crosswalk",
        "03_hubspot_extract": "identity_crosswalk",
        "04_field_mapping": "authority_record",
        "05_owner_mapping": "governed_transition",
        "06_stage_mapping": "live_system_corroboration",
        "07_activity_counts": "operating_observation",
        "08_gong_links": "operating_observation",
        "09_error_queue": "live_system_corroboration",
        "10_acceptance_rules": "governed_transition",
        "11_rollbacks": "exception_record",
        "12_deliverables": "exception_record",
    },
}

for _family, _settings in FAMILY_SETTINGS.items():
    _folders = list(_settings["folders"])
    _role_map = EVIDENCE_ROLE_FOLDERS.get(_family, {})
    _role_counts = {
        role: list(_role_map.values()).count(role) for role in EVIDENCE_ROLES
    }
    if set(_role_map) != set(_folders) or any(
        count != 2 for count in _role_counts.values()
    ):
        raise ValueError(
            f"invalid evidence-role folder map for {_family}: {_role_counts}"
        )


@dataclass(frozen=True)
class GeneratedTask:
    task_id: str
    spine: TaskSpine
    prompt: str
    documents: dict[str, str | bytes]
    spec: dict[str, Any]
    reference: dict[str, Any]
    seed: dict[str, Any]


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _pdf_bytes(title: str, lines: list[str]) -> bytes:
    safe = [
        re.sub(r"[^\x20-\x7e]", " ", value)
        .replace("\\", "\\\\")
        .replace("(", "\\(")
        .replace(")", "\\)")
        for value in [title, *lines]
    ]
    commands = ["BT", "/F1 12 Tf", "54 744 Td"]
    for index, line in enumerate(safe[:28]):
        if index:
            commands.append("0 -23 Td")
        commands.append(f"({line[:105]}) Tj")
    commands.append("ET")
    stream = "\n".join(commands).encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, 1):
        offsets.append(len(output))
        output.extend(f"{index} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f\n".encode())
    output.extend(
        b"".join(f"{offset:010d} 00000 n\n".encode() for offset in offsets[1:])
    )
    output.extend(
        f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    return bytes(output)


def _xlsx_bytes(sheets: dict[str, list[dict[str, Any]]]) -> bytes:
    def escaped(value: Any) -> str:
        return html.escape(str(value), quote=True)

    def write_member(archive: zipfile.ZipFile, name: str, content: str) -> None:
        member = zipfile.ZipInfo(name, date_time=FIXED_XLSX_ZIP_TIMESTAMP)
        member.compress_type = zipfile.ZIP_DEFLATED
        member.create_system = 3
        member.external_attr = 0o600 << 16
        archive.writestr(member, content)

    output = io.BytesIO()
    names = list(sheets)[:4]
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        write_member(
            archive,
            "[Content_Types].xml",
            '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            + "".join(
                f'<Override PartName="/xl/worksheets/sheet{index}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                for index in range(1, len(names) + 1)
            )
            + "</Types>",
        )
        write_member(
            archive,
            "_rels/.rels",
            '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>',
        )
        write_member(
            archive,
            "xl/workbook.xml",
            '<?xml version="1.0"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
            + "".join(
                f'<sheet name="{escaped(name[:31])}" sheetId="{index}" r:id="rId{index}"/>'
                for index, name in enumerate(names, 1)
            )
            + "</sheets></workbook>",
        )
        write_member(
            archive,
            "xl/_rels/workbook.xml.rels",
            '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            + "".join(
                f'<Relationship Id="rId{index}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{index}.xml"/>'
                for index in range(1, len(names) + 1)
            )
            + "</Relationships>",
        )
        for sheet_index, name in enumerate(names, 1):
            rows = sheets[name]
            fields = sorted({key for row in rows for key in row}) or ["record"]
            values = [fields] + [[row.get(field, "") for field in fields] for row in rows]
            body = []
            for row_index, row in enumerate(values, 1):
                cells = "".join(
                    f'<c r="{chr(64 + column)}{row_index}" t="inlineStr"><is><t>{escaped(value)}</t></is></c>'
                    for column, value in enumerate(row, 1)
                )
                body.append(f'<row r="{row_index}">{cells}</row>')
            write_member(
                archive,
                f"xl/worksheets/sheet{sheet_index}.xml",
                '<?xml version="1.0"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
                + "".join(body)
                + "</sheetData></worksheet>",
            )
    return output.getvalue()


def _supplemental_documents(
    spine: TaskSpine,
    task_id: str,
    task_number: int,
) -> dict[str, str | bytes]:
    revisions = [
        {
            "case_id": task_id,
            "source": source,
            "revision": f"{task_number:03d}-{index:02d}",
            "effective_period": spine.period if index <= 8 else f"retired-before-{spine.period}",
            "status": "current" if index <= 8 else "retired",
            "control_note": note,
        }
        for index, (source, note) in enumerate(
            [
                ("Salesforce", "Identity must be resolved by immutable CRM ID, not account name."),
                ("HubSpot", "Lifecycle state is corroboration and cannot authorize a Salesforce write."),
                ("Gong", "Buyer statements are read-only evidence and private call content stays excluded."),
                ("Forecast", "The current signed forecast revision controls period inclusion."),
                ("Territory", "Current owner and region must agree before routing changes."),
                ("Approval", "Only approvals effective for the requested period authorize action."),
                ("Finance", "Amount inputs require current-period reconciliation and explicit rounding."),
                ("Operations", "Every changed record needs a post-write readback and auditable handoff."),
                ("Legacy CRM", "This export is retained for lineage only and is not controlling authority."),
                ("Former owner", "A prior owner suggestion is non-authoritative until current records agree."),
                ("Draft policy", "The superseded review draft cannot replace the effective control."),
                ("Archive", "Historical evidence may explain a discrepancy but cannot authorize a current write."),
            ],
            1,
        )
    ]
    current = [row for row in revisions if row["status"] == "current"]
    retired = [row for row in revisions if row["status"] == "retired"]

    def json_document(kind: str, rows: list[dict[str, Any]]) -> str:
        return json.dumps(
            {
                "case_id": task_id,
                "company": spine.company,
                "workflow": spine.family,
                "record_type": kind,
                "records": rows,
                "warning": "Correlate effective revisions and immutable provider IDs; this file does not pre-authorize a mutation.",
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ) + "\n"

    def csv_document(kind: str, rows: list[dict[str, Any]]) -> str:
        stream = io.StringIO(newline="")
        fields = ["case_id", "record_type", "source", "revision", "effective_period", "status", "control_note"]
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({"case_id": task_id, "record_type": kind, **row})
        return stream.getvalue()

    def email_document(subject: str, rows: list[dict[str, Any]], authority: str) -> str:
        bullets = "\n".join(
            f"- {row['source']} revision {row['revision']} ({row['status']}): {row['control_note']}"
            for row in rows
        )
        return (
            f"From: revenue-controls@{task_number:03d}.example\n"
            f"To: {spine.requester.replace(' ', '.').casefold()}@{task_number:03d}.example\n"
            "Date: Wed, 26 Aug 2026 12:00:00 -0700\n"
            f"Subject: {subject} — {task_id}\n"
            "MIME-Version: 1.0\nContent-Type: text/plain; charset=UTF-8\n\n"
            f"Case: {task_id}\nCompany: {spine.company}\nAuthority: {authority}\n\n"
            f"{bullets}\n\nDo not infer a supported record change from this thread alone.\n"
        )

    current_markdown = "\n".join(
        [
            f"# Current authority register — {task_id}",
            "",
            f"Case: {task_id}",
            f"Company: {spine.company}",
            f"Review period: {spine.period}",
            "",
            "These controls are effective for the requested review. Resolve immutable IDs across systems, compare current revisions, preserve ambiguous records, and read persisted state after every authorized write.",
            "",
            *[f"## {row['source']} {row['revision']}\n\n{row['control_note']}" for row in current],
        ]
    ) + "\n"
    retired_markdown = "\n".join(
        [
            f"# Retired authority register — {task_id}",
            "",
            f"Case: {task_id}",
            f"Company: {spine.company}",
            f"Requested review period: {spine.period}",
            "Status: superseded; retained only to explain historical conflicts.",
            "",
            "Use this register only to understand why older exports, messages, or display names may disagree with the current systems. Every historical assertion must be correlated to an immutable provider ID and then checked against the effective-period authority before it can influence the review.",
            "",
            *[f"## {row['source']} {row['revision']}\n\n{row['control_note']}" for row in retired],
            "",
            "A retired control may be cited as conflict context but cannot authorize a current-period transition. Never use this appendix by itself to select an option, change CRM state, infer approval, or overwrite a current owner. If current evidence remains ambiguous, preserve the live record and identify the conflict in the handoff.",
        ]
    ) + "\n"
    audit_log = "\n".join(
        f"2026-08-26T{index:02d}:00:00Z case={task_id} source={row['source']} revision={row['revision']} status={row['status']} event=metadata-indexed note={row['control_note']}"
        for index, row in enumerate(revisions)
    ) + "\n"
    evidence_yaml = "\n".join(
        [f"case_id: {task_id}", f"company: {json.dumps(spine.company)}", "sources:"]
        + [
            f"  - name: {row['source']}\n    revision: {row['revision']}\n    status: {row['status']}\n    effective_period: {row['effective_period']}\n    note: {json.dumps(row['control_note'])}"
            for row in revisions
        ]
    ) + "\n"
    current_pdf_lines = [
        f"Case {task_id} | {spine.company} | {spine.period}",
        "Effective control: correlate immutable CRM IDs and effective revisions before acting.",
        "Live provider reads and task evidence must precede every authorized state change.",
        "Ambiguous or conflicting records remain unchanged and are named in the handoff.",
        "Each write is task-scoped, performed once, and followed by an exact persisted readback.",
        "Gong remains read-only; private call content is never copied to another system.",
        "The result brief cites controlling and corroborating sources without exposing private content.",
        *[f"CURRENT {row['source']} {row['revision']}: {row['control_note']}" for row in current],
    ]
    retired_pdf_lines = [
        f"Case {task_id} | superseded control appendix",
        "This revision expired before the requested review period and cannot authorize work.",
        "Historical records may explain a mismatch but must be checked against current authority.",
        "Names, stages, filenames, or seller assertions alone are insufficient identity evidence.",
        *[f"RETIRED {row['source']} {row['revision']}: {row['control_note']}" for row in retired],
        "Escalate a control conflict rather than combining current and retired rules.",
    ]
    workbook_rows = [
        {
            "source": row["source"],
            "revision": row["revision"],
            "period": row["effective_period"],
            "status": row["status"],
            "owner": spine.requester,
            "case_id": task_id,
        }
        for row in revisions
    ]
    return {
        "13_controls/current-revenue-control.pdf": _pdf_bytes(
            "Current revenue operations control", current_pdf_lines
        ),
        "13_controls/retired-revenue-control.pdf": _pdf_bytes(
            "Retired revenue operations control", retired_pdf_lines
        ),
        "14_workbooks/source-revision-matrix.xlsx": _xlsx_bytes(
            {"Source revisions": workbook_rows, "Control notes": revisions}
        ),
        "14_workbooks/review-capacity.xlsx": _xlsx_bytes(
            {"Review calendar": list(reversed(workbook_rows)), "Authority": current}
        ),
        "15_collaboration/operations-slack-thread.json": json_document("operations_slack_thread", revisions),
        "15_collaboration/revenue-slack-thread.json": json_document("revenue_slack_thread", list(reversed(revisions))),
        "16_approvals/drive-approval-record.json": json_document("drive_approval_record", current),
        "16_approvals/drive-source-index.json": json_document("drive_source_index", revisions),
        "17_communications/source-request.eml": email_document("Current review request", current, "current"),
        "17_communications/former-owner-suggestion.eml": email_document("Former owner suggestion", retired, "retired"),
        "18_lineage/record-lineage.csv": csv_document("record_lineage", revisions),
        "18_lineage/cross-system-register.csv": csv_document("cross_system_register", list(reversed(revisions))),
        "19_controls/current-authority.md": current_markdown,
        "19_controls/retired-authority.md": retired_markdown,
        "20_audit/system-audit.log": audit_log,
        "20_audit/evidence-status.yaml": evidence_yaml,
    }


def stable_seed(value: str) -> int:
    return int(sha256_text(value)[:16], 16)


def verification_token(task_id: str) -> str:
    return sha256_text(f"SalesBench-100 verifier capability::{task_id}")


def task_id_for(index: int, slug: str) -> str:
    return f"sb100-{index:03d}-{slug}"


def target_change_count(spine: TaskSpine, task_number: int) -> int:
    """Return a deterministic, task-specific workload size.

    Real operating requests do not conveniently contain twelve actionable rows
    every time.  The count is deliberately not exposed in the employee prompt;
    it must fall out of the evidence review.
    """

    width = MAX_TARGET_CHANGE_COUNT - MIN_TARGET_CHANGE_COUNT + 1
    return MIN_TARGET_CHANGE_COUNT + stable_seed(
        f"{task_number}:{spine.slug}:actionable-portfolio"
    ) % width


def _decision_method(spine: TaskSpine) -> str:
    return DECISION_RULES[spine.slug].method


def _render_decision_template(
    template: str,
    spine: TaskSpine,
    entity: dict[str, Any],
) -> str:
    context = {
        "account": entity["account_name"],
        "amount": entity["amount"],
        "batch_id": f"BATCH-{stable_seed(spine.slug) % 97:02d}-{entity['slot'] // 2 + 1:02d}",
        "close_date": entity["close_date"],
        "milestone_id": f"MS-{stable_seed(spine.title) % 10_000:04d}-{entity['slot'] + 1:02d}",
        "owner": entity["owner_name"],
        "owner_role": entity["owner_role"],
        "period": spine.period,
        "region": spine.region,
        "repeat_count": 3 + entity["slot"] % 5,
        "risk_code": entity["risk_code"],
        "signal": entity["signal"],
        "stage": entity["stage"],
    }
    return template.format(**context)


def _candidate_options(spine: TaskSpine) -> list[dict[str, str]]:
    """Return plausible task-specific approaches without disclosing the winner."""

    kind = ACTION_SPECS[spine.slug].value_kind
    variants = {
        "static": (
            (
                "controlled-evidence-join",
                "Apply the governed result only to rows passing every control",
                "Join identity, current observation, authority, provider state, and exceptions.",
            ),
            (
                "latest-provider-bulk-sync",
                "Treat the newest provider timestamp as authoritative",
                "Use recency as the only selection rule and synchronize the portfolio.",
            ),
            (
                "portfolio-wide-hold",
                "Leave the entire portfolio unchanged",
                "Wait for every source to agree verbatim before acting on any row.",
            ),
        ),
        "amount": (
            (
                "controlled-input-recalculation",
                "Recalculate the governed measure from its controlled inputs",
                "Apply the documented exclusions, effective rate, and rounding rule per row.",
            ),
            (
                "gross-header-value",
                "Copy the gross CRM header value",
                "Ignore exclusions and conversion controls and use the displayed gross amount.",
            ),
            (
                "amount-review-hold",
                "Hold all amount corrections",
                "Defer every row until the next finance review even when inputs reconcile.",
            ),
        ),
        "date": (
            (
                "supported-policy-date",
                "Use the later supported and policy-compliant date",
                "Compare the buyer-supported date with the first allowed operating date.",
            ),
            (
                "earliest-calendar-date",
                "Use the earliest date found in any source",
                "Prefer speed even when that date violates the current policy constraint.",
            ),
            (
                "retain-stale-date",
                "Leave every current CRM date in place",
                "Avoid correction even where current evidence resolves the conflict.",
            ),
        ),
        "owner": (
            (
                "qualified-owner-with-capacity",
                "Assign the active qualified owner with available capacity",
                "Reconcile territory and role fit with the effective capacity register.",
            ),
            (
                "round-robin-owner",
                "Use an unqualified round-robin assignment",
                "Ignore territory, status, and capacity in favor of queue order.",
            ),
            (
                "retain-routing-queue",
                "Leave every supported row in the routing queue",
                "Avoid assignment even where one candidate satisfies every control.",
            ),
        ),
        "risk": (
            (
                "corroborated-permitted-risk",
                "Apply only a corroborated risk from permitted evidence",
                "Meet the independent-source threshold without copying private activity.",
            ),
            (
                "seller-note-risk",
                "Trust a single seller-authored risk note",
                "Classify from one assertion without independent corroboration.",
            ),
            (
                "clear-all-risks",
                "Remove risk labels from the entire portfolio",
                "Treat missing verbatim agreement as evidence that no risk exists.",
            ),
        ),
        "signal": (
            (
                "buyer-supported-action",
                "Record the permitted buyer-supported action",
                "Use the explicit synthesized buyer commitment and reject seller inference.",
            ),
            (
                "seller-inferred-action",
                "Record the seller's inferred next step",
                "Treat an internal interpretation as if the buyer had committed to it.",
            ),
            (
                "blanket-signal-hold",
                "Leave all signal fields unchanged",
                "Defer supported actions together with genuinely ambiguous records.",
            ),
        ),
        "role": (
            (
                "corroborated-stakeholder-role",
                "Assign the independently corroborated stakeholder role",
                "Require two permitted sources to agree on the person's buying role.",
            ),
            (
                "title-derived-role",
                "Infer the role from a job title alone",
                "Use one ambiguous attribute without source corroboration.",
            ),
            (
                "retain-unknown-role",
                "Keep every stakeholder role unknown",
                "Leave even independently supported role corrections unresolved.",
            ),
        ),
        "cross_id": (
            (
                "effective-exact-crosswalk",
                "Write the opposite provider ID from the effective exact crosswalk",
                "Require legal name, domain, external key, and mapping revision to agree.",
            ),
            (
                "name-only-crosswalk",
                "Match records by the closest display name",
                "Ignore domain, immutable identifiers, and effective revision.",
            ),
            (
                "leave-links-empty",
                "Leave every cross-system link empty",
                "Defer exact matches together with genuinely ambiguous identities.",
            ),
        ),
        "account": (
            (
                "three-key-legal-identity",
                "Select the legal account satisfying all three identity keys",
                "Reconcile legal name, domain, and external identifier.",
            ),
            (
                "closest-account-alias",
                "Select the closest account alias",
                "Ignore the immutable crosswalk when a display name looks similar.",
            ),
            (
                "leave-account-unresolved",
                "Leave every account association unresolved",
                "Avoid supported associations along with genuinely ambiguous ones.",
            ),
        ),
    }[kind]
    options = [
        {
            "id": f"{spine.slug}:{suffix}",
            "label": label,
            "approach": approach,
        }
        for suffix, label, approach in variants
    ]
    rule = DECISION_RULES[spine.slug]
    options[0]["label"] = f"Apply the controlled {spine.title.casefold()} rule"
    options[0]["approach"] = rule.method
    options[1]["label"] = (
        f"Use {rule.observation_key.replace('_', ' ')} without the controlling authority"
    )
    options[2]["label"] = f"Hold the entire {spine.title.casefold()} portfolio"
    return options


def _hold_reason(entity: dict[str, Any]) -> str:
    return (
        "approval_pending",
        "source_conflict",
        "identity_ambiguous",
        "outside_current_period",
    )[entity["slot"] % 4]


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
    target_slots = set(
        rng.sample(
            range(PORTFOLIO_ENTITY_COUNT),
            target_change_count(spine, task_number),
        )
    )
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
    for entity in entities:
        entity["decision_facts"] = _build_decision_facts(spine, entity)
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


def governed_policy(spine: TaskSpine) -> dict[str, Any]:
    """Return the task's policy table without selecting a row or record.

    A policy is allowed to explain what action follows when a condition is
    proven.  It must not say which portfolio rows satisfy those conditions.
    """

    spec = ACTION_SPECS[spine.slug]
    derivation = _decision_method(spine)
    salesforce_result = (
        spec.salesforce_after
        if spec.value_kind == "static"
        else derivation
    )
    hubspot_result = (
        spec.hubspot_after
        if spec.value_kind == "static"
        else derivation
    )
    return {
        "workflow": spine.family,
        "effective_period": spine.period,
        "eligibility_test": {
            "identity": "independently matched",
            "operating_observation": "corroborated and effective in the current period",
            "authority": "approved for the requested scope",
            "live_systems": "current records agree with the crosswalk and observation",
            "exception_register": "no unresolved blocking exception",
        },
        "actions_when_all_conditions_pass": [
            {
                "system": "salesforce",
                "object_type": spec.salesforce_object,
                "field": spec.salesforce_field,
                "from": spec.salesforce_before,
                "to_or_derivation": salesforce_result,
            },
            {
                "system": "hubspot",
                "object_type": spec.hubspot_object,
                "field": spec.hubspot_field,
                "from": spec.hubspot_before,
                "to_or_derivation": hubspot_result,
            },
        ],
        "selection_rule": (
            "Use the identity crosswalk and current provider state to choose the system row; "
            "the policy does not identify an actionable portfolio record by itself."
        ),
        "candidate_approaches": _candidate_options(spine),
    }

SALESFORCE_ID_KEYS = {
    "Account": "sf_account_id",
    "Opportunity": "sf_opportunity_id",
    "Contact": "sf_contact_id",
    "Lead": "sf_lead_id",
    "Quote": "sf_quote_id",
    "Task": "sf_task_id",
    "CampaignMember": "sf_campaign_member_id",
}

HUBSPOT_ID_KEYS = {
    "companies": "hs_company_id",
    "deals": "hs_deal_id",
    "contacts": "hs_contact_id",
    "tasks": "hs_task_id",
}


def _resolved_action_values(
    spec: ActionSpec,
    entity: dict[str, Any],
) -> tuple[Any, Any]:
    facts = entity["decision_facts"]
    return facts["salesforce_value"], facts["hubspot_value"]


def _provider_record_id(
    entity: dict[str, Any], system: str, object_type: str
) -> str:
    key = (
        SALESFORCE_ID_KEYS[object_type]
        if system == "salesforce"
        else HUBSPOT_ID_KEYS[object_type]
    )
    return str(entity[key])


def _build_decision_facts(
    spine: TaskSpine,
    entity: dict[str, Any],
) -> dict[str, Any]:
    """Build raw, split-source facts and the hidden deterministic derivation."""

    spec = ACTION_SPECS[spine.slug]
    rule = DECISION_RULES[spine.slug]
    kind = spec.value_kind
    observed: dict[str, Any]
    authority: dict[str, Any]
    method: str
    explanation: str

    if kind == "static":
        salesforce_value = spec.salesforce_after
        hubspot_value = spec.hubspot_after
        observed = {
            "observed_signal": entity["signal"],
            "observed_risk": entity["risk_code"],
            "current_period": spine.period,
        }
        authority = {
            "approved_salesforce_outcome": spec.salesforce_after,
            "approved_hubspot_outcome": spec.hubspot_after,
            "scope": "only rows passing every eligibility condition",
        }
        method = _decision_method(spine)
        explanation = (
            "Identity, effective observation, scoped authority, live provider state, "
            "and the exception register must all agree."
        )
    elif kind == "amount":
        gross = int(entity["amount"])
        exclusion_rate = 7 + ((entity["slot"] + stable_seed(spine.slug)) % 9)
        excluded = round(gross * exclusion_rate / 100)
        if spine.slug == "quarry-enterprise-split":
            rate_basis_points = 10_000
            excluded_label = "duplicated overlay forecast value"
            transaction_currency = "USD"
        else:
            transaction_currency = ("AUD", "JPY", "SGD", "EUR")[
                entity["slot"] % 4
            ]
            rate_basis_points = {
                "AUD": 6_512,
                "JPY": 67,
                "SGD": 7_415,
                "EUR": 10_840,
            }[transaction_currency]
            excluded_label = "services amount excluded from subscription ARR"
        method = _decision_method(spine)
        derived = round((gross - excluded) * rate_basis_points / 10_000)
        salesforce_value = derived
        hubspot_value = str(derived)
        observed = {
            "gross_measure": gross,
            "excluded_measure": excluded,
            "excluded_measure_label": excluded_label,
            "transaction_currency": transaction_currency,
        }
        authority = {
            "approved_rate": rate_basis_points / 10_000,
            "rate_effective_period": spine.period,
            "rate_table_revision": f"FX-{spine.period}-APPROVED",
            "rounding": "nearest whole reporting-currency unit",
        }
        explanation = (
            f"{gross} less {excluded}, multiplied by {rate_basis_points / 10_000:.4f}, "
            f"produces {derived}."
        )
    elif kind == "date":
        buyer_date = date.fromisoformat(entity["close_date"])
        constraint_date = buyer_date + timedelta(days=(entity["slot"] % 4) - 1)
        derived_date = max(buyer_date, constraint_date).isoformat()
        salesforce_value = derived_date
        hubspot_value = derived_date
        observed = {
            "buyer_supported_date": buyer_date.isoformat(),
            "source_event": entity["signal"],
        }
        authority = {
            "first_policy_compliant_date": constraint_date.isoformat(),
            "calendar_rule": "use the later of the buyer-supported and policy-compliant dates",
        }
        method = _decision_method(spine)
        explanation = (
            f"The later of {buyer_date.isoformat()} and {constraint_date.isoformat()} "
            f"is {derived_date}."
        )
    elif kind == "owner":
        salesforce_value = entity["owner_id"]
        hubspot_value = entity["owner_id"]
        observed = {
            "territory": spine.region,
            "language_or_segment_fit": entity["owner_role"],
            "candidate_owner_name": entity["owner_name"],
        }
        authority = {
            "candidate_owner_id": entity["owner_id"],
            "owner_active": True,
            "remaining_capacity": 3 + entity["slot"] % 7,
            "alternate_owner_status": "inactive_or_at_capacity",
        }
        method = _decision_method(spine)
        explanation = (
            f"{entity['owner_name']} ({entity['owner_id']}) matches {spine.region} and "
            "has remaining capacity; the alternate does not."
        )
    elif kind == "risk":
        salesforce_value = entity["risk_code"]
        hubspot_value = entity["risk_code"]
        observed = {
            "corroborated_signal": entity["signal"],
            "candidate_risk_code": entity["risk_code"],
            "independent_mentions": 2 + entity["slot"] % 3,
        }
        authority = {
            "minimum_independent_mentions": 2,
            "private_call_text_permitted": False,
        }
        method = _decision_method(spine)
        explanation = (
            f"{entity['risk_code']} has {2 + entity['slot'] % 3} independent permitted "
            "mentions, meeting the threshold of 2."
        )
    elif kind == "signal":
        salesforce_value = entity["signal"]
        hubspot_value = entity["signal"]
        observed = {
            "buyer_supported_action": entity["signal"],
            "seller_only_inference": SIGNALS[(entity["slot"] + 1) % len(SIGNALS)],
        }
        authority = {
            "copy_permitted_synthesized_action": True,
            "copy_raw_private_transcript": False,
        }
        method = _decision_method(spine)
        explanation = f"The permitted action is {entity['signal']!r}."
    elif kind == "role":
        role = ("Economic Buyer", "Champion", "Technical Evaluator", "Procurement")[
            entity["slot"] % 4
        ]
        salesforce_value = role
        hubspot_value = role
        observed = {
            "named_stakeholder": f"Jordan {entity['account_name'].split()[0]}",
            "corroborated_role": role,
            "independent_sources": 2,
        }
        authority = {
            "minimum_sources": 2,
            "manually_verified_opt_out": False,
        }
        method = _decision_method(spine)
        explanation = f"Two sources identify the stakeholder as {role}."
    elif kind == "cross_id":
        salesforce_value = str(entity[HUBSPOT_ID_KEYS[spec.hubspot_object]])
        hubspot_value = str(entity[SALESFORCE_ID_KEYS[spec.salesforce_object]])
        observed = {
            "legal_name": entity["account_name"],
            "domain": entity["domain"],
            "external_match_confidence": "exact",
        }
        authority = {
            "matched_salesforce_id": str(
                entity[SALESFORCE_ID_KEYS[spec.salesforce_object]]
            ),
            "matched_hubspot_id": str(entity[HUBSPOT_ID_KEYS[spec.hubspot_object]]),
            "mapping_revision": f"MAP-{spine.period}",
        }
        method = _decision_method(spine)
        explanation = "Legal name, domain, external key, and mapping revision agree."
    elif kind == "account":
        salesforce_value = entity["account_name"]
        hubspot_value = entity["account_name"]
        observed = {
            "legal_account_name": entity["account_name"],
            "domain": entity["domain"],
            "conflicting_alias": f"{entity['account_name'].split()[0]} Global",
        }
        authority = {
            "identity_rule": "legal name plus domain plus external ID",
            "alias_alone_sufficient": False,
        }
        method = _decision_method(spine)
        explanation = f"{entity['account_name']} is the only identity satisfying all three keys."
    else:
        raise ValueError(f"unsupported action value kind: {kind}")

    business_observation = _render_decision_template(
        rule.observation_template, spine, entity
    )
    business_authority = _render_decision_template(
        rule.authority_template, spine, entity
    )
    observed[rule.observation_key] = business_observation
    authority[rule.authority_key] = business_authority
    method = rule.method
    explanation = (
        f"Observed: {business_observation}. Control: {business_authority}. "
        f"Application: {explanation}"
    )

    return {
        "value_kind": kind,
        "method": method,
        "observed_inputs": observed,
        "authority_inputs": authority,
        "salesforce_value": salesforce_value,
        "hubspot_value": hubspot_value,
        "explanation": explanation,
    }


def _gong_evidence_call(spine: TaskSpine, entity: dict[str, Any]) -> dict[str, Any]:
    common = {
        "workspaceId": f"ws-{int(entity['portfolio_key'].split('-')[1]):03d}",
        "timePeriod": "THIS_QUARTER",
    }
    if spine.family in {
        "identity-migration",
        "lead-routing",
        "account-planning",
        "sequence-compliance",
    }:
        return {
            "server": "gong",
            "name": "ask_account",
            "arguments": {
                **common,
                "crmAccountId": entity["gong_account_id"],
                "question": "What permitted account-level identity, stakeholder, or outreach evidence is established?",
            },
        }
    if spine.family in {"pipeline-recovery", "gong-action-reconciliation"}:
        return {
            "server": "gong",
            "name": "generate_brief",
            "arguments": {
                **common,
                "briefName": "Deal Inspection",
                "crmEntityType": "DEAL",
                "crmEntityId": entity["gong_deal_id"],
            },
        }
    return {
        "server": "gong",
        "name": "ask_deal",
        "arguments": {
            **common,
            "crmDealId": entity["gong_deal_id"],
            "question": "What buyer-supported next step, blocker, or decision is established for this deal?",
        },
    }


def provider_evidence_order(spine: TaskSpine) -> tuple[str, str, str]:
    """Choose the investigation order from the business question's source logic."""

    text = f"{spine.title} {spine.narrative}".casefold()
    explicit_positions = {
        "salesforce": text.find("salesforce"),
        "hubspot": text.find("hubspot"),
        "gong": text.find("gong"),
    }
    named = [
        system
        for system, position in sorted(
            explicit_positions.items(),
            key=lambda item: item[1] if item[1] >= 0 else len(text) + 1,
        )
        if position >= 0
    ]
    if not named:
        if "event scans" in text:
            named.append("salesforce")
        elif "company associations" in text:
            named.append("hubspot")
        elif any(
            token in text
            for token in ("call", "conversation", "buyer commitment", "stakeholder")
        ):
            named.append("gong")
        elif any(
            token in text
            for token in ("consent", "sequence", "campaign", "email", "lifecycle")
        ):
            named.append("hubspot")
        else:
            named.append("salesforce")
    family_defaults = {
        "forecast-reconciliation": ("salesforce", "hubspot", "gong"),
        "pipeline-recovery": ("gong", "salesforce", "hubspot"),
        "gong-action-reconciliation": ("gong", "hubspot", "salesforce"),
        "identity-migration": ("hubspot", "salesforce", "gong"),
        "lead-routing": ("hubspot", "salesforce", "gong"),
        "renewal-expansion": ("salesforce", "gong", "hubspot"),
        "quote-governance": ("salesforce", "hubspot", "gong"),
        "account-planning": ("gong", "salesforce", "hubspot"),
        "sequence-compliance": ("hubspot", "salesforce", "gong"),
        "cutover-audit": ("salesforce", "hubspot", "gong"),
    }
    ordered = [*named]
    for system in family_defaults[spine.family]:
        if system not in ordered:
            ordered.append(system)
    return tuple(ordered)  # type: ignore[return-value]


def build_changes(
    spine: TaskSpine,
    task_number: int,
    entities: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    targets = [entity for entity in entities if entity["target"]]
    targets.sort(key=lambda entity: entity["portfolio_key"])
    action_spec = ACTION_SPECS[spine.slug]
    changes: list[dict[str, Any]] = []
    for sequence, entity in enumerate(targets, start=1):
        # The authoritative CRM follows the entity-level crosswalk rather than
        # an artificial quota. This lets each portfolio's evidence determine
        # both the Salesforce/HubSpot action mix and the amount of work.
        alternate = entity["slot"] % 2 == 1
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
        salesforce_after, hubspot_after = _resolved_action_values(
            action_spec,
            entity,
        )
        if change["system"] == "salesforce":
            object_type = action_spec.salesforce_object
            record_id = _provider_record_id(entity, "salesforce", object_type)
            field = action_spec.salesforce_field
            before = action_spec.salesforce_before
            after = salesforce_after
            arguments = {
                "sobject-name": object_type,
                "id": record_id,
                "body": {field: after},
            }
        else:
            object_type = action_spec.hubspot_object
            record_id = _provider_record_id(entity, "hubspot", object_type)
            field = action_spec.hubspot_field
            before = action_spec.hubspot_before
            after = hubspot_after
            arguments = {
                "object_type": object_type,
                "object_id": record_id,
                "properties": {field: after},
            }
        change.update(
            {
                "object_type": object_type,
                "record_id": record_id,
                "field": field,
                "before": before,
                "after": after,
                "arguments": arguments,
                "value_kind": entity["decision_facts"]["value_kind"],
                "decision_method": entity["decision_facts"]["method"],
                "decision_inputs": {
                    "observed": deepcopy(
                        entity["decision_facts"]["observed_inputs"]
                    ),
                    "authority": deepcopy(
                        entity["decision_facts"]["authority_inputs"]
                    ),
                },
                "decision_explanation": entity["decision_facts"]["explanation"],
                "selected_option_id": _candidate_options(spine)[0]["id"],
            }
        )
        change["reason"] = (
            f"{entity['portfolio_key']} satisfies the current {spine.period} evidence and authority "
            f"gates for {spine.title.casefold()}; {entity['signal']} is corroborated under "
            f"{entity['risk_code']}."
        )
        changes.append(change)
    expected_count = target_change_count(spine, task_number)
    if len(changes) != expected_count:
        raise ValueError(f"expected {expected_count} changes, got {len(changes)}")
    return changes


def _event_lines(
    spine: TaskSpine,
    entity: dict[str, Any],
    task_number: int,
    artifact_number: int,
) -> list[str]:
    base = date(2026, 5, 1) + timedelta(days=(task_number + artifact_number) % 50)
    observed_items = list(entity["decision_facts"]["observed_inputs"].items())
    details = [
        f"business request opened: {spine.title}",
        f"buyer-supported observation: {entity['signal']}",
        *[f"{key.replace('_', ' ')} recorded as {value}" for key, value in observed_items[:3]],
        f"independent review retained risk classification {entity['risk_code']}",
    ]
    return [
        (
            f"{(base + timedelta(days=offset * 4)).isoformat()} | "
            f"EVT-{task_number:03d}-{artifact_number:03d}-{offset + 1} | "
            f"{('buyer' if offset % 2 == 0 else 'operations')} | {detail}"
        )
        for offset, detail in enumerate(details)
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
    role = EVIDENCE_ROLE_FOLDERS[spine.family][folder]
    action_spec = ACTION_SPECS[spine.slug]
    salesforce_object = action_spec.salesforce_object
    hubspot_object = action_spec.hubspot_object
    salesforce_record_id = _provider_record_id(
        entity, "salesforce", salesforce_object
    )
    hubspot_record_id = _provider_record_id(entity, "hubspot", hubspot_object)
    gong_call = _gong_evidence_call(spine, entity)
    gong_lookup_key = str(
        gong_call["arguments"].get("crmDealId")
        or gong_call["arguments"].get("crmAccountId")
        or gong_call["arguments"].get("crmEntityId")
    )
    hold_reason = _hold_reason(entity)
    supported = change is not None
    control = {
        "task_id": task_id,
        "portfolio_key": entity["portfolio_key"],
        "account_name": entity["account_name"],
        "period": spine.period,
        "as_of": _as_of(task_number),
        "folder": folder,
        "evidence_role": role,
        "source_version": f"v{1 + artifact_number % 4}.{artifact_number % 9}",
        "classification": "synthetic-confidential",
    }
    evidence: dict[str, Any]
    if role == "identity_crosswalk":
        evidence = {
            "legal_name": entity["account_name"],
            "domain": entity["domain"],
            "salesforce_account_id": entity["sf_account_id"],
            "salesforce_opportunity_id": entity["sf_opportunity_id"],
            "hubspot_company_id": entity["hs_company_id"],
            "hubspot_deal_id": entity["hs_deal_id"],
            "governed_salesforce_object": salesforce_object,
            "governed_salesforce_record_id": salesforce_record_id,
            "governed_hubspot_object": hubspot_object,
            "governed_hubspot_record_id": hubspot_record_id,
            "identity_review": (
                "ambiguous_parent_or_alias"
                if not supported and hold_reason == "identity_ambiguous"
                else "independently_matched"
            ),
            "match_basis": ["legal name", "domain", "external ID crosswalk"],
        }
    elif role == "operating_observation":
        evidence = {
            "observed_signal": entity["signal"],
            "risk_code": entity["risk_code"],
            "observation_status": (
                "conflicts_with_current_period_register"
                if not supported and hold_reason == "source_conflict"
                else "corroborated"
            ),
            "effective_period": (
                "superseded-prior-period"
                if not supported and hold_reason == "outside_current_period"
                else spine.period
            ),
            "decision_inputs": entity["decision_facts"]["observed_inputs"],
            "events": _event_lines(spine, entity, task_number, artifact_number),
        }
    elif role == "authority_record":
        evidence = {
            "requester": spine.requester,
            "owner": entity["owner_name"],
            "owner_role": entity["owner_role"],
            "response_due": entity["deadline"],
            "approval_status": (
                "pending_secondary_approval"
                if not supported and hold_reason == "approval_pending"
                else "approved_within_policy"
            ),
            "authorized_period": spine.period,
            "decision_control_inputs": entity["decision_facts"]["authority_inputs"],
            "scope": "Only records whose identity, effective evidence, live state, and governed rule all agree.",
        }
    elif role == "governed_transition":
        evidence = {
            "policy_version": f"{spine.period}-controlled",
            "decision_table": governed_policy(spine),
            "prohibitions": [
                "no bulk sync from timestamp alone",
                "no mutation when one controlling source conflicts",
                "no copying private Gong transcript text",
            ],
        }
    elif role == "live_system_corroboration":
        evidence = {
            "systems_to_reconcile": ["Salesforce", "HubSpot", "Gong"],
            "salesforce_object": salesforce_object,
            "salesforce_lookup_key": salesforce_record_id,
            "hubspot_object": hubspot_object,
            "hubspot_lookup_key": hubspot_record_id,
            "gong_tool": gong_call["name"],
            "gong_lookup_key": gong_lookup_key,
            "gong_evidence_id": entity["evidence_id"],
            "required_checks": [
                "current provider value",
                "cross-system account association",
                "permitted buyer-supported signal",
            ],
            "warning": "This record is an index, not proof that the live values agree.",
        }
    else:
        evidence = {
            "review_status": "no_exception_recorded" if supported else "unresolved_exception",
            "exception_type": "none" if supported else hold_reason,
            "source_note": (
                "No unresolved control exception was recorded for this portfolio key."
                if supported
                else {
                    "approval_pending": "The secondary approver has not signed the current-period request.",
                    "source_conflict": "The current-period register and the latest seller note disagree.",
                    "identity_ambiguous": "The parent and carved-out entity share a domain but not a confirmed external ID.",
                    "outside_current_period": "The supporting observation belongs to a superseded period.",
                }[hold_reason]
            ),
            "disposition_owner": entity["owner_name"],
            "review_by": entity["deadline"],
        }
    payload = {
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
        "evidence": evidence,
        "controls": {
            "gong_is_read_only": True,
            "deletes_authorized": False,
            "neighboring_records_must_remain_unchanged": True,
            "private_call_content_may_be_copied": False,
            "duplicate_mutations_allowed": False,
            "single_document_is_sufficient": False,
        },
    }
    if folder == "12_deliverables":
        payload["workflow_contract"] = {
            "requester": spine.requester,
            "business_question": spine.narrative,
            "evidence_scope": (
                "Inventory the complete evidence room and reconcile every recurring portfolio key. "
                "A CRM timestamp, filename, stage, or seller assertion is not sufficient on its own."
            ),
            "decision_rule": (
                "Change a record only when the current-period controlling record, a corroborating "
                "source, and the live Salesforce, HubSpot, and permitted Gong evidence agree. "
                "Unresolved or control records remain unchanged."
            ),
            "candidate_approaches": _candidate_options(spine),
            "required_outputs": {
                "changes.json": {
                    "schema_version": "salesbench.changes.v1",
                    "top_level_fields": [
                        "task_id", "title", "company", "as_of", "decision_summary",
                        "changes", "holds",
                    ],
                    "decision_summary_fields": [
                        "selected_option_id", "value_kind", "method", "actionable_records",
                        "held_records", "alternatives_considered",
                    ],
                    "change_fields": [
                        "id", "system", "object_type", "record_id", "operation", "field",
                        "before", "after", "reason", "primary_source", "corroborating_source",
                        "gong_evidence_id", "owner", "deadline", "portfolio_key", "value_kind",
                        "decision_method", "decision_inputs", "decision_explanation",
                        "selected_option_id", "evidence_sources",
                    ],
                    "hold_fields": [
                        "id", "portfolio_key", "account_name", "blocking_condition",
                        "primary_source", "corroborating_source", "owner", "deadline",
                        "required_next_step",
                    ],
                },
                "brief.md": {
                    "sections": [
                        "Executive assessment", "Decision and alternatives",
                        "Review method and system coverage",
                        "Authorized changes", "Holds and unresolved conflicts",
                        "Control confirmation", "Next operating cadence",
                    ],
                    "grounding": (
                        "Explain each supported change and each hold with immutable record IDs, "
                        "the controlling and corroborating sources, owner, and deadline."
                    ),
                },
            },
        }
    return payload


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


def _render_collection(
    *,
    folder: str,
    extension: str,
    payloads: list[dict[str, Any]],
) -> str:
    """Render one production-style source containing a multi-record register."""

    first = payloads[0]
    collection = {
        "source_register": {
            "task_id": first["record_control"]["task_id"],
            "folder": folder,
            "evidence_role": first["record_control"]["evidence_role"],
            "effective_period": first["record_control"]["period"],
            "record_count": len(payloads),
            "control_note": (
                "Rows are independent source observations. Join by portfolio key and "
                "effective revision; this register does not select an action."
            ),
        },
        "records": payloads,
    }
    if extension == "json":
        return json.dumps(collection, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if extension == "csv":
        stream = io.StringIO()
        columns = (
            "task_id",
            "portfolio_key",
            "account_name",
            "period",
            "as_of",
            "evidence_role",
            "source_version",
            "amount_usd",
            "stage",
            "close_date",
            "owner",
            "evidence_json",
        )
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        for payload in payloads:
            control = payload["record_control"]
            context = payload["business_context"]
            writer.writerow(
                {
                    "task_id": control["task_id"],
                    "portfolio_key": control["portfolio_key"],
                    "account_name": control["account_name"],
                    "period": control["period"],
                    "as_of": control["as_of"],
                    "evidence_role": control["evidence_role"],
                    "source_version": control["source_version"],
                    "amount_usd": context["amount_usd"],
                    "stage": context["stage"],
                    "close_date": context["close_date"],
                    "owner": context["owner"],
                    "evidence_json": json.dumps(
                        payload["evidence"],
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                }
            )
        return stream.getvalue()
    if extension == "eml":
        control = first["record_control"]
        summaries = "\n".join(
            "- "
            + json.dumps(
                {
                    "portfolio_key": payload["record_control"]["portfolio_key"],
                    "account_name": payload["record_control"]["account_name"],
                    "evidence_role": payload["record_control"]["evidence_role"],
                    "evidence": payload["evidence"],
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            for payload in payloads
        )
        return (
            f"From: revenue-operations@{control['task_id']}.example\n"
            f"To: portfolio-review@{control['task_id']}.example\n"
            "Date: Wed, 26 Aug 2026 12:00:00 -0700\n"
            f"Subject: {folder.replace('_', ' ').title()} — controlled portfolio update\n"
            "MIME-Version: 1.0\nContent-Type: text/plain; charset=UTF-8\n\n"
            "Team,\n\n"
            "Below is the current controlled register. It is one input to the review, "
            "not a pre-approved mutation list. Reconcile each key against the other "
            "sources and live systems.\n\n"
            f"{summaries}\n\nRegards,\nRevenue Operations Controls\n"
        )
    if extension in {"xml", "html"}:
        return _render_payload(collection, extension)

    heading = "#" if extension == "md" else ""
    lines = [
        f"{heading} {folder.replace('_', ' ').title()}".strip(),
        "",
        collection["source_register"]["control_note"],
        "",
        "| Portfolio key | Account | Source revision | Evidence role |",
        "|---|---|---|---|",
    ]
    for payload in payloads:
        control = payload["record_control"]
        lines.append(
            f"| {control['portfolio_key']} | {control['account_name']} | "
            f"{control['source_version']} | {control['evidence_role']} |"
        )
    lines.extend(["", "## Controlled record details", ""])
    for payload in payloads:
        control = payload["record_control"]
        lines.extend(
            [
                f"### {control['portfolio_key']} — {control['account_name']}",
                "",
                json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
                "",
            ]
        )
    return "\n".join(lines) + "\n"


def build_documents(
    spine: TaskSpine,
    task_id: str,
    task_number: int,
    entities: list[dict[str, Any]],
    changes: list[dict[str, Any]],
) -> tuple[dict[str, str | bytes], dict[str, list[str]]]:
    changes_by_key = {change["portfolio_key"]: change for change in changes}
    folders = list(FAMILY_SETTINGS[spine.family]["folders"])
    documents: dict[str, str | bytes] = {}
    paths_by_key_and_role: dict[str, dict[str, str]] = {
        entity["portfolio_key"]: {} for entity in entities
    }
    role_occurrences = {role: 0 for role in EVIDENCE_ROLES}
    for folder_index, folder in enumerate(folders):
        role = EVIDENCE_ROLE_FOLDERS[spine.family][folder]
        occurrence = role_occurrences[role]
        role_occurrences[role] += 1
        role_index = EVIDENCE_ROLES.index(role)
        entity_offset = occurrence * (PORTFOLIO_ENTITY_COUNT // 2)
        selected_entities = entities[
            entity_offset : entity_offset + PORTFOLIO_ENTITY_COUNT // 2
        ]
        extension = EXTENSIONS[folder_index]
        payloads: list[dict[str, Any]] = []
        for entity in selected_entities:
            artifact_number = role_index * PORTFOLIO_ENTITY_COUNT + entity["slot"] + 1
            payloads.append(_artifact_payload(
                spine=spine,
                task_id=task_id,
                task_number=task_number,
                folder=folder,
                artifact_number=artifact_number,
                entity=entity,
                change=changes_by_key.get(entity["portfolio_key"]),
            ))
        filename = f"{folder_index + 1:02d}_{folder}_register.{extension}"
        relative = f"{folder}/{filename}"
        documents[relative] = _render_collection(
            folder=folder,
            extension=extension,
            payloads=payloads,
        )
        for entity in selected_entities:
            paths_by_key_and_role[entity["portfolio_key"]][role] = str(
                PurePosixPath("/workspace/documents") / relative
            )
    documents.update(_supplemental_documents(spine, task_id, task_number))
    if len(documents) != DOCUMENT_COUNT:
        raise ValueError(f"expected {DOCUMENT_COUNT} documents, got {len(documents)}")
    paths_by_key = {
        portfolio_key: [role_paths[role] for role in EVIDENCE_ROLES]
        for portfolio_key, role_paths in paths_by_key_and_role.items()
    }
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

    action_spec = ACTION_SPECS[spine.slug]
    for row in sf[action_spec.salesforce_object]:
        row[action_spec.salesforce_field] = deepcopy(action_spec.salesforce_before)
    for row in hs[action_spec.hubspot_object]:
        row["properties"][action_spec.hubspot_field] = deepcopy(
            action_spec.hubspot_before
        )

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


def _task_investigation_calls(
    spine: TaskSpine,
    task_number: int,
    entities: list[dict[str, Any]],
    document_paths: list[str],
    metadata_paths: list[str],
) -> list[dict[str, Any]]:
    """Build a task-specific, causally relevant read plan.

    Every probe is a provider-native read that answers an identity, ownership,
    association, recency, or scope question in the employee's workflow.  The
    stable authored spine selects a different subset and order, so two tasks do
    not collapse to the same generic CRM reconnaissance recipe.
    """

    action_spec = ACTION_SPECS[spine.slug]
    first, second, third = entities[:3]
    held_entities = [entity for entity in entities if not entity["target"]]
    hubspot_ids = [
        _provider_record_id(entity, "hubspot", action_spec.hubspot_object)
        for entity in entities[:3]
    ]
    related_salesforce_object = {
        "forecast-reconciliation": "Quote",
        "pipeline-recovery": "Task",
        "gong-action-reconciliation": "Task",
        "identity-migration": "Contact",
        "lead-routing": "Lead",
        "renewal-expansion": "Opportunity",
        "quote-governance": "Quote",
        "account-planning": "Contact",
        "sequence-compliance": "CampaignMember",
        "cutover-audit": "Account",
    }[spine.family]
    if related_salesforce_object == action_spec.salesforce_object:
        related_salesforce_object = next(
            candidate
            for candidate in ("Account", "Contact", "Lead", "Opportunity", "Quote", "Task")
            if candidate != action_spec.salesforce_object
        )
    related_hubspot_object = {
        "forecast-reconciliation": "deals",
        "pipeline-recovery": "tasks",
        "gong-action-reconciliation": "tasks",
        "identity-migration": "companies",
        "lead-routing": "contacts",
        "renewal-expansion": "deals",
        "quote-governance": "deals",
        "account-planning": "contacts",
        "sequence-compliance": "contacts",
        "cutover-audit": "companies",
    }[spine.family]
    if related_hubspot_object == action_spec.hubspot_object:
        related_hubspot_object = next(
            candidate
            for candidate in ("companies", "contacts", "deals", "tasks")
            if candidate != action_spec.hubspot_object
        )
    search_suffixes = sorted(
        {PurePosixPath(path).suffix for path in document_paths} - {".eml"}
    )
    selected_suffix = search_suffixes[stable_seed(f"{spine.slug}|source-format") % len(search_suffixes)]
    gong_probes = [
        _gong_evidence_call(spine, entity)
        for entity in held_entities[:3]
    ]
    pool: list[dict[str, Any]] = [
        {
            "server": "salesforce", "name": "find",
            "arguments": {"search": f"FIND {{{first['portfolio_key']}}}"},
            "purpose": "cross-object identity search",
        },
        {
            "server": "salesforce", "name": "listRecentSobjectRecords",
            "arguments": {"sobject-name": related_salesforce_object},
            "purpose": "recent related-record scope",
        },
        {
            "server": "salesforce", "name": "getObjectSchema",
            "arguments": {"object-name": related_salesforce_object},
            "purpose": "related-object field authority",
        },
        {
            "server": "salesforce", "name": "getRelatedRecords",
            "arguments": {
                "sobject-name": "Opportunity", "id": first["sf_opportunity_id"],
                "relationship-path": "Tasks",
            },
            "purpose": "existing follow-up containment",
        },
        {
            "server": "salesforce", "name": "getRelatedRecords",
            "arguments": {
                "sobject-name": "Opportunity", "id": second["sf_opportunity_id"],
                "relationship-path": "Quotes",
            },
            "purpose": "commercial-record corroboration",
        },
        {
            "server": "salesforce", "name": "getRelatedRecords",
            "arguments": {
                "sobject-name": "Account", "id": third["sf_account_id"],
                "relationship-path": "Contacts",
            },
            "purpose": "stakeholder identity corroboration",
        },
        {
            "server": "hubspot", "name": "hubspot_list_owners",
            "arguments": {"limit": 100, "archived": False},
            "purpose": "active-owner capacity check",
        },
        {
            "server": "hubspot", "name": "hubspot_get_object_schema",
            "arguments": {"object_type": related_hubspot_object},
            "purpose": "related-object property authority",
        },
        {
            "server": "hubspot", "name": "hubspot_search_objects",
            "arguments": {
                "object_type": action_spec.hubspot_object,
                "query": first["portfolio_key"],
                "properties": [action_spec.hubspot_field, "salesbench_key"],
                "limit": 20,
            },
            "purpose": "cross-system portfolio-key search",
        },
        {
            "server": "hubspot", "name": "hubspot_batch_read_objects",
            "arguments": {
                "object_type": action_spec.hubspot_object,
                "ids": hubspot_ids,
                "properties": [action_spec.hubspot_field, "salesbench_key"],
            },
            "purpose": "bounded provider population comparison",
        },
        {
            "server": "hubspot", "name": "hubspot_list_associations",
            "arguments": {
                "object_type": "deals", "object_id": first["hs_deal_id"],
                "to_object_type": "companies", "limit": 100,
            },
            "purpose": "deal-to-company identity join",
        },
        {
            "server": "hubspot", "name": "hubspot_list_objects",
            "arguments": {
                "object_type": related_hubspot_object, "limit": 3,
                "properties": ["salesbench_key"], "associations": [], "archived": False,
            },
            "purpose": "neighbor-record scope check",
        },
        {
            **gong_probes[0],
            "purpose": "conversation-backed account identity check",
        },
        {
            **gong_probes[1],
            "purpose": "independent buyer-evidence comparison",
        },
        {
            **gong_probes[2],
            "purpose": "neighbor-record private-data boundary check",
        },
        {
            "server": "filesystem", "name": "search_files",
            "arguments": {
                "path": "/workspace/documents", "pattern": f"**/*{selected_suffix}",
                "excludePatterns": [],
            },
            "purpose": "native source-format inventory",
        },
        {
            "server": "filesystem", "name": "get_file_info",
            "arguments": {
                "path": next(
                    path
                    for path in document_paths[task_number % len(document_paths) :]
                    + document_paths[: task_number % len(document_paths)]
                    if path not in metadata_paths
                )
            },
            "purpose": "task-specific source revision metadata",
        },
    ]
    rotation = stable_seed(f"{spine.slug}|investigation-rotation") % len(pool)
    strides = (1, 3, 5, 7, 11, 13)
    stride = strides[stable_seed(f"{spine.slug}|investigation-stride") % len(strides)]
    count = 6 + stable_seed(f"{spine.slug}|investigation-count") % 6
    return [deepcopy(pool[(rotation + index * stride) % len(pool)]) for index in range(count)]


def _evidence_folder_order(spine: TaskSpine) -> list[str]:
    """Order source roles from the task's authored causal rule, not file names."""

    rule = DECISION_RULES[spine.slug]
    signature = f"{rule.observation_key}|{rule.authority_key}|{rule.method}"
    middle_roles = [
        role
        for role in EVIDENCE_ROLES
        if role not in {"identity_crosswalk", "exception_record"}
    ]
    role_order = [
        "identity_crosswalk",
        *sorted(
            middle_roles,
            key=lambda role: stable_seed(f"{signature}|role|{role}"),
        ),
        "exception_record",
    ]
    folder_roles = EVIDENCE_ROLE_FOLDERS[spine.family]
    ordered: list[str] = []
    for role in role_order:
        ordered.extend(
            sorted(
                (folder for folder, folder_role in folder_roles.items() if folder_role == role),
                key=lambda folder: stable_seed(f"{signature}|folder|{folder}"),
            )
        )
    return ordered


def _reference_calls(
    spine: TaskSpine,
    task_number: int,
    entities: list[dict[str, Any]],
    changes: list[dict[str, Any]],
    document_paths: list[str],
    metadata_paths: list[str],
) -> list[dict[str, Any]]:
    entity_by_key = {entity["portfolio_key"]: entity for entity in entities}
    action_spec = ACTION_SPECS[spine.slug]
    salesforce_object = action_spec.salesforce_object
    hubspot_object = action_spec.hubspot_object
    salesforce_field = action_spec.salesforce_field
    hubspot_field = action_spec.hubspot_field
    orientation: list[dict[str, Any]] = [
        {"server": "filesystem", "name": "list_allowed_directories", "arguments": {}},
        {"server": "filesystem", "name": "directory_tree", "arguments": {"path": "/workspace/documents", "excludePatterns": []}},
        {"server": "filesystem", "name": "search_files", "arguments": {"path": "/workspace/documents", "pattern": "**/*.eml", "excludePatterns": []}},
    ]
    system_discovery: list[dict[str, Any]] = [
        {"server": "salesforce", "name": "getUserInfo", "arguments": {}},
        {"server": "salesforce", "name": "getObjectSchema", "arguments": {}},
        {"server": "salesforce", "name": "getObjectSchema", "arguments": {"object-name": salesforce_object}},
        {"server": "hubspot", "name": "hubspot_get_account_details", "arguments": {}},
        {"server": "hubspot", "name": "hubspot_get_object_schema", "arguments": {"object_type": hubspot_object}},
        (
            {"server": "hubspot", "name": "hubspot_list_pipelines", "arguments": {"object_type": "deals"}}
            if hubspot_object == "deals"
            else {
                "server": "hubspot",
                "name": "hubspot_list_objects",
                "arguments": {
                    "object_type": hubspot_object,
                    "limit": 1,
                    "properties": [hubspot_field, "salesbench_key"],
                    "associations": [],
                    "archived": False,
                },
            }
        ),
    ]

    # Follow a business-derived order: identity first, exceptions last, and the
    # intervening source roles ordered by the task's authored observation,
    # authority, and derivation rule.
    paths_by_folder: dict[str, list[str]] = {}
    for path in document_paths:
        folder = PurePosixPath(path).parts[-2]
        paths_by_folder.setdefault(folder, []).append(path)
    folders = _evidence_folder_order(spine)
    metadata_by_folder = {
        PurePosixPath(path).parts[-2]: path for path in metadata_paths
    }
    evidence_folders = set(paths_by_folder) | set(metadata_by_folder)
    folders.extend(sorted(evidence_folders - set(folders)))
    task_investigation = _task_investigation_calls(
        spine, task_number, entities, document_paths, metadata_paths
    )
    calls: list[dict[str, Any]] = [*orientation, *system_discovery, *task_investigation]
    for folder in folders:
        paths = sorted(paths_by_folder.get(folder, []))
        calls.extend(
            {"server": "filesystem", "name": "read_text_file", "arguments": {"path": path}}
            for path in paths
        )
        if folder in metadata_by_folder:
            calls.append(
                {
                    "server": "filesystem",
                    "name": "get_file_info",
                    "arguments": {"path": metadata_by_folder[folder]},
                }
            )

    ordered_changes = sorted(
        changes,
        key=lambda change: (
            entity_by_key[change["portfolio_key"]]["deadline"],
            -entity_by_key[change["portfolio_key"]]["amount"],
            change["portfolio_key"],
        ),
    )
    for change in ordered_changes:
        entity = entity_by_key[change["portfolio_key"]]
        salesforce_id = _provider_record_id(
            entity, "salesforce", salesforce_object
        )
        hubspot_id = _provider_record_id(entity, "hubspot", hubspot_object)
        evidence_calls = {
            "salesforce": {
                "server": "salesforce", "name": "soqlQuery",
                "arguments": {
                    "query": (
                        f"SELECT Id, {salesforce_field}, SalesBenchKey__c "
                        f"FROM {salesforce_object} WHERE Id = '{salesforce_id}' LIMIT 1"
                    )
                },
            },
            "hubspot": {
                "server": "hubspot", "name": "hubspot_get_object",
                "arguments": {
                    "object_type": hubspot_object,
                    "object_id": hubspot_id,
                    "properties": [hubspot_field, "salesbench_key"],
                    "associations": ["companies"] if hubspot_object == "deals" else [],
                },
            },
            "gong": _gong_evidence_call(spine, entity),
        }
        calls.extend(
            {
                **evidence_calls[system],
                "phase": "prewrite_provider_evidence",
                "change_id": change["id"],
            }
            for system in provider_evidence_order(spine)
        )
        calls.append(
            {
                "server": change["system"],
                "name": change["tool"],
                "arguments": deepcopy(change["arguments"]),
                "phase": "authorized_mutation",
                "change_id": change["id"],
            }
        )
        if change["system"] == "salesforce":
            readback = {
                "server": "salesforce",
                "name": "soqlQuery",
                "arguments": {
                    "query": (
                        f"SELECT Id, {change['field']} FROM {change['object_type']} "
                        f"WHERE Id = '{change['record_id']}' LIMIT 1"
                    )
                },
            }
        else:
            readback = {
                "server": "hubspot",
                "name": "hubspot_get_object",
                "arguments": {
                    "object_type": change["object_type"],
                    "object_id": change["record_id"],
                    "properties": [change["field"]],
                    "associations": [],
                },
            }
        change["postwrite_evidence"] = {
            **deepcopy(readback),
            "expected_field": change["field"],
            "expected_value": change["after"],
        }
        calls.append(
            {
                **readback,
                "phase": "postwrite_readback",
                "change_id": change["id"],
            }
        )
    return calls


def _build_holds(
    task_number: int,
    entities: list[dict[str, Any]],
    changes: list[dict[str, Any]],
    paths_by_key: dict[str, list[str]],
) -> list[dict[str, Any]]:
    changed_keys = {change["portfolio_key"] for change in changes}
    corroborating_role = {
        "approval_pending": 2,
        "source_conflict": 1,
        "identity_ambiguous": 0,
        "outside_current_period": 1,
    }
    next_steps = {
        "approval_pending": "Obtain the missing current-period secondary approval, then re-run the full control join.",
        "source_conflict": "Resolve the current-period source conflict with the named owner before changing either CRM.",
        "identity_ambiguous": "Confirm the immutable external-ID mapping for the legal entity and carved-out account.",
        "outside_current_period": "Collect a current-period operating observation and revalidate it against live provider state.",
    }
    holds: list[dict[str, Any]] = []
    for entity in entities:
        if entity["portfolio_key"] in changed_keys:
            continue
        reason = _hold_reason(entity)
        sources = paths_by_key[entity["portfolio_key"]]
        if len(sources) != len(EVIDENCE_ROLES):
            raise ValueError(
                f"expected {len(EVIDENCE_ROLES)} source roles for {entity['portfolio_key']}"
            )
        holds.append(
            {
                "id": f"HLD-{task_number:03d}-{entity['slot'] + 1:02d}",
                "portfolio_key": entity["portfolio_key"],
                "account_name": entity["account_name"],
                "blocking_condition": reason,
                "primary_source": sources[5],
                "corroborating_source": sources[corroborating_role[reason]],
                "owner": entity["owner_name"],
                "deadline": entity["deadline"],
                "required_next_step": next_steps[reason],
            }
        )
    return holds


def _reference_outputs(
    task_id: str,
    spine: TaskSpine,
    task_number: int,
    changes: list[dict[str, Any]],
    holds: list[dict[str, Any]],
) -> tuple[dict[str, Any], str]:
    options = _decision_options(spine, task_number, len(changes))
    selected = next(option for option in options if option["selected"])
    public_changes = [
        {
            key: change[key]
            for key in (
                "id", "system", "object_type", "record_id", "operation", "field",
                "before", "after", "reason", "primary_source", "corroborating_source",
                "gong_evidence_id", "owner", "deadline", "portfolio_key", "value_kind",
                "decision_method", "decision_inputs", "decision_explanation",
                "selected_option_id", "evidence_sources",
            )
        }
        for change in changes
    ]
    decision_summary = {
        "selected_option_id": selected["id"],
        "value_kind": ACTION_SPECS[spine.slug].value_kind,
        "method": _decision_method(spine),
        "actionable_records": len(public_changes),
        "held_records": len(holds),
        "alternatives_considered": [option["id"] for option in options],
    }
    payload = {
        "schema_version": "salesbench.changes.v1",
        "task_id": task_id,
        "title": spine.title,
        "company": spine.company,
        "as_of": _as_of(task_number),
        "decision_summary": decision_summary,
        "changes": public_changes,
        "holds": holds,
    }
    sections = [
        f"# {spine.title}",
        "",
        "## Executive assessment",
        "",
        (
            f"{spine.narrative} The evidence supports {len(public_changes)} bounded changes; "
            f"{len(holds)} portfolio records remain on hold."
        ),
        "",
        "## Decision and alternatives",
        "",
        f"Selected option: {selected['id']} — {selected['label']}.",
        f"Method: {decision_summary['method']}.",
        "Alternatives considered:",
        *[
            f"- {option['id']} — {option['label']}: {option['reason']}"
            for option in options
        ],
        "",
        "## Review method and system coverage",
        "",
        (
            "Reviewed all 12 multi-record source assets, joined six independent evidence roles "
            "for every portfolio key, validated live records in Salesforce and HubSpot, and used "
            "Gong only for permitted synthesized insights."
        ),
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
                f"Derivation: {change['decision_method']}. {change['decision_explanation']}",
                f"Inputs: {json.dumps(change['decision_inputs'], ensure_ascii=False, sort_keys=True)}.",
                f"Selected approach: {change['selected_option_id']}.",
                f"Evidence: {change['primary_source']} and {change['corroborating_source']}; Gong insight {change['gong_evidence_id']}.",
                f"Complete evidence join: {', '.join(change['evidence_sources'])}.",
                f"Owner: {change['owner']}; deadline: {change['deadline']}.",
                "",
            ]
        )
    sections.extend(
        [
            "## Holds and unresolved conflicts",
            "",
            f"{len(holds)} portfolio records remained unchanged:",
            "",
        ]
    )
    for hold in holds:
        sections.extend(
            [
                f"### {hold['id']} — {hold['portfolio_key']}",
                "",
                (
                    f"{hold['account_name']} remains unchanged for {hold['blocking_condition']}. "
                    f"Evidence: {hold['primary_source']} and {hold['corroborating_source']}."
                ),
                (
                    f"Next step: {hold['required_next_step']} Owner: {hold['owner']}; "
                    f"deadline: {hold['deadline']}."
                ),
                "",
            ]
        )
    sections.extend(
        [
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


def _decision_options(
    spine: TaskSpine,
    task_number: int,
    change_count: int,
) -> list[dict[str, Any]]:
    """Public alternatives the employee request genuinely leaves open."""

    as_of = _as_of(task_number)
    options = _candidate_options(spine)
    reasons = (
        (
            f"The independently controlled evidence effective on {as_of} and the live provider "
            f"state agree for {change_count} portfolio keys."
        ),
        (
            f"This shortcut ignores at least one controlling input and would also alter "
            f"{PORTFOLIO_ENTITY_COUNT - change_count} held records."
        ),
        (
            f"This avoids damage but leaves {change_count} evidence-supported records unresolved."
        ),
    )
    return [
        {
            **option,
            "selected": index == 0,
            "reason": reasons[index],
        }
        for index, option in enumerate(options)
    ]


def rubric_narrative(spec: dict[str, Any]) -> dict[str, Any]:
    """Explain the causal business proof, not merely the final API calls."""

    objects = sorted(
        {
            f"{change['system']}.{change['object_type']}.{change['field']}"
            for change in spec["expected_changes"]
        }
    )
    selected = spec["expected_decision_summary"]["selected_option_id"]
    alternatives = spec["expected_decision_summary"]["alternatives_considered"]
    return {
        "business_outcome": (
            f"Resolve {spec['title'].casefold()} for {spec['company']} as of {spec['as_of']}: "
            f"act on the {spec['expected_change_count']} supported portfolio rows and explicitly "
            f"hold the other {spec['expected_hold_count']} rows."
        ),
        "investigation": (
            f"The model must inventory all {len(spec['required_document_paths'])} multi-record assets, "
            "join each portfolio key across identity, operating observation, authority, governed "
            "transition, live-system index, and exception evidence, then inspect the corresponding "
            f"live records in Salesforce, HubSpot, and Gong. Governed targets: {', '.join(objects)}."
        ),
        "reasoning": (
            f"For every candidate row, apply {spec['expected_decision_summary']['method']!r} to the "
            "independently split observation and authority inputs. Reject rows with a pending approval, "
            "source conflict, ambiguous identity, or superseded-period evidence. Compare all candidate "
            f"approaches ({', '.join(alternatives)}) and justify selecting {selected}."
        ),
        "state_transition": (
            "Write only the task-scoped provider object, immutable record ID, and authorized field/value "
            "for each supported row, exactly once. Every held row, neighboring record, Gong object, and "
            "unrelated field must remain unchanged."
        ),
        "verification": (
            "After each write, query that exact record again and observe the intended field value; a "
            "successful mutation acknowledgement without readback is insufficient. Then produce the "
            "structured decision summary, per-row inputs and derivation, exact held-case blockers, and "
            "human handoff through the filesystem MCP."
        ),
        "required_inferences": [
            {
                "change_id": change["id"],
                "portfolio_key": change["portfolio_key"],
                "provider_target": (
                    f"{change['system']}.{change['object_type']}.{change['record_id']}."
                    f"{change['field']}"
                ),
                "method": change["decision_method"],
                "inputs": change["decision_inputs"],
                "derived_value": change["after"],
            }
            for change in spec["expected_changes"]
        ],
    }


def rubric_criteria(spec: dict[str, Any]) -> list[dict[str, Any]]:
    """Describe every executable criterion in the deterministic verifier.

    These descriptions are generated from immutable task IDs, record IDs,
    fields, and sources.  They are the public explanation of the verifier, not
    a gold call-order recipe.
    """

    rows: list[dict[str, Any]] = []

    def add(category: str, criterion_id: str, description: str) -> None:
        rows.append({
            "id": f"{category}.{criterion_id}",
            "category": category,
            "description": description,
        })

    procedure = {
        "all_evidence_read_in_full": (
            f"Read all {len(spec['required_document_paths'])} task-scoped source records in full before relying on them."
        ),
        "custody_metadata_checked": (
            f"Inspect custody metadata for the {len(spec['metadata_check_paths'])} designated source records."
        ),
        "filesystem_discovery_completed": "Inventory, search, and traverse the released evidence room.",
        "salesforce_discovery_completed": "Identify the Salesforce user and inspect the relevant object contract.",
        "hubspot_discovery_completed": "Inspect the HubSpot account, deal schema, and active pipelines.",
        "task_specific_investigation_completed": (
            "Before changing CRM state, complete this task's distinct identity, association, owner, "
            "scope, and corroboration checks: " + "; ".join(spec["investigation_purposes"]) + "."
        ),
        "all_salesforce_evidence_queried": "Query the Salesforce record corresponding to every proposed portfolio correction.",
        "all_hubspot_evidence_retrieved": "Retrieve the HubSpot record corresponding to every proposed portfolio correction.",
        "all_gong_evidence_queried": "Use the permitted Gong deal insight for every proposed portfolio correction.",
        "all_required_evidence_precedes_mutation": (
            "Read the identity, operating, authority, policy, live-system index, and exception records "
            "before the first CRM mutation."
        ),
        "all_provider_evidence_precedes_mutation": (
            "For each changed record, inspect its live Salesforce, HubSpot, and permitted Gong evidence "
            "before changing that record."
        ),
        "all_mutations_verified_by_readback": (
            "After every CRM mutation, retrieve that exact immutable record again and observe the "
            "derived field at its intended value."
        ),
        "exact_deliverable_set": "Leave only changes.json and brief.md in the output workspace.",
        "deliverables_written_through_mcp": "Create both final deliverables through the filesystem MCP surface.",
    }
    for criterion_id, description in procedure.items():
        add("procedure", criterion_id, description)

    for change in spec["expected_changes"]:
        prefix = change["id"]
        target = f"{change['system']} {change['object_type']} {change['record_id']} field {change['field']}"
        add("state", f"{prefix}.initial_value", f"Confirm {target} began as {change['before']!r}.")
        add("state", f"{prefix}.target_value", f"Leave {target} at the supported value {change['after']!r}.")
        add("state", f"{prefix}.authorized_fields", f"Change only the provider fields authorized for {prefix} on {change['record_id']}.")
        add("state", f"{prefix}.exactly_one_authorized_call", f"Apply the authorized {change['tool']} mutation for {prefix} exactly once.")
        add(
            "state",
            f"{prefix}.postwrite_readback",
            f"Read {target} after the mutation and verify the observed value is {change['after']!r}.",
        )
    add(
        "state",
        "entire_business_state_exact",
        (
            f"Choose the evidence-backed records: all {spec['expected_change_count']} supported changes land "
            "and every held or neighboring record remains byte-for-byte unchanged."
        ),
    )
    add("state", "no_delete_tool_succeeded", "Complete the work without deleting any CRM record.")
    add("state", "gong_remained_read_only", "Keep Gong read-only throughout the workflow.")

    add("changes", "changes_is_object", "Produce changes.json as a JSON object.")
    add("changes", "changes_exact_count", f"Record exactly {spec['expected_change_count']} supported changes in changes.json.")
    add("changes", "change_ids_unique", "Use every authorized change ID once and only once.")
    for field in ("schema_version", "task_id", "title", "company", "as_of"):
        add("changes", f"top_level.{field}", f"Set changes.json top-level {field} to this task's exact released value.")
    for field, expected in spec["expected_decision_summary"].items():
        add(
            "changes",
            f"decision_summary.{field}",
            f"Report the derived decision summary field {field} as {expected!r} after evaluating all three approaches.",
        )
    change_fields = (
        "id", "system", "object_type", "record_id", "operation", "field", "before", "after",
        "reason", "primary_source", "corroborating_source", "gong_evidence_id", "owner", "deadline",
        "portfolio_key", "value_kind", "decision_method", "decision_inputs",
        "decision_explanation", "selected_option_id", "evidence_sources",
    )
    for change in spec["expected_changes"]:
        add("changes", f"{change['id']}.present", f"Include an auditable row for {change['id']} ({change['portfolio_key']}).")
        for field in change_fields:
            add(
                "changes",
                f"{change['id']}.{field}",
                f"Ground {change['id']}'s {field} in the released record for {change['record_id']} and its controlling sources.",
            )
    add(
        "changes",
        "holds_exact_count",
        f"Report exactly {spec['expected_hold_count']} unresolved portfolio records without mutating them.",
    )
    hold_fields = (
        "id", "portfolio_key", "account_name", "blocking_condition", "primary_source",
        "corroborating_source", "owner", "deadline", "required_next_step",
    )
    for hold in spec["expected_holds"]:
        add(
            "changes",
            f"{hold['id']}.present",
            f"Identify {hold['portfolio_key']} as held because of {hold['blocking_condition']}.",
        )
        for field in hold_fields:
            add(
                "changes",
                f"{hold['id']}.{field}",
                f"Ground held-case {hold['id']}'s {field} in its exception and corroborating source.",
            )

    for section in spec["brief_sections"]:
        add("brief", f"section.{section}", f"Include the {section!r} decision section in brief.md.")
    for change in spec["expected_changes"]:
        add(
            "brief",
            f"change.{change['id']}",
            f"Explain {change['id']} with portfolio key {change['portfolio_key']}, record {change['record_id']}, "
            f"field transition {change['before']!r} to {change['after']!r}, both source paths, owner, and deadline.",
        )
    add(
        "brief",
        "decision_and_alternatives",
        "Name the selected evidence-backed option, the rejected alternatives, the derivation method, and the actionable/held counts.",
    )
    for hold in spec["expected_holds"]:
        add(
            "brief",
            f"hold.{hold['id']}",
            f"Explain why {hold['portfolio_key']} stayed unchanged, cite both sources, and state its owner, deadline, and next step.",
        )
    add("brief", "forbidden_claims_absent", "Do not claim that Gong changed, expose private transcript text, invent approval, or report a forbidden bulk action.")

    if len(rows) < 40:
        raise ValueError(f"expected at least 40 rubric criteria, got {len(rows)}")
    return rows


def build_prompt(
    spine: TaskSpine,
    task_id: str,
    task_number: int,
    documents: dict[str, str | bytes],
) -> str:
    frames = (
        (
            "Can you get {title} settled for {requester} before the {period} review? {narrative} "
            "Make the changes the evidence supports, leave uncertain records alone, and send back a short "
            "account of what changed and what still needs a decision."
        ),
        (
            "{requester} has asked for a clean answer on {title}. {narrative} Please resolve the supported "
            "records before the {period} review and leave the team enough source detail to understand every "
            "change and every hold."
        ),
        (
            "We need to finish {title} for {company} this cycle. {narrative} Figure out which records can be "
            "acted on safely, carry those through, and summarize the unresolved cases for {requester}."
        ),
        (
            "Could you take ownership of {title} for {company}? {narrative} The {period} review needs an honest "
            "operating picture, so correct only what the current evidence establishes and explain anything "
            "you deliberately leave untouched."
        ),
        (
            "Before {company}'s {period} review, {requester} needs {title} closed out. {narrative} Please make "
            "the bounded repairs you can support and leave a concise handoff with the facts behind each call."
        ),
        (
            "The next operating meeting is blocked on {title}. {narrative} Work through the records for "
            "{company}, fix the cases that are actually supported, and give {requester} a clear list of the "
            "changes and the exceptions you held."
        ),
        (
            "{company} needs a reliable result for {title}, not another dashboard export. {narrative} Reconcile "
            "what happened, make only justified corrections, and leave {requester} a practical handoff for "
            "the {period} review."
        ),
        (
            "Please sort out {title} for {requester}. {narrative} Use the current records to decide what can "
            "move now, protect anything that remains ambiguous, and document the outcome before the {period} "
            "team review."
        ),
        (
            "There is a live operating decision behind {title} at {company}. {narrative} Resolve the supported "
            "cases, keep conflicting ones on hold, and leave a source-backed note that {requester} can use in "
            "the {period} meeting."
        ),
        (
            "Can you close the loop on {title}? {narrative} {requester} needs the supported corrections in place "
            "for {company}, plus a brief explanation of the records you changed and the ones you did not."
        ),
    )
    frame = frames[(task_number - 1) % len(frames)]
    return frame.format(
        title=spine.title.casefold(),
        requester=spine.requester,
        period=spine.period,
        company=spine.company,
        narrative=spine.narrative,
    )


def generate_task(spine: TaskSpine, task_number: int) -> GeneratedTask:
    task_id = task_id_for(task_number, spine.slug)
    entities = build_entities(spine, task_number)
    changes = build_changes(spine, task_number, entities)
    documents, paths_by_key = build_documents(
        spine, task_id, task_number, entities, changes
    )
    entity_by_key = {entity["portfolio_key"]: entity for entity in entities}
    action_spec = ACTION_SPECS[spine.slug]
    salesforce_object = action_spec.salesforce_object
    hubspot_object = action_spec.hubspot_object
    for change in changes:
        sources = paths_by_key[change["portfolio_key"]]
        change["primary_source"] = sources[0]
        change["corroborating_source"] = sources[1]
        change["evidence_sources"] = list(sources)
        entity = entity_by_key[change["portfolio_key"]]
        gong_call = _gong_evidence_call(spine, entity)
        change["prewrite_evidence"] = {
            "document_paths": list(sources),
            "salesforce_object": salesforce_object,
            "salesforce_record_id": _provider_record_id(
                entity, "salesforce", salesforce_object
            ),
            "hubspot_object": hubspot_object,
            "hubspot_record_id": _provider_record_id(
                entity, "hubspot", hubspot_object
            ),
            "gong_tool": gong_call["name"],
            "gong_record_id": str(
                gong_call["arguments"].get("crmDealId")
                or gong_call["arguments"].get("crmAccountId")
                or gong_call["arguments"].get("crmEntityId")
            ),
        }
    seed = build_seed(spine, task_number, entities)
    all_document_paths = [
        str(PurePosixPath("/workspace/documents") / relative)
        for relative in sorted(documents)
    ]
    required_document_paths = [
        str(PurePosixPath("/workspace/documents") / relative)
        for relative, content in sorted(documents.items())
        if isinstance(content, str)
    ]
    if len(required_document_paths) != REQUIRED_TEXT_DOCUMENT_COUNT:
        raise ValueError(
            f"expected {REQUIRED_TEXT_DOCUMENT_COUNT} readable evidence files, "
            f"got {len(required_document_paths)}"
        )
    binary_document_paths = [
        str(PurePosixPath("/workspace/documents") / relative)
        for relative, content in sorted(documents.items())
        if isinstance(content, bytes)
    ]
    metadata_by_folder: dict[str, str] = {}
    for path in [*binary_document_paths, *required_document_paths]:
        metadata_by_folder.setdefault(PurePosixPath(path).parts[-2], path)
    first_by_folder = list(metadata_by_folder.values())[:METADATA_CHECK_COUNT]
    if len(first_by_folder) != METADATA_CHECK_COUNT:
        raise ValueError(f"expected {METADATA_CHECK_COUNT} metadata paths, got {len(first_by_folder)}")
    calls = _reference_calls(
        spine, task_number, entities, changes, required_document_paths, first_by_folder
    )
    holds = _build_holds(task_number, entities, changes, paths_by_key)
    changes_payload, brief_text = _reference_outputs(
        task_id, spine, task_number, changes, holds
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
    if not MIN_REFERENCE_TOOL_CALLS <= len(calls) <= MAX_REFERENCE_TOOL_CALLS:
        raise ValueError(
            f"reference call count {len(calls)} outside "
            f"{MIN_REFERENCE_TOOL_CALLS}..{MAX_REFERENCE_TOOL_CALLS}"
        )
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
        "agent_visible_document_paths": all_document_paths,
        "required_document_paths": required_document_paths,
        "metadata_check_paths": first_by_folder,
        "required_investigation_calls": [
            {
                "server": call["server"],
                "name": call["name"],
                "arguments": deepcopy(call["arguments"]),
                "purpose": call["purpose"],
            }
            for call in calls
            if call.get("purpose")
        ],
        "investigation_purposes": [
            call["purpose"] for call in calls if call.get("purpose")
        ],
        "reference_tool_calls": len(calls),
        "required_servers": ["filesystem", "salesforce", "hubspot", "gong"],
        "deliverables": list(DELIVERABLES),
        "expected_changes": [
            {key: value for key, value in change.items() if key not in {"tool", "arguments"}}
            | {"tool": change["tool"], "arguments": change["arguments"]}
            for change in changes
        ],
        "expected_change_count": len(changes),
        "expected_decision_summary": changes_payload["decision_summary"],
        "expected_holds": holds,
        "expected_hold_count": len(holds),
        "decision_options": _decision_options(spine, task_number, len(changes)),
        "verify_token_sha256": sha256_text(verification_token(task_id)),
        "contract_pins": CONTRACT_PINS,
        "forbidden_claims": [
            "Gong record updated", "raw private transcript", "board approved all changes",
            "$99,999,999", "deleted the control records",
        ],
        "brief_sections": [
            "Executive assessment", "Decision and alternatives",
            "Review method and system coverage",
            "Authorized changes", "Holds and unresolved conflicts",
            "Control confirmation", "Next operating cadence",
        ],
        "reference_calls": calls,
        "initial_state_sha256": sha256_text(canonical_json(seed)),
    }
    spec["rubric_narrative"] = rubric_narrative(spec)
    spec["rubric_criteria"] = rubric_criteria(spec)
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
