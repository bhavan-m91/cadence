# Restore drill (target: under 60 minutes)

1. Create a scratch database: `createdb cadence_restore`.
2. Fetch the newest object under `daily/` from the R2 bucket and decrypt it: `aws s3 cp s3://$R2_BUCKET/<key> - --endpoint-url $R2_ENDPOINT | age -d -i key.txt > restore.sql`.
3. Load it: `psql cadence_restore < restore.sql`.
4. Point a throwaway API at it (`DATABASE_URL=...cadence_restore`) and run `alembic current` (must be `head`), then `pytest -k invariants` equivalents: call the slice invariant check and compare row counts with production.
5. Record the elapsed time. A drill that exceeds 60 minutes is a launch blocker (PRD Phase 5 gate).

Status: the script and this procedure exist; the first real drill has **not** been run (no production environment yet).
