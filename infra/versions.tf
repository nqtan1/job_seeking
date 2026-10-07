terraform {
  required_version = ">= 1.9, < 2.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 7.0"
    }
  }

  # Bucket and prefix come from envs/<env>.backend.hcl:
  #   terraform init -backend-config=envs/dev.backend.hcl
  backend "gcs" {}
}

provider "google" {
  project = var.project_id
  region  = var.region
  # Needed so billingbudgets (and other quota-project APIs) bill this project when using ADC.
  user_project_override = true
  billing_project       = var.project_id
}
