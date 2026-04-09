variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "Cloud Run region"
  type        = string
}

variable "cloud_run_sa_email" {
  description = "Service account email for Cloud Run runtime identity"
  type        = string
}

variable "image" {
  description = "Container image URL (e.g. REGION-docker.pkg.dev/PROJECT/REPO/api:TAG)"
  type        = string
}
