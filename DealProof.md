DealProof
Product Requirements Document — Version 2.0

Product: DealProof
Tagline: Discover opportunities. Verify the evidence. Evaluate with confidence.
Category: AI-Native Investment Intelligence and Due Diligence
Date: 22 November 2026
Status: Product definition ready; technical feasibility and customer validation pending
Initial deployment: ContextCon 05, BITS Pilani
Long-term market: Investment firms, M&A advisory firms, corporate development teams and strategic acquirers

1. Executive Summary
1.1 Product Vision
DealProof is an AI-native investment research and decision-support platform that helps investors and acquirers discover businesses, independently investigate their claims, and evaluate opportunities against an investment thesis.
The platform integrates three stages traditionally handled through separate tools and manual research:
Discover → Diligence → Evaluate
Discover: Find companies matching a user's investment thesis using live company data, growth signals, funding history and industry information.
Diligence: Investigate selected businesses using Crustdata, company registries, public filings, trusted external sources and authorized uploaded documents. Verify specific claims, detect inconsistencies and identify missing evidence.
Evaluate: Combine investment-thesis fit, available operating indicators, verified facts, financial information where available, and unresolved risks into an explainable investment screening assessment.
DealProof does not autonomously determine whether a company will generate attractive investment returns.
Instead, it delivers the research and evaluation work needed to make a better-informed investment or acquisition decision.

1.2 Central Value Proposition
From an investment thesis to a defensible investment screening case, within one connected workflow.
The user should not need to separately search for companies, manually investigate each one, compare conflicting information, and build an investment memo.
DealProof performs those steps, identifies uncertainties, and prepares appropriate follow-up actions.

1.3 Product Differentiation

DealProof is inspired by two established product categories:
Dealroom.co: Company discovery, startup intelligence, market mapping and investment signals.
DealRoom.net: Acquisition pipelines, diligence coordination and transaction workflows.
The differentiation we propose is the connection between discovery, independent claim verification and transparent evaluation.

Key product principle
A company can be attractive while its claims remain unverified.
DealProof must preserve that distinction.
For example:
- A startup may strongly match an investor's sector and geography preferences.
- Its disclosed funding may be corroborated.
- Its reported annual revenue may be impossible to verify publicly.
- Its founder's employment history may be supported by professional records.
- Its valuation may be unattractive under the investor's assumptions.
- These are separate findings, not ingredients to blend into one unexplained AI score.

1.4 Long-Term Product Outcome
A completed DealProof case should contain:
- The business opportunity and its relevance to the user's thesis.
- A company profile and resolved identity.
- Material claims and their evidence.
- An assessment of operational and commercial indicators.
- Financial evaluation where reliable inputs exist.
- Explicit risks, assumptions and unknowns.
- Comparisons against relevant alternatives where possible.
- A recommendation for the next investigation or decision stage.
- Specific information requests required to resolve uncertainties.
- A reproducible audit trail.

2. Problem Definition

2.1 The Existing Investor Workflow

An investment analyst or corporate development professional may need to:
- Identify relevant industries or business categories.
- Search multiple databases for candidate companies.
- Build a longlist.
- Evaluate business models, stages and company sizes.
- Investigate founders and management teams.
- Analyze growth and organizational signals.
- Review funding announcements and transactions.
- Examine seller presentations.
- Independently verify material claims.
- Compare companies against investment criteria.
- Review available financial data.
- Identify potential risks and unresolved questions.
- Prepare investment-screening memoranda.
- Coordinate requests for supporting documents.
- Reevaluate opportunities when new evidence arrives.

Existing tools address parts of this workflow, but users may still need substantial manual work to connect findings into a decision.

2.2 Specific User Problems
Problem
Consequence

Product response

Company information is fragmented

Slow discovery and repeated research

Unified company search and research workflow

Companies are difficult to compare consistently

Subjective or inconsistent screening

Configurable investment evaluation criteria

Growth indicators are mistaken for actual traction

Overconfident conclusions

Distinguish observed signals from confirmed operating results

Seller presentations contain unverified claims

Important assumptions may go unquestioned

Claim-level diligence and evidence reconciliation

Similar names cause identity confusion

Wrong company or director records may be attached

Entity resolution and ambiguity handling

Financial information is missing

