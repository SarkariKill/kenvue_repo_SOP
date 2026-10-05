import io
import json
import logging
import os
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import List, Optional

import httpx
from fastapi import FastAPI, File, Header, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

from auth import hash_password, verify_password
from minio_storage import minio_storage
from pdf_processor import extract_sop_pdf
from rag_engine import INDEX_STORAGE_PATH, create_hierarchical_chunks, get_vector_store
from similarity_engine import MultiSopSimilarityEngine
from harmonization_engine import HarmonizationEngine, SIMPLIFICATION_CATALOG
from sop_evaluator import evaluate_sop_with_llm
from sop_generator import generate_optimized_sop
from template_manager import template_manager

logger = logging.getLogger(__name__)

similarity_engine = MultiSopSimilarityEngine()
harmonization_engine = HarmonizationEngine()

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.getcwd() if os.path.exists(os.path.join(os.getcwd(), "services")) else os.path.abspath(os.path.join(CURRENT_DIR, "..", ".."))
DEFAULT_DB_PATH = os.path.join(PROJECT_ROOT, "storage", "data", "chat.db")
DATABASE_PATH = os.getenv("DATABASE_PATH", DEFAULT_DB_PATH)
LLM_SERVICE_URL = os.getenv("LLM_SERVICE_URL", "http://localhost:8001")

LEGACY_MODEL_MAP = {
    "llama-3.3-70b-versatile": "openai/gpt-oss-120b",
    "llama-3.1-8b-instant": "openai/gpt-oss-20b",
    "gemini-2.0-flash": "gemini-2.5-flash",
    "gemini-2.0-flash-lite": "gemini-2.5-flash",
    "gemini-2.5-pro": "gemini-2.5-flash",
    "gemini-2.5-flash-lite": "gemini-2.5-flash",
    "gemini-3.8-flash": "gemini-2.5-flash",
    "qwen/qwen3.8-27b": "openai/gpt-oss-120b",
}

