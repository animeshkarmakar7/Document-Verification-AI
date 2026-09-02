import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile

from app.models.ingestion import PageShardStatus
from app.storage.storage_service import StorageService


@dataclass(frozen=True)
class ExtractedShardChunk:
    chunk_id: str
    document_id: str
    shard_index: int
    page_number: int
    text: str
    chunk_hash: str
    metadata: dict


class PageShardProcessor:
    def __init__(self, storage_service: StorageService | None = None):
        self.storage_service = storage_service or StorageService()

    def extract_chunks(
        self,
        document_id: str,
        object_key: str,
        shard: PageShardStatus,
        processing_pool: str = "cpu",
    ) -> list[ExtractedShardChunk]:
        with NamedTemporaryFile(suffix=Path(object_key).suffix or ".pdf", delete=True) as temp_file:
            self.storage_service.download_file_to_path(object_key, temp_file.name)
            return self._extract_from_path(document_id, temp_file.name, shard, processing_pool)

    def _extract_from_path(
        self,
        document_id: str,
        file_path: str,
        shard: PageShardStatus,
        processing_pool: str,
    ) -> list[ExtractedShardChunk]:
        import fitz
        from langchain_text_splitters import RecursiveCharacterTextSplitter

        splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
            chunk_size=900,
            chunk_overlap=120,
            separators=["\n\n", "\n", ". ", "; ", ", ", " "],
        )
        doc = fitz.open(file_path)
        chunks: list[ExtractedShardChunk] = []

        try:
            for page_number in range(shard.page_start, shard.page_end + 1):
                page = doc.load_page(page_number - 1)
                page_text = page.get_text("text").strip()
                if not page_text and processing_pool == "gpu":
                    page_text = self._ocr_page_with_vision(page)
                if not page_text:
                    continue

                section_title = self._infer_section_title(page_text)
                for chunk_index, chunk_text in enumerate(splitter.split_text(page_text), start=1):
                    chunk_hash = self._chunk_hash(chunk_text)
                    chunk_id = (
                        f"{document_id}-p{page_number:05d}-"
                        f"s{shard.shard_index:04d}-c{chunk_index:03d}-{chunk_hash[:12]}"
                    )
                    chunks.append(
                        ExtractedShardChunk(
                            chunk_id=chunk_id,
                            document_id=document_id,
                            shard_index=shard.shard_index,
                            page_number=page_number,
                            text=chunk_text,
                            chunk_hash=chunk_hash,
                            metadata={
                                "document_id": document_id,
                                "shard_index": shard.shard_index,
                                "page_number": page_number,
                                "page_start": shard.page_start,
                                "page_end": shard.page_end,
                                "section_title": section_title,
                                "chunk_hash": chunk_hash,
                                "chunk_id": chunk_id,
                            },
                        )
                    )
        finally:
            doc.close()

        return chunks

    def _ocr_page_with_vision(self, page) -> str:
        import fitz
        from app.services.ocr_extractor import LocalOCRExtractor

        pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2))
        png_bytes = pixmap.tobytes("png")
        return LocalOCRExtractor()._extract_image(png_bytes, ".png").text

    def _infer_section_title(self, text: str) -> str:
        for line in text.splitlines():
            candidate = line.strip()
            if not candidate:
                continue
            if re.match(r"^((section|clause|article)\s+[\w.]+|[A-Z][A-Z\s]{3,80})", candidate, re.IGNORECASE):
                return candidate[:255]
            return candidate[:120]
        return ""

    def _chunk_hash(self, text: str) -> str:
        normalized = re.sub(r"\s+", " ", text).strip().lower()
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
