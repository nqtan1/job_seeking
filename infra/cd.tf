# ---- P4-06/07: GitHub Actions deploys through Workload Identity Federation (no JSON keys) ----

resource "google_iam_workload_identity_pool" "github" {
  workload_identity_pool_id = "github"
  depends_on                = [google_project_service.api]
}

resource "google_iam_workload_identity_pool_provider" "github" {
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "github"
  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.repository" = "assertion.repository"
  }
  # dev/staging deploys from main; prod only from release tags.
  attribute_condition = var.env == "prod" ? "assertion.repository == '${var.github_repo}' && assertion.ref.startsWith('refs/tags/v')" : "assertion.repository == '${var.github_repo}' && assertion.ref == 'refs/heads/main'"
  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

resource "google_service_account" "deploy" {
  account_id   = "recruitai-deploy"
  display_name = "RecruitAI CI deploy"
  depends_on   = [google_project_service.api]
}

resource "google_service_account_iam_member" "deploy_wif" {
  service_account_id = google_service_account.deploy.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository/${var.github_repo}"
}

resource "google_project_iam_member" "deploy" {
  for_each = toset(["roles/run.developer", "roles/firebasehosting.admin"])
  project  = var.project_id
  role     = each.key
  member   = google_service_account.deploy.member
}

resource "google_artifact_registry_repository_iam_member" "deploy_push" {
  repository = google_artifact_registry_repository.images.name
  location   = var.region
  role       = "roles/artifactregistry.writer"
  member     = google_service_account.deploy.member
}

# Deploying a revision "acts as" the runtime identity; scoped to those two accounts only.
resource "google_service_account_iam_member" "deploy_acts_as" {
  for_each           = local.runners
  service_account_id = google_service_account.run[each.key].name
  role               = "roles/iam.serviceAccountUser"
  member             = google_service_account.deploy.member
}

output "github_vars" {
  description = "Not secrets. Put in GitHub repo variables (per environment)."
  value = {
    GCP_PROJECT  = var.project_id
    GCP_REGION   = var.region
    WIF_PROVIDER = google_iam_workload_identity_pool_provider.github.name
    DEPLOY_SA    = google_service_account.deploy.email
  }
}
