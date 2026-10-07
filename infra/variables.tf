variable "project_id" {
  type = string
}

variable "env" {
  type        = string
  description = "dev or prod. Prod is plan-only until the owner applies it."
  validation {
    condition     = contains(["dev", "prod"], var.env)
    error_message = "env must be dev or prod."
  }
}

variable "region" {
  type    = string
  default = "europe-west9"
}

variable "billing_account" {
  type        = string
  description = "Billing account id (XXXXXX-XXXXXX-XXXXXX)."
}

variable "budget_amount_eur" {
  type = number
}

variable "sql_tier" {
  type    = string
  default = "db-f1-micro"
}

variable "llm_backend" {
  type    = string
  default = "vertex"
}

variable "llm_model" {
  type    = string
  default = "gemini-3.5-flash"
}

variable "llm_location" {
  type    = string
  default = "eu"
}

variable "tmp_ttl_days" {
  type        = number
  default     = 7
  description = "Lifecycle TTL of the tmp/ prefix (letter previews). 1 in dev to test the rule quickly."
}

variable "github_repo" {
  type        = string
  description = "owner/name allowed to deploy through Workload Identity Federation."
}

variable "alert_email" {
  type        = string
  description = "Where Cloud Monitoring alerts go."
}

variable "deploy_run" {
  type        = bool
  default     = false
  description = "Create the Cloud Run resources. Needs images pushed and all secrets holding a version, so enable it in a second apply."
}
