output "archive_artifacts_bucket" {
  value = aws_s3_bucket.archive_artifacts.bucket
}
output "archive_manifests_bucket" {
  value = aws_s3_bucket.archive_manifests.bucket
}
output "opensearch_endpoint" {
  value = aws_opensearch_domain.archive_search.endpoint
}
