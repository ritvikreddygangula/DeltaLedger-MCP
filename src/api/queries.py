import json
import os

from ..storage.s3_store import S3Client


def _require_bucket_from_env() -> str:
    bucket = os.environ.get("S3_BUCKET")
    if not bucket:
        raise RuntimeError(
            "S3_BUCKET is required (the bucket scripts/export_to_s3.py publishes to). "
            "See .env.example."
        )
    return bucket


def list_curated_tickers(client: S3Client, bucket: str | None = None) -> list[str]:
    """'Curated' = 'whatever's already been published to S3' -- no separate
    hardcoded allowlist to maintain. Expanding the curated set happens by
    running the existing CLI scripts plus scripts/export_to_s3.py, never
    through this API. Un-paginated -- fine well past the ~50-70 ticker
    scale this project targets; S3 caps a single list_objects_v2 response
    at 1000 keys, so this would need paginating long before that stops
    being true.
    """
    bucket = bucket or _require_bucket_from_env()
    resp = client.list_objects_v2(Bucket=bucket)
    tickers = []
    for obj in resp.get("Contents", []):
        key = obj["Key"]
        if key.endswith(".json") and not key.startswith("_"):
            tickers.append(key[: -len(".json")])
    return sorted(tickers)


def get_report(client: S3Client, ticker: str, bucket: str | None = None) -> dict | None:
    """Returns the two most recent 10-Ks for a ticker plus every finding for
    that pair, exactly as scripts/export_to_s3.py published it, or None if
    that ticker hasn't been published.
    """
    bucket = bucket or _require_bucket_from_env()
    try:
        obj = client.get_object(Bucket=bucket, Key=f"{ticker.upper()}.json")
    except client.exceptions.NoSuchKey:
        return None
    return json.loads(obj["Body"].read())


def get_finding(client: S3Client, finding_id: int, bucket: str | None = None) -> dict | None:
    """Looks up which ticker's report contains this finding via the
    _index.json scripts/export_to_s3.py publishes alongside every report,
    rather than fetching and scanning every ticker's file for one id.
    """
    bucket = bucket or _require_bucket_from_env()
    try:
        index_obj = client.get_object(Bucket=bucket, Key="_index.json")
    except client.exceptions.NoSuchKey:
        return None
    index = json.loads(index_obj["Body"].read())
    ticker = index.get(str(finding_id))
    if ticker is None:
        return None
    report = get_report(client, ticker, bucket=bucket)
    if report is None:
        return None
    return next((f for f in report["findings"] if f["id"] == finding_id), None)
