resource "google_cloud_run_v2_service" "api" {
  name     = "caixabank-ai-api"
  location = var.region
  project  = var.project_id

  template {
    service_account = var.cloud_run_sa_email

    containers {
      image = var.image

      ports {
        container_port = 8080
      }

      resources {
        limits = {
          cpu    = "2"
          memory = "2Gi"
        }
      }

      env {
        name  = "AGENT_LLM_BACKEND"
        value = "regex" # Default: regex-only. Set to "vertex" to enable Vertex AI Gemini.
      }

      startup_probe {
        http_get {
          path = "/health"
        }
        initial_delay_seconds = 5
        period_seconds        = 3
        failure_threshold     = 10 # ~30s to load fraud + forecast models
      }

      liveness_probe {
        http_get {
          path = "/health"
        }
        period_seconds = 30
      }
    }

    scaling {
      min_instance_count = 0 # Scale to zero when idle
      max_instance_count = 3 # Modest ceiling for a portfolio project
    }
  }

  traffic {
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
    percent = 100
  }
}

# Public access — portfolio project, no authentication required
resource "google_cloud_run_v2_service_iam_member" "public" {
  name     = google_cloud_run_v2_service.api.name
  location = google_cloud_run_v2_service.api.location
  project  = var.project_id
  role     = "roles/run.invoker"
  member   = "allUsers"
}