Valuations may rest on unsupported assumptions

Conditional financial analysis and explicit missing-data states

Reports take time to prepare

Analyst time spent on repetitive compilation

Automated evidence-backed screening memos

Missing information is not systematically followed up

Screening remains incomplete

Targeted evidence requests and tracked unresolved questions

2.3 Core Jobs to Be Done

JTBD A — Opportunity Discovery

"When I have an investment thesis, help me identify relevant companies and explain why they qualify, so I can decide which ones deserve further investigation."

JTBD B — Independent Verification

"When I receive information about a company, investigate the material claims against independent evidence and show what can and cannot be trusted."

JTBD C — Investment Evaluation

"When I have several opportunities, evaluate them consistently against my own criteria so I can determine which ones deserve a meeting, further diligence or deprioritization."

JTBD D — Evidence-Gap Resolution

"When a potentially important investment claim remains unverified, identify the exact evidence needed and help me request it safely."

3. Target Customers and ICP

3.1 Primary Commercial ICP

Boutique M&A advisory firms and corporate development teams conducting repeated acquisition-target screening.

Typical customer characteristics:

Screens several potential investment or acquisition targets each month.

Has a small analyst or corporate development team.

Uses external databases, documents and manual research.

Requires defensible evidence before communicating findings.

Needs repeatable screening reports.

Has a specific decision-maker who owns the research budget.

User persona

Role: Investment associate, corporate development analyst or M&A advisory associate.

Primary motivation: Reduce research effort while improving consistency and traceability.

Primary concern: Incorrect facts, unsupported investment recommendations, confidential-data exposure and reputational damage.

3.2 Secondary ICPs

Segment

Primary need

Product emphasis

Early-stage VC funds

Find startups aligned with an investment thesis

Discovery, founder research and traction signals

Private equity funds

Screen established businesses

Company diligence and financial assessment

Search funds

Research acquisition opportunities

Target discovery and first-pass diligence

Roll-up operators

Repeatedly assess acquisition targets

Strategic fit, comparables and reusable research

Family offices

Investigate private businesses

Evidence verification and decision support

Business brokers

Prepare credible company profiles

Seller-claim verification and evidence collection

3.3 ContextCon-Specific Customer

For the hackathon, the written brief specifies a mid-sized Indian third-party logistics company as the common client.

DealProof will serve its CFO or corporate development function.

Hackathon use case:

The company is considering acquiring or investing in regional logistics, transport, warehousing or supply-chain technology businesses.

The system helps identify suitable targets, investigate company claims and prepare an evidence-backed recommendation for a second meeting.

This must be reconciled with the actual kickoff request and the organizer's latest instructions.

A new product theme does not automatically waive the common-client requirement.

4. Product Structure

DealProof has three primary product modules and one shared service layer.

4.1 Module A — Discover

Purpose: Identify and shortlist relevant investment opportunities.

User inputs

Free-text investment thesis

Industry or sector

Geography

Company type

Business model

Investment stage

Company size

Funding history or funding stage

Target investment amount, if relevant

Growth requirements

Specific technologies or business capabilities

Exclusion criteria

Optional strategic-acquisition requirements

Example

"Find privately held Indian warehousing and supply-chain software companies that serve enterprise customers, have evidence of recent expansion, and could be relevant to a regional 3PL acquisition strategy."

Agent behavior

Interpret the investment thesis.

Extract measurable screening criteria.

Distinguish mandatory requirements from preferences.

Ask for clarification only when a missing criterion prevents a meaningful search.

Convert the thesis into Crustdata search queries and structured filters.

Retrieve candidate companies.

Deduplicate and resolve company identities.

Remove companies that fail verified hard constraints.

Identify observable opportunity signals.

Rank remaining candidates by thesis fit.

Preserve missing or uncertain data separately.

Allow the user to select a candidate for deeper investigation.

Output

A structured shortlist containing:

Company name

Website/domain

Industry

Geography

Description/business model

Founding year, if known

Headcount and growth estimates, where available

Funding history, where available

Relevant hiring signals

Thesis-fit assessment

Reasons for inclusion

Missing screening information

Sources and refresh dates

Important limitation

The discovery score must represent fit with the investor's requirements, not expected investment returns.

Hiring growth, employee count and funding history should never automatically be treated as proof of revenue growth or product-market fit.