app = FastAPI(title="Kenvue SOP Optimization & RAG API", version="0.3.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def db():
    c = sqlite3.connect(DATABASE_PATH, timeout=30.0)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA busy_timeout=30000")
    c.row_factory = sqlite3.Row
    return c


def now():
    return datetime.now(timezone.utc).isoformat()


def init_db():
    if os.path.dirname(DATABASE_PATH):
        os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
    c = db()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'user',
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS conversations (
        id TEXT PRIMARY KEY,
        username TEXT NOT NULL DEFAULT 'admin',
        title TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'active',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS messages (
        id TEXT PRIMARY KEY,
        conversation_id TEXT NOT NULL,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS sop_documents (
        id TEXT PRIMARY KEY,
        conversation_id TEXT NOT NULL,
        username TEXT NOT NULL DEFAULT 'admin',
        filename TEXT NOT NULL,
        page_count INTEGER NOT NULL,
        scores_json TEXT,
        optimized_scores_json TEXT,
        optimized_pdf_object_name TEXT,
        optimized_sections_json TEXT,
        optimized_title TEXT,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS sop_artifacts (
        id TEXT PRIMARY KEY,
        conversation_id TEXT NOT NULL,
        document_id TEXT NOT NULL,
        artifact_type TEXT NOT NULL,
        object_name TEXT NOT NULL,
        caption TEXT NOT NULL,
        page INTEGER NOT NULL,
        table_markdown TEXT,
        width INTEGER,
        height INTEGER,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS harmonized_sop_versions (
        id TEXT PRIMARY KEY,
        conversation_id TEXT NOT NULL,
        username TEXT NOT NULL DEFAULT 'admin',
        version_number INTEGER NOT NULL,
        version_label TEXT NOT NULL,
        version_type TEXT NOT NULL,
        parent_version_id TEXT,
        source_document_ids_json TEXT NOT NULL,
        source_filenames_json TEXT NOT NULL,
        title TEXT NOT NULL,
        markdown_content TEXT NOT NULL,
        sections_json TEXT NOT NULL,
        scores_json TEXT NOT NULL,
        change_summary TEXT,
        applied_recommendations_json TEXT,
        user_prompt TEXT,
        pdf_object_name TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS sop_similarity_cache (
        id TEXT PRIMARY KEY,
        conversation_id TEXT UNIQUE NOT NULL,
        analysis_json TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """)

    # Safe column migrations for pre-existing databases
    try:
        conv_cols = [row[1] for row in c.execute("PRAGMA table_info(conversations)").fetchall()]
        if "username" not in conv_cols:
            c.execute("ALTER TABLE conversations ADD COLUMN username TEXT NOT NULL DEFAULT 'admin'")
        if "status" not in conv_cols:
            c.execute("ALTER TABLE conversations ADD COLUMN status TEXT NOT NULL DEFAULT 'active'")
    except Exception as e:
        logger.warning("Conversation migration error: %s", e)

    try:
        sop_cols = [row[1] for row in c.execute("PRAGMA table_info(sop_documents)").fetchall()]
        if "username" not in sop_cols:
            c.execute("ALTER TABLE sop_documents ADD COLUMN username TEXT NOT NULL DEFAULT 'admin'")
        if "scores_json" not in sop_cols:
            c.execute("ALTER TABLE sop_documents ADD COLUMN scores_json TEXT")
        if "optimized_scores_json" not in sop_cols:
            c.execute("ALTER TABLE sop_documents ADD COLUMN optimized_scores_json TEXT")
        if "optimized_pdf_object_name" not in sop_cols:
            c.execute("ALTER TABLE sop_documents ADD COLUMN optimized_pdf_object_name TEXT")
        if "optimized_sections_json" not in sop_cols:
            c.execute("ALTER TABLE sop_documents ADD COLUMN optimized_sections_json TEXT")
        if "optimized_title" not in sop_cols:
            c.execute("ALTER TABLE sop_documents ADD COLUMN optimized_title TEXT")
    except Exception as e:
        logger.warning("SOP document migration error: %s", e)

    # Seed default admin user: username=admin, password=admin
    admin_row = c.execute("SELECT id FROM users WHERE username='admin'").fetchone()
    if not admin_row:
        c.execute(
            "INSERT INTO users (id, username, password_hash, role, created_at) VALUES (?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), "admin", hash_password("admin"), "admin", now()),
        )
    c.commit()
    c.close()


init_db()


# -------------------------------------------------------------
# PYDANTIC REQUEST MODELS
# -------------------------------------------------------------
class AuthRequest(BaseModel):
    username: str = Field(min_length=2, max_length=50)
    password: str = Field(min_length=3, max_length=100)


class MessageRequest(BaseModel):
    conversation_id: str
    content: str = Field(min_length=1, max_length=20000)


class ConversationCreate(BaseModel):
    title: str = "New Chat"


class SettingsRequest(BaseModel):
    provider: str
    model: str
    api_key: Optional[str] = None


class OptimizeRequest(BaseModel):
    document_id: Optional[str] = None
    selected_suggestion_ids: List[str] = []
    custom_instructions: str = ""


class HarmonizeRequest(BaseModel):
    selected_document_ids: List[str]
    custom_instructions: Optional[str] = None
    title_override: Optional[str] = None


class SimplifyRequest(BaseModel):
    version_id: Optional[str] = None
    selected_recommendation_ids: List[str] = []
    custom_instructions: Optional[str] = None


class RefineRequest(BaseModel):
    version_id: Optional[str] = None
    refinement_prompt: str = Field(min_length=1, max_length=20000)


# =============================================================
# 1. AUTHENTICATION & USER MANAGEMENT
# =============================================================
@app.post("/auth/register")
def register(payload: AuthRequest):
    username = payload.username.strip().lower()
    c = db()
    existing = c.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
    if existing:
        c.close()
        raise HTTPException(400, "Username already exists. Please pick another one or sign in.")

    uid = str(uuid.uuid4())
    pw_hash = hash_password(payload.password)
    role = "admin" if username == "admin" else "user"
    c.execute("INSERT INTO users (id, username, password_hash, role, created_at) VALUES (?, ?, ?, ?, ?)", (uid, username, pw_hash, role, now()))
    c.commit()
    c.close()
    return {"status": "ok", "username": username, "role": role}


@app.post("/auth/login")
def login(payload: AuthRequest):
    username = payload.username.strip().lower()
    c = db()
    user = c.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    c.close()
    if not user or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(401, "Invalid username or password.")
    return {"status": "ok", "username": user["username"], "role": user["role"]}


# =============================================================
# 2. CONVERSATIONS (USER-ISOLATED)
# =============================================================
@app.get("/health")
def health():
    return {"status": "ok", "service": "api"}


@app.post("/conversations")
def create_conversation(payload: ConversationCreate, x_username: Optional[str] = Header(None, alias="X-User-Name")):
    username = (x_username or "admin").strip().lower()
    cid = str(uuid.uuid4())
    ts = now()
    c = db()
    c.execute(
        "INSERT INTO conversations (id, username, title, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
        (cid, username, payload.title, "active", ts, ts),
    )
    c.commit()
    c.close()
    return {"id": cid, "title": payload.title, "username": username}



@app.get("/conversations")
def list_conversations(x_username: Optional[str] = Header(None, alias="X-User-Name")):
    username = (x_username or "admin").strip().lower()
    c = db()
    rows = c.execute(
        "SELECT * FROM conversations WHERE username=? ORDER BY updated_at DESC",
        (username,),
    ).fetchall()
    c.close()
    return [dict(r) for r in rows]


@app.get("/conversations/{conversation_id}/messages")
def get_messages(conversation_id: str):
    c = db()
    rows = c.execute(
        "SELECT * FROM messages WHERE conversation_id=? ORDER BY created_at ASC",
        (conversation_id,),
    ).fetchall()
    c.close()
    return [dict(r) for r in rows]


@app.delete("/conversations/{conversation_id}")
def delete_conversation(
    conversation_id: str,
    x_username: Optional[str] = Header(None, alias="X-User-Name"),
):
    """
    # --- HERE PERMANENT SESSION DELETION HAPPENS ---
    Permanently deletes a chat session from history.
    Wipes:
    1. Database entries (messages, sop_documents, sop_artifacts, conversations).
    2. MinIO user folder assets for this conversation:
       - users/{username}/conversations/{conversation_id}/*
       - users/{username}/summaries/{conversation_id}_summary.txt
       - any specific stored artifacts or optimized PDFs.
    3. FAISS vector index files (faiss_{conversation_id}.index, faiss_{conversation_id}_meta.json).
    """
    username = (x_username or "admin").strip().lower()
    c = db()
    conv = c.execute(
        "SELECT * FROM conversations WHERE id=? AND username=?",
        (conversation_id, username),
    ).fetchone()
    if not conv:
        c.close()
        raise HTTPException(404, "Conversation not found or access denied")

    # Fetch artifacts & documents to ensure all MinIO files are explicitly removed
    artifacts = c.execute(
        "SELECT object_name FROM sop_artifacts WHERE conversation_id=?",
        (conversation_id,),
    ).fetchall()
    docs = c.execute(
        "SELECT optimized_pdf_object_name FROM sop_documents WHERE conversation_id=?",
        (conversation_id,),
    ).fetchall()

    # 1. Clean up individual MinIO artifacts if any
    for art in artifacts:
        if art["object_name"]:
            try:
                minio_storage.remove_file(art["object_name"])
            except Exception as e:
                logger.warning("Could not delete artifact %s: %s", art["object_name"], e)

    for doc in docs:
        if doc["optimized_pdf_object_name"]:
            try:
                minio_storage.remove_file(doc["optimized_pdf_object_name"])
            except Exception as e:
                logger.warning("Could not delete optimized pdf %s: %s", doc["optimized_pdf_object_name"], e)

    # 2. Recursively delete entire conversation folder prefix in MinIO
    conv_prefix = f"users/{username}/conversations/{conversation_id}/"
    minio_storage.remove_directory_prefix(conv_prefix)

    # 3. Delete any archived summary in MinIO
    summary_object_name = f"users/{username}/summaries/{conversation_id}_summary.txt"
    try:
        minio_storage.remove_file(summary_object_name)
    except Exception as e:
        logger.warning("Could not delete summary file %s: %s", summary_object_name, e)

    # 4. Clean up FAISS vector index files
    index_file = os.path.join(INDEX_STORAGE_PATH, f"faiss_{conversation_id}.index")
    meta_file = os.path.join(INDEX_STORAGE_PATH, f"faiss_{conversation_id}_meta.json")
    for f_path in (index_file, meta_file):
        if os.path.exists(f_path):
            try:
                os.remove(f_path)
            except Exception:
                pass

    # 5. Delete from SQLite database
    c.execute("DELETE FROM messages WHERE conversation_id=?", (conversation_id,))
    c.execute("DELETE FROM sop_artifacts WHERE conversation_id=?", (conversation_id,))
    c.execute("DELETE FROM sop_documents WHERE conversation_id=?", (conversation_id,))
    c.execute("DELETE FROM conversations WHERE id=? AND username=?", (conversation_id, username))
    c.commit()
    c.close()

    logger.info("Permanently deleted conversation %s and all associated assets for user '%s'", conversation_id, username)
    return {
        "status": "deleted",
        "conversation_id": conversation_id,
        "message": "Chat session and all associated files/indexes permanently deleted.",
    }


# =============================================================
# 3. SETTINGS & ADMIN KENVUE TEMPLATE GUIDELINES
# =============================================================
@app.get("/settings")
def get_settings():
    c = db()
    rows = c.execute("SELECT key, value FROM settings").fetchall()
    c.close()
    values = {r["key"]: r["value"] for r in rows}
    provider = values.get("provider", "groq")
    default_model = "openai/gpt-oss-120b" if provider == "groq" else "gemini-2.5-flash"
    raw_model = values.get("model", default_model)
    model = LEGACY_MODEL_MAP.get(raw_model, raw_model)
    groq_configured = bool(
        values.get("groq_api_key")
        or (values.get("api_key") if values.get("provider") == "groq" else None)
        or os.getenv("GROQ_API_KEY", "")
    )
    gemini_configured = bool(
        values.get("gemini_api_key")
        or (values.get("api_key") if values.get("provider") == "gemini" else None)
        or os.getenv("GEMINI_API_KEY", "")
    )
    active_configured = groq_configured if provider == "groq" else gemini_configured
    template_status = template_manager.get_template_status()

    return {
        "provider": provider,
        "model": model,
        "api_key_configured": active_configured,
        "groq_configured": groq_configured,
        "gemini_configured": gemini_configured,
        "template_status": template_status,
    }


@app.post("/settings")
def save_settings(payload: SettingsRequest):
    provider = payload.provider.lower().strip()
    if provider not in {"groq", "gemini"}:
        raise HTTPException(400, "Provider must be groq or gemini")
    clean_key = payload.api_key.strip() if payload.api_key else ""
    if provider == "groq" and clean_key and not clean_key.startswith("gsk"):
        raise HTTPException(400, "Groq API key should start with gsk")

    save_model = LEGACY_MODEL_MAP.get(payload.model.strip(), payload.model.strip())
    c = db()
    c.execute("INSERT OR REPLACE INTO settings(key, value) VALUES('provider', ?)", (provider,))
    c.execute("INSERT OR REPLACE INTO settings(key, value) VALUES('model', ?)", (save_model,))
    if clean_key:
        c.execute("INSERT OR REPLACE INTO settings(key, value) VALUES(?, ?)", (f"{provider}_api_key", clean_key))
        c.execute("INSERT OR REPLACE INTO settings(key, value) VALUES('api_key', ?)", (clean_key,))
    c.commit()
    c.close()
    return {"status": "saved", "provider": provider, "model": save_model}


@app.post("/admin/upload-template")
async def upload_admin_template(file: UploadFile = File(...), x_username: Optional[str] = Header(None, alias="X-User-Name")):
    """
    Admin-only endpoint: upload the official Kenvue Template PDF.
    Old template embeddings are deleted, and fresh FAISS embeddings are built.
    """
    username = (x_username or "").strip().lower()
    c = db()
    user = c.execute("SELECT role FROM users WHERE username=?", (username,)).fetchone()
    c.close()
    if not user or user["role"] != "admin":
        raise HTTPException(403, "Admin privileges required to upload standard Kenvue templates.")

    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Template file must be a PDF document.")

    file_bytes = await file.read()
    if len(file_bytes) == 0:
        raise HTTPException(400, "Uploaded file is empty.")

    res = template_manager.upload_admin_template(
        file_bytes=file_bytes,
        filename=file.filename,
        uploaded_by=username,
    )
    return res


# =============================================================
# 4. SOP UPLOAD, EVALUATION & MINIO STORAGE
# =============================================================
@app.post("/conversations/{conversation_id}/upload-sop")
async def upload_sop(
    conversation_id: str,
    files: Optional[List[UploadFile]] = File(None),
    file: Optional[UploadFile] = File(None),
    x_username: Optional[str] = Header(None, alias="X-User-Name"),
):
    """
    Multi-SOP Upload & Evaluation (At Max 10 SOPs at a time):
    - Accepts 1 to 10 SOP PDF files concurrently
    - Extracts text, images, and tables for each SOP into MinIO
    - Hierarchically chunks each document with document_id and filename metadata
    - Generates FastEmbed bge-small-en-v1.5 embeddings
    - Builds/Stores into FAISS HNSW (Hierarchical Navigable Small World) index
      so semantically similar procedures across SOPs form connected graph clusters
    - Evaluates each SOP against Kenvue guidelines & compiles individual + collection scorecards
    """
    username = (x_username or "admin").strip().lower()
    c = db()
    conv = c.execute("SELECT * FROM conversations WHERE id=?", (conversation_id,)).fetchone()
    if not conv:
        c.close()
        raise HTTPException(404, "Conversation not found")

    # Consolidate files from either 'files' or 'file' parameters
    upload_list: List[UploadFile] = []
    if files:
        upload_list.extend([f for f in files if f.filename])
    if file and file.filename and not any(f.filename == file.filename for f in upload_list):
        upload_list.append(file)

    if not upload_list:
        c.close()
        raise HTTPException(400, "Please provide at least one SOP PDF file.")

    if len(upload_list) > 10:
        c.close()
        raise HTTPException(400, f"You can upload a maximum of 10 SOP PDFs at a time (selected: {len(upload_list)}).")

    for f in upload_list:
        if not f.filename.lower().endswith(".pdf"):
            c.close()
            raise HTTPException(400, f"File '{f.filename}' is not a PDF. Only PDF files are supported.")

    settings_rows = c.execute("SELECT key, value FROM settings").fetchall()
    config = {r["key"]: r["value"] for r in settings_rows}

    provider = config.get("provider", "groq")
    default_model = "openai/gpt-oss-120b" if provider == "groq" else "gemini-2.5-flash"
    raw_model = config.get("model", default_model)
    model = LEGACY_MODEL_MAP.get(raw_model, raw_model)
    api_key = config.get(f"{provider}_api_key") or config.get("api_key", "")
    if not api_key:
        api_key = os.getenv("GROQ_API_KEY" if provider == "groq" else "GEMINI_API_KEY", "")

    scoped_conv_prefix = f"users/{username}/conversations/{conversation_id}"
    ts = now()
    all_child_chunks: List[Dict[str, Any]] = []
    processed_docs: List[Dict[str, Any]] = []

    for f in upload_list:
        file_bytes = await f.read()
        if len(file_bytes) == 0:
            continue

        doc_id = str(uuid.uuid4())
        filename = f.filename

        # Step 1: Extract PDF contents (Images & Tables -> MinIO under users/{username}/...)
        try:
            pages_data, artifacts_data, stats = extract_sop_pdf(
                file_bytes=file_bytes,
                conversation_id=scoped_conv_prefix,
                filename=filename,
            )
        except Exception as e:
            logger.error("Failed extracting PDF '%s': %s", filename, e)
            continue

        # Step 2: Store artifacts in SQLite
        for art in artifacts_data:
            c.execute(
                """INSERT INTO sop_artifacts 
                   (id, conversation_id, document_id, artifact_type, object_name, caption, page, table_markdown, width, height, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    art["id"],
                    conversation_id,
                    doc_id,
                    art["artifact_type"],
                    art["object_name"],
                    art["caption"],
                    art["page"],
                    art["table_markdown"],
                    art.get("width", 0),
                    art.get("height", 0),
                    ts,
                ),
            )

        # Step 3: Hierarchical Chunking tagged with document_id and filename
        _, child_chunks = create_hierarchical_chunks(
            pages_data,
            document_id=doc_id,
            filename=filename,
        )
        all_child_chunks.extend(child_chunks)

        # Step 4: Evaluate SOP against Kenvue guidelines
        full_text = "\n\n".join([p["text"] for p in pages_data if p["text"]])
        evaluation = await evaluate_sop_with_llm(
            sop_text=full_text,
            llm_service_url=LLM_SERVICE_URL,
            provider=provider,
            model=model,
            api_key=api_key,
        )

        # Store document record in SQLite
        c.execute(
            """INSERT INTO sop_documents 
               (id, conversation_id, username, filename, page_count, scores_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (doc_id, conversation_id, username, filename, stats["page_count"], json.dumps(evaluation), ts),
        )

        processed_docs.append({
            "id": doc_id,
            "document_id": doc_id,
            "filename": filename,
            "page_count": stats["page_count"],
            "evaluation": evaluation,
            "scores": evaluation,
            "images_extracted": stats["images_extracted"],
            "tables_extracted": stats["tables_extracted"],
        })

    if not processed_docs:
        c.close()
        raise HTTPException(400, "Could not extract or process any of the uploaded PDF files.")

    # Step 5: Embed all chunks into FAISS HNSW Vector Store
    # Hierarchical Navigable Small World links similar vectors into tight graph clusters
    try:
        vector_store = get_vector_store(conversation_id)
        vector_store.build_and_save(all_child_chunks)
    except Exception as e:
        c.close()
        raise HTTPException(500, f"Failed creating FAISS HNSW vector index: {e}")

    # Step 6: Compute aggregated evaluation metrics across all uploaded SOPs
    avg_score = round(sum(d["evaluation"]["average_score"] for d in processed_docs) / len(processed_docs))
    tmpl_score = round(sum(d["evaluation"]["template_score"] for d in processed_docs) / len(processed_docs))
    read_score = round(sum(d["evaluation"]["readability_score"] for d in processed_docs) / len(processed_docs))
    qual_score = round(sum(d["evaluation"]["quality_score"] for d in processed_docs) / len(processed_docs))

    # Deduplicate improvement suggestions across the batch
    all_suggestions = []
    seen_sug_titles = set()
    for d in processed_docs:
        for sug in d["evaluation"].get("suggestions", []):
            if sug.get("title") not in seen_sug_titles:
                seen_sug_titles.add(sug.get("title"))
                all_suggestions.append(sug)

    aggregated_evaluation = {
        "average_score": avg_score,
        "template_score": tmpl_score,
        "readability_score": read_score,
        "quality_score": qual_score,
        "summary": (
            f"Multi-SOP Collection Assessment ({len(processed_docs)} Documents, {sum(d['page_count'] for d in processed_docs)} Total Pages). "
            f"All procedural vectors clustered in FAISS HNSW graph ({len(all_child_chunks)} chunks indexed)."
            if len(processed_docs) > 1
            else processed_docs[0]["evaluation"].get("summary", "")
        ),
        "suggestions": all_suggestions[:6],
    }

    # Step 7: Auto-update conversation title
    if conv["title"] == "New Chat":
        if len(processed_docs) == 1:
            clean_name = re.sub(r"\.pdf$", "", processed_docs[0]["filename"], flags=re.IGNORECASE).replace("_", " ").replace("-", " ").strip()
            new_title = f"SOP: {clean_name[:28]}"
        else:
            names_summary = ", ".join([re.sub(r"\.pdf$", "", d["filename"], flags=re.IGNORECASE)[:12] for d in processed_docs[:3]])
            if len(processed_docs) > 3:
                names_summary += f" +{len(processed_docs) - 3}"
            new_title = f"SOP Batch ({len(processed_docs)}): {names_summary}"
        c.execute("UPDATE conversations SET title=?, updated_at=? WHERE id=?", (new_title, ts, conversation_id))
    else:
        new_title = conv["title"]

    # Pre-compute similarity analysis if multi-SOP upload
    sim_analysis = None
    if len(processed_docs) > 1:
        try:
            doc_texts_map = {}
            for cc in all_child_chunks:
                did = cc.get("document_id")
                pid = cc.get("parent_id")
                if did not in doc_texts_map:
                    doc_texts_map[did] = {}
                doc_texts_map[did][pid] = cc.get("parent_text", "")

            sim_docs = []
            for pd in processed_docs:
                p_texts = list(doc_texts_map.get(pd["id"], {}).values())
                sim_docs.append({
                    "id": pd["id"],
                    "document_id": pd["id"],
                    "filename": pd["filename"],
                    "original_text": "\n\n".join(p_texts),
                })

            sim_analysis = similarity_engine.analyze_collection(sim_docs, all_child_chunks)
            c.execute(
                "INSERT OR REPLACE INTO sop_similarity_cache (id, conversation_id, analysis_json, updated_at) VALUES (?, ?, ?, ?)",
                (str(uuid.uuid4()), conversation_id, json.dumps(sim_analysis), ts),
            )
        except Exception as e:
            logger.warning("Could not precompute similarity analysis on upload: %s", e)

    c.commit()
    c.close()

    primary_doc = processed_docs[0]
    return {
        "status": "success",
        "has_sop": True,
        "document_count": len(processed_docs),
        "documents": processed_docs,
        "document_id": primary_doc["document_id"],
        "filename": primary_doc["filename"],
        "filenames": [d["filename"] for d in processed_docs],
        "page_count": sum(d["page_count"] for d in processed_docs),
        "conversation_title": new_title,
        "evaluation": aggregated_evaluation if len(processed_docs) > 1 else primary_doc["evaluation"],
        "collection_scores": aggregated_evaluation,
        "index_type": "FAISS HNSW (Hierarchical Navigable Small World)",
        "total_vectors": len(all_child_chunks),
        "similarity_analysis": sim_analysis,
    }


def _enrich_harmonized_version_dict(d: dict, conversation_id: str) -> dict:
    """Standardizes all version attributes, action_type, URLs, and 6-dimension scores for harmonized SOP versions."""
    if "source_document_ids_json" in d and isinstance(d.get("source_document_ids_json"), str):
        d["source_document_ids"] = json.loads(d["source_document_ids_json"]) if d["source_document_ids_json"] else []
    elif "source_document_ids" not in d:
        d["source_document_ids"] = []

    if "source_filenames_json" in d and isinstance(d.get("source_filenames_json"), str):
        d["source_filenames"] = json.loads(d["source_filenames_json"]) if d["source_filenames_json"] else []
    elif "source_filenames" not in d:
        d["source_filenames"] = []

    if "sections_json" in d and isinstance(d.get("sections_json"), str):
        d["sections"] = json.loads(d["sections_json"]) if d["sections_json"] else []
    elif "sections" not in d:
        d["sections"] = []

    if "scores_json" in d and isinstance(d.get("scores_json"), str):
        d["scores"] = json.loads(d["scores_json"]) if d["scores_json"] else {}
    elif "scores" not in d:
        d["scores"] = {}

    if "applied_recommendations_json" in d and isinstance(d.get("applied_recommendations_json"), str):
        d["applied_recommendations"] = json.loads(d["applied_recommendations_json"]) if d["applied_recommendations_json"] else []
    elif "applied_recommendations" not in d:
        d["applied_recommendations"] = []

    sc = d.get("scores") or {}
    ov = sc.get("overall_score") or sc.get("average_score") or d.get("overall_score") or 92
    sc["overall_score"] = ov
    sc["average_score"] = ov
    d["scores"] = sc

    d["overall_score"] = ov
    d["template_score"] = sc.get("template_score") or d.get("template_score", 92)
    d["readability_score"] = sc.get("readability_score") or d.get("readability_score", 90)
    d["quality_score"] = sc.get("quality_score") or d.get("quality_score", 91)
    d["kenvue_alignment_score"] = sc.get("alignment_score") or sc.get("kenvue_alignment_score") or d.get("kenvue_alignment_score", 94)
    d["completeness_score"] = sc.get("completeness_score") or d.get("completeness_score", 95)

    vt = d.get("version_type", "")
    if "harm" in vt or d.get("version_number") == 1:
        d["action_type"] = "harmonize"
    elif "simp" in vt:
        d["action_type"] = "simplify"
    elif "refin" in vt:
        d["action_type"] = "refine"
    else:
        d["action_type"] = "harmonize" if d.get("version_number") == 1 else "refine"

    d["preview_url"] = f"/conversations/{conversation_id}/harmonized-sop/versions/{d['id']}/preview"
    d["download_url"] = f"/conversations/{conversation_id}/harmonized-sop/versions/{d['id']}/download"
    return d


@app.get("/conversations/{conversation_id}/sop")
def get_conversation_sop(conversation_id: str):
    c = db()
    all_docs = c.execute(
        "SELECT * FROM sop_documents WHERE conversation_id=? ORDER BY created_at ASC",
        (conversation_id,),
    ).fetchall()

    if not all_docs:
        c.close()
        return {
            "has_sop": False,
            "document": None,
            "documents": [],
            "document_count": 0,
            "artifacts_count": 0,
            "harmonized_versions_count": 0,
            "harmonized_versions": [],
        }

    artifacts = c.execute(
        "SELECT * FROM sop_artifacts WHERE conversation_id=? ORDER BY page ASC",
        (conversation_id,),
    ).fetchall()

    # Load all harmonized versions
    harm_rows = c.execute(
        "SELECT * FROM harmonized_sop_versions WHERE conversation_id=? ORDER BY version_number ASC",
        (conversation_id,),
    ).fetchall()

    harm_versions = [_enrich_harmonized_version_dict(dict(hr), conversation_id) for hr in harm_rows]

    # Similarity analysis cache or live computation
    sim_analysis = None
    if len(all_docs) > 1:
        cached_sim = c.execute(
            "SELECT analysis_json FROM sop_similarity_cache WHERE conversation_id=?",
            (conversation_id,),
        ).fetchone()
        if cached_sim and cached_sim["analysis_json"]:
            try:
                sim_analysis = json.loads(cached_sim["analysis_json"])
            except Exception:
                pass

        if not sim_analysis:
            meta_path = os.path.join(INDEX_STORAGE_PATH, f"faiss_{conversation_id}_meta.json")
            all_child_chunks = []
            if os.path.exists(meta_path):
                try:
                    with open(meta_path, "r", encoding="utf-8") as f:
                        all_child_chunks = json.load(f)
                except Exception:
                    pass

            doc_texts_map = {}
            for cc in all_child_chunks:
                did = cc.get("document_id")
                pid = cc.get("parent_id")
                if did not in doc_texts_map:
                    doc_texts_map[did] = {}
                doc_texts_map[did][pid] = cc.get("parent_text", "")

            sim_docs = []
            for d in all_docs:
                did = d["id"]
                p_texts = list(doc_texts_map.get(did, {}).values())
                sim_docs.append({
                    "id": did,
                    "document_id": did,
                    "filename": d["filename"],
                    "original_text": "\n\n".join(p_texts),
                })

            sim_analysis = similarity_engine.analyze_collection(sim_docs, all_child_chunks)
            c.execute(
                "INSERT OR REPLACE INTO sop_similarity_cache (id, conversation_id, analysis_json, updated_at) VALUES (?, ?, ?, ?)",
                (str(uuid.uuid4()), conversation_id, json.dumps(sim_analysis), now()),
            )
            c.commit()

    c.close()

    parsed_docs = []
    for d_row in all_docs:
        d_dict = dict(d_row)
        d_dict["scores"] = json.loads(d_dict["scores_json"]) if d_dict.get("scores_json") else None
        d_dict["optimized_scores"] = json.loads(d_dict["optimized_scores_json"]) if d_dict.get("optimized_scores_json") else None
        if d_dict.get("optimized_scores") and not d_dict["optimized_scores"].get("suggestions"):
            d_dict["optimized_scores"]["suggestions"] = [
                {
                    "id": "sug_refine_imperative",
                    "title": "Streamline Procedural Imperative Phrasing",
                    "description": "Further polish step directives into direct, crisp imperative commands without auxiliary verbs.",
                },
                {
                    "id": "sug_refine_tolerances",
                    "title": "Tighten Numerical Tolerances & Critical Limits",
                    "description": "Verify that all equipment temperatures, speeds, and timing include exact ± ranges.",
                },
                {
                    "id": "sug_refine_safety",
                    "title": "Enhance Precautionary Warnings & Interlock Checks",
                    "description": "Ensure personal protective equipment and hazard controls precede mechanical steps.",
                },
                {
                    "id": "sug_refine_qc",
                    "title": "Sharpen In-Process Quality Acceptance Standards",
                    "description": "Ensure clear pass/fail checkpoints with documented supervisory sign-offs.",
                },
            ]
        d_dict["optimized_sections"] = json.loads(d_dict["optimized_sections_json"]) if d_dict.get("optimized_sections_json") else None
        d_dict["optimized_title"] = d_dict.get("optimized_title")
        parsed_docs.append(d_dict)

    # Primary document is the latest
    primary_doc = parsed_docs[-1]

    # Calculate collection composite scores if multiple documents exist
    if len(parsed_docs) > 1:
        avg_s = round(sum(d["scores"]["average_score"] for d in parsed_docs if d["scores"]) / len(parsed_docs))
        tmpl_s = round(sum(d["scores"]["template_score"] for d in parsed_docs if d["scores"]) / len(parsed_docs))
        read_s = round(sum(d["scores"]["readability_score"] for d in parsed_docs if d["scores"]) / len(parsed_docs))
        qual_s = round(sum(d["scores"]["quality_score"] for d in parsed_docs if d["scores"]) / len(parsed_docs))
        collection_scores = {
            "average_score": avg_s,
            "template_score": tmpl_s,
            "readability_score": read_s,
            "quality_score": qual_s,
            "summary": f"Multi-SOP Collection ({len(parsed_docs)} Documents). All procedural vectors clustered in FAISS HNSW index.",
            "suggestions": primary_doc["scores"].get("suggestions", []) if primary_doc["scores"] else [],
        }
    else:
        collection_scores = primary_doc["scores"]

    return {
        "has_sop": True,
        "document": primary_doc,
        "documents": parsed_docs,
        "document_count": len(parsed_docs),
        "collection_scores": collection_scores,
        "artifacts_count": len(artifacts),
        "images_count": len([a for a in artifacts if a["artifact_type"] == "image"]),
        "tables_count": len([a for a in artifacts if a["artifact_type"] == "table"]),
        "has_optimized_sop": any(bool(d.get("optimized_pdf_object_name")) for d in parsed_docs),
        "index_type": "FAISS HNSW (Hierarchical Navigable Small World)",
        "similarity_analysis": sim_analysis,
        "harmonized_versions_count": len(harm_versions),
        "latest_harmonized_version": harm_versions[-1] if harm_versions else None,
        "harmonized_versions": harm_versions,
    }


@app.get("/conversations/{conversation_id}/artifacts")
def get_conversation_artifacts(conversation_id: str):
    c = db()
    rows = c.execute(
        "SELECT * FROM sop_artifacts WHERE conversation_id=? ORDER BY page ASC, created_at ASC",
        (conversation_id,),
    ).fetchall()
    c.close()

    result = []
    for r in rows:
        d = dict(r)
        d["preview_url"] = f"/artifacts/{d['id']}/file"
        result.append(d)
    return result


@app.get("/artifacts/{artifact_id}/file")
def get_artifact_file(artifact_id: str):
    c = db()
    row = c.execute("SELECT object_name, artifact_type FROM sop_artifacts WHERE id=?", (artifact_id,)).fetchone()
    c.close()
    if not row:
        raise HTTPException(404, "Artifact not found")

    data, content_type = minio_storage.get_file_bytes(row["object_name"])
    if not data:
        raise HTTPException(404, "Artifact file not found in MinIO")

    return Response(content=data, media_type=content_type)


# =============================================================
# 5. SOP OPTIMIZATION & REPORTLAB GENERATION
# =============================================================
@app.post("/conversations/{conversation_id}/optimize-sop")
async def optimize_sop(
    conversation_id: str,
    payload: OptimizeRequest,
    x_username: Optional[str] = Header(None, alias="X-User-Name"),
):
    """
    Applies the selected checkbox improvements + custom user instructions.
    Compiles a clean Kenvue-standard PDF via ReportLab, re-inserting all
    original images and tables from MinIO as-is into their original positions.
    Re-evaluates and returns updated comparison scores.
    """
    username = (x_username or "admin").strip().lower()
    c = db()
    if payload.document_id:
        doc = c.execute(
            "SELECT * FROM sop_documents WHERE id=? AND conversation_id=?",
            (payload.document_id, conversation_id),
        ).fetchone()
        if not doc:
            doc = c.execute(
                "SELECT * FROM sop_documents WHERE conversation_id=? ORDER BY created_at DESC LIMIT 1",
                (conversation_id,),
            ).fetchone()
    else:
        doc = c.execute(
            "SELECT * FROM sop_documents WHERE conversation_id=? ORDER BY created_at DESC LIMIT 1",
            (conversation_id,),
        ).fetchone()
    if not doc:
        c.close()
        raise HTTPException(404, "No SOP document found for this conversation.")

    artifacts_rows = c.execute(
        "SELECT * FROM sop_artifacts WHERE conversation_id=? AND (document_id=? OR document_id IS NULL) ORDER BY page ASC",
        (conversation_id, doc["id"]),
    ).fetchall()
    artifacts = [dict(r) for r in artifacts_rows]

    # Check for existing optimized sections to support iterative refinement ("Further Optimize")
    prior_sections = None
    if doc["optimized_sections_json"]:
        try:
            prior_sections = json.loads(doc["optimized_sections_json"])
        except Exception:
            pass
    if not prior_sections:
        # Check MinIO as fallback
        sections_obj_name = f"users/{username}/conversations/{conversation_id}/optimized_sections.json"
        prior_data, _ = minio_storage.get_file_bytes(sections_obj_name)
        if prior_data:
            try:
                prior_sections = json.loads(prior_data.decode("utf-8"))
            except Exception:
                pass

    is_iterative = bool(prior_sections and isinstance(prior_sections, list) and len(prior_sections) >= 3)

    original_text = ""
    if is_iterative:
        # Reconstruct base text directly from the current optimized sections!
        original_text = "\n\n".join([
            f"## {s.get('heading', '')}\n{s.get('content', '')}"
            for s in prior_sections
        ])
    else:
        # Retrieve original text from FAISS chunks or chunks json for initial optimization
        meta_path = os.path.join(INDEX_STORAGE_PATH, f"faiss_{conversation_id}_meta.json")
        if os.path.exists(meta_path):
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    child_chunks = json.load(f)
                seen_p = set()
                p_texts = []
                for cc in child_chunks:
                    pid = cc.get("parent_id")
                    if pid not in seen_p:
                        seen_p.add(pid)
                        p_texts.append(cc.get("parent_text", ""))
                original_text = "\n\n".join(p_texts)
            except Exception:
                pass

    # Resolve baseline scores and available suggestions
    if is_iterative and doc["optimized_scores_json"]:
        try:
            baseline_scores = json.loads(doc["optimized_scores_json"])
        except Exception:
            baseline_scores = json.loads(doc["scores_json"]) if doc["scores_json"] else {}
    else:
        baseline_scores = json.loads(doc["scores_json"]) if doc["scores_json"] else {}

    available_suggs = baseline_scores.get("suggestions", [])
    selected_suggs = [s for s in available_suggs if s.get("id") in payload.selected_suggestion_ids]
    if not selected_suggs and payload.selected_suggestion_ids:
        # If user picked suggestions by title or custom ID
        selected_suggs = [{"title": sid, "description": sid} for sid in payload.selected_suggestion_ids]

    prior_title = doc["optimized_title"] if ("optimized_title" in doc.keys() and doc["optimized_title"]) else None
    if not prior_title and prior_sections:
        for s in prior_sections:
            c_text = s.get("content", "")
            m_dt = re.search(r"Document Title:\s*([^\n\r]+)", c_text, re.IGNORECASE)
            if m_dt:
                prior_title = m_dt.group(1).strip()
                break
            m_p1 = re.search(r"(?:The purpose of this (?:procedure|Standard Operating Procedure)\s*\(([^)]+)\)|本標準作業手順書\s*\(([^)]+)\))", c_text)
            if m_p1:
                cand = (m_p1.group(1) or m_p1.group(2) or "").strip()
                if cand:
                    prior_title = cand
                    break
    if not prior_title:
        conv_row = c.execute("SELECT title FROM conversations WHERE id=?", (conversation_id,)).fetchone()
        if conv_row and conv_row["title"] and conv_row["title"].startswith("SOP: "):
            prior_title = conv_row["title"].replace("SOP: ", "").strip()

    settings_rows = c.execute("SELECT key, value FROM settings").fetchall()
    config = {r["key"]: r["value"] for r in settings_rows}

    provider = config.get("provider", "groq")
    default_model = "openai/gpt-oss-120b" if provider == "groq" else "gemini-2.5-flash"
    raw_model = config.get("model", default_model)
    model = LEGACY_MODEL_MAP.get(raw_model, raw_model)
    api_key = config.get(f"{provider}_api_key") or config.get("api_key", "")
    if not api_key:
        api_key = os.getenv("GROQ_API_KEY" if provider == "groq" else "GEMINI_API_KEY", "")

    c.close()

    # Execute optimization and ReportLab PDF build with iterative baseline
    opt_result = await generate_optimized_sop(
        conversation_id=conversation_id,
        username=username,
        original_text=original_text,
        original_filename=doc["filename"],
        selected_suggestions=selected_suggs,
        custom_instructions=payload.custom_instructions,
        artifacts=artifacts,
        llm_service_url=LLM_SERVICE_URL,
        provider=provider,
        model=model,
        api_key=api_key,
        existing_sections=prior_sections if is_iterative else None,
        existing_title=prior_title,
    )

    c = db()
    # Update conversation title in SQLite if custom title was specified
    new_doc_title = opt_result.get("document_title")
    if new_doc_title:
        c.execute(
            "UPDATE conversations SET title=?, updated_at=? WHERE id=?",
            (f"SOP: {new_doc_title}", now(), conversation_id),
        )

    # Save updated scores, optimized PDF object name, sections JSON, and title to SQLite
    c.execute(
        """UPDATE sop_documents 
           SET optimized_scores_json=?, optimized_pdf_object_name=?, optimized_sections_json=?, optimized_title=? 
           WHERE id=?""",
        (
            json.dumps(opt_result["updated_scores"]),
            opt_result["object_name"],
            json.dumps(opt_result.get("sections", [])),
            new_doc_title,
            doc["id"],
        ),
    )
    c.commit()
    c.close()

    # Re-index the newly generated SOP into FAISS vector index
    try:
        pdf_data, _ = minio_storage.get_file_bytes(opt_result["object_name"])
        opt_pages_data = []
        if pdf_data:
            import pymupdf
            opt_pdf_doc = pymupdf.open(stream=pdf_data, filetype="pdf")
            for p_num in range(len(opt_pdf_doc)):
                p_text = opt_pdf_doc[p_num].get_text("text").strip()
                if p_text:
                    opt_pages_data.append({"page": p_num + 1, "text": p_text})
            opt_pdf_doc.close()

        if not opt_pages_data and opt_result.get("sections"):
            opt_pages_data = [
                {"page": idx + 1, "text": f"{s.get('heading', '')}\n\n{s.get('content', '')}"}
                for idx, s in enumerate(opt_result["sections"])
            ]

        if opt_pages_data:
            _, child_chunks = create_hierarchical_chunks(opt_pages_data)
            vector_store = get_vector_store(conversation_id)
            vector_store.build_and_save(child_chunks)
            logger.info(
                "Successfully re-indexed FAISS embeddings for optimized SOP in conversation %s (%d child chunks)",
                conversation_id,
                len(child_chunks),
            )
    except Exception as e:
        logger.error("Failed to re-index FAISS embeddings for optimized SOP: %s", e)

    return {
        "status": "success",
        "document_title": new_doc_title,
        "title": new_doc_title,
        "optimized_title": new_doc_title,
        "is_iterative": is_iterative,
        "previous_scores": baseline_scores,
        "updated_scores": opt_result["updated_scores"],
        "validation_report": opt_result.get("validation_report"),
        "pdf_download_url": f"/conversations/{conversation_id}/optimized-sop/download",
        "pdf_preview_url": f"/conversations/{conversation_id}/optimized-sop/preview",
        "skill_url": f"/conversations/{conversation_id}/optimization-skill",
        "skill_object_name": opt_result.get("skill_object_name"),
        "summary": opt_result["summary"],
    }


@app.get("/conversations/{conversation_id}/optimized-sop/download")
def download_optimized_sop(conversation_id: str, document_id: Optional[str] = None):
    c = db()
    if document_id:
        doc = c.execute(
            "SELECT optimized_pdf_object_name, filename FROM sop_documents WHERE conversation_id=? AND id=? AND optimized_pdf_object_name IS NOT NULL",
            (conversation_id, document_id),
        ).fetchone()
    else:
        doc = c.execute(
            "SELECT optimized_pdf_object_name, filename FROM sop_documents WHERE conversation_id=? AND optimized_pdf_object_name IS NOT NULL ORDER BY created_at DESC LIMIT 1",
            (conversation_id,),
        ).fetchone()
    c.close()
    if not doc or not doc["optimized_pdf_object_name"]:
        raise HTTPException(404, "No optimized SOP PDF generated yet.")

    data, content_type = minio_storage.get_file_bytes(doc["optimized_pdf_object_name"])
    if not data:
        raise HTTPException(404, "Optimized PDF not found in MinIO.")

    safe_name = f"Optimized_{doc['filename']}"
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={safe_name}"},
    )


@app.get("/conversations/{conversation_id}/optimized-sop/preview")
def preview_optimized_sop(conversation_id: str, document_id: Optional[str] = None):
    c = db()
    if document_id:
        doc = c.execute(
            "SELECT optimized_pdf_object_name FROM sop_documents WHERE conversation_id=? AND id=? AND optimized_pdf_object_name IS NOT NULL",
            (conversation_id, document_id),
        ).fetchone()
    else:
        doc = c.execute(
            "SELECT optimized_pdf_object_name FROM sop_documents WHERE conversation_id=? AND optimized_pdf_object_name IS NOT NULL ORDER BY created_at DESC LIMIT 1",
            (conversation_id,),
        ).fetchone()
    c.close()
    if not doc or not doc["optimized_pdf_object_name"]:
        raise HTTPException(404, "No optimized SOP PDF generated yet.")

    data, content_type = minio_storage.get_file_bytes(doc["optimized_pdf_object_name"])
    if not data:
        raise HTTPException(404, "Optimized PDF not found in MinIO.")

    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": "inline"},
    )


@app.get("/conversations/{conversation_id}/optimization-skill")
def get_conversation_optimization_skill(
    conversation_id: str,
    x_username: Optional[str] = Header(None, alias="X-User-Name"),
):
    """
    Returns the dynamically compiled Optimization Directive & Skill Recipe
    for this chat session from MinIO.
    """
    username = (x_username or "admin").strip().lower()
    skill_object = f"users/{username}/conversations/{conversation_id}/optimization_skill.md"
    data, _ = minio_storage.get_file_bytes(skill_object)
    if not data:
        raise HTTPException(404, "Optimization skill file not found in MinIO for this session.")

    return Response(content=data, media_type="text/markdown; charset=utf-8")


@app.get("/skills/audit")
def get_master_audit_skill():
    """Returns the Master Kenvue SOP Audit & Scoring Skill markdown."""
    from skill_manager import skill_manager
    content = skill_manager.get_audit_skill()
    return {"skill": "kenvue_audit_skill.md", "content": content}


# =============================================================
# 5B. MULTI-SOP SIMILARITY, HARMONIZATION, & SIMPLIFICATION WORKFLOW
# =============================================================
@app.get("/conversations/{conversation_id}/similarity-analysis")
def get_similarity_analysis(conversation_id: str):
    """
    Performs or retrieves multi-SOP pairwise similarity, procedural overlap,
    parameter conflict analysis, and similarity clustering for uploaded SOPs.
    """
    c = db()
    all_docs = c.execute(
        "SELECT * FROM sop_documents WHERE conversation_id=? ORDER BY created_at ASC",
        (conversation_id,),
    ).fetchall()

    if len(all_docs) < 2:
        c.close()
        return {
            "has_similarity_analysis": False,
            "document_count": len(all_docs),
            "analysis": {
                "groups": [],
                "pairwise_matrix": [],
                "executive_summary": "Single SOP uploaded. Upload additional SOPs to enable multi-document similarity analysis and harmonization.",
                "has_duplicates_or_overlaps": False,
                "recommended_harmonize_ids": [],
            },
        }

    # Check cache first
    cached = c.execute(
        "SELECT analysis_json FROM sop_similarity_cache WHERE conversation_id=?",
        (conversation_id,),
    ).fetchone()
    if cached and cached["analysis_json"]:
        c.close()
        try:
            analysis_data = json.loads(cached["analysis_json"])
            res = {
                "has_similarity_analysis": True,
                "document_count": len(all_docs),
                "analysis": analysis_data,
            }
            if isinstance(analysis_data, dict):
                res.update(analysis_data)
            return res
        except Exception:
            pass

    # Read child chunks from FAISS metadata
    meta_path = os.path.join(INDEX_STORAGE_PATH, f"faiss_{conversation_id}_meta.json")
    all_child_chunks = []
    if os.path.exists(meta_path):
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                all_child_chunks = json.load(f)
        except Exception as e:
            logger.warning("Could not read meta chunks: %s", e)

    doc_texts_map = {}
    for cc in all_child_chunks:
        did = cc.get("document_id")
        pid = cc.get("parent_id")
        if did not in doc_texts_map:
            doc_texts_map[did] = {}
        doc_texts_map[did][pid] = cc.get("parent_text", "")

    sim_docs = []
    for d in all_docs:
        did = d["id"]
        p_texts = list(doc_texts_map.get(did, {}).values())
        sim_docs.append({
            "id": did,
            "document_id": did,
            "filename": d["filename"],
            "original_text": "\n\n".join(p_texts),
        })

    analysis_result = similarity_engine.analyze_collection(sim_docs, all_child_chunks)
    c = db()
    c.execute(
        "INSERT OR REPLACE INTO sop_similarity_cache (id, conversation_id, analysis_json, updated_at) VALUES (?, ?, ?, ?)",
        (str(uuid.uuid4()), conversation_id, json.dumps(analysis_result), now()),
    )
    c.commit()
    c.close()

    res = {
        "has_similarity_analysis": True,
        "document_count": len(all_docs),
        "analysis": analysis_result,
    }
    if isinstance(analysis_result, dict):
        res.update(analysis_result)
    return res


@app.post("/conversations/{conversation_id}/harmonize-sops")
async def harmonize_sops(
    conversation_id: str,
    payload: HarmonizeRequest,
    x_username: Optional[str] = Header(None, alias="X-User-Name"),
):
    """
    Intelligently consolidates selected similar SOPs into a single standardized Kenvue SOP:
    - Resolves procedural divergences to conservative GMP tolerances
    - Eliminates redundant steps while preserving unique rules and MinIO media
    - Applies parallel optimization and QA agents
    - Stores harmonized SOP v1 permanently in SQLite and MinIO with full lineage.
    """
    username = (x_username or "admin").strip().lower()
    if not payload.selected_document_ids or len(payload.selected_document_ids) < 2:
        raise HTTPException(400, "Please select at least 2 SOP documents to harmonize.")

    c = db()
    all_docs = c.execute(
        "SELECT * FROM sop_documents WHERE conversation_id=?",
        (conversation_id,),
    ).fetchall()

    selected_docs = [
        dict(d) for d in all_docs
        if d["id"] in payload.selected_document_ids or d["filename"] in payload.selected_document_ids
    ]

    if len(selected_docs) < 2:
        c.close()
        raise HTTPException(400, "Could not find at least 2 matching SOP documents to harmonize.")

    meta_path = os.path.join(INDEX_STORAGE_PATH, f"faiss_{conversation_id}_meta.json")
    all_child_chunks = []
    if os.path.exists(meta_path):
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                all_child_chunks = json.load(f)
        except Exception as e:
            logger.warning("Could not load chunks: %s", e)

    doc_texts_map = {}
    for cc in all_child_chunks:
        did = cc.get("document_id")
        pid = cc.get("parent_id")
        if did not in doc_texts_map:
            doc_texts_map[did] = {}
        doc_texts_map[did][pid] = cc.get("parent_text", "")

    source_documents = []
    for d in selected_docs:
        did = d["id"]
        p_texts = list(doc_texts_map.get(did, {}).values())
        source_documents.append({
            "id": did,
            "document_id": did,
            "filename": d["filename"],
            "original_text": "\n\n".join(p_texts),
            "scores": json.loads(d["scores_json"]) if d.get("scores_json") else None,
        })

    # Fetch artifacts for selected documents
    doc_ids = [d["id"] for d in selected_docs]
    placeholders = ",".join(["?"] * len(doc_ids))
    artifacts_rows = c.execute(
        f"SELECT * FROM sop_artifacts WHERE conversation_id=? AND document_id IN ({placeholders}) ORDER BY page ASC",
        (conversation_id, *doc_ids),
    ).fetchall()
    all_artifacts = [dict(r) for r in artifacts_rows]

    # Resolve LLM configuration
    settings_rows = c.execute("SELECT key, value FROM settings").fetchall()
    config = {r["key"]: r["value"] for r in settings_rows}

    provider = config.get("provider", "groq")
    default_model = "openai/gpt-oss-120b" if provider == "groq" else "gemini-2.5-flash"
    raw_model = config.get("model", default_model)
    model = LEGACY_MODEL_MAP.get(raw_model, raw_model)
    api_key = config.get(f"{provider}_api_key") or config.get("api_key", "")
    if not api_key:
        api_key = os.getenv("GROQ_API_KEY" if provider == "groq" else "GEMINI_API_KEY", "")

    c.close()

    try:
        harm_result = await harmonization_engine.harmonize_sops(
            conversation_id=conversation_id,
            username=username,
            source_documents=source_documents,
            custom_instructions=payload.custom_instructions,
            title_override=payload.title_override,
            all_artifacts=all_artifacts,
            llm_service_url=LLM_SERVICE_URL,
            provider=provider,
            model=model,
            api_key=api_key,
        )
    except Exception as exc:
        logger.exception("Harmonization failed: %s", exc)
        raise HTTPException(500, f"Harmonization process failed: {exc}")

    c = db()
    # Determine version number
    existing_versions = c.execute(
        "SELECT COUNT(*) as count FROM harmonized_sop_versions WHERE conversation_id=?",
        (conversation_id,),
    ).fetchone()
    v_num = (existing_versions["count"] or 0) + 1
    harm_result["version_number"] = v_num
    harm_result["version_label"] = f"Harmonized SOP v{v_num} (Initial Harmonized Release)"

    # Persist version immutably
    c.execute(
        """INSERT INTO harmonized_sop_versions (
            id, conversation_id, username, version_number, version_label, version_type,
            parent_version_id, source_document_ids_json, source_filenames_json,
            title, markdown_content, sections_json, scores_json, change_summary,
            applied_recommendations_json, user_prompt, pdf_object_name, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            harm_result["id"],
            conversation_id,
            username,
            harm_result["version_number"],
            harm_result["version_label"],
            harm_result["version_type"],
            harm_result["parent_version_id"],
            json.dumps(harm_result["source_document_ids"]),
            json.dumps(harm_result["source_filenames"]),
            harm_result["title"],
            harm_result["markdown_content"],
            json.dumps(harm_result["sections"]),
            json.dumps(harm_result["scores"]),
            harm_result["change_summary"],
            json.dumps(harm_result.get("applied_recommendations", [])),
            harm_result.get("user_prompt", ""),
            harm_result["pdf_object_name"],
            now(),
        ),
    )
    c.commit()
    c.close()

    return _enrich_harmonized_version_dict(harm_result, conversation_id)


@app.get("/conversations/{conversation_id}/harmonized-sop/versions")
def get_harmonized_versions(conversation_id: str):
    """Returns complete version history and lineage of all harmonized SOPs for this session."""
    c = db()
    rows = c.execute(
        "SELECT * FROM harmonized_sop_versions WHERE conversation_id=? ORDER BY version_number ASC",
        (conversation_id,),
    ).fetchall()
    c.close()

    return [_enrich_harmonized_version_dict(dict(r), conversation_id) for r in rows]


@app.get("/conversations/{conversation_id}/harmonized-sop/versions/{version_id}")
def get_harmonized_version_by_id(conversation_id: str, version_id: str):
    """Retrieves full details for a specific harmonized SOP version."""
    c = db()
    row = c.execute(
        "SELECT * FROM harmonized_sop_versions WHERE id=? AND conversation_id=?",
        (version_id, conversation_id),
    ).fetchone()
    c.close()
    if not row:
        raise HTTPException(404, "Harmonized SOP version not found")

    return _enrich_harmonized_version_dict(dict(row), conversation_id)


@app.get("/conversations/{conversation_id}/harmonized-sop/simplification-suggestions")
def get_simplification_suggestions(conversation_id: str):
    """Returns available simplification recommendations catalog with descriptions and benefits."""
    return {"catalog": SIMPLIFICATION_CATALOG}


@app.post("/conversations/{conversation_id}/harmonized-sop/simplify")
async def simplify_harmonized_sop(
    conversation_id: str,
    payload: SimplifyRequest,
    x_username: Optional[str] = Header(None, alias="X-User-Name"),
):
    """
    Applies user-selected simplification recommendations and generates a NEW version
    (e.g., Harmonized SOP v2). NEVER overwrites previous versions!
    """
    username = (x_username or "admin").strip().lower()
    c = db()
    if payload.version_id:
        v_row = c.execute(
            "SELECT * FROM harmonized_sop_versions WHERE id=? AND conversation_id=?",
            (payload.version_id, conversation_id),
        ).fetchone()
    else:
        v_row = c.execute(
            "SELECT * FROM harmonized_sop_versions WHERE conversation_id=? ORDER BY version_number DESC LIMIT 1",
            (conversation_id,),
        ).fetchone()

    if not v_row:
        c.close()
        raise HTTPException(404, "No harmonized SOP version found to simplify.")

    current_version = {
        "id": v_row["id"],
        "conversation_id": v_row["conversation_id"],
        "version_number": v_row["version_number"],
        "version_label": v_row["version_label"],
        "source_document_ids": json.loads(v_row["source_document_ids_json"]),
        "source_filenames": json.loads(v_row["source_filenames_json"]),
        "title": v_row["title"],
        "sections": json.loads(v_row["sections_json"]),
        "scores": json.loads(v_row["scores_json"]),
        "pdf_object_name": v_row["pdf_object_name"],
    }

    artifacts_rows = c.execute(
        "SELECT * FROM sop_artifacts WHERE conversation_id=? ORDER BY page ASC",
        (conversation_id,),
    ).fetchall()
    all_artifacts = [dict(r) for r in artifacts_rows]

    rec_ids = payload.selected_recommendation_ids
    if not rec_ids:
        rec_ids = [r["id"] for r in SIMPLIFICATION_CATALOG]

    new_v = harmonization_engine.simplify_sop(
        current_version=current_version,
        selected_recommendation_ids=rec_ids,
        custom_instructions=payload.custom_instructions,
        conversation_id=conversation_id,
        username=username,
        all_artifacts=all_artifacts,
    )

    c.execute(
        """INSERT INTO harmonized_sop_versions (
            id, conversation_id, username, version_number, version_label, version_type,
            parent_version_id, source_document_ids_json, source_filenames_json,
            title, markdown_content, sections_json, scores_json, change_summary,
            applied_recommendations_json, user_prompt, pdf_object_name, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            new_v["id"],
            conversation_id,
            username,
            new_v["version_number"],
            new_v["version_label"],
            new_v["version_type"],
            new_v["parent_version_id"],
            json.dumps(new_v["source_document_ids"]),
            json.dumps(new_v["source_filenames"]),
            new_v["title"],
            new_v["markdown_content"],
            json.dumps(new_v["sections"]),
            json.dumps(new_v["scores"]),
            new_v["change_summary"],
            json.dumps(new_v["applied_recommendations"]),
            new_v["user_prompt"],
            new_v["pdf_object_name"],
            now(),
        ),
    )
    c.commit()
    c.close()

    return _enrich_harmonized_version_dict(new_v, conversation_id)


@app.post("/conversations/{conversation_id}/harmonized-sop/refine")
async def refine_harmonized_sop(
    conversation_id: str,
    payload: RefineRequest,
    x_username: Optional[str] = Header(None, alias="X-User-Name"),
):
    """
    Applies user's interactive refinement prompt (e.g., 'Make Section 3 easier to understand')
    and creates a NEW harmonized SOP version (e.g., v3). Preserves lineage and history!
    """
    username = (x_username or "admin").strip().lower()
    c = db()
    if payload.version_id:
        v_row = c.execute(
            "SELECT * FROM harmonized_sop_versions WHERE id=? AND conversation_id=?",
            (payload.version_id, conversation_id),
        ).fetchone()
    else:
        v_row = c.execute(
            "SELECT * FROM harmonized_sop_versions WHERE conversation_id=? ORDER BY version_number DESC LIMIT 1",
            (conversation_id,),
        ).fetchone()

    if not v_row:
        c.close()
        raise HTTPException(404, "No harmonized SOP version found to refine.")

    current_version = {
        "id": v_row["id"],
        "conversation_id": v_row["conversation_id"],
        "version_number": v_row["version_number"],
        "version_label": v_row["version_label"],
        "source_document_ids": json.loads(v_row["source_document_ids_json"]),
        "source_filenames": json.loads(v_row["source_filenames_json"]),
        "title": v_row["title"],
        "sections": json.loads(v_row["sections_json"]),
        "scores": json.loads(v_row["scores_json"]),
        "pdf_object_name": v_row["pdf_object_name"],
    }

    artifacts_rows = c.execute(
        "SELECT * FROM sop_artifacts WHERE conversation_id=? ORDER BY page ASC",
        (conversation_id,),
    ).fetchall()
    all_artifacts = [dict(r) for r in artifacts_rows]

    new_v = harmonization_engine.refine_sop(
        current_version=current_version,
        refinement_prompt=payload.refinement_prompt,
        conversation_id=conversation_id,
        username=username,
        all_artifacts=all_artifacts,
    )

    c.execute(
        """INSERT INTO harmonized_sop_versions (
            id, conversation_id, username, version_number, version_label, version_type,
            parent_version_id, source_document_ids_json, source_filenames_json,
            title, markdown_content, sections_json, scores_json, change_summary,
            applied_recommendations_json, user_prompt, pdf_object_name, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            new_v["id"],
            conversation_id,
            username,
            new_v["version_number"],
            new_v["version_label"],
            new_v["version_type"],
            new_v["parent_version_id"],
            json.dumps(new_v["source_document_ids"]),
            json.dumps(new_v["source_filenames"]),
            new_v["title"],
            new_v["markdown_content"],
            json.dumps(new_v["sections"]),
            json.dumps(new_v["scores"]),
            new_v["change_summary"],
            json.dumps(new_v["applied_recommendations"]),
            new_v["user_prompt"],
            new_v["pdf_object_name"],
            now(),
        ),
    )
    c.commit()
    c.close()

    return _enrich_harmonized_version_dict(new_v, conversation_id)


@app.get("/conversations/{conversation_id}/harmonized-sop/versions/{version_id}/preview")
def preview_harmonized_version_pdf(conversation_id: str, version_id: str):
    """Previews the PDF for a specific harmonized version."""
    c = db()
    row = c.execute(
        "SELECT * FROM harmonized_sop_versions WHERE id=? AND conversation_id=?",
        (version_id, conversation_id),
    ).fetchone()
    c.close()
    if not row:
        raise HTTPException(404, "Harmonized SOP version not found")

    pdf_data, content_type = minio_storage.get_file_bytes(row["pdf_object_name"])
    if not pdf_data:
        raise HTTPException(404, "PDF file not found in storage")

    safe_title = re.sub(r"[^\w\-_.]", "_", row["title"])
    fname = f"Harmonized_SOP_v{row['version_number']}_{safe_title}.pdf"
    return Response(
        content=pdf_data,
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename=\"{fname}\""},
    )


@app.get("/conversations/{conversation_id}/harmonized-sop/versions/{version_id}/download")
def download_harmonized_version_pdf(conversation_id: str, version_id: str):
    """Downloads the PDF for a specific harmonized version."""
    c = db()
    row = c.execute(
        "SELECT * FROM harmonized_sop_versions WHERE id=? AND conversation_id=?",
        (version_id, conversation_id),
    ).fetchone()
    c.close()
    if not row:
        raise HTTPException(404, "Harmonized SOP version not found")

    pdf_data, content_type = minio_storage.get_file_bytes(row["pdf_object_name"])
    if not pdf_data:
        raise HTTPException(404, "PDF file not found in storage")

    safe_title = re.sub(r"[^\w\-_.]", "_", row["title"])
    fname = f"Harmonized_SOP_v{row['version_number']}_{safe_title}.pdf"
    return Response(
        content=pdf_data,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=\"{fname}\""},
    )


# =============================================================
# 6. END CHAT & LIFECYCLE CLEANUP
# =============================================================
@app.post("/conversations/{conversation_id}/end-chat")
async def end_chat(conversation_id: str, x_username: Optional[str] = Header(None, alias="X-User-Name")):
    """
    Concludes the session while strictly preserving all version lineage:
    1. Archives comprehensive summary of chat, SOPs, and Harmonized Version history to MinIO.
    2. Retains all generated Harmonized SOP PDFs and SQLite version records permanently.
    3. Cleans up temporary intermediate image/table crops and vector index files.
    """
    username = (x_username or "admin").strip().lower()
    c = db()
    conv = c.execute("SELECT * FROM conversations WHERE id=?", (conversation_id,)).fetchone()
    if not conv:
        c.close()
        raise HTTPException(404, "Conversation not found")

    messages = c.execute(
        "SELECT role, content FROM messages WHERE conversation_id=? ORDER BY created_at ASC",
        (conversation_id,),
    ).fetchall()

    all_docs = c.execute(
        "SELECT * FROM sop_documents WHERE conversation_id=? ORDER BY created_at ASC",
        (conversation_id,),
    ).fetchall()

    harm_versions = c.execute(
        "SELECT * FROM harmonized_sop_versions WHERE conversation_id=? ORDER BY version_number ASC",
        (conversation_id,),
    ).fetchall()

    artifacts = c.execute(
        "SELECT object_name FROM sop_artifacts WHERE conversation_id=?",
        (conversation_id,),
    ).fetchall()

    # Step 1: Generate comprehensive summary with full lineage
    summary_text = (
        f"KENVUE SOP OPTIMIZATION SESSION SUMMARY\n"
        f"=======================================\n"
        f"User: {username}\n"
        f"Conversation ID: {conversation_id}\n"
        f"Title: {conv['title']}\n"
        f"Date: {now()}\n"
        f"Total SOPs Uploaded: {len(all_docs)}\n"
    )
    for i, d in enumerate(all_docs):
        d_scores = json.loads(d["scores_json"]) if d["scores_json"] else {}
        opt_s = json.loads(d["optimized_scores_json"]) if d["optimized_scores_json"] else None
        summary_text += f"\n[SOP {i+1}]: {d['filename']} (Pages: {d['page_count']})\n"
        summary_text += f"  Initial Scores: Template: {d_scores.get('template_score')}, Readability: {d_scores.get('readability_score')}, Quality: {d_scores.get('quality_score')}, Avg: {d_scores.get('average_score')}%\n"
        if opt_s:
            summary_text += f"  Optimized Scores: Template: {opt_s.get('template_score')}, Readability: {opt_s.get('readability_score')}, Quality: {opt_s.get('quality_score')}, Avg: {opt_s.get('average_score')}%\n"

    if harm_versions:
        summary_text += f"\n--- HARMONIZED SOP VERSION HISTORY & LINEAGE ---\n"
        summary_text += f"Total Harmonized Versions Generated: {len(harm_versions)}\n"
        for hv in harm_versions:
            v_scores = json.loads(hv["scores_json"]) if hv["scores_json"] else {}
            v_sources = json.loads(hv["source_filenames_json"]) if hv["source_filenames_json"] else []
            v_recs = json.loads(hv["applied_recommendations_json"]) if hv["applied_recommendations_json"] else []
            summary_text += (
                f"\nVersion {hv['version_number']}: {hv['version_label']}\n"
                f"  Type: {hv['version_type']}\n"
                f"  Parent Version ID: {hv['parent_version_id'] or 'None (Root Initial Harmonization)'}\n"
                f"  Source SOPs: {', '.join(v_sources)}\n"
                f"  PDF Object: {hv['pdf_object_name']}\n"
                f"  Scores: Overall: {v_scores.get('average_score')}%, Template: {v_scores.get('template_score')}%, Readability: {v_scores.get('readability_score')}%, Quality: {v_scores.get('quality_score')}%\n"
                f"  Change Summary: {hv['change_summary']}\n"
            )
            if v_recs:
                summary_text += f"  Applied Simplifications: {', '.join(v_recs)}\n"
            if hv["user_prompt"]:
                summary_text += f"  User Prompt: {hv['user_prompt']}\n"
        summary_text += "\nLINEAGE STATUS: All Harmonized SOP Versions & Original PDFs Permanently Retained in MinIO & SQLite.\n"

    summary_text += f"\nTotal Messages Exchanged: {len(messages)}\n\n--- CONVERSATION TRANSCRIPT ---\n"
    for m in messages:
        summary_text += f"[{m['role'].upper()}]: {m['content']}\n\n"

    # Step 2: Upload session summary to MinIO under users/{username}/summaries/
    summary_object_name = f"users/{username}/summaries/{conversation_id}_summary.txt"
    minio_storage.upload_file_bytes(
        object_name=summary_object_name,
        data=summary_text.encode("utf-8"),
        content_type="text/plain",
        metadata={"username": username, "conversation_id": conversation_id, "type": "chat_summary"},
    )

    # Step 3: Cleanup intermediate extracted images and table crops from MinIO
    for art in artifacts:
        try:
            minio_storage.remove_file(art["object_name"])
        except Exception as e:
            logger.warning("Could not delete artifact %s: %s", art["object_name"], e)

    # Step 4: Cleanup FAISS vector index files from disk
    index_file = os.path.join(INDEX_STORAGE_PATH, f"faiss_{conversation_id}.index")
    meta_file = os.path.join(INDEX_STORAGE_PATH, f"faiss_{conversation_id}_meta.json")
    for f_path in (index_file, meta_file):
        if os.path.exists(f_path):
            try:
                os.remove(f_path)
            except Exception:
                pass

    # Step 5: Clean up temporary artifacts records from SQLite & mark conversation ended
    c.execute("DELETE FROM sop_artifacts WHERE conversation_id=?", (conversation_id,))
    c.execute("UPDATE conversations SET status='ended', updated_at=? WHERE id=?", (now(), conversation_id))
    c.commit()
    c.close()

    logger.info("Ended conversation %s. Lineage preserved in MinIO (%s); intermediate vectors and media purged.", conversation_id, summary_object_name)

    return {
        "status": "ended",
        "summary_object_name": summary_object_name,
        "summary_url": f"/conversations/{conversation_id}/summary",
        "message": f"Session concluded. Summary with complete version lineage saved to MinIO ({summary_object_name}). Intermediate media and vector embeddings have been cleaned up.",
    }


@app.get("/conversations/{conversation_id}/summary")
def get_conversation_summary(conversation_id: str, x_username: Optional[str] = Header(None, alias="X-User-Name")):
    """Retrieves the archived session summary text and version lineage from MinIO."""
    username = (x_username or "admin").strip().lower()
    summary_object_name = f"users/{username}/summaries/{conversation_id}_summary.txt"
    data, ctype = minio_storage.get_file_bytes(summary_object_name)
    if not data:
        raise HTTPException(404, "Summary not found for this conversation.")
    return Response(content=data, media_type="text/plain; charset=utf-8")


# =============================================================
# 7. CHAT WITH RAG & 1-LINE CHATGPT-STYLE HISTORY SUMMARIES
# =============================================================
async def generate_chat_title_summary(provider: str, model: str, api_key: str, message_text: str) -> str:
    prompt = (
        "You are a helpful naming assistant like ChatGPT. "
        "Summarize the following user request into a concise 3 to 5 word title for the chat history sidebar. "
        "Do NOT include punctuation, quotes, or markdown. Output ONLY the short title.\n\n"
        f"User message: {message_text}\n"
        "Title:"
    )

    body = {
        "provider": provider,
        "model": model,
        "api_key": api_key,
        "messages": [{"role": "user", "content": prompt}],
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            res = await client.post(f"{LLM_SERVICE_URL}/generate", json=body)
        if res.status_code == 200:
            raw_title = res.json().get("content", "").strip()
            clean = re.sub(r'["\'\*\#]', "", raw_title).split("\n")[0].strip()
            if clean.lower().startswith("title:"):
                clean = clean[6:].strip()
            if len(clean) >= 3 and len(clean) <= 40:
                return clean
    except Exception:
        pass

    words = message_text.strip().split()
    fallback_title = " ".join(words[:5])
    if len(words) > 5:
        fallback_title += "..."
    return fallback_title[:32].capitalize()


@app.post("/chat")
async def chat(payload: MessageRequest):
    c = db()
    conv = c.execute("SELECT * FROM conversations WHERE id=?", (payload.conversation_id,)).fetchone()
    if not conv:
        c.close()
        raise HTTPException(404, "Conversation not found")

    c.execute(
        "INSERT INTO messages VALUES (?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), payload.conversation_id, "user", payload.content, now()),
    )
    history = c.execute(
        "SELECT role, content FROM messages WHERE conversation_id=? ORDER BY created_at ASC",
        (payload.conversation_id,),
    ).fetchall()
    c.commit()

    config = {r["key"]: r["value"] for r in c.execute("SELECT key,value FROM settings").fetchall()}
    c.close()

    provider = config.get("provider", "groq")
    default_model = "openai/gpt-oss-120b" if provider == "groq" else "gemini-2.5-flash"
    raw_model = config.get("model", default_model)
    model = LEGACY_MODEL_MAP.get(raw_model, raw_model)
    api_key = config.get(f"{provider}_api_key") or config.get("api_key", "")
    if not api_key:
        api_key = os.getenv("GROQ_API_KEY" if provider == "groq" else "GEMINI_API_KEY", "")

    # Retrieve relevant SOP chunks via FAISS HNSW
    vector_store = get_vector_store(payload.conversation_id)
    retrieved_chunks = []
    rag_context_blocks = []

    if vector_store.index is not None and vector_store.index.ntotal > 0:
        retrieved_chunks = vector_store.search(payload.content, top_k=6)
        if retrieved_chunks:
            seen_parents = set()
            for chunk in retrieved_chunks:
                p_id = chunk.get("parent_id")
                if p_id in seen_parents:
                    continue
                seen_parents.add(p_id)
                page = chunk.get("page", 1)
                doc_name = chunk.get("filename", "")
                parent_text = chunk.get("parent_text") or chunk.get("child_text", "")
                if doc_name:
                    rag_context_blocks.append(f"--- [Document: {doc_name} | Page {page}] ---\n{parent_text}")
                else:
                    rag_context_blocks.append(f"--- [SOP Document Excerpt (Page {page})] ---\n{parent_text}")

    llm_messages = []
    if rag_context_blocks:
        system_instruction = (
            "You are an expert Technical and Quality Operations Assistant for Standard Operating Procedures (SOPs).\n"
            "You provide clear, well-structured, professional answers strictly grounded in the user's uploaded SOP document(s) retrieved via FAISS HNSW vector search.\n\n"
            "Verified Context from the SOP Collection:\n\n"
            + "\n\n".join(rag_context_blocks)
            + "\n\n"
            "Formatting & Tone Guidelines:\n"
            "1. Format answers with clear, beautiful structure: use concise intro/overview sentences, clean bullet points for lists, and bold headers where appropriate.\n"
            "2. When citing specific sources, use standard format '[Document: filename.pdf, Page X]' or '[Page X]' if only one document. Do NOT use non-standard Unicode brackets like '【Page 2】'.\n"
            "3. Ground all statements strictly in the verified context above. If information is not in the SOP collection, state that clearly."
        )
        llm_messages.append({"role": "system", "content": system_instruction})

    for r in history:
        llm_messages.append({"role": r["role"], "content": r["content"]})

    body = {
        "provider": provider,
        "model": model,
        "api_key": api_key,
        "messages": llm_messages,
    }

    try:
        async with httpx.AsyncClient(timeout=90) as client:
            response = await client.post(f"{LLM_SERVICE_URL}/generate", json=body)
        if response.status_code >= 400:
            error_detail = response.text
            try:
                data = response.json()
                if isinstance(data, dict) and "detail" in data:
                    error_detail = data["detail"]
            except Exception:
                pass
            raise HTTPException(response.status_code, error_detail)
        answer = response.json()["content"]
        # Normalize non-standard citation brackets e.g. 【Page 2】 -> [Page 2]
        answer = re.sub(r"【(?:Document:\s*([^,】]+),\s*)?Page[\s\u202f]*(\d+)】", r"[Document: \1, Page \2]", answer)
        answer = re.sub(r"【Page[\s\u202f]*(\d+)】", r"[Page \1]", answer)
        answer = re.sub(r"[\u202f\u00a0\u200b]", " ", answer)
    except httpx.RequestError as exc:
        raise HTTPException(503, f"LLM service unavailable: {exc}") from exc

    # ChatGPT-style title summary
    updated_title = conv["title"]
    if conv["title"] == "New Chat":
        try:
            summary_title = await generate_chat_title_summary(
                provider=provider,
                model=model,
                api_key=api_key,
                message_text=payload.content,
            )
            if summary_title and summary_title != "New Chat":
                updated_title = summary_title
                c = db()
                c.execute("UPDATE conversations SET title=? WHERE id=?", (updated_title, payload.conversation_id))
                c.commit()
                c.close()
        except Exception:
            pass

    c = db()
    c.execute(
        "INSERT INTO messages VALUES (?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), payload.conversation_id, "assistant", answer, now()),
    )
    c.execute("UPDATE conversations SET updated_at=? WHERE id=?", (now(), payload.conversation_id))
    c.commit()
    c.close()

    return {
        "role": "assistant",
        "content": answer,
        "title": updated_title,
        "rag_applied": bool(rag_context_blocks),
        "referenced_pages": list({c["page"] for c in retrieved_chunks if c.get("page")}),
    }


# =============================================================
# SPA FRONTEND STATIC MOUNT (FOR CLOUD DEPLOYMENT)
# =============================================================
FRONTEND_DIST = os.path.join(PROJECT_ROOT, "frontend", "dist")
if not os.path.exists(FRONTEND_DIST):
    alt_dist = os.path.abspath(os.path.join(CURRENT_DIR, "..", "..", "frontend", "dist"))
    if os.path.exists(alt_dist):
        FRONTEND_DIST = alt_dist

if os.path.exists(FRONTEND_DIST):
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import FileResponse

    assets_dir = os.path.join(FRONTEND_DIST, "assets")
    if os.path.exists(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="spa_assets")

    @app.get("/{full_path:path}")
    async def serve_spa_frontend(full_path: str):
        # Do not catch API endpoints, swagger, or system routes
        api_prefixes = (
            "api",
            "docs",
            "redoc",
            "openapi.json",
            "health",
            "auth",
            "chat",
            "sop",
            "settings",
        )
        if any(full_path == p or full_path.startswith(f"{p}/") for p in api_prefixes):
            raise HTTPException(404, "API route not found")

        file_path = os.path.join(FRONTEND_DIST, full_path)
        if full_path and os.path.exists(file_path) and os.path.isfile(file_path):
            return FileResponse(file_path)

        index_path = os.path.join(FRONTEND_DIST, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)

        raise HTTPException(404, "Frontend build not found")

