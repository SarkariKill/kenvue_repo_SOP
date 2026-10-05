# Kenvue Global SOP Audit & Scoring Skill
**Version**: 2.4.0  
**Domain**: Quality Assurance, Regulatory Compliance & Operational Excellence  
**Standard**: Kenvue Standard Operating Procedure Architecture (SOP-STD-001)

---

## 1. Objective & Purpose
This skill defines the authoritative criteria and scoring rubrics used to evaluate Standard Operating Procedures (SOPs) against Kenvue Global Quality Standards. It establishes quantifiable evaluation metrics and produces actionable, user-selectable remediation points to drive document optimization.

---

## 2. Kenvue Standard Section Hierarchy
An approved Kenvue SOP must adhere to the following 10-tier modular structure:

| Section # | Required Section Title | Scope & Quality Criteria |
| :---: | :--- | :--- |
| **1.0** | **Purpose & Objective** | Concise statement defining why the procedure exists and the exact outcome it achieves. Must avoid vague generalizations. |
| **2.0** | **Scope, Applicability & Definitions** | Specific operational units, facilities, manufacturing lines, and equipment covered. Must include a glossary table defining technical terms and acronyms. |
| **3.0** | **Roles & Responsibilities** | Explicit RACI breakdown (Responsible, Accountable, Consulted, Informed) detailing Certified Operator, Shift Supervisor, and QA reviewer obligations. |
| **4.0** | **Mandatory Safety, PPE & Hazard Controls** | Standalone high-visibility section listing required PPE (ANSI safety glasses, nitrile gloves), chemical exposure thresholds, and emergency stop/spill response protocols. |
| **5.0** | **Equipment, Materials & Workstation Setup** | Exhaustive list of validated equipment, calibrated tools, approved reagents, and workstation layout/staging diagrams. |
| **6.0** | **Step-by-Step Operating Procedure** | Sequentially numbered hierarchical steps (6.1, 6.2, 6.2.1) written in direct imperative command voice. Accompanied by process flowcharts. |
| **7.0** | **Quality Control, Inspection & Acceptance Standards** | Quantified verification parameters with explicit numerical tolerances (e.g., ± 2.0%, ± 0.5 °C). Objective pass/fail criteria and inspection checklists. |
| **8.0** | **Documentation, Records Retention & References** | Logbook requirements, electronic batch records (eBR), document retention schedules, and cross-referenced SOP standards. |
| **9.0** | **Revision History & Document Control** | Document control metadata, version numbering (e.g., 2.0), effective date, change summary, and author/approver sign-off records. |
| **10.0** | **Appendix: Operational Checklists & Logsheets** | Pre-operational quick check forms, verification checklists, and operator sign-off tables. |

---

## 3. Scoring Rubric Specifications

### Metric 1: Template Compliance Score (`template_score`: 0–100)
Evaluates architectural alignment with Kenvue standard sections:
* **90–100**: All mandatory sections (1.0 to 9.0) are present, properly numbered, and follow standard hierarchical sequencing.
* **75–89**: Most sections present; minor gaps in dedicated EHS/PPE, Definitions, or Document Control tables.
* **60–74**: Basic procedure present but lacks formal roles, explicit quality acceptance criteria, or revision history.
* **< 60**: Unstructured or legacy text lacking standard numbering, missing safety precautions and formal document headers.

### Metric 2: Readability & Command Voice Score (`readability_score`: 0–100)
Evaluates sentence complexity, clarity, and directive tone:
* **Imperative Command Voice**: Steps must open with strong action verbs (*"Inspect"*, *"Sanitize"*, *"Calibrate"*, *"Verify"*) rather than passive voice (*"The operator should check"*, *"It is recommended that"*).
* **Sentence Length**: Procedural steps must average between 12 and 22 words. Penalize sentences exceeding 30 words.
* **Clarity & Ambiguity Elimination**: Zero tolerance for vague adverbs like *"properly"*, *"approximately"*, *"sufficient amount"*, or *"as needed"*.

### Metric 3: Technical Quality & Tolerance Score (`quality_score`: 0–100)
Evaluates precision, hazard management, and verifiable controls:
* **Quantified Tolerances**: Operating parameters must include explicit allowable tolerances (e.g., `12,500 ± 50 RPM`, `4.0 ± 0.5 °C`, `15 ± 2 PSI`, `10 to 15 minutes contact time`).
* **Critical Safety Alerts**: High-risk steps must feature prominent Warning / Caution callouts preceding the action.
* **Asset Integration**: High-resolution process flowcharts, equipment staging figures, and parameter tables must be referenced and embedded directly within corresponding sections.

### Metric 4: Composite Average Score (`average_score`: 0–100)
$$\text{Average Score} = \text{round}\left(\frac{\text{Template Score} + \text{Readability Score} + \text{Quality Score}}{3}\right)$$

---

## 4. Remediation Suggestion Taxonomy
When auditing an SOP, the auditor must generate 4 to 6 concrete, mutually exclusive improvement points presented as user-selectable checkboxes:
1. `sug_struct`: **Standardize Section Hierarchy to Kenvue Format** — Restructure headings into standard 1.0–10.0 numbering.
2. `sug_ppe`: **Add Dedicated Safety, PPE & Hazard Controls Section** — Create formal personal protective equipment matrix and emergency triggers.
3. `sug_imperative`: **Convert Procedural Steps to Active Imperative Voice** — Transform passive descriptions into direct action commands.
4. `sug_tolerances`: **Incorporate Quantified Numerical Tolerances (±)** — Replace vague estimates with explicit measurable limits.
5. `sug_qc`: **Establish Quality Acceptance Criteria & Inspection Standards** — Add objective pass/fail verification tables before release.
6. `sug_records`: **Add Standardized Document Control & Revision History** — Add formal version tracking, RACI roles, and record retention periods.
