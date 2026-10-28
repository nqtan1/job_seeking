# Cloud Run (api, worker pool, migrate job) + service accounts
# Images are pushed by ./deploy.sh build (tags :latest + git sha). Terraform only owns the shape;
# ignore_changes on the image lets `deploy.sh deploy` roll new revisions without drift.

locals {
  image = "${var.region}-docker.pkg.dev/${var.project_id}/recruitai"

  plain_env = {
    ENV                       = var.env
    FIREBASE_PROJECT_ID       = var.project_id
    STORAGE_BACKEND           = "gcs"
    GCS_BUCKET                = google_storage_bucket.files.name
    GOOGLE_GENAI_USE_VERTEXAI = "true"
    GOOGLE_CLOUD_PROJECT      = var.project_id
    GOOGLE_CLOUD_LOCATION     = var.llm_location
    EMAIL_BACKEND             = "brevo"
  }
  # env var -> Secret Manager id (all containers created in main.tf)
  secret_env = {
    DATABASE_URL                 = "recruitai-database-url"
    FRANCE_TRAVAIL_CLIENT_ID     = "recruitai-france-travail-client-id"
    FRANCE_TRAVAIL_CLIENT_SECRET = "recruitai-france-travail-client-secret"
    BREVO_API_KEY                = "recruitai-brevo-api-key"
    ADMIN_EMAILS                 = "recruitai-admin-emails"
  }
  runners = toset(["api", "worker"])

  # Cloud SQL IAM user of a service account = its email without ".gserviceaccount.com".
  db_user = { for k in ["api", "worker", "migrate"] :
    k => trimsuffix(k == "migrate" ? google_service_account.migrate.email : google_service_account.run[k].email, ".gserviceaccount.com")
  }
}

# Owns the schema (DDL); only the migrate job runs as it. The API and worker are data-only.
resource "google_service_account" "migrate" {
  account_id   = "recruitai-migrate"
  display_name = "RecruitAI migrate"
  depends_on   = [google_project_service.api]
}

resource "google_sql_user" "iam" {
  for_each = local.db_user
  name     = each.value
  instance = google_sql_database_instance.main.name
  type     = "CLOUD_IAM_SERVICE_ACCOUNT"
}

resource "google_project_iam_member" "sql_login" {
  for_each = toset(["api", "worker", "migrate"])
  project  = var.project_id
  role     = "roles/cloudsql.instanceUser"
  member   = "serviceAccount:${each.key == "migrate" ? google_service_account.migrate.email : google_service_account.run[each.key].email}"
}

# The migrate job only needs the connection URL, not the other secrets.
resource "google_secret_manager_secret_iam_member" "migrate_read" {
  secret_id = google_secret_manager_secret.app["recruitai-database-url"].id
  role      = "roles/secretmanager.secretAccessor"
  member    = google_service_account.migrate.member
}

# The deploy SA acts as the migrate identity when it updates the job.
resource "google_service_account_iam_member" "deploy_acts_as_migrate" {
  service_account_id = google_service_account.migrate.name
  role               = "roles/iam.serviceAccountUser"
  member             = google_service_account.deploy.member
}

resource "google_compute_subnetwork" "run" {
  name          = "recruitai-run"
  region        = var.region
  network       = google_compute_network.main.id
  ip_cidr_range = "10.200.0.0/24" # must not overlap the Cloud SQL peering range; plan/apply will say if it does
}

resource "google_service_account" "run" {
  for_each     = local.runners
  account_id   = "recruitai-${each.key}"
  display_name = "RecruitAI ${each.key}"
  depends_on   = [google_project_service.api]
}

# Needed to sign GCS URLs without a JSON key (IAM signBlob on itself).
resource "google_service_account_iam_member" "self_token_creator" {
  for_each           = local.runners
  service_account_id = google_service_account.run[each.key].name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = google_service_account.run[each.key].member
}

resource "google_project_iam_member" "run" {
  for_each = {
    for p in setproduct(local.runners, ["roles/aiplatform.user", "roles/firebaseauth.admin"]) :
    "${p[0]}-${p[1]}" => { sa = p[0], role = p[1] }
  }
  project = var.project_id
  role    = each.value.role
  member  = google_service_account.run[each.value.sa].member
}

resource "google_storage_bucket_iam_member" "files" {
  for_each = local.runners
  bucket   = google_storage_bucket.files.name
  role     = "roles/storage.objectAdmin"
  member   = google_service_account.run[each.key].member
}

resource "google_secret_manager_secret_iam_member" "read" {
  for_each = {
    for p in setproduct(local.runners, keys(google_secret_manager_secret.app)) :
    "${p[0]}-${p[1]}" => { sa = p[0], secret = p[1] }
  }
  secret_id = google_secret_manager_secret.app[each.value.secret].id
  role      = "roles/secretmanager.secretAccessor"
  member    = google_service_account.run[each.value.sa].member
}

