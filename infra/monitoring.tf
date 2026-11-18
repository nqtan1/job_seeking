# alerts from handbook 04 §5 (email only)
# New error types: Sentry (ADR 0040). Not yet covered: queue backlog, DB connections, daily AI spend.

resource "google_monitoring_notification_channel" "email" {
  display_name = "recruitai-${var.env}"
  type         = "email"
  labels       = { email_address = var.alert_email }
  depends_on   = [google_project_service.api]
}

resource "google_logging_metric" "task_failed" {
  name   = "recruitai_task_failed"
  filter = "resource.type=\"cloud_run_worker_pool\" AND jsonPayload.message=\"task_failed\""
  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
  }
}

locals {
  run_api = "resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"recruitai-api\""
  alerts = {
    api_5xx = {
      name = "API 5xx rate > 2% (5 min)"
      cond = {
        filter      = "${local.run_api} AND metric.type=\"run.googleapis.com/request_count\" AND metric.labels.response_code_class=\"5xx\""
        denominator = "${local.run_api} AND metric.type=\"run.googleapis.com/request_count\""
        aligner     = "ALIGN_RATE"
        threshold   = 0.02
        duration    = "300s"
      }
    }
    api_p95 = {
      name = "API p95 latency > 5 s (10 min)"
      cond = {
        filter      = "${local.run_api} AND metric.type=\"run.googleapis.com/request_latencies\""
        denominator = null
        aligner     = "ALIGN_PERCENTILE_95"
        threshold   = 5000
        duration    = "600s"
      }
    }
    sql_cpu = {
      name = "Cloud SQL CPU > 80% (15 min)"
      cond = {
        filter      = "resource.type=\"cloudsql_database\" AND metric.type=\"cloudsql.googleapis.com/database/cpu/utilization\""
        denominator = null
        aligner     = "ALIGN_MEAN"
        threshold   = 0.8
        duration    = "900s"
      }
    }
    sql_disk = {
      name = "Cloud SQL storage > 80%"
      cond = {
        filter      = "resource.type=\"cloudsql_database\" AND metric.type=\"cloudsql.googleapis.com/database/disk/utilization\""
        denominator = null
        aligner     = "ALIGN_MEAN"
        threshold   = 0.8
        duration    = "300s"
      }
    }
    tasks_failed = {
      name = "More than 5 failed tasks in an hour"
      cond = {
        filter      = "metric.type=\"logging.googleapis.com/user/${google_logging_metric.task_failed.name}\" AND resource.type=\"cloud_run_worker_pool\""
        denominator = null
        aligner     = "ALIGN_SUM"
        threshold   = 5
        duration    = "0s"
      }
    }
  }
}

resource "google_monitoring_alert_policy" "this" {
  for_each              = local.alerts
  display_name          = "recruitai-${var.env}: ${each.value.name}"
  combiner              = "OR"
  notification_channels = [google_monitoring_notification_channel.email.id]
  user_labels           = local.labels

  conditions {
    display_name = each.value.name
    condition_threshold {
      filter             = each.value.cond.filter
      denominator_filter = each.value.cond.denominator
      comparison         = "COMPARISON_GT"
      threshold_value    = each.value.cond.threshold
      duration           = each.value.cond.duration
      aggregations {
        alignment_period     = each.key == "tasks_failed" ? "3600s" : "60s"
        per_series_aligner   = each.value.cond.aligner
        cross_series_reducer = each.value.cond.denominator == null ? null : "REDUCE_SUM"
      }
      dynamic "denominator_aggregations" {
        for_each = each.value.cond.denominator == null ? [] : [1]
        content {
          alignment_period     = "60s"
          per_series_aligner   = "ALIGN_RATE"
          cross_series_reducer = "REDUCE_SUM"
        }
      }
    }
  }
}

