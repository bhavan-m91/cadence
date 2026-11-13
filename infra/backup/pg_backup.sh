#!/usr/bin/env bash
# Nightly encrypted logical backup to R2 (PRD 4.15). Needs: pg_dump, age, aws-cli (S3-compatible R2 endpoint).
# Env: DATABASE_URL_SYNC (postgresql://...), AGE_RECIPIENT, R2_BUCKET, R2_ENDPOINT, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY
set -euo pipefail
stamp=$(date -u +%Y%m%dT%H%M%SZ)
key="daily/cadence-${stamp}.sql.age"
pg_dump --no-owner --format=plain "$DATABASE_URL_SYNC" | age -r "$AGE_RECIPIENT" \
  | aws s3 cp - "s3://${R2_BUCKET}/${key}" --endpoint-url "$R2_ENDPOINT"
echo "uploaded ${key}"
# Retention (30 daily / 12 monthly) is enforced by an R2 lifecycle rule, not by this script.
