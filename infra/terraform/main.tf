# LOCAL-ONLY resources for the MiniStack emulator. Several settings here are
# deliberately unsafe outside it (force_destroy buckets, an open OpenSearch
# access policy, HTTP endpoints). See README.md before reusing any of this.

locals {
  # MiniStack's fixed emulated account.
  ministack_account_id = "000000000000"
}

resource "aws_dynamodb_table" "coordinator_archives" {
  name         = "coordinator_archive_runs"
  billing_mode = "PAY_PER_REQUEST"

  hash_key = "archiveId"

  attribute {
    name = "archiveId"
    type = "S"
  }

  attribute {
    name = "recoveryKey"
    type = "S"
  }

  attribute {
    name = "updatedAt"
    type = "S"
  }

  global_secondary_index {
    name            = "recoveryKey-updatedAt-index"
    hash_key        = "recoveryKey"
    range_key       = "updatedAt"
    projection_type = "ALL"
  }
}

resource "aws_dynamodb_table" "coordinator_submissions" {
  name         = "coordinator_submission_keys"
  billing_mode = "PAY_PER_REQUEST"

  hash_key = "idempotencyKey"

  attribute {
    name = "idempotencyKey"
    type = "S"
  }

  ttl {
    attribute_name = "expiresAt"
    enabled        = true
  }
}

resource "aws_dynamodb_table" "coordinator_outbox" {
  name         = "coordinator_outbox"
  billing_mode = "PAY_PER_REQUEST"

  hash_key = "messageId"

  attribute {
    name = "messageId"
    type = "S"
  }
}

resource "aws_dynamodb_table" "coordinator_inbox" {
  name         = "coordinator_inbox"
  billing_mode = "PAY_PER_REQUEST"

  hash_key = "messageId"

  attribute {
    name = "messageId"
    type = "S"
  }
}

# Search-owned tables (docs/backend/state-and-recovery.md#search--index-typescript).

# Indexing ledger (ADR-0005, ADR-0019): one item per archive snapshot,
# recording claims, artifact references and terminal indexing outcomes.
resource "aws_dynamodb_table" "search_indexing_ledger" {
  name         = "search_indexing_ledger"
  billing_mode = "PAY_PER_REQUEST"

  hash_key  = "archiveId"
  range_key = "snapshotId"

  attribute {
    name = "archiveId"
    type = "S"
  }

  attribute {
    name = "snapshotId"
    type = "S"
  }
}

# Per-archive publication record (ADR-0027): manifest, publication decision,
# Capture's replay acknowledgment, compensation, indexed counts and
# reconciliation status.
resource "aws_dynamodb_table" "search_publications" {
  name         = "search_publications"
  billing_mode = "PAY_PER_REQUEST"

  hash_key = "archiveId"

  attribute {
    name = "archiveId"
    type = "S"
  }

  attribute {
    name = "reconcilePending"
    type = "S"
  }

  # Sparse: only archives with an outstanding reconciliation request carry
  # `reconcilePending`, so the periodic pass queries just those.
  global_secondary_index {
    name            = "reconcile-pending-index"
    hash_key        = "reconcilePending"
    projection_type = "KEYS_ONLY"
  }
}

# Events Search emits, written in the same transaction as the state they
# report and dispatched with publisher confirms.
resource "aws_dynamodb_table" "search_outbox" {
  name         = "search_outbox"
  billing_mode = "PAY_PER_REQUEST"

  hash_key = "messageId"

  attribute {
    name = "messageId"
    type = "S"
  }

  attribute {
    name = "dispatchPending"
    type = "S"
  }

  # Sparse: only records the broker has not confirmed yet.
  global_secondary_index {
    name            = "dispatch-pending-index"
    hash_key        = "dispatchPending"
    projection_type = "KEYS_ONLY"
  }
}

# Consumed message IDs, recorded after their effect is durable. TTL only
# cleans up old records; deduplication never depends on when they expire.
resource "aws_dynamodb_table" "search_inbox" {
  name         = "search_inbox"
  billing_mode = "PAY_PER_REQUEST"

  hash_key = "messageId"

  attribute {
    name = "messageId"
    type = "S"
  }

  ttl {
    attribute_name = "expiresAt"
    enabled        = true
  }
}

resource "aws_s3_bucket" "archive_artifacts" {
  bucket        = "castellani-archive-artifacts"
  force_destroy = true
}

resource "aws_s3_bucket" "archive_manifests" {
  bucket        = "castellani-archive-manifests"
  force_destroy = true
}

resource "aws_s3_bucket_versioning" "archive_artifacts" {
  bucket = aws_s3_bucket.archive_artifacts.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_versioning" "archive_manifests" {
  bucket = aws_s3_bucket.archive_manifests.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_public_access_block" "archive_artifacts" {
  bucket = aws_s3_bucket.archive_artifacts.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_public_access_block" "archive_manifests" {
  bucket = aws_s3_bucket.archive_manifests.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_opensearch_domain" "archive_search" {
  domain_name    = "castellani-search"
  engine_version = "OpenSearch_2.15"

  cluster_config {
    instance_type  = "t3.small.search"
    instance_count = 1
  }

  ebs_options {
    ebs_enabled = true
    volume_type = "gp3"
    volume_size = 10
  }

  domain_endpoint_options {
    # Local-only: the emulated data plane serves plain HTTP.
    enforce_https = false
  }

  # Local-only: allows any principal. Unacceptable on a real AWS account.
  access_policies = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { AWS = "*" }
      Action    = "es:*"
      Resource  = "arn:aws:es:${var.aws_region}:${local.ministack_account_id}:domain/castellani-search/*"
    }]
  })

  depends_on = [
    aws_dynamodb_table.coordinator_archives,
    aws_dynamodb_table.coordinator_submissions,
    aws_dynamodb_table.coordinator_outbox,
    aws_dynamodb_table.coordinator_inbox,
    aws_s3_bucket.archive_artifacts,
    aws_s3_bucket.archive_manifests,
  ]
}

resource "aws_dynamodb_table" "capture_runs" {
  name         = "capture_runs"
  billing_mode = "PAY_PER_REQUEST"

  hash_key = "archiveId"

  attribute {
    name = "archiveId"
    type = "S"
  }
}

resource "aws_dynamodb_table" "capture_frontier" {
  name         = "capture_frontier"
  billing_mode = "PAY_PER_REQUEST"

  hash_key  = "archiveId"
  range_key = "urlKey"

  attribute {
    name = "archiveId"
    type = "S"
  }

  attribute {
    name = "urlKey"
    type = "S"
  }
}

resource "aws_dynamodb_table" "capture_outbox" {
  name         = "capture_outbox"
  billing_mode = "PAY_PER_REQUEST"

  hash_key = "messageId"

  attribute {
    name = "messageId"
    type = "S"
  }

  attribute {
    name = "status"
    type = "S"
  }

  attribute {
    name = "nextAttemptAt"
    type = "N"
  }

  global_secondary_index {
    name            = "status-nextAttemptAt-index"
    hash_key        = "status"
    range_key       = "nextAttemptAt"
    projection_type = "ALL"
  }
}
