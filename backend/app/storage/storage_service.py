from app.config.settings import settings

try:
    from botocore.exceptions import ClientError
except ImportError:
    ClientError = Exception


class StorageService:

    def __init__(self):
        try:
            import boto3
        except ImportError as exc:
            raise RuntimeError(
                "boto3 is required for S3/MinIO storage operations."
            ) from exc

        self.client = boto3.client(
            "s3",
            endpoint_url=settings.STORAGE_ENDPOINT,
            aws_access_key_id=(
                settings.STORAGE_ACCESS_KEY
            ),
            aws_secret_access_key=(
                settings.STORAGE_SECRET_KEY
            ),
            region_name=settings.STORAGE_REGION,
        )

        self.bucket = settings.STORAGE_BUCKET

        self.ensure_bucket_exists()

    def ensure_bucket_exists(self) -> None:

        try:

            self.client.head_bucket(
                Bucket=self.bucket,
            )

        except ClientError as exc:

            error_code = exc.response.get(
                "Error",
                {},
            ).get("Code")

            if error_code not in {
                "404",
                "NoSuchBucket",
                "NotFound",
            }:
                raise

            self.client.create_bucket(
                Bucket=self.bucket,
            )

    def upload_file(
        self,
        file_object,
        object_key: str,
        content_type: str,
    ) -> str:

        self.client.upload_fileobj(
            file_object,
            self.bucket,
            object_key,
            ExtraArgs={
                "ContentType": content_type,
            },
        )

        return (
            f"s3://{self.bucket}/{object_key}"
        )

    def create_presigned_put_url(
        self,
        object_key: str,
        content_type: str,
        expires_in: int | None = None,
    ) -> str:

        return self.client.generate_presigned_url(
            ClientMethod="put_object",
            Params={
                "Bucket": self.bucket,
                "Key": object_key,
                "ContentType": content_type,
            },
            ExpiresIn=expires_in or settings.PRESIGNED_UPLOAD_EXPIRY_SECONDS,
            HttpMethod="PUT",
        )

    def download_file(
        self,
        object_key: str,
    ) -> bytes:

        response = self.client.get_object(
            Bucket=self.bucket,
            Key=object_key,
        )

        return response["Body"].read()

    def download_file_to_path(
        self,
        object_key: str,
        destination_path: str,
    ) -> None:

        with open(destination_path, "wb") as handle:
            self.client.download_fileobj(
                self.bucket,
                object_key,
                handle,
            )

    def delete_file(
        self,
        object_key: str,
    ) -> None:

        self.client.delete_object(
            Bucket=self.bucket,
            Key=object_key,
        )

    def file_exists(
        self,
        object_key: str,
    ) -> bool:

        try:

            self.client.head_object(
                Bucket=self.bucket,
                Key=object_key,
            )

            return True

        except ClientError:

            return False
