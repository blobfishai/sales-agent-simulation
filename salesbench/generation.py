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
from .runtime.scoring import MILESTONE_IDS, criterion_catalog, milestone_for


RELEASE_VERSION = "3.4.0"
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

# Every held portfolio record carries one of these blocking conditions.  Held
# records are assigned in slot order so each task always contains at least one
# approval-pending record (the unauthorized scope that must stay untouched) and
# one superseded-period record (the control-window exclusion).
HOLD_REASONS = (
    "approval_pending",
    "source_conflict",
    "identity_ambiguous",
    "outside_current_period",
)

# Text sources that carry the operating calendar, queue capacity, fee, and
# review-date facts behind the graded decision model.  No single source holds
# every input and none of them states an option outcome.
DECISION_CALENDAR_SOURCES = (
    "15_collaboration/operations-slack-thread.json",
    "15_collaboration/revenue-slack-thread.json",
    "16_approvals/drive-approval-record.json",
    "17_communications/source-request.eml",
    "19_controls/current-authority.md",
    "20_audit/evidence-status.yaml",
)

OPTION_APPROVAL_STATES = (
    "APPROVED",
    "ADDITIONAL_APPROVAL_REQUIRED",
    "AVAILABLE_NOT_RECOMMENDED",
)
EXPEDITE_OPTION_SUFFIX = "expedited-exception-queue"

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
    calendar: dict[str, Any],
) -> dict[str, str | bytes]:
    retired_calendar = calendar["retired"]
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

    def json_document(kind: str, rows: list[dict[str, Any]], **extra: Any) -> str:
        return json.dumps(
            {
                "case_id": task_id,
                "company": spine.company,
                "workflow": spine.family,
                "record_type": kind,
                "records": rows,
                "warning": "Correlate effective revisions and immutable provider IDs; this file does not pre-authorize a mutation.",
                **extra,
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

    def email_document(
        subject: str,
        rows: list[dict[str, Any]],
        authority: str,
        preamble: list[str],
    ) -> str:
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
            + "\n".join(preamble)
            + f"\n\n{bullets}\n\nDo not infer a supported record change from this thread alone.\n"
        )

    standard_rate = calendar["standard_rate"]
    expedited_rate = calendar["expedited_rate"]
    expedite_fee = calendar["expedite_fee"]
    rereview_cost = calendar["rereview_cost"]
    review_date = calendar["review_date"]
    refresh_date = calendar["refresh_date"]
    blackout_dates = list(calendar["blackout_dates"])
    approval_id = calendar["approval_id"]
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
            "",
            "## Operations queue capacity",
            "",
            f"The standard operations queue executes and reads back {standard_rate} supported "
            "records per business day. Processing days are Monday to Friday, start on the first "
            "business day after the as-of date, and skip the blackout dates published by "
            "Operations. Standard-queue processing of records that pass every control is "
            "delegated to the requester under the current approval.",
            "",
            "## Expedited exception queue",
            "",
            f"The expedited exception queue clears up to {expedited_rate} records per business day "
            f"at USD {expedite_fee} per record. Expedite fees are outside the requester's delegated "
            "authority and require Finance Deal Desk approval before any record is submitted.",
            "",
            "## Re-review cycle",
            "",
            "A portfolio that is held in full re-enters review only at the next full register "
            f"refresh, and every one of the {PORTFOLIO_ENTITY_COUNT} keys is re-reviewed at the "
            f"standard queue rate. The re-review charge is USD {rereview_cost} per record.",
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
            "## Retired queue and fee schedule",
            "",
            f"Superseded capacity: {retired_calendar['standard_rate']} records per business day "
            f"with an expedite fee of USD {retired_calendar['expedite_fee']} per record and a "
            f"re-review charge of USD {retired_calendar['rereview_cost']} per record. These "
            "figures expired with this register and must not be used for the current review.",
            "",
            "A retired control may be cited as conflict context but cannot authorize a current-period transition. Never use this appendix by itself to select an option, change CRM state, infer approval, or overwrite a current owner. If current evidence remains ambiguous, preserve the live record and identify the conflict in the handoff.",
        ]
    ) + "\n"
    audit_log = "\n".join(
        [
            *[
                f"2026-08-26T{index:02d}:00:00Z case={task_id} source={row['source']} revision={row['revision']} status={row['status']} event=metadata-indexed note={row['control_note']}"
                for index, row in enumerate(revisions)
            ],
            *[
                f"2026-08-26T12:{index:02d}:00Z case={task_id} source=Operations event=blackout-published date={value} note=CRM release freeze; the operations queue does not process records on this date"
                for index, value in enumerate(blackout_dates)
            ],
            f"2026-08-26T12:30:00Z case={task_id} source=Revenue event=refresh-scheduled date={refresh_date} note=next full register refresh for a held portfolio",
        ]
    ) + "\n"
    evidence_yaml = "\n".join(
        [
            f"case_id: {task_id}",
            f"company: {json.dumps(spine.company)}",
            "operating_calendar:",
            "  processing_days: Monday to Friday",
            "  blackout_dates:",
            *[f"    - {value}" for value in blackout_dates],
            f"  next_full_register_refresh: {refresh_date}",
            "  note: a held portfolio is re-reviewed in full at the next refresh; outcomes are not stated here",
            "sources:",
        ]
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
        "Standard-queue processing is delegated; expedite fees require Finance Deal Desk sign-off.",
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
    calendar_rows = [
        {"case_id": task_id, "item": "as_of", "date": calendar["as_of"], "status": "current"},
        {"case_id": task_id, "item": "portfolio_review_meeting", "date": review_date, "status": "current"},
        *[
            {"case_id": task_id, "item": "operations_blackout", "date": value, "status": "current"}
            for value in blackout_dates
        ],
        {"case_id": task_id, "item": "next_full_register_refresh", "date": refresh_date, "status": "current"},
        {"case_id": task_id, "item": "portfolio_review_meeting", "date": retired_calendar["review_date"], "status": "retired"},
    ]
    operations_messages = [
        {
            "author": "operations-lead",
            "posted": f"{calendar['as_of']}T09:15:00Z",
            "text": (
                f"Queue status for {task_id}: the standard operations queue is executing and "
                f"reading back {standard_rate} supported records per business day, Monday to Friday, "
                "starting the first business day after the as-of date."
            ),
        },
        {
            "author": "operations-lead",
            "posted": f"{calendar['as_of']}T09:20:00Z",
            "text": (
                f"Reminder: {', '.join(blackout_dates)} is a CRM release-freeze blackout. No "
                "portfolio records are processed that day; count it out of every projection."
            ),
        },
        {
            "author": "revenue-controls",
            "posted": f"{calendar['as_of']}T09:32:00Z",
            "text": (
                "Projections are not published here. Derive them from the supported-record count "
                "after the control join; this thread only confirms capacity and the calendar."
            ),
        },
    ]
    revenue_messages = [
        {
            "author": "revenue-controls",
            "posted": f"{calendar['as_of']}T10:05:00Z",
            "text": (
                f"If the {spine.title.casefold()} portfolio is held in full, it does not re-enter "
                f"review until the next full register refresh on {refresh_date}, and all "
                f"{PORTFOLIO_ENTITY_COUNT} keys are re-reviewed at the standard queue rate."
            ),
        },
        {
            "author": "finance-deal-desk",
            "posted": f"{calendar['as_of']}T10:12:00Z",
            "text": (
                f"The re-review charge is USD {rereview_cost} per record and is billed to the "
                "requesting team. Expedite fees remain a Finance Deal Desk decision and are "
                "not delegated with the standard approval."
            ),
        },
        {
            "author": spine.requester,
            "posted": f"{calendar['as_of']}T10:20:00Z",
            "text": (
                "Understood. I will take the supported records through the queue the current "
                "approval covers and escalate anything that needs a separate sign-off."
            ),
        },
    ]
    approval_record = {
        "approval_id": approval_id,
        "approved_by": "Revenue Controls Committee",
        "approved_scope": (
            "standard operations queue processing of the portfolio records that pass every "
            "identity, observation, authority, live-system, and exception control"
        ),
        "approval_window_closes": review_date,
        "window_note": (
            f"The {spine.period} portfolio review meeting on {review_date} closes the approval "
            "window; supported records must be executed and read back before it."
        ),
        "excluded_scope": [
            "records whose secondary approval is still pending",
            "records with a superseded-period observation",
            "expedited exception-queue submissions",
        ],
        "expedite_fee_usd_per_record": expedite_fee,
        "expedite_fee_authority": (
            "Finance Deal Desk approval; not covered by this approval and outside the "
            "requester's delegated authority"
        ),
    }
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
            {"Review calendar": calendar_rows, "Authority": current}
        ),
        "15_collaboration/operations-slack-thread.json": json_document(
            "operations_slack_thread", revisions, messages=operations_messages
        ),
        "15_collaboration/revenue-slack-thread.json": json_document(
            "revenue_slack_thread", list(reversed(revisions)), messages=revenue_messages
        ),
        "16_approvals/drive-approval-record.json": json_document(
            "drive_approval_record", current, approval=approval_record
        ),
        "16_approvals/drive-source-index.json": json_document("drive_source_index", revisions),
        "17_communications/source-request.eml": email_document(
            "Current review request",
            current,
            "current",
            [
                f"The {spine.period} portfolio review meeting is scheduled for {review_date} "
                f"({calendar['review_weekday']}). Every supported record must be executed and "
                "read back before that meeting.",
                f"Approval {approval_id} covers standard-queue processing of supported records "
                "only. Do not commit expedite fees or act on approval-pending records without "
                "the separate sign-off.",
            ],
        ),
        "17_communications/former-owner-suggestion.eml": email_document(
            "Former owner suggestion",
            retired,
            "retired",
            [
                f"For what it is worth, the old plan had the review on "
                f"{retired_calendar['review_date']} and the queue running at "
                f"{retired_calendar['standard_rate']} records a day. That schedule was retired "
                "with my handover and is not the current calendar.",
            ],
        ),
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
    """Return the three operating alternatives without disclosing their outcomes.

    Index 0 applies the authored rule through the standard operations queue,
    index 1 pushes the same supported records through the expedited exception
    queue (a fee that only Finance Deal Desk can approve), and index 2 holds
    the whole portfolio until the next full register refresh.  Outcome dates,
    incremental costs, and authority statuses are derived from the evidence
    room and are never published with the approaches.
    """

    kind = ACTION_SPECS[spine.slug].value_kind
    variants = {
        "static": (
            (
                "controlled-evidence-join",
                "Apply the governed result only to rows passing every control",
                "Join identity, current observation, authority, provider state, and exceptions.",
            ),
            (
                "portfolio-wide-hold",
                "Leave the entire portfolio unchanged",
                "Wait for the next full register refresh before acting on any row.",
            ),
        ),
        "amount": (
            (
                "controlled-input-recalculation",
                "Recalculate the governed measure from its controlled inputs",
                "Apply the documented exclusions, effective rate, and rounding rule per row.",
            ),
            (
                "amount-review-hold",
                "Hold all amount corrections",
                "Defer every row to the next full register refresh even when inputs reconcile.",
            ),
        ),
        "date": (
            (
                "supported-policy-date",
                "Use the later supported and policy-compliant date",
                "Compare the buyer-supported date with the first allowed operating date.",
            ),
            (
                "retain-stale-date",
                "Leave every current CRM date in place",
                "Defer correction to the next full register refresh even where evidence resolves the conflict.",
            ),
        ),
        "owner": (
            (
                "qualified-owner-with-capacity",
                "Assign the active qualified owner with available capacity",
                "Reconcile territory and role fit with the effective capacity register.",
            ),
            (
                "retain-routing-queue",
                "Leave every supported row in the routing queue",
                "Defer assignment to the next full register refresh even where one candidate satisfies every control.",
            ),
        ),
        "risk": (
            (
                "corroborated-permitted-risk",
                "Apply only a corroborated risk from permitted evidence",
                "Meet the independent-source threshold without copying private activity.",
            ),
            (
                "retain-unreviewed-risk",
                "Leave every risk field unreviewed",
                "Defer classification to the next full register refresh even where corroboration exists.",
            ),
        ),
        "signal": (
            (
                "buyer-supported-action",
                "Record the permitted buyer-supported action",
                "Use the explicit synthesized buyer commitment and reject seller inference.",
            ),
            (
                "blanket-signal-hold",
                "Leave all signal fields unchanged",
                "Defer supported actions to the next full register refresh together with ambiguous records.",
            ),
        ),
        "role": (
            (
                "corroborated-stakeholder-role",
                "Assign the independently corroborated stakeholder role",
                "Require two permitted sources to agree on the person's buying role.",
            ),
            (
                "retain-unknown-role",
                "Keep every stakeholder role unknown",
                "Defer even independently supported role corrections to the next full register refresh.",
            ),
        ),
        "cross_id": (
            (
                "effective-exact-crosswalk",
                "Write the opposite provider ID from the effective exact crosswalk",
                "Require legal name, domain, external key, and mapping revision to agree.",
            ),
            (
                "leave-links-empty",
                "Leave every cross-system link empty",
                "Defer exact matches to the next full register refresh together with ambiguous identities.",
            ),
        ),
        "account": (
            (
                "three-key-legal-identity",
                "Select the legal account satisfying all three identity keys",
                "Reconcile legal name, domain, and external identifier.",
            ),
            (
                "leave-account-unresolved",
                "Leave every account association unresolved",
                "Defer supported associations to the next full register refresh along with ambiguous ones.",
            ),
        ),
    }[kind]
    (controlled_suffix, _, controlled_approach), (hold_suffix, _, hold_approach) = variants
    rule = DECISION_RULES[spine.slug]
    title = spine.title.casefold()
    return [
        {
            "id": f"{spine.slug}:{controlled_suffix}",
            "label": f"Apply the controlled {title} rule through the standard operations queue",
            "approach": f"{rule.method}; {controlled_approach}",
        },
        {
            "id": f"{spine.slug}:{EXPEDITE_OPTION_SUFFIX}",
            "label": f"Push the supported {title} records through the expedited exception queue",
            "approach": (
                "Apply the same controlled rule, but submit every supported record to the "
                "expedited exception queue at the documented per-record fee."
            ),
        },
        {
            "id": f"{spine.slug}:{hold_suffix}",
            "label": f"Hold the entire {title} portfolio until the next full register refresh",
            "approach": hold_approach,
        },
    ]


