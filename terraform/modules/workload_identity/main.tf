###############################################################################
# Workload Identity Federation — reference outputs for the pool + provider
# created in bootstrap.
#
# The google provider does not expose WIF data sources, so we construct the
# resource names from project number and known IDs.
###############################################################################

data "google_project" "this" {
  project_id = var.project_id
}

locals {
  pool_name     = "projects/${data.google_project.this.number}/locations/global/workloadIdentityPools/github-pool"
  provider_name = "${local.pool_name}/providers/github-provider"
}
