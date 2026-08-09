import json
import logging
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from app.config.settings import settings
from app.models.chat import ChatMessage
from app.models.clause import Clause
from app.repositories.chat_repository import ChatRepository
from app.repositories.clause_repository import ClauseRepository
from app.repositories.document_repository import DocumentRepository
from app.services.embedding_service import ClauseEmbeddingService
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

SIMILARITY_THRESHOLD = 0.15


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
    ):
        self.db = db
        self.doc_repo = DocumentRepository(db)
        self.clause_repo = ClauseRepository(db)
        self.chat_repo = ChatRepository(db)
        self.search_service = ClauseEmbeddingService()
        self.api_key = api_key or settings.GEMINI_API_KEY
        self.model_name = model_name or settings.GEMINI_MODEL
        self.client = genai.Client(api_key=self.api_key) if self.api_key else None

    def chat(self, document_id: str, query: str, top_k: int = 3) -> dict:
        doc = self.doc_repo.get_by_id(document_id)
        if not doc:
            raise DocumentNotFoundError(f"Document '{document_id}' not found")

        clauses = self.clause_repo.list_by_document(document_id)
        if not clauses:
            user_msg = ChatMessage(
                document_id=document_id, role="user", content=query
            )
            self.chat_repo.create(user_msg)
            assistant_msg = ChatMessage(
                document_id=document_id,
                role="assistant",
                content="No clauses found for this document to answer your question.",
                citations=[],
                confidence=0.0,
            )
            self.chat_repo.create(assistant_msg)
            self.db.commit()
            return {
                "message_id": assistant_msg.id,
                "document_id": document_id,
                "query": query,
                "answer": assistant_msg.content,
                "citations": [],
                "confidence": 0.0,
                "created_at": assistant_msg.created_at,
            }

        search_results = self.search_service.search_similar_clauses(
            query=query, clauses=clauses, top_k=top_k
        )
        retrieved_clauses = [r.clause for r in search_results]

        best_score = search_results[0].score if search_results else 0.0

        user_msg = ChatMessage(
            document_id=document_id, role="user", content=query
        )
        self.chat_repo.create(user_msg)

        if not self.client or best_score < SIMILARITY_THRESHOLD:
            answer_data = self._generate_fallback(query, retrieved_clauses, best_score)
        else:
            answer_data = self._generate_gemini_answer(query, retrieved_clauses)

        citations_json = [c.model_dump() for c in answer_data.citations]

        assistant_msg = ChatMessage(
            document_id=document_id,
            role="assistant",
            content=answer_data.answer,
            citations=citations_json,
            confidence=answer_data.confidence,
        )
        self.chat_repo.create(assistant_msg)
        self.db.commit()

        return {
            "message_id": assistant_msg.id,
            "document_id": document_id,
            "query": query,
            "answer": answer_data.answer,
            "citations": citations_json,
            "confidence": answer_data.confidence,
            "created_at": assistant_msg.created_at,
        }

    def get_chat_history(self, document_id: str) -> list[ChatMessage]:
        doc = self.doc_repo.get_by_id(document_id)
        if not doc:
            raise DocumentNotFoundError(f"Document '{document_id}' not found")
        return self.chat_repo.list_by_document(document_id)

    def _generate_gemini_answer(
        self, query: str, clauses: list[Clause]
    ) -> GroundedAnswerBatch:
        context_str = ""
        for c in clauses:
            context_str += f"--- Clause ID: {c.clause_id} (span: {c.source_start}-{c.source_end}) ---\n{c.text}\n\n"

        prompt = (
            "You are a strict, grounded legal assistant. Answer the user's question ONLY using the provided contract clauses.\n"
            "Rules:\n"
            "1. Base your answer strictly on the provided context clauses.\n"
            "2. For every fact or claim in your answer, add a citation matching the clause_id and exact span.\n"
            "3. If the context does not contain enough information to answer the question, state that clearly and set confidence < 0.5.\n\n"
            f"Question: {query}\n\n"
            f"Context Clauses:\n{context_str}"
        )

        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=GroundedAnswerBatch,
                    temperature=0.1,
                ),
            )
            raw = response.text or "{}"
            parsed = json.loads(raw)
            return GroundedAnswerBatch(**parsed)
        except Exception as e:
            logger.warning(f"Gemini RAG call failed, using fallback: {e}")
            return self._generate_fallback(query, clauses, 0.5)

    def _generate_fallback(
        self, query: str, clauses: list[Clause], best_score: float
    ) -> GroundedAnswerBatch:
        if not clauses or best_score < SIMILARITY_THRESHOLD:
            return GroundedAnswerBatch(
                answer=(
                    "We are not confident in answering this question based on the document clauses. "
                    "Please consult a legal professional."
                ),
                confidence=0.2,
                citations=[],
            )

        top_clause = clauses[0]
        summary = (
            f"Based on clause '{top_clause.clause_id}': \"{top_clause.text[:200]}...\". "
            "Please review the highlighted section of your document for full details."
        )
        citation = GroundedCitation(
            clause_id=top_clause.clause_id,
            source_span_start=top_clause.source_start,
            source_span_end=top_clause.source_end,
            quoted_text=top_clause.text[:150],
        )
        return GroundedAnswerBatch(
            answer=summary,
            confidence=0.7,
            citations=[citation],
        )
