import os
from typing import Any, cast

from boto3.session import Session
from mypy_boto3_s3.client import S3Client
from mypy_boto3_s3.type_defs import ObjectIdentifierTypeDef

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
        endpoint_url=os.environ.get("CAPTURE_S3_ENDPOINT_URL"),
        region_name="us-east-1",
        aws_access_key_id=os.environ.get("CAPTURE_AWS_ACCESS_KEY_ID", "minio"),
        aws_secret_access_key=os.environ.get("CAPTURE_AWS_SECRET_ACCESS_KEY", "minio-secret"),
    )


def setup_s3(client: S3Client) -> None:
    existing = {
        name for item in client.list_buckets()["Buckets"] if (name := item.get("Name")) is not None
    }

    for bucket in BUCKETS:
        if bucket not in existing:
            client.create_bucket(Bucket=bucket)

        client.put_bucket_versioning(
            Bucket=bucket,
            VersioningConfiguration={"Status": "Enabled"},
        )


def cleanup_s3(client: S3Client) -> None:
    for bucket in BUCKETS:
        objects: list[ObjectIdentifierTypeDef] = []
        pages = client.get_paginator("list_object_versions").paginate(Bucket=bucket)

        for page in pages:
            for entry in (*page.get("Versions", ()), *page.get("DeleteMarkers", ())):
                key = entry.get("Key")
                version_id = entry.get("VersionId")

                if key is None or version_id is None:
                    continue

                objects.append({"Key": key, "VersionId": version_id})

        for offset in range(0, len(objects), DELETE_BATCH_SIZE):
            client.delete_objects(
                Bucket=bucket,
                Delete={"Objects": objects[offset : offset + DELETE_BATCH_SIZE], "Quiet": True},
            )


def put_object(client: S3Client, bucket: str, key: str, body: bytes) -> dict[str, Any]:
    return cast(dict[str, Any], client.put_object(Bucket=bucket, Key=key, Body=body))


def read_object(client: S3Client, bucket: str, key: str, version_id: str | None = None) -> bytes:
    request: dict[str, Any] = {"Bucket": bucket, "Key": key}

    if version_id is not None:
        request["VersionId"] = version_id

    body = client.get_object(**request)["Body"]

    try:
        return body.read()
    finally:
        body.close()


def object_version_ids(client: S3Client, bucket: str, key: str) -> tuple[str, ...]:
    response = client.list_object_versions(Bucket=bucket, Prefix=key)
    versions: list[str] = []

    for item in response.get("Versions", ()):
        item_key = item.get("Key")
        version_id = item.get("VersionId")

        if item_key == key and version_id is not None:
            versions.append(version_id)

    return tuple(versions)


def object_keys(client: S3Client, bucket: str, prefix: str = "") -> tuple[str, ...]:
    pages = client.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix)
    keys: list[str] = []

    for page in pages:
        for item in page.get("Contents", ()):
            key = item.get("Key")

            if key is not None:
                keys.append(key)

    return tuple(keys)
