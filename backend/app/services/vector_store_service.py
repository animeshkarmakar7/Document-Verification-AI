import logging
import os
import re
from dataclasses import dataclass
from typing import Any

from app.models.clause import Clause

logger = logging.getLogger(__name__)

# Try importing chromadb and sentence_transformers
try:
    import chromadb
    from chromadb.config import Settings
    HAS_CHROMADB = True
except ImportError:
    HAS_CHROMADB = False

try:
    from sentence_transformers import SentenceTransformer
    HAS_SENTENCE_TRANSFORMERS = True
except ImportError:
    HAS_SENTENCE_TRANSFORMERS = False

try:
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    HAS_LANGCHAIN_SPLITTER = True
except ImportError:
    HAS_LANGCHAIN_SPLITTER = False


@dataclass
class DocumentChunk:
    chunk_id: str
    document_id: str
    clause_id: str
    heading: str | None
    text: str
    source_start: int
    source_end: int
    chunk_index: int
    metadata: dict[str, Any]


@dataclass
class VectorSearchResult:
    clause_id: str
    text: str
    score: float
    source_start: int
    source_end: int
    heading: str | None = None
    chunk_id: str | None = None


class VectorStoreService:
    """
    Manages vector storage, LangChain chunking, SentenceTransformer embeddings,
    and hybrid semantic search over document clauses.
    """

    def __init__(self, persist_directory: str = ".chroma_db", model_name: str = "all-MiniLM-L6-v2"):
        self.persist_directory = persist_directory
        self.model_name = model_name

        self.chroma_client = None
        self.collection = None
        self.encoder = None

        if HAS_CHROMADB:
            try:
                os.makedirs(self.persist_directory, exist_ok=True)
                self.chroma_client = chromadb.PersistentClient(path=self.persist_directory)
                self.collection = self.chroma_client.get_or_create_collection(
                    name="legal_document_chunks",
                    metadata={"hnsw:space": "cosine"},
                )
            except Exception as e:
                logger.warning(f"Failed to initialize ChromaDB: {e}. Falling back to in-memory search.")

        if HAS_SENTENCE_TRANSFORMERS:
            try:
                self.encoder = SentenceTransformer(self.model_name)
            except Exception as e:
                logger.warning(f"Failed to load SentenceTransformer ({self.model_name}): {e}.")

        # LangChain text splitter for legal document chunks
        if HAS_LANGCHAIN_SPLITTER:
            self.text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=400,
                chunk_overlap=80,
                separators=["\n\n", "\n", ". ", "; ", ", ", " "],
            )
        else:
            self.text_splitter = None

    def chunk_clause(self, clause: Clause) -> list[DocumentChunk]:
        """
        Splits a Clause into overlapping chunks using LangChain RecursiveCharacterTextSplitter
        preserving metadata (document_id, clause_id, heading, spans).
        """
        text = clause.text or ""
        if not text.strip():
            return []

        if self.text_splitter:
            raw_chunks = self.text_splitter.split_text(text)
        else:
            # Simple fallback splitter
            raw_chunks = [text[i:i+400] for i in range(0, len(text), 320)]

        chunks = []
        current_offset = clause.source_start
        for idx, chunk_text in enumerate(raw_chunks, start=1):
            chunk_start = text.find(chunk_text[:30], max(0, current_offset - clause.source_start))
            if chunk_start != -1:
                abs_start = clause.source_start + chunk_start
                abs_end = abs_start + len(chunk_text)
            else:
                abs_start = clause.source_start
                abs_end = clause.source_end

            chunk_id = f"{clause.clause_id}-chunk-{idx:03d}"
            meta = {
                "document_id": clause.document_id,
                "clause_id": clause.clause_id,
                "clause_pk": clause.id,
                "heading": clause.heading or "",
                "source_start": abs_start,
                "source_end": abs_end,
                "chunk_index": idx,
            }
            chunks.append(
                DocumentChunk(
                    chunk_id=chunk_id,
                    document_id=clause.document_id,
                    clause_id=clause.clause_id,
                    heading=clause.heading,
                    text=chunk_text,
                    source_start=abs_start,
                    source_end=abs_end,
                    chunk_index=idx,
                    metadata=meta,
                )
            )
        return chunks

    def index_document_clauses(self, document_id: str, clauses: list[Clause]) -> int:
        """
        Chunks clauses and upserts their embeddings & metadata into ChromaDB.
        """
        if not clauses:
            return 0

        all_chunks: list[DocumentChunk] = []
        for clause in clauses:
            all_chunks.extend(self.chunk_clause(clause))

        if not all_chunks:
            return 0

        ids = [c.chunk_id for c in all_chunks]
        texts = [c.text for c in all_chunks]
        metadatas = [c.metadata for c in all_chunks]

        if self.collection:
            try:
                embeddings = None
                if self.encoder:
                    embeddings = self.encoder.encode(texts, show_progress_bar=False).tolist()

                if embeddings:
                    self.collection.upsert(ids=ids, documents=texts, embeddings=embeddings, metadatas=metadatas)
                else:
                    self.collection.upsert(ids=ids, documents=texts, metadatas=metadatas)
                logger.info(f"Indexed {len(all_chunks)} chunks for document {document_id} into ChromaDB.")
            except Exception as e:
                logger.error(f"Failed to upsert into ChromaDB: {e}")

        return len(all_chunks)

    def hybrid_search(
        self, document_id: str, query: str, clauses: list[Clause], top_k: int = 3
    ) -> list[VectorSearchResult]:
        """
        Executes hybrid semantic search (dense vector similarity + BM25 keyword matching).
        """
        if not clauses:
            return []

        # 1. ChromaDB vector search if available
        if self.collection:
            try:
                query_embedding = None
                if self.encoder:
                    query_embedding = self.encoder.encode([query], show_progress_bar=False).tolist()

                if query_embedding:
                    res = self.collection.query(
                        query_embeddings=query_embedding,
                        where={"document_id": document_id},
                        n_results=min(top_k * 2, 10),
                    )
                else:
                    res = self.collection.query(
                        query_texts=[query],
                        where={"document_id": document_id},
                        n_results=min(top_k * 2, 10),
                    )

                if res and res.get("documents") and res["documents"][0]:
                    docs = res["documents"][0]
                    metas = res["metadatas"][0] if res.get("metadatas") else []
                    distances = res["distances"][0] if res.get("distances") else [0.0] * len(docs)

                    results = []
                    for doc_str, meta, dist in zip(docs, metas, distances):
                        # Convert cosine distance to similarity score
                        sim = max(0.0, 1.0 - float(dist)) if dist is not None else 0.8
                        results.append(
                            VectorSearchResult(
                                clause_id=meta.get("clause_id", ""),
                                text=doc_str,
                                score=round(sim, 4),
                                source_start=meta.get("source_start", 0),
                                source_end=meta.get("source_end", 0),
                                heading=meta.get("heading") or None,
                                chunk_id=meta.get("clause_id"),
                            )
                        )

                    # Deduplicate by clause_id taking top score
                    clause_results_map = {}
                    for r in results:
                        if r.clause_id not in clause_results_map or r.score > clause_results_map[r.clause_id].score:
                            clause_results_map[r.clause_id] = r
                    sorted_vector = sorted(clause_results_map.values(), key=lambda x: x.score, reverse=True)
                    if sorted_vector:
                        return sorted_vector[:top_k]
            except Exception as e:
                logger.warning(f"ChromaDB search failed: {e}. Falling back to hybrid lexical search.")

        # Fallback BM25 / Cosine lexical matching across clauses
        return self._lexical_hybrid_fallback(query, clauses, top_k)

    def _lexical_hybrid_fallback(self, query: str, clauses: list[Clause], top_k: int) -> list[VectorSearchResult]:
        query_words = set(re.findall(r"\b\w+\b", query.lower()))
        if not query_words:
            return [
                VectorSearchResult(
                    clause_id=c.clause_id,
                    text=c.text,
                    score=0.5,
                    source_start=c.source_start,
                    source_end=c.source_end,
                    heading=c.heading,
                )
                for c in clauses[:top_k]
            ]

        results = []
        for clause in clauses:
            clause_words = set(re.findall(r"\b\w+\b", clause.text.lower()))
            overlap = query_words.intersection(clause_words)
            score = len(overlap) / float(len(query_words)) if query_words else 0.0
            results.append(
                VectorSearchResult(
                    clause_id=clause.clause_id,
                    text=clause.text,
                    score=round(score, 4),
                    source_start=clause.source_start,
                    source_end=clause.source_end,
                    heading=clause.heading,
                )
            )

        results.sort(key=lambda x: x.score, reverse=True)
        return results[:top_k]
