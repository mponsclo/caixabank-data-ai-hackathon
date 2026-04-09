###############################################################################
# KMS — managed by main Terraform after bootstrap creates the keyring + key.
#
# This module imports the existing KMS resources and manages IAM bindings
# for collaborator access to SOPS encryption/decryption.
###############################################################################

data "google_kms_key_ring" "sops" {
  name     = "sops-keyring"
  location = "global"
  project  = var.project_id
}

data "google_kms_crypto_key" "sops" {
  name     = "sops-key"
  key_ring = data.google_kms_key_ring.sops.id
}

# Grant collaborators encrypt + decrypt access for SOPS workflows
resource "google_kms_crypto_key_iam_member" "collaborators" {
  for_each = toset(var.collaborator_emails)

  crypto_key_id = data.google_kms_crypto_key.sops.id
  role          = "roles/cloudkms.cryptoKeyEncrypterDecrypter"
  member        = "user:${each.value}"
}
