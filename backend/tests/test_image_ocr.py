from unittest.mock import MagicMock
import pytest
from app.services.ocr_extractor import LocalOCRExtractor, OCRExtractionError


def test_image_ocr_unsupported_extension():
    extractor = LocalOCRExtractor()
    with pytest.raises(OCRExtractionError):
        extractor.extract(b"dummy", ".invalid")


def test_image_ocr_success(monkeypatch):
    extractor = LocalOCRExtractor()

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = "1. Rent Payment\nTenant agrees to pay $1000 monthly."
    mock_client.models.generate_content.return_value = mock_response

    monkeypatch.setattr("google.genai.Client", lambda api_key: mock_client)

    res = extractor.extract(b"fake-image-bytes", ".png")
    assert res.text.startswith("1. Rent Payment")
    assert res.page_count == 1