4.2 Module B — Diligence

Purpose: Independently investigate selected companies.

Entry methods

Select a company from Discover.

Enter a company URL or name directly.

Enter a legal entity identifier where available.

Upload a pitch deck or company presentation.

Enter individual claims manually.

Investigation categories

P0 — Identity

Company name

Legal entity, when registry evidence is accessible

Website and domain

Location

Company aliases

Corporate status where available

Parent/subsidiary distinctions

P0 — Company Intelligence

Industry and business model

Reported funding events

Organizational growth indicators

Relevant leadership information

Publicly observable business developments

P0 — Claim Verification

Date-specific factual assertions

Founder employment-history claims

Funding announcements

Public launch or expansion claims

Claims directly supported by accessible source fields

P1 — Additional Investigation

Registered security interests, correctly interpreted

Corporate directorship associations

Relevant litigation and adverse media

Commercial partnerships

Public customer claims

Trademark ownership

Available financial filings

P1 investigations are enabled only when suitable authoritative or adequately corroborated data is accessible.

Claim-verification statuses

Supported: Adequate evidence directly supports the claim.

Contradicted: Reliable evidence directly conflicts with the precise claim.

Partially corroborated: Evidence supports some, but not all, of the assertion.

Conflicting evidence: Relevant sources materially disagree.

Cannot verify: Available evidence cannot settle the question.

Not checked: Verification was not performed, including budget or source limitations.

Example

Seller claim: "We currently employ 250 people."

Crustdata returns an estimate based on professional profiles.

The agent must explain what that estimate measures.

It cannot simply label the claim false because the profile estimate is lower than 250.

The output may be:

"Current payroll headcount cannot be verified from professional-profile estimates. Request a dated employee register or payroll summary."

Diligence deliverable

A claim ledger with exact evidence, discrepancies, unresolved questions, and next steps.

4.3 Module C — Evaluate

Purpose: Convert investigated company information into an explainable screening assessment.

This is intended to be the product's most important differentiator.

Product philosophy

DealProof must not generate investment conclusions from arbitrary LLM confidence.

Evaluation should be:

Investor-specific

Stage-aware

Explainable

Evidence-backed

Reproducible

Adjustable

Honest about missing information

Required evaluation outputs

Investment thesis fit

Evidence quality and completeness

Operational or business performance indicators

Financial assessment, when reliable inputs exist

Material risks and unknowns

Peer comparisons, when genuinely comparable data exists

Final screening disposition

Specific reasons for that disposition

Separate assessments

DealProof must distinguish:

Opportunity Fit: How well the company matches the investor's strategy.

Evidence Sufficiency: Whether available records support the required screening criteria.

Business Assessment: What observable operating indicators suggest, without turning correlations into established financial facts.

Financial Assessment: An explicitly assumption-based valuation or feasibility analysis using available, valid financial inputs.

Screening Disposition: What the investor should investigate next under their own policy.

These must not be blended into a single opaque "investment quality" score.

5. Evaluation Framework

5.1 Stage-Aware Evaluation

The evaluation framework must adjust according to the opportunity.

Evaluation Profile A — Early-Stage Startup
Suitable for venture investments and younger businesses.

Dimensions:
Dimension
Possible indicators
Important limitation
Thesis fit
Sector, geography, business model, stage
Requires investor-defined criteria
Founder relevance
Prior employers, roles, relevant experience
Employment history does not establish founder quality
Team development
Headcount and hiring trends
Profile-based estimates may exclude workers
Product and market evidence
Public products, partnerships, identifiable demand indicators
Cannot assume product-market fit
Funding history
Disclosed funding rounds and investors
Not evidence of future returns
Competitive landscape
Comparable company descriptions and product focus
Coverage may be incomplete
Evidence sufficiency
Availability of required supporting information
Missing information is not negative performance

Output: Investment-thesis fit and priority for further research or a founder meeting.

Evaluation Profile B — Established SME / Acquisition Target

Suitable for strategic acquisitions, lower-middle-market businesses and mature operating companies.

Dimensions:

Dimension

Possible indicators

Important limitation

Strategic fit

Geography, services, capabilities, customer segments

Buyer-specific

Identity

Legal entity, operations, ownership evidence

