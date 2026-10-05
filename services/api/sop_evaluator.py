import json
import logging
import re
from typing import Any, Dict, List
import httpx

from skill_manager import skill_manager
from template_manager import template_manager

logger = logging.getLogger(__name__)

# =====================================================================
# SOP EVALUATION ENGINE
# Evaluates uploaded SOP against Kenvue guidelines:
# 1. Template Score (structure & required Kenvue sections)
# 2. Readability Score (sentence clarity, active voice, complexity)
# 3. Quality Score (tolerances, safety warnings, completeness)
# 4. Average Score (average of all 3)
# 5. Checkbox Suggestions (actionable improvements for the user)
# =====================================================================

def evaluate_sop_heuristics(sop_text: str) -> Dict[str, Any]:
    """
    Algorithmic heuristic fallback to score SOP and generate suggestions.
    Guarantees reliable, instant scoring even if LLM API is unavailable.
    """
    text_lower = sop_text.lower()
    
    # 1. Template Scoring (Structure & Sections)
    expected_sections = [
        ("purpose", 12),
        ("scope", 10),
        ("responsibilit", 12),
        ("safety", 15),
        ("ppe", 10),
        ("procedure", 15),
        ("equipment", 10),
        ("deviation", 8),
        ("revision", 8),
    ]
    template_pts = sum(pts for term, pts in expected_sections if term in text_lower)
    template_score = min(98, max(45, template_pts))

    # 2. Readability Scoring (Sentence Length & Active Voice)
    sentences = [s.strip() for s in re.split(r"[.!?]+", sop_text) if len(s.strip()) > 5]
    if sentences:
        avg_len = sum(len(s.split()) for s in sentences) / len(sentences)
        # Optimal procedural sentence length is 12-20 words
        len_penalty = max(0, min(30, int(abs(avg_len - 15) * 2)))
        readability_score = max(50, min(95, 88 - len_penalty))
    else:
        readability_score = 65

    # 3. Quality Scoring (Tolerances, Numbers, Warnings)
    has_tolerances = bool(re.search(r"(±|\+\/-|rpm|°c|psi|min|seconds|hours)", text_lower))
    has_warnings = bool(re.search(r"(warning|caution|danger|emergency|stop)", text_lower))
    has_numbering = bool(re.search(r"(step\s+\d|\d\.\d|\d\.\d\.\d)", text_lower))

    quality_score = 55
    if has_tolerances:
        quality_score += 15
    if has_warnings:
        quality_score += 15
    if has_numbering:
        quality_score += 10
    quality_score = min(96, quality_score)

    average_score = round((template_score + readability_score + quality_score) / 3)

    # 4. Concrete Suggestions for Checkboxes
    suggestions = [
        {
            "id": "sug_struct",
            "title": "Standardize Section Hierarchy to Kenvue Format",
            "description": "Restructure headings into standard numbering (1.0 Purpose, 2.0 Scope, 3.0 Responsibilities, 7.0 Procedure) for regulatory alignment.",
        },
        {
            "id": "sug_ppe",
            "title": "Add Formal PPE & Hazard Precautions Section",
            "description": "Establish a distinct section detailing required Personal Protective Equipment (PPE) and mandatory emergency shutdown protocols.",
        },
        {
            "id": "sug_imperative",
            "title": "Convert Steps to Active Imperative Voice",
            "description": "Rewrite procedural steps with direct action verbs ('Inspect', 'Adjust', 'Sanitize') instead of passive statements to eliminate ambiguity.",
        },
        {
            "id": "sug_tolerances",
            "title": "Specify Explicit Operating Tolerances",
            "description": "Add numeric acceptable deviation ranges (e.g., ± 50 RPM, ± 0.5 °C) to all operating parameters and process steps.",
        },
        {
            "id": "sug_qc",
            "title": "Include Quality Acceptance & Verification Criteria",
            "description": "Add an explicit checklist of pass/fail criteria at the conclusion of the procedure before releasing equipment for production.",
        },
    ]

    return {
        "template_score": template_score,
        "readability_score": readability_score,
        "quality_score": quality_score,
        "average_score": average_score,
        "summary": (
            f"The document received an overall rating of {average_score}/100. "
            f"Adherence to Kenvue standard sections scored {template_score}%, "
            f"while operational clarity and quality parameters scored {readability_score}% and {quality_score}% respectively."
        ),
        "suggestions": suggestions,
    }


async def evaluate_sop_with_llm(
    sop_text: str,
    llm_service_url: str,
    provider: str,
    model: str,
    api_key: str,
) -> Dict[str, Any]:
    """
    Uses the configured LLM and active Kenvue Guidelines to perform in-depth scoring
    and generate tailored suggestions. Falls back to algorithmic scoring if LLM call fails.
    """
    audit_skill = skill_manager.get_audit_skill()
    custom_guidelines = template_manager.get_guidelines_summary()

    prompt = f"""You are an elite pharmaceutical and healthcare SOP Quality Auditor evaluating a procedure using the official Kenvue SOP Audit & Scoring Skill.

--- MASTER KENVUE SOP AUDIT SKILL SPECIFICATION ---
{audit_skill}

--- FACILITY GUIDELINE SPECIFICATIONS ---
{custom_guidelines}

--- UPLOADED SOP DOCUMENT (EXCERPT) ---
{sop_text[:4500]}

--- AUDIT & SCORING TASK ---
Using the exact scoring rubrics defined in the Kenvue SOP Audit Skill above, evaluate the uploaded SOP and return a JSON object with:
1. "template_score": integer (0 to 100), measuring structural compliance with the standard 10-tier sections.
2. "readability_score": integer (0 to 100), measuring imperative command voice, active verbs, and sentence clarity.
3. "quality_score": integer (0 to 100), measuring quantified numerical tolerances (±), safety precautions, and precision.
4. "summary": A concise 2-sentence diagnostic assessment of the SOP's compliance status.
5. "suggestions": A list of 4 to 6 specific, actionable improvement points formatted as checkboxes for the user. Each suggestion must have:
   - "id": a unique string (e.g. "sug_struct", "sug_ppe", "sug_tolerances", "sug_imperative", "sug_qc")
   - "title": a clear, action-oriented title (3 to 7 words)
   - "description": a 1-2 sentence technical explanation of why this change improves compliance.

Respond ONLY with valid JSON. No markdown fences, no explanation.
"""

    body = {
        "provider": provider,
        "model": model,
        "api_key": api_key,
        "messages": [{"role": "user", "content": prompt}],
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            res = await client.post(f"{llm_service_url}/generate", json=body)
        if res.status_code == 200:
            content = res.json().get("content", "").strip()
            # Clean JSON fences if present
            clean_json = re.sub(r"^```json\s*", "", content)
            clean_json = re.sub(r"^```\s*", "", clean_json)
            clean_json = re.sub(r"\s*```$", "", clean_json).strip()
            parsed = json.loads(clean_json)

            t_score = int(parsed.get("template_score", 70))
            r_score = int(parsed.get("readability_score", 72))
            q_score = int(parsed.get("quality_score", 68))
            avg_score = round((t_score + r_score + q_score) / 3)

            return {
                "template_score": t_score,
                "readability_score": r_score,
                "quality_score": q_score,
                "average_score": avg_score,
                "summary": parsed.get("summary", ""),
                "suggestions": parsed.get("suggestions", []),
            }
    except Exception as e:
        logger.warning("LLM evaluation failed, falling back to heuristics: %s", e)

    return evaluate_sop_heuristics(sop_text)
