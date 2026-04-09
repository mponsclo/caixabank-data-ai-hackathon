variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "collaborator_emails" {
  description = "List of collaborator emails who need KMS encrypt/decrypt access for SOPS"
  type        = list(string)
  default     = []
}
