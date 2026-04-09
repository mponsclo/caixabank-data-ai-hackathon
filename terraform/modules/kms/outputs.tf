output "key_id" {
  description = "KMS crypto key ID for SOPS .sops.yaml configuration"
  value       = data.google_kms_crypto_key.sops.id
}
