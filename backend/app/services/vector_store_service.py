import logging
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from functools import lru_cache
from math import log
from typing import Any

from app.config.settings import settings
from app.models.clause import Clause

logger = logging.getLogger(__name__)

# Try importing chromadb and sentence_transformers
try:
    import chromadb
    HAS_CHROMADB = True
except ImportError:
    HAS_CHROMADB = False

try:
    from sentence_transformers import CrossEncoder, SentenceTransformer
    HAS_SENTENCE_TRANSFORMERS = True
except ImportError:
    HAS_SENTENCE_TRANSFORMERS = False

try:
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    HAS_LANGCHAIN_SPLITTER = True
except ImportError:
    HAS_LANGCHAIN_SPLITTER = False


@lru_cache(maxsize=4)
def _load_sentence_transformer(model_name: str):
    return SentenceTransformer(model_name)


@lru_cache(maxsize=4)
def _load_cross_encoder(model_name: str):
    return CrossEncoder(model_name, max_length=512)


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
    rrf_score: float | None = None
    rerank_score: float | None = None
    dense_rank: int | None = None
    sparse_rank: int | None = None


class SearchReranker:
    def __init__(self, model_name: str | None = None, batch_size: int | None = None):
        self.model_name = model_name or settings.RERANKER_MODEL
        if batch_size is not None and batch_size < 1:
            raise ValueError("batch_size must be positive.")
        self.batch_size = (
            batch_size if batch_size is not None else settings.RERANKER_BATCH_SIZE
        )
        self._model = None

    def _get_model(self):
        if self._model is None:
            if not HAS_SENTENCE_TRANSFORMERS:
                raise RuntimeError("sentence-transformers is required for cross-encoder reranking.")
            self._model = _load_cross_encoder(self.model_name)
        return self._model

    def rerank(
        self,
        query: str,
        results: list[VectorSearchResult],
        top_k: int,
    ) -> list[VectorSearchResult]:
        if top_k < 1:
            raise ValueError("top_k must be positive.")
        if not results:
            return []

        model = self._get_model()
        pairs = [(query, result.text) for result in results]
        scores = model.predict(
            pairs,
            batch_size=self.batch_size,
            show_progress_bar=False,
        )
        if len(scores) != len(results):
            raise RuntimeError("Cross-encoder returned an unexpected number of scores.")

        ranked = sorted(
            zip(results, scores, range(len(results))),
            key=lambda item: (float(item[1]), -item[2]),
            reverse=True,
        )
        output = []
        for result, raw_score, _ in ranked[:top_k]:
            score = float(raw_score)
            output.append(
                VectorSearchResult(
                    clause_id=result.clause_id,
                    text=result.text,
                    score=score,
                    source_start=result.source_start,
                    source_end=result.source_end,
                    heading=result.heading,
                    chunk_id=result.chunk_id,
                    rrf_score=result.rrf_score if result.rrf_score is not None else result.score,
                    rerank_score=score,
                    dense_rank=result.dense_rank,
                    sparse_rank=result.sparse_rank,
                )
            )
        return output


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
        model_key = re.sub(r"[^a-zA-Z0-9_-]+", "_", model_name).strip("_").lower()
        self.collection_name = f"legal_document_chunks_{model_key}"
        self.extracted_collection_name = f"legal_document_page_chunks_{model_key}"

        self.chroma_client = None
        self.collection = None
        self.extracted_collection = None
        self.encoder = None
        self._encoder_load_attempted = False
        self.reranker = SearchReranker()

        if not HAS_CHROMADB:
            raise RuntimeError("chromadb is required for the configured retrieval pipeline.")

        try:
            os.makedirs(self.persist_directory, exist_ok=True)
            self.chroma_client = chromadb.PersistentClient(path=self.persist_directory)
            self.collection = self.chroma_client.get_or_create_collection(
                name=self.collection_name,
                metadata={
                    "hnsw:space": "cosine",
                    "embedding_model": self.model_name,
                    "collection_role": "clause_retrieval",
                },
            )
            self.extracted_collection = self.chroma_client.get_or_create_collection(
                name=self.extracted_collection_name,
                metadata={
                    "hnsw:space": "cosine",
                    "embedding_model": self.model_name,
                    "collection_role": "page_extraction",
                },
            )
            for collection, role in (
                (self.collection, "clause_retrieval"),
                (self.extracted_collection, "page_extraction"),
            ):
                metadata = collection.metadata or {}
                stored_model = metadata.get("embedding_model")
                stored_role = metadata.get("collection_role")
                if stored_model != self.model_name or stored_role != role:
                    raise RuntimeError(
                        f"Vector collection '{collection.name}' does not match the configured embedding model and collection role."
                    )
        except Exception as exc:
            raise RuntimeError(
                f"Unable to initialize ChromaDB collection '{self.collection_name}'."
            ) from exc

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
            if self.encoder is None:
                raise RuntimeError(
                    f"Could not load embedding model '{self.model_name}'."
                )
            return self.encoder

        self._encoder_load_attempted = True
        if not HAS_SENTENCE_TRANSFORMERS:
            raise RuntimeError("sentence-transformers is required for dense retrieval.")

        try:
            self.encoder = _load_sentence_transformer(self.model_name)
        except Exception as exc:
            raise RuntimeError(
                f"Could not load embedding model '{self.model_name}'."
            ) from exc

        return self.encoder

    def reset_collection(self):
        if self.chroma_client is None:
            raise RuntimeError("ChromaDB is not available; cannot reset the evaluation collection.")

        try:
            for item in self.chroma_client.list_collections():
                name = item if isinstance(item, str) else getattr(item, "name", None)
                if name in {self.collection_name, self.extracted_collection_name}:
                    self.chroma_client.delete_collection(name=name)
            self.collection = self.chroma_client.get_or_create_collection(
                name=self.collection_name,
                metadata={
                    "hnsw:space": "cosine",
                    "embedding_model": self.model_name,
                    "collection_role": "clause_retrieval",
                },
            )
            self.extracted_collection = self.chroma_client.get_or_create_collection(
                name=self.extracted_collection_name,
                metadata={
                    "hnsw:space": "cosine",
                    "embedding_model": self.model_name,
                    "collection_role": "page_extraction",
                },
            )
        except Exception as exc:
            raise RuntimeError(f"Unable to reset ChromaDB collection: {exc}") from exc

    def validate_embedding_dimensions(self) -> int:
        encoder = self._get_encoder()
        if encoder is None:
            raise RuntimeError(
                f"Could not load embedding model '{self.model_name}'. Check the model installation and network/cache access."
            )
        if self.collection is None:
            raise RuntimeError("ChromaDB collection is not initialized.")

        stored_model = (self.collection.metadata or {}).get("embedding_model")
        if stored_model != self.model_name:
            raise RuntimeError(
                f"Vector collection model '{stored_model}' does not match configured model '{self.model_name}'."
            )

        expected_dim = encoder.get_embedding_dimension()
        if expected_dim is None:
            raise RuntimeError(f"Embedding model '{self.model_name}' did not report its vector dimension.")

        if self.collection.count() > 0:
            stored = self.collection.get(limit=1, include=["embeddings"])
            embeddings = stored.get("embeddings")
            if embeddings is None or len(embeddings) == 0:
                raise RuntimeError("ChromaDB contains records but no stored embeddings.")
            actual_dim = len(embeddings[0])
            if int(actual_dim) != int(expected_dim):
                raise RuntimeError(
                    f"Embedding dimension mismatch: ChromaDB has {actual_dim}, "
                    f"but model '{self.model_name}' produces {expected_dim}. "
                    "Rebuild the evaluation index."
                )

        return int(expected_dim)

    def chunk_clause(self, clause: Clause) -> list[DocumentChunk]:
        text = clause.text or ""
        if not text.strip():
            return []

        raw_chunks = self._structure_aware_split_with_offsets(text)
        chunks = []

        for idx, (chunk_text, chunk_start, chunk_end) in enumerate(raw_chunks, start=1):
            abs_start = int(clause.source_start) + chunk_start
            abs_end = int(clause.source_start) + chunk_end
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

    def _structure_aware_split_with_offsets(
        self,
        text: str,
        max_chars: int = 1200,
    ) -> list[tuple[str, int, int]]:
        paragraph_spans = []
        paragraph_start = 0

        for separator in re.finditer(r"\n\s*\n", text):
            paragraph_end = separator.start()
            raw_paragraph = text[paragraph_start:paragraph_end]
            left_trim = len(raw_paragraph) - len(raw_paragraph.lstrip())
            right_trim = len(raw_paragraph.rstrip())
            if right_trim > left_trim:
                start = paragraph_start + left_trim
                end = paragraph_start + right_trim
                paragraph_spans.append((text[start:end], start, end))
            paragraph_start = separator.end()

        raw_paragraph = text[paragraph_start:]
        left_trim = len(raw_paragraph) - len(raw_paragraph.lstrip())
        right_trim = len(raw_paragraph.rstrip())
        if right_trim > left_trim:
            start = paragraph_start + left_trim
            end = paragraph_start + right_trim
            paragraph_spans.append((text[start:end], start, end))

        if not paragraph_spans:
            raise RuntimeError("Structure-aware chunking produced no paragraphs.")

        chunks: list[tuple[str, int, int]] = []
        current_start = None
        current_end = None

        def flush_current():
            nonlocal current_start, current_end
            if current_start is not None and current_end is not None:
                chunks.append((text[current_start:current_end], current_start, current_end))
            current_start = None
            current_end = None

        for paragraph, start, end in paragraph_spans:
            if end - start > max_chars:
                flush_current()
                if self.text_splitter is None:
                    raise RuntimeError(
                        "langchain-text-splitters is required for paragraphs over the chunk limit."
                    )
                search_offset = 0
                for part in self.text_splitter.split_text(paragraph):
                    part_start = paragraph.find(part, search_offset)
                    if part_start < 0:
                        raise RuntimeError(
                            "Text splitter returned a chunk that cannot be mapped to the source paragraph."
                        )
                    part_end = part_start + len(part)
                    chunks.append(
                        (
                            part,
                            start + part_start,
                            start + part_end,
                        )
                    )
                    search_offset = part_start + 1
                continue

            starts_new_section = self._looks_like_section_boundary(paragraph)
            projected_length = end - current_start if current_start is not None else end - start

            if current_start is not None and (
                projected_length > max_chars or starts_new_section
            ):
                flush_current()

            if current_start is None:
                current_start = start
            current_end = end

        flush_current()
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

    def index_document_clauses(
        self,
        document_id: str,
        clauses: list[Clause],
        force: bool = False,
    ) -> int:
        if self.collection is None:
            raise RuntimeError("ChromaDB collection is not initialized.")
        if not clauses:
            return 0

        all_chunks = [
            chunk
            for clause in clauses
            for chunk in self.chunk_clause(clause)
        ]
        if not all_chunks:
            return 0

        if force:
            chunks_to_index = all_chunks
        else:
            chunk_ids = [chunk.chunk_id for chunk in all_chunks]
            existing_chunk_ids = set()
            for offset in range(0, len(chunk_ids), 500):
                existing = self.collection.get(
                    ids=chunk_ids[offset : offset + 500],
                    include=["metadatas"],
                )
                existing_chunk_ids.update(existing.get("ids", []))
            chunks_to_index = [
                chunk
                for chunk in all_chunks
                if chunk.chunk_id not in existing_chunk_ids
            ]

        if not chunks_to_index:
            return 0

        encoder = self._get_encoder()
        ids = [chunk.chunk_id for chunk in chunks_to_index]
        texts = [chunk.text for chunk in chunks_to_index]
        metadatas = [chunk.metadata for chunk in chunks_to_index]
        embeddings = encoder.encode(texts, show_progress_bar=False).tolist()

        if len(embeddings) != len(texts):
            raise RuntimeError("Embedding model returned an unexpected number of vectors.")

        expected_dimension = encoder.get_embedding_dimension()
        if expected_dimension is not None and any(
            len(embedding) != expected_dimension for embedding in embeddings
        ):
            raise RuntimeError("Embedding model returned an unexpected vector dimension.")

        try:
            self.collection.upsert(
                ids=ids,
                documents=texts,
                embeddings=embeddings,
                metadatas=metadatas,
            )
        except Exception as exc:
            raise RuntimeError(
                f"Failed to index document '{document_id}' into ChromaDB."
            ) from exc

        logger.info(
            "Indexed %s chunks for document %s into ChromaDB.",
            len(chunks_to_index),
            document_id,
        )
        return len(chunks_to_index)

    def index_extracted_chunks(self, chunks: list[Any]) -> int:
        if not chunks:
            return 0
        if self.extracted_collection is None:
            raise RuntimeError("ChromaDB collection is not initialized.")

        unique_chunks = {}
        for chunk in chunks:
            if not chunk.chunk_id:
                raise ValueError("Every indexed chunk must include chunk_id.")
            unique_chunks.setdefault(chunk.chunk_id, chunk)

        chunk_ids = list(unique_chunks)
        existing_chunk_ids = set()
        for offset in range(0, len(chunk_ids), 500):
            existing = self.extracted_collection.get(
                ids=chunk_ids[offset : offset + 500],
                include=["metadatas"],
            )
            existing_chunk_ids.update(existing.get("ids", []))

        new_chunks = [
            chunk
            for chunk_id, chunk in unique_chunks.items()
            if chunk_id not in existing_chunk_ids
        ]
        if not new_chunks:
            return 0

        encoder = self._get_encoder()
        if encoder is None:
            raise RuntimeError(f"Could not load embedding model '{self.model_name}'.")

        ids = [chunk.chunk_id for chunk in new_chunks]
        texts = [chunk.text for chunk in new_chunks]
        metadatas = [chunk.metadata for chunk in new_chunks]
        embeddings = encoder.encode(texts, show_progress_bar=False).tolist()

        if len(embeddings) != len(texts):
            raise RuntimeError("Embedding model returned an unexpected number of vectors.")

        expected_dimension = encoder.get_embedding_dimension()
        if expected_dimension is not None and any(
            len(embedding) != expected_dimension for embedding in embeddings
        ):
            raise RuntimeError("Embedding model returned an unexpected vector dimension.")

        self.extracted_collection.upsert(
            ids=ids,
            documents=texts,
            embeddings=embeddings,
            metadatas=metadatas,
        )

        return len(new_chunks)

    def dense_search(
        self,
        document_id: str,
        query: str,
        candidate_k: int,
    ) -> list[VectorSearchResult]:
        if not query.strip():
            raise ValueError("query must not be empty.")
        if candidate_k < 1:
            raise ValueError("candidate_k must be positive.")
        if self.collection is None:
            raise RuntimeError("ChromaDB collection is not initialized.")

        encoder = self._get_encoder()
        if encoder is None:
            raise RuntimeError(f"Could not load embedding model '{self.model_name}'.")

        query_instruction = settings.EMBEDDING_QUERY_INSTRUCTION.strip()
        query_text = f"{query_instruction} {query}" if query_instruction else query
        query_embeddings = encoder.encode([query_text], show_progress_bar=False).tolist()
        if len(query_embeddings) != 1:
            raise RuntimeError("Embedding model returned an invalid query embedding.")
        expected_dimension = encoder.get_embedding_dimension()
        if expected_dimension is not None and len(query_embeddings[0]) != expected_dimension:
            raise RuntimeError(
                f"Query embedding dimension {len(query_embeddings[0])} does not match "
                f"the configured dimension {expected_dimension}."
            )

        response = self.collection.query(
            query_embeddings=query_embeddings,
            where={"document_id": document_id},
            n_results=candidate_k,
            include=["documents", "metadatas", "distances"],
        )
        documents = (response.get("documents") or [[]])[0]
        metadatas = (response.get("metadatas") or [[]])[0]
        distances = (response.get("distances") or [[]])[0]
        if not (len(documents) == len(metadatas) == len(distances)):
            raise RuntimeError("ChromaDB returned inconsistent dense retrieval arrays.")

        results = []
        for document, metadata, distance in zip(documents, metadatas, distances):
            if not metadata:
                raise RuntimeError("A dense retrieval result is missing metadata.")
            if str(metadata.get("document_id", "")) != str(document_id):
                raise RuntimeError("Dense retrieval returned a result outside the requested document.")
            chunk_id = metadata.get("chunk_id")
            clause_id = metadata.get("clause_id")
            if not chunk_id or not clause_id:
                raise RuntimeError("Dense retrieval metadata must include chunk_id and clause_id.")
            similarity = 1.0 - float(distance)
            results.append(
                VectorSearchResult(
                    clause_id=str(clause_id),
                    text=str(document or ""),
                    score=similarity,
                    source_start=int(metadata.get("source_start", 0)),
                    source_end=int(metadata.get("source_end", 0)),
                    heading=metadata.get("heading") or None,
                    chunk_id=str(chunk_id),
                )
            )
        return results

    def sparse_search(
        self,
        query: str,
        clauses: list[Clause],
        candidate_k: int,
    ) -> list[VectorSearchResult]:
        return self._sparse_keyword_search(query, clauses, top_k=candidate_k)

    def hybrid_search(
        self,
        document_id: str,
        query: str,
        clauses: list[Clause],
        top_k: int = 5,
        candidate_k: int | None = None,
        apply_reranker: bool = True,
    ) -> list[VectorSearchResult]:
        results, _ = self.hybrid_search_with_trace(
            document_id=document_id,
            query=query,
            clauses=clauses,
            top_k=top_k,
            candidate_k=candidate_k,
            apply_reranker=apply_reranker,
        )
        return results

    def hybrid_search_with_trace(
        self,
        document_id: str,
        query: str,
        clauses: list[Clause],
        top_k: int = 5,
        candidate_k: int | None = None,
        apply_reranker: bool = True,
    ) -> tuple[list[VectorSearchResult], dict[str, Any]]:
        if not query.strip():
            raise ValueError("query must not be empty.")
        if top_k < 1:
            raise ValueError("top_k must be positive.")
        candidate_k = (
            settings.RETRIEVAL_CANDIDATE_K if candidate_k is None else candidate_k
        )
        if candidate_k < top_k:
            raise ValueError("candidate_k must be greater than or equal to top_k.")
        if not clauses:
            return [], {
                "retrieval_pipeline": "dense_bm25_rrf_cross_encoder",
                "dense_candidate_count": 0,
                "sparse_candidate_count": 0,
                "fused_candidate_count": 0,
                "candidate_k": candidate_k,
                "final_k": top_k,
                "reranker_applied": apply_reranker,
            }

        dense_results = self.dense_search(document_id, query, candidate_k)
        sparse_results = self.sparse_search(query, clauses, candidate_k)
        fused_results = self._rrf_fuse(
            dense_results,
            sparse_results,
            top_k=candidate_k,
            k=settings.RRF_K,
        )

        if apply_reranker:
            final_results = self.reranker.rerank(query, fused_results, top_k=top_k)
        else:
            final_results = fused_results[:top_k]

        trace = {
            "retrieval_pipeline": "dense_bm25_rrf_cross_encoder" if apply_reranker else "dense_bm25_rrf",
            "dense_model": self.model_name,
            "sparse_method": "bm25_okapi",
            "fusion_method": "reciprocal_rank_fusion",
            "rrf_k": settings.RRF_K,
            "reranker_model": self.reranker.model_name if apply_reranker else None,
            "dense_candidate_count": len(dense_results),
            "sparse_candidate_count": len(sparse_results),
            "fused_candidate_count": len(fused_results),
            "candidate_k": candidate_k,
            "final_k": top_k,
            "reranker_applied": apply_reranker,
        }
        return final_results, trace

    def _sparse_keyword_search(
        self,
        query: str,
        clauses: list[Clause],
        top_k: int,
    ) -> list[VectorSearchResult]:
        if not query.strip():
            raise ValueError("query must not be empty.")
        if top_k < 1:
            raise ValueError("top_k must be positive.")

        chunks = [
            chunk
            for clause in clauses
            for chunk in self.chunk_clause(clause)
        ]
        if not chunks:
            return []

        query_terms = re.findall(r"\b\w+\b", query.lower())
        if not query_terms:
            raise ValueError("query must contain searchable terms.")

        corpus_terms = [
            re.findall(
                r"\b\w+\b",
                f"{chunk.heading or ''} {chunk.text}".lower(),
            )
            for chunk in chunks
        ]
        document_count = len(corpus_terms)
        document_frequency: dict[str, int] = {}
        for terms in corpus_terms:
            for term in set(terms):
                document_frequency[term] = document_frequency.get(term, 0) + 1

        average_length = sum(len(terms) for terms in corpus_terms) / document_count
        k1 = 1.5
        b = 0.75
        scored_results = []

        for chunk, terms in zip(chunks, corpus_terms):
            term_frequency: dict[str, int] = {}
            for term in terms:
                term_frequency[term] = term_frequency.get(term, 0) + 1

            score = 0.0
            for term in query_terms:
                frequency = term_frequency.get(term, 0)
                if frequency == 0:
                    continue
                df = document_frequency[term]
                inverse_document_frequency = log(
                    1.0 + (document_count - df + 0.5) / (df + 0.5)
                )
                length_normalizer = 1.0 - b + b * (len(terms) / average_length)
                denominator = frequency + k1 * length_normalizer
                score += inverse_document_frequency * (
                    frequency * (k1 + 1.0) / denominator
                )

            if score <= 0.0:
                continue

            scored_results.append(
                VectorSearchResult(
                    clause_id=chunk.clause_id,
                    text=chunk.text,
                    score=float(score),
                    source_start=chunk.source_start,
                    source_end=chunk.source_end,
                    heading=chunk.heading,
                    chunk_id=chunk.chunk_id,
                )
            )

        scored_results.sort(key=lambda item: item.score, reverse=True)
        return scored_results[:top_k]

    def _rrf_fuse(
        self,
        dense_results: list[VectorSearchResult],
        sparse_results: list[VectorSearchResult],
        top_k: int,
        k: int = 60,
    ) -> list[VectorSearchResult]:
        if top_k < 1 or k < 1:
            raise ValueError("top_k and k must be positive.")

        ranked_lists = []
        for result_set in (dense_results, sparse_results):
            unique_results = []
            seen_chunk_ids = set()
            for result in result_set:
                if not result.chunk_id:
                    raise ValueError("RRF candidates must include chunk_id.")
                if result.chunk_id in seen_chunk_ids:
                    continue
                seen_chunk_ids.add(result.chunk_id)
                unique_results.append(result)
            ranked_lists.append(unique_results)

        fused_scores: dict[str, float] = {}
        representatives: dict[str, VectorSearchResult] = {}
        ranks: dict[str, dict[str, int]] = {}

        for source_name, result_set in zip(("dense", "sparse"), ranked_lists):
            for rank, result in enumerate(result_set, start=1):
                chunk_id = result.chunk_id
                fused_scores[chunk_id] = fused_scores.get(chunk_id, 0.0) + (
                    1.0 / (k + rank)
                )
                representatives.setdefault(chunk_id, result)
                ranks.setdefault(chunk_id, {})[source_name] = rank

        ranked = []
        for chunk_id, fused_score in fused_scores.items():
            result = representatives[chunk_id]
            ranked.append(
                VectorSearchResult(
                    clause_id=result.clause_id,
                    text=result.text,
                    score=fused_score,
                    source_start=result.source_start,
                    source_end=result.source_end,
                    heading=result.heading,
                    chunk_id=chunk_id,
                    rrf_score=fused_score,
                    dense_rank=ranks.get(chunk_id, {}).get("dense"),
                    sparse_rank=ranks.get(chunk_id, {}).get("sparse"),
                )
            )

        ranked.sort(key=lambda item: item.score, reverse=True)
        return ranked[:top_k]

