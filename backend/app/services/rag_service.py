from typing import Any
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from app.config.settings import settings
from app.models.chat import ChatMessage
from app.models.clause import Clause
from app.repositories.chat_repository import ChatRepository
from app.repositories.clause_repository import ClauseRepository
from app.repositories.document_repository import DocumentRepository
from app.services.vector_store_service import VectorStoreService, VectorSearchResult
from app.services.gemini_rate_limiter import wait_for_gemini_request
from sqlalchemy.orm import Session



class RAGServiceError(Exception):
    pass


class DocumentNotFoundError(RAGServiceError):
    pass


class GroundedCitation(BaseModel):
    clause_id: str
    source_span_start: int
    source_span_end: int
    quoted_text: str


class GroundedAnswerBatch(BaseModel):
    answer: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    citations: list[GroundedCitation]


class GeneratedCitation(BaseModel):
    clause_id: str = Field(..., min_length=1)
    quoted_text: str = Field(..., min_length=1)


class GeneratedAnswerBatch(BaseModel):
    answer: str = Field(..., min_length=1)
    confidence: float = Field(..., ge=0.0, le=1.0)
    citations: list[GeneratedCitation]


class RAGService:

    def __init__(
        self,
        db: Session,
        api_key: str | None = None,
        model_name: str | None = None,
        vector_store: VectorStoreService | None = None,
        client: Any = None,
    ):
        self.db = db
        self.doc_repo = DocumentRepository(db)
        self.clause_repo = ClauseRepository(db)
        self.chat_repo = ChatRepository(db)
        self.vector_store = vector_store or VectorStoreService()
        self.api_key = api_key if api_key is not None else settings.GEMINI_API_KEY
        self.model_name = model_name or settings.GEMINI_MODEL
        self.client = client or (
            genai.Client(api_key=self.api_key) if self.api_key else None
        )

    def chat(
        self,
        document_id: str,
        query: str,
        top_k: int = settings.RETRIEVAL_FINAL_K,
        candidate_k: int = settings.RETRIEVAL_CANDIDATE_K,
        *,
        persist_messages: bool = True,
        include_evaluation_details: bool = False,
        index_document: bool = True,
    ) -> dict:
        doc = self.doc_repo.get_by_id(document_id)
        if not doc:
            raise DocumentNotFoundError(f"Document '{document_id}' not found")

        clauses = self.clause_repo.list_by_document(document_id)
        if not clauses:
            no_clause_answer = "No clauses found for this document to answer your question."
            assistant_msg = None
            if persist_messages:
                user_msg = ChatMessage(document_id=document_id, role="user", content=query)
                self.chat_repo.create(user_msg)
                assistant_msg = ChatMessage(
                    document_id=document_id,
                    role="assistant",
                    content=no_clause_answer,
                    citations=[],
                    confidence=0.0,
                )
                self.chat_repo.create(assistant_msg)
                self.db.commit()
            result = {
                "message_id": assistant_msg.id if assistant_msg else None,
                "document_id": document_id,
                "query": query,
                "answer": no_clause_answer,
                "citations": [],
                "confidence": 0.0,
                "created_at": assistant_msg.created_at if assistant_msg else None,
            }
            if include_evaluation_details:
                result.update({
                    "retrieved_contexts": [],
                    "retrieved_clause_ids": [],
                    "retrieval_scores": [],
                    "generation_mode": "no_clauses",
                })
            return result

        if index_document:
            self.vector_store.index_document_clauses(
                document_id,
                clauses,
            )

        search_results, retrieval_trace = self.vector_store.hybrid_search_with_trace(
            document_id=document_id,
            query=query,
            clauses=clauses,
            top_k=top_k,
            candidate_k=candidate_k,
            apply_reranker=True,
        )

        if persist_messages:
            self.chat_repo.create(ChatMessage(document_id=document_id, role="user", content=query))

        if not search_results:
            answer_data = GroundedAnswerBatch(
                answer="The available document clauses do not provide sufficient evidence to answer this question.",
                confidence=0.0,
                citations=[],
            )
            generation_mode = "no_retrieved_context"
        else:
            if self.client is None:
                raise RuntimeError("GEMINI_API_KEY is required for grounded answer generation.")
            answer_data = self._generate_gemini_answer(query, search_results)
            generation_mode = "gemini"

        citations_json = [citation.model_dump() for citation in answer_data.citations]
        assistant_msg = None
        if persist_messages:
            assistant_msg = ChatMessage(
                document_id=document_id,
                role="assistant",
                content=answer_data.answer,
                citations=citations_json,
                confidence=answer_data.confidence,
            )
            self.chat_repo.create(assistant_msg)
            self.db.commit()

        result = {
            "message_id": assistant_msg.id if assistant_msg else None,
            "document_id": document_id,
            "query": query,
            "answer": answer_data.answer,
            "citations": citations_json,
            "confidence": answer_data.confidence,
            "created_at": assistant_msg.created_at if assistant_msg else None,
        }
        if include_evaluation_details:
            result.update({
                "retrieved_contexts": [item.text for item in search_results],
                "retrieved_clause_ids": [item.clause_id for item in search_results],
                "retrieval_scores": [item.score for item in search_results],
                "retrieved_chunk_ids": [item.chunk_id for item in search_results],
                "retrieval_trace": retrieval_trace,
                "generation_mode": generation_mode,
            })
        return result

    def get_chat_history(self, document_id: str) -> list[ChatMessage]:
        doc = self.doc_repo.get_by_id(document_id)
        if not doc:
            raise DocumentNotFoundError(f"Document '{document_id}' not found")
        return self.chat_repo.list_by_document(document_id)

    def _generate_gemini_answer(
        self, query: str, search_results: list[VectorSearchResult]
    ) -> GroundedAnswerBatch:
        context_parts = []
        for result in search_results:
            heading_info = f" ({result.heading})" if result.heading else ""
            context_parts.append(
                f"--- Clause ID: {result.clause_id}{heading_info} ---\n"
                f"{result.text}"
            )
        context_str = "\n\n".join(context_parts)

        prompt = (
            "You are a strict, grounded legal assistant. Answer the user's question ONLY using the provided contract clauses.\n"
            "Rules:\n"
            "1. Base every factual statement strictly on the supplied context.\n"
            "2. Cite every material factual claim with a clause_id from the supplied context.\n"
            "3. For each citation, provide a short, contiguous, verbatim quote copied from that clause.\n"
            "4. Preserve the exact capitalization, punctuation, and wording of each quote. Do not paraphrase, add ellipses, or add quotation marks to the quoted_text value.\n"
            "5. Return only clause_id and quoted_text for each citation. Do not generate offsets, line numbers, or source positions.\n"
            "6. Do not infer missing names, amounts, dates, obligations, or legal outcomes.\n"
            "7. If the context does not establish the answer, explicitly abstain and set confidence below 0.5.\n"
            "8. Return the required structured JSON only.\n\n"
            f"Question: {query}\n\n"
            f"Context Clauses:\n{context_str}"
        )

        wait_for_gemini_request()
        response = self.client.models.generate_content(
            model=self.model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=GeneratedAnswerBatch,
                temperature=0.1,
            ),
        )
        if not response or not response.text:
            raise RuntimeError("Gemini returned an empty structured response.")

        generated = GeneratedAnswerBatch.model_validate_json(response.text)
        if generated.confidence >= 0.5 and not generated.citations:
            raise ValueError("A non-abstaining answer must include at least one source citation.")

        answer = GroundedAnswerBatch(
            answer=generated.answer,
            confidence=generated.confidence,
            citations=self._ground_citations(generated.citations, search_results),
        )
        self._validate_citations(answer, search_results)
        return answer

    @staticmethod
    def _find_quote_span(source_text: str, quoted_text: str) -> tuple[int, int] | None:
        normalized_chars = []
        source_spans = []
        cursor = 0

        while cursor < len(source_text):
            if source_text[cursor].isspace():
                whitespace_start = cursor
                while cursor < len(source_text) and source_text[cursor].isspace():
                    cursor += 1
                if normalized_chars and cursor < len(source_text):
                    normalized_chars.append(" ")
                    source_spans.append((whitespace_start, cursor))
            else:
                normalized_chars.append(source_text[cursor])
                source_spans.append((cursor, cursor + 1))
                cursor += 1

        normalized_source = "".join(normalized_chars)
        normalized_quote = " ".join(quoted_text.split())
        if not normalized_quote:
            return None

        match_start = normalized_source.find(normalized_quote)
        if match_start < 0:
            return None

        match_end = match_start + len(normalized_quote)
        return (
            source_spans[match_start][0],
            source_spans[match_end - 1][1],
        )

    @staticmethod
    def _ground_citations(
        generated_citations: list[GeneratedCitation],
        search_results: list[VectorSearchResult],
    ) -> list[GroundedCitation]:
        grounded_citations = []
        seen_spans = set()

        for citation in generated_citations:
            matched_result = None
            matched_span = None

            for result in search_results:
                if result.clause_id != citation.clause_id:
                    continue
                if result.source_end - result.source_start != len(result.text):
                    raise RuntimeError(
                        f"Retrieved source offsets do not align with chunk text for clause '{result.clause_id}'."
                    )

                span = RAGService._find_quote_span(
                    result.text,
                    citation.quoted_text,
                )
                if span is not None:
                    matched_result = result
                    matched_span = span
                    break

            if matched_result is None or matched_span is None:
                raise ValueError(
                    f"Quoted evidence for clause '{citation.clause_id}' "
                    "was not found verbatim in retrieved context."
                )

            local_start, local_end = matched_span
            source_start = matched_result.source_start + local_start
            source_end = matched_result.source_start + local_end
            canonical_quote = matched_result.text[local_start:local_end]

            if source_end <= source_start:
                raise ValueError("A grounded citation must have a non-empty source span.")

            span_key = (citation.clause_id, source_start, source_end)
            if span_key in seen_spans:
                continue
            seen_spans.add(span_key)

            grounded_citations.append(
                GroundedCitation(
                    clause_id=citation.clause_id,
                    source_span_start=source_start,
                    source_span_end=source_end,
                    quoted_text=canonical_quote,
                )
            )

        return grounded_citations

    @staticmethod
    def _validate_citations(
        answer: GroundedAnswerBatch,
        search_results: list[VectorSearchResult],
    ) -> None:
        for citation in answer.citations:
            if not citation.quoted_text:
                raise ValueError("A citation must include quoted source text.")
            if citation.source_span_end <= citation.source_span_start:
                raise ValueError("A citation source span must have a positive length.")

            valid_quote = False
            for result in search_results:
                if result.clause_id != citation.clause_id:
                    continue
                if not (
                    result.source_start <= citation.source_span_start
                    and citation.source_span_end <= result.source_end
                ):
                    continue
                if result.source_end - result.source_start != len(result.text):
                    raise RuntimeError(
                        f"Retrieved source offsets do not align with chunk text for clause '{result.clause_id}'."
                    )

                local_start = citation.source_span_start - result.source_start
                local_end = citation.source_span_end - result.source_start
                source_quote = result.text[local_start:local_end]
                if source_quote == citation.quoted_text:
                    valid_quote = True
                    break

            if not valid_quote:
                raise ValueError(
                    f"Citation for clause '{citation.clause_id}' does not match its exact retrieved source span."
                )
