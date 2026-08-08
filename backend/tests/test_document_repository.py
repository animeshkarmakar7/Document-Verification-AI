import uuid

import pytest
from app.database.database import SessionLocal
from app.models.document import Document
from app.models.enums import DocumentStatus
from app.repositories.document_repository import (
    DocumentRepository,
)


@pytest.mark.integration
def test_get_by_sha256():

    db = SessionLocal()

    sha256 = "a" * 64

    try:
        document = Document(
            id=str(uuid.uuid4()),
            original_filename="repository-test.pdf",
            stored_filename=f"{uuid.uuid4()}.pdf",
            mime_type="application/pdf",
            extension=".pdf",
            storage_uri=(
                f"documents/raw/{uuid.uuid4()}.pdf"
            ),
            object_key=(
                f"documents/raw/{uuid.uuid4()}.pdf"
            ),
            file_size=1024,
            sha256=sha256,
            checksum_algorithm="SHA-256",
            status=DocumentStatus.UPLOADED,
        )

        repository = DocumentRepository(db)

        repository.create(document)

        # Force the INSERT here.
        db.flush()

        found = repository.get_by_sha256(
            sha256
        )

        assert found is not None
        assert found.sha256 == sha256

        db.rollback()

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()
