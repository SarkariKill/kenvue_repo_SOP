---
title: Kenvue SOP Optimization & Harmonization
emoji: 📑
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
---

# Kenvue SOP Optimization & Multi-SOP Harmonization Assistant

A high-performance modular AI web application for Standard Operating Procedure (SOP) PDF ingestion, multimodal artifact extraction (images & tables), FAISS HNSW similarity clustering, multi-SOP harmonization, interactive simplification, and Kenvue standard compliance scoring.

---

## 🏗️ Local Architecture (Docker-Free)

```
Frontend (React + Vite) :3000
      │
      ▼
API Service (FastAPI) :8000 ────► Local Storage (./storage/ for images, tables, PDFs)
      │                     ────► FAISS HNSW Vector Store (Hierarchical Embeddings)
      │                     ────► SQLite Database (./storage/data/chat.db)
      ▼
LLM Service (Groq / Gemini) :8001
```

- **Zero Docker / Zero MinIO Dependency**: Runs natively and smoothly on local development environments without containers.
- **Local File Storage**: All extracted images, tables, generated PDFs, and FAISS vector indexes reside cleanly inside `./storage/`.

---

## 🚀 Key Features

1. **Multi-SOP Upload & HNSW Similarity Clustering**:
   - Upload up to 10 SOPs concurrently in "All Uploaded SOPs".
   - Generates document-level embeddings and groups documents into similarity clusters with similarity percentages and confidence scores.

2. **Intelligent SOP Harmonization & Simplification**:
   - Harmonize multiple overlapping or duplicate SOPs into a single unified Kenvue standard document.
   - Interactive simplification workflow with selectable recommendations (clarity, concise terminology, consistency).
   - Preserves complete immutable version history (`Harmonized SOP v1`, `v2`, etc.).

3. **Multimodal Extraction & Image Placement**:
   - **Text**: Hierarchical chunking (parent and child chunks).
   - **Images & Tables**: Extracted *as-is* with page references and automatically placed in newly generated PDFs.

4. **Kenvue Standard Scoring & Evaluation**:
   - Real-time scoring for Readability, Template Match, Kenvue Alignment, and Completeness.
   - Live animated visual progress bar during ingestion and harmonization.

---

## 🛠️ Quick Start

### One-Click Local Launcher
Run the turnkey launcher from terminal:
```bash
python3 run.py
```

This automatically:
- Initializes `./storage/` folders and checks Python & Node environments.
- Starts LLM microservice (:8001), API backend (:8000), and Frontend (:3000).
- Opens [http://localhost:3000](http://localhost:3000) directly in your default browser.

### Stop All Services
```bash
python3 run.py --stop
```
*(or press `Ctrl+C` in the running terminal)*

---

## 🔑 Default Credentials
- **Username**: `admin`
- **Password**: `admin`
*(or register any new user account directly on the login screen)*
# kenvue_repo_SOP
