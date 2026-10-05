import json
import logging
import os
import shutil
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import faiss
import numpy as np
import pymupdf

from minio_storage import minio_storage
from rag_engine import generate_embeddings

logger = logging.getLogger(__name__)

INDEX_STORAGE_PATH = os.getenv("INDEX_STORAGE_PATH", "./indexes")
TEMPLATE_INDEX_FILE = os.path.join(INDEX_STORAGE_PATH, "template_rules.index")
TEMPLATE_META_FILE = os.path.join(INDEX_STORAGE_PATH, "template_rules.json")

# =====================================================================
# DEFAULT KENVUE SOP STANDARD GUIDELINES
# Used as baseline when no custom admin PDF has been uploaded yet.
# =====================================================================
DEFAULT_KENVUE_GUIDELINES = """
KENVUE GLOBAL STANDARD OPERATING PROCEDURE (SOP) SPECIFICATION & GUIDELINES

1. DOCUMENT STRUCTURE & REQUIRED SECTIONS:
- 1.0 Document Header: Title, SOP Number (format: SOP-XXX-000), Version (X.0), Effective Date, Review Cycle.
- 2.0 Purpose & Objective: Concise explanation of why the procedure exists and what it accomplishes.
- 3.0 Scope & Applicability: Clearly defines departments, facilities, equipment, and roles to which this applies.
- 4.0 Roles & Responsibilities: Explicit RACI table or list of operators, supervisors, and quality reviewers.
- 5.0 Environmental Health & Safety (EHS) / PPE: Mandatory personal protective equipment, chemical hazards, and emergency shutdown triggers.
- 6.0 Equipment, Tools & Materials: Detailed listing of all machines, calibration tools, reagents, and part numbers.
- 7.0 Step-by-Step Procedure:
  * Strict hierarchical numbering (Step 7.1, 7.1.1, etc.).
  * Active voice with imperative command verbs ("Inspect", "Measure", "Clean", "Verify").
  * Quantified tolerances on all numerical parameters (e.g. 12500 ± 50 RPM, 4.0 ± 0.5 °C).
  * Explicit Warning/Caution callouts before critical hazard steps.
- 8.0 Quality Control & Verification Criteria: Objective pass/fail criteria and inspection checklists.
- 9.0 Deviations & Troubleshooting: Action protocol when operating parameters fall outside tolerance.
- 10.0 Document History & Approval Log: Version history table with author, approver, date, and change description.

2. READABILITY & CLARITY TARGETS:
- Reading clarity: Flesch Reading Ease score between 60.0 and 80.0.
- Sentences must be concise (< 25 words per step). Avoid passive voice ("The lever is moved" -> "Move the lever").
- Avoid ambiguous modifiers ("quickly", "approximately", "properly"). Use explicit parameters.

3. QUALITY & ASSET PRESERVATION:
- All schematics, diagrams, control panels, and tables must be embedded directly in their respective steps.
- Visual clarity: High-resolution crops with explicit figure/table numbering (e.g. 'Figure 1: Panel Layout').
"""


class TemplateManager:
    """
    Manages the Kenvue Standard Template / Guideline PDF uploaded by the Admin.
    When a new template PDF is uploaded, existing template embeddings are deleted,
    and a fresh FAISS vector index is created from the new guideline.
    """

    def __init__(self):
        self.active_template_name: Optional[str] = None
        self.active_template_uploaded_at: Optional[str] = None
        self.rules_text: str = DEFAULT_KENVUE_GUIDELINES
        self._load_existing_template()

    def _load_existing_template(self):
        """Check if custom admin template index exists on disk."""
        if os.path.exists(TEMPLATE_INDEX_FILE) and os.path.exists(TEMPLATE_META_FILE):
            try:
                with open(TEMPLATE_META_FILE, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                self.active_template_name = meta.get("filename", "Kenvue_Guidelines.pdf")
                self.active_template_uploaded_at = meta.get("uploaded_at")
                self.rules_text = meta.get("full_text", DEFAULT_KENVUE_GUIDELINES)
                logger.info("Loaded custom admin template guidelines: %s", self.active_template_name)
            except Exception as e:
                logger.warning("Could not load template metadata: %s", e)

    def upload_admin_template(self, file_bytes: bytes, filename: str, uploaded_by: str) -> Dict[str, Any]:
        """
        # --- HERE ADMIN TEMPLATE REPLACEMENT HAPPENS ---
        1. Deletes old template FAISS index and metadata.
        2. Uploads the new guideline PDF to MinIO under 'system/templates/'.
        3. Parses text, creates chunks, and embeds them into a fresh FAISS index.
        """
        # Step 1: Remove old template vector index files if present
        if os.path.exists(TEMPLATE_INDEX_FILE):
            try:
                os.remove(TEMPLATE_INDEX_FILE)
            except Exception as e:
                logger.warning("Could not delete old template index: %s", e)
        if os.path.exists(TEMPLATE_META_FILE):
            try:
                os.remove(TEMPLATE_META_FILE)
            except Exception as e:
                logger.warning("Could not delete old template meta: %s", e)

        # Step 2: Upload new template PDF to MinIO
        ts = datetime.now(timezone.utc).isoformat()
        object_name = f"system/templates/{filename}"
        minio_storage.upload_file_bytes(
            object_name=object_name,
            data=file_bytes,
            content_type="application/pdf",
            metadata={"uploaded_by": uploaded_by, "uploaded_at": ts},
        )

        # Step 3: Extract text from PDF
        doc = pymupdf.open(stream=file_bytes, filetype="pdf")
        pages_text = []
        for i, page in enumerate(doc, start=1):
            text = page.get_text("text").strip()
            if text:
                pages_text.append(f"--- [Guideline Page {i}] ---\n{text}")
        doc.close()

        full_guidelines_text = "\n\n".join(pages_text) if pages_text else DEFAULT_KENVUE_GUIDELINES

        # Step 4: Chunk and generate fresh FAISS embeddings for guideline rules
        chunks = [c.strip() for c in full_guidelines_text.split("\n\n") if len(c.strip()) > 40]
        if not chunks:
            chunks = [full_guidelines_text]

        vectors = generate_embeddings(chunks)
        dim = vectors.shape[1]
        index = faiss.IndexFlatIP(dim)
        index.add(vectors)

        # Save to disk
        faiss.write_index(index, TEMPLATE_INDEX_FILE)
        meta_payload = {
            "filename": filename,
            "object_name": object_name,
            "uploaded_by": uploaded_by,
            "uploaded_at": ts,
            "chunks": chunks,
            "full_text": full_guidelines_text,
        }
        with open(TEMPLATE_META_FILE, "w", encoding="utf-8") as f:
            json.dump(meta_payload, f)

        self.active_template_name = filename
        self.active_template_uploaded_at = ts
        self.rules_text = full_guidelines_text

        logger.info("Admin successfully updated Kenvue SOP Template: %s (%d chunks)", filename, len(chunks))
        return {
            "status": "success",
            "filename": filename,
            "chunks_count": len(chunks),
            "uploaded_at": ts,
        }

    def get_template_status(self) -> Dict[str, Any]:
        """Returns the current state of active Kenvue guideline."""
        return {
            "has_custom_template": bool(self.active_template_name),
            "template_name": self.active_template_name or "Default Kenvue Standard Guideline",
            "uploaded_at": self.active_template_uploaded_at,
            "is_default": self.active_template_name is None,
        }

    def get_guidelines_summary(self) -> str:
        """Returns the active guideline rules for LLM evaluation."""
        return self.rules_text[:3500]


# Singleton instance
template_manager = TemplateManager()
