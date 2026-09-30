import json
from typing import Any

import boto3

# Type of the object boto3.client("s3") returns -- botocore builds it
# dynamically at runtime, so there's no importable class to type-hint
# against directly; callers just need "whatever get_client() returns."
S3Client = Any


def get_client() -> S3Client:
    return boto3.client("s3")


def put_json(client: S3Client, bucket: str, key: str, data: Any) -> None:
    client.put_object(
        Bucket=bucket,
        Key=key,
        Body=json.dumps(data, indent=2).encode("utf-8"),
        ContentType="application/json",
    )
