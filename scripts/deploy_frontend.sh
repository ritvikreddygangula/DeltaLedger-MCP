#!/usr/bin/env bash
# Syncs frontend/ to the S3 bucket backing the manually-created CloudFront
# distribution (set up via console rather than IaC, same as RDS). Usage:
#   ./scripts/deploy_frontend.sh <bucket-name> [cloudfront-distribution-id]
set -euo pipefail

BUCKET="${1:?Usage: deploy_frontend.sh <bucket-name> [cloudfront-distribution-id]}"
DISTRIBUTION_ID="${2:-}"

cd "$(dirname "$0")/.."

echo "Syncing frontend/ to s3://${BUCKET}..."
aws s3 sync frontend/ "s3://${BUCKET}" --delete

if [ -n "$DISTRIBUTION_ID" ]; then
  echo "Invalidating CloudFront cache for distribution ${DISTRIBUTION_ID}..."
  aws cloudfront create-invalidation --distribution-id "$DISTRIBUTION_ID" --paths "/*"
else
  echo "No distribution ID given -- skipping CloudFront invalidation."
  echo "Pass it as the second argument once you have it: ./scripts/deploy_frontend.sh ${BUCKET} <distribution-id>"
fi
