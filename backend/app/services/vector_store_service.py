import logging
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from math import log
from typing import Any

from app.config.settings import settings
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
    chunk_hash: str
    source_filename: str | None
    section_title: str | None
    page_start: int | None
    page_end: int | None
    created_at: str
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


class ChunkDedupCache:
    def __init__(self):
        self._seen: set[str] = set()
        self._redis = None

        if settings.DEDUP_CACHE_BACKEND.lower().strip() == "redis":
            try:
                import redis

                self._redis = redis.Redis.from_url(settings.REDIS_URL)
            except Exception as exc:
                logger.warning(f"Redis chunk dedup cache unavailable: {exc}")

    def seen_or_mark(self, chunk_hash: str) -> bool:
        if self._redis is not None:
            key = f"chunk_hash:{chunk_hash}"
            was_set = self._redis.set(key, "1", nx=True)
            return not bool(was_set)

        if chunk_hash in self._seen:
            return True
        self._seen.add(chunk_hash)
        return False


class SearchReranker:
    def rerank(
        self,
        query: str,
        results: list[VectorSearchResult],
        top_k: int,
    ) -> list[VectorSearchResult]:
        query_terms = set(re.findall(r"\b\w+\b", query.lower()))
        if not query_terms:
            return results[:top_k]

        reranked = []
        for result in results:
            text_terms = set(re.findall(r"\b\w+\b", result.text.lower()))
            overlap_bonus = len(query_terms & text_terms) / max(len(query_terms), 1)
            reranked.append(
                VectorSearchResult(
                    clause_id=result.clause_id,
                    text=result.text,
                    score=round(result.score + (0.05 * overlap_bonus), 4),
                    source_start=result.source_start,
                    source_end=result.source_end,
                    heading=result.heading,
                    chunk_id=result.chunk_id,
                )
            )

        reranked.sort(key=lambda item: item.score, reverse=True)
        return reranked[:top_k]


