"""Task-specific CRM transitions for SalesBench-100.

The employee requests are not interchangeable.  This table binds every authored
business spine to a provider object, field, starting value, and evidence-derived
value class.  Generic Salesforce and HubSpot update tools remain shared, as they
are in real MCP servers; the business state being changed does not.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ActionSpec:
    salesforce_object: str
    hubspot_object: str
    salesforce_field: str
    hubspot_field: str
    value_kind: str
    salesforce_before: Any
    hubspot_before: Any
    salesforce_after: Any = None
    hubspot_after: Any = None


def _a(
    salesforce_object: str,
    hubspot_object: str,
    salesforce_field: str,
    hubspot_field: str,
    value_kind: str,
    salesforce_before: Any,
    hubspot_before: Any,
    salesforce_after: Any = None,
    hubspot_after: Any = None,
) -> ActionSpec:
    return ActionSpec(
        salesforce_object,
        hubspot_object,
        salesforce_field,
        hubspot_field,
        value_kind,
        salesforce_before,
        hubspot_before,
        salesforce_after,
        hubspot_after,
    )


ACTION_SPECS: dict[str, ActionSpec] = {
    # Forecast reconciliation
    "northwind-q3-commit": _a("Opportunity", "deals", "ForecastCategoryName", "forecast_status", "static", "Pipeline", "pipeline", "Commit", "commit"),
    "velora-emea-rollup": _a("Opportunity", "deals", "ForecastCategoryName", "forecast_status", "static", "Pipeline", "pipeline", "Best Case", "upside"),
    "harborstone-public-sector": _a("Opportunity", "deals", "Funding_Status__c", "funding_status", "static", "Unverified", "unverified", "Funded", "funded"),
    "cedarline-midmarket": _a("Opportunity", "deals", "CloseDate", "closedate", "date", "2026-12-31", "2026-12-31"),
    "atlas-apac-currency": _a("Opportunity", "deals", "Normalized_Subscription_ARR__c", "normalized_subscription_arr", "amount", 0, "0"),
    "lattice-partner-overlay": _a("Opportunity", "deals", "Forecast_Credit_Account__c", "forecast_credit_account", "account", "", ""),
    "meridian-usage-expansion": _a("Opportunity", "deals", "Expansion_Forecast_Status__c", "expansion_forecast_status", "static", "Pipeline", "pipeline", "Upside", "upside"),
    "opal-healthcare-commit": _a("Opportunity", "deals", "Commit_Certification__c", "commit_certification", "static", "Pending", "pending", "Certified", "certified"),
    "quarry-enterprise-split": _a("Opportunity", "deals", "Forecast_Value__c", "forecast_value", "amount", 0, "0"),
    "solstice-fiscal-boundary": _a("Opportunity", "deals", "Fiscal_Probability__c", "fiscal_probability", "static", 0.0, "0", 0.65, "0.65"),

    # Pipeline recovery
    "acorn-stalled-enterprise": _a("Task", "tasks", "Status", "hs_task_status", "static", "Deferred", "DEFERRED", "Not Started", "NOT_STARTED"),
    "brightwell-trial-expiry": _a("Task", "tasks", "ActivityDate", "hs_timestamp", "date", "2026-12-31", "2026-12-31"),
    "cinder-manufacturing-slips": _a("Task", "tasks", "Schedule_Risk__c", "schedule_risk", "risk", "Unreviewed", "unreviewed"),
    "drift-renewal-blockers": _a("Task", "tasks", "Priority", "hs_task_priority", "static", "Normal", "MEDIUM", "High", "HIGH"),
    "ember-champion-departures": _a("Task", "tasks", "Subject", "hs_task_subject", "signal", "Deferred relationship review", "Deferred relationship review"),
    "fable-procurement-pauses": _a("Task", "tasks", "Type", "hs_task_type", "static", "Routine", "ROUTINE", "Procurement Follow-up", "PROCUREMENT_FOLLOW_UP"),
    "granite-security-reviews": _a("Task", "tasks", "OwnerId", "hubspot_owner_id", "owner", "00GQUEUE", "unassigned"),
    "helix-multi-threading": _a("Task", "tasks", "Stakeholder_Action__c", "stakeholder_action", "static", "None", "none", "Develop Missing Role", "develop_missing_role"),
    "indigo-next-step-aging": _a("Task", "tasks", "False_Freshness__c", "false_freshness", "static", False, "false", True, "true"),
    "juniper-partner-handoffs": _a("Task", "tasks", "OwnerId", "hubspot_owner_id", "owner", "00GQUEUE", "unassigned"),

    # Gong action reconciliation
    "keystone-discovery-actions": _a("Task", "tasks", "Subject", "hs_task_subject", "signal", "Deferred call action", "Deferred call action"),
    "lumen-exec-briefs": _a("Task", "tasks", "Executive_Brief_Status__c", "executive_brief_status", "static", "Pending", "pending", "Ready", "ready"),
    "monarch-competitor-mentions": _a("Opportunity", "deals", "Competitor_Evidence__c", "competitor_evidence", "risk", "Unknown", "unknown"),
    "nova-mutual-plans": _a("Task", "tasks", "ActivityDate", "hs_timestamp", "date", "2026-12-31", "2026-12-31"),
    "orbit-objection-coding": _a("Opportunity", "deals", "Objection_Code__c", "objection_code", "risk", "Unclassified", "unclassified"),
    "palisade-handoff-notes": _a("Lead", "contacts", "Qualification_Status__c", "qualification_status", "static", "Pending", "pending", "Qualified", "qualified"),
    "quill-coaching-actions": _a("Task", "tasks", "Subject", "hs_task_subject", "signal", "Deferred coaching follow-up", "Deferred coaching follow-up"),
    "ridgeway-call-privacy": _a("CampaignMember", "contacts", "Privacy_Review_Status__c", "privacy_review_status", "static", "Pending", "pending", "Permitted Insight Only", "permitted_insight_only"),
    "summit-commercial-terms": _a("Opportunity", "deals", "NextStep", "next_step", "signal", "", ""),
    "tandem-contact-roles": _a("Contact", "contacts", "Buying_Role__c", "buying_role", "role", "Unknown", "Unknown"),

    # Identity and migration
    "umbra-domain-collisions": _a("Account", "companies", "External_Match_Status__c", "external_match_status", "static", "Pending", "pending", "Independently Matched", "independently_matched"),
    "vector-contact-dedup": _a("Contact", "contacts", "Identity_Link_Status__c", "identity_link_status", "static", "Unlinked", "unlinked", "Linked", "linked"),
    "willow-parent-child": _a("Account", "companies", "Hierarchy_Status__c", "hierarchy_status", "static", "Flat", "flat", "Verified", "verified"),
    "xenon-owner-crosswalk": _a("Account", "companies", "OwnerId", "hubspot_owner_id", "owner", "00GQUEUE", "unassigned"),
    "yellowbrick-lifecycle-sync": _a("Lead", "contacts", "Status", "lifecyclestage", "static", "Open - Not Contacted", "lead", "Working - Contacted", "salesqualifiedlead"),
    "zenith-external-id-gaps": _a("Account", "companies", "HubSpot_Company_ID__c", "salesforce_account_id", "cross_id", "", ""),
    "alpine-acquisition-merge": _a("Account", "companies", "Migration_Status__c", "migration_status", "static", "Pending", "pending", "Consolidated", "consolidated"),
    "brookfield-consent-survival": _a("Contact", "contacts", "Consent_Status__c", "consent_status", "static", "Unknown", "unknown", "Restricted", "restricted"),
    "cascade-custom-object-map": _a("Account", "companies", "Site_Association_Status__c", "site_association_status", "static", "Missing", "missing", "Restored", "restored"),
    "delta-sandbox-cutover": _a("Account", "companies", "Production_Identity_Status__c", "production_identity_status", "static", "Sandbox Only", "sandbox_only", "Certified", "certified"),

    # Lead routing
    "everest-enterprise-inbound": _a("Lead", "contacts", "OwnerId", "hubspot_owner_id", "owner", "00GQUEUE", "unassigned"),
    "foxtrot-emea-consent": _a("Lead", "contacts", "Consent_Status__c", "consent_status", "static", "Pending", "pending", "Eligible", "eligible"),
    "ginkgo-product-led": _a("Lead", "contacts", "Qualification_Tier__c", "qualification_tier", "static", "Unscored", "unscored", "Product Qualified", "product_qualified"),
    "highland-public-sector": _a("Lead", "contacts", "Account_Hierarchy_Status__c", "account_hierarchy_status", "static", "Campus", "campus", "Centralized", "centralized"),
    "ion-health-system": _a("Lead", "contacts", "Health_System_Route__c", "health_system_route", "account", "", ""),
    "jasper-apac-capacity": _a("Lead", "contacts", "OwnerId", "hubspot_owner_id", "owner", "00GQUEUE", "unassigned"),
    "kinetic-partner-sourced": _a("Lead", "contacts", "Routing_Channel__c", "routing_channel", "static", "Unclassified", "unclassified", "Partner", "partner"),
    "lowell-duplicate-mqls": _a("Lead", "contacts", "Duplicate_Status__c", "duplicate_status", "static", "Unreviewed", "unreviewed", "Consolidated", "consolidated"),
    "mosaic-intent-threshold": _a("Lead", "contacts", "Qualification_Status__c", "qualification_status", "static", "Pending", "pending", "Qualified", "qualified"),
    "nimbus-student-exclusion": _a("Lead", "contacts", "Buyer_Persona_Status__c", "buyer_persona_status", "static", "Unreviewed", "unreviewed", "Qualified Buyer", "qualified_buyer"),

    # Renewal and expansion
    "oak-renewal-notice": _a("Opportunity", "deals", "Notice_Status__c", "notice_status", "static", "Unreviewed", "unreviewed", "Inside Cure Window", "inside_cure_window"),
    "prairie-usage-expansion": _a("Opportunity", "deals", "Expansion_Motion__c", "expansion_motion", "static", "Unreviewed", "unreviewed", "Customer Success Recovery", "customer_success_recovery"),
    "quartz-multi-product": _a("Opportunity", "deals", "Renewal_Group__c", "renewal_group", "account", "", ""),
    "redwood-churn-save": _a("Opportunity", "deals", "Renewal_Risk__c", "renewal_risk", "risk", "Unreviewed", "unreviewed"),
    "sequoia-merger-renewals": _a("Opportunity", "deals", "OwnerId", "hubspot_owner_id", "owner", "00GQUEUE", "unassigned"),
    "timberline-support-risk": _a("Opportunity", "deals", "Expansion_Gate__c", "expansion_gate", "static", "Unreviewed", "unreviewed", "Recovery Required", "recovery_required"),
    "upland-channel-renewal": _a("Opportunity", "deals", "CloseDate", "closedate", "date", "2026-12-31", "2026-12-31"),
    "vista-auto-renewal": _a("Opportunity", "deals", "Notice_Required__c", "notice_required", "static", False, "false", True, "true"),
    "watershed-seat-trueup": _a("Opportunity", "deals", "True_Up_Status__c", "true_up_status", "static", "Unreviewed", "unreviewed", "Candidate", "candidate"),
    "yarrow-executive-handoff": _a("Opportunity", "deals", "Executive_Sponsor_Status__c", "executive_sponsor_status", "static", "Unreviewed", "unreviewed", "Introduction Required", "introduction_required"),

    # Quote governance
    "zephyr-discount-chain": _a("Quote", "deals", "Readiness_Status__c", "quote_readiness", "static", "Unreviewed", "unreviewed", "Ready with Conditions", "ready_with_conditions"),
    "amber-ramp-pricing": _a("Quote", "deals", "Effective_Discount__c", "effective_discount", "static", 0.0, "0", 18.5, "18.5"),
    "birch-public-sector-terms": _a("Quote", "deals", "Public_Sector_Readiness__c", "public_sector_readiness", "static", "Unreviewed", "unreviewed", "Ready", "ready"),
    "coral-nonstandard-payment": _a("Quote", "deals", "Payment_Term_Risk__c", "payment_term_risk", "risk", "Unreviewed", "unreviewed"),
    "dogwood-bundle-floor": _a("Quote", "deals", "Bundle_Floor_Status__c", "bundle_floor_status", "static", "Unreviewed", "unreviewed", "Within Approved Floor", "within_approved_floor"),
    "elm-partner-margin": _a("Quote", "deals", "Partner_Margin_Status__c", "partner_margin_status", "static", "Unreviewed", "unreviewed", "Exception", "exception"),
    "fir-usage-commit": _a("Quote", "deals", "Approval_Requirement__c", "approval_requirement", "static", "Unreviewed", "unreviewed", "Required", "required"),
    "grove-currency-lock": _a("Quote", "deals", "Currency_Lock_Status__c", "currency_lock_status", "static", "Current", "current", "Reprice", "reprice"),
    "hawthorn-legal-gate": _a("Quote", "deals", "Legal_Gate_Status__c", "legal_gate_status", "static", "Complete", "complete", "Open", "open"),
    "ironwood-order-form": _a("Quote", "deals", "Order_Form_Reconciliation__c", "order_form_reconciliation", "static", "Unreviewed", "unreviewed", "Exception", "exception"),

    # Account planning
    "jade-global-account": _a("Contact", "contacts", "Buying_Role__c", "buying_role", "role", "Unknown", "Unknown"),
    "kingfisher-exec-map": _a("Contact", "contacts", "Executive_Role__c", "executive_role", "role", "Unknown", "Unknown"),
    "laurel-white-space": _a("Opportunity", "deals", "Whitespace_Status__c", "whitespace_status", "static", "Unreviewed", "unreviewed", "Qualified", "qualified"),
    "maple-partner-ecosystem": _a("Contact", "contacts", "Partner_Role__c", "partner_role", "role", "Unknown", "Unknown"),
    "nutmeg-contact-coverage": _a("Contact", "contacts", "Coverage_Gap__c", "coverage_gap", "risk", "Unreviewed", "unreviewed"),
    "olive-support-overlay": _a("Opportunity", "deals", "Account_Plan_Risk__c", "account_plan_risk", "risk", "Unreviewed", "unreviewed"),
    "pine-competitive-plan": _a("Opportunity", "deals", "Competitor_Evidence__c", "competitor_evidence", "risk", "Unknown", "unknown"),
    "riverbank-succession": _a("Contact", "contacts", "Succession_Status__c", "succession_status", "static", "Unreviewed", "unreviewed", "Rebuild", "rebuild"),
    "spruce-board-prep": _a("Opportunity", "deals", "Board_Action_Status__c", "board_action_status", "signal", "", ""),
    "topaz-regional-org": _a("Contact", "contacts", "Reporting_Line_Status__c", "reporting_line_status", "static", "Flat", "flat", "Restored", "restored"),

    # Sequence compliance
    "umber-gdpr-sequence": _a("CampaignMember", "contacts", "Status", "sequence_status", "static", "Sent", "ACTIVE", "Removed - Compliance", "PAUSED_COMPLIANCE"),
    "violet-suppression-sync": _a("CampaignMember", "contacts", "Suppression_Status__c", "suppression_status", "static", "Active", "active", "Suppressed", "suppressed"),
    "walnut-domain-health": _a("CampaignMember", "contacts", "Domain_Enrollment_Status__c", "domain_enrollment_status", "static", "Active", "active", "Paused", "paused"),
    "xylem-cadence-overlap": _a("CampaignMember", "contacts", "Sequence_Priority__c", "sequence_priority", "static", "Unreviewed", "unreviewed", "Preferred Motion", "preferred_motion"),
    "yucca-country-policy": _a("CampaignMember", "contacts", "Consent_Version_Status__c", "consent_version_status", "static", "Legacy", "legacy", "Current", "current"),
    "azalea-customer-exclusion": _a("CampaignMember", "contacts", "Customer_Exclusion_Status__c", "customer_exclusion_status", "static", "Active", "active", "Removed", "removed"),
    "bluebell-reply-stop": _a("CampaignMember", "contacts", "Reply_Stop_Status__c", "reply_stop_status", "static", "Active", "active", "Stopped", "stopped"),
    "clover-event-consent": _a("CampaignMember", "contacts", "Event_Consent_Status__c", "event_consent_status", "static", "Pending", "pending", "Eligible", "eligible"),
    "dahlia-role-account": _a("CampaignMember", "contacts", "Mailbox_Type_Status__c", "mailbox_type_status", "static", "Unreviewed", "unreviewed", "Removed", "removed"),
    "eucalyptus-frequency-cap": _a("CampaignMember", "contacts", "Frequency_Cap_Status__c", "frequency_cap_status", "static", "Within Cap", "within_cap", "Paused", "paused"),

    # Cutover audit
    "fjord-phase-one-cutover": _a("Opportunity", "deals", "Association_Migration_Status__c", "association_migration_status", "static", "Missing", "missing", "Restored", "restored"),
    "glacier-stage-map": _a("Opportunity", "deals", "StageName", "dealstage", "static", "Qualification", "qualification", "Discovery", "discovery"),
    "hemlock-owner-migration": _a("Opportunity", "deals", "OwnerId", "hubspot_owner_id", "owner", "00GQUEUE", "unassigned"),
    "isotope-activity-counts": _a("Opportunity", "deals", "Activity_Count_Status__c", "activity_count_status", "static", "Unreconciled", "unreconciled", "Reconciled", "reconciled"),
    "kestrel-line-item-cutover": _a("Opportunity", "deals", "Line_Item_Migration_Status__c", "line_item_migration_status", "static", "Missing", "missing", "Restored", "restored"),
    "lagoon-consent-cutover": _a("Opportunity", "deals", "Consent_Migration_Status__c", "consent_migration_status", "static", "Legacy", "legacy", "Restricted", "restricted"),
    "meadow-gong-linkage": _a("Opportunity", "deals", "HubSpot_Deal_ID__c", "salesforce_opportunity_id", "cross_id", "", ""),
    "northstar-custom-fields": _a("Opportunity", "deals", "Risk_Field_Migration_Status__c", "risk_field_migration_status", "static", "Pending", "pending", "Accepted", "accepted"),
    "orchard-delta-load": _a("Opportunity", "deals", "Delta_Load_Status__c", "delta_load_status", "static", "Unreconciled", "unreconciled", "Reconciled", "reconciled"),
    "pebble-rollback-readiness": _a("Opportunity", "deals", "Rollback_Exception_Status__c", "rollback_exception_status", "static", "Open", "open", "Cleared", "cleared"),
}


VALID_VALUE_KINDS = {"static", "date", "amount", "owner", "risk", "signal", "role", "cross_id", "account"}


def validate_action_specs(slugs: set[str]) -> None:
    missing = slugs - set(ACTION_SPECS)
    extra = set(ACTION_SPECS) - slugs
    invalid = {
        slug: spec.value_kind
        for slug, spec in ACTION_SPECS.items()
        if spec.value_kind not in VALID_VALUE_KINDS
    }
    if missing or extra or invalid:
        raise ValueError(
            f"invalid action specs: missing={sorted(missing)}, extra={sorted(extra)}, invalid={invalid}"
        )