Requires authoritative registry information

Operational scale

Locations, workforce, publicly reported activities

Public indicators are incomplete

Financial performance

Revenue, EBITDA, cash flow, margins

Requires reliable financial statements

Commercial position

Customers, contracts, market presence

Public references may be insufficient

Leadership continuity

Management composition and dated changes

Public profiles may lag

Material concerns

Verified discrepancies, regulatory or legal records

Avoid guilt by association

Evidence sufficiency

Coverage of the buyer's mandatory checks

Must explicitly identify missing records

Output: Acquisition screening assessment and next-diligence requirements.

5.2 Investment Thesis Configuration

A thesis contains:

Mandatory filters

Preferred attributes

Evaluation dimensions

Relative dimension weights

Material disqualifiers

Required evidence categories

Maximum permitted uncertainty for a ready-to-proceed disposition

Review and approval rules

For example:

Hypothetical 3PL acquisition thesis

Indian company.

Warehousing or contract-logistics operations.

Presence in North or West India.

Relevant enterprise logistics capabilities.

Evidence of operating activity.

Management continuity preferred.

Material legal identity mismatch prohibited.

Unverified ownership or key financial information triggers further review.

5.3 Opportunity Fit Algorithm

For each company, evaluate known thesis criteria.

A candidate that fails a verified mandatory constraint is excluded or placed in an exception queue.

For eligible candidates, calculate:

Thesis Fit = Σ(weight × criterion score) / Σ(applicable weights)

Each criterion score should use a documented scale, such as 0–5.

Examples:

Geography match

Business model relevance

Stage compatibility

Operational capability match

Investor-specific preferences

Only include a criterion in the numerical calculation when it has enough evidence to be assessed.

Display evaluated weight coverage beside the score.

Example: "Thesis fit 82/100; 70% of weighted criteria could be assessed."

A company with poor evidence coverage must not appear equally decision-ready as one with complete evidence simply because its available criteria scored highly.

5.4 Evidence Coverage

Track evidence sufficiency separately.

Suggested measures:

Required checks completed

Required checks supported

Unresolved critical checks

Conflicting records

Source freshness

Verified entity matches

The product should show the individual statuses and the precise missing records, not a fabricated probability that the company is trustworthy.

5.5 Screening Disposition Rules

Possible outcomes:

Prioritize: Strong thesis fit and mandatory screening requirements satisfied within the scope of the service.

Investigate further: Attractive company, but material evidence is incomplete.

Deprioritize: Verified failure of an investor-defined requirement or sufficiently evidenced unfavorable fit.

Cannot assess: Identity or other essential information is too uncertain for a defensible evaluation.

A lack of public evidence alone must not automatically lead to deprioritization.

5.6 Dynamic Re-Evaluation

When newly retrieved evidence materially changes a claim verdict, the evaluation engine should:

Identify which claim changed.

Record old and new evidence.

Recalculate affected evaluation dimensions.

Reassess relevant screening rules.

Save the previous assessment version.

Explain why the disposition changed.

Illustrative demonstration:

Company A initially ranks highly based on a claimed expansion event.

A later investigation shows that the available source refers to a proposed expansion, not a completed facility opening.

The system marks the actual operational-expansion claim unresolved and updates the assessment.

This should be triggered by genuine evidentiary differences, not artificially manufactured score changes.

6. Financial Evaluation

Financial evaluation must be explicitly separated from company intelligence.

6.1 Early-Stage Companies

The MVP should not promise accurate valuations or expected returns from headcount, funding or hiring signals.

Permitted outputs:

Historical disclosed funding

Investor-provided valuation assumptions

Simple capitalization or dilution scenarios, when inputs exist

Comparable financing observations with caveats

Identified financial questions requiring founder confirmation

6.2 Established Acquisition Targets

Where a user uploads reliable financial data, the future product may calculate:

Revenue growth

Gross and operating margins

EBITDA margin

Cash conversion

Working capital

Debt and net debt

Basic valuation multiples

Scenario-based enterprise value

Potential acquisition affordability

Financial correctness rules

The original figures and reporting periods must be retained.

Standalone and consolidated financials must not be mixed.

Currency units must be standardized.

Fiscal years and calendar years must be distinguished.

Missing values must remain missing.

Model assumptions must be visible and editable.

