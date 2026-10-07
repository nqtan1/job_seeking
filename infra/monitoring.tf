# ---- P4-08: alerts from handbook 04 §5 (email only) ----
# Not yet covered: new-error-type (Error Reporting), queue backlog, DB connections, daily AI spend.

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