# SLOs (plan R / P3, Google SRE Workbook ch. 2), 28-day window. Error-budget rule: docs/handbook/runbooks.md §1.
# Latency counts reads only: the AI and streaming routes are POSTs, and /jobs/search waits on the job board.
resource "google_logging_metric" "read_latency" {
  name   = "recruitai_read_latency"
  filter = "resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"recruitai-api\" AND jsonPayload.message=\"http_request\" AND jsonPayload.method=\"GET\" AND NOT jsonPayload.path:\"/jobs/search\""
  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "DISTRIBUTION"
    unit        = "ms"
  }
  value_extractor = "EXTRACT(jsonPayload.duration_ms)"
  bucket_options {
    explicit_buckets { bounds = [100, 250, 500, 1000, 2500, 5000] }
  }
}

resource "google_monitoring_custom_service" "api" {
  service_id   = "recruitai-api"
  display_name = "RecruitAI API"
}

locals {
  slos = {
    availability = { name = "99.5% of API requests succeed (not 5xx)", goal = 0.995 }
    read_latency = { name = "95% of reads answer in under 1 s", goal = 0.95 }
  }
}

resource "google_monitoring_slo" "api" {
  for_each            = local.slos
  service             = google_monitoring_custom_service.api.service_id
  slo_id              = replace(each.key, "_", "-")
  display_name        = each.value.name
  goal                = each.value.goal
  rolling_period_days = 28

  request_based_sli {
    dynamic "good_total_ratio" {
      for_each = each.key == "availability" ? [1] : []
      content {
        bad_service_filter   = "${local.run_api} AND metric.type=\"run.googleapis.com/request_count\" AND metric.labels.response_code_class=\"5xx\""
        total_service_filter = "${local.run_api} AND metric.type=\"run.googleapis.com/request_count\""
      }
    }
    dynamic "distribution_cut" {
      for_each = each.key == "read_latency" ? [1] : []
      content {
        distribution_filter = "metric.type=\"logging.googleapis.com/user/${google_logging_metric.read_latency.name}\" AND resource.type=\"cloud_run_revision\""
        range { max = 1000 }
      }
    }
  }
}

# Fast burn: at 10x, a 28-day budget is gone in under 3 days. Page by e-mail.
resource "google_monitoring_alert_policy" "slo_burn" {
  for_each              = local.slos
  display_name          = "recruitai-${var.env}: SLO burning fast: ${each.value.name}"
  combiner              = "OR"
  notification_channels = [google_monitoring_notification_channel.email.id]
  user_labels           = local.labels
  conditions {
    display_name = "burn rate > 10 over 1 h"
    condition_threshold {
      filter          = "select_slo_burn_rate(\"${google_monitoring_slo.api[each.key].id}\", \"3600s\")"
      comparison      = "COMPARISON_GT"
      threshold_value = 10
      duration        = "0s"
    }
  }
}

resource "google_monitoring_uptime_check_config" "health" {
  count        = var.deploy_run ? 1 : 0
  display_name = "recruitai-${var.env} /health"
  timeout      = "10s"
  period       = "300s"
  http_check {
    path    = "/health"
    use_ssl = true
  }
  monitored_resource {
    type   = "uptime_url"
    labels = { project_id = var.project_id, host = trimprefix(google_cloud_run_v2_service.api[0].uri, "https://") }
  }
}

resource "google_monitoring_alert_policy" "uptime" {
  count                 = var.deploy_run ? 1 : 0
  display_name          = "recruitai-${var.env}: /health is down"
  combiner              = "OR"
  notification_channels = [google_monitoring_notification_channel.email.id]
  user_labels           = local.labels
  conditions {
    display_name = "uptime check failing (10 min)"
    condition_threshold {
      filter          = "metric.type=\"monitoring.googleapis.com/uptime_check/check_passed\" AND resource.type=\"uptime_url\" AND metric.labels.check_id=\"${google_monitoring_uptime_check_config.health[0].uptime_check_id}\""
      comparison      = "COMPARISON_GT"
      threshold_value = 1
      duration        = "600s"
      aggregations {
        alignment_period     = "300s"
        per_series_aligner   = "ALIGN_NEXT_OLDER"
        cross_series_reducer = "REDUCE_COUNT_FALSE"
        group_by_fields      = ["resource.label.host"]
      }
    }
  }
}
