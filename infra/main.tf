locals {
  labels = { app = "recruitai", env = var.env }
}

resource "google_project_service" "api" {
  for_each = toset([
    "aiplatform.googleapis.com",
    "artifactregistry.googleapis.com",
    "billingbudgets.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "compute.googleapis.com",
    "run.googleapis.com",
    "firebase.googleapis.com",
    "firebaseappcheck.googleapis.com",
    "firebasehosting.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
    "identitytoolkit.googleapis.com",
    "monitoring.googleapis.com",
    "recaptchaenterprise.googleapis.com",
    "secretmanager.googleapis.com",
    "servicenetworking.googleapis.com",
    "sqladmin.googleapis.com",
  ])
  service            = each.key
  disable_on_destroy = false
}

# Budget alerts: emails go to the billing account admins by default (no channel to manage).
resource "google_billing_budget" "project" {
  billing_account = var.billing_account
  display_name    = "recruitai-${var.env}"

  budget_filter {
    projects = ["projects/${data.google_project.this.number}"]
  }
  amount {
    specified_amount {
      currency_code = "EUR"
      units         = var.budget_amount_eur
    }
  }
  dynamic "threshold_rules" {
    for_each = [0.5, 0.9, 1.0]
    content {
      threshold_percent = threshold_rules.value
    }
  }
  depends_on = [google_project_service.api]
}

data "google_project" "this" {
  depends_on = [google_project_service.api]
}

# ---- P4-02: network, Cloud SQL, secrets, registry ----

resource "google_compute_network" "main" {
  name                    = "recruitai"
  auto_create_subnetworks = false
  depends_on              = [google_project_service.api]
}

# Private services access: lets Cloud SQL get a private IP in this VPC.
resource "google_compute_global_address" "sql_range" {
  name          = "recruitai-sql-range"
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = 20
  network       = google_compute_network.main.id
}

resource "google_service_networking_connection" "sql" {
  network                 = google_compute_network.main.id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.sql_range.name]
}

resource "google_sql_database_instance" "main" {
  name                = "recruitai"
  region              = var.region
  database_version    = "POSTGRES_16"
  deletion_protection = true

  settings {
    tier                        = var.sql_tier
    edition                     = "ENTERPRISE"
    availability_type           = "ZONAL"
    disk_size                   = 10
    disk_autoresize             = true
    deletion_protection_enabled = true
    user_labels                 = local.labels

    ip_configuration {
      ipv4_enabled    = false
      private_network = google_compute_network.main.id
      ssl_mode        = "ENCRYPTED_ONLY"
    }
    backup_configuration {
      enabled                        = true
      point_in_time_recovery_enabled = true
      transaction_log_retention_days = 7
      backup_retention_settings {
        retained_backups = 7
      }
    }
  }
  depends_on = [google_service_networking_connection.sql]
}

resource "google_sql_database" "app" {
  name     = "recruitai"
  instance = google_sql_database_instance.main.name
}

# Containers only. The owner adds the values: gcloud secrets versions add <id> --data-file=-
resource "google_secret_manager_secret" "app" {
  for_each = toset([
    "recruitai-database-url",
    "recruitai-france-travail-client-id",
    "recruitai-france-travail-client-secret",
    "recruitai-brevo-api-key",
    "recruitai-admin-emails",
  ])
  secret_id = each.key
  labels    = local.labels
  replication {
    user_managed {
      replicas {
        location = var.region
      }
    }
  }
  depends_on = [google_project_service.api]
}

resource "google_artifact_registry_repository" "images" {
  repository_id = "recruitai"
  location      = var.region
  format        = "DOCKER"
  labels        = local.labels
  depends_on    = [google_project_service.api]
}

# ---- P4-03: files bucket ----

resource "google_storage_bucket" "files" {
  name                        = "${var.project_id}-files"
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false
  labels                      = local.labels

  # Account deletion must remove files at once (ARCHITECTURE §11.2); no 7-day soft-delete copy.
  soft_delete_policy {
    retention_duration_seconds = 0
  }
  lifecycle_rule {
    condition {
      age            = var.tmp_ttl_days
      matches_prefix = ["tmp/"]
    }
    action {
      type = "Delete"
    }
  }
}
