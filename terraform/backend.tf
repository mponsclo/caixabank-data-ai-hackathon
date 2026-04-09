###############################################################################
# Remote State — GCS bucket created by bootstrap.
#
# Note: The state bucket lives in the same project we manage. This is not best
# practice (a dedicated admin project is preferred), but is acceptable for a
# personal project without an existing admin project.
###############################################################################

terraform {
  backend "gcs" {
    bucket = "mpc-caixabank-ai-tf-state"
    prefix = "terraform/state"
  }
}