resource "google_cloud_run_v2_service" "api" {
  count               = var.deploy_run ? 1 : 0
  name                = "recruitai-api"
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = false # stateless; the image is rebuilt from git
  labels              = local.labels

  template {
    service_account = google_service_account.run["api"].email
    timeout         = "120s"
    scaling {
      min_instance_count = var.api_min_instances
      max_instance_count = 3
    }
    vpc_access {
      egress = "PRIVATE_RANGES_ONLY"
      network_interfaces {
        network    = google_compute_network.main.id
        subnetwork = google_compute_subnetwork.run.id
      }
    }
    containers {
      image = "${local.image}/api:latest"
      ports {
        container_port = 8000
      }
      resources {
        limits            = { cpu = "1", memory = "512Mi" }
        cpu_idle          = true # CPU only while a request is in flight (SSE counts); makes a warm instance cheap
        startup_cpu_boost = true # extra CPU only while the container starts: faster Python imports on a cold start
      }
      # Default probing is every 10 s, so a cold start was rounded up to the next 10 s tick
      # (measured: 21 s). Probe every second; keep ~60 s of patience.
      startup_probe {
        period_seconds    = 1
        timeout_seconds   = 1
        failure_threshold = 60
        http_get {
          path = "/health"
        }
      }
      dynamic "env" {
        for_each = local.plain_env
        content {
          name  = env.key
          value = env.value
        }
      }
      dynamic "env" {
        for_each = local.secret_env
        content {
          name = env.key
          value_source {
            secret_key_ref {
              secret  = env.value
              version = "latest"
            }
          }
        }
      }
      env {
        name  = "DB_IAM_AUTH"
        value = "true"
      }
      env {
        name  = "DB_IAM_USER"
        value = local.db_user["api"]
      }
    }
  }
  lifecycle {
    ignore_changes = [template[0].containers[0].image, client, client_version]
  }
  depends_on = [google_secret_manager_secret_iam_member.read]
}

# Auth is enforced in the app (Firebase ID token + App Check); Hosting rewrites need a public invoker.
resource "google_cloud_run_v2_service_iam_member" "api_public" {
  count    = var.deploy_run ? 1 : 0
  name     = google_cloud_run_v2_service.api[0].name
  location = var.region
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# Procrastinate worker: no HTTP port, so a worker pool (ADR 0005), 1 instance, runs the periodic sweeps too.
resource "google_cloud_run_v2_worker_pool" "worker" {
  count               = var.deploy_run ? 1 : 0
  name                = "recruitai-worker"
  location            = var.region
  deletion_protection = false
  labels              = local.labels

  scaling {
    manual_instance_count = 0 # parked; `deploy.sh up` raises it (ignored below)
  }
  template {
    service_account = google_service_account.run["worker"].email
    vpc_access {
      egress = "PRIVATE_RANGES_ONLY"
      network_interfaces {
        network    = google_compute_network.main.id
        subnetwork = google_compute_subnetwork.run.id
      }
    }
    containers {
      image = "${local.image}/worker:latest"
      resources {
        limits = { cpu = "1", memory = "1Gi" } # tectonic (LaTeX) needs headroom
      }
      dynamic "env" {
        for_each = local.plain_env
        content {
          name  = env.key
          value = env.value
        }
      }
      dynamic "env" {
        for_each = local.secret_env
        content {
          name = env.key
          value_source {
            secret_key_ref {
              secret  = env.value
              version = "latest"
            }
          }
        }
      }
      env {
        name  = "DB_IAM_AUTH"
        value = "true"
      }
      env {
        name  = "DB_IAM_USER"
        value = local.db_user["worker"]
      }
    }
  }
  lifecycle {
    ignore_changes = [template[0].containers[0].image, scaling, client, client_version]
  }
  depends_on = [google_secret_manager_secret_iam_member.read]
}

# One-off `alembic upgrade head`; deploy.sh runs it before rolling the api (ARCHITECTURE §6).
resource "google_cloud_run_v2_job" "migrate" {
  count               = var.deploy_run ? 1 : 0
  name                = "recruitai-migrate"
  location            = var.region
  deletion_protection = false
  labels              = local.labels

  template {
    template {
      service_account = google_service_account.migrate.email
      max_retries     = 0
      vpc_access {
        egress = "PRIVATE_RANGES_ONLY"
        network_interfaces {
          network    = google_compute_network.main.id
          subnetwork = google_compute_subnetwork.run.id
        }
      }
      containers {
        image = "${local.image}/api:latest"
        # Procrastinate's own schema is not in Alembic (core/tasks.py docstring). `|| true`: re-applying an
        # existing schema errors, which is fine; real DB failures already stopped `alembic` before it.
        command = ["sh", "-c", "alembic upgrade head && (procrastinate --app=recruitai.worker.app schema --apply || true) && python -m recruitai.core.db_grants"]
        dynamic "env" {
          # No e-mail here: the migrate SA cannot read BREVO_API_KEY, and Settings rejects brevo without it.
          for_each = { for k, v in local.plain_env : k => v if k != "EMAIL_BACKEND" }
          content {
            name  = env.key
            value = env.value
          }
        }
        env {
          name = "DATABASE_URL"
          value_source {
            secret_key_ref {
              secret  = local.secret_env["DATABASE_URL"]
              version = "latest"
            }
          }
        }
        env {
          name  = "DB_IAM_AUTH"
          value = "true"
        }
        env {
          name  = "DB_IAM_USER"
          value = local.db_user["migrate"]
        }
        env {
          name  = "DB_APP_ROLES"
          value = "${local.db_user["api"]},${local.db_user["worker"]}"
        }
      }
    }
  }
  lifecycle {
    ignore_changes = [template[0].template[0].containers[0].image, client, client_version]
  }
  depends_on = [google_secret_manager_secret_iam_member.read, google_secret_manager_secret_iam_member.migrate_read]
}
