import json
import logging
import os
import re
import uuid
from typing import Any, Dict, List, Optional, Tuple
import faiss
import numpy as np
from fastembed import TextEmbedding

logger = logging.getLogger(__name__)

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.getcwd() if os.path.exists(os.path.join(os.getcwd(), "services")) else os.path.abspath(os.path.join(CURRENT_DIR, "..", ".."))
DEFAULT_INDEX_DIR = os.path.join(PROJECT_ROOT, "storage", "indexes")
INDEX_STORAGE_PATH = os.getenv("INDEX_STORAGE_PATH", DEFAULT_INDEX_DIR)
os.makedirs(INDEX_STORAGE_PATH, exist_ok=True)

# =====================================================================
# INITIALIZE LOCAL EMBEDDING ENGINE
# =====================================================================
# BAAI/bge-small-en-v1.5 produces 384-dimensional embeddings optimized
# for semantic retrieval, running locally via fast ONNX runtime.
logger.info("Initializing FastEmbed TextEmbedding model (BAAI/bge-small-en-v1.5)...")
_embedding_model: Optional[TextEmbedding] = None


def get_embedding_model() -> TextEmbedding:
    global _embedding_model
    if _embedding_model is None:
        _embedding_model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
    return _embedding_model


# =====================================================================
# 1. HERE HIERARCHICAL CHUNKING HAPPENS
# Divides PDF text into Parent Chunks (macro context) and Child Chunks
# (fine search units). Parent chunks ensure the LLM receives complete
# surrounding instructions, while child chunks ensure precise retrieval.
# =====================================================================

