import boto3
from app.config.settings import settings
from botocore.exceptions import ClientError


class StorageService:

    def __init__(self):

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

    def download_file(
        self,
        object_key: str,
    ) -> bytes:

        response = self.client.get_object(
            Bucket=self.bucket,
            Key=object_key,
        )

        return response["Body"].read()

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
