from io import BytesIO

from app.storage.storage_service import StorageService


def main():

    storage = StorageService()

    content = b"Legal Document AI storage test"

    file_object = BytesIO(content)

    object_key = "temp/storage_test.txt"

    uploaded_key = storage.upload_file(
        file_object=file_object,
        object_key=object_key,
        content_type="text/plain",
    )

    print(f"Uploaded: {uploaded_key}")

    exists = storage.file_exists(object_key)

    print(f"Exists: {exists}")

    downloaded = storage.download_file(object_key)

    print(
        f"Downloaded: {downloaded.decode('utf-8')}"
    )

    storage.delete_file(object_key)

    print(
        f"Exists after delete: "
        f"{storage.file_exists(object_key)}"
    )


if __name__ == "__main__":
    main()