def create_hierarchical_chunks(
    pages_data: List[Dict[str, Any]],
    parent_chunk_size: int = 1000,
    parent_chunk_overlap: int = 150,
    child_chunk_size: int = 250,
    child_chunk_overlap: int = 40,
    document_id: Optional[str] = None,
    filename: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    # --- HERE HIERARCHICAL CHUNKING HAPPENS ---
    Extracts hierarchical parent and child chunks from document pages,
    annotating each chunk with its originating document ID and filename.
    """
    parent_chunks: List[Dict[str, Any]] = []
    child_chunks: List[Dict[str, Any]] = []

    child_global_idx = 0
    parent_global_idx = 0

    for page_item in pages_data:
        page_num = page_item["page"]
        text = page_item["text"].strip()
        if not text:
            continue

        # Split page text into sentences/paragraphs for clean chunk boundaries
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        if not paragraphs:
            paragraphs = [text]

        # Step 1: Build Parent Chunks (Macro-level context: ~1000 chars)
        current_parent_text = ""
        page_parents: List[str] = []

        for p in paragraphs:
            if len(current_parent_text) + len(p) + 1 > parent_chunk_size and current_parent_text:
                page_parents.append(current_parent_text.strip())
                # Keep overlap from the end of current parent
                overlap_text = current_parent_text[-parent_chunk_overlap:] if len(current_parent_text) > parent_chunk_overlap else ""
                current_parent_text = overlap_text + " " + p if overlap_text else p
            else:
                current_parent_text += (" " if current_parent_text else "") + p

        if current_parent_text.strip():
            page_parents.append(current_parent_text.strip())

        # Step 2: Build Child Chunks for each Parent Chunk
        for parent_text in page_parents:
            parent_id = f"parent_{parent_global_idx}_{uuid.uuid4().hex[:6]}"
            parent_global_idx += 1

            parent_chunks.append({
                "parent_id": parent_id,
                "page": page_num,
                "text": parent_text,
                "document_id": document_id,
                "filename": filename,
            })

            # Subdivide Parent into Child Chunks (Micro-level search units: ~250 chars)
            start = 0
            parent_len = len(parent_text)
            while start < parent_len:
                end = min(start + child_chunk_size, parent_len)
                
                # Try to break on whitespace boundary if possible
                if end < parent_len:
                    space_idx = parent_text.rfind(" ", start, end)
                    if space_idx != -1 and space_idx > start + (child_chunk_size // 2):
                        end = space_idx

                child_slice = parent_text[start:end].strip()
                if child_slice:
                    child_chunks.append({
                        "child_id": f"child_{child_global_idx}",
                        "parent_id": parent_id,
                        "page": page_num,
                        "text": child_slice,
                        "parent_text": parent_text,
                        "index": child_global_idx,
                        "document_id": document_id,
                        "filename": filename,
                    })
                    child_global_idx += 1

                if end >= parent_len:
                    break
                start = max(start + 1, end - child_chunk_overlap)

    logger.info(
        "Hierarchical chunking complete for '%s': generated %d parent chunks and %d child chunks.",
        filename or "document",
        len(parent_chunks),
        len(child_chunks),
    )
    return parent_chunks, child_chunks


# =====================================================================
# 2. HERE EMBEDDING HAPPENS
# Generates dense vector representations for all child chunks.
# =====================================================================

def generate_embeddings(texts: List[str]) -> np.ndarray:
    """
    # --- HERE EMBEDDING HAPPENS ---
    Generates normalized 384-dimensional vector embeddings for given texts.
    """
    if not texts:
        return np.empty((0, 384), dtype=np.float32)

    model = get_embedding_model()
    # model.embed returns a generator yielding numpy float arrays
    embeddings_list = list(model.embed(texts))
    vectors = np.array(embeddings_list, dtype=np.float32)

    # Normalize vectors for cosine similarity in FAISS
    faiss.normalize_L2(vectors)
    return vectors


# =====================================================================
# 3. HERE FAISS VECTOR STORE HAPPENS
# Builds, saves, and loads FAISS Index for high-speed similarity search.
# =====================================================================

class FaissVectorStore:
    """
    FAISS HNSW Vector Store manager for multi-SOP PDF chunks.
    Uses Hierarchical Navigable Small World (HNSW) indexing to cluster
    semantically similar procedural, safety, and equipment chunks
    close to each other in a multi-layer graph for fast, high-recall retrieval.
    """

    def __init__(self, conversation_id: str):
        self.conversation_id = conversation_id
        self.index_file = os.path.join(INDEX_STORAGE_PATH, f"faiss_{conversation_id}.index")
        self.meta_file = os.path.join(INDEX_STORAGE_PATH, f"faiss_{conversation_id}_meta.json")
        self.index: Optional[Any] = None
        self.child_chunks: List[Dict[str, Any]] = []
        self._load_if_exists()

    def _load_if_exists(self):
        """Load existing FAISS HNSW index from disk if present."""
        if os.path.exists(self.index_file) and os.path.exists(self.meta_file):
            try:
                self.index = faiss.read_index(self.index_file)
                # Tune HNSW graph search parameter if applicable
                if hasattr(self.index, "hnsw"):
                    self.index.hnsw.efSearch = 32
                with open(self.meta_file, "r", encoding="utf-8") as f:
                    self.child_chunks = json.load(f)
                logger.info(
                    "Loaded FAISS HNSW index for conversation %s (%d vectors, index_type=%s)",
                    self.conversation_id,
                    self.index.ntotal,
                    type(self.index).__name__,
                )
            except Exception as e:
                logger.error("Failed loading FAISS HNSW index for %s: %s", self.conversation_id, e)

    def build_and_save(self, child_chunks: List[Dict[str, Any]]):
        """
        # --- HERE FAISS HNSW VECTOR STORE CREATION HAPPENS ---
        Builds FAISS HNSW Index (Hierarchical Navigable Small World) with Cosine Similarity
        (METRIC_INNER_PRODUCT on normalized embeddings) and persists to disk.
        M=32 bi-directional links per node, efConstruction=64 for high-quality semantic clustering.
        """
        if not child_chunks:
            logger.warning("No child chunks provided to build FAISS HNSW index.")
            return

        texts = [c["text"] for c in child_chunks]
        
        # --- HERE EMBEDDING HAPPENS ---
        vectors = generate_embeddings(texts)
        dimension = vectors.shape[1]

        # Use IndexHNSWFlat: M=32, metric=METRIC_INNER_PRODUCT (cosine similarity on L2-normalized vectors)
        index = faiss.IndexHNSWFlat(dimension, 32, faiss.METRIC_INNER_PRODUCT)
        index.hnsw.efConstruction = 64  # Higher construction depth ensures tight semantic clustering
        index.hnsw.efSearch = 32        # Exploration beam width for query retrieval
        index.add(vectors)

        # Save to disk
        faiss.write_index(index, self.index_file)
        with open(self.meta_file, "w", encoding="utf-8") as f:
            json.dump(child_chunks, f)

        self.index = index
        self.child_chunks = child_chunks
        logger.info(
            "Built and saved FAISS HNSW index with %d vectors to %s",
            index.ntotal,
            self.index_file,
        )

    def add_and_save(self, new_child_chunks: List[Dict[str, Any]]):
        """
        Incrementally adds new vectors into the existing FAISS HNSW graph,
        connecting them to their nearest neighbor clusters, and updates disk persistence.
        """
        if not new_child_chunks:
            return

        if self.index is None or not self.child_chunks:
            self.build_and_save(new_child_chunks)
            return

        new_texts = [c["text"] for c in new_child_chunks]
        new_vectors = generate_embeddings(new_texts)

        # Add vectors to HNSW graph - HNSW links them to semantic neighbors
        self.index.add(new_vectors)
        self.child_chunks.extend(new_child_chunks)

        # Save updated graph to disk
        faiss.write_index(self.index, self.index_file)
        with open(self.meta_file, "w", encoding="utf-8") as f:
            json.dump(self.child_chunks, f)

        logger.info(
            "Added %d vectors to FAISS HNSW index for conversation %s (total: %d vectors)",
            len(new_child_chunks),
            self.conversation_id,
            self.index.ntotal,
        )

    # =================================================================
    # 4. HERE RETRIEVAL HAPPENS
    # Searches FAISS HNSW graph using question embedding, expands matched
    # child chunks to their parent chunks with document citation metadata.
    # =================================================================
    def search(self, query: str, top_k: int = 6) -> List[Dict[str, Any]]:
        """
        # --- HERE RETRIEVAL HAPPENS ---
        1. Embed user query.
        2. Perform fast approximate nearest-neighbor search via HNSW graph traversal.
        3. Retrieve matched child chunks with originating document filename & page.
        4. Expand to Parent Chunks for rich context.
        """
        if not self.index or not self.child_chunks:
            return []

        # --- HERE EMBEDDING FOR QUERY HAPPENS ---
        query_vector = generate_embeddings([query])

        k = min(top_k, self.index.ntotal)
        if k == 0:
            return []

        # Search top-k closest child chunks in HNSW graph
        distances, indices = self.index.search(query_vector, k)

        retrieved: List[Dict[str, Any]] = []
        seen_parents = set()

        for score, idx in zip(distances[0], indices[0]):
            if idx < 0 or idx >= len(self.child_chunks):
                continue

            child = self.child_chunks[idx]
            parent_id = child.get("parent_id")

            # Avoid duplicate parent chunks in final context
            is_new_parent = parent_id not in seen_parents
            if is_new_parent:
                seen_parents.add(parent_id)

            retrieved.append({
                "score": float(score),
                "child_id": child.get("child_id"),
                "parent_id": parent_id,
                "child_text": child.get("text"),
                "parent_text": child.get("parent_text"),
                "page": child.get("page"),
                "filename": child.get("filename"),
                "document_id": child.get("document_id"),
                "is_primary": is_new_parent,
            })

        return retrieved


# In-memory vector store cache for active sessions
_vector_stores: Dict[str, FaissVectorStore] = {}


def get_vector_store(conversation_id: str) -> FaissVectorStore:
    """Get or create FAISS vector store instance for a conversation."""
    if conversation_id not in _vector_stores:
        _vector_stores[conversation_id] = FaissVectorStore(conversation_id)
    return _vector_stores[conversation_id]
