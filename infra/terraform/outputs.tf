output "archive_artifacts_bucket" {
  value = aws_s3_bucket.archive_artifacts.bucket
}

output "archive_manifests_bucket" {
  value = aws_s3_bucket.archive_manifests.bucket
}

output "opensearch_endpoint" {
  value = aws_opensearch_domain.archive_search.endpoint
}

# Stable DNS name of the OpenSearch data-plane container on the Compose
# network. `opensearch_endpoint` is a container IP that can change on restart;
# MiniStack names the container `ministack-opensearch-<sha1(account:region)[:12]>-<domain>`.
output "opensearch_dataplane_url" {
  value = "http://ministack-opensearch-${substr(sha1("${local.ministack_account_id}:${var.aws_region}"), 0, 12)}-${aws_opensearch_domain.archive_search.domain_name}:9200"
}

output "search_ledger_table" {
  value = aws_dynamodb_table.search_index_ledger.name
}
