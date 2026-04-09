output "provider_name" {
  description = "Full WIF provider resource name (set as GitHub secret WIF_PROVIDER)"
  value       = local.provider_name
}

output "pool_name" {
  description = "Workload Identity Pool resource name"
  value       = local.pool_name
}
