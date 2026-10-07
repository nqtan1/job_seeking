#!/usr/bin/env bash
# Usage: ./deploy.sh <cmd> [env=dev]
# Config = envs/<env>.tfvars (project, region, budget, llm_*). Prod is plan-only: everything but plan/status/logs refuses it.
set -euo pipefail
cd "$(dirname "$0")"
CMD=${1:-help}; ENV=${2:-dev}
V=envs/$ENV.tfvars
[ -f "$V" ] || { echo "missing $V"; exit 1; }
tfv() { sed -n "s/^$1 *= *\"\{0,1\}\([^\"# ]*\).*/\1/p" "$V"; }
P=$(tfv project_id); R=$(tfv region); R=${R:-europe-west9}
API=recruitai-api; WORKER=recruitai-worker; MIGRATE=recruitai-migrate # = run.tf names
IMG=$R-docker.pkg.dev/$P/recruitai
guard() { if [ "$ENV" = prod ]; then echo "prod is plan-only: run terraform by hand"; exit 1; fi; }
tf() { c=$1; shift; terraform init -input=false -backend-config=envs/$ENV.backend.hcl >/dev/null; terraform "$c" -var-file=$V "$@"; }
run() { gcloud run services update "$1" --project "$P" --region "$R" "${@:2}"; }
worker() { gcloud beta run worker-pools update $WORKER --project "$P" --region "$R" "$@"; } # worker = pool, not service

case $CMD in
  plan)   tf plan ;;
  apply)  guard; tf apply ;; # infra only
  build)  # build + push both images, tagged with the git sha; prints the tag
    TAG=$(git rev-parse --short HEAD); gcloud auth configure-docker "$R-docker.pkg.dev" -q >&2
    for s in api worker; do
      docker build -f ../backend/Dockerfile.$s -t "$IMG/$s:$TAG" -t "$IMG/$s:latest" ../backend >&2 && docker push --all-tags "$IMG/$s" >&2
    done; echo "$TAG" ;;
  deploy|redeploy) guard # build, then roll both Cloud Run services to the new image
    TAG=$("$0" build "$ENV" | tail -1)
    gcloud run jobs update $MIGRATE --project "$P" --region "$R" --image "$IMG/api:$TAG"
    gcloud run jobs execute $MIGRATE --project "$P" --region "$R" --wait # schema first, then code
    run $API --image "$IMG/api:$TAG"; worker --image "$IMG/worker:$TAG" ;;
  web)    guard # build the SPA (needs web/.env.production.local) and publish it to Firebase Hosting
    (cd ../web && pnpm install --frozen-lockfile && pnpm build) && (cd .. && npx --yes firebase-tools deploy --only hosting --project "$P") ;;
  smoke)  curl -fsS "$(gcloud run services describe $API --project "$P" --region "$R" --format='value(status.url)')/health"; echo ;;
  down)   guard # reversible stop: API unreachable, worker scaled to 0
    run $API --ingress internal; worker --instances 0 ;;
  up)     guard
    run $API --ingress all; worker --instances 1 ;;
  kill)   guard # emergency: block traffic + stop worker entirely. Deletes nothing; `up` restores.
    run $API --ingress internal; worker --instances 0 ;;
  status) gcloud run services list --project "$P" --region "$R"; gcloud beta run worker-pools list --project "$P" --region "$R" ;;
  logs)   gcloud logging read "resource.type=cloud_run_revision" --project "$P" --limit 30 --freshness 1h \
            --format='value(timestamp,resource.labels.service_name,severity,textPayload)' ;;
  *) sed -n '2,3p' "$0"; echo "cmds: plan apply build deploy redeploy smoke web up down kill status logs" ;;
esac
