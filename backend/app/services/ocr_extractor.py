import xml.etree.ElementTree as ET
from dataclasses import dataclass
from io import BytesIO
from zipfile import ZipFile

from google import genai
from google.genai import types
from pypdf import PdfReader

from app.config.settings import settings


class OCRExtractionError(Exception):
    pass


@dataclass(frozen=True)
class OCRExtraction:
    text: str
    page_count: int
    layout: dict


class LocalOCRExtractor:
    provider = "local-text-extractor"

    def extract(
        self,
        content: bytes,
        extension: str,
    ) -> OCRExtraction:

        if extension == ".pdf":
            return self._extract_pdf(content)

        if extension == ".docx":
            return self._extract_docx(content)

        if extension in {".png", ".jpg", ".jpeg", ".webp", ".tiff"}:
            return self._extract_image(content, extension)

        raise OCRExtractionError(
            f"Unsupported file format for OCR: {extension}"
        )

    def _extract_pdf(self, content: bytes) -> OCRExtraction:
        reader = PdfReader(BytesIO(content))
        pages = []

        for index, page in enumerate(reader.pages, start=1):
            page_text = page.extract_text() or ""
            pages.append(
                {
                    "page_number": index,
                    "text": page_text,
                }
            )

        text = "\n\n".join(page["text"] for page in pages).strip()

        if not text:
            raise OCRExtractionError(
                "No text was extracted. This may be a scanned PDF "
                "that needs image-based Document OCR."
            )

        return OCRExtraction(
            text=text,
            page_count=len(pages),
            layout={
                "pages": pages,
            },
        )

    def _extract_docx(self, content: bytes) -> OCRExtraction:
        namespace = {
            "w": (
                "http://schemas.openxmlformats.org/"
                "wordprocessingml/2006/main"
            )
        }

        with ZipFile(BytesIO(content)) as archive:
            document_xml = archive.read("word/document.xml")

        root = ET.fromstring(document_xml)
        paragraphs = []

        for paragraph in root.findall(".//w:p", namespace):
            parts = [
                node.text
                for node in paragraph.findall(".//w:t", namespace)
                if node.text
            ]
            if parts:
                paragraphs.append("".join(parts))

        text = "\n".join(paragraphs).strip()

        if not text:
            raise OCRExtractionError(
                "No text was extracted from the DOCX file."
            )

        return OCRExtraction(
            text=text,
            page_count=1,
            layout={
                "pages": [
                    {
                        "page_number": 1,
                        "text": text,
                    }
                ]
            },
        )

    def _extract_image(self, content: bytes, extension: str) -> OCRExtraction:
        mime_map = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
            ".tiff": "image/tiff",
        }
        mime_type = mime_map.get(extension, "image/jpeg")

        try:
            client = genai.Client(api_key=settings.GEMINI_API_KEY)
            image_part = types.Part.from_bytes(
                data=content,
                mime_type=mime_type,
            )
            prompt = (
                "Extract all printed and handwritten text from this legal document image "
                "verbatim. Preserve layout, numbered section titles, paragraphs, and formatting. "
                "Do not add summary commentary."
            )
            response = client.models.generate_content(
                model=settings.GEMINI_MODEL,
                contents=[image_part, prompt],
            )
            extracted_text = (response.text or "").strip()

            if not extracted_text:
                raise OCRExtractionError(
                    f"No text could be extracted from image ({extension})."
                )

            return OCRExtraction(
                text=extracted_text,
                page_count=1,
                layout={
                    "pages": [
                        {
                            "page_number": 1,
                            "text": extracted_text,
                        }
                    ]
                },
            )
        except Exception as exc:
            raise OCRExtractionError(
                f"Image OCR failed for {extension}: {exc}"
            ) from exc
