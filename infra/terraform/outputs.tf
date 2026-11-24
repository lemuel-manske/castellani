output "archive_artifacts_bucket" {
  value = aws_s3_bucket.archive_artifacts.bucket
}

output "archive_manifests_bucket" {
  value = aws_s3_bucket.archive_manifests.bucket
}

output "auth_profiles_bucket" {
  value = aws_s3_bucket.auth_profiles.bucket
}