def _hold_reason(entity: dict[str, Any]) -> str | None:
    return entity.get("hold_reason")


def _sf_id(prefix: str, task_number: int, slot: int) -> str:
    return f"{prefix}SB{task_number:03d}{slot:06d}"[:18]


def _hub_id(task_number: int, slot: int, offset: int) -> str:
    return str(8_000_000_000 + task_number * 100_000 + offset + slot)


def _as_of(task_number: int) -> str:
    return (date(2026, 8, 26) + timedelta(days=task_number % 19)).isoformat()


def business_days_after(start: date, count: int, blackouts: frozenset[date]) -> date:
    """Return the business day ``count`` working days after ``start``.

    The operations queue runs Monday to Friday and skips published blackout
    dates; ``count`` is the number of processing days consumed.
    """

    current = start
    remaining = count
    while remaining > 0:
        current += timedelta(days=1)
        if current.weekday() < 5 and current not in blackouts:
            remaining -= 1
    return current


def _ceil_div(numerator: int, denominator: int) -> int:
    return -(-numerator // denominator)


def decision_calendar(spine: TaskSpine, task_number: int) -> dict[str, Any]:
    """Return the task's documented operating calendar and cost controls.

    These are the raw inputs behind the decision model.  They are seeded into
    the evidence room across several independent sources; the option outcomes
    derived from them are never written anywhere the agent can read.
    """

    as_of = date.fromisoformat(_as_of(task_number))
    seed = stable_seed(f"{task_number}:{spine.slug}:decision-calendar")
    standard_rate = 2 + seed % 3
    expedited_rate = (12, 15, 20)[(seed // 3) % 3]
    expedite_fee = 150 + 25 * ((seed // 9) % 5)
    rereview_cost = 40 + 15 * ((seed // 45) % 4)
    blackout = business_days_after(as_of, 1 + (seed // 180) % 4, frozenset())
    blackouts = frozenset({blackout})
    review_date = business_days_after(as_of, 3 + (seed // 720) % 6, blackouts)
    refresh_date = business_days_after(review_date, 1 + (seed // 4320) % 3, blackouts)
    retired_review_date = review_date - timedelta(days=7 + (seed // 12960) % 5)
    return {
        "as_of": as_of.isoformat(),
        "review_date": review_date.isoformat(),
        "review_weekday": review_date.strftime("%A"),
        "standard_rate": standard_rate,
        "expedited_rate": expedited_rate,
        "expedite_fee": expedite_fee,
        "rereview_cost": rereview_cost,
        "blackout_dates": [blackout.isoformat()],
        "refresh_date": refresh_date.isoformat(),
        "approval_id": f"AP-{task_number:03d}-{stable_seed(spine.slug) % 900 + 100}",
        "retired": {
            "review_date": retired_review_date.isoformat(),
            "standard_rate": standard_rate + 1,
            "expedite_fee": expedite_fee - 25,
            "rereview_cost": rereview_cost + 10,
        },
    }


def decision_model(
    spine: TaskSpine,
    task_number: int,
    changes: list[dict[str, Any]],
    holds: list[dict[str, Any]],
    calendar: dict[str, Any],
) -> dict[str, Any]:
    """Derive the costed, dated, authority-tagged alternatives for a task.

    Outcomes are computed from the supported-record count (the control join),
    the documented queue capacities, the operations blackout calendar, the
    review date, and the refresh schedule.  None of the outcomes appear in the
    evidence room.
    """

    as_of = date.fromisoformat(calendar["as_of"])
    blackouts = frozenset(date.fromisoformat(value) for value in calendar["blackout_dates"])
    review_date = date.fromisoformat(calendar["review_date"])
    refresh_date = date.fromisoformat(calendar["refresh_date"])
    supported = len(changes)
    standard_days = _ceil_div(supported, calendar["standard_rate"])
    expedited_days = _ceil_div(supported, calendar["expedited_rate"])
    hold_days = _ceil_div(PORTFOLIO_ENTITY_COUNT, calendar["standard_rate"])
    standard_outcome = business_days_after(as_of, standard_days, blackouts)
    expedited_outcome = business_days_after(as_of, expedited_days, blackouts)
    hold_outcome = business_days_after(refresh_date, hold_days, blackouts)

    def variance(outcome: date) -> int:
        return (outcome - review_date).days

    def status(outcome: date) -> str:
        return "ON_TIME" if outcome <= review_date else "LATE"

    options = _candidate_options(spine)
    controlled, expedited, hold = options
    graded_options = {
        controlled["id"]: {
            "outcome": standard_outcome.isoformat(),
            "incremental_cost": 0,
            "approval": "APPROVED",
            "control_status": "SUPPORTED_AND_APPROVED",
            "outcome_vs_control_days": variance(standard_outcome),
            "timing_status": status(standard_outcome),
        },
        expedited["id"]: {
            "outcome": expedited_outcome.isoformat(),
            "incremental_cost": supported * calendar["expedite_fee"],
            "approval": "ADDITIONAL_APPROVAL_REQUIRED",
            "control_status": "SEPARATE_APPROVAL_OR_POLICY_EXCEPTION_REQUIRED",
            "outcome_vs_control_days": variance(expedited_outcome),
            "timing_status": status(expedited_outcome),
        },
        hold["id"]: {
            "outcome": hold_outcome.isoformat(),
            "incremental_cost": PORTFOLIO_ENTITY_COUNT * calendar["rereview_cost"],
            "approval": "AVAILABLE_NOT_RECOMMENDED",
            "control_status": "FEASIBLE_WITH_INFERIOR_TRADEOFF",
            "outcome_vs_control_days": variance(hold_outcome),
            "timing_status": status(hold_outcome),
        },
    }
    standard_status = status(standard_outcome)
    return {
        "business_need_date": review_date.isoformat(),
        "standard_queue_records_per_business_day": calendar["standard_rate"],
        "expedited_queue_records_per_business_day": calendar["expedited_rate"],
        "expedite_fee_usd_per_record": calendar["expedite_fee"],
        "rereview_cost_usd_per_record": calendar["rereview_cost"],
        "operations_blackout_dates": list(calendar["blackout_dates"]),
        "next_full_register_refresh": refresh_date.isoformat(),
        "standard_processing_business_days": standard_days,
        "options": graded_options,
        "recommended_outcome_date": standard_outcome.isoformat(),
        "recommended_incremental_cost_usd": 0,
        "outcome_vs_control_days": variance(standard_outcome),
        "decision_timing_status": standard_status,
        "expedite_days_saved": (standard_outcome - expedited_outcome).days,
        "escalation_recommended": standard_status == "LATE",
    }


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
    held = sorted(
        (entity for entity in entities if not entity["target"]),
        key=lambda entity: entity["slot"],
    )
    if len(held) < len(HOLD_REASONS):
        raise ValueError(f"expected at least {len(HOLD_REASONS)} held records, got {len(held)}")
    for index, entity in enumerate(held):
        entity["hold_reason"] = HOLD_REASONS[index % len(HOLD_REASONS)]
    for entity in entities:
        entity.setdefault("hold_reason", None)
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
                        "decision_model", "changes", "holds",
                    ],
                    "decision_summary_fields": [
                        "selected_option_id", "value_kind", "method", "actionable_records",
                        "held_records", "approval_pending_records", "alternatives_considered",
                    ],
                    "decision_model_fields": [
                        "business_need_date", "standard_queue_records_per_business_day",
                        "expedited_queue_records_per_business_day", "expedite_fee_usd_per_record",
                        "rereview_cost_usd_per_record", "operations_blackout_dates",
                        "next_full_register_refresh", "standard_processing_business_days",
                        "options", "recommended_outcome_date", "recommended_incremental_cost_usd",
                        "outcome_vs_control_days", "decision_timing_status", "expedite_days_saved",
                        "escalation_recommended",
                    ],
                    "decision_model_option_fields": [
                        "outcome", "incremental_cost", "approval", "control_status",
                        "outcome_vs_control_days", "timing_status",
                    ],
                    "decision_model_rules": (
                        "Key options by candidate approach id. outcome is the ISO date on which "
                        "the option's full scope is executed and read back: processing days are "
                        "Monday to Friday after the as-of date, skip published blackout dates, and "
                        "consume the documented queue capacity per business day; the hold "
                        "alternative starts at the next full register refresh and re-reviews all "
                        "16 keys. incremental_cost is whole USD relative to the standard queue. "
                        "approval is APPROVED, ADDITIONAL_APPROVAL_REQUIRED, or "
                        "AVAILABLE_NOT_RECOMMENDED. outcome_vs_control_days is the signed calendar "
                        "difference between the outcome and the documented review meeting; "
                        "timing_status is ON_TIME or LATE. escalation_recommended is true only "
                        "when the recommended option lands after the review meeting."
                    ),
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
                        "the controlling and corroborating sources, owner, and deadline. State the "
                        "documented review meeting date and, for every candidate approach, its "
                        "outcome date, incremental cost as 'USD <amount>', approval status, and "
                        "whether the recommended outcome is ON_TIME or LATE."
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
    calendar: dict[str, Any],
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
    documents.update(_supplemental_documents(spine, task_id, task_number, calendar))
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
    model: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    options = _decision_options(spine, task_number, changes, holds, model)
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
        "approval_pending_records": sum(
            hold["blocking_condition"] == "approval_pending" for hold in holds
        ),
        "alternatives_considered": [option["id"] for option in options],
    }
    payload = {
        "schema_version": "salesbench.changes.v1",
        "task_id": task_id,
        "title": spine.title,
        "company": spine.company,
        "as_of": _as_of(task_number),
        "decision_summary": decision_summary,
        "decision_model": deepcopy(model),
        "changes": public_changes,
        "holds": holds,
    }
    selected_variance = model["outcome_vs_control_days"]
    escalation_line = (
        f"Escalation: recommended — the standard queue lands {selected_variance:+d} day(s) "
        f"against the {model['business_need_date']} review, so request Finance Deal Desk "
        f"approval for the expedited exception queue ({selected['id'].split(':')[0]}:"
        f"{EXPEDITE_OPTION_SUFFIX}) in parallel with the authorized changes."
        if model["escalation_recommended"]
        else (
            f"Escalation: not required — the standard queue lands {selected_variance:+d} "
            f"day(s) against the {model['business_need_date']} review; the expedite fee "
            "stays uncommitted and the approval-pending records stay untouched."
        )
    )
    sections = [
        f"# {spine.title}",
        "",
        "## Executive assessment",
        "",
        (
            f"{spine.narrative} The evidence supports {len(public_changes)} bounded changes; "
            f"{len(holds)} portfolio records remain on hold, "
            f"{decision_summary['approval_pending_records']} of them pending secondary approval."
        ),
        "",
        "## Decision and alternatives",
        "",
        (
            f"Business need: the {spine.period} portfolio review meeting on "
            f"{model['business_need_date']}, documented in the review request and the approval "
            "record rather than inferred from the request title."
        ),
        (
            f"Operating calendar: standard queue {model['standard_queue_records_per_business_day']} "
            "supported records per business day (Monday to Friday) with blackout "
            f"{', '.join(model['operations_blackout_dates'])}; expedited exception queue "
            f"{model['expedited_queue_records_per_business_day']} records per business day at "
            f"USD {model['expedite_fee_usd_per_record']} per record (Finance Deal Desk approval); "
            f"next full register refresh {model['next_full_register_refresh']} with re-review at "
            f"USD {model['rereview_cost_usd_per_record']} per record."
        ),
        (
            f"Selected option: {selected['id']} — {selected['label']}. Outcome "
            f"{selected['outcome']} after {model['standard_processing_business_days']} processing "
            f"business day(s), incremental cost USD {selected['incremental_cost']:,}, "
            f"{selected['approval']} ({selected['control_status']}), "
            f"{selected_variance:+d} day(s) versus the review date, "
            f"{model['decision_timing_status']}."
        ),
        f"Method: {decision_summary['method']}.",
        "Alternatives considered:",
        *[
            (
                f"- {option['id']} — {option['label']}: outcome {option['outcome']}, "
                f"incremental cost USD {option['incremental_cost']:,}, {option['approval']} "
                f"({option['control_status']}), {option['outcome_vs_control_days']:+d} day(s) "
                f"versus the review date, {option['timing_status']}. {option['reason']}"
            )
            for option in options
        ],
        escalation_line,
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
    changes: list[dict[str, Any]],
    holds: list[dict[str, Any]],
    model: dict[str, Any],
) -> list[dict[str, Any]]:
    """Public alternatives the employee request genuinely leaves open.

    Every option carries its derived outcome date, incremental cost, and
    authority status; exactly one is recommended.
    """

    as_of = _as_of(task_number)
    change_count = len(changes)
    options = _candidate_options(spine)
    graded = model["options"]
    controlled, expedited, hold = (graded[option["id"]] for option in options)
    pending = sum(row["blocking_condition"] == "approval_pending" for row in holds)
    reasons = (
        (
            f"The independently controlled evidence effective on {as_of} and the live provider "
            f"state agree for {change_count} portfolio keys; the standard queue is the only "
            "currently authorized path and it carries no incremental cost."
        ),
        (
            f"Clearing the same {change_count} records {model['expedite_days_saved']} day(s) "
            f"earlier adds USD {expedited['incremental_cost']:,} in expedite fees that only "
            "Finance Deal Desk can approve; it is not executable under the current approval."
        ),
        (
            f"Holding all {PORTFOLIO_ENTITY_COUNT} records defers work to the "
            f"{model['next_full_register_refresh']} refresh, lands "
            f"{hold['outcome_vs_control_days']:+d} day(s) against the review, bills USD "
            f"{hold['incremental_cost']:,} in re-review charges, and leaves {change_count} "
            "evidence-supported records unresolved."
        ),
    )
    consequences = (
        (
            f"Executes exactly the {change_count} supported changes, keeps the {len(holds)} held "
            f"records untouched ({pending} awaiting secondary approval), and lands "
            f"{controlled['timing_status']} against the documented review date."
        ),
        (
            "Would reach the same CRM state sooner but commits a fee outside the requester's "
            "delegated authority; treated as an escalation request, never executed here."
        ),
        (
            "Changes nothing now, misses the review meeting, and re-opens every key in the next "
            "full refresh cycle."
        ),
    )
    return [
        {
            **option,
            **graded[option["id"]],
            "selected": index == 0,
            "recommended": index == 0,
            "reason": reasons[index],
            "consequence": consequences[index],
        }
        for index, option in enumerate(options)
    ]


def _material_document_paths(
    changes: list[dict[str, Any]],
    holds: list[dict[str, Any]],
) -> list[str]:
    """Return evidence that controls a change, an explicit hold, or the decision model."""

    paths = {
        str(path)
        for change in changes
        for path in change.get("prewrite_evidence", {}).get("document_paths", [])
    }
    paths.update(
        str(path)
        for hold in holds
        for path in (hold["primary_source"], hold["corroborating_source"])
    )
    paths.update(
        str(PurePosixPath("/workspace/documents") / relative)
        for relative in DECISION_CALENDAR_SOURCES
    )
    if not 14 <= len(paths) <= 20:
        raise ValueError(f"expected 14-20 material evidence records, got {len(paths)}")
    return sorted(paths)


def _investigation_slot(purpose: str) -> str:
    lowered = purpose.casefold()
    if any(value in lowered for value in ("identity", "deal-to-company", "portfolio-key")):
        return "identity"
    if any(value in lowered for value in ("authority", "capacity")):
        return "authority"
    if any(value in lowered for value in ("scope", "boundary", "containment", "population")):
        return "scope"
    if any(value in lowered for value in ("corroboration", "buyer-evidence", "conversation-backed")):
        return "corroboration"
    return "custody"


def _semantic_investigation_anchors(arguments: dict[str, Any]) -> list[str]:
    anchored: list[str] = []
    fallbacks: list[str] = []

    def walk(value: Any, key: str = "") -> None:
        if isinstance(value, dict):
            for child_key, child in value.items():
                walk(child, str(child_key))
            return
        if isinstance(value, list):
            for child in value:
                walk(child, key)
            return
        if not isinstance(value, (str, int)) or isinstance(value, bool):
            return
        text = str(value)
        if re.search(
            r"(?:SBP-\d|(?:001|003|006|00Q|0Q0|00T|00v)SB|^8\d{6,}$|^ws-\d)",
            text,
        ):
            anchored.append(text)
        elif key in {
            "object_type",
            "object-name",
            "sobject-name",
            "relationship-path",
            "pattern",
        }:
            fallbacks.append(text)

    walk(arguments)
    values = anchored or fallbacks
    return list(dict.fromkeys(values))[:3]


def _material_investigation_calls(calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates = [call for call in calls if call.get("purpose")]
    by_slot: dict[str, dict[str, Any]] = {}
    for call in candidates:
        by_slot.setdefault(_investigation_slot(str(call["purpose"])), call)
    selected = [
        by_slot[slot]
        for slot in ("identity", "authority", "scope", "corroboration", "custody")
        if slot in by_slot
    ]
    for call in candidates:
        if len(selected) >= 5:
            break
        if call not in selected:
            selected.append(call)
    if len(selected) < 4:
        raise ValueError(f"expected at least four material investigations, got {len(selected)}")
    return [
        {
            "server": call["server"],
            "name": call["name"],
            "arguments": deepcopy(call["arguments"]),
            "purpose": call["purpose"],
            "semantic_anchors": _semantic_investigation_anchors(call["arguments"]),
        }
        for call in selected
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
    model = spec["expected_decision_model"]
    expedite_id = next(
        option["id"] for option in spec["decision_options"]
        if option["approval"] == "ADDITIONAL_APPROVAL_REQUIRED"
    )
    hold_id = next(
        option["id"] for option in spec["decision_options"]
        if option["approval"] == "AVAILABLE_NOT_RECOMMENDED"
    )
    return {
        "business_outcome": (
            f"Resolve {spec['title'].casefold()} for {spec['company']} as of {spec['as_of']}: "
            f"act on the {spec['expected_change_count']} supported portfolio rows and explicitly "
            f"hold the other {spec['expected_hold_count']} rows."
        ),
        "investigation": (
            f"The model must identify the {len(spec['required_document_paths'])} material records inside "
            f"the {len(spec['agent_visible_document_paths'])}-asset evidence room, "
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
        "decision": (
            f"Read the {model['business_need_date']} review meeting from the review request and the "
            "approval record, the standard and expedited queue capacities and fees from the current "
            "authority register and the collaboration threads, and the blackout and refresh calendar "
            "from the operations thread and the audit evidence. Cost and date every alternative from "
            f"the {spec['expected_change_count']} supported records: the standard queue lands on "
            f"{model['recommended_outcome_date']} ({model['outcome_vs_control_days']:+d} day(s), "
            f"{model['decision_timing_status']}); the expedited queue lands "
            f"{model['expedite_days_saved']} day(s) earlier but needs Finance Deal Desk approval; "
            "a full hold waits for the next register refresh and re-reviews every key."
        ),
        "decision_calculations": [
            {
                "id": "identify_business_need_date",
                "field": "business_need_date",
                "description": "Preserve the documented review meeting date; do not infer urgency from the request title.",
                "sources": ["17_communications/source-request.eml", "16_approvals/drive-approval-record.json"],
            },
            {
                "id": "read_standard_queue_capacity",
                "field": "standard_queue_records_per_business_day",
                "description": "Read the current standard-queue throughput; the retired register carries a superseded figure.",
                "sources": ["19_controls/current-authority.md", "15_collaboration/operations-slack-thread.json"],
            },
            {
                "id": "apply_operations_calendar",
                "field": "operations_blackout_dates",
                "description": "Count only Monday-to-Friday processing days and skip the published blackout date.",
                "sources": ["15_collaboration/operations-slack-thread.json", "20_audit/evidence-status.yaml"],
            },
            {
                "id": "calculate_standard_processing_days",
                "field": "standard_processing_business_days",
                "description": "Divide the supported-record count from the control join by the standard-queue capacity and round up.",
                "sources": ["changes.json control join", "19_controls/current-authority.md"],
            },
            {
                "id": "calculate_recommended_outcome",
                "field": "recommended_outcome_date",
                "description": "Advance the as-of date by the processing days across the business-day calendar.",
                "sources": ["as_of", "operations calendar"],
            },
            {
                "id": "calculate_expedite_alternative",
                "field": f"options.{expedite_id}.outcome",
                "description": "Date the expedited exception queue from its capacity and cost it at the documented per-record fee.",
                "sources": ["19_controls/current-authority.md", "16_approvals/drive-approval-record.json"],
            },
            {
                "id": "calculate_hold_alternative",
                "field": f"options.{hold_id}.outcome",
                "description": "Start the full re-review at the next register refresh and cost all 16 keys at the re-review rate.",
                "sources": ["15_collaboration/revenue-slack-thread.json", "20_audit/evidence-status.yaml"],
            },
            {
                "id": "apply_escalation_authority",
                "field": f"options.{expedite_id}.approval",
                "description": "Recognize that expedite fees sit outside the requester's delegated authority.",
                "sources": ["16_approvals/drive-approval-record.json", "19_controls/current-authority.md"],
            },
            {
                "id": "calculate_outcome_variance",
                "field": "outcome_vs_control_days",
                "description": "Compare the recommended outcome with the review meeting into a signed calendar-day variance.",
                "sources": ["recommended_outcome_date", "business_need_date"],
            },
            {
                "id": "state_honest_timing_status",
                "field": "decision_timing_status",
                "description": "Report ON_TIME or LATE; never relabel a late but authorized result as on time.",
                "sources": ["outcome_vs_control_days"],
            },
        ],
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


def rubric_milestones(spec: dict[str, Any]) -> list[dict[str, Any]]:
    """Describe the weighted business milestones the atomic criteria roll into."""

    selected = spec["expected_decision_summary"]["selected_option_id"]
    method = spec["expected_decision_summary"]["method"]
    model = spec["expected_decision_model"]
    systems = ", ".join(sorted({change["system"] for change in spec["expected_changes"]}))
    rows = [
        ("investigation.scope", "investigation", 5, f"Establish {spec['task_id']} as of {spec['as_of']}, inventory the released evidence room, and identify the live Salesforce and HubSpot object contracts without crossing into neighboring portfolio records."),
        ("investigation.evidence", "investigation", 8, f"Find and reconcile the {len(spec['required_document_paths'])} material identity, operating, authority, policy, calendar, and exception records inside the larger evidence room before relying on a recommendation."),
        ("investigation.identity", "investigation", 6, "Resolve cross-system portfolio keys, account or deal associations, active ownership, and record identity through task-specific searches; valid query shapes and investigation order are open."),
        ("investigation.authority", "investigation", 7, f"Separate observations from authority under {method!r}, reject pending, conflicting, ambiguous, or superseded evidence, and preserve the supported owners and deadlines."),
        ("investigation.provider_correlation", "investigation", 9, f"Correlate every proposed change against its immutable Salesforce, HubSpot, and permitted Gong evidence before mutating {systems}; do not infer live state from files alone."),
        ("decision.portfolio", "decision", 8, f"Evaluate all three released approaches, choose {selected!r} from the joined evidence, and derive exactly {spec['expected_change_count']} actionable and {spec['expected_hold_count']} held portfolio rows."),
        ("decision.alternatives", "decision", 7, f"Date and cost every alternative from the {spec['expected_change_count']} supported records, the documented queue capacities, fees, blackout calendar, and refresh schedule; compare the recommended outcome with the {model['business_need_date']} review meeting into a signed variance and an honest ON_TIME/LATE status; keep the expedite fee unauthorized and the full hold as the inferior tradeoff."),
        ("state.primary", "state", 15, f"Persist exactly the {spec['expected_change_count']} authorized CRM field transitions on their immutable record IDs, once each, with provider-critical values supported by the evidence."),
        ("verification.readback", "verification", 6, "After every CRM mutation, retrieve the same immutable record and observe the intended persisted field value rather than trusting the acknowledgement."),
        ("containment.scope", "containment", 8, f"Keep all {spec['expected_hold_count']} held rows, neighboring records, unrelated fields, and Gong state unchanged; complete without deletion or a forbidden claim."),
        ("deliverable.decision_summary", "answer", 4, f"Produce a task-scoped decision summary with the exact selected option, method, alternatives, and actionable-versus-held counts for {spec['company']}."),
        ("deliverable.changes", "answer", 7, "Provide one auditable structured row per supported change, including immutable identity, before/after value, derivation inputs, sources, owner, and deadline."),
        ("deliverable.holds", "answer", 5, "Provide one auditable row per held case with its evidence-backed blocker, corroboration, owner, deadline, and required next step."),
        ("deliverable.brief", "answer", 3, "Write a concise executive handoff that explains the decision, the dated and costed alternatives, authorized changes, unresolved holds, control confirmation, and next operating cadence."),
        ("execution.delivery", "execution", 2, "Leave only changes.json and brief.md, write both through the filesystem MCP, and complete without a rejected state-changing call."),
    ]
    if tuple(row[0] for row in rows) != MILESTONE_IDS or sum(row[2] for row in rows) != 100:
        raise ValueError("semantic rubric must contain the published milestones totaling 100 points")
    return [
        {"id": milestone_id, "category": category, "weight": weight, "description": description}
        for milestone_id, category, weight, description in rows
    ]


def _criterion_description(spec: dict[str, Any], component: str, criterion_id: str) -> str:
    """Explain one executable verifier criterion from immutable task facts."""

    changes = {change["id"]: change for change in spec["expected_changes"]}
    holds = {hold["id"]: hold for hold in spec["expected_holds"]}
    model = spec["expected_decision_model"]
    if component == "procedure":
        return {
            "filesystem_discovery_completed": "Inventory, search, and traverse the released evidence room.",
            "custody_metadata_checked": f"Inspect custody metadata for the {len(spec['metadata_check_paths'])} designated source records.",
            "salesforce_discovery_completed": "Identify the Salesforce user and inspect the relevant object contract.",
            "hubspot_discovery_completed": "Inspect the HubSpot account, object schema, and pipelines or object listing.",
            "material_evidence_read_in_full": f"Read all {len(spec['required_document_paths'])} material source records, including the review-date, capacity, fee, and calendar evidence, in full.",
            "all_required_evidence_precedes_mutation": "Read the identity, operating, authority, policy, live-system index, exception, and calendar records before the first CRM mutation.",
            "task_specific_investigation_completed": "Before changing CRM state, complete this task's distinct identity, association, owner, scope, and corroboration checks: " + "; ".join(spec["investigation_purposes"]) + ".",
            "all_salesforce_evidence_queried": "Query the Salesforce record corresponding to every proposed portfolio correction.",
            "all_hubspot_evidence_retrieved": "Retrieve the HubSpot record corresponding to every proposed portfolio correction.",
            "all_gong_evidence_queried": "Use the permitted Gong insight for every proposed portfolio correction.",
            "all_provider_evidence_precedes_mutation": "For each changed record, inspect its live Salesforce, HubSpot, and permitted Gong evidence before changing that record.",
            "all_mutations_verified_by_readback": "After every CRM mutation, retrieve that exact immutable record again and observe the derived field at its intended value.",
            "exact_deliverable_set": "Leave only changes.json and brief.md in the output workspace.",
            "deliverables_written_through_mcp": "Create both final deliverables through the filesystem MCP surface.",
            "no_rejected_mutation": "Complete the work without a rejected state-changing call.",
        }[criterion_id]
    if component == "state":
        if criterion_id == "entire_business_state_exact":
            return f"All {spec['expected_change_count']} supported changes land and every held or neighboring record remains byte-for-byte unchanged."
        if criterion_id == "no_delete_tool_succeeded":
            return "Complete the work without deleting any CRM record."
        if criterion_id == "gong_remained_read_only":
            return "Keep Gong read-only throughout the workflow."
        change_id, suffix = criterion_id.rsplit(".", 1)
        change = changes[change_id]
        target = f"{change['system']} {change['object_type']} {change['record_id']} field {change['field']}"
        return {
            "initial_value": f"Confirm {target} began as {change['before']!r}.",
            "target_value": f"Leave {target} at the supported value {change['after']!r}.",
            "authorized_fields": f"Change only the provider fields authorized for {change_id} on {change['record_id']}.",
            "exactly_one_authorized_call": f"Apply the authorized {change['tool']} mutation for {change_id} exactly once.",
            "postwrite_readback": f"Read {target} after the mutation and verify the observed value is {change['after']!r}.",
        }[suffix]
    if component == "changes":
        if criterion_id == "changes_is_object":
            return "Produce changes.json as a JSON object."
        if criterion_id == "changes_exact_count":
            return f"Record exactly {spec['expected_change_count']} supported changes in changes.json."
        if criterion_id == "change_ids_unique":
            return "Use every authorized change ID once and only once."
        if criterion_id == "holds_exact_count":
            return f"Report exactly {spec['expected_hold_count']} unresolved portfolio records without mutating them."
        if criterion_id == "hold_ids_unique":
            return "Use every held-case ID once and only once."
        if criterion_id.startswith("top_level."):
            return f"Set changes.json top-level {criterion_id.split('.', 1)[1]} to this task's exact released value."
        if criterion_id.startswith("decision_summary."):
            key = criterion_id.split(".", 1)[1]
            return f"Report the derived decision summary field {key} as {spec['expected_decision_summary'][key]!r} after evaluating all three approaches."
        if criterion_id.startswith("decision_model."):
            path = criterion_id.split(".", 1)[1]
            option_descriptions = {
                "outcome": "the ISO date on which its full scope is executed and read back across the business-day calendar",
                "incremental_cost": "its whole-USD incremental cost relative to the standard queue",
                "approval": "its authority status (APPROVED, ADDITIONAL_APPROVAL_REQUIRED, or AVAILABLE_NOT_RECOMMENDED)",
                "control_status": "its control status",
                "outcome_vs_control_days": "its signed calendar-day variance against the documented review meeting",
                "timing_status": "its honest ON_TIME or LATE status against the review meeting",
            }
            if path.startswith("options."):
                option_id, field = path[len("options."):].rsplit(".", 1)
                return f"Grade alternative {option_id}: report {option_descriptions[field]} exactly as derived from the evidence room."
            return {
                "business_need_date": f"Report the review meeting date {model['business_need_date']} documented in the review request and the approval record, not inferred from the request title.",
                "standard_queue_records_per_business_day": "Report the current standard-queue capacity from the current authority register and operations thread, not the retired figure.",
                "expedited_queue_records_per_business_day": "Report the expedited exception-queue capacity from the current authority register.",
                "expedite_fee_usd_per_record": "Report the current expedite fee from the approval record and the current authority register.",
                "rereview_cost_usd_per_record": "Report the current re-review charge from the revenue thread and the current authority register.",
                "operations_blackout_dates": "List the published operations blackout dates that the projection must skip.",
                "next_full_register_refresh": "Report the next full register refresh date from the revenue thread and the audit evidence.",
                "standard_processing_business_days": f"Derive {model['standard_processing_business_days']} processing day(s) by dividing the supported-record count by the standard-queue capacity and rounding up.",
                "recommended_outcome_date": f"Derive the recommended outcome date {model['recommended_outcome_date']} by advancing the as-of date across Monday-to-Friday processing days and skipping the blackout.",
                "recommended_incremental_cost_usd": "Report the recommended option's incremental cost (USD 0 for the standard queue).",
                "outcome_vs_control_days": f"Report the signed variance {model['outcome_vs_control_days']:+d} day(s) between the recommended outcome and the review meeting.",
                "decision_timing_status": f"Report {model['decision_timing_status']} honestly; never relabel a late authorized result as on time.",
                "expedite_days_saved": "Report how many calendar days the expedited queue would save, without executing it.",
                "escalation_recommended": "Recommend escalation to Finance Deal Desk only when the recommended outcome lands after the review meeting.",
            }[path]
        prefix, field = criterion_id.rsplit(".", 1)
        if prefix in changes:
            change = changes[prefix]
            if field == "present":
                return f"Include an auditable row for {prefix} ({change['portfolio_key']})."
            return f"Ground {prefix}'s {field} in the released record for {change['record_id']} and its controlling sources."
        hold = holds[prefix]
        if field == "present":
            return f"Identify {hold['portfolio_key']} as held because of {hold['blocking_condition']}."
        return f"Ground held-case {prefix}'s {field} in its exception and corroborating source."
    if component == "brief":
        if criterion_id.startswith("section."):
            return f"Include the {criterion_id.split('.', 1)[1]!r} decision section in brief.md."
        if criterion_id.startswith("change."):
            change = changes[criterion_id.split(".", 1)[1]]
            return f"Explain {change['id']} with portfolio key {change['portfolio_key']}, record {change['record_id']}, field transition {change['before']!r} to {change['after']!r}, both source paths, owner, and deadline."
        if criterion_id.startswith("hold."):
            hold = holds[criterion_id.split(".", 1)[1]]
            return f"Explain why {hold['portfolio_key']} stayed unchanged, cite both sources, and state its owner, deadline, and next step."
        return {
            "decision_and_alternatives": "Name the selected evidence-backed option, the rejected alternatives, and the derivation method.",
            "alternatives_costed_and_dated": f"State the {model['business_need_date']} review meeting, every alternative's outcome date, incremental cost as 'USD <amount>', and approval status, and the recommended option's ON_TIME/LATE status.",
            "forbidden_claims_absent": "Make no forbidden claim about Gong mutation, private transcripts, blanket approval, invented amounts, or deleted controls.",
        }[criterion_id]
    raise ValueError(f"unknown verifier component: {component}")


def rubric_criteria(spec: dict[str, Any]) -> list[dict[str, Any]]:
    """Publish every executable criterion together with the milestone it rolls into.

    The list is derived from the verifier's own criterion catalog, so the
    released rubric and the executed report agree criterion for criterion.
    """

    rows = [
        {
            "id": f"{component}.{criterion_id}",
            "category": component,
            "milestone": milestone_for(component, criterion_id),
            "description": _criterion_description(spec, component, criterion_id),
        }
        for component, criterion_id in criterion_catalog(spec)
    ]
    if len({row["id"] for row in rows}) != len(rows):
        raise ValueError("atomic criterion ids must be unique")
    milestones = {row["milestone"] for row in rows}
    if milestones != set(MILESTONE_IDS):
        raise ValueError(f"every milestone needs atomic evidence: {set(MILESTONE_IDS) - milestones}")
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
    calendar = decision_calendar(spine, task_number)
    documents, paths_by_key = build_documents(
        spine, task_id, task_number, entities, changes, calendar
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
    reference_document_paths = [
        str(PurePosixPath("/workspace/documents") / relative)
        for relative, content in sorted(documents.items())
        if isinstance(content, str)
    ]
    if len(reference_document_paths) != REQUIRED_TEXT_DOCUMENT_COUNT:
        raise ValueError(
            f"expected {REQUIRED_TEXT_DOCUMENT_COUNT} readable evidence files, "
            f"got {len(reference_document_paths)}"
        )
    binary_document_paths = [
        str(PurePosixPath("/workspace/documents") / relative)
        for relative, content in sorted(documents.items())
        if isinstance(content, bytes)
    ]
    metadata_by_folder: dict[str, str] = {}
    for path in [*binary_document_paths, *reference_document_paths]:
        metadata_by_folder.setdefault(PurePosixPath(path).parts[-2], path)
    first_by_folder = list(metadata_by_folder.values())[:METADATA_CHECK_COUNT]
    if len(first_by_folder) != METADATA_CHECK_COUNT:
        raise ValueError(f"expected {METADATA_CHECK_COUNT} metadata paths, got {len(first_by_folder)}")
    calls = _reference_calls(
        spine, task_number, entities, changes, reference_document_paths, first_by_folder
    )
    holds = _build_holds(task_number, entities, changes, paths_by_key)
    required_document_paths = _material_document_paths(changes, holds)
    metadata_check_paths = [
        path
        for path in first_by_folder
        if path in binary_document_paths or path in required_document_paths
    ][:4]
    for path in first_by_folder:
        if len(metadata_check_paths) >= 4:
            break
        if path not in metadata_check_paths:
            metadata_check_paths.append(path)
    model = decision_model(spine, task_number, changes, holds, calendar)
    options = _decision_options(spine, task_number, changes, holds, model)
    changes_payload, brief_text = _reference_outputs(
        task_id, spine, task_number, changes, holds, model
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
        "reference_document_paths": reference_document_paths,
        "metadata_check_paths": metadata_check_paths,
        "reference_metadata_check_paths": first_by_folder,
        "required_investigation_calls": _material_investigation_calls(calls),
        "reference_investigation_calls": [
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
            call["purpose"] for call in _material_investigation_calls(calls)
        ],
        "reference_investigation_purposes": [
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
        "expected_decision_model": changes_payload["decision_model"],
        "decision_calendar": {
            key: value for key, value in calendar.items() if key != "retired"
        },
        "expected_holds": holds,
        "expected_hold_count": len(holds),
        "decision_options": options,
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
    spec["rubric_milestones"] = rubric_milestones(spec)
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
