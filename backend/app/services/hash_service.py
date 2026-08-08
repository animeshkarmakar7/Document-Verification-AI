import hashlib

from fastapi import UploadFile


class HashService:

    CHUNK_SIZE = 1024 * 1024  # 1 MB

    async def calculate_sha256(
        self,
        file: UploadFile,
    ) -> str:

        digest = hashlib.sha256()

        while True:

            chunk = await file.read(
                self.CHUNK_SIZE
            )

            if not chunk:
                break

            digest.update(chunk)

        # Reset the pointer so the same file
        # can be uploaded to storage afterward.
        await file.seek(0)

        return digest.hexdigest()