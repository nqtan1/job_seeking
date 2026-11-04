# infra/

One Terraform root, one state prefix per env. `dev` = project `dev-recruitai`. Prod is applied only after the same change is verified in dev.

## One-time bootstrap per project (owner, before the first `init`)
```bash
P=dev-recruitai
gcloud services enable cloudresourcemanager.googleapis.com serviceusage.googleapis.com --project $P
gcloud storage buckets create gs://$P-tfstate --project $P --location europe-west9 \
  --uniform-bucket-level-access --public-access-prevention
gcloud storage buckets update gs://$P-tfstate --versioning
```

## Use
```bash
cd infra
cp envs/dev.tfvars.example envs/dev.tfvars   # edit if needed; *.tfvars is gitignored
terraform init -backend-config=envs/dev.backend.hcl
terraform plan  -var-file=envs/dev.tfvars
terraform apply -var-file=envs/dev.tfvars    # dev only; prod = envs/prod.* once that project exists
```

## Secrets (values are never in Terraform)
`gcloud secrets versions add recruitai-<name> --data-file=- --project <project>`

## Capacity and abuse (ADR-less notes)

- Traffic reaches Cloud Run through Firebase Hosting rewrites, not a load balancer, so Cloud Armor cannot be attached
  without changing that architecture. The protections are: App Check, per-user and global limits in the app,
  `api_max_instances` (cost ceiling under a flood) and Hosting's own edge.
- Connection budget: `api_max_instances x 10 + 10` (worker) must stay under the Cloud SQL `max_connections` of `sql_tier`.
  `db-f1-micro` is the tightest; raise `sql_tier` before raising `api_max_instances` or the worker's `--concurrency`.
- Suggested prod values (plan only, by hand): `api_min_instances = 1`, `sql_tier` one step above `db-f1-micro`.