Valuation is scenario-based, not presented as a verified fair value.

MVP decision

Financial valuation and investment return forecasting are excluded from the hackathon's critical path unless valid financial inputs and a complete calculation engine are already available.

The immediate evaluation engine should focus on strategic/thesis fit and verified evidence.

7. End-to-End Product Journeys

7.1 Journey A — Discover and Screen

User: Investment analyst.

Request: "Find five Indian supply-chain technology businesses matching our acquisition thesis."

Flow:

User enters the thesis.

System generates structured search criteria.

User reviews or edits the criteria.

Crustdata searches candidate companies.

Companies are deduplicated.

Available business data is normalized.

System calculates thesis fit and coverage.

User receives a ranked shortlist.

User selects a company.

System creates a diligence case.

Company identity is resolved.

Available material claims are investigated.

Evaluation is updated.

System generates a screening memo.

User receives a prioritized next-action recommendation.

Completed result: A decision-ready company-screening case initiated from investment discovery.

7.2 Journey B — Direct Diligence

User: M&A associate.

Request: "Investigate this company before our second meeting."

Flow:

User provides company identifiers.

User uploads seller claims or documents.

System extracts individual factual claims.

System resolves the relevant legal/business entity.

Each claim is matched to an investigation method.

External evidence is retrieved.

Evidence is verified for identity, period, definition and provenance.

Claim verdicts are assigned.

Unresolved information requirements are generated.

A screening report is produced.

Any external communication waits for approval.

Completed result: A persisted, cited claims review with a targeted information-request list.

7.3 Journey C — Evaluate Alternatives

User: Corporate development manager.

Request: "Compare these three companies against our acquisition strategy."

Flow:

User selects existing companies or screening cases.

System loads the same investment thesis.

Available facts are normalized.

Comparisons are restricted to genuinely comparable measures.

Thesis-fit indicators are calculated.

Evidence sufficiency is displayed.

Important uncertainties and differences are highlighted.

System explains relative suitability.

User chooses which targets require further diligence.

Completed result: A consistent comparative screening decision, not an unsupported prediction of which investment will perform best.

7.4 Journey D — Resolve Missing Evidence

User: Analyst with an unresolved screening case.

Request: "Get the information necessary to complete this diligence screen."

Flow:

System identifies critical unresolved claims.

It determines which documents could resolve them.

It creates a consolidated information-request list.

It drafts a communication to the authorized counterparty.

Human approval is required.

An approved request is sent through a controlled provider.

Execution state and provider references are saved.

New documents can be attached to the same case.

The system rechecks affected claims and updates the evaluation.

Completed result: A tracked, approval-controlled evidence-request action and a case ready for re-verification.

8. Functional Requirements

8.1 Core Features

ID

Feature

Priority

Acceptance criteria

FR-01

Natural-language thesis

P0

Converts request to a structured thesis

FR-02

Editable search filters

P0

User can inspect hard and soft criteria

FR-03

Company discovery

P0

Retrieves real companies matching supported filters

FR-04

Candidate deduplication

P0

Same company is not listed twice under aliases

FR-05

Company profile

P0

Displays available enriched information and provenance

FR-06

Thesis-fit evaluation

P0

Reproducible score with criteria and weights

FR-07

Direct company screening

P0

Target can be investigated without using discovery first

FR-08

Company identity resolution

P0

Ambiguous entities are not silently selected

FR-09

Claim extraction

P0

Supported factual claims extracted into typed records

FR-10

Evidence retrieval

P0

Uses live, permitted external data

FR-11

Evidence verification

P0

Checks exact source and proposition

FR-12

Claim verdicts

P0

Produces defensible statuses with explanations

FR-13

Evidence Ledger

P0

Persists exact sources, dates and field references

FR-14

Evaluation engine

P0

Combines thesis fit and diligence readiness

FR-15

Screening disposition

P0

Returns explicit, rule-backed next-stage recommendation

FR-16

Information-request list

P0

Identifies what is needed to settle important gaps

FR-17

Persistent jobs

P0

Jobs survive process termination

FR-18

Cost and budget tracking

P0

Actual usage recorded; caps enforced

FR-19

Exportable screening case

P0

Complete decision-ready report saved

FR-20

Approval-gated outbound action

P0

