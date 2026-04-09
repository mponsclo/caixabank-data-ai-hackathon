variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region — Madrid, colocated with CaixaBank business context"
  type        = string
  default     = "europe-southwest1"
}

variable "billing_account" {
  description = "GCP Billing Account ID (used for budget alerts)"
  type        = string
  sensitive   = true
}

variable "github_repo" {
  description = "GitHub repository (owner/repo) for Workload Identity Federation"
  type        = string
  default     = "mponsclo/caixabank-data-ai-hackathon"
}

variable "collaborator_emails" {
  description = "Collaborator emails who need KMS encrypt/decrypt access for SOPS"
  type        = list(string)
  default     = []
}

variable "cloud_run_image" {
  description = "Container image URL for Cloud Run deployment"
  type        = string
  default     = "us-docker.pkg.dev/cloudrun/container/hello"
}
