import os
from typing import Any, cast

from boto3.session import Session
from mypy_boto3_s3.client import S3Client

from config.environment import (
    CAPTURE_AWS_ACCESS_KEY_ID,
    CAPTURE_AWS_SECRET_ACCESS_KEY,
    CAPTURE_S3_ENDPOINT_URL,
)
from topology.buckets import (
    ARCHIVE_ARTIFACTS_BUCKET,
    ARCHIVE_MANIFESTS_BUCKET,
    AUTH_PROFILE_BUCKET,
)

BUCKETS: tuple[str, ...] = (
    ARCHIVE_ARTIFACTS_BUCKET,
    ARCHIVE_MANIFESTS_BUCKET,
    AUTH_PROFILE_BUCKET,
)

DELETE_BATCH_SIZE = 1000


def new_s3_client() -> S3Client:
    return Session().client(
        "s3",
        endpoint_url=os.environ.get(CAPTURE_S3_ENDPOINT_URL),
        region_name="us-east-1",
        aws_access_key_id=os.environ.get(CAPTURE_AWS_ACCESS_KEY_ID, "minio"),
        aws_secret_access_key=os.environ.get(CAPTURE_AWS_SECRET_ACCESS_KEY, "minio-secret"),
    )


def setup_s3(client: S3Client) -> None:
    existing = {
        name for item in client.list_buckets()["Buckets"] if (name := item.get("Name")) is not None
    }

    for bucket in BUCKETS:
        if bucket not in existing:
            client.create_bucket(Bucket=bucket)


def cleanup_s3(client: S3Client) -> None:
    for bucket in BUCKETS:
        objects: list[dict[str, str]] = []
        pages = client.get_paginator("list_objects_v2").paginate(Bucket=bucket)

        for page in pages:
            objects.extend(
                {"Key": item["Key"]}
                for item in page.get("Contents", ())
                if item.get("Key") is not None
            )

        for offset in range(0, len(objects), DELETE_BATCH_SIZE):
            client.delete_objects(
                Bucket=bucket,
                Delete={"Objects": objects[offset : offset + DELETE_BATCH_SIZE], "Quiet": True},
            )


def put_object(client: S3Client, bucket: str, key: str, body: bytes) -> dict[str, Any]:
    return cast(dict[str, Any], client.put_object(Bucket=bucket, Key=key, Body=body))


def read_object(client: S3Client, bucket: str, key: str) -> bytes:
    body = client.get_object(Bucket=bucket, Key=key)["Body"]

    try:
        return body.read()
    finally:
        body.close()


def object_keys(client: S3Client, bucket: str, prefix: str = "") -> tuple[str, ...]:
    pages = client.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix)
    keys: list[str] = []

    for page in pages:
        for item in page.get("Contents", ()):
            key = item.get("Key")

            if key is not None:
                keys.append(key)

    return tuple(keys)
