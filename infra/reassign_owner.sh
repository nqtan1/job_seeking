#!/usr/bin/env bash
# One-time per env (ADR 0028 step 2): hand schema ownership from the old password user to the
# IAM migrator. Runs a throwaway Cloud Run job in the VPC with the API image. Usage: ./reassign_owner.sh [project]
set -euo pipefail
P=${1:-dev-recruitai}; R=europe-west9
IMG=$R-docker.pkg.dev/$P/recruitai/api:latest
PY=$(cat <<'PYEOF' | base64 -w0
import os, psycopg
u = os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://", 1)
m = '"recruitai-migrate@%s.iam"' % os.environ["P"]
with psycopg.connect(u, autocommit=True) as c:
    c.execute(f"GRANT {m} TO CURRENT_USER")
    c.execute(f"REASSIGN OWNED BY CURRENT_USER TO {m}")
    print("owners:", c.execute("select distinct tableowner from pg_tables where schemaname='public'").fetchall())
PYEOF
)
gcloud run jobs deploy recruitai-own-once --project "$P" --region $R --image "$IMG" \
  --service-account "recruitai-api@$P.iam.gserviceaccount.com" \
  --network recruitai --subnet recruitai-run --vpc-egress private-ranges-only \
  --set-secrets DATABASE_URL=recruitai-database-url:latest --set-env-vars "P=$P" \
  --command sh --args="-c,echo $PY | base64 -d | python -" --max-retries 0
gcloud run jobs execute recruitai-own-once --project "$P" --region $R --wait
gcloud run jobs delete recruitai-own-once --project "$P" --region $R --quiet