No external communication without authorization

FR-21

Peer benchmarking

P1

Uses consistently defined measures

FR-22

Updated evaluation on new evidence

P1

Shows why assessment changed

FR-23

Multiple-company comparison

P1

Compares results under the same thesis

FR-24

Financial scenario engine

P2

Uses verified/user-supplied financial inputs

FR-25

Continuous monitoring

P2

Alerts on material evidence changes

FR-26

Deal pipeline management

P2

Tracks later deal lifecycle stages

FR-27

Data-room integration

P2

Supports authorized private diligence

FR-28

CRM and collaboration integration

P2

Syncs approved statuses and activities

9. Data Architecture and Crustdata Integration

9.1 Primary Data Strategy

Use specialized data sources for different kinds of facts.

Crustdata: Business discovery, organizational signals, company profiles, people and funding information.

Government and official records: Legal corporate identity and applicable regulatory facts.

Company publications: What a business publicly represents.

Independent publications: Corroborating or contradictory evidence.

User-supplied materials: Seller claims and authorized financial/documentary evidence.

No source should be treated as authoritative outside its area of competence.

9.2 Crustdata APIs

Company Search

Endpoint: POST /company/search

Purpose:

Search by sector, geography, business characteristics and other supported filters.

Run ranked searches using natural-language relevance.

Retrieve candidate companies.

Search supports structured filters and hybrid, lexical or semantic modes.

Fields should be selected explicitly to control costs.

Company Identify / Entity Matching

Purpose:

Match a provided company domain or identifier.

Distinguish similar company records.

Connect search results to canonical records.

Use reliable identifiers such as domains or registry identifiers where available.

A Crustdata match score alone is insufficient to establish a legal identity.

Company Enrich

Endpoint: POST /company/enrich

Requested field groups may include:

basic_info

taxonomy

locations

headcount

funding

people

hiring

news

revenue, where appropriate

competitors, where appropriate

The request should include only required field groups.

For example, use the minimum relevant set for first-pass screening rather than requesting every available premium dataset.

People Search / Enrich

Purpose:

Identify founders or named executives.

Investigate reported professional backgrounds.

Establish employment dates where available.

Do not perform broad collection of personal contact information merely because the API provides it.

Jobs and Hiring

Purpose:

Observe advertised hiring demand.

Identify function-specific recruiting activity.

Investigate public expansion signals.

A job posting is not proof that a person was hired.

News and Web Retrieval

Purpose:

Retrieve dated announcements.

Verify public claims.

Investigate material events.

Search-result snippets alone should not establish a factual verdict when the underlying passage can be retrieved.

9.3 Crustdata Technical Requirements

API key stored securely.

Use the documented API version.

Record request ID where returned.

Record actual credits charged.

Store endpoint, requested fields and request hash.

Respect per-endpoint rate limits.

Cache permitted responses.

Preserve data-refresh timestamps.

Handle empty match arrays.

Implement bounded retries.

Enforce per-job credit budgets.

Reconcile usage using account usage endpoints.

Important: Company-search pricing may include premium field/filter charges in addition to the base per-result price.

9.4 Additional Data Sources

Source class

Intended use

MVP condition

Authorized MCA registry access or aggregator

Legal company identity

Only if authenticated access succeeds

Official stock exchange filings

Listed-company events and financial disclosures

Use exact relevant primary records

Company websites

Officially represented product and company information

Treat claims as representations

Public announcements

Funding, expansion and partnerships

Preserve source and event date

Authorized court records

Specific legal proceedings

Require correct entity disambiguation

Uploaded financials

Financial analysis

Require period, basis, currency and provenance

Other data providers

Fill demonstrated source gaps

Verify terms, access and cost before integration

9.5 Source Hierarchy

Evidence should be evaluated based on the proposition being checked.

For example:

A government corporate registry is stronger for incorporation status.

An audited financial statement is stronger for historical reported revenue.

A customer's direct confirmation is stronger for an actual customer relationship.

A professional profile is useful for career research but not necessarily definitive proof of employment.

A company's own announcement can establish that it announced an expansion, not that the facility subsequently became operational.

Source authority is claim-specific, not a universal ranking.


17. Success Metrics

17.1 North Star Metric

Completed evidence-backed screening cases accepted for investment decision review.

