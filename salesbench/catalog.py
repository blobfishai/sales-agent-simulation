"""Hand-authored business spines for SalesBench-100.

Generation supplies deterministic records, artifacts, and distractors, but the
business request behind each task is written here.  Keeping one hundred distinct
spines prevents the release from becoming one template with swapped names.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TaskSpine:
    family: str
    slug: str
    title: str
    company: str
    industry: str
    region: str
    period: str
    requester: str
    narrative: str


FAMILY_SETTINGS: dict[str, dict[str, object]] = {
    "forecast-reconciliation": {
        "label": "forecast reconciliation and commit inspection",
        "requester": "VP of Revenue Operations",
        "folders": [
            "01_salesforce_pipeline", "02_hubspot_deals", "03_gong_briefs",
            "04_call_evidence", "05_forecast_snapshots", "06_rep_commits",
            "07_stage_policy", "08_close_plans", "09_finance_actuals",
            "10_territories", "11_exceptions", "12_deliverables",
        ],
        "mutation": "forecast-and-next-step repair",
    },
    "pipeline-recovery": {
        "label": "stalled-pipeline cleanup and next-step recovery",
        "requester": "Regional Sales Director",
        "folders": [
            "01_open_opportunities", "02_stage_history", "03_hubspot_activity",
            "04_gong_deal_questions", "05_next_steps", "06_calendar",
            "07_owner_roster", "08_slippage", "09_support_risks",
            "10_playbooks", "11_exclusions", "12_deliverables",
        ],
        "mutation": "targeted follow-up creation",
    },
    "gong-action-reconciliation": {
        "label": "Gong-to-CRM discovery and action-item reconciliation",
        "requester": "Sales Enablement Director",
        "folders": [
            "01_gong_calls", "02_gong_briefs", "03_salesforce_activities",
            "04_hubspot_engagements", "05_commitments", "06_stakeholders",
            "07_objections", "08_competitors", "09_followups",
            "10_evidence_policy", "11_private_calls", "12_deliverables",
        ],
        "mutation": "grounded activity and task sync",
    },
    "identity-migration": {
        "label": "duplicate detection, migration, and source-of-truth repair",
        "requester": "CRM Migration Lead",
        "folders": [
            "01_salesforce_accounts", "02_hubspot_companies", "03_contacts",
            "04_domains", "05_external_ids", "06_associations",
            "07_merge_history", "08_sync_failures", "09_source_rules",
            "10_consent", "11_do_not_merge", "12_deliverables",
        ],
        "mutation": "cross-CRM identity repair",
    },
    "lead-routing": {
        "label": "lead qualification, enrichment, and territory routing",
        "requester": "Global SDR Operations Manager",
        "folders": [
            "01_inbound_leads", "02_hubspot_contacts", "03_salesforce_leads",
            "04_gong_history", "05_account_matches", "06_territories",
            "07_scoring_policy", "08_consent", "09_owner_capacity",
            "10_disqualifiers", "11_routing_audit", "12_deliverables",
        ],
        "mutation": "qualified-lead routing",
    },
    "renewal-expansion": {
        "label": "renewal, expansion, and customer-success handoff",
        "requester": "Chief Customer Officer",
        "folders": [
            "01_contracts", "02_subscriptions", "03_salesforce_renewals",
            "04_hubspot_health", "05_gong_account_voice", "06_support",
            "07_usage", "08_notice_windows", "09_expansion_signals",
            "10_handoff_policy", "11_risks", "12_deliverables",
        ],
        "mutation": "renewal and expansion handoff",
    },
    "quote-governance": {
        "label": "discount approval, quote governance, and close readiness",
        "requester": "Deal Desk Director",
        "folders": [
            "01_opportunities", "02_quotes", "03_line_items",
            "04_discount_matrix", "05_approvals", "06_gong_commercials",
            "07_hubspot_deals", "08_legal_status", "09_finance_checks",
            "10_close_plan", "11_exceptions", "12_deliverables",
        ],
        "mutation": "policy-compliant quote progression",
    },
    "account-planning": {
        "label": "account planning, stakeholder mapping, and executive preparation",
        "requester": "Strategic Accounts Vice President",
        "folders": [
            "01_accounts", "02_opportunities", "03_contacts",
            "04_gong_briefs", "05_org_charts", "06_engagement",
            "07_products", "08_competition", "09_support",
            "10_white_space", "11_account_plan_policy", "12_deliverables",
        ],
        "mutation": "stakeholder and account-plan update",
    },
    "sequence-compliance": {
        "label": "sequence, consent, deliverability, and activity compliance",
        "requester": "Revenue Compliance Manager",
        "folders": [
            "01_sequences", "02_enrollments", "03_contacts",
            "04_consent", "05_suppressions", "06_email_events",
            "07_domains", "08_salesforce_campaigns", "09_hubspot_workflows",
            "10_regional_policy", "11_exceptions", "12_deliverables",
        ],
        "mutation": "consent-safe sequence remediation",
    },
    "cutover-audit": {
        "label": "cross-CRM cutover and post-migration reconciliation",
        "requester": "Enterprise Applications Director",
        "folders": [
            "01_cutover_plan", "02_salesforce_extract", "03_hubspot_extract",
            "04_field_mapping", "05_owner_mapping", "06_stage_mapping",
            "07_activity_counts", "08_gong_links", "09_error_queue",
            "10_acceptance_rules", "11_rollbacks", "12_deliverables",
        ],
        "mutation": "post-cutover exception resolution",
    },
}


_ROWS = """
forecast-reconciliation|northwind-q3-commit|Northwind Q3 commit inspection|Northwind Grid Systems|energy software|North America|2026-Q3|VP of Revenue Operations|The board forecast includes channel deals whose Salesforce stages moved forward while HubSpot still shows unsigned evaluations; Gong records reveal which buyers actually confirmed procurement dates.
forecast-reconciliation|velora-emea-rollup|Velora EMEA rollup repair|Velora Mobility|fleet technology|EMEA|2026-Q3|EMEA Revenue Operations Lead|A regional rollup double-counts German reseller opportunities after a HubSpot-to-Salesforce sync retry, and three late Gong calls change whether the deals belong in commit or upside.
forecast-reconciliation|harborstone-public-sector|Harborstone public-sector forecast audit|Harborstone Cloud|government cloud|United States Public Sector|2026-Q4|Public Sector Sales COO|Federal opportunities use milestone-based stages, but the weekly forecast treated contract vehicle access as an award; validate agency timing and separate funded work from speculative extensions.
forecast-reconciliation|cedarline-midmarket|Cedarline mid-market forecast scrub|Cedarline Analytics|business intelligence|North America|2026-Q3|Mid-Market Sales Director|A manager bulk-updated close dates before QBR. Reconstruct the defensible forecast from stage history, buyer commitments, rep notes, and finance-recognized bookings without undoing legitimate renewals.
forecast-reconciliation|atlas-apac-currency|Atlas APAC currency-normalized forecast|Atlas Robotics|industrial automation|APAC|2026-Q3|APAC Finance Business Partner|HubSpot stores local-currency amounts while Salesforce carries converted ACV at inconsistent FX dates; reconcile the portfolio using the quarter's approved rates and exclude services from subscription ARR.
forecast-reconciliation|lattice-partner-overlay|Lattice partner-overlay de-duplication|Lattice Security|cybersecurity|Global Channels|2026-Q4|Channel Chief|Partner-sourced opportunities appear once under the reseller and again under a direct account. Gong names the end customer, and the source-of-truth policy determines which record owns forecast credit.
forecast-reconciliation|meridian-usage-expansion|Meridian usage-expansion outlook|Meridian Data Fabric|data infrastructure|North America|2026-Q4|Chief Revenue Officer|Expansion opportunities were opened from product-usage alerts, but only accounts with an identified economic buyer and scheduled validation call may enter upside; several stale alerts should remain pipeline only.
forecast-reconciliation|opal-healthcare-commit|Opal healthcare commit certification|Opal Clinical Network|healthcare IT|United States|2026-Q3|Healthcare Sales VP|Hospital deals cross fiscal years and contain conditional security reviews. Determine which signatures and approvals are real blockers rather than generic CRM flags and certify only executable quarter-end commits.
forecast-reconciliation|quarry-enterprise-split|Quarry enterprise split-credit reconciliation|Quarry Compute|cloud infrastructure|North America|2026-Q3|Sales Compensation Director|Parent and subsidiary opportunities share a procurement event, but overlay and account executives recorded incompatible split credit. Reconcile forecast value without changing compensation allocations not covered by the request.
forecast-reconciliation|solstice-fiscal-boundary|Solstice fiscal-boundary forecast reset|Solstice Learning|education technology|Global|FY2027-Q1|Revenue Accounting Manager|The company changed fiscal calendars after CRM records were created. Normalize close dates and stage probabilities to the new boundary while preserving already-booked deals and documenting all excluded rows.
pipeline-recovery|acorn-stalled-enterprise|Acorn stalled-enterprise recovery|Acorn Payments|payments|North America|2026-Q3|Regional Sales Director|Large open opportunities passed their close dates, but owners who already reached quota are excluded from QBR follow-up. Create targeted tasks only where Gong shows an unresolved buyer action.
pipeline-recovery|brightwell-trial-expiry|Brightwell trial-expiry rescue|Brightwell Observability|developer tools|North America|2026-Q3|Commercial Sales VP|Product trials expired without a next meeting. Separate deliberate no-decisions from administrative CRM neglect and schedule follow-up only when the prospect committed to a technical validation step.
pipeline-recovery|cinder-manufacturing-slips|Cinder manufacturing slippage review|Cinder Logistics|supply-chain software|EMEA|2026-Q4|EMEA Sales Director|Plant shutdown calendars pushed implementation dates, while reps repeatedly moved CRM close dates without updating mutual action plans. Flag deals where buyer timing and current stage are materially inconsistent.
pipeline-recovery|drift-renewal-blockers|Driftwood renewal blocker cleanup|Driftwood Media Systems|media technology|North America|2026-Q3|Renewals Director|Renewal opportunities lack next steps even though Gong captured pricing objections and service incidents. Create one owned recovery task per actionable blocker and leave accounts already in formal notice untouched.
pipeline-recovery|ember-champion-departures|Ember champion-departure response|Ember Bioinformatics|life sciences software|Global|2026-Q4|Strategic Sales Director|Several champions changed employers. Use CRM contact status, bounced HubSpot activity, and Gong stakeholder mentions to identify deals needing relationship rebuilding rather than routine cadence reminders.
pipeline-recovery|fable-procurement-pauses|Fable procurement-pause triage|Fable Workspace|collaboration software|APAC|2026-Q3|APAC Sales Director|Procurement paused a subset of expansion deals during budget review. Distinguish explicit holds from silent deals, assign the right recovery motion, and avoid tasks on opportunities with documented customer-requested pauses.
pipeline-recovery|granite-security-reviews|Granite security-review acceleration|Granite Commerce|commerce platform|North America|2026-Q4|Enterprise Sales VP|Security questionnaires are scattered across activities and call briefs. Identify opportunities truly blocked on vendor action and create tasks for the responsible specialist, not the account executive by default.
pipeline-recovery|helix-multi-threading|Helix single-thread risk recovery|Helix Factory AI|industrial AI|EMEA|2026-Q4|Regional VP Sales|Late-stage deals depend on one contact despite larger buying committees discussed in calls. Add stakeholder-development tasks only where the evidence identifies a missing role and no equivalent task is open.
pipeline-recovery|indigo-next-step-aging|Indigo next-step aging cleanup|Indigo Treasury|fintech|North America|2026-Q3|Sales Operations Manager|CRM next-step dates are current but copied forward verbatim for weeks. Use field history and Gong commitments to find false freshness and replace only the affected follow-up tasks.
pipeline-recovery|juniper-partner-handoffs|Juniper partner-handoff recovery|Juniper Field Service|field operations software|Global Channels|2026-Q3|Channel Operations Director|Reseller-owned deals stalled after demo handoffs. Recover the correct direct and partner owners from territory rules, create coordinated tasks, and avoid reassigning the underlying opportunity.
gong-action-reconciliation|keystone-discovery-actions|Keystone discovery action reconciliation|Keystone Ledger|accounting software|North America|2026-Q3|Sales Enablement Director|Discovery calls contain buyer and seller commitments that never reached either CRM. Reconcile each grounded action into the designated system without copying private-call content.
gong-action-reconciliation|lumen-exec-briefs|Lumen executive briefing sync|Lumen Care Platform|healthcare software|North America|2026-Q4|Executive Programs Lead|Prepare executive meetings from Gong briefs, correct stale stakeholder roles in Salesforce, and add HubSpot tasks for explicit follow-ups while excluding speculative risks from raw rep notes.
gong-action-reconciliation|monarch-competitor-mentions|Monarch competitor evidence audit|Monarch DevOps|developer infrastructure|Global|2026-Q3|Competitive Intelligence Lead|Competitor fields were populated from marketing attribution rather than buyer conversations. Use Gong evidence to correct only deals with explicit competitive mentions and retain unknowns elsewhere.
gong-action-reconciliation|nova-mutual-plans|Nova mutual-plan commitment sync|Nova Identity|identity security|EMEA|2026-Q4|Enterprise Enablement VP|Mutual action plans disagree with the latest calls. Update dated CRM next steps for commitments accepted by both sides and create tasks for seller-owned actions, preserving buyer-owned items as notes.
gong-action-reconciliation|orbit-objection-coding|Orbit objection taxonomy repair|Orbit Manufacturing Cloud|manufacturing SaaS|North America|2026-Q3|Revenue Intelligence Manager|Reps used a generic loss-reason code for active deals. Classify only objections supported by Gong's account and deal insight tools and leave closed-lost reason governance outside scope.
gong-action-reconciliation|palisade-handoff-notes|Palisade SDR-to-AE handoff audit|Palisade Risk|risk management|North America|2026-Q3|SDR Enablement Manager|SDR discovery notes, Gong call outcomes, and CRM qualification fields conflict. Produce grounded handoffs and repair missing qualification fields without overwriting AE-entered commercial data.
gong-action-reconciliation|quill-coaching-actions|Quill coaching-action follow-through|Quill Customer Data|customer data platform|Global|2026-Q3|Sales Coaching Director|Call scorecards identified specific rep behaviors and customer follow-ups. Create customer-facing tasks only for explicit commitments; coaching-only observations belong in the deliverable, not the CRM.
gong-action-reconciliation|ridgeway-call-privacy|Ridgeway call-privacy boundary audit|Ridgeway Networks|networking|EMEA|2026-Q4|Revenue Compliance Counsel|A mixture of public and private Gong calls supports a deal review. Use only permitted synthesized insights, document exclusions, and ensure no private transcript fragment is copied into either CRM.
gong-action-reconciliation|summit-commercial-terms|Summit commercial-term capture|Summit Compute|cloud compute|North America|2026-Q4|Deal Strategy Director|Calls contain agreed pricing guardrails and unresolved legal points. Update commercial next steps and risk codes without treating discussion as approval or changing quote amounts.
gong-action-reconciliation|tandem-contact-roles|Tandem buying-role reconciliation|Tandem Procurement AI|procurement technology|APAC|2026-Q3|Strategic Enablement Lead|Gong names economic buyers, champions, blockers, and evaluators differently from CRM roles. Repair supported contact roles and create gap tasks while preserving manually verified opt-out contacts.
identity-migration|umbra-domain-collisions|Umbra domain-collision cleanup|Umbra Energy Markets|energy trading|Global|2026-Q3|CRM Migration Lead|Two unrelated companies share a parent email domain after an acquisition. Resolve duplicates using legal names, external IDs, and Gong account references without merging the carved-out subsidiary.
identity-migration|vector-contact-dedup|Vector contact duplicate repair|Vector Service Cloud|customer service software|North America|2026-Q3|Data Quality Director|Contacts were re-created during webinar imports with changed titles and consent. Link or repair exact identities while preserving the most restrictive consent and the latest verified employment.
identity-migration|willow-parent-child|Willow hierarchy reconstruction|Willow Construction Tech|construction software|North America|2026-Q4|Enterprise Systems Manager|HubSpot companies flatten regional subsidiaries while Salesforce uses a parent hierarchy. Reconcile associations and external IDs without moving open opportunities between legal buyers.
identity-migration|xenon-owner-crosswalk|Xenon owner crosswalk correction|Xenon Materials|advanced materials|EMEA|2026-Q3|Sales Systems Lead|Departed reps and renamed teams caused owner sync failures. Apply the approved crosswalk to active records, leave historical activity ownership intact, and report unmapped owners.
identity-migration|yellowbrick-lifecycle-sync|Yellowbrick lifecycle-stage repair|Yellowbrick Learning|education software|Global|2026-Q4|Marketing Operations VP|HubSpot lifecycle stages advanced from campaigns while Salesforce lead conversions lagged. Reconcile only identities with valid conversion evidence and do not recreate already converted leads.
identity-migration|zenith-external-id-gaps|Zenith external-ID backfill|Zenith Aviation Systems|aviation software|North America|2026-Q3|Integration Product Manager|A deployment omitted cross-system IDs for a portfolio of accounts. Backfill matches supported by domain and address evidence; quarantine ambiguous names instead of guessing.
identity-migration|alpine-acquisition-merge|Alpine acquisition account migration|Alpine Supply Chain|logistics software|Europe|2026-Q4|M&A Systems Lead|An acquired CRM contains legacy company records that overlap existing Salesforce accounts. Preserve separate contracts and Gong history while consolidating safe marketing identities in HubSpot.
identity-migration|brookfield-consent-survival|Brookfield consent-preserving deduplication|Brookfield Data Services|data services|North America|2026-Q3|Privacy Operations Manager|Duplicate contacts carry contradictory subscription states. Merge identity links only when evidence is strong and propagate the strictest valid suppression without deleting audit history.
identity-migration|cascade-custom-object-map|Cascade custom-object relationship repair|Cascade MedTech|medical technology|United States|2026-Q4|CRM Architecture Lead|Implementation-site custom objects lost company associations during migration. Restore relationships from external keys and deployment documents without modifying regulated device records.
identity-migration|delta-sandbox-cutover|Delta sandbox-to-production identity audit|Delta Workforce|workforce software|Global|2026-Q3|Release Manager|Test identifiers leaked into production mappings for a subset of deals and contacts. Repair production associations from approved manifests and leave all rows lacking a signed cutover record untouched.
lead-routing|everest-enterprise-inbound|Everest enterprise inbound routing|Everest Data Lake|data infrastructure|North America|2026-Q3|Global SDR Operations Manager|High-value inbound leads span named accounts and whitespace territories. Qualify from firmographics and activity, route by approved rules, and avoid reassignment where an active opportunity already establishes ownership.
lead-routing|foxtrot-emea-consent|Foxtrot EMEA consent-aware routing|Foxtrot Automation|automation software|EMEA|2026-Q3|EMEA SDR Director|Event leads include mixed lawful-basis and country data. Route eligible buyers, suppress prohibited outreach, and quarantine contacts whose consent evidence conflicts across imports.
lead-routing|ginkgo-product-led|Ginkgo product-led sales handoff|Ginkgo API Platform|developer platform|Global|2026-Q4|Product-Led Growth Director|Usage-qualified accounts generated multiple contacts and free-email signups. Group identities, identify the buying organization, and create sales handoffs only above the documented product threshold.
lead-routing|highland-public-sector|Highland public-sector territory routing|Highland Security|cybersecurity|United States Public Sector|2026-Q3|Public Sector SDR Manager|Agency and contractor leads overlap federal territories. Route by ultimate agency and contract vehicle, respecting protected named accounts and partner-origin rules.
lead-routing|ion-health-system|Ion health-system lead qualification|Ion Patient Access|healthcare technology|United States|2026-Q4|Healthcare Growth VP|Hospital campuses submit separate forms but buy centrally. Consolidate qualification at the health-system level, preserve campus contacts, and route by the executive account hierarchy.
lead-routing|jasper-apac-capacity|Jasper APAC capacity-balanced routing|Jasper Logistics AI|logistics technology|APAC|2026-Q3|APAC SDR Operations Lead|Territory rules yield multiple eligible owners, but weekly capacity limits and language coverage break ties. Assign only qualified leads and record why overflow moved to the pooled queue.
lead-routing|kinetic-partner-sourced|Kinetic partner-sourced lead routing|Kinetic Payments|payments|Global Channels|2026-Q4|Partner Sales Operations|Partner referrals claim account protection inconsistently. Validate registration windows and existing opportunity ownership before choosing partner, direct, or conflict-review routing.
lead-routing|lowell-duplicate-mqls|Lowell duplicate-MQL suppression|Lowell Compliance Cloud|compliance software|North America|2026-Q3|Demand Generation Operations|Campaign retries created repeated MQLs for the same people. Preserve attribution history, consolidate routing, and prevent duplicate sales tasks while respecting recent disqualifications.
lead-routing|mosaic-intent-threshold|Mosaic intent-threshold qualification|Mosaic Retail AI|retail technology|North America|2026-Q4|ABM Operations Director|Third-party intent surges disagree with first-party engagement. Apply the documented threshold and named-account rules, excluding accounts whose activity is entirely anonymous.
lead-routing|nimbus-student-exclusion|Nimbus education persona filtering|Nimbus Campus Systems|education technology|Global|2026-Q3|Inbound Operations Manager|A product launch attracted students, consultants, and institutional buyers. Qualify and route real buying roles while retaining nonbuyers for marketing analytics without creating sales records.
renewal-expansion|oak-renewal-notice|Oak renewal notice recovery|Oak Infrastructure|infrastructure software|North America|2026-Q4|Chief Customer Officer|Contract notice windows, CRM renewal dates, and HubSpot health fields disagree. Create recovery actions for accounts still inside a cure window and escalate already-missed notices separately.
renewal-expansion|prairie-usage-expansion|Prairie usage-led expansion|Prairie Analytics|analytics|North America|2026-Q3|Expansion Sales VP|Usage exceeds contracted capacity for several accounts, but support severity and Gong sentiment determine whether to open expansion motions or customer-success recovery plans.
renewal-expansion|quartz-multi-product|Quartz multi-product renewal consolidation|Quartz Security|security software|Global|2026-Q4|Renewals Operations Director|Separate product opportunities refer to one co-termed agreement. Consolidate the renewal view, preserve product line detail, and avoid double-counting ARR.
renewal-expansion|redwood-churn-save|Redwood churn-save handoff|Redwood Collaboration|collaboration software|EMEA|2026-Q3|Customer Success VP|Gong identifies executive dissatisfaction while HubSpot health remains green. Create evidence-grounded save actions and update renewal risk without marking churn as certain.
renewal-expansion|sequoia-merger-renewals|Sequoia acquired-account renewals|Sequoia Finance Cloud|financial software|North America|2026-Q4|Strategic Renewals Lead|A customer merger changed billing entities and stakeholders. Link successor accounts, preserve contract notice obligations, and assign one coordinated renewal owner.
renewal-expansion|timberline-support-risk|Timberline support-risk expansion gate|Timberline Field Ops|field service software|APAC|2026-Q3|Customer Growth Director|Sales proposed an expansion despite unresolved priority incidents. Gate the motion according to support policy and schedule executive recovery tasks before commercial follow-up.
renewal-expansion|upland-channel-renewal|Upland channel renewal alignment|Upland Identity|identity software|Global Channels|2026-Q4|Channel Renewals Director|Distributor records and direct CRM renewals show different end dates. Reconcile using executed documents and leave partner compensation decisions outside the data repair.
renewal-expansion|vista-auto-renewal|Vista auto-renewal exception review|Vista Commerce|commerce software|North America|2026-Q3|Commercial Operations Counsel|Auto-renewal records include customers with negotiated opt-outs and superseding amendments. Correct opportunity timing and create notices only from controlling terms.
renewal-expansion|watershed-seat-trueup|Watershed seat true-up preparation|Watershed HR Tech|HR software|Global|2026-Q4|Account Management VP|Active seats exceed contracted bands, but dormant and sandbox users are excluded. Calculate grounded true-up candidates and open opportunities only where the policy and usage evidence agree.
renewal-expansion|yarrow-executive-handoff|Yarrow executive sponsor handoff|Yarrow Supply Network|supply-chain platform|EMEA|2026-Q3|Executive Programs Director|Account leadership changed during renewal. Update supported stakeholder roles, create sponsor-introduction tasks, and preserve contacts whose role is unverified.
quote-governance|zephyr-discount-chain|Zephyr discount approval chain|Zephyr Compute|cloud infrastructure|North America|2026-Q3|Deal Desk Director|Quotes over multiple discount and TCV thresholds require ordered approvals. Progress only quotes with complete evidence and never treat a Gong pricing discussion as approval.
quote-governance|amber-ramp-pricing|Amber ramp-pricing validation|Amber Data Cloud|data platform|North America|2026-Q4|Pricing Operations VP|A multi-year ramp has conflicting annual quantities between Salesforce and HubSpot. Reconcile the signed commercial schedule before calculating the effective discount.
quote-governance|birch-public-sector-terms|Birch public-sector quote readiness|Birch Cyber Defense|cybersecurity|United States Public Sector|2026-Q3|Public Sector Deal Desk|Government quotes combine mandatory clauses, reseller margins, and funding limits. Flag unready deals and progress only those with valid vehicle and approval evidence.
quote-governance|coral-nonstandard-payment|Coral nonstandard payment-term review|Coral Bio Cloud|life sciences technology|Global|2026-Q4|Finance Deal Desk Lead|Reps offered extended terms in calls, but finance approval exists for only some opportunities. Update risk and tasks without changing quote terms that lack formal authorization.
quote-governance|dogwood-bundle-floor|Dogwood bundle-floor audit|Dogwood Developer Tools|developer software|North America|2026-Q3|Commercial Strategy Director|Bundled SKUs obscure product-level discount floors. Validate line items and exception approvals, correct close-readiness fields, and leave pricing math intact where source records conflict.
quote-governance|elm-partner-margin|Elm partner-margin reconciliation|Elm Network Systems|network software|EMEA|2026-Q4|Channel Deal Desk Manager|Distributor margin, end-customer discount, and Salesforce quote discount are conflated. Separate them using partner documents and route only genuine policy exceptions.
quote-governance|fir-usage-commit|Fir usage-commit approval audit|Fir AI Platform|AI infrastructure|Global|2026-Q3|Strategic Pricing Lead|Consumption commitments carry make-good clauses and variable credits. Determine approval requirements from normalized commitment value rather than headline maximums.
quote-governance|grove-currency-lock|Grove currency-lock validation|Grove Treasury Systems|treasury software|APAC|2026-Q4|International Deal Desk|Quotes use stale currency locks after close dates slipped. Flag affected offers, create repricing tasks, and preserve formally extended locks.
quote-governance|hawthorn-legal-gate|Hawthorn legal-gate close review|Hawthorn Health Data|health data software|United States|2026-Q3|Chief Commercial Counsel|CRM marks deals contract-complete despite open privacy terms. Reconcile legal status and Gong commitments, but do not change opportunity stage or quote status without executed language.
quote-governance|ironwood-order-form|Ironwood order-form consistency audit|Ironwood Manufacturing Cloud|manufacturing SaaS|Global|2026-Q4|Quote-to-Cash Director|Order forms, quote lines, and CRM amounts diverge after amendments. Identify controlling values, repair readiness metadata, and create one exception task per unsupported discrepancy.
account-planning|jade-global-account|Jade global-account plan refresh|Jade Communications|communications software|Global|2026-Q3|Strategic Accounts Vice President|A global customer has regional opportunities, fragmented contacts, and conflicting priorities. Build one evidence-grounded stakeholder map while preserving regional ownership.
account-planning|kingfisher-exec-map|Kingfisher executive stakeholder map|Kingfisher Energy Tech|energy technology|North America|2026-Q4|Executive Accounts Director|Gong reveals an economic buyer and two blockers absent from CRM roles. Update only supported roles and create relationship tasks for uncovered functions.
account-planning|laurel-white-space|Laurel product white-space analysis|Laurel Financial Systems|financial software|EMEA|2026-Q3|Account Growth VP|Product adoption and opportunity history show expansion gaps, but support escalations constrain outreach. Record qualified whitespace and defer motions for accounts under recovery.
account-planning|maple-partner-ecosystem|Maple partner ecosystem plan|Maple Industrial IoT|industrial technology|Global Channels|2026-Q4|Alliance Sales VP|Consultants, integrators, and a reseller influence one buying committee. Reconcile their roles and create coordinated tasks without converting partner contacts into customer employees.
account-planning|nutmeg-contact-coverage|Nutmeg buying-committee coverage audit|Nutmeg Workforce|workforce technology|North America|2026-Q3|Enterprise Sales Enablement|Late-stage accounts lack security and procurement contacts. Use Gong themes and existing associations to identify role gaps without fabricating people.
account-planning|olive-support-overlay|Olive support-aware account plan|Olive Commerce Data|commerce analytics|APAC|2026-Q4|Strategic Account Director|Expansion potential is high, but open incidents and adoption gaps change the executive message. Update plan risks and tasks using both support and conversation evidence.
account-planning|pine-competitive-plan|Pine competitive account strategy|Pine Observability|observability|Global|2026-Q3|Competitive Sales Strategy Lead|CRM competitor fields and call evidence conflict across a portfolio. Correct supported entries and produce grounded counter-positioning actions without copying internal-only battlecard claims as customer facts.
account-planning|riverbank-succession|Riverbank stakeholder succession plan|Riverbank Payments|payments|North America|2026-Q4|Key Accounts VP|A sponsor departed and responsibilities split among successors. Repair contact roles and outreach tasks while retaining the departed contact's historical activities.
account-planning|spruce-board-prep|Spruce board-meeting account preparation|Spruce Logistics|logistics software|North America|2026-Q3|Chief Revenue Officer|Prepare a board-level view of top accounts from fragmented CRM and Gong evidence. Update only operational next steps; the narrative deliverable must distinguish fact, inference, and unresolved conflict.
account-planning|topaz-regional-org|Topaz regional organization mapping|Topaz Healthcare Cloud|healthcare IT|EMEA|2026-Q4|Global Account Programs Lead|Country contacts report into a central procurement team, but CRM associations are flat. Restore evidence-backed hierarchy links and list unresolved reporting lines without guessing.
sequence-compliance|umber-gdpr-sequence|Umber GDPR sequence remediation|Umber DevSecOps|security software|EMEA|2026-Q3|Revenue Compliance Manager|An outbound sequence enrolled contacts with mixed consent and legitimate-interest records. Remove prohibited enrollments, preserve audit evidence, and create no replacement outreach tasks.
sequence-compliance|violet-suppression-sync|Violet suppression-list reconciliation|Violet Commerce|commerce platform|North America|2026-Q4|Marketing Systems Director|Global and portal-specific suppressions drifted across HubSpot and Salesforce campaigns. Apply the strictest current status without suppressing transactional contacts outside scope.
sequence-compliance|walnut-domain-health|Walnut domain-health response|Walnut Analytics|analytics software|Global|2026-Q3|Sales Engagement Operations|Bounce spikes affect two sending domains and only certain sequence cohorts. Pause impacted enrollments and create remediation tasks without editing unrelated CRM lifecycle stages.
sequence-compliance|xylem-cadence-overlap|Xylem cadence-overlap cleanup|Xylem Field Service|field service software|North America|2026-Q4|SDR Operations Director|Contacts are active in overlapping prospecting and event follow-up sequences. Keep the policy-preferred motion and remove duplicates while preserving completed activity history.
sequence-compliance|yucca-country-policy|Yucca country-policy enforcement|Yucca Finance AI|fintech|Global|2026-Q3|International Compliance Lead|Regional contact rules changed mid-quarter. Evaluate enrollment dates, countries, and consent versions before changing current sequence membership.
sequence-compliance|azalea-customer-exclusion|Azalea customer-exclusion audit|Azalea Data Security|data security|North America|2026-Q4|Customer Marketing Operations|Existing customers entered acquisition sequences because company associations were missing. Repair associations and remove only confirmed customers, not prospects sharing parent domains.
sequence-compliance|bluebell-reply-stop|Bluebell reply-stop enforcement|Bluebell Productivity|productivity software|Global|2026-Q3|Sales Automation Manager|Positive and negative replies failed to stop follow-up steps in one integration window. Cancel remaining enrollments, create response tasks where appropriate, and avoid reopening completed work.
sequence-compliance|clover-event-consent|Clover event-consent reconciliation|Clover Health Analytics|health analytics|EMEA|2026-Q4|Field Marketing Compliance|Event scans, registration choices, and CRM consent fields disagree. Enroll only eligible attendees and quarantine ambiguous records for review.
sequence-compliance|dahlia-role-account|Dahlia role-account outreach guard|Dahlia Procurement|procurement software|APAC|2026-Q3|Regional Marketing Operations|Generic role accounts and personal buyers were mixed during enrichment. Remove non-person mailboxes and duplicates while retaining valid opted-in individuals.
sequence-compliance|eucalyptus-frequency-cap|Eucalyptus frequency-cap audit|Eucalyptus Cloud Cost|cloud management|North America|2026-Q4|Lifecycle Operations VP|Multiple teams contacted the same people above the documented weekly cap. Stop excess enrollments, preserve the highest-priority active motion, and record conflicts for owner review.
cutover-audit|fjord-phase-one-cutover|Fjord phase-one CRM cutover audit|Fjord Risk Platform|risk software|North America|2026-Q3|Enterprise Applications Director|The first migration wave moved accounts and contacts but missed associations and activities. Resolve deterministic mapping errors and quarantine rows with no approved source key.
cutover-audit|glacier-stage-map|Glacier stage-mapping validation|Glacier Revenue Cloud|revenue software|Global|2026-Q4|CRM Program Director|HubSpot and Salesforce stage models were collapsed during cutover. Reapply the approved conditional mapping based on probability, exit evidence, and closed status.
cutover-audit|hemlock-owner-migration|Hemlock ownership migration audit|Hemlock Security Ops|security operations|EMEA|2026-Q3|Sales Systems Director|Team restructuring changed territory and owner IDs during migration. Repair active-record ownership from the signed crosswalk while preserving historical owners.
cutover-audit|isotope-activity-counts|Isotope activity-count reconciliation|Isotope Research Cloud|research software|North America|2026-Q4|Data Migration Assurance Lead|Activity totals differ because archived HubSpot engagements and private Gong calls were handled incorrectly. Reconcile allowed counts without importing private content.
cutover-audit|kestrel-line-item-cutover|Kestrel line-item cutover repair|Kestrel Manufacturing AI|manufacturing technology|APAC|2026-Q3|Quote-to-Cash Systems Lead|Opportunity headers migrated but selected HubSpot line items did not. Restore supported associations and values from the frozen manifest without changing pricing.
cutover-audit|lagoon-consent-cutover|Lagoon consent cutover certification|Lagoon Travel Systems|travel technology|Global|2026-Q4|Privacy Engineering Director|Subscription categories changed between systems. Map consent by purpose and timestamp, favor the more restrictive valid state, and retain source evidence.
cutover-audit|meadow-gong-linkage|Meadow Gong linkage repair|Meadow Service Platform|service software|North America|2026-Q3|Revenue Intelligence Administrator|Gong CRM references point to retired opportunity IDs after cutover. Repair CRM-side external links and task context without attempting to modify Gong.
cutover-audit|northstar-custom-fields|Northstar custom-field acceptance audit|Northstar Banking Cloud|banking software|United States|2026-Q4|Regulated Systems Owner|Required risk and regulatory fields were transformed inconsistently. Correct values only where mapping and source evidence agree, and produce an exception register for the rest.
cutover-audit|orchard-delta-load|Orchard delta-load reconciliation|Orchard Supply Cloud|supply-chain software|EMEA|2026-Q3|Migration Release Manager|Changes made during the freeze window were replayed twice or omitted. Compare timestamps and external IDs, remove deterministic duplicates, and preserve legitimate post-cutover edits.
cutover-audit|pebble-rollback-readiness|Pebble rollback-readiness certification|Pebble Education Cloud|education software|Global|2026-Q4|Business Systems VP|A go-live decision depends on unresolved record, owner, activity, and Gong-link exceptions. Repair in-scope defects, calculate acceptance status, and leave a deterministic rollback manifest.
""".strip()


def _parse_rows() -> tuple[TaskSpine, ...]:
    rows: list[TaskSpine] = []
    for line_number, line in enumerate(_ROWS.splitlines(), start=1):
        fields = [field.strip() for field in line.split("|")]
        if len(fields) != 9:
            raise ValueError(f"catalog line {line_number} has {len(fields)} fields")
        rows.append(TaskSpine(*fields))
    if len(rows) != 100:
        raise ValueError(f"expected 100 task spines, found {len(rows)}")
    slugs = [row.slug for row in rows]
    if len(slugs) != len(set(slugs)):
        raise ValueError("task slugs must be unique")
    expected_families = set(FAMILY_SETTINGS)
    observed_families = {row.family for row in rows}
    if observed_families != expected_families:
        raise ValueError(
            f"catalog family mismatch: expected {expected_families}, got {observed_families}"
        )
    for family in expected_families:
        count = sum(row.family == family for row in rows)
        if count != 10:
            raise ValueError(f"family {family} has {count} spines, expected 10")
    return tuple(rows)


TASK_SPINES = _parse_rows()