class VectorStoreService:
    """
    Manages vector storage, LangChain chunking, SentenceTransformer embeddings,
    and hybrid semantic search over document clauses.
    """

    def __init__(self, persist_directory: str | None = None, model_name: str | None = None):
        persist_directory = persist_directory or settings.VECTOR_STORE_DIRECTORY
        model_name = model_name or settings.EMBEDDING_MODEL

        self.persist_directory = persist_directory
        self.model_name = model_name

        self.chroma_client = None
        self.collection = None
        self.encoder = None
        self._encoder_load_attempted = False
        self.dedup_cache = ChunkDedupCache()
        self.reranker = SearchReranker()

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

        # LangChain text splitter remains a fallback; primary splitting is
        # structure-aware and follows legal paragraph/section boundaries.
        if HAS_LANGCHAIN_SPLITTER:
            self.text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=1200,
                chunk_overlap=150,
                separators=["\n\n", "\n", ". ", "; ", ", ", " "],
            )
        else:
            self.text_splitter = None

    def _get_encoder(self):
        if self._encoder_load_attempted:
            return self.encoder

        self._encoder_load_attempted = True
        if not HAS_SENTENCE_TRANSFORMERS:
            return None

        try:
            self.encoder = SentenceTransformer(self.model_name)
        except Exception as e:
            logger.warning(f"Failed to load SentenceTransformer ({self.model_name}): {e}.")

        return self.encoder

    def chunk_clause(self, clause: Clause) -> list[DocumentChunk]:
        """
        Splits a Clause into overlapping chunks using LangChain RecursiveCharacterTextSplitter
        preserving metadata (document_id, clause_id, heading, spans).
        """
        text = clause.text or ""
        if not text.strip():
            return []

        raw_chunks = self._structure_aware_split(text)

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

            chunk_hash = self._chunk_hash(chunk_text)
            chunk_id = f"{clause.clause_id}-chunk-{idx:03d}-{chunk_hash[:12]}"
            created_at = datetime.now(UTC).isoformat()
            meta = {
                "document_id": clause.document_id,
                "clause_id": clause.clause_id,
                "clause_pk": clause.id,
                "heading": clause.heading or "",
                "section_title": clause.heading or "",
                "source_filename": "",
                "source_start": abs_start,
                "source_end": abs_end,
                "page_start": 0,
                "page_end": 0,
                "chunk_index": idx,
                "chunk_id": chunk_id,
                "chunk_hash": chunk_hash,
                "created_at": created_at,
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
                    chunk_hash=chunk_hash,
                    source_filename=None,
                    section_title=clause.heading,
                    page_start=None,
                    page_end=None,
                    created_at=created_at,
                    metadata=meta,
                )
            )
        return chunks

    def _structure_aware_split(self, text: str, max_chars: int = 1200) -> list[str]:
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        if not paragraphs:
            return self.text_splitter.split_text(text) if self.text_splitter else [text]

        chunks: list[str] = []
        current: list[str] = []
        current_len = 0

        for paragraph in paragraphs:
            if len(paragraph) > max_chars:
                if current:
                    chunks.append("\n\n".join(current))
                    current = []
                    current_len = 0
                chunks.extend(self.text_splitter.split_text(paragraph) if self.text_splitter else [paragraph])
                continue

            projected = current_len + len(paragraph) + (2 if current else 0)
            starts_new_section = self._looks_like_section_boundary(paragraph)

            if current and (projected > max_chars or starts_new_section):
                chunks.append("\n\n".join(current))
                current = [paragraph]
                current_len = len(paragraph)
            else:
                current.append(paragraph)
                current_len = projected

        if current:
            chunks.append("\n\n".join(current))

        return chunks

    def _looks_like_section_boundary(self, paragraph: str) -> bool:
        first_line = paragraph.splitlines()[0].strip()
        return bool(
            re.match(
                r"^((section|clause|article|part)\s+[\w.]+|[A-Z][A-Z\s]{3,80}|"
                r"\d+(\.\d+)*[\.)]\s+|\([a-zA-Z0-9]+\)\s+)",
                first_line,
                re.IGNORECASE,
            )
        )

    def _chunk_hash(self, chunk_text: str) -> str:
        normalized = re.sub(r"\s+", " ", chunk_text).strip().lower()
        return sha256(normalized.encode("utf-8")).hexdigest()

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

        deduped_chunks = []
        for chunk in all_chunks:
            if self.dedup_cache.seen_or_mark(chunk.chunk_hash):
                continue
            deduped_chunks.append(chunk)

        if not deduped_chunks:
            return 0

        ids = [c.chunk_id for c in deduped_chunks]
        texts = [c.text for c in deduped_chunks]
        metadatas = [c.metadata for c in deduped_chunks]

        if self.collection:
            try:
                embeddings = None
                encoder = self._get_encoder()
                if encoder:
                    embeddings = encoder.encode(texts, show_progress_bar=False).tolist()

                if embeddings:
                    self.collection.upsert(ids=ids, documents=texts, embeddings=embeddings, metadatas=metadatas)
                else:
                    self.collection.upsert(ids=ids, documents=texts, metadatas=metadatas)
                logger.info(f"Indexed {len(deduped_chunks)} chunks for document {document_id} into ChromaDB.")
            except Exception as e:
                logger.error(f"Failed to upsert into ChromaDB: {e}")

        return len(deduped_chunks)

    def index_extracted_chunks(self, chunks: list[Any]) -> int:
        deduped_chunks = []
        for chunk in chunks:
            if self.dedup_cache.seen_or_mark(chunk.chunk_hash):
                continue
            deduped_chunks.append(chunk)

        if not deduped_chunks:
            return 0

        ids = [chunk.chunk_id for chunk in deduped_chunks]
        texts = [chunk.text for chunk in deduped_chunks]
        metadatas = [chunk.metadata for chunk in deduped_chunks]

        if self.collection:
            try:
                embeddings = None
                encoder = self._get_encoder()
                if encoder:
                    embeddings = encoder.encode(texts, show_progress_bar=False).tolist()

                if embeddings:
                    self.collection.upsert(ids=ids, documents=texts, embeddings=embeddings, metadatas=metadatas)
                else:
                    self.collection.upsert(ids=ids, documents=texts, metadatas=metadatas)
            except Exception as e:
                logger.error(f"Failed to upsert extracted chunks into ChromaDB: {e}")
                raise

        return len(deduped_chunks)

    def hybrid_search(
        self, document_id: str, query: str, clauses: list[Clause], top_k: int = 3
    ) -> list[VectorSearchResult]:
        """
        Executes hybrid semantic search (dense vector similarity + BM25 keyword matching).
        """
        if not clauses:
            return []

        dense_results: list[VectorSearchResult] = []
        if self.collection:
            try:
                query_embedding = None
                encoder = self._get_encoder()
                if encoder:
                    query_embedding = encoder.encode([query], show_progress_bar=False).tolist()

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

                    for doc_str, meta, dist in zip(docs, metas, distances):
                        # Convert cosine distance to similarity score
                        sim = max(0.0, 1.0 - float(dist)) if dist is not None else 0.8
                        dense_results.append(
                            VectorSearchResult(
                                clause_id=meta.get("clause_id", ""),
                                text=doc_str,
                                score=round(sim, 4),
                                source_start=meta.get("source_start", 0),
                                source_end=meta.get("source_end", 0),
                                heading=meta.get("heading") or None,
                                chunk_id=meta.get("chunk_id"),
                            )
                        )
            except Exception as e:
                logger.warning(f"ChromaDB search failed: {e}. Falling back to hybrid lexical search.")

        sparse_results = self._sparse_keyword_search(query, clauses, top_k=top_k * 3)

        if dense_results:
            fused = self._rrf_fuse(dense_results, sparse_results, top_k=top_k * 2)
            return self.reranker.rerank(query, fused, top_k=top_k)

        return self.reranker.rerank(query, sparse_results, top_k=top_k)

    def _lexical_hybrid_fallback(self, query: str, clauses: list[Clause], top_k: int) -> list[VectorSearchResult]:
        return self._sparse_keyword_search(query, clauses, top_k)

    def _sparse_keyword_search(self, query: str, clauses: list[Clause], top_k: int) -> list[VectorSearchResult]:
        query_terms = re.findall(r"\b\w+\b", query.lower())
        if not query_terms:
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

        doc_terms = [re.findall(r"\b\w+\b", clause.text.lower()) for clause in clauses]
        doc_count = len(doc_terms)
        document_frequency: dict[str, int] = {}

        for terms in doc_terms:
            for term in set(terms):
                document_frequency[term] = document_frequency.get(term, 0) + 1

        results = []
        avg_len = sum(len(terms) for terms in doc_terms) / max(doc_count, 1)
        k1 = 1.5
        b = 0.75

        for clause, terms in zip(clauses, doc_terms):
            term_counts: dict[str, int] = {}
            for term in terms:
                term_counts[term] = term_counts.get(term, 0) + 1

            score = 0.0
            for term in query_terms:
                tf = term_counts.get(term, 0)
                if tf == 0:
                    continue
                df = document_frequency.get(term, 0)
                idf = log(1 + (doc_count - df + 0.5) / (df + 0.5))
                denom = tf + k1 * (1 - b + b * (len(terms) / max(avg_len, 1)))
                score += idf * ((tf * (k1 + 1)) / denom)

            results.append(
                VectorSearchResult(
                    clause_id=clause.clause_id,
                    text=clause.text,
                    score=round(float(score), 4),
                    source_start=clause.source_start,
                    source_end=clause.source_end,
                    heading=clause.heading,
                )
            )

        results.sort(key=lambda x: x.score, reverse=True)
        return results[:top_k]

    def _rrf_fuse(
        self,
        dense_results: list[VectorSearchResult],
        sparse_results: list[VectorSearchResult],
        top_k: int,
        k: int = 60,
    ) -> list[VectorSearchResult]:
        fused: dict[str, tuple[float, VectorSearchResult]] = {}

        for result_set in (dense_results, sparse_results):
            for rank, result in enumerate(result_set, start=1):
                existing_score, existing_result = fused.get(
                    result.clause_id,
                    (0.0, result),
                )
                best_result = result if result.score > existing_result.score else existing_result
                fused[result.clause_id] = (
                    existing_score + (1.0 / (k + rank)),
                    best_result,
                )

        ranked = []
        for fused_score, result in fused.values():
            ranked.append(
                VectorSearchResult(
                    clause_id=result.clause_id,
                    text=result.text,
                    score=round(fused_score, 4),
                    source_start=result.source_start,
                    source_end=result.source_end,
                    heading=result.heading,
                    chunk_id=result.chunk_id,
                )
            )

        ranked.sort(key=lambda item: item.score, reverse=True)
        return ranked[:top_k]