17.2 Product KPIs

Metric

Definition

Screening completion rate

Completed / valid submitted screening jobs

Evidence-backed finding rate

Material factual findings with valid direct evidence

Claim verdict accuracy

Correct verdicts against a labeled test set

False contradiction rate

Incorrectly contradicted claims / evaluated claims

Entity resolution accuracy

Correctly matched company/person identities

Appropriate abstention rate

Correct unresolved decisions when evidence is insufficient

Time to first shortlist

Search initiation to usable candidate list

Time to screening case

Investigation start to saved output

Evaluation reproducibility

Same records + policy produce same assessment

Restart success

Interrupted jobs completing without duplicated consequential actions

Unauthorized action count

Count of external actions without approval

Actual cost per job

Measured provider and model usage

Human time saved

Baseline manual effort minus assisted effort

17.3 Provisional MVP Quality Gates

No unsupported verified claim in the team's labeled test suite.

No unauthorized external action.

No duplicated consequential action during tested restarts.

Every material factual verdict linked to retained evidence.

Every unresolved critical claim states what is missing.

All job costs and external calls logged.

At least one real company retrieved using a live permitted source.

At least one end-to-end case completed in the organizer's required format.

Architecture, README and demo reproducible from the repository.

Do not claim statistical accuracy from a small set of manually selected examples.

21. ContextCon Scoring Optimization

The official finals rubric totals 100 points.

Category

Points

Required product proof

Live execution

20

Complete an unseen investment-screening request correctly

Robustness

15

Resume after forced process termination without duplicate actions

System design

15

Explain architecture and implement a small live change

Ethics

25

Demonstrate fair identity handling, privacy controls, evidence and approvals

Financial feasibility

25

Identify buyer, rupee price, actual cost/job and credible savings

Screening is a separate elimination stage. Hidden-test correctness, restart behavior and engineering artifacts determine whether the team reaches the finals.

21.1 Hidden-Case Readiness

Test at least:

Duplicate company.

Similar-name company.

Same-name founder.

Wrong legal identifier.

False premise.

Missing source.

Contradictory dates.

Different company subsidiaries.

Source that cannot resolve a claim.

Recent record unavailable in one data provider.

Process kill.

Budget reduction.

Repeated outbound request.

The official hidden cases may use events or records dated after 1 September 2026.

Our own test suite does not replace the organizers' hidden evaluation.

21.2 Five-Minute Live-Fix Readiness

Structure policies to support simple modifications, such as:

Add an output field.

Change a screening threshold.

Reduce per-job credit allowance.

Require an additional source for a claim type.

Change a thesis weight.

Add an approval rule.

Restrict source freshness.

Rules should live in configurable policy files wherever practical.

21.3 Stage Demo

Opening

"We built DealProof, an AI analyst that doesn't stop at finding investment opportunities. It independently checks the claims behind them and produces a defensible investment screening case."

Demonstration

Enter a real investment thesis.

Discover companies through Crustdata.

Select a candidate.

Investigate available claims.

Open exact evidence.

Show opportunity fit and evidence sufficiency separately.

Explain why the screening disposition follows.

Show the completed report and information request.

Terminate and restart the process.

Show that stored evidence, budget usage and action state remain correct.

If the live event requires an unseen request, prioritize that request rather than a rehearsed company.

Finance explanation

"The customer pays ₹4,000 per completed first-pass screening case under our proposed pricing model. Here is the actual cost of the case that just ran. Our estimated manual comparison is explicitly a hypothesis until validated with practitioners."


28. Final Product Statement

DealProof is an AI-native investment intelligence service that discovers businesses matching an investment thesis, investigates the evidence behind their claims, and delivers a transparent evaluation of whether they deserve further consideration.

Its core advantage is a connected and reproducible workflow:

Discover → Investigate → Verify → Evaluate → Act

The product should not compete on the number of companies displayed, number of agents deployed or number of metrics shown.

It should compete on the quality of the finished investment-screening job: correct company identification, useful research, defensible factual conclusions, explicit uncertainty, consistent evaluation and actionable next steps.

The most important technical and product requirement is that new evidence can change an assessment without hiding what was previously believed or why the assessment changed.

That is the proposed foundation for DealProof's long-term differentiation and its ContextCon MVP.
