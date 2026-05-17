from uuid import uuid4

import boto3
from fastapi import UploadFile

from ..config import settings


def _client():
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
    )


def ensure_bucket() -> None:
    client = _client()
    buckets = {bucket["Name"] for bucket in client.list_buckets().get("Buckets", [])}
    if settings.s3_bucket not in buckets:
        client.create_bucket(Bucket=settings.s3_bucket)


async def upload_photo(file: UploadFile) -> str:
    ensure_bucket()
    key = f"photos/{uuid4()}-{file.filename}"
    client = _client()
    client.upload_fileobj(file.file, settings.s3_bucket, key, ExtraArgs={"ContentType": file.content_type or "image/jpeg"})
    return f"{settings.s3_public_base_url}/{key}"
