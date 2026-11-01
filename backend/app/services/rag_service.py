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
        context_str = ""
        for result in search_results:
            heading_info = f" ({result.heading})" if result.heading else ""
            context_str += (
                f"--- Clause ID: {result.clause_id}{heading_info} "
                f"(span: {result.source_start}-{result.source_end}) ---\n"
                f"{result.text}\n\n"
            )

        prompt = (
            "You are a strict, grounded legal assistant. Answer the user's question ONLY using the provided contract clauses.\n"
            "Rules:\n"
            "1. Base your answer strictly on the provided context clauses.\n"
            "2. For every factual claim, add a citation matching the exact clause_id and source span.\n"
            "3. Do not infer missing names, amounts, dates, obligations, or legal outcomes.\n"
            "4. If the context does not contain enough information, explicitly abstain and set confidence below 0.5.\n"
            "5. Use only the supplied evidence and return the required structured JSON.\n\n"
            f"Question: {query}\n\n"
            f"Context Clauses:\n{context_str}"
        )

        response = self.client.models.generate_content(
            model=self.model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=GroundedAnswerBatch,
                temperature=0.1,
            ),
        )
        if not response or not response.text:
            raise RuntimeError("Gemini returned an empty structured response.")

        answer = GroundedAnswerBatch.model_validate_json(response.text)
        if answer.confidence >= 0.5 and not answer.citations:
            raise ValueError("A non-abstaining answer must include at least one source citation.")
        self._validate_citations(answer, search_results)
        return answer

    @staticmethod
    def _validate_citations(
        answer: GroundedAnswerBatch,
        search_results: list[VectorSearchResult],
    ) -> None:
        for citation in answer.citations:
            matches = [
                result
                for result in search_results
                if result.clause_id == citation.clause_id
                and result.source_start <= citation.source_span_start
                and citation.source_span_end <= result.source_end
            ]
            if not citation.quoted_text.strip():
                raise ValueError("A citation must include quoted source text.")
            normalized_quote = " ".join(citation.quoted_text.lower().split())
            valid_quote = any(
                " ".join(
                    result.text[
                        citation.source_span_start - result.source_start :
                        citation.source_span_end - result.source_start
                    ].lower().split()
                ) == normalized_quote
                for result in matches
            )
            if not valid_quote:
                raise ValueError(
                    f"Citation for clause '{citation.clause_id}' does not match its exact retrieved source span."
                )